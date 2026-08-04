"""
Unit tests for Sensor S5 deterministic clock anchor synchronization (S01).
Verifies:
1. Three-point verification fires on drift > tolerance (raising ClockDrift).
2. Explicit, logged fallback chain: burned_in -> monitor_clock -> manual -> none.
3. Derivation of T0 for simvideo2.mp4 within 2s of 2023-11-07T07:55:57.
"""

import os
from typing import Any

import numpy as np
import pytest

from sensors.s5_timecode import (
    ClockAnchor,
    ClockDrift,
    S5ClockAnchor,
    parse_timecode_to_iso,
    read_timecode,
    read_video_timecode_samples,
)


@pytest.mark.integration
def test_read_timecode_decodes_a_real_frame() -> None:
    """Verifies empirical OCR timecode reading from simvideo2.mp4 and T0 derivation."""
    video_path = os.path.join(os.path.dirname(__file__), "video", "vidsim2.mp4")
    if not os.path.exists(video_path):
        pytest.skip(f"Integration video {video_path} not found.")

    samples = read_video_timecode_samples(video_path, sample_times_s=(10.0, 300.0, 600.0))
    assert len(samples) == 3
    assert samples[0]["raw_string"] == "11/7/2023 07:56:06.630 AM"
    assert samples[1]["raw_string"] == "11/7/2023 08:00:57.072 AM"
    assert samples[2]["raw_string"] == "11/7/2023 08:05:57.081 AM"

    anchor = S5ClockAnchor.derive_t0({"burned_in": samples}, max_drift_tol_s=2.0)
    assert anchor.t0_iso == "2023-11-07T07:55:57"
    assert anchor.source == "burned_in"
    assert anchor.confidence == 0.98
    assert anchor.max_drift_s < 2.0
    assert any("burned_in: Validated 3 samples" in msg for msg in anchor.fallback_log)


def test_read_timecode_returns_none_on_low_confidence() -> None:
    """Verifies that read_timecode returns None when match score is below confidence threshold."""
    blank_frame = np.zeros((200, 400), dtype=np.uint8)
    assert read_timecode(blank_frame, min_confidence=0.60) is None


def test_parse_timecode_to_iso() -> None:
    """Verifies parsing raw OCR timecode strings to UTC ISO-8601 timestamps."""
    iso = parse_timecode_to_iso("11/7/2023 08:00:57.072 AM")
    assert iso == "2023-11-07T08:00:57.072000+00:00"
    with pytest.raises(ValueError, match="Could not parse timecode string"):
        parse_timecode_to_iso("invalid timestamp")


def test_three_point_verification_raises_clockdrift() -> None:
    """
    Builds a fixture where the third sample disagrees by 5 seconds and confirms
    ClockDrift is raised.
    """
    bad_samples: dict[str, list[dict[str, Any]]] = {
        "burned_in": [
            {"video_time_s": 10.0, "wall_clock_iso": "2023-11-07T07:56:07.000000+00:00"},
            {"video_time_s": 100.0, "wall_clock_iso": "2023-11-07T07:57:37.000000+00:00"},
            {"video_time_s": 200.0, "wall_clock_iso": "2023-11-07T07:59:22.000000+00:00"},  # 5s drift!
        ]
    }
    with pytest.raises(ClockDrift, match="Clock drift detected in source 'burned_in'.*max drift 5.00s"):
        S5ClockAnchor.derive_t0(bad_samples, max_drift_tol_s=2.0)


def test_explicit_fallback_chain_logging() -> None:
    """
    Verifies fallback order burned_in -> monitor_clock -> manual -> none
    and ensures that every skipped source is logged in fallback_log.
    """
    fallback_samples: dict[str, list[dict[str, Any]]] = {
        "burned_in": [
            {"video_time_s": 10.0, "wall_clock_iso": "2023-11-07T07:56:07.000000+00:00"}
        ],  # Only n=1 sample (insufficient)
        "monitor_clock": [
            {"video_time_s": 10.0, "wall_clock_iso": "2023-11-07T07:56:07.000000+00:00"},
            {"video_time_s": 100.0, "wall_clock_iso": "2023-11-07T07:57:37.000000+00:00"},
            {"video_time_s": 200.0, "wall_clock_iso": "2023-11-07T07:59:17.000000+00:00"},
        ],
    }

    anchor = S5ClockAnchor.derive_t0(fallback_samples, max_drift_tol_s=2.0)
    assert anchor.source == "monitor_clock"
    assert len(anchor.fallback_log) == 2
    assert "burned_in: Insufficient samples" in anchor.fallback_log[0]
    assert "monitor_clock: Validated 3 samples" in anchor.fallback_log[1]


def test_fallback_to_none_terminal() -> None:
    """Verifies that empty/unusable inputs fall back cleanly to 'none' with complete log."""
    anchor = S5ClockAnchor.derive_t0({}, max_drift_tol_s=2.0)
    assert anchor.source == "none"
    assert anchor.confidence == 0.0
    assert anchor.t0_iso == ""
    assert len(anchor.fallback_log) == 4
    assert "burned_in: Insufficient samples" in anchor.fallback_log[0]
    assert "monitor_clock: Insufficient samples" in anchor.fallback_log[1]
    assert "manual: Insufficient samples" in anchor.fallback_log[2]
    assert "none: No reliable clock anchor found" in anchor.fallback_log[3]
