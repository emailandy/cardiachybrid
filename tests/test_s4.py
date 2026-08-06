"""
tests/test_s4.py — Comprehensive Tests for Sensor S4 Monitor OCR (S08).

Verifies monitor OCR vital signs telemetry ingestion, per-monitor display layout
configuration loading, deterministic time-series output, and strict abstention
when OCR confidence < 0.80.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from sensors.s4_monitor_ocr import (
    MonitorOCRReading,
    S4MonitorOCRDetector,
    load_monitor_layout,
    run_s4_monitor_ocr,
)


def test_s4_abstains_below_080_confidence() -> None:
    """
    Verifies the S08 acceptance gate: abstains below 0.80 confidence, emitting
    confidence=0.0, abstained=True, and None for all numeric vital signs.
    """
    detector = S4MonitorOCRDetector(device_model="zoll_x_series")

    # Below threshold (0.79 < 0.80) -> abstains
    low_conf_reading = detector.extract_vitals_from_frame_roi(
        frame_roi=None,
        timestamp_s=100.0,
        simulated_ocr_result={
            "confidence": 0.79,
            "sbp_mmHg": 120.0,
            "dbp_mmHg": 80.0,
            "heart_rate_bpm": 110.0,
            "spo2_pct": 98.0,
            "etco2_mmHg": 38.0,
        },
    )
    assert low_conf_reading.abstained is True
    assert low_conf_reading.confidence == 0.0
    assert low_conf_reading.sbp_mmHg is None
    assert low_conf_reading.dbp_mmHg is None
    assert low_conf_reading.heart_rate_bpm is None
    assert "below calibrated threshold" in str(low_conf_reading.abstain_reason)

    # At or above threshold (0.80 >= 0.80) -> accepts
    valid_reading = detector.extract_vitals_from_frame_roi(
        frame_roi=None,
        timestamp_s=101.0,
        simulated_ocr_result={
            "confidence": 0.80,
            "sbp_mmHg": 120.0,
            "dbp_mmHg": 80.0,
            "heart_rate_bpm": 110.0,
            "spo2_pct": 98.0,
            "etco2_mmHg": 38.0,
        },
    )
    assert valid_reading.abstained is False
    assert valid_reading.confidence == 0.80
    assert valid_reading.sbp_mmHg == 120.0
    assert valid_reading.heart_rate_bpm == 110.0


def test_s4_shell_dataclass_construction_determinism(tmp_path: Path) -> None:
    """
    Verifies that extract_vitals_series produces deterministic dataclass instances
    across repeated calls on dummy video inputs (structural shell test).
    """
    dummy_video = tmp_path / "video.mp4"
    dummy_video.touch()
    detector = S4MonitorOCRDetector(device_model="simvideo2_default")
    run0 = detector.extract_vitals_series(dummy_video)
    run1 = detector.extract_vitals_series(dummy_video)

    assert len(run0) >= 1
    assert len(run0) == len(run1)
    for r0, r1 in zip(run0, run1):
        assert r0.id == r1.id
        assert r0.confidence == r1.confidence
        assert r0.t_start_s == r1.t_start_s


def test_s4_per_monitor_layout_config(tmp_path: Path) -> None:
    """
    Verifies that layout coordinates and confidence thresholds are loaded
    from per-monitor layout YAML config files keyed by device model.
    """
    custom_yaml = tmp_path / "custom_layouts.yaml"
    custom_content = """
custom_device_x:
  device_model: "custom_device_x"
  roi: [10, 20, 300, 200]
  min_confidence: 0.85
  contrast_threshold: 0.30
  vitals_roi:
    hr: [15, 25, 50, 30]
  vitals_range:
    hr: [20.0, 250.0]
"""
    custom_yaml.write_text(custom_content, encoding="utf-8")

    layout = load_monitor_layout(
        profile_name="custom_device_x", config_path=custom_yaml
    )
    assert layout["device_model"] == "custom_device_x"
    assert layout["roi"] == [10, 20, 300, 200]
    assert float(layout["min_confidence"]) == 0.85

    detector = S4MonitorOCRDetector(
        device_model="custom_device_x", config_path=custom_yaml
    )
    assert detector.min_confidence == 0.85


def test_s4_shell_returns_monitor_ocr_type(
    tmp_path: Path,
) -> None:
    """
    Verifies that run_s4_monitor_ocr executes on dummy video inputs
    and returns MonitorOCRReading dataclass instances (structural shell test).
    """
    dummy_video = tmp_path / "video.mp4"
    dummy_video.touch()
    readings = run_s4_monitor_ocr(dummy_video, device_model="simvideo2_default")
    assert len(readings) >= 1
    assert readings[0].type == "monitor_ocr"


@pytest.mark.integration
@pytest.mark.xfail(
    reason="S4 monitor OCR is an uncalibrated architectural shell without a real vision OCR model (F-016)",
    strict=True,
)
def test_s4_integration_vidsim2() -> None:
    """
    Integration test: S4 is an architectural shell without a trained OCR model.
    Marked xfail to prevent presenting a green pass to clinicians on an unbuilt sensor.
    """
    vp = Path("tests/video/vidsim2.mp4")
    if not vp.exists():
        pytest.skip("Integration video tests/video/vidsim2.mp4 not found")

    readings = run_s4_monitor_ocr(vp, device_model="simvideo2_default")
    # Fails strict xfail because run_s4_monitor_ocr currently returns a mock reading without OCR
    assert False, "S4 monitor OCR has no vision OCR engine implemented (F-016)"
