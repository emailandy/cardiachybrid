"""
tests/test_s2.py — Comprehensive Tests for Sensor S2 Compression-Audio (S07).

Verifies CPR compression cadence and periodicity detection from audio tracks,
specifically testing uninterrupted detection through synthetic full-occlusion
windows where Sensor S1 optical flow fails.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from sensors.s2_compression_audio import (
    AudioCompressionInterval,
    S2CompressionAudioDetector,
    run_s2_compression_audio,
)


def test_s2_detects_compressions_through_synthetic_full_occlusion_window_where_s1_fails(
    tmp_path: Path,
) -> None:
    """
    Verifies the S07 acceptance gate: detects CPR compressions through a synthetic
    full-occlusion window where Sensor S1 optical flow fails.
    """
    sr = 16000
    duration_s = 20.0
    t = np.linspace(0.0, duration_s, int(sr * duration_s), endpoint=False)
    noise = np.random.normal(0.0, 0.01, len(t))
    cadence_envelope = 0.5 * (1.0 + np.sin(2.0 * np.pi * 1.83 * t))
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
    )

    assert len(overlapping) >= 1
    intv = overlapping[0]
    assert intv.abstained is False
    assert intv.type == "compression_audio"
    assert intv.t_start_s <= occlusion_window[0]
    assert intv.t_end_s >= occlusion_window[1]
    assert 1.6 <= intv.frequency_hz <= 2.2
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


def test_s2_detects_synthetic_110_cpm_cadence_array() -> None:
    """
    Verifies cadence periodicity detection on a synthetic 1D audio array
    with 1.83 Hz (110 cpm) amplitude envelope pulses.
    """
    sr = 16000
    duration_s = 10.0
    t = np.linspace(0.0, duration_s, int(sr * duration_s), endpoint=False)

    # Carrier noise modulated by 1.83 Hz pulse envelope
    noise = np.random.normal(0.0, 0.2, len(t))
    cadence_envelope = 0.5 * (1.0 + np.sin(2.0 * np.pi * 1.83 * t))
    audio_signal = noise + 0.8 * cadence_envelope

    detector = S2CompressionAudioDetector(sr=sr)
    intervals = detector._detect_from_audio_array(audio_signal.astype(np.float32), sr)

    assert len(intervals) >= 1
    assert any(not intv.abstained for intv in intervals)
    for intv in intervals:
        if not intv.abstained:
            assert intv.type == "compression_audio"
            assert intv.t_start_s <= intv.t_end_s
            assert intv.confidence > 0.0


@pytest.mark.integration
def test_s2_integration_vidsim2() -> None:
    """
    Integration test: runs S2CompressionAudioDetector on tests/video/vidsim2.mp4.
    Verifies audio CPR cadence detection through visual occlusion intervals.
    """
    vp = Path("tests/video/vidsim2.mp4")
    if not vp.exists():
        pytest.skip("Integration video tests/video/vidsim2.mp4 not found")

    detector = S2CompressionAudioDetector()
    intervals = detector.detect_cadence_intervals(vp)
    assert len(intervals) >= 1
    for intv in intervals:
        assert intv.type == "compression_audio"
        assert intv.t_start_s <= intv.t_end_s
        assert 0.0 <= intv.confidence <= 1.0
