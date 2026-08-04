"""
sensors/s3_defib.py — Sensor S3 defibrillator acoustic charge and shock detector.

The charge TONE is primary, not the discharge click. A 3-second rising
narrowband tone survives 16 kHz mono compression, distance, and room noise.
A sub-100ms transient barely does. Track the tone, then search a bounded
window after it for the transient.

defib_charge_aborted falls out of the else branch. The Constitution's
negative control needs no separate rule.
"""

from dataclasses import dataclass
import logging
from pathlib import Path
import subprocess
from typing import Any

import numpy as np
import soundfile as sf  # type: ignore[import-untyped]
from scipy import signal, stats  # type: ignore[import-untyped]
from codegen.yamlio import StrictLoader


@dataclass(frozen=True)
class DefibChargeTone:
    """Represents an acoustic charge tone detected in the spectrogram."""

    charge_start_s: float
    charge_end_s: float
    slope_hz_per_s: float
    r_value: float


@dataclass(frozen=True)
class DefibEvent:
    """Represents a classified defibrillator event (shock or aborted charge)."""

    event_type: str
    timestamp_s: float
    charge_start_s: float
    charge_end_s: float
    slope_hz_per_s: float
    r_value: float
    transient_ratio: float
    confidence: float


def load_defib_profile(profile_name: str = "default") -> dict[str, Any]:
    """
    Loads defibrillator calibration parameters for the specified profile.
    Logs a warning when using 'default' or 'UNKNOWN' on uncalibrated bays.
    """
    profile_path = (
        Path(__file__).resolve().parent / "calibration" / "defib_profiles.yaml"
    )
    with open(profile_path, "r", encoding="utf-8") as f:
        profiles: dict[str, Any] = StrictLoader(f).get_single_data()

    if profile_name not in profiles:
        logging.warning(
            "Defibrillator calibration profile '%s' not found. Falling back to 'default'. "
            "Per-device calibration required before production.",
            profile_name,
        )
        profile_name = "default"
    if profile_name in ("default", "UNKNOWN"):
        logging.warning(
            "Using default/UNKNOWN defibrillator calibration profile. %s",
            profiles[profile_name].get("warning", ""),
        )
    return dict(profiles[profile_name])


def load_audio_mono_16k(audio_or_video_path: str | Path) -> tuple[np.ndarray, int]:
    """Loads audio from a wav or video file, converting to 16 kHz mono."""
    path = Path(audio_or_video_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio/video file not found: {path}")

    if path.suffix.lower() == ".wav":
        y, sr_val = sf.read(str(path))
        if y.ndim > 1:
            y = y.mean(axis=1)
        return y, int(sr_val)

    temp_wav = Path(f"/tmp/s3_audio_{abs(hash(str(path.resolve())))}.wav")
    if not temp_wav.exists():
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-loglevel",
            "error",
            str(temp_wav),
        ]
        subprocess.run(cmd, check=True)
    y, sr_val = sf.read(str(temp_wav))
    if y.ndim > 1:
        y = y.mean(axis=1)
    return y, int(sr_val)


