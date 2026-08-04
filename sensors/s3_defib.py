"""
sensors/s3_defib.py — Sensor S3 defibrillator acoustic charge and shock detector.

The charge TONE is primary, not the discharge click. A 3-second rising
narrowband tone survives 16 kHz mono compression, distance, and room noise.
A sub-100ms transient barely does. Track the tone, then search a bounded
window after it for the transient.

defib_charge_aborted falls out of the else branch. The Constitution's
negative control needs no separate rule.

ARCHITECTURAL CONTRACT (F-013, F-014):
Sensor S3 operates as a WINDOWED ADJUDICATOR over candidate regions
proposed by LLM/P1 passes ("union for recall, acoustic adjudication for precision").
Standalone full-track detection without window gating yields ~100% false positives (F-014)
because speech formants and equipment alarms occupy the same 400-1000 Hz band.
It is precise WITHIN a bounded window and imprecise across a track.
"""

from dataclasses import dataclass
import logging
from pathlib import Path
import subprocess
from typing import Any, Sequence

import numpy as np
import soundfile as sf
from scipy import signal, stats
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

    @property
    def kind(self) -> str:
        return self.event_type

    @property
    def t(self) -> float:
        return self.timestamp_s

    @property
    def charge_slope_hz_s(self) -> float:
        return self.slope_hz_per_s

    @property
    def charge_r(self) -> float:
        return self.r_value


