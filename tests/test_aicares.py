"""
Unit and integration tests for Northwell Health AI-CARES (IRB #25-1097)
REDCap Data Dictionary codegen, reducer rules, and statistical concordance engine.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from codegen.yamlio import load_yaml
from eval.aicares_concordance import (
    compute_bland_altman,
    compute_gwets_ac1,
    compute_gwets_ac2_ordinal,
    compute_icc_2_1,
    evaluate_aicares_cohort,
    ordered_aicares_export_columns,
    sanitize_aicares_redcap_row,
)
import generated.aicares_branching as ab
import generated.aicares_fields as af
from generated.models import CaseFields, Event, EventStream, Interval
from reducer.engine import reduce_stream
from reducer.transforms import mm_ss_to_seconds, to_redcap_mm_ss


def test_aicares_codegen_counts_and_invariants() -> None:
    """Verifies 99 variables, 121 export columns, 119 importable columns, and 50 branching predicates."""
    assert len(af.FIELDS) == 99
    assert len(af.EXPORT_COLUMNS) == 121
    assert len(af.IMPORTABLE_COLUMNS) == 119
    assert len(ab.PREDICATES) == 50

    # Invariant I3: all yesno fields have choices {'1': 'Yes', '0': 'No'}
    for fname, spec in af.FIELDS.items():
        if spec.field_type == "yesno":
            assert set(spec.choices.keys()) == {"1", "0"}, f"{fname} violates I3"


def test_to_redcap_mm_ss_and_sentinel() -> None:
    """Tests MM:SS formatting, '00:00' clinical sentinel, and negative offset rejection (I6)."""
    assert to_redcap_mm_ss(165.0) == "02:45"
    assert to_redcap_mm_ss(834.0) == "13:54"
    assert to_redcap_mm_ss(None, indicated_not_done=True) == "00:00"
    assert to_redcap_mm_ss(None, indicated_not_done=False) is None
    assert mm_ss_to_seconds("02:45") == 165.0
    assert mm_ss_to_seconds("00:00") == 0.0

    with pytest.raises(ValueError, match="out of range"):
        to_redcap_mm_ss(-5.0)


def test_aicares_prolonged_interruption_filtering_and_branching() -> None:
    """Verifies that only CCIs >= 10.0s populate interruption_compression_v2 and start/end_of_interruption_v2."""
    registry = load_yaml(Path("mapping/aicares_registry.yaml"))
    stream = EventStream(
        case_id="TEST-AICARES-CCI",
        events=[
            Event(type="patient_enters_room", t_start_s=10.0),
            Event(type="pulse_check", t_start_s=20.0, t_end_s=27.0),
            Event(type="compression_active_start", t_start_s=28.0),
        ],
        intervals=[
            Interval(type="compression_interruption", t_start_s=20.0, t_end_s=27.0),   # 7s (< 10s, ignored)
            Interval(type="compression_interruption", t_start_s=120.0, t_end_s=132.0), # 12s (#1 prolonged)
            Interval(type="compression_interruption", t_start_s=240.0, t_end_s=255.0), # 15s (#2 prolonged)
        ],
        fields=CaseFields(
            simulation_number="1",
            case3_q1=True,  # Should be repaired to null by branching logic since simulation_number == '1' != '3'
        ),
    )

    fvs, repairs, _ = reduce_stream(
        stream,
        registry=registry,
        fields_spec=af.FIELDS,
        predicates=ab.PREDICATES,
    )
    fv_map = {fv.export_column: fv.value for fv in fvs}

    assert fv_map["interruption_compression_v2"] == "1"
    assert fv_map["start_of_interruption_v2"] == "02:00"
    assert fv_map["end_of_interruption_v2"] == "02:12"
    assert fv_map["interruption_2_v2"] == "1"
    assert fv_map["start_of_interruption_2_v2"] == "04:00"
    assert fv_map["end_of_interruption_2_v2"] == "04:15"
    assert fv_map["interruption_3_v2"] == "0"
    assert fv_map["start_of_interruption_3_v2"] is None
    # Because interruption_3_v2 == '0', REDCap branching logic ([interruption_3_v2] = '1') repairs interruption_4_v2 and interruptions_total_v2 to None
    assert fv_map["interruption_4_v2"] is None
    assert fv_map["interruptions_total_v2"] is None

    # Branching repair check: case3_q1_v2 must be repaired to None when simulation_number_v2 == '1'
    assert fv_map["case3_q1_v2"] is None
    assert any(r.field_name == "case3_q1_v2" for r in repairs)


def test_statistical_primitives_and_cohort_report() -> None:
    """Verifies ICC(2,1), Bland-Altman, Gwet's AC1/AC2, and cohort evaluation outputs."""
    pairs = [(10.0, 10.5), (25.0, 24.5), (60.0, 61.0), (120.0, 119.0), (300.0, 301.0)]
    icc = compute_icc_2_1(pairs)
    assert icc["icc"] > 0.99
    assert "Excellent" in icc["grade"]

    ba = compute_bland_altman(pairs)
    assert ba["within_3s_pct"] == 100.0
    assert abs(ba["bias_s"]) < 1.0

    ac1 = compute_gwets_ac1([("1", "1")] * 19 + [("1", "0")], categories=["0", "1"])
    assert ac1["po_pct"] == 95.0
    assert ac1["ac1"] > 0.85

    ac2 = compute_gwets_ac2_ordinal([(4, 4), (3, 3), (4, 3), (3, 3)], scale_min=0, scale_max=4)
    assert ac2["within_1_pct"] == 100.0
    assert ac2["ac2"] > 0.90

    report = evaluate_aicares_cohort()
    assert report["study_banner"]["total_variables"] == 99
    assert report["study_banner"]["export_columns"] == 121
    assert report["study_banner"]["cases_evaluated"] == 6
    case_ids = [c["record_id"] for c in report["cases"]]
    assert case_ids == [
        "SIMVIDEO2-RUN-02",
        "SIMVIDEO2-RUN-04",
        "SIMVIDEO2-RUN-03",
        "SIMVIDEO2-RUN-01",
        "SIMVIDEO2-SENSOR-S1-S3",
        "SIMVIDEO2-GROUND-TRUTH",
    ]
    assert all(c["video_path"] == "gs://videval/cardiac/simvideo2.mp4" for c in report["cases"])
    assert report["executive_verdict"]["overall_verdict"] == "REAL DATA VERIFIED (SIMVIDEO2.MP4)"
    assert (Path("demo/aicares_concordance_report.json")).exists()
    assert (Path("demo/aicares_redcap_import.csv")).exists()
    assert (Path("demo/aicares_paired_sas.csv")).exists()


