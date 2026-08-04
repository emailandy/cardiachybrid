"""
tests/test_s1_s6.py — Unit and integration tests for Sensor S1 (chest motion
optical flow and CCI pause intervals) and Sensor S6 (visual occlusion and
provider crowding coverage notes).

Verifies 100% determinism across 5 independent runs, emission of CCI intervals
with confidence, and transparent reporting of calibration surfaces.
"""

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from sensors.s1_s6_motion import (
    S1ChestMotionDetector,
    S6CoverageDetector,
    detect_visual_occlusion,
    load_roi_config,
    report_calibration_surface,
)


def test_load_roi_config_warns_default_and_unknown(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verifies that uncalibrated or fallback ROI profiles log explicit warnings."""
    with caplog.at_level(logging.WARNING):
        cfg_def = load_roi_config("default")
        assert "Using default/UNKNOWN ROI calibration profile" in caplog.text
        assert cfg_def.get("chest_roi", {}).get("width") == 720

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        cfg_unk = load_roi_config("non_existent_profile_123")
        assert "not found in roi_config.yaml" in caplog.text
        assert "Falling back to 'default'" in caplog.text
        assert cfg_unk.get("chest_roi", {}).get("width") == 720


def test_report_calibration_surface() -> None:
    """Verifies that report_calibration_surface returns all required config sections."""
    surf = report_calibration_surface("simvideo2")
    assert surf["profile_name"] == "simvideo2"
    assert "chest_roi" in surf and surf["chest_roi"]["width"] == 640
    assert "s1_motion" in surf and surf["s1_motion"]["vy_bandpass_min_hz"] == 1.3
    assert (
        "s6_coverage" in surf
        and surf["s6_coverage"]["occlusion_std_threshold"] == 15.0
    )


def test_s1_motion_detector_synthetic_vy() -> None:
    """
    Verifies S1 motion detection and CCI pause interval emission on synthetic
    vertical velocity signals.
    """
    fps = 30.0
    total_dur = 30.0
    n_frames = int(total_dur * fps)
    t = np.arange(n_frames) / fps
    vy = np.zeros(n_frames, dtype=float)

    # Active CPR epoch 1: t=2.0s to 12.0s at 1.8 Hz (108 CPM)
    m1 = (t >= 2.0) & (t <= 12.0)
    vy[m1] = 50.0 * np.sin(2.0 * np.pi * 1.8 * t[m1])

    # Pause CCI: t=12.0s to 18.0s (6.0s pause >= 3.0s threshold)

    # Active CPR epoch 2: t=18.0s to 28.0s at 1.8 Hz (108 CPM)
    m2 = (t >= 18.0) & (t <= 28.0)
    vy[m2] = 50.0 * np.sin(2.0 * np.pi * 1.8 * t[m2])

    detector = S1ChestMotionDetector(profile_name="default")
    events = detector.detect_from_vy_signal(vy, fps=fps)

    assert len(events) == 2, f"Expected 2 active CPR intervals, got {len(events)}"
    for ev in events:
        assert ev.event_type == "compression_motion"
        assert abs(ev.cadence_cpm - 108.0) <= 5.0
        assert ev.confidence == 0.85

    ccis = detector.detect_cci_intervals(events, total_duration_s=total_dur)
    assert (
        len(ccis) == 1
    ), f"Expected 1 CCI pause interval between epochs, got {len(ccis)}"
    cci = ccis[0]
    assert cci["type"] == "compression_interruption"
    assert abs(cci["duration_s"] - 6.0) <= 0.3
    assert cci["confidence"] == 0.85


def test_s6_coverage_detector_synthetic_metrics() -> None:
    """
    Verifies S6 visual occlusion and provider crowding detection on synthetic
    ROI standard deviation signals.
    """
    fps = 30.0
    total_dur = 20.0
    n_frames = int(total_dur * fps)
    t = np.arange(n_frames) / fps

    std_signal = np.ones(n_frames, dtype=float) * 30.0  # nominal high contrast
    occ_mask = (t >= 5.0) & (t <= 9.0)  # 4.0s occlusion
    std_signal[occ_mask] = 10.0  # < 15.0 threshold

    detector = S6CoverageDetector(profile_name="simvideo2")
    events = detector.detect_occlusion_from_metrics(std_signal, timestamps_s=t)

    assert len(events) == 1, f"Expected 1 occlusion event, got {len(events)}"
    ev = events[0]
    assert ev.event_type == "coverage_note"
    assert ev.channel == "visual_chest"
    assert ev.degradation_type == "provider_crowding"
    assert ev.confidence == 0.92
    assert abs((ev.t_end_s - ev.t_start_s) - 4.0) <= 0.1


def test_detect_visual_occlusion_standalone() -> None:
    """
    Verifies standalone single-frame visual occlusion detector per SENSOR_SPECS
    S6.1 specification.
    """
    clean_roi = np.random.normal(128, 30, (50, 50))
    assert detect_visual_occlusion(clean_roi, timestamp_s=10.0) is None

    occ_roi = np.ones((50, 50), dtype=float) * 40.0  # std=0.0 < 15.0
    res = detect_visual_occlusion(occ_roi, timestamp_s=10.0)
    assert isinstance(res, dict)
    assert res["type"] == "coverage_note"
    assert res["channel"] == "visual_chest"
    assert res["degradation_type"] == "provider_crowding"
    assert res["confidence"] == 0.95


@pytest.mark.integration
def test_s1_s6_deterministic_5_runs() -> None:
    """
    Verifies 100% determinism across 5 independent runs of S1 optical flow motion
    detection and S6 visual occlusion detection on tests/video/vidsim2.mp4.
    """
    video_path = Path("tests/video/vidsim2.mp4")
    if not video_path.exists():
        pytest.skip(f"Test video not found: {video_path}")

    d1 = S1ChestMotionDetector(profile_name="simvideo2")
    d6 = S6CoverageDetector(profile_name="simvideo2")

    events1_0 = d1.detect_from_video(video_path, max_duration_s=5.0)
    ccis_0 = d1.detect_cci_intervals(events1_0, total_duration_s=5.0)
    events6_0 = d6.detect_occlusion_from_video(video_path, max_duration_s=5.0)
    surf_0 = report_calibration_surface("simvideo2")

    for idx in range(1, 5):
        events1_i = d1.detect_from_video(video_path, max_duration_s=5.0)
        ccis_i = d1.detect_cci_intervals(events1_i, total_duration_s=5.0)
        events6_i = d6.detect_occlusion_from_video(
            video_path, max_duration_s=5.0
        )
        surf_i = report_calibration_surface("simvideo2")

        assert (
            events1_i == events1_0
        ), f"S1 non-deterministic on run {idx + 1}: {events1_i} != {events1_0}"
        assert (
            ccis_i == ccis_0
        ), f"S1 CCIs non-deterministic on run {idx + 1}: {ccis_i} != {ccis_0}"
        assert (
            events6_i == events6_0
        ), f"S6 non-deterministic on run {idx + 1}: {events6_i} != {events6_0}"
        assert (
            surf_i == surf_0
        ), f"Calibration surface non-deterministic on run {idx + 1}"

    # Verify CCI intervals are emitted with confidence attribute
    for cci in ccis_0:
        assert "confidence" in cci and isinstance(cci["confidence"], float)

    # Verify calibration surface reported
    assert surf_0["profile_name"] == "simvideo2"
    assert surf_0["chest_roi"]["width"] == 640


@pytest.mark.integration
def test_s1_vidsim2_percentiles_and_shock_containment() -> None:
    """
    Verifies Sensor S1 percentile thresholding, camera bump exclusion,
    and shock containment inside CCI pause intervals on vidsim2.mp4.
    """
    video_path = Path("tests/video/vidsim2.mp4")
    if not video_path.exists():
        pytest.skip(f"Test video not found: {video_path}")

    detector = S1ChestMotionDetector(profile_name="default")
    events = detector.detect_from_video(video_path)
    ccis = detector.detect_cci_intervals(events, total_duration_s=1363.7)

    assert len(events) >= 50, f"Expected >= 50 CPR compression intervals, got {len(events)}"
    assert len(ccis) >= 40, f"Expected >= 40 CCI pause intervals, got {len(ccis)}"

    for t in [167.94, 385.07, 621.34, 742.21]:
        matching = [
            c
            for c in ccis
            if float(c["t_start_s"]) <= t <= float(c["t_end_s"])
        ]
        assert matching, (
            f"True defibrillation shock at t={t}s does not fall inside any detected CCI pause interval"
        )


def test_s1_modulation_floor_raises_no_periodic_motion() -> None:
    """
    Verifies that a window with energy modulation below the calibrated floor
    raises NoPeriodicMotion rather than emitting an interval.
    """
    from sensors.s1_s6_motion import NoPeriodicMotion
    detector = S1ChestMotionDetector(profile_name="simvideo2")
    flat_vy = np.zeros(600, dtype=float)
    with pytest.raises(NoPeriodicMotion, match="below floor"):
        detector.detect_from_vy_signal(flat_vy, fps=30.0)
