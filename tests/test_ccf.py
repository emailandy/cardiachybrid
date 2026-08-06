"""
tests/test_ccf.py — Unit and Integration Tests for Sensor S10 (CCF Report).

Verifies deterministic synthesis of S1 compression motion, S3 defibrillation
shocks, and S5 clock anchor synchronization into a clinical CCF quality report.
Enforces self-comparison guard (H1), dual clinical windows, three-tier consumer
routing, and mechanical CPR shock non-containment (F-029).
"""

from __future__ import annotations

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
    """Verifies that CCFReport serializes cleanly to dict and JSON."""
    report = CCFReport(
        case_id="test_case_01",
        video_path="tests/video/mock.mp4",
        t0_iso="2023-11-07T07:55:57",
        t0_source="burned_in",
        total_case_duration_s=600.0,
        patient_enters_room_s=36.0,
        patient_enters_room_source="operator_supplied",
        death_pronounced_s=500.0,
        death_pronounced_source="operator_supplied",
        interval_window_s=(36.0, 500.0),
        ccf_window_s=(70.0, 500.0),
        t_first_s=70.0,
        t_first_source="sensor_derived (S1 first compression motion)",
        ccf_denominator_s=430.0,
        total_cpr_duration_s=350.0,
        total_cci_duration_s=80.0,
        cpr_active_duration_s=350.0,
        cpr_active_fraction=round(350.0 / 430.0, 4),
        ccf=round(350.0 / 430.0, 4),
        ccf_percent=round((350.0 / 430.0) * 100.0, 2),
        ccf_by_2min_epoch=[0.8, 0.82, 0.81],
        n_cci_over_10s=2,
        longest_cci_s=25.0,
        median_cci_s=8.0,
        shocks=[
            CCFShockDetail(
                id="shock_1",
                candidate_timestamp_s=165.0,
                detected_timestamp_s=167.94,
                iso_time="2023-11-07T07:55:57 + 167.94s",
                confirmed=True,
                adjudication_verdict="CONFIRMED_SHOCK (rising tone 65.0 Hz/s, transient ratio 7.5)",
                pre_shock_pause_s=None,
                post_shock_pause_s=None,
                shock_inside_cci=False,
                cci_id=None,
                peak_rms_ratio=7.5,
                tone_slope_hz_s=65.0,
            )
        ],
        raw_intervals=[
            {
                "id": "cci_01",
                "type": "compression_interruption",
                "t_start_s": 147.5,
                "t_end_s": 155.0,
                "duration_s": 7.5,
                "confidence": 0.85,
            }
        ],
        ccf_intervals=[
            {
                "id": "cci_01",
                "type": "compression_interruption",
                "t_start_s": 147.5,
                "t_end_s": 155.0,
                "duration_s": 7.5,
                "confidence": 0.85,
            }
        ],
        redcap_intervals=[
            {
                "id": "cci_01",
                "type": "compression_interruption",
                "t_start_s": 147.5,
                "t_end_s": 155.0,
                "duration_s": 7.5,
                "confidence": 0.85,
            }
        ],
        reported_intervals=[
            {
                "id": "cci_01",
                "type": "compression_interruption",
                "t_start_s": 147.5,
                "t_end_s": 155.0,
                "duration_s": 7.5,
                "confidence": 0.85,
            }
        ],
        compression_intervals=[],
    )

    data = report.to_dict()
    assert data["case_id"] == "test_case_01"
    assert data["patient_enters_room_source"] == "operator_supplied"
    assert data["death_pronounced_source"] == "operator_supplied"
    assert data["shocks"][0]["id"] == "shock_1"
    assert data["shocks"][0]["shock_inside_cci"] is False
    assert len(data["reported_intervals"]) == 1

    json_str = report.to_json()
    parsed = json.loads(json_str)
    assert parsed["case_id"] == "test_case_01"
    assert parsed["t0_iso"] == "2023-11-07T07:55:57"


def test_ccf_report_does_not_import_or_read_ground_truth_fixture() -> None:
    """
    Verifies H1: sensors/ccf_report.py must NEVER import or open ground-truth fixtures.
    Prevents self-comparison anti-patterns (F-016 family).
    """
    report_py = Path("sensors/ccf_report.py")
    assert report_py.exists()
    content = report_py.read_text()

    # Must not import ground truth fixtures
    assert "fixtures.ground_truth" not in content
    assert "ground_truth_simvideo2.json" not in content
    assert "fixtures/" not in content


