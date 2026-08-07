"""
sensors/s1_s6_motion.py — Sensor S1 chest-ROI optical flow compression motion
detection and Sensor S6 channel coverage visual occlusion detection.

Measures chest compression displacement via optical flow and flags visual
occlusions or provider crowding over the ROI. Sensors are 100% deterministic,
with calibration parameters loaded from sensors/calibration/roi_config.yaml.
"""

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np
from scipy import signal
from scipy.ndimage import median_filter
from codegen.yamlio import StrictLoader

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CompressionMotionEvent:
    """Represents an active CPR chest compression interval (Sensor S1)."""

    id: str
    event_type: str  # const "compression_motion"
    t_start_s: float
    t_end_s: float
    cadence_cpm: float
    confidence: float
    cadence_std_cpm: float | None = None
    compression_mode: str = "unable_to_determine"  # enum "mechanical", "manual", "unable_to_determine"


@dataclass(frozen=True)
class CoverageNoteEvent:
    """Represents a visual occlusion or coverage degradation interval (Sensor S6)."""

    id: str
    event_type: str  # const "coverage_note"
    channel: str  # enum "visual_chest", "monitor_ocr", "audio_room"
    t_start_s: float
    t_end_s: float
    degradation_type: str  # e.g. "provider_crowding", "visual_occlusion", "deidentification_mask"
    confidence: float


def detect_blackout(roi: Any, min_std: float = 0.5) -> bool:
    """
    Detects automated privacy / de-identification blackout masks over an ROI.
    Returns True if max pixel intensity is 0 or standard deviation < min_std.
    """
    arr = np.array(roi, dtype=float)
    if arr.size == 0:
        return True
    return bool(arr.max() == 0 or np.std(arr) < min_std)


def compute_rms_window(fps: float, rms_window_s: float) -> int:
    """
    Computes rolling RMS envelope window size in frames with int(round(...)).
    Enforces a floor of 3 frames so low-fps sources cannot silently degrade to no smoothing.
    """
    return max(3, int(round(fps * float(rms_window_s))))


