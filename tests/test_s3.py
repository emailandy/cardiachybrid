"""
tests/test_s3.py — Comprehensive unit and integration tests for Sensor S3 (Defibrillator Audio).
"""

import logging
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf  # type: ignore[import-untyped]

from sensors.s3_defib import S3DefibDetector, load_defib_profile


def test_load_defib_profile_default_warns(caplog: pytest.LogCaptureFixture) -> None:
    """Loading default profile must log warning on every run, never silently."""
    with caplog.at_level(logging.WARNING):
        profile = load_defib_profile("default")
    assert "Using default/UNKNOWN defibrillator calibration profile." in caplog.text
    assert "Fitted, not general." in caplog.text
    assert profile["freq_min_hz"] == 400


def test_load_defib_profile_unknown_fallback(caplog: pytest.LogCaptureFixture) -> None:
    """Loading a non-existent bay profile logs a warning and falls back to default."""
    with caplog.at_level(logging.WARNING):
        profile = load_defib_profile("missing_bay")
    assert "Defibrillator calibration profile 'missing_bay' not found" in caplog.text
    assert profile["min_slope_hz_s"] == 40.0


def test_s3_defib_detector_deterministic_5_runs_synthetic(tmp_path: Path) -> None:
    """Five runs on synthetic audio must produce byte-identical event output."""
    sr = 16000
    t = np.linspace(0, 5.0, 5 * sr, endpoint=False)
    y = np.zeros_like(t)

    # Inject rising charge tone 400..800 Hz from 1.0 to 2.0s
    tone_idx = (t >= 1.0) & (t <= 2.0)
    freq_traj = np.linspace(400, 800, np.sum(tone_idx))
    phase = 2 * np.pi * np.cumsum(freq_traj) / sr
    y[tone_idx] += 0.5 * np.sin(phase)

    # Inject transient spike at t=2.1s
    click_idx = int(2.1 * sr)
    y[click_idx : click_idx + 50] = 5.0

    wav_path = tmp_path / "synthetic_defib.wav"
    sf.write(str(wav_path), y, sr)

    detector = S3DefibDetector("default")
    run_0 = detector.detect_events(wav_path)
    for _ in range(4):
        run_i = detector.detect_events(wav_path)
        assert run_i == run_0


@pytest.mark.integration
def test_s3_defib_detector_full_track_simvideo2() -> None:
    """
    Integration verification on full 22-minute track tests/video/vidsim2.mp4:
    1. Runs on the full track (1,363 seconds) without being told where to look.
    2. Detects 4/4 true shocks at 167.94, 385.07, 621.34, 742.21 with timestamp MAE <= 0.5s.
    3. 0 false positives at 861.0 and 884.5 (both measured at tone slope 0.0 and r 0.00).
    4. Deterministic across 5 independent runs (byte-identical output).
    """
    video_path = (
        Path(__file__).resolve().parent.parent / "tests" / "video" / "vidsim2.mp4"
    )
    if not video_path.exists():
        pytest.skip("Test video tests/video/vidsim2.mp4 not found.")

    detector = S3DefibDetector("default")
    events_0 = detector.detect_events(video_path)

    # 4. Deterministic across 5 runs
    for _ in range(4):
        events_i = detector.detect_events(video_path)
        assert events_i == events_0

    # 2. Verify 4/4 true shocks
    shocks = [e for e in events_0 if e.event_type == "defibrillation_shock"]
    expected_shocks = [167.94, 385.07, 621.34, 742.21]
    for exp_t in expected_shocks:
        matching = [s for s in shocks if abs(s.timestamp_s - exp_t) <= 0.5]
        assert matching, (
            f"Expected shock at {exp_t}s not found within 0.5s MAE "
            f"(closest shocks: {[round(s.timestamp_s, 2) for s in shocks]})"
        )

    # 3. Verify 0 false positives specifically at 861.0 and 884.5
    for rej_t in [861.0, 884.5]:
        near = [s for s in shocks if abs(s.timestamp_s - rej_t) <= 0.5]
        assert not near, f"Unexpected shock detected at rejection timestamp {rej_t}s"
        slope_val, r_val = detector.inspect_rejection_window(video_path, rej_t)
        assert slope_val == 0.0 and r_val == 0.0, (
            f"Expected slope=0.0 and r=0.00 for {rej_t}s, got slope={slope_val}, r={r_val}"
        )