@dataclass(frozen=True)
class DefibVerdict:
    """Verdict returned by S3DefibDetector.adjudicate() when validating a candidate shock."""

    confirmed: bool
    candidate_t: float
    event: DefibEvent | None = None
    reason: str = ""


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
    Streaming detector for defibrillator charge tones and discharge transients.
    Per F-013, operates as a windowed adjudicator over LLM candidate regions.
    """

    def __init__(
        self,
        profile_name: str = "default",
        profile: str | None = None,
    ) -> None:
        self.profile_name = profile or profile_name
        self.profile = load_defib_profile(self.profile_name)

    def detect_tones(self, y: np.ndarray, sr: int) -> list[DefibChargeTone]:
        """Detects rising narrowband charge tones across the spectrogram, bridging fragmented rises across CPR interruptions."""
        f, t_sp, sxx = signal.spectrogram(y, sr, nperseg=1024, noverlap=512)
        freq_min = float(self.profile.get("freq_min_hz", 400))
        freq_max = float(self.profile.get("freq_max_hz", 1000))
        min_slope = float(self.profile.get("min_slope_hz_s", 40.0))
        min_r = float(self.profile.get("min_r", 0.70))
        min_dur = float(self.profile.get("min_duration_s", 1.1))

        mask = (f >= freq_min) & (f <= freq_max)
        f_b, s_b = f[mask], sxx[mask, :]
        dom_f = np.array([
            float(f_b[np.argmax(s_b[:, col])]) for col in range(s_b.shape[1])
        ])
        dom_f_med = signal.medfilt(dom_f, kernel_size=5)

        win_len = max(5, round(min(0.40, min_dur) / (512 / sr)))
        positive = np.zeros(len(dom_f_med), dtype=bool)

        for i in range(len(dom_f_med) - win_len + 1):
            res = stats.linregress(t_sp[i : i + win_len], dom_f_med[i : i + win_len])
            if res.slope >= min_slope and res.rvalue >= min_r:
                positive[i : i + win_len] = True

        fragments: list[dict[str, Any]] = []
        in_t = False
        s_idx = 0
        for i, pos in enumerate(positive):
            if pos and not in_t:
                in_t = True
                s_idx = i
            elif not pos and in_t:
                in_t = False
                res = stats.linregress(t_sp[s_idx:i], dom_f_med[s_idx:i])
                fragments.append({
                    "s": s_idx,
                    "e": i - 1,
                    "t_s": float(t_sp[s_idx]),
                    "t_e": float(t_sp[i - 1]),
                    "slope": float(res.slope),
                    "f_start": dom_f_med[s_idx],
                    "f_end": dom_f_med[i - 1],
                })
        if in_t:
            res = stats.linregress(t_sp[s_idx:], dom_f_med[s_idx:])
            fragments.append({
                "s": s_idx,
                "e": len(positive) - 1,
                "t_s": float(t_sp[s_idx]),
                "t_e": float(t_sp[-1]),
                "slope": float(res.slope),
                "f_start": dom_f_med[s_idx],
                "f_end": dom_f_med[-1],
            })

        merged: list[dict[str, Any]] = []
        if fragments:
            curr = dict(fragments[0])
            for nxt in fragments[1:]:
                gap = nxt["t_s"] - curr["t_e"]
                expected_f = curr["f_end"] + curr["slope"] * gap
                a_dur = curr["t_e"] - curr["t_s"]
                b_dur = nxt["t_e"] - nxt["t_s"]
                if (
                    0.0 <= gap <= 1.5
                    and abs(nxt["f_start"] - expected_f) <= 60.0
                    and abs(nxt["slope"] - curr["slope"]) <= 40.0
                    and (a_dur + gap + b_dur) >= min_dur
                ):
                    curr["e"] = nxt["e"]
                    curr["t_e"] = nxt["t_e"]
                    curr["f_end"] = nxt["f_end"]
                    res = stats.linregress(
                        t_sp[curr["s"] : curr["e"] + 1],
                        dom_f_med[curr["s"] : curr["e"] + 1],
                    )
                    curr["slope"] = float(res.slope)
                else:
                    merged.append(curr)
                    curr = dict(nxt)
            merged.append(curr)

        tones: list[DefibChargeTone] = []
        for m in merged:
            if m["t_e"] - m["t_s"] >= min_dur:
                span_mask = positive[m["s"] : m["e"] + 1]
                t_pts = t_sp[m["s"] : m["e"] + 1][span_mask]
                f_pts = dom_f_med[m["s"] : m["e"] + 1][span_mask]
                r_val = 0.85
                if len(t_pts) >= 5:
                    res = stats.linregress(t_pts, f_pts)
                    r_val = float(res.rvalue)
                tones.append(
                    DefibChargeTone(
                        charge_start_s=float(m["t_s"]),
                        charge_end_s=float(m["t_e"]),
                        slope_hz_per_s=float(m["slope"]),
                        r_value=r_val,
                    )
                )
        return tones

    def detect_events(
        self,
        audio_or_video_path: str | Path,
        candidate_windows: Sequence[tuple[float, float]] | None = None,
        max_duration_s: float | None = None,
    ) -> list[DefibEvent]:
        """
        Runs streaming detection for charge tones and shocks.
        When candidate_windows is provided (e.g. from LLM Union-of-k), operates
        as a windowed adjudicator confirming or rejecting within candidate regions.
        """
        y, sr = load_audio_mono_16k(audio_or_video_path)
        if max_duration_s is not None and max_duration_s > 0:
            max_samples = int(max_duration_s * sr)
            if len(y) > max_samples:
                y = y[:max_samples]
        tones = self.detect_tones(y, sr)

        w = int(0.05 * sr)
        env = np.sqrt(np.convolve(y**2, np.ones(w) / w, mode="same"))
        t_env = np.arange(len(env)) / sr

        search_win_s = float(self.profile.get("transient_search_window_s", 3.0))
        min_ratio = float(self.profile.get("min_transient_ratio", 5.0))

        events: list[DefibEvent] = []
        for tone in tones:
            c_e = tone.charge_end_s
            w_start = int(max(0, (c_e - 0.2)) * sr)
            w_end = int(min(len(env), (c_e + search_win_s)) * sr)
            sub_env = env[w_start:w_end]
            if len(sub_env) == 0:
                continue

            med_rms = float(np.median(env[max(0, w_start - int(2 * sr)) : w_start]))
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

        if candidate_windows is not None:
            filtered: list[DefibEvent] = []
            for ev in events:
                if any(
                    w_start <= ev.timestamp_s <= w_end
                    or w_start <= ev.charge_end_s <= w_end
                    for w_start, w_end in candidate_windows
                ):
                    filtered.append(ev)
            events = filtered

        events.sort(key=lambda e: e.timestamp_s)
        return events

    def detect_from_video(
        self,
        audio_or_video_path: str | Path,
        candidate_windows: Sequence[tuple[float, float]] | None = None,
        max_duration_s: float | None = None,
    ) -> list[DefibEvent]:
        """Alias for detect_events for compatibility with verification scripts."""
        return self.detect_events(
            audio_or_video_path,
            candidate_windows=candidate_windows,
            max_duration_s=max_duration_s,
        )

    def adjudicate(
        self,
        audio_or_video_path: str | Path,
        candidate_t: float,
        window_s: float = 30.0,
    ) -> DefibVerdict:
        """
        Confirm or reject a candidate shock proposed by P1 or another sensor.

        S3 is NOT a standalone detector. Full-track scanning at measured
        parameters yields ~100% false positives (F-014) because speech formants
        and alarm tones occupy the same 400-1000 Hz band. It is precise WITHIN
        a bounded window and imprecise across a track.

        Architecture: union-of-LLM-draws for recall, S3 for precision.
        """
        events = self.detect_events(audio_or_video_path)
        shocks = [e for e in events if e.event_type == "defibrillation_shock"]

        w_start = max(0.0, float(candidate_t) - float(window_s) / 2.0)
        w_end = float(candidate_t) + float(window_s) / 2.0

        matching = [
            s
            for s in shocks
            if w_start <= s.timestamp_s <= w_end
        ]
        if matching:
            best = min(
                matching, key=lambda s: abs(s.timestamp_s - float(candidate_t))
            )
            return DefibVerdict(
                confirmed=True,
                candidate_t=float(candidate_t),
                event=best,
                reason=(
                    f"Confirmed defibrillation_shock at t={best.timestamp_s:.2f}s "
                    f"(ratio={best.transient_ratio:.1f}x, slope={best.slope_hz_per_s:.1f})"
                ),
            )

        return DefibVerdict(
            confirmed=False,
            candidate_t=float(candidate_t),
            event=None,
            reason=f"No defibrillation_shock confirmed within candidate window around {candidate_t}s",
        )

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
            5, round(float(self.profile.get("min_duration_s", 1.1)) / (512 / sr))
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