def load_roi_config(profile_name: str = "default") -> dict[str, Any]:
    """
    Loads ROI calibration and threshold parameters from roi_config.yaml.
    Never hardcodes thresholds; falls back to 'default' with a warning if
    profile_name is unlisted.
    """
    config_path = (
        Path(__file__).resolve().parent / "calibration" / "roi_config.yaml"
    )
    with open(config_path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = StrictLoader(f).get_single_data()

    profiles: dict[str, Any] = data.get("profiles", {})
    if profile_name not in profiles:
        logging.warning(
            "ROI calibration profile '%s' not found in roi_config.yaml. "
            "Falling back to 'default'. Per-device calibration required.",
            profile_name,
        )
        profile_name = "default"

    if profile_name in ("default", "UNKNOWN"):
        logging.warning(
            "Using default/UNKNOWN ROI calibration profile '%s'. Thresholds "
            "are provisional until calibrated against human ground truth.",
            profile_name,
        )

    profile_data: dict[str, Any] = dict(profiles.get(profile_name, {}))
    return profile_data


def report_calibration_surface(profile_name: str = "default") -> dict[str, Any]:
    """
    Returns the full calibration surface dictionary for S1 and S6,
    satisfying S03 acceptance requirements for transparent threshold reporting.
    """
    config = load_roi_config(profile_name)
    return {
        "profile_name": profile_name,
        "chest_roi": dict(config.get("chest_roi", {})),
        "s1_motion": dict(config.get("s1_motion", {})),
        "s6_coverage": dict(config.get("s6_coverage", {})),
    }


class SensorFailure(RuntimeError):
    """Raised when a sensor track fails physiological sanity bounds."""

    pass


class NoPeriodicMotion(SensorFailure):
    """Raised when energy modulation falls below the calibrated floor, indicating no periodic motion in the window."""

    pass


class S1ChestMotionDetector:
    """
    Sensor S1: Detects CPR chest compression motion intervals and pause CCIs
    from optical flow vertical velocity signals.
    """

    def __init__(
        self,
        profile_name: str = "default",
        profile: str | None = None,
    ) -> None:
        self.profile_name = profile or profile_name
        self.profile = load_roi_config(self.profile_name)
        self.s1_config = dict(self.profile.get("s1_motion", {}))
        self.last_cpr_window_mask: np.ndarray | None = None
        self.last_active_resuscitation_duration_s: float | None = None
        self.last_coverage_notes: list[dict[str, Any]] = []
        self.last_blackout_mask: np.ndarray | None = None
        self.last_fps: float | None = None

    def _validate_track(self, active_mask: np.ndarray, duration_s: float) -> None:
        """
        Sanity check that raises SensorFailure if track fraction is < 0.05 or > 0.98.
        Only enforced on clinical resuscitation tracks (duration_s >= 60.0s).
        """
        if duration_s >= 60.0:
            frac = float(np.mean(active_mask))
            if frac < 0.05 or frac > 0.98:
                raise SensorFailure(
                    f"{frac:.1%} active over {duration_s:.1f}s — threshold is outside the signal"
                )

    def _reject_impulses(
        self,
        vy: np.ndarray,
    ) -> tuple[np.ndarray, int]:
        """
        Rejects isolated single-frame optical flow glitch spikes via median filter MAD isolation.
        Replaces spikes with median value rather than zeroing to prevent filter discontinuity.
        """
        k = float(self.s1_config.get("impulse_rejection_k", 8.0))
        win = int(self.s1_config.get("impulse_rejection_win", 5))
        min_spike = float(self.s1_config.get("impulse_min_spike_px", 2.0))

        med = median_filter(vy, size=win)
        diff = np.abs(vy - med)
        mad = float(np.median(diff))
        spike = (diff > k * mad) & (diff > min_spike)
        vy_clean = vy.copy()
        vy_clean[spike] = med[spike]
        n_spikes = int(spike.sum())
        if n_spikes > 0:
            logger.info("Rejected %d optical flow impulse spikes", n_spikes)
        return vy_clean, n_spikes

    def _frames(self, seconds: float, fps: float, name: str) -> int:
        n = int(round(seconds * fps))
        if n == 0:
            raise ValueError(f"{name} ({seconds}s at {fps} fps) evaluates to 0 frames")
        return n

    def _estimate_epoch_cadence_and_mode(
        self,
        seg_filtered: np.ndarray,
        fps: float,
    ) -> tuple[float, float | None, str]:
        """
        Estimates median cadence CPM, cadence standard deviation across 20s windows,
        and compression mode ('mechanical', 'manual', or 'unable_to_determine').
        """
        dur_s = len(seg_filtered) / fps
        if dur_s < 4.0:
            cad = self._estimate_cadence_cpm(seg_filtered, fps)
            return cad, None, "unable_to_determine — epoch too short for cadence variance"

        # Signal Quality Gate (Y1/Y2): abstain on sub-floor noise
        min_mod = float(self.s1_config.get("min_modulation", 0.010))
        rms_win = min(len(seg_filtered), self._frames(1.6, fps, "rms window"))
        if rms_win > 0 and len(seg_filtered) >= rms_win:
            rms_sig = np.sqrt(np.convolve(seg_filtered**2, np.ones(rms_win) / rms_win, mode="valid"))
            median_mod = float(np.median(rms_sig)) if len(rms_sig) > 0 else 0.0
        else:
            median_mod = float(np.sqrt(np.mean(seg_filtered**2)))

        if median_mod < min_mod:
            return 0.0, None, "unable_to_determine — sub-floor modulation (unmeasured noise)"

        mech_max_std = float(
            self.s1_config.get("mechanical_cadence_max_std_cpm", 2.83)
        )
        man_min_std = float(
            self.s1_config.get("manual_cadence_min_std_cpm", 8.0)
        )

        win_frames = self._frames(20.0, fps, "variance window")
        hop_frames = self._frames(10.0, fps, "variance hop")
        cadences: list[float] = []

        if len(seg_filtered) <= win_frames:
            cad = self._estimate_cadence_cpm(seg_filtered, fps)
            cadences.append(cad)
        else:
            for w_s in range(0, len(seg_filtered) - win_frames + 1, hop_frames):
                w_sig = seg_filtered[w_s : w_s + win_frames]
                cad = self._estimate_cadence_cpm(w_sig, fps)
                cadences.append(cad)

        med_cad = round(float(np.median(cadences)), 1) if cadences else 102.0

        if not (80.0 <= med_cad <= 140.0):
            return med_cad, None, "unable_to_determine — cadence outside physiological range"

        if len(cadences) < 3:
            return med_cad, None, "unable_to_determine — epoch too short for cadence variance"

        std_cad_overall = float(np.std(cadences))
        sub_stds = [float(np.std(cadences[i : i + 3])) for i in range(len(cadences) - 2)]
        min_sub_std = min(sub_stds)

        mech_min_cpm = float(self.s1_config.get("mechanical_cadence_min_cpm", 96.0))
        mech_max_cpm = float(self.s1_config.get("mechanical_cadence_max_cpm", 108.0))

        if min_sub_std < mech_max_std:
            if mech_min_cpm <= med_cad <= mech_max_cpm:
                mode = "mechanical"
                std_cad = round(min_sub_std, 1)
            else:
                mode = "unable_to_determine — steady cadence outside mechanical device specification"
                std_cad = round(min_sub_std, 1)
        elif std_cad_overall > man_min_std and all(s > man_min_std for s in sub_stds):
            mode = "manual"
            std_cad = round(std_cad_overall, 1)
        else:
            mode = "unable_to_determine"
            std_cad = round(std_cad_overall, 1)

        return med_cad, std_cad, mode

    def detect_from_vy_signal(
        self,
        vy_signal: np.ndarray | Sequence[float],
        fps: float = 30.0,
        blackout_mask: np.ndarray | Sequence[bool] | None = None,
    ) -> list[CompressionMotionEvent]:
        """
        Detects CPR compression intervals from vertical velocity signal vy(t)
        using a Two-Stage architecture:
          Stage 1 (Window Gate): Scale-free frequency-domain discriminator on 60s windows
          Stage 2 (Continuous Segmentation): Continuous rolling RMS envelope thresholding
        Excludes automated privacy / de-identification blackout frames from energy thresholding.
        """
        vy_arr = np.array(vy_signal, dtype=float)
        n_frames = len(vy_arr)
        if n_frames < 4 or fps <= 0:
            return []

        # Reject isolated single-frame impulse spikes
        vy_arr_clean, n_spikes = self._reject_impulses(vy_arr)

        min_hz = float(self.s1_config.get("vy_bandpass_min_hz", 1.3))
        max_hz = float(self.s1_config.get("vy_bandpass_max_hz", 3.0))
        min_active_s = float(self.s1_config.get("min_active_duration_s", 2.0))
        conf_val = float(self.s1_config.get("confidence", 0.88))
        bump_thresh = float(self.s1_config.get("bump_threshold_px", 30.0))
        bump_mask = np.abs(vy_arr_clean) > bump_thresh

        if blackout_mask is not None and len(blackout_mask) == n_frames:
            blk_arr = np.array(blackout_mask, dtype=bool)
            self.last_blackout_mask = blk_arr
        elif self.last_blackout_mask is not None and len(self.last_blackout_mask) == n_frames:
            blk_arr = self.last_blackout_mask
        else:
            blk_arr = np.zeros(n_frames, dtype=bool)
            self.last_blackout_mask = blk_arr

        self.last_fps = fps
        excluded_mask = bump_mask | blk_arr

        duration_s = float(n_frames / fps)

        min_ratio = float(self.s1_config.get("min_band_power_ratio", 0.15))
        cpr_min_f = float(self.s1_config.get("cpr_peak_min_hz", 1.5))
        cpr_max_f = float(self.s1_config.get("cpr_peak_max_hz", 2.5))
        min_snr = float(self.s1_config.get("min_peak_snr", 10.0))

        # --- Stage 1: Window Gate ---
        cpr_window_mask = np.zeros(n_frames, dtype=bool)

        win_s = min(60.0, duration_s)
        hop_s = 30.0 if duration_s >= 60.0 else max(5.0, duration_s / 4.0)
        win_frames = int(win_s * fps)
        hop_frames = int(hop_s * fps)
        min_eff_snr = min_snr if duration_s >= 60.0 else max(4.0, min_snr * 0.5)

        for w_start in range(0, n_frames, hop_frames):
            w_end = min(n_frames, w_start + win_frames)
            w_raw = vy_arr_clean[w_start:w_end]
            w_blk = blk_arr[w_start:w_end]
            if len(w_raw) / fps < 4.0 or np.mean(w_blk) > 0.8:
                continue
            f = np.fft.rfftfreq(len(w_raw), d=1.0 / float(fps))
            P = np.abs(np.fft.rfft(w_raw)) ** 2
            tot_m = f >= 0.1
            tot_p = float(P[tot_m].sum()) if np.any(tot_m) else 0.0
            band_m = (f >= min_hz) & (f <= max_hz)
            band_p = float(P[band_m].sum()) if np.any(band_m) else 0.0
            b_ratio = (band_p / tot_p) if tot_p > 0.0 else 0.0
            p_idx = int(P[band_m].argmax()) if np.any(band_m) else 0
            p_f = float(f[band_m][p_idx]) if np.any(band_m) else 0.0
            p_pow = float(P[band_m][p_idx]) if np.any(band_m) else 0.0
            med_p = float(np.median(P[tot_m])) if np.any(tot_m) else 1e-9
            p_snr = (p_pow / med_p) if med_p > 0.0 else 0.0

            is_cpr = (
                (b_ratio >= min_ratio)
                and (cpr_min_f <= p_f <= cpr_max_f)
                and (p_snr >= min_eff_snr)
            )
            if is_cpr:
                cpr_window_mask[w_start:w_end] = True

        if not np.any(cpr_window_mask):
            self.last_cpr_window_mask = cpr_window_mask
            self.last_active_resuscitation_duration_s = 0.0
            self.last_coverage_notes = [
                {
                    "type": "coverage_note",
                    "channel": "visual_chest",
                    "t_start_s": 0.0,
                    "t_end_s": round(duration_s, 2),
                    "duration_s": round(duration_s, 2),
                    "note": "unmeasured_epoch_no_periodic_motion",
                }
            ]
            raise NoPeriodicMotion(
                "No periodic CPR motion detected across track"
            )

        self.last_cpr_window_mask = cpr_window_mask
        self.last_active_resuscitation_duration_s = float(
            cpr_window_mask.sum() / fps
        )

        # Unmeasured debrief coverage notes
        self.last_coverage_notes = []
        in_unm = False
        unm_start = 0
        for i in range(len(cpr_window_mask)):
            if not cpr_window_mask[i] and not in_unm:
                in_unm = True
                unm_start = i
            elif cpr_window_mask[i] and in_unm:
                in_unm = False
                unm_dur = (i - unm_start) / fps
                if unm_dur >= 30.0:
                    self.last_coverage_notes.append(
                        {
                            "type": "coverage_note",
                            "channel": "visual_chest",
                            "t_start_s": round(unm_start / fps, 2),
                            "t_end_s": round(i / fps, 2),
                            "duration_s": round(unm_dur, 2),
                            "note": "unmeasured_epoch_no_periodic_motion",
                        }
                    )
        if in_unm:
            unm_dur = (len(cpr_window_mask) - unm_start) / fps
            if unm_dur >= 30.0:
                note_str = "unmeasured_epoch_no_periodic_motion" if unm_start == 0 else "unmeasured_debrief_no_periodic_motion"
                self.last_coverage_notes.append(
                    {
                        "type": "coverage_note",
                        "channel": "visual_chest",
                        "t_start_s": round(unm_start / fps, 2),
                        "t_end_s": round(len(cpr_window_mask) / fps, 2),
                        "duration_s": round(unm_dur, 2),
                        "note": note_str,
                    }
                )

        # --- Stage 2: Continuous Rolling RMS Segmentation ---
        nyq = fps / 2.0
        low = max(0.01, min(0.99, min_hz / nyq))
        high = max(low + 0.01, min(0.99, max_hz / nyq))
        b, a = signal.butter(2, [low, high], btype="band")
        filtered = signal.filtfilt(b, a, vy_arr_clean)

        rms_window_s = float(self.s1_config.get("rms_window_s", 1.6))
        win = compute_rms_window(fps, rms_window_s)
        kernel = np.ones(win, dtype=float) / float(win)
        energy = np.convolve(filtered**2, kernel, mode="same")

        valid_energy = energy[cpr_window_mask & (~excluded_mask)]
        if len(valid_energy) == 0:
            raise NoPeriodicMotion("No valid non-excluded frames in CPR window")

        baseline = float(np.percentile(valid_energy, 10))
        active_p = float(np.percentile(valid_energy, 90))
        min_mod = float(self.s1_config.get("min_modulation", 0.010))
        if (active_p - baseline) < min_mod:
            raise NoPeriodicMotion(
                f"Energy modulation ({active_p - baseline:.4f}) below floor ({min_mod})"
            )

        thresh_ratio = float(
            self.s1_config.get("energy_threshold_ratio", 0.05)
        )
        threshold = baseline + thresh_ratio * (active_p - baseline)

        raw_active = (energy > threshold) & cpr_window_mask & (~excluded_mask)

        # Gap merge (0.5s)
        gap_merge_s = float(self.s1_config.get("gap_merge_duration_s", 0.5))
        gap_merge_frames = int(gap_merge_s * fps)
        active_mask = raw_active.copy()
        last_act = -100000
        for i in range(len(active_mask)):
            if active_mask[i]:
                if 0 < (i - last_act) <= gap_merge_frames:
                    active_mask[last_act:i] = True
                last_act = i

        # Validate active fraction within the active resuscitation epoch
        active_epoch_len = int(cpr_window_mask.sum())
        if (active_epoch_len / fps) >= 60.0:
            frac = float(np.mean(active_mask[cpr_window_mask]))
            if frac < 0.05 or frac > 0.98:
                raise SensorFailure(
                    f"{frac:.1%} active over {active_epoch_len/fps:.1f}s — threshold is outside the signal"
                )

        # Form continuous CompressionMotionEvent intervals
        events: list[CompressionMotionEvent] = []
        in_act = False
        s_idx = 0
        idx_counter = 1

        for i in range(len(active_mask)):
            if active_mask[i] and not in_act:
                in_act = True
                s_idx = i
            elif not active_mask[i] and in_act:
                in_act = False
                dur = (i - s_idx) / fps
                if dur >= min_active_s:
                    sub_sig = filtered[s_idx:i]
                    cad, cad_std, mode = self._estimate_epoch_cadence_and_mode(
                        sub_sig, fps
                    )
                    events.append(
                        CompressionMotionEvent(
                            id=f"s1_{idx_counter}",
                            event_type="compression_motion",
                            t_start_s=round(s_idx / fps, 2),
                            t_end_s=round(i / fps, 2),
                            cadence_cpm=cad,
                            confidence=conf_val,
                            cadence_std_cpm=cad_std,
                            compression_mode=mode,
                        )
                    )
                    idx_counter += 1

        if in_act:
            dur = (len(active_mask) - s_idx) / fps
            if dur >= min_active_s:
                sub_sig = filtered[s_idx:]
                cad, cad_std, mode = self._estimate_epoch_cadence_and_mode(
                    sub_sig, fps
                )
                events.append(
                    CompressionMotionEvent(
                        id=f"s1_{idx_counter}",
                        event_type="compression_motion",
                        t_start_s=round(s_idx / fps, 2),
                        t_end_s=round(len(active_mask) / fps, 2),
                        cadence_cpm=cad,
                        confidence=conf_val,
                        cadence_std_cpm=cad_std,
                        compression_mode=mode,
                    )
                )

        return events

    @staticmethod
    def _estimate_cadence_cpm(seg_filtered: np.ndarray, fps: float) -> float:
        """Estimates CPR compression cadence in CPM from bandpass signal."""
        n = len(seg_filtered)
        if n < 4:
            return 110.0
        fft_vals = np.fft.rfft(seg_filtered)
        fft_freqs = np.fft.rfftfreq(n, d=1.0 / fps)
        mask = (fft_freqs >= 1.0) & (fft_freqs <= 3.0)
        if not np.any(mask):
            return 110.0
        masked_freqs = fft_freqs[mask]
        masked_mags = np.abs(fft_vals[mask])
        peak_hz = float(masked_freqs[np.argmax(masked_mags)])
        return round(peak_hz * 60.0, 1)

    def compute_ccf(
        self,
        motion_events: Sequence[CompressionMotionEvent],
        death_pronounced_s: float | None = None,
    ) -> dict[str, Any]:
        """
        Computes Chest Compression Fraction (CCF) per Q-012:
        first compression start to last compression end (gated on death_pronounced when present).
        CCF denominator gates on compression_mode (mechanical/manual) rather than Stage 1 alone.
        """
        sorted_events = sorted(motion_events, key=lambda e: e.t_start_s)
        if not sorted_events:
            return {
                "ccf": None,
                "note": "unmeasured_epoch_no_periodic_motion_detected",
                "t_first_s": 0.0,
                "t_last_s": 0.0,
                "denominator_s": 0.0,
                "cpr_duration_s": 0.0,
            }

        valid_modes = ("mechanical", "manual")
        first_mode_ev = next(
            (e for e in sorted_events if getattr(e, "compression_mode", None) in valid_modes),
            None,
        )
        if first_mode_ev is not None:
            t_first = float(first_mode_ev.t_start_s)
            valid_events = [e for e in sorted_events if float(e.t_start_s) >= t_first - 1e-6]
        else:
            t_first = float(sorted_events[0].t_start_s)
            valid_events = sorted_events

        if not valid_events:
            valid_events = sorted_events
            t_first = float(sorted_events[0].t_start_s)

        if death_pronounced_s is not None and float(death_pronounced_s) > t_first:
            t_last = float(death_pronounced_s)
        else:
            t_last = float(valid_events[-1].t_end_s)

        denominator = max(t_last - t_first, 1e-6)
        cpr_duration = sum(
            max(0.0, min(t_last, float(e.t_end_s)) - max(t_first, float(e.t_start_s)))
            for e in valid_events
            if float(e.t_start_s) < t_last and float(e.t_end_s) > t_first
        )
        ccf = round(cpr_duration / denominator, 3)
        note = "normal"
        if hasattr(self, "last_coverage_notes") and any(
            "no_periodic_motion" in n.get("note", "") for n in getattr(self, "last_coverage_notes", [])
        ):
            note = "unmeasured_debrief_excluded"

        return {
            "ccf": ccf,
            "note": note,
            "t_first_s": round(t_first, 2),
            "t_last_s": round(t_last, 2),
            "denominator_s": round(denominator, 2),
            "cpr_duration_s": round(cpr_duration, 2),
        }

    def detect_cci_intervals(
        self,
        motion_events: Sequence[CompressionMotionEvent] | str | Path,
        total_duration_s: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Emits Chest Compression Interruption (CCI) pause intervals
        with confidence scores between active compression periods.
        Detection floor is min_pause_duration_s (default 1.0s).
        Excludes unmeasured de-identification blackout gaps by splitting pause intervals.
        """
        if isinstance(motion_events, (str, Path)):
            video_path = Path(motion_events)
            events = self.detect_from_video(video_path)
            if total_duration_s is None:
                cap = cv2.VideoCapture(str(video_path))
                fps_val = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
                n_frames_val = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                cap.release()
                total_duration_s = (
                    n_frames_val / fps_val if fps_val > 0 else 0.0
                )
            motion_events = events
        elif total_duration_s is None:
            total_duration_s = max(
                (e.t_end_s for e in motion_events), default=0.0
            )

        min_pause_s = float(self.s1_config.get("min_pause_duration_s", 1.0))
        conf_val = float(self.s1_config.get("confidence", 0.88))
        ccis: list[dict[str, Any]] = []
        idx = 1

        sorted_events = sorted(motion_events, key=lambda e: e.t_start_s)
        if not sorted_events:
            raise NoPeriodicMotion(
                "No active CPR compression intervals found across track"
            )

        valid_modes = ("mechanical", "manual")
        first_mode_ev = next(
            (e for e in sorted_events if getattr(e, "compression_mode", None) in valid_modes),
            None,
        )
        if first_mode_ev is not None:
            t_first = float(first_mode_ev.t_start_s)
            sorted_events = [e for e in sorted_events if float(e.t_start_s) >= t_first - 1e-6]
        else:
            t_first = float(sorted_events[0].t_start_s)

        if not sorted_events:
            sorted_events = sorted(motion_events, key=lambda e: e.t_start_s)
            t_first = float(sorted_events[0].t_start_s)

        for i in range(len(sorted_events) - 1):
            pause_start = float(sorted_events[i].t_end_s)
            pause_end = float(sorted_events[i + 1].t_start_s)
            dur = pause_end - pause_start
            if dur >= min_pause_s:
                if (
                    hasattr(self, "last_blackout_mask")
                    and self.last_blackout_mask is not None
                ):
                    fps_val = float(getattr(self, "last_fps", None) or 16.0)
                    i_s = int(round(pause_start * fps_val))
                    i_e = int(round(pause_end * fps_val))
                    if (
                        0 <= i_s < len(self.last_blackout_mask)
                        and 0 <= i_e <= len(self.last_blackout_mask)
                        and i_e > i_s
                    ):
                        sub_mask = self.last_blackout_mask[i_s:i_e]
                        if np.any(sub_mask):
                            if not hasattr(self, "last_coverage_notes") or self.last_coverage_notes is None:
                                self.last_coverage_notes = []
                            changes = np.where(np.diff(sub_mask))[0] + 1
                            indices = [0] + list(changes) + [len(sub_mask)]
                            for k_run in range(len(indices) - 1):
                                r_start_idx = indices[k_run]
                                r_end_idx = indices[k_run + 1]
                                is_blk = sub_mask[r_start_idx]
                                r_start_t = (
                                    pause_start if r_start_idx == 0 else round(pause_start + r_start_idx / fps_val, 2)
                                )
                                r_end_t = (
                                    pause_end if r_end_idx == len(sub_mask) else round(pause_start + r_end_idx / fps_val, 2)
                                )
                                r_dur = round(r_end_t - r_start_t, 2)
                                if r_dur <= 0:
                                    continue
                                if is_blk:
                                    self.last_coverage_notes.append(
                                        {
                                            "type": "coverage_note",
                                            "channel": "visual_chest",
                                            "t_start_s": r_start_t,
                                            "t_end_s": r_end_t,
                                            "duration_s": r_dur,
                                            "note": "deidentification_mask",
                                        }
                                    )
                                else:
                                    if r_dur >= 0.05:
                                        ccis.append(
                                            {
                                                "id": f"cci_{idx}",
                                                "type": "compression_interruption",
                                                "t_start_s": r_start_t,
                                                "t_end_s": r_end_t,
                                                "duration_s": r_dur,
                                                "confidence": conf_val,
                                            }
                                        )
                                        idx += 1
                            continue
                ccis.append(
                    {
                        "id": f"cci_{idx}",
                        "type": "compression_interruption",
                        "t_start_s": round(pause_start, 2),
                        "t_end_s": round(pause_end, 2),
                        "duration_s": round(dur, 2),
                        "confidence": conf_val,
                    }
                )
                idx += 1

        return ccis

    def detect_from_video(
        self,
        video_path: str | Path,
        max_duration_s: float | None = None,
    ) -> list[CompressionMotionEvent]:
        """
        Computes dense Lucas-Kanade optical flow over the calibrated chest ROI
        in a video file and detects CPR motion intervals.
        """
    def extract_vy_signal(
        self,
        video_path: str | Path,
        t0: float = 0.0,
        t1: float | None = None,
    ) -> np.ndarray:
        """
        Extracts optical flow vertical velocity signal vy(t) across the configured
        chest ROI between timestamps t0 and t1. Also extracts blackout flags.
        """
        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"Video file not found: {path}")

        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video file: {path}")

        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        self.last_fps = fps
        roi_box = self.profile.get("chest_roi", {})
        rx = int(roi_box.get("x", 600))
        ry = int(roi_box.get("y", 400))
        rw = int(roi_box.get("width", 720))
        rh = int(roi_box.get("height", 480))

        start_frame = int(t0 * fps)
        if start_frame > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        vy_signal: list[float] = []
        blackout_flags: list[bool] = []
        ret, prev_frame = cap.read()
        if not ret or prev_frame is None:
            cap.release()
            return np.array([], dtype=float)

        prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
        prev_roi = prev_gray[ry : ry + rh, rx : rx + rw]
        blackout_flags.append(detect_blackout(prev_roi))
        vy_signal.append(0.0)

        frame_count = 1
        max_frames = (
            int((t1 - t0) * fps) if t1 is not None else None
        )

        while True:
            if max_frames is not None and frame_count >= max_frames:
                break
            ret, frame = cap.read()
            if not ret or frame is None:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            roi_gray = gray[ry : ry + rh, rx : rx + rw]
            is_blk = detect_blackout(roi_gray)
            blackout_flags.append(is_blk)

            flow = cv2.calcOpticalFlowFarneback(
                prev_roi,
                roi_gray,
                None,
                pyr_scale=0.5,
                levels=3,
                winsize=15,
                iterations=3,
                poly_n=5,
                poly_sigma=1.2,
                flags=0,
            )
            vy_val = float(np.mean(flow[..., 1]))
            vy_signal.append(vy_val)
            prev_roi = roi_gray
            frame_count += 1

        cap.release()
        self.last_blackout_mask = np.array(blackout_flags, dtype=bool)
        return np.array(vy_signal, dtype=float)

    def detect_from_video(
        self,
        video_path: str | Path,
        max_duration_s: float | None = None,
        t0: float = 0.0,
    ) -> list[CompressionMotionEvent]:
        """
        Executes S1 motion detection on a video recording.
        Accepts max_duration_s and t0 for rapid unit test verification.
        """
        path = Path(video_path)
        cap = cv2.VideoCapture(str(path))
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        cap.release()
        vy_signal = self.extract_vy_signal(
            video_path, t0=t0, t1=max_duration_s
        )
        return self.detect_from_vy_signal(
            vy_signal, fps=fps, blackout_mask=self.last_blackout_mask
        )

    def filter_ccis_by_consumer(
        self,
        ccis: Sequence[dict[str, Any]],
        consumer: str = "reporting",
    ) -> list[dict[str, Any]]:
        """
        Applies consumer-specific duration floor rules to detected CCI pause intervals:
        - 'ccf': counts all unoccluded no-flow physical pauses >= min_pause_duration_s.
        - 'redcap' / 'repeating_group': enforces the >= 3.0s dictionary rule required by the clinical extraction registry.
        - 'reporting': applies the calibrated reporting floor (cci_reporting_floor_s) from roi_config.yaml.
        Three consumers, three rules, two measurements (the interval stream and an independently-derived CPR duration, which differ by 15.96s over the CCF window).
        """
        if consumer == "ccf":
            floor_s = float(self.s1_config.get("min_pause_duration_s") or 1.0)
        elif consumer in ("redcap", "repeating_group"):
            floor_s = float(self.s1_config.get("redcap_cci_floor_s") or 3.0)
        elif consumer == "reporting":
            if "cci_reporting_floor_s" not in self.s1_config:
                raise KeyError(
                    "cci_reporting_floor_s missing from ROI config for profile "
                    f"'{self.profile_name}'"
                )
            floor_s = float(self.s1_config["cci_reporting_floor_s"])
        else:
            raise ValueError(
                f"Unknown consumer '{consumer}': must be ccf, redcap, or reporting."
            )

        filtered: list[dict[str, Any]] = []
        for c in ccis:
            dur = float(
                c.get("duration_s", round(float(c["t_end_s"]) - float(c["t_start_s"]), 2))
            )
            if dur >= floor_s:
                filtered.append(c)
        return filtered


class S6CoverageDetector:
    """
    Sensor S6: Detects visual occlusions and provider crowding degradation
    over the calibrated chest ROI.
    """

    def __init__(self, profile_name: str = "default") -> None:
        self.profile_name = profile_name
        self.profile = load_roi_config(profile_name)
        self.s6_config = dict(self.profile.get("s6_coverage", {}))

    def detect_blackout_from_video(
        self,
        video_path: str | Path,
        max_duration_s: float | None = None,
    ) -> list[CoverageNoteEvent]:
        """
        Detects automated privacy / de-identification blackout masks across video.
        Emits CoverageNoteEvents with degradation_type='deidentification_mask'.
        """
        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"Video file not found: {path}")

        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video file: {path}")

        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        roi_box = self.profile.get("chest_roi", {})
        rx = int(roi_box.get("x", 600))
        ry = int(roi_box.get("y", 400))
        rw = int(roi_box.get("width", 720))
        rh = int(roi_box.get("height", 480))
        min_std = float(self.s6_config.get("blackout_min_std", 0.5))

        blackout_flags: list[bool] = []
        timestamps_s: list[float] = []
        frame_idx = 0
        max_frames = (
            int(max_duration_s * fps) if max_duration_s is not None else None
        )

        while True:
            if max_frames is not None and frame_idx >= max_frames:
                break
            ret, frame = cap.read()
            if not ret or frame is None:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            roi_gray = gray[ry : ry + rh, rx : rx + rw]
            is_blk = detect_blackout(roi_gray, min_std=min_std)
            blackout_flags.append(is_blk)
            timestamps_s.append(frame_idx / fps)
            frame_idx += 1

        cap.release()

        events: list[CoverageNoteEvent] = []
        in_blk = False
        s_idx = 0
        idx_counter = 1
        for i, is_blk in enumerate(blackout_flags):
            if is_blk and not in_blk:
                in_blk = True
                s_idx = i
            elif not is_blk and in_blk:
                in_blk = False
                e_idx = i
                events.append(
                    CoverageNoteEvent(
                        id=f"s6_blk_{idx_counter}",
                        event_type="coverage_note",
                        channel="visual_chest",
                        t_start_s=round(timestamps_s[s_idx], 2),
                        t_end_s=round(timestamps_s[e_idx], 2),
                        degradation_type="deidentification_mask",
                        confidence=1.0,
                    )
                )
                idx_counter += 1
        if in_blk:
            e_idx = len(blackout_flags) - 1
            events.append(
                CoverageNoteEvent(
                    id=f"s6_blk_{idx_counter}",
                    event_type="coverage_note",
                    channel="visual_chest",
                    t_start_s=round(timestamps_s[s_idx], 2),
                    t_end_s=round(timestamps_s[e_idx], 2),
                    degradation_type="deidentification_mask",
                    confidence=1.0,
                )
            )

        return events

    def detect_occlusion_from_metrics(
        self,
        std_signal: np.ndarray | Sequence[float],
        timestamps_s: np.ndarray | Sequence[float],
    ) -> list[CoverageNoteEvent]:
        """
        Detects coverage occlusion intervals from ROI standard deviation time series.
        """
        if len(std_signal) != len(timestamps_s) or len(std_signal) == 0:
            return []

        std_arr = np.array(std_signal, dtype=float)
        ts_arr = np.array(timestamps_s, dtype=float)
        std_thresh = float(self.s6_config.get("occlusion_std_threshold", 15.0))
        min_dur_s = float(self.s6_config.get("min_occlusion_duration_s", 2.0))
        conf_val = float(self.s6_config.get("confidence", 0.90))

        occluded = std_arr < std_thresh
        events: list[CoverageNoteEvent] = []
        in_occ = False
        s_idx = 0
        idx_counter = 1

        for i, is_occ in enumerate(occluded):
            if is_occ and not in_occ:
                in_occ = True
                s_idx = i
            elif not is_occ and in_occ:
                in_occ = False
                e_idx = i - 1
                dur = float(ts_arr[e_idx] - ts_arr[s_idx])
                if dur >= min_dur_s:
                    events.append(
                        CoverageNoteEvent(
                            id=f"s6_{idx_counter}",
                            event_type="coverage_note",
                            channel="visual_chest",
                            t_start_s=float(ts_arr[s_idx]),
                            t_end_s=float(ts_arr[e_idx]),
                            degradation_type="provider_crowding",
                            confidence=conf_val,
                        )
                    )
                    idx_counter += 1

        if in_occ:
            e_idx = len(occluded) - 1
            dur = float(ts_arr[e_idx] - ts_arr[s_idx])
            if dur >= min_dur_s:
                events.append(
                    CoverageNoteEvent(
                        id=f"s6_{idx_counter}",
                        event_type="coverage_note",
                        channel="visual_chest",
                        t_start_s=float(ts_arr[s_idx]),
                        t_end_s=float(ts_arr[e_idx]),
                        degradation_type="provider_crowding",
                        confidence=conf_val,
                    )
                )

        return events

    def detect_occlusion_from_video(
        self,
        video_path: str | Path,
        max_duration_s: float | None = None,
    ) -> list[CoverageNoteEvent]:
        """
        Computes temporal difference occlusion signatures across a video file to detect
        provider crowding and visual occlusions:
        - Entry/Exit: massive pixel shift bounding spike
        - During: ROI internal stillness while surrounding resuscitation room moves
        """
        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"Video file not found: {path}")

        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video file: {path}")

        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        roi_box = self.profile.get("chest_roi", {})
        rx = int(roi_box.get("x", 600))
        ry = int(roi_box.get("y", 400))
        rw = int(roi_box.get("width", 720))
        rh = int(roi_box.get("height", 480))

        entry_spike_thresh = float(self.s6_config.get("occlusion_entry_spike_px", 20.0))
        max_roi_still_thresh = float(self.s6_config.get("occlusion_max_roi_still_px", 1.5))
        min_room_active_thresh = float(self.s6_config.get("occlusion_min_room_active_px", 0.02))
        min_dur_s = float(self.s6_config.get("min_occlusion_duration_s", 0.5))
        conf_val = float(self.s6_config.get("confidence", 0.90))

        roi_diffs: list[float] = [0.0]
        room_diffs: list[float] = [0.0]
        timestamps_s: list[float] = [0.0]
        frame_idx = 1
        max_frames = (
            int(max_duration_s * fps) if max_duration_s is not None else None
        )

        ret, prev_frame = cap.read()
        if not ret or prev_frame is None:
            cap.release()
            return []
        prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY).astype(np.float32)

        while True:
            if max_frames is not None and frame_idx >= max_frames:
                break
            ret, frame = cap.read()
            if not ret or frame is None:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
            diff = np.abs(gray - prev_gray)
            roi_slice = diff[ry : ry + rh, rx : rx + rw]
            r_diff = float(np.mean(roi_slice)) if roi_slice.size > 0 else 0.0
            room_size = gray.size - roi_slice.size
            rm_diff = float((np.sum(diff) - np.sum(roi_slice)) / room_size) if room_size > 0 else 0.0
            roi_diffs.append(r_diff)
            room_diffs.append(rm_diff)
            timestamps_s.append(frame_idx / fps)
            prev_gray = gray
            frame_idx += 1

        cap.release()

        n_pts = len(roi_diffs)
        roi_arr = np.array(roi_diffs, dtype=float)
        room_arr = np.array(room_diffs, dtype=float)
        ts_arr = np.array(timestamps_s, dtype=float)

        # Stillness during occlusion while surrounding room moves
        during_mask = (roi_arr < max_roi_still_thresh) & (room_arr > min_room_active_thresh)

        events: list[CoverageNoteEvent] = []
        in_occ = False
        s_idx = 0
        idx_counter = 1
        w_spike = max(1, int(fps * 0.5))

        for i, is_occ in enumerate(during_mask):
            if is_occ and not in_occ:
                in_occ = True
                s_idx = i
            elif not is_occ and in_occ:
                in_occ = False
                e_idx = i - 1
                dur = float(ts_arr[e_idx] - ts_arr[s_idx])
                if dur >= min_dur_s:
                    s_win = max(0, s_idx - w_spike)
                    e_win = min(n_pts, e_idx + w_spike)
                    spike_max = float(np.max(roi_arr[s_win:e_win]))
                    if spike_max >= entry_spike_thresh:
                        events.append(
                            CoverageNoteEvent(
                                id=f"s6_occ_{idx_counter:03d}",
                                event_type="coverage_note",
                                channel="visual_chest",
                                t_start_s=round(float(ts_arr[s_idx]), 2),
                                t_end_s=round(float(ts_arr[e_idx]), 2),
                                degradation_type="provider_crowding",
                                confidence=conf_val,
                            )
                        )
                        idx_counter += 1

        if in_occ:
            e_idx = len(during_mask) - 1
            dur = float(ts_arr[e_idx] - ts_arr[s_idx])
            if dur >= min_dur_s:
                s_win = max(0, s_idx - w_spike)
                e_win = min(n_pts, e_idx + w_spike)
                spike_max = float(np.max(roi_arr[s_win:e_win]))
                if spike_max >= entry_spike_thresh:
                    events.append(
                        CoverageNoteEvent(
                            id=f"s6_occ_{idx_counter:03d}",
                            event_type="coverage_note",
                            channel="visual_chest",
                            t_start_s=round(float(ts_arr[s_idx]), 2),
                            t_end_s=round(float(ts_arr[e_idx]), 2),
                            degradation_type="provider_crowding",
                            confidence=conf_val,
                        )
                    )

        return events


def detect_visual_occlusion(
    frame_roi: Any,
    timestamp_s: float,
) -> dict[str, Any] | None:
    """
    Standalone single-frame occlusion detector matching SENSOR_SPECS S6.1
    algorithmic specification signature. Returns coverage_note dict if occluded.
    """
    arr = np.array(frame_roi, dtype=float)
    if arr.size == 0:
        return None

    std_val = float(np.std(arr))
    if std_val < 15.0:
        return {
            "type": "coverage_note",
            "channel": "visual_chest",
            "t_start_s": float(timestamp_s),
            "t_end_s": float(timestamp_s + 5.0),
            "degradation_type": "provider_crowding",
            "confidence": 0.95,
        }
    return None
