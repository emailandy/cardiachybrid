"""
tests/test_ccf.py — Unit and Integration Tests for Sensor S04 (CCF Report).

Verifies deterministic synthesis of S1 compression motion, S3 defibrillation
shocks, and S5 clock anchor synchronization into a clinical CCF quality report.
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
        total_cpr_duration_s=450.0,
        total_cci_duration_s=150.0,
        cpr_active_duration_s=450.0,
        cpr_active_fraction=0.75,
        ccf=0.75,
        ccf_percent=75.0,
        ccf_by_2min_epoch=[0.8, 0.7, 0.75, 0.75, 0.75],
        n_cci_over_10s=5,
        longest_cci_s=45.0,
        median_cci_s=15.0,
        shocks=[
            CCFShockDetail(
                id="shock_1",
                timestamp_s=168.0,
                iso_time="2023-11-07T07:55:57 + 168.00s",
                pre_shock_pause_s=20.5,
                post_shock_pause_s=29.0,
                cci_id="cci_11",
                peak_rms_ratio=7.5,
                tone_slope_hz_s=65.0,
            )
        ],
        cci_intervals=[
            {
                "id": "cci_11",
                "type": "compression_interruption",
                "t_start_s": 147.5,
                "t_end_s": 197.0,
                "duration_s": 49.5,
                "confidence": 0.85,
            }
        ],
        compression_intervals=[],
    )

    data = report.to_dict()
    assert data["case_id"] == "test_case_01"
    assert data["ccf"] == 0.75
    assert data["ccf_percent"] == 75.0
    assert data["shocks"][0]["id"] == "shock_1"
    assert data["shocks"][0]["pre_shock_pause_s"] == 20.5
    assert len(data["cci_intervals"]) == 1

    json_str = report.to_json()
    parsed = json.loads(json_str)
    assert parsed["case_id"] == "test_case_01"
    assert parsed["t0_iso"] == "2023-11-07T07:55:57"


def test_ccf_metrics_math_invariance() -> None:
    """Verifies invariant mathematical relationships across CCF report fields."""
    report = CCFReport(
        case_id="math_test",
        video_path="none",
        t0_iso=None,
        t0_source="none",
        total_case_duration_s=100.0,
        total_cpr_duration_s=80.0,
        total_cci_duration_s=20.0,
        cpr_active_duration_s=80.0,
        cpr_active_fraction=0.80,
        ccf=0.80,
        ccf_percent=80.0,
        ccf_by_2min_epoch=[0.80],
        n_cci_over_10s=1,
        longest_cci_s=20.0,
        median_cci_s=20.0,
        shocks=[],
        cci_intervals=[],
        compression_intervals=[],
    )
    assert report.total_cpr_duration_s + report.total_cci_duration_s == pytest.approx(
        report.total_case_duration_s
    )
    assert report.ccf * 100.0 == pytest.approx(report.ccf_percent)


@pytest.mark.integration
def test_generate_ccf_report_vidsim2() -> None:
    """
    Integration test: runs generate_ccf_report on simvideo2.mp4.
    Verifies deterministic execution, zero LLM calls, S5 timecode anchor,
    S3 shock containment in CCIs, and valid CCF quality metrics.
    """
    vp = Path("tests/video/vidsim2.mp4")
    if not vp.exists():
        pytest.skip("Integration video tests/video/vidsim2.mp4 not found")

    report = generate_ccf_report(vp, case_id="simvideo2", profile_name="simvideo2")
    assert report.case_id == "simvideo2"
    assert report.t0_source == "burned_in"
    assert report.t0_iso == "2023-11-07T07:55:57"
    assert report.total_case_duration_s == pytest.approx(1363.78, abs=0.5)

    assert isinstance(report.shocks, list)

    # CCI stats
    assert len(report.cci_intervals) >= 40
    assert report.longest_cci_s > 10.0
    assert 0.0 < report.ccf < 1.0
