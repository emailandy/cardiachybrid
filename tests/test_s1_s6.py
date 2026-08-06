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
    assert "chest_roi" in surf and surf["chest_roi"]["width"] == 140
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
    ), f"Expected 1 CCI pause interval (intra-epoch 5.7s), got {len(ccis)}"
    mid_cci = [c for c in ccis if c["t_start_s"] >= 10.0][0]
    assert mid_cci["type"] == "compression_interruption"
    assert abs(mid_cci["duration_s"] - 5.5) <= 1.0
    assert mid_cci["confidence"] == 0.85

    ccf_res = detector.compute_ccf(events)
    assert ccf_res["ccf"] > 0.0
    assert ccf_res["denominator_s"] > 0.0


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

    events1_0 = d1.detect_from_video(video_path, t0=140.0, max_duration_s=160.0)
    ccis_0 = d1.detect_cci_intervals(events1_0, total_duration_s=20.0)
    events6_0 = d6.detect_occlusion_from_video(video_path, max_duration_s=5.0)
    surf_0 = report_calibration_surface("simvideo2")

    for idx in range(1, 5):
        events1_i = d1.detect_from_video(video_path, t0=140.0, max_duration_s=160.0)
        ccis_i = d1.detect_cci_intervals(events1_i, total_duration_s=20.0)
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
    assert surf_0["chest_roi"]["width"] == 140


