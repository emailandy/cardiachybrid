"""
tests/test_s2.py — Comprehensive Tests for Sensor S2 Compression-Audio & Occlusion-Gated Fusion (S07).

Verifies CPR compression cadence and periodicity detection from audio tracks with frequency lock
and frame stability, specifically testing uninterrupted detection through synthetic full-occlusion
windows where Sensor S1 optical flow fails, and validating S6 occlusion-gated fusion logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from sensors.s2_compression_audio import (
    AudioCompressionInterval,
    S2CompressionAudioDetector,
    fuse_s1_s2,
    load_audio_config,
    run_s2_compression_audio,
)


@dataclass(frozen=True)
class MockS1Interval:
    id: str
    type: str
    t_start_s: float
    t_end_s: float
    cadence_cpm: float = 102.0
    confidence: float = 0.88


@dataclass(frozen=True)
class MockS6Occlusion:
    t_start_s: float
    t_end_s: float
    note: str = "provider_crowding"


def test_load_audio_config_profiles() -> None:
    """Verifies calibrated threshold profiles load without literals."""
    default = load_audio_config("default")
    sim = load_audio_config("simvideo2")
    unknown = load_audio_config("UNKNOWN")
    assert default["band_min_hz"] == 1.3
    assert sim["min_band_power_ratio"] == 0.05
    assert unknown["confidence_dual"] == 0.95
    assert sim["max_freq_delta_hz"] == 0.08
    assert sim["max_freq_std_hz"] == 0.05
    # Non-existent profile falls back to default
    fallback = load_audio_config("nonexistent")
    assert fallback["band_min_hz"] == default["band_min_hz"]


def test_s2_stft_peak_detection_on_synthetic_sinusoid(
    tmp_path: Path,
) -> None:
    """
    Verifies STFT peak detection and harmonic tracking on a synthetic 1.70 Hz sinusoid
    in Gaussian noise. Note: tests mathematical signal processing only; does NOT prove
    or assert compression cadence isolation on real clinical room audio (F-023).
    """
    sr = 16000
    duration_s = 20.0
    t = np.linspace(0.0, duration_s, int(sr * duration_s), endpoint=False)
    noise = np.random.normal(0.0, 0.01, len(t))
    # 1.70 Hz metronomic LUCAS rate
    cadence_envelope = 0.5 * (1.0 + np.sin(2.0 * np.pi * 1.70 * t))
    # Enable CPR compressions from 4.0s to 16.0s
    active_cpr = ((t >= 4.0) & (t <= 16.0)).astype(np.float32)
    audio_signal = (noise + 0.8 * cadence_envelope * active_cpr).astype(np.float32)

    audio_path = tmp_path / "cpr_occlusion.wav"
    sf.write(str(audio_path), audio_signal, sr)

    detector = S2CompressionAudioDetector(sr=sr)
    occlusion_window = (5.0, 15.0)

    overlapping = detector.detect_through_occlusion(
        audio_path,
        occlusion_window_s=occlusion_window,
        device_hz=1.70,
    )

    assert len(overlapping) >= 1
    intv = overlapping[0]
    assert intv.abstained is False
    assert intv.type == "compression_audio"
    assert intv.t_start_s <= occlusion_window[0]
    assert intv.t_end_s >= occlusion_window[1]
    assert intv.support == ["s2"]
    assert 0.0 < intv.confidence <= 1.0


def test_s2_abstains_on_silent_audio(tmp_path: Path) -> None:
    """
    Verifies that S2CompressionAudioDetector abstains cleanly with confidence=0.0
    and abstain_reason when presented with a silent audio file.
    """
    silent_path = tmp_path / "silent.wav"
    sr = 16000
    data = np.zeros(sr * 2, dtype=np.float32)
    sf.write(str(silent_path), data, sr)

    detector = S2CompressionAudioDetector()
    res = detector.detect_cadence_intervals(silent_path)

    assert len(res) == 1
    assert res[0].abstained is True
    assert res[0].confidence == 0.0
    assert "silent" in str(res[0].abstain_reason).lower()
    assert res[0].support == []


def test_s1_s2_interval_merging_logic_on_mock_dataclasses() -> None:
    """
    Verifies interval-merging and coverage note assignment on mock dataclasses.
    Tests data structure routing only; this is NOT a validated clinical fusion strategy
    (retracted under F-020 and F-023 item 9 where OR-fusion erased 57% of real pauses).
    """
    s1_intervals = [
        MockS1Interval("s1_1", "compression_motion", t_start_s=40.0, t_end_s=50.0),
        MockS1Interval("s1_2", "compression_motion", t_start_s=60.0, t_end_s=70.0),
        MockS1Interval("s1_3", "compression_motion", t_start_s=80.0, t_end_s=90.0),
    ]

    # S2 is active continuously across the whole span (mocking ambient noise / continuous CPR)
    s2_intervals = [
        AudioCompressionInterval(
            id="s2_cont",
            type="compression_audio",
            t_start_s=40.0,
            t_end_s=90.0,
            frequency_hz=1.70,
            confidence=0.88,
            abstained=False,
            support=["s2"],
        )
    ]

    # S6 confirms visual occlusion ONLY between 50.0s and 60.0s (leaving 70.0-80.0s unoccluded)
    s6_occlusions = [
        MockS6Occlusion(t_start_s=50.0, t_end_s=60.0)
    ]

    fused_gated = fuse_s1_s2(
        s1_intervals,
        s2_intervals,
        s6_occlusions=s6_occlusions,
        total_duration_s=100.0,
        clinical_window_s=(40.0, 90.0),
        operator_mode="occlusion_gated",
    )

    # In occlusion_gated mode:
    # 50-60s is bridged into an S6 coverage note (S1 gap + S6 occlusion + S2 active)
    assert len(fused_gated["coverage_notes"]) == 1
    cov = fused_gated["coverage_notes"][0]
    assert cov.subtype == "occlusion_bridged_by_audio"
    assert cov.t_start_s == pytest.approx(50.0, abs=0.2)
    assert cov.t_end_s == pytest.approx(60.0, abs=0.2)
    assert cov.support == ["s2"]

    # 70-80s is preserved as a genuine CCI despite S2 being active (S1 gap + NO occlusion -> S2 ignored!)
    assert len(fused_gated["ccis"]) == 1
    cci = fused_gated["ccis"][0]
    assert cci.t_start_s == pytest.approx(70.0, abs=0.2)
    assert cci.t_end_s == pytest.approx(80.0, abs=0.2)
    assert cci.support == ["s1"]