class S3DefibDetector:
    """
    Streaming detector for defibrillator charge tones and discharge transients
    over full audio tracks.
    """

    def __init__(self, profile_name: str = "default") -> None:
        self.profile_name = profile_name
        self.profile = load_defib_profile(profile_name)

    def detect_tones(self, y: np.ndarray, sr: int) -> list[DefibChargeTone]:
        """Detects rising narrowband charge tones across the spectrogram."""
        f, t_sp, sxx = signal.spectrogram(y, sr, nperseg=1024, noverlap=512)
        freq_min = float(self.profile.get("freq_min_hz", 400))
        freq_max = float(self.profile.get("freq_max_hz", 1000))
        min_slope = float(self.profile.get("min_slope_hz_s", 40.0))
        min_r = float(self.profile.get("min_r", 0.70))
        min_dur = float(self.profile.get("min_duration_s", 0.50))

        mask = (f >= freq_min) & (f <= freq_max)
        f_b, s_b = f[mask], sxx[mask, :]
        dom_f = [float(f_b[np.argmax(s_b[:, col])]) for col in range(s_b.shape[1])]

        win_len = max(5, round(min_dur / (512 / sr)))
        positive = np.zeros(len(dom_f), dtype=bool)

        for i in range(len(dom_f) - win_len + 1):
            res = stats.linregress(t_sp[i : i + win_len], dom_f[i : i + win_len])
            if res.slope >= min_slope and res.rvalue >= min_r:
                positive[i : i + win_len] = True

        tones: list[DefibChargeTone] = []
        in_t = False
        s_idx = 0
        for i, pos in enumerate(positive):
            if pos and not in_t:
                in_t = True
                s_idx = i
            elif not pos and in_t:
                in_t = False
                res = stats.linregress(t_sp[s_idx:i], dom_f[s_idx:i])
                tones.append(
                    DefibChargeTone(
                        charge_start_s=float(t_sp[s_idx]),
                        charge_end_s=float(t_sp[i - 1]),
                        slope_hz_per_s=float(res.slope),
                        r_value=float(res.rvalue),
                    )
                )
        if in_t:
            res = stats.linregress(t_sp[s_idx:], dom_f[s_idx:])
            tones.append(
                DefibChargeTone(
                    charge_start_s=float(t_sp[s_idx]),
                    charge_end_s=float(t_sp[-1]),
                    slope_hz_per_s=float(res.slope),
                    r_value=float(res.rvalue),
                )
            )
        return tones

    def detect_events(self, audio_or_video_path: str | Path) -> list[DefibEvent]:
        """
        Runs full-track streaming detection for charge tones and shocks.
        """
        y, sr = load_audio_mono_16k(audio_or_video_path)
        tones = self.detect_tones(y, sr)

        w = int(0.05 * sr)
        env = np.sqrt(np.convolve(y**2, np.ones(w) / w, mode="same"))
        t_env = np.arange(len(env)) / sr

        search_win_s = float(self.profile.get("transient_search_window_s", 4.0))
        min_ratio = float(self.profile.get("min_transient_ratio", 4.0))

        events: list[DefibEvent] = []
        for tone in tones:
            c_e = tone.charge_end_s
            w_start = int(max(0, (c_e - 0.2)) * sr)
            w_end = int(min(len(env), (c_e + search_win_s)) * sr)
            sub_env = env[w_start:w_end]
            if len(sub_env) == 0:
                continue

            med_rms = float(np.median(env[max(0, w_start - int(3 * sr)) : w_start]))
            if med_rms <= 0:
                med_rms = 1e-6
            max_rms = float(np.max(sub_env))
            ratio = max_rms / med_rms
            t_trans = float(t_env[w_start + np.argmax(sub_env)])

            if ratio >= min_ratio:
                events.append(
                    DefibEvent(
                        event_type="defibrillation_shock",
                        timestamp_s=t_trans,
                        charge_start_s=tone.charge_start_s,
                        charge_end_s=tone.charge_end_s,
                        slope_hz_per_s=tone.slope_hz_per_s,
                        r_value=tone.r_value,
                        transient_ratio=ratio,
                        confidence=min(1.0, tone.r_value * 1.1),
                    )
                )
            else:
                events.append(
                    DefibEvent(
                        event_type="defib_charge_aborted",
                        timestamp_s=tone.charge_end_s,
                        charge_start_s=tone.charge_start_s,
                        charge_end_s=tone.charge_end_s,
                        slope_hz_per_s=tone.slope_hz_per_s,
                        r_value=tone.r_value,
                        transient_ratio=0.0,
                        confidence=tone.r_value,
                    )
                )

        events.sort(key=lambda e: e.timestamp_s)
        return events

    def inspect_rejection_window(
        self,
        audio_or_video_path: str | Path,
        t_target_s: float,
        search_window_s: float = 4.0,
    ) -> tuple[float, float]:
        """
        Inspects whether a target transient timestamp t_target_s was preceded
        by a valid narrowband charge tone within search_window_s.
        Returns (measured_slope, measured_r). If no valid narrowband charge tone
        preceded it, returns (0.0, 0.0), confirming near-zero slope and r.
        """
        y, sr = load_audio_mono_16k(audio_or_video_path)
        f, t_sp, sxx = signal.spectrogram(y, sr, nperseg=1024, noverlap=512)
        mask_all = (f > 200) & (f < 4000)
        dom_f_all = [
            float(f[mask_all][np.argmax(sxx[mask_all, col])])
            for col in range(sxx.shape[1])
        ]

        freq_min = float(self.profile.get("freq_min_hz", 400))
        freq_max = float(self.profile.get("freq_max_hz", 1000))
        mask = (f >= freq_min) & (f <= freq_max)
        dom_f_band = [
            float(f[mask][np.argmax(sxx[mask, col])]) for col in range(sxx.shape[1])
        ]

        win_len = max(
            5, round(float(self.profile.get("min_duration_s", 0.50)) / (512 / sr))
        )
        min_slope = float(self.profile.get("min_slope_hz_s", 40.0))
        min_r = float(self.profile.get("min_r", 0.70))

        best_slope = 0.0
        best_r = 0.0
        for i in range(len(t_sp) - win_len + 1):
            t0 = t_sp[i]
            t1 = t_sp[i + win_len - 1]
            if t_target_s - search_window_s <= t0 and t1 <= t_target_s:
                seg_all = np.array(dom_f_all[i : i + win_len])
                if np.mean((seg_all >= freq_min) & (seg_all <= freq_max)) >= 0.65:
                    res = stats.linregress(
                        t_sp[i : i + win_len], dom_f_band[i : i + win_len]
                    )
                    if res.slope >= min_slope and res.rvalue >= min_r:
                        if res.rvalue > best_r:
                            best_slope = float(res.slope)
                            best_r = float(res.rvalue)
        return best_slope, best_r
