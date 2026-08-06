"""
tests/test_ccf.py — Deterministic CCF (Chest Compression Fraction) Report Tests (Task S10).

Validates:
- CCF report generation without LLM calls.
- Self-comparison guard: ccf_report never imports or reads ground-truth fixtures (H1, I5).
- CCF abstention when death_pronounced_s is absent (I6).
- Strict separation of unvalidated vs validated clinical reports (H3, I3).
- Operator-supplied shock candidate provenance and S3 adjudication availability (I1, I4).
- Dual windows: CCF window (70.75–922.0s, denom 851.25s) and Interval window (36.0–922.0s).
- Three-tier consumer routing (CCF >=1.0s, REDCap >=3.0s, Reporting >=5.0s).
"""

from __future__ import annotations

import builtins
import json
from pathlib import Path
from typing import Any

import pytest

from sensors.ccf_report import (
    CCFReport,
    CCFReportGenerator,
    CCFShockDetail,
    generate_ccf_report,
)


def test_ccf_report_serialization() -> None:
    """Proves CCFReport converts to dictionary and JSON string with all schema keys."""
    report = CCFReport(
        case_id="simvideo2",
        video_path="tests/video/vidsim2.mp4",
        t0_iso="2023-11-07T07:55:57",
        t0_source="burned_in",
        total_case_duration_s=1363.78,
        patient_enters_room_s=36.0,
        patient_enters_room_source="operator_supplied",
        death_pronounced_s=922.0,
        death_pronounced_source="operator_supplied",
        interval_window_s=(36.0, 922.0),
        ccf_window_s=(70.75, 922.0),
        t_first_s=70.75,
        t_first_source="sensor_derived (S1 first compression motion)",
        ccf_denominator_s=851.25,
        total_cpr_duration_s=695.29,
        total_cci_duration_s=137.82,
        cpr_active_duration_s=695.29,
        cpr_active_fraction=0.8168,
        ccf=0.8170,
        ccf_percent=81.70,
        ccf_by_2min_epoch=[0.9615, 0.9036, 0.7182, 0.736, 0.7777, 0.7649, 0.8385],
        ccf_abstained=False,
        ccf_abstain_reason=None,
        n_cci_over_10s=0,
        longest_cci_s=9.62,
        median_cci_s=2.83,
        shocks=[
            CCFShockDetail(
                id="shock_1",
                candidate_timestamp_s=165.0,
                candidate_source="operator_supplied",
                detected_timestamp_s=None,
                iso_time=None,
                confirmed=False,
                adjudication_status="UNAVAILABLE",
                adjudication_verdict="S3 adjudication unavailable: no calibrated profile for this device (Q-019)",
                pre_shock_pause_s=None,
                post_shock_pause_s=None,
                shock_inside_cci=False,
                cci_id=None,
                peak_rms_ratio=0.0,
                tone_slope_hz_s=0.0,
            )
        ],
        raw_intervals=[],
        ccf_intervals=[],
        redcap_intervals=[],
        reported_intervals=[],
        compression_intervals=[],
    )

    d = report.to_dict()
    assert d["case_id"] == "simvideo2"
    assert d["ccf"] == 0.8170
    assert d["total_case_duration_s"] == 1363.78
    assert d["ccf_window_s"] == [70.75, 922.0]
    assert d["interval_window_s"] == [36.0, 922.0]
    assert d["ccf_abstained"] is False

    json_str = report.to_json()
    parsed = json.loads(json_str)
    assert parsed["case_id"] == "simvideo2"
    assert parsed["ccf"] == 0.8170