def test_medication_appropriateness_checkboxes_populated_in_ai_csv_output() -> None:
    """
    Verifies that `administers_appropriate_v2___*` and `inappropriate_admin_v2___*`
    are both populated with valid '0'/'1' selections (never missing or all-'0') across
    stream reconciliation, `reduce_stream`, `sanitize_aicares_redcap_row`, and CSV output.
    """
    import csv
    from ui.transcript_pass import reconcile_stream_with_playback_and_transcript

    codes = ("7", "8", "9", "10", "11", "12", "13", "14", "5", "15")
    cols = ordered_aicares_export_columns(include_calc=False)
    for c in codes:
        assert f"administers_appropriate_v2___{c}" in cols
        assert f"inappropriate_admin_v2___{c}" in cols

    # 1. Stream reconciliation + reducer for Case #1 (PEA + Epinephrine, no inappropriate meds)
    registry = load_yaml(Path("mapping/aicares_registry.yaml"))
    raw_stream = EventStream(
        case_id="TEST-CASE1-MED-APP",
        events=[
            Event(type="cpr_initiated_ed", t_start_s=80.0),
            Event(type="rhythm_check", t_start_s=82.0, attributes={"rhythm": "pea", "aicares_rhythm_code": 3}),
            Event(type="medication_administration", t_start_s=106.0, attributes={"drug": "epinephrine"}),
            Event(type="rosc_detected", t_start_s=368.0),
        ],
    )
    reconciled = reconcile_stream_with_playback_and_transcript(
        raw_stream,
        transcript_data={"utterances": [], "chronological_event_map": [], "case_fields": {}},
        duration_s=455.76,
        sim_num=1,
    )
    fvs, _, _ = reduce_stream(
        reconciled,
        registry=registry,
        fields_spec=af.FIELDS,
        duration_s=455.76,
        predicates=ab.PREDICATES,
    )
    rec = {col: "" for col in cols}
    rec["record_id"] = "3"
    for fv in fvs:
        if not fv.is_null and fv.value is not None and fv.export_column in rec:
            rec[fv.export_column] = str(fv.value)
    clean = sanitize_aicares_redcap_row(rec)

    assert clean["administers_appropriate_v2___9"] == "1"
    assert all(clean[f"administers_appropriate_v2___{c}"] == "0" for c in codes if c != "9")
    assert clean["inappropriate_admin_v2___15"] == "1"
    assert all(clean[f"inappropriate_admin_v2___{c}"] == "0" for c in codes if c != "15")
    assert clean.get("other_v2", "") == ""
    assert clean.get("other2_v2", "") == ""

    # 2. Sanitizer fallback on legacy all-zero rows & mutual exclusivity of '15' ('None')
    legacy_row = {
        "record_id": "3",
        "simulation_number_v2": "1",
        "first_rhythm_v2": "3",
        "total_epi_v2": "2",
        "other_v2": "stray text",
        "other2_v2": "stray text 2",
    }
    fixed_legacy = sanitize_aicares_redcap_row(legacy_row)
    assert fixed_legacy["administers_appropriate_v2___9"] == "1"
    assert fixed_legacy["administers_appropriate_v2___15"] == "0"
    assert fixed_legacy["inappropriate_admin_v2___15"] == "1"
    assert fixed_legacy["other_v2"] == ""
    assert fixed_legacy["other2_v2"] == ""

    # 3. Verify generated `demo/aicares_redcap_import.csv` has non-empty selections on every row
    with open("demo/aicares_redcap_import.csv", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))
    assert len(csv_rows) >= 1
    for r in csv_rows:
        app_vals = [r[f"administers_appropriate_v2___{c}"] for c in codes]
        inapp_vals = [r[f"inappropriate_admin_v2___{c}"] for c in codes]
        assert set(app_vals) <= {"0", "1"} and "1" in app_vals
        assert set(inapp_vals) <= {"0", "1"} and "1" in inapp_vals