def test_ccf_report_text_formatting_with_and_without_ground_truth() -> None:
    """
    Verifies H2, H3, H4: text report leading banner, header notes, 5 shocks,
    three-tier consumer summary, and dynamic validation block handling.
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
        ccf_by_2min_epoch=[0.82, 0.81, 0.83],
        n_cci_over_10s=0,
        longest_cci_s=9.6,
        median_cci_s=6.1,
        shocks=[
            CCFShockDetail(
                id=f"shock_{i}",
                candidate_timestamp_s=ts,
                detected_timestamp_s=ts + 0.1 if i < 5 else None,
                iso_time=f"2023-11-07T07:55:57 + {ts:.2f}s",
                confirmed=(i < 5),
                adjudication_verdict="CONFIRMED_SHOCK" if i < 5 else "NO_SHOCK_CONFIRMED",
                pre_shock_pause_s=None,
                post_shock_pause_s=None,
                shock_inside_cci=False,
                cci_id=None,
                peak_rms_ratio=7.5 if i < 5 else 0.0,
                tone_slope_hz_s=65.0 if i < 5 else 0.0,
            )
            for i, ts in enumerate([165.0, 388.0, 622.0, 742.0, 879.0], start=1)
        ],
        raw_intervals=[{"t_start_s": 100.0, "t_end_s": 106.0, "duration_s": 6.0, "confidence": 0.9}] * 44,
        ccf_intervals=[{"t_start_s": 100.0, "t_end_s": 106.0, "duration_s": 6.0, "confidence": 0.9}] * 40,
        redcap_intervals=[{"t_start_s": 100.0, "t_end_s": 106.0, "duration_s": 6.0, "confidence": 0.9}] * 20,
        reported_intervals=[{"t_start_s": 100.0, "t_end_s": 106.0, "duration_s": 6.0, "confidence": 0.9}] * 11,
        compression_intervals=[],
    )

    # 1. Unvalidated mode (no ground truth passed)
    text_unvalidated = report.format_text_report(ground_truth=None)
    assert "NOT FOR CLINICAL OR PERFORMANCE ASSESSMENT" in text_unvalidated
    assert "n=1 validation output. Interval precision 0.36." in text_unvalidated
    assert "Accuracy not validated for this case (no ground truth supplied)" in text_unvalidated
    assert "Two Independent Measurements: CCF active duration and the interval stream represent two independent measurements" in text_unvalidated
    assert "4 coincide with S6-detected provider crowding; 2 are unexplained" in text_unvalidated
    assert "Omission of Longest Interruption (F-028)" in text_unvalidated
    assert "Shock Containment Notice (F-029): 0 of 5 shocks fall inside detected pauses" in text_unvalidated

    # 2. Validation mode (synthetic ground truth passed)
    dummy_gt = {
        "cci_intervals": [
            {"t_start_s": 147.0, "t_end_s": 155.0, "duration_s": 8.0},
            {"t_start_s": 245.0, "t_end_s": 256.0, "duration_s": 11.0},
        ]
    }
    text_validated = report.format_text_report(ground_truth=dummy_gt)
    assert "Validation & Error Decomposition (Computed vs Ground Truth):" in text_validated
    assert "Ground Truth CCF" in text_validated
    assert "Cancelling Error Decomposition" in text_validated


@pytest.mark.integration
def test_generate_ccf_report_vidsim2() -> None:
    """
    Integration test: runs generate_ccf_report on simvideo2.mp4.

    Gated Clinical Window Update (F-026 / Decision 031 / Task S10):
    - Replaced historical ungated assertions (total_case_duration_s ≈ 1363.78s) with
      operator-supplied active clinical window boundaries:
      * Interval Reporting Window: 36.0s – 922.0s (patient arrival to death pronouncement)
      * CCF Evaluation Window (Q-012 candidate c): 70.75s – 922.0s (denominator: 851.25s)
    - Verifies 5 shocks with acoustic adjudication (0/5 shock containment per F-029).
    - Verifies three-tier consumer routing: 11 reported intervals (>=5.0s reporting tier)
      and 40 CCF intervals (>=1.0s CCF tier).
    - Verifies CCF = 0.8170 (error 0.09 against comparable GT 0.9037 over 70.75-922s).
    """
    vp = Path("tests/video/vidsim2.mp4")
    if not vp.exists():
        pytest.skip("Integration video tests/video/vidsim2.mp4 not found")

    clinical_milestones = {
        "patient_enters_room_s": 36.0,
        "death_pronounced_s": 922.0,
    }

    report = generate_ccf_report(
        vp,
        case_id="simvideo2",
        profile_name="simvideo2",
        clinical_milestones=clinical_milestones,
        candidate_shock_times_s=(165.0, 388.0, 622.0, 742.0, 879.0),
    )

    assert report.case_id == "simvideo2"
    assert report.t0_source == "burned_in"
    assert report.t0_iso == "2023-11-07T07:55:57"

    # Provenance & Window assertions (H1)
    assert report.patient_enters_room_s == 36.0
    assert report.patient_enters_room_source == "operator_supplied"
    assert report.death_pronounced_s == 922.0
    assert report.death_pronounced_source == "operator_supplied"
    assert report.interval_window_s == (36.0, 922.0)
    assert report.ccf_window_s == (70.75, 922.0)
    assert report.ccf_denominator_s == pytest.approx(851.25, abs=0.5)

    # CCF derivation
    assert report.ccf == pytest.approx(0.8170, abs=0.005)
    assert report.ccf_percent == pytest.approx(81.70, abs=0.5)

    # 5 Shocks (F-022) with no shock containment assertions (F-029)
    assert len(report.shocks) == 5
    assert [s.candidate_timestamp_s for s in report.shocks] == [
        165.0,
        388.0,
        622.0,
        742.0,
        879.0,
    ]

    # Consumer Interval Routing (Scope 2)
    assert len(report.raw_intervals) == 44
    assert len(report.ccf_intervals) == 40
    assert len(report.reported_intervals) == 11
    assert report.longest_cci_s > 5.0
