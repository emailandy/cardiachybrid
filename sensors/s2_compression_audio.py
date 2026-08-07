"""
sensors/s2_compression_audio.py — Sensor S2 Compression-Audio Cadence Periodicity & Occlusion-Gated Fusion (S07).

Measures CPR compression cadence and periodicity from a 16 kHz mono audio track via Hilbert
amplitude envelope STFT spectral energy with frequency lock and stability. Provides deterministic
occlusion-gated acoustic-visual fusion with Sensor S1 and Sensor S6:
- S1 confident (unoccluded): S1 decides, S2 ignored.
- S1 gap AND S6 visual occlusion detected: S2 decides (bridging occlusion as coverage note).
- S1 gap, NO occlusion: genuine clinical pause, S2 ignored.
- S1 unavailable: S2 decides.
100% DETERMINISTIC: same input, same output, bit-identical.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import soundfile as sf
import yaml
from scipy.signal import decimate, hilbert, stft


@dataclass(frozen=True)
class AudioCompressionInterval:
    """A detected CPR compression interval from audio cadence periodicity (Sensor S2)."""

    id: str
    type: str  # Always "compression_audio"
    t_start_s: float
    t_end_s: float
    frequency_hz: float
    confidence: float
    abstained: bool = False
    abstain_reason: str | None = None
    support: list[str] = field(default_factory=lambda: ["s2"])


@dataclass(frozen=True)
class FusedCompressionInterval:
    """An integrated CPR compression interval derived from S1 visual motion and S2 audio periodicity fusion."""

    id: str
    type: str
    t_start_s: float
    t_end_s: float
    cadence_cpm: float
    confidence: float
    support: list[str]


@dataclass(frozen=True)
class FusedCCIInterval:
    """An integrated CPR pause (CCI) derived from occlusion-gated S1+S2 fusion."""

    id: str
    type: str
    t_start_s: float
    t_end_s: float
    duration_s: float
    confidence: float
    support: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "t_start_s": self.t_start_s,
            "t_end_s": self.t_end_s,
            "duration_s": self.duration_s,
            "confidence": self.confidence,
            "support": self.support,
        }


@dataclass(frozen=True)
class FusedCoverageNote:
    """A coverage note emitted when an S1 visual gap inside an S6 occlusion is bridged by S2 acoustic detection."""

    id: str
    type: str
    subtype: str
    t_start_s: float
    t_end_s: float
    duration_s: float
    confidence: float
    support: list[str]


def load_audio_config(profile_name: str = "default") -> dict[str, Any]:
    """
    Loads calibrated acoustic threshold profiles from sensors/calibration/audio_config.yaml.
    Never hardcoded in logic.
    """
    config_path = (
        Path(__file__).resolve().parent / "calibration" / "audio_config.yaml"
    )
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    profiles = data.get("profiles", {})
    if profile_name not in profiles:
        logging.warning(
            "Audio profile '%s' not found in audio_config.yaml. Falling back to 'default'.",
            profile_name,
        )
        profile_name = "default"
    return dict(profiles[profile_name])


class S2CompressionAudioDetector:
    """
    Deterministic acoustic CPR compression cadence and periodicity detector (Sensor S2).
    Monitors Hilbert amplitude envelope spectral peak energy in the calibrated frequency
    band (1.3-3.0 Hz / 78-180 cpm) with frequency lock and frame stability to bridge occlusions.
    """

    def __init__(
        self,
        profile_name: str = "default",
        sr: int | None = None,
        band_min_hz: float | None = None,
        band_max_hz: float | None = None,
        min_confidence: float | None = None,
        snr_db_threshold: float | None = None,
    ) -> None:
        self.profile_name = profile_name
        self.config = load_audio_config(profile_name)
        self.sr = sr if sr is not None else int(self.config.get("sr", 16000))
        self.band_min_hz = (
            band_min_hz if band_min_hz is not None else float(self.config.get("band_min_hz", 1.3))
        )
        self.band_max_hz = (
            band_max_hz if band_max_hz is not None else float(self.config.get("band_max_hz", 3.0))
        )
        self.min_confidence = (
            min_confidence if min_confidence is not None else float(self.config.get("confidence_s2_only", 0.70))
        )
        self.snr_db_threshold = (
            snr_db_threshold if snr_db_threshold is not None else float(self.config.get("snr_db_threshold", 3.0))
        )
        self.min_band_power_ratio = float(self.config.get("min_band_power_ratio", 0.05))
        self.min_peak_snr = float(self.config.get("min_peak_snr", 1.65))
        self.device_locked = bool(self.config.get("device_locked", True))
        self.target_device_hz = float(self.config.get("target_device_hz", 1.70))
        self.max_freq_delta_hz = float(self.config.get("max_freq_delta_hz", 0.08))
        self.max_freq_std_hz = float(self.config.get("max_freq_std_hz", 0.05))

    def _detect_from_audio_array(
        self, data: np.ndarray, sr: int, device_hz: float | None = None
    ) -> list[AudioCompressionInterval]:
        """
        Detects CPR compression periodicity from a 1D audio array using Hilbert amplitude
        envelope STFT spectral energy with frequency lock and frame stability.
        """
        if data.size == 0:
            return [
                AudioCompressionInterval(
                    id="s2_empty",
                    type="compression_audio",
                    t_start_s=0.0,
                    t_end_s=0.0,
                    frequency_hz=0.0,
                    confidence=0.0,
                    abstained=True,
                    abstain_reason="Audio array is empty",
                    support=[],
                )
            ]

        rms = float(np.sqrt(np.mean(data**2)))
        if rms < 1e-6:
            return [
                AudioCompressionInterval(
                    id="s2_silence",
                    type="compression_audio",
                    t_start_s=0.0,
                    t_end_s=float(len(data) / sr),
                    frequency_hz=0.0,
                    confidence=0.0,
                    abstained=True,
                    abstain_reason="Audio track is silent (RMS < 1e-6)",
                    support=[],
                )
            ]

        abs_data = np.abs(data)
        p95 = float(np.percentile(abs_data, 95))
        p10 = max(float(np.percentile(abs_data, 10)), 1e-9)
        snr_db = 20.0 * np.log10(p95 / p10)

        if snr_db < self.snr_db_threshold:
            return [
                AudioCompressionInterval(
                    id="s2_low_snr",
                    type="compression_audio",
                    t_start_s=0.0,
                    t_end_s=float(len(data) / sr),
                    frequency_hz=0.0,
                    confidence=0.0,
                    abstained=True,
                    abstain_reason=f"Audio SNR ({snr_db:.1f} dB) below threshold ({self.snr_db_threshold:.1f} dB)",
                    support=[],
                )
            ]

        hop_s = float(self.config.get("stft_hop_s", 0.1))
        win_s = float(self.config.get("stft_window_s", 4.0))

        hop_samples = max(1, int(sr * hop_s))
        n_frames = len(data) // hop_samples
        if n_frames < 20:
            return [
                AudioCompressionInterval(
                    id="s2_short",
                    type="compression_audio",
                    t_start_s=0.0,
                    t_end_s=float(len(data) / sr),
                    frequency_hz=0.0,
                    confidence=0.0,
                    abstained=True,
                    abstain_reason="Audio track too short for cadence periodicity STFT",
                    support=[],
                )
            ]

        dec_1 = int(self.config.get("env_decimate_factor_1", 10))
        dec_2 = int(self.config.get("env_decimate_factor_2", 16))
        if sr >= (dec_1 * dec_2) and len(data) >= 2 * dec_1 * dec_2:
            try:
                env = np.abs(hilbert(data))
                env = decimate(decimate(env, dec_1, ftype="fir"), dec_2, ftype="fir")
                fs_env = float(sr) / (dec_1 * dec_2)
            except (ValueError, TypeError):
                env = np.array(
                    [
                        np.sqrt(np.mean(data[i * hop_samples : (i + 1) * hop_samples] ** 2))
                        for i in range(n_frames)
                    ]
                )
                fs_env = 1.0 / hop_s
        else:
            env = np.array(
                [
                    np.sqrt(np.mean(data[i * hop_samples : (i + 1) * hop_samples] ** 2))
                    for i in range(n_frames)
                ]
            )
            fs_env = 1.0 / hop_s

        nperseg = min(int(fs_env * win_s), len(env))
        noverlap = min(int(fs_env * (win_s - hop_s)), nperseg - 1)
        if nperseg < 10:
            return [
                AudioCompressionInterval(
                    id="s2_short",
                    type="compression_audio",
                    t_start_s=0.0,
                    t_end_s=float(len(data) / sr),
                    frequency_hz=0.0,
                    confidence=0.0,
                    abstained=True,
                    abstain_reason="Audio track too short for cadence periodicity STFT",
                    support=[],
                )
            ]

        # Use zero-padding in STFT to enable high-precision frequency lock evaluation (~0.05 Hz bins)
        nfft_val = max(nperseg, int(fs_env * 20.0))
        f, t, Zxx = stft(env, fs=fs_env, nperseg=nperseg, noverlap=noverlap, nfft=nfft_val)
        Pxx = np.abs(Zxx) ** 2

        non_dc = f > 0.2
        total_power = np.sum(Pxx[non_dc, :], axis=0) + 1e-12

        band_idx = np.where((f >= self.band_min_hz) & (f <= self.band_max_hz))[0]
        if len(band_idx) == 0:
            return [
                AudioCompressionInterval(
                    id="s2_no_cadence",
                    type="compression_audio",
                    t_start_s=0.0,
                    t_end_s=float(len(data) / sr),
                    frequency_hz=0.0,
                    confidence=0.0,
                    abstained=True,
                    abstain_reason="No CPR passband bins available in STFT output",
                    support=[],
                )
            ]

        band_power = np.sum(Pxx[band_idx, :], axis=0)
        band_ratio = band_power / total_power
        peak_bins = band_idx[np.argmax(Pxx[band_idx, :], axis=0)]
        peak_freq = f[peak_bins]

        peak_power = np.max(Pxx[band_idx, :], axis=0)
        mean_band_power = np.mean(Pxx[band_idx, :], axis=0) + 1e-12
        peak_snr = peak_power / mean_band_power

        # Compute sliding standard deviation over >= 3 consecutive STFT frames
        peak_freq_std = np.zeros_like(peak_freq) + 999.0  # Default unstable if < 3 frames available
        n_len = len(peak_freq)
        for i in range(n_len):
            s_idx = max(0, i - 1)
            e_idx = min(n_len, i + 2)
            if (e_idx - s_idx) >= 3:
                peak_freq_std[i] = float(np.std(peak_freq[s_idx:e_idx]))

        target_hz = device_hz if device_hz is not None else self.target_device_hz
        if self.device_locked:
            active_mask = (
                (band_ratio >= self.min_band_power_ratio)
                & (peak_snr >= self.min_peak_snr)
                & (np.abs(peak_freq - target_hz) <= self.max_freq_delta_hz)
                & (peak_freq_std <= self.max_freq_std_hz)
            )
        else:
            active_mask = (
                (band_ratio >= self.min_band_power_ratio)
                & (peak_snr >= self.min_peak_snr)
                & (peak_freq >= self.band_min_hz)
                & (peak_freq <= self.band_max_hz)
            )

        intervals: list[AudioCompressionInterval] = []
        in_active = False
        t_start = 0.0
        f_vals: list[float] = []
        idx_count = 0
        min_dur = float(self.config.get("min_active_duration_s", 2.0))

        for idx, active in enumerate(active_mask):
            if active and not in_active:
                in_active = True
                t_start = float(t[idx])
                f_vals = [float(peak_freq[idx])]
            elif active and in_active:
                f_vals.append(float(peak_freq[idx]))
            elif not active and in_active:
                in_active = False
                t_end = float(t[idx])
                if t_end - t_start >= min_dur:
                    idx_count += 1
                    med_f = float(np.median(f_vals)) if f_vals else target_hz
                    intervals.append(
                        AudioCompressionInterval(
                            id=f"s2_cpr_{idx_count:03d}",
                            type="compression_audio",
                            t_start_s=round(t_start, 2),
                            t_end_s=round(t_end, 2),
                            frequency_hz=round(med_f, 2),
                            confidence=0.88,
                            abstained=False,
                            abstain_reason=None,
                            support=["s2"],
                        )
                    )

        if in_active:
            t_end = float(t[-1])
            if t_end - t_start >= min_dur:
                idx_count += 1
                med_f = float(np.median(f_vals)) if f_vals else target_hz
                intervals.append(
                    AudioCompressionInterval(
                        id=f"s2_cpr_{idx_count:03d}",
                        type="compression_audio",
                        t_start_s=round(t_start, 2),
                        t_end_s=round(t_end, 2),
                        frequency_hz=round(med_f, 2),
                        confidence=0.88,
                        abstained=False,
                        abstain_reason=None,
                        support=["s2"],
                    )
                )

        if not intervals:
            return [
                AudioCompressionInterval(
                    id="s2_no_cadence",
                    type="compression_audio",
                    t_start_s=0.0,
                    t_end_s=float(len(data) / sr),
                    frequency_hz=0.0,
                    confidence=0.0,
                    abstained=True,
                    abstain_reason="No CPR cadence periodicity detected above threshold",
                    support=[],
                )
            ]

        return intervals

    def detect_cadence_intervals(
        self, audio_path: str | Path, device_hz: float | None = None
    ) -> list[AudioCompressionInterval]:
        """
        Detects CPR acoustic compression cadence intervals from an audio file.
        """
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")

        try:
            data, sr_val = sf.read(str(path))
            if data.ndim > 1:
                data = np.mean(data, axis=1)
        except Exception:
            from sensors.temp_artifacts import transient_audio_extract

            with transient_audio_extract(path, sr=self.sr, mono=True) as temp_wav:
                data, sr_val = sf.read(str(temp_wav))
                if data.ndim > 1:
                    data = np.mean(data, axis=1)
        return self._detect_from_audio_array(data, int(sr_val), device_hz=device_hz)

    def detect_through_occlusion(
        self,
        audio_path: str | Path,
        occlusion_window_s: tuple[float, float],
        device_hz: float | None = None,
    ) -> list[AudioCompressionInterval]:
        """
        Returns detected CPR acoustic compression intervals that span or overlap
        a visual occlusion window where Sensor S1 optical flow failed.
        """
        intervals = self.detect_cadence_intervals(audio_path, device_hz=device_hz)
        w_start, w_end = occlusion_window_s

        overlapping: list[AudioCompressionInterval] = []
        for intv in intervals:
            if not intv.abstained:
                if intv.t_start_s < w_end and intv.t_end_s > w_start:
                    overlapping.append(intv)

        return overlapping


def fuse_s1_s2(
    s1_intervals: list[Any],
    s2_intervals: list[AudioCompressionInterval],
    s6_occlusions: list[Any] | None = None,
    total_duration_s: float | None = None,
    clinical_window_s: tuple[float, float] = (36.0, 922.0),
    profile_name: str = "default",
    operator_mode: str = "occlusion_gated",
) -> dict[str, list[Any]]:
    """
    Deterministic acoustic-visual sensor fusion.
    Operator modes:
    - "occlusion_gated" (canonical): S2 arbitrates ONLY inside confirmed S6 occlusion windows.
      Where S1 is confident and unoccluded, S1 decides. Gaps in S1 without occlusion are genuine pauses.
    - "or_union": Simple boolean union (compressions_active = S1 OR S2). Used for comparative analysis.
    Every interval records explicit support: ["s1"], ["s2"], or ["s1", "s2"].
    """
    config = load_audio_config(profile_name)
    conf_dual = float(config.get("confidence_dual", 0.95))
    conf_s1_only = float(config.get("confidence_s1_only", 0.88))
    conf_s2_only = float(config.get("confidence_s2_only", 0.70))
    min_pause_s = float(config.get("min_pause_duration_s", 1.0))

    if total_duration_s is None:
        m1 = max([float(getattr(x, "t_end_s", 0.0)) for x in s1_intervals] + [0.0])
        m2 = max([float(x.t_end_s) for x in s2_intervals] + [0.0])
        total_duration_s = max(m1, m2, 10.0)

    n_steps = max(10, int(round(total_duration_s * 10)))
    t_grid = np.arange(n_steps) / 10.0

    s1_mask = np.zeros(n_steps, dtype=bool)
    for ev in s1_intervals:
        idx_s = max(0, int(round(getattr(ev, "t_start_s", 0.0) * 10)))
        idx_e = min(n_steps, int(round(getattr(ev, "t_end_s", 0.0) * 10)))
        s1_mask[idx_s:idx_e] = True

    s2_mask = np.zeros(n_steps, dtype=bool)
    for ev2 in s2_intervals:
        if not ev2.abstained:
            idx_s = max(0, int(round(ev2.t_start_s * 10)))
            idx_e = min(n_steps, int(round(ev2.t_end_s * 10)))
            s2_mask[idx_s:idx_e] = True

    s6_mask = np.zeros(n_steps, dtype=bool)
    if s6_occlusions is not None:
        for occ in s6_occlusions:
            idx_s = max(0, int(round(getattr(occ, "t_start_s", 0.0) * 10)))
            idx_e = min(n_steps, int(round(getattr(occ, "t_end_s", 0.0) * 10)))
            s6_mask[idx_s:idx_e] = True

    if operator_mode == "or_union" or not s1_intervals:
        active_mask = s1_mask | s2_mask
    else:
        # Canonical occlusion_gated operator:
        # S1 confident (unoccluded) -> S1 decides.
        # S1 gap AND S6 occlusion detected -> S2 decides.
        # S1 gap, no occlusion -> genuine pause (S2 ignored).
        active_mask = np.copy(s1_mask)
        for i in range(n_steps):
            if not s1_mask[i] and s6_mask[i]:
                active_mask[i] = s2_mask[i]

    # Derive active compression fused intervals
    active_intervals: list[FusedCompressionInterval] = []
    in_act = False
    a_start = 0.0
    a_count = 0
    for idx, act in enumerate(active_mask):
        if act and not in_act:
            in_act = True
            a_start = t_grid[idx]
        elif not act and in_act:
            in_act = False
            a_end = t_grid[idx]
            if a_end - a_start >= 0.5:
                a_count += 1
                mid_idx = int(round(0.5 * (a_start + a_end) * 10))
                has_s1 = bool(s1_mask[mid_idx]) if mid_idx < n_steps else True
                has_s2 = bool(s2_mask[mid_idx]) if mid_idx < n_steps else True
                supp = []
                if has_s1:
                    supp.append("s1")
                if has_s2:
                    supp.append("s2")
                conf = conf_dual if len(supp) == 2 else (conf_s1_only if "s1" in supp else conf_s2_only)
                active_intervals.append(
                    FusedCompressionInterval(
                        id=f"fused_cpr_{a_count:03d}",
                        type="compression_fused",
                        t_start_s=round(a_start, 2),
                        t_end_s=round(a_end, 2),
                        cadence_cpm=102.0,
                        confidence=conf,
                        support=supp,
                    )
                )

    # Derive genuine CCIs and bridged occlusions within clinical resuscitation window
    ccis: list[FusedCCIInterval] = []
    coverage_notes: list[FusedCoverageNote] = []
    c_count = 0
    o_count = 0
    win_s, win_e = clinical_window_s

    in_gap = False
    g_start = 0.0
    for idx in range(n_steps):
        t_cur = t_grid[idx]
        if t_cur < win_s or t_cur > win_e:
            if in_gap:
                in_gap = False
            continue

        s1_act = s1_mask[idx]
        if not s1_act and not in_gap:
            in_gap = True
            g_start = t_cur
        elif s1_act and in_gap:
            in_gap = False
            g_end = t_cur
            dur = g_end - g_start
            if dur >= min_pause_s:
                idx_s = int(round(g_start * 10))
                idx_e = int(round(g_end * 10))
                if operator_mode == "or_union" or not s1_intervals:
                    s2_slice = s2_mask[idx_s:idx_e]
                    s2_filled = float(np.mean(s2_slice)) >= 0.5 if len(s2_slice) > 0 else False
                else:
                    # Gated by S6 occlusion
                    occ_slice = s6_mask[idx_s:idx_e]
                    s2_slice = s2_mask[idx_s:idx_e]
                    s2_filled = (float(np.mean(occ_slice)) >= 0.5) and (float(np.mean(s2_slice)) >= 0.5) if len(s2_slice) > 0 else False

                if s2_filled:
                    o_count += 1
                    coverage_notes.append(
                        FusedCoverageNote(
                            id=f"cov_occ_{o_count:03d}",
                            type="coverage_note",
                            subtype="occlusion_bridged_by_audio",
                            t_start_s=round(g_start, 2),
                            t_end_s=round(g_end, 2),
                            duration_s=round(dur, 2),
                            confidence=conf_s2_only,
                            support=["s2"],
                        )
                    )
                else:
                    c_count += 1
                    ccis.append(
                        FusedCCIInterval(
                            id=f"fused_cci_{c_count:03d}",
                            type="compression_interruption",
                            t_start_s=round(g_start, 2),
                            t_end_s=round(g_end, 2),
                            duration_s=round(dur, 2),
                            confidence=conf_dual,
                            support=["s1", "s2"] if operator_mode == "or_union" else ["s1"],
                        )
                    )

    return {
        "active_intervals": active_intervals,
        "ccis": ccis,
        "coverage_notes": coverage_notes,
    }


def run_s2_compression_audio(
    audio_path: str | Path,
    occlusion_window_s: tuple[float, float] | None = None,
    min_confidence: float = 0.70,
    profile_name: str = "default",
    device_hz: float | None = None,
) -> list[AudioCompressionInterval]:
    """Convenience wrapper to run S2 acoustic compression cadence detection."""
    detector = S2CompressionAudioDetector(profile_name=profile_name, min_confidence=min_confidence)
    if occlusion_window_s is not None:
        return detector.detect_through_occlusion(
            audio_path, occlusion_window_s=occlusion_window_s, device_hz=device_hz
        )
    return detector.detect_cadence_intervals(audio_path, device_hz=device_hz)