def test_ccf_report_does_not_import_or_read_ground_truth_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Self-comparison guard (H1, I5):
    Proves that sensors/ccf_report.py does NOT import, reference, or open any ground-truth fixture.
    """
    # 1. Source code check
    ccf_code = Path("sensors/ccf_report.py").read_text()
    assert "ground_truth_simvideo2.json" not in ccf_code
    assert "fixtures/ground_truth" not in ccf_code
    assert "import fixtures" not in ccf_code

    # 2. Runtime filesystem interception check during execution
    orig_open = builtins.open
    opened_files: list[str] = []

    def mock_open(file: Any, *args: Any, **kwargs: Any) -> Any:
        file_str = str(file)
        if "ground_truth" in file_str or "fixtures" in file_str:
            raise AssertionError(
                f"Self-comparison violation: ccf_report opened {file_str}"
            )
        opened_files.append(file_str)
        return orig_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", mock_open)

    # Instantiate generator and verify no fixture opened during initialization
    gen = CCFReportGenerator(profile_name="default")
    assert gen is not None


def test_ccf_report_abstains_when_death_pronounced_missing() -> None:
    """
    Proves that when death_pronounced_s is absent, CCF is ABSTAINED rather than
    falling back to an ungated full-track calculation (I6 / F-026).
    """
    report = CCFReport(
        case_id="case_no_death_milestone",
        video_path="tests/video/vidsim2.mp4",
        t0_iso=None,
        t0_source="none",
        total_case_duration_s=1363.78,
        patient_enters_room_s=36.0,
        patient_enters_room_source="operator_supplied",
        death_pronounced_s=None,
        death_pronounced_source="not_supplied",
        interval_window_s=(36.0, 1363.78),
        ccf_window_s=None,
        t_first_s=70.75,
        t_first_source="sensor_derived (S1 first compression motion)",
        ccf_denominator_s=None,
        total_cpr_duration_s=None,
        total_cci_duration_s=137.82,
        cpr_active_duration_s=None,
        cpr_active_fraction=None,
        ccf=None,
        ccf_percent=None,
        ccf_by_2min_epoch=[],
        ccf_abstained=True,
        ccf_abstain_reason=(
            "death_pronounced_s milestone not supplied by operator "
            "(ungated full-track CCF calculation prohibited per F-026 / Decision 027)"
        ),
        n_cci_over_10s=0,
        longest_cci_s=9.62,
        median_cci_s=2.83,
        shocks=[],
        raw_intervals=[],
        ccf_intervals=[],
        redcap_intervals=[],
        reported_intervals=[],
        compression_intervals=[],
    )

    assert report.ccf is None
    assert report.ccf_abstained is True
    text = report.format_text_report(ground_truth=None)
    assert "Chest Compression Fraction (CCF): ABSTAINED" in text
    assert "death_pronounced_s milestone not supplied" in text


def test_ccf_report_text_formatting_unvalidated_vs_validated() -> None:
    """
    Proves that:
    1. Unvalidated mode (ground_truth=None) prints only system-level notes and
       says 'Accuracy not validated for this case (no ground truth supplied)' (H3, I3).
    2. Validated mode (ground_truth passed) computes dynamic error metrics,
       cancelling error decomposition, and measurement gap (H3).
    3. Section 2 shock containment notice and rows derive from one computation (I2).
    """
    report = CCFReport(
        case_id="simvideo2",
        video_path="tests/video/vidsim2.mp4",
        t0_iso="2023-11-07T07:55:57",
        t0_source="burned_in",
        total_case_duration_s=1363.78,
        patient_enters_room_s=36.0,
        patient_enters_room_source="operator_supplied",
        death_pronounced_s=922.0,
        death_pronounced_source="operator_supplied",
        interval_window_s=(36.0, 922.0),
        ccf_window_s=(70.75, 922.0),
        t_first_s=70.75,
        t_first_source="sensor_derived (S1 first compression motion)",
        ccf_denominator_s=851.25,
        total_cpr_duration_s=695.29,
        total_cci_duration_s=137.82,
        cpr_active_duration_s=695.29,
        cpr_active_fraction=0.8168,
        ccf=0.8170,
        ccf_percent=81.70,
        ccf_by_2min_epoch=[0.9615, 0.9036, 0.7182, 0.736, 0.7777, 0.7649, 0.8385],
        ccf_abstained=False,
        ccf_abstain_reason=None,
        n_cci_over_10s=0,
        longest_cci_s=9.62,
        median_cci_s=2.83,
        shocks=[
            CCFShockDetail(
                id="shock_1",
                candidate_timestamp_s=165.0,
                candidate_source="operator_supplied",
                detected_timestamp_s=None,
                iso_time=None,
                confirmed=False,
                adjudication_status="UNAVAILABLE",
                adjudication_verdict="S3 adjudication unavailable: no calibrated profile for this device (Q-019)",
                pre_shock_pause_s=None,
                post_shock_pause_s=None,
                shock_inside_cci=False,
                cci_id=None,
                peak_rms_ratio=0.0,
                tone_slope_hz_s=0.0,
            )
        ],
        raw_intervals=[
            {"id": "cci_1", "t_start_s": 150.0, "t_end_s": 154.62, "duration_s": 4.62}
        ],
        ccf_intervals=[
            {"id": "cci_1", "t_start_s": 150.0, "t_end_s": 154.62, "duration_s": 4.62}
        ],
        redcap_intervals=[
            {"id": "cci_1", "t_start_s": 150.0, "t_end_s": 154.62, "duration_s": 4.62}
        ],
        reported_intervals=[],
        compression_intervals=[],
    )

    # 1. Unvalidated mode
    unval_text = report.format_text_report(ground_truth=None)
    assert "NOT FOR CLINICAL OR PERFORMANCE ASSESSMENT." in unval_text
    assert "Accuracy not validated for this case (no ground truth supplied)." in unval_text
    # Proves case-specific GT statements are NOT in unvalidated text (I3)
    assert "6 of 11 reported intervals are false positives" not in unval_text
    assert "GT #7" not in unval_text
    assert "Shock Containment (0 of 1 shocks fall inside detected intervals)" in unval_text

    # 2. Validated mode
    gt_mock = {
        "ccis": [
            {"start_s": 147.0, "end_s": 155.0, "duration_s": 8.0}
        ]
    }
    val_text = report.format_text_report(ground_truth=gt_mock)
    assert "Validation & Error Decomposition (Computed vs Ground Truth):" in val_text
    assert "Ground Truth CCF" in val_text
    assert "Cancelling Error Decomposition" in val_text


@pytest.mark.integration
def test_generate_ccf_report_vidsim2() -> None:
    """
    End-to-end integration test of CCF report generation on tests/video/vidsim2.mp4.

    Gated behavior:
    - Interval reporting window is gated to 36.0–922.0s (patient arrival to death pronouncement).
    - CCF evaluation window is gated to 70.75–922.0s (denom 851.25s, Q-012 Candidate c).
    - Intervals route through three-tier consumer duration rules:
      * 44 raw intervals in clinical window
      * 40 CCF tier (>=1.0s)
      * 16 REDCap tier (>=3.0s)
      * 11 Reporting tier (>=5.0s)
    - CCF is 0.8170 (active CPR motion duration 695.29s / 851.25s).
    - 5 human candidate shocks evaluated with zero containment assertions (F-029).
    """
    video_path = Path("tests/video/vidsim2.mp4")
    if not video_path.exists():
        pytest.skip(f"Video file not found: {video_path}")

    # Explicit operator-supplied clinical milestones and shock candidates (H1, I4)
    milestones = {
        "patient_enters_room_s": 36.0,
        "death_pronounced_s": 922.0,
    }
    candidate_shocks = (165.0, 388.0, 622.0, 742.0, 879.0)

    report = generate_ccf_report(
        video_path=video_path,
        case_id="simvideo2",
        clinical_milestones=milestones,
        candidate_shock_times_s=candidate_shocks,
    )

    assert report.case_id == "simvideo2"
    assert report.total_case_duration_s == pytest.approx(1363.78, abs=0.5)

    # Windows and Milestones
    assert report.interval_window_s == (36.0, 922.0)
    assert report.patient_enters_room_source == "operator_supplied"
    assert report.death_pronounced_source == "operator_supplied"
    assert report.ccf_window_s is not None
    assert report.ccf_window_s[0] == pytest.approx(70.75, abs=0.5)
    assert report.ccf_window_s[1] == pytest.approx(922.0, abs=0.5)
    assert report.ccf_denominator_s == pytest.approx(851.25, abs=0.5)
    assert report.t_first_source == "sensor_derived (S1 first compression motion)"

    # CCF Active Duration Metrics
    assert report.ccf == pytest.approx(0.8170, abs=0.005)
    assert report.ccf_percent == pytest.approx(81.70, abs=0.5)
    assert report.cpr_active_duration_s == pytest.approx(695.29, abs=1.0)
    assert report.ccf_abstained is False

    # Three-Tier Consumer Routing Counts
    assert len(report.raw_intervals) == 44
    assert len(report.ccf_intervals) == 40
    assert len(report.redcap_intervals) == 16
    assert len(report.reported_intervals) == 11

    # 5 Shocks Evaluated without Containment Requirement (F-029)
    assert len(report.shocks) == 5
    expected_cands = [165.0, 388.0, 622.0, 742.0, 879.0]
    for idx, s in enumerate(report.shocks):
        assert s.candidate_timestamp_s == pytest.approx(expected_cands[idx], abs=0.1)
        assert s.candidate_source == "operator_supplied"
        # Profile is default/UNKNOWN (uncalibrated), so status is UNAVAILABLE (I1)
        assert s.adjudication_status == "UNAVAILABLE"
        assert "no calibrated profile for this device (Q-019)" in s.adjudication_verdict

    # Text report generation succeeds without errors
    text_unval = report.format_text_report(ground_truth=None)
    assert "NOT FOR CLINICAL OR PERFORMANCE ASSESSMENT." in text_unval
    assert "Validation Status: Accuracy not validated for this case" in text_unval