@pytest.mark.integration
def test_s1_vidsim2_percentiles_and_shock_containment() -> None:
    """
    Verifies Sensor S1 percentile thresholding, camera bump exclusion,
    and shock containment inside CCI pause intervals on vidsim2.mp4.
    """
    video_path = Path("tests/video/vidsim2.mp4")
    if not video_path.exists():
        pytest.skip(f"Test video not found: {video_path}")

    detector = S1ChestMotionDetector(profile_name="simvideo2")
    events = detector.detect_from_video(video_path)
    ccis = detector.detect_cci_intervals(events, total_duration_s=1363.7)

    assert len(events) >= 50, f"Expected >= 50 CPR compression intervals, got {len(events)}"
    assert len(ccis) >= 40, f"Expected >= 40 CCI pause intervals, got {len(ccis)}"

    for t in [385.07, 742.21]:
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
    Verifies that a window without periodic CPR motion
    raises NoPeriodicMotion rather than emitting an interval.
    """
    from sensors.s1_s6_motion import NoPeriodicMotion
    detector = S1ChestMotionDetector(profile_name="simvideo2")
    flat_vy = np.zeros(600, dtype=float)
    with pytest.raises(NoPeriodicMotion):
        detector.detect_from_vy_signal(flat_vy, fps=30.0)


def test_no_hardcoded_thresholds_in_sensors() -> None:
    """SENSOR LAYER rule: thresholds live in calibration YAML."""
    import re

    for f in sorted(Path("sensors").glob("s*.py")):
        for n, line in enumerate(f.read_text().splitlines(), 1):
            if (
                re.search(
                    r"(threshold|ratio|floor|min_|max_)\s*[=+*]\s*0?\.\d",
                    line,
                )
                and "config" not in line
                and "self." not in line
                and "profile" not in line
                and "def " not in line
                and not line.strip().startswith("#")
                and "transient_ratio=0.0" not in line
            ):
                pytest.fail(f"{f}:{n} hardcoded threshold: {line.strip()}")


def test_s1_ccf_bounded_by_first_and_last_cpr() -> None:
    """
    Verifies that compute_ccf calculates the Chest Compression Fraction strictly bounded
    between the first and last CPR events (t_last - t_first), rather than diluting
    over total recording duration.
    """
    from sensors.s1_s6_motion import CompressionMotionEvent, S1ChestMotionDetector

    detector = S1ChestMotionDetector(profile_name="simvideo2")
    events = [
        CompressionMotionEvent("s1_1", "compression_motion", 100.0, 160.0, 102.0, 0.5, "mechanical", 0.85),
        CompressionMotionEvent("s1_2", "compression_motion", 180.0, 240.0, 102.0, 0.5, "mechanical", 0.85),
    ]

    ccf_dict = detector.compute_ccf(events)
    assert ccf_dict["t_first_s"] == 100.0
    assert ccf_dict["t_last_s"] == 240.0
    assert ccf_dict["denominator_s"] == 140.0
    assert ccf_dict["cpr_duration_s"] == 120.0
    assert ccf_dict["ccf"] == round(120.0 / 140.0, 3)


def test_s1_cci_floor_and_blackout_exclusion() -> None:
    """
    Verifies that pause intervals shorter than the minimum floor are ignored,
    and that gaps dominated by automated de-identification blackout masks are suppressed
    as unmeasured coverage gaps rather than true CCI pauses.
    """
    from sensors.s1_s6_motion import CompressionMotionEvent, S1ChestMotionDetector
    import numpy as np

    detector = S1ChestMotionDetector(profile_name="simvideo2")
    events = [
        CompressionMotionEvent("s1_1", "compression_motion", 10.0, 20.0, 105.0, 1.5, "manual", 0.85),
        # 0.5s gap (20.0 to 20.5s) -> should be filtered out by pause floor (min_pause_duration_s=1.0)
        CompressionMotionEvent("s1_2", "compression_motion", 20.5, 40.0, 105.0, 1.5, "manual", 0.85),
        # 10.0s gap (40.0 to 50.0s) -> simulate blackout mask active during this gap
        CompressionMotionEvent("s1_3", "compression_motion", 50.0, 70.0, 105.0, 1.5, "manual", 0.85),
    ]

    # Without blackout mask set: gap 40.0-50.0s is emitted, but 0.5s gap is ignored
    ccis_no_blk = detector.detect_cci_intervals(events)
    gap_no_blk = [c for c in ccis_no_blk if c["t_start_s"] >= 39.0]
    assert len(gap_no_blk) == 1
    assert gap_no_blk[0]["t_start_s"] == 40.0 and gap_no_blk[0]["t_end_s"] == 50.0
    short_ccis = [c for c in ccis_no_blk if abs(c["t_start_s"] - 20.0) < 0.1]
    assert len(short_ccis) == 0, "0.5s pause should have been filtered out by 1.0s floor"

    # Now set self.last_blackout_mask covering 40.0s to 50.0s at fps=10.0
    fps = 10.0
    blk_mask = np.zeros(1000, dtype=bool)
    blk_mask[400:500] = True
    detector.last_blackout_mask = blk_mask
    detector.last_fps = fps

    ccis_with_blk = detector.detect_cci_intervals(events)
    gap_with_blk = [c for c in ccis_with_blk if c["t_start_s"] >= 39.0]
    assert len(gap_with_blk) == 0, "Pause covered by blackout should be excluded from CCI as unmeasured coverage gap"


def test_s1_cadence_mode_classification() -> None:
    """
    Verifies mechanical vs manual CPR mode classification based on cadence uniformity
    over continuous intervals.
    """
    from sensors.s1_s6_motion import S1ChestMotionDetector
    import numpy as np

    detector = S1ChestMotionDetector(profile_name="simvideo2")
    fps = 30.0

    # Mechanical: uniform 1.7 Hz (102 CPM) sine wave over 70 seconds (std < 3.0 cpm)
    t = np.arange(2100) / fps
    vy_mech = 50.0 * np.sin(2.0 * np.pi * 1.7 * t)
    cad_med, cad_std, mode_mech = detector._estimate_epoch_cadence_and_mode(vy_mech, fps)
    assert mode_mech == "mechanical"
    assert cad_std < 3.0

    # Manual: variable rate frequency shift between windows over 70 seconds (std > 8.0 cpm)
    # We construct alternating frequency epochs between 90 CPM (1.5 Hz) and 135 CPM (2.25 Hz) across 25s blocks
    vy_man = np.zeros(2100, dtype=float)
    for w in range(0, 2100, 750):
        f = 1.5 if (w // 750) % 2 == 0 else 2.25
        end_idx = min(2100, w + 750)
        idx_t = np.arange(end_idx - w) / fps
        vy_man[w:end_idx] = 50.0 * np.sin(2.0 * np.pi * f * idx_t)
    _, cad_std_man, mode_man = detector._estimate_epoch_cadence_and_mode(vy_man, fps)
    assert mode_man == "manual"
    assert cad_std_man > 8.0

    # Short duration (< 60s) falls back to unable_to_determine
    vy_short = 50.0 * np.sin(2.0 * np.pi * 1.7 * np.arange(300) / fps)
    _, _, mode_short = detector._estimate_epoch_cadence_and_mode(vy_short, fps)
    assert mode_short == "unable_to_determine — epoch too short for cadence variance"


def test_s6_blackout_deidentification_mask() -> None:
    """
    Verifies that detect_blackout identifies solid color de-identification overlays
    as deidentification masks.
    """
    from sensors.s1_s6_motion import detect_blackout
    import numpy as np

    clean_roi = np.random.randint(50, 200, (100, 100, 3), dtype=np.uint8)
    blackout_roi = np.zeros((100, 100, 3), dtype=np.uint8)
    solid_gray_mask = np.full((100, 100, 3), 128, dtype=np.uint8)

    assert detect_blackout(clean_roi, min_std=0.5) is False
    assert detect_blackout(blackout_roi, min_std=0.5) is True
    assert detect_blackout(solid_gray_mask, min_std=0.5) is True


def test_rms_window_spans_two_compression_cycles() -> None:
    """
    A 1-frame window is instantaneous power, not an envelope. Velocity
    crosses zero twice per stroke, so anything shorter than 2 cycles
    fragments continuous compressions.
    """
    from sensors.s1_s6_motion import compute_rms_window, load_roi_config

    cfg = load_roi_config("simvideo2")["s1_motion"]
    for fps in (8, 16, 24, 30, 60):
        win = compute_rms_window(fps, cfg["rms_window_s"])
        assert win / fps >= 2.0 / 1.3, f"{fps} fps -> {win/fps:.2f}s"


def test_three_consumers_three_rules_two_measurements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    R2: Verifies that the reporting layer reads cci_reporting_floor_s from roi_config.yaml,
    S1 continues to emit every inactive run >= 1.0s unchanged, and asserts:
    1. changing the YAML value changes the count of reported intervals;
    2. changing the YAML value does not change the interval set handed to CCF;
    3. the REDCap/repeating-group path still uses the dictionary >= 3.0s rule.
    Three consumers, three rules, two measurements (interval stream and independently-derived CPR duration).
    """
    from typing import Any, Sequence
    from sensors.s1_s6_motion import S1ChestMotionDetector
    from codegen.yamlio import load_yaml

    config_path = Path("sensors/calibration/roi_config.yaml")
    raw_yaml_str = config_path.read_text()
    test_cfg_path = tmp_path / "roi_config.yaml"
    test_cfg_path.write_text(raw_yaml_str)

    def mock_load(profile: str = "default") -> dict[str, Any]:
        data = load_yaml(test_cfg_path)
        return data.get("profiles", {}).get(profile, {})

    monkeypatch.setattr("sensors.s1_s6_motion.load_roi_config", mock_load)

    detector = S1ChestMotionDetector("simvideo2")
    raw_ccis = [
        {"id": "c1", "t_start_s": 10.0, "t_end_s": 11.5, "duration_s": 1.5},
        {"id": "c2", "t_start_s": 20.0, "t_end_s": 23.5, "duration_s": 3.5},
        {"id": "c3", "t_start_s": 30.0, "t_end_s": 35.5, "duration_s": 5.5},
        {"id": "c4", "t_start_s": 40.0, "t_end_s": 48.5, "duration_s": 8.5},
    ]

    ccf_intervals = detector.filter_ccis_by_consumer(raw_ccis, "ccf")
    assert len(ccf_intervals) == 4

    redcap_intervals = detector.filter_ccis_by_consumer(raw_ccis, "redcap")
    assert len(redcap_intervals) == 3
    assert [c["id"] for c in redcap_intervals] == ["c2", "c3", "c4"]

    report_intervals_5 = detector.filter_ccis_by_consumer(raw_ccis, "reporting")
    assert len(report_intervals_5) == 2
    assert [c["id"] for c in report_intervals_5] == ["c3", "c4"]

    modified_yaml_str = raw_yaml_str.replace("cci_reporting_floor_s: 5.0", "cci_reporting_floor_s: 7.0")
    test_cfg_path.write_text(modified_yaml_str)
    detector_7 = S1ChestMotionDetector("simvideo2")
    report_intervals_7 = detector_7.filter_ccis_by_consumer(raw_ccis, "reporting")
    assert len(report_intervals_7) == 1
    assert [c["id"] for c in report_intervals_7] == ["c4"]

    assert len(detector_7.filter_ccis_by_consumer(raw_ccis, "ccf")) == 4



