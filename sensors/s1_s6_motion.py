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


@dataclass(frozen=True)
class CoverageNoteEvent:
    """Represents a visual occlusion or coverage degradation interval (Sensor S6)."""

    id: str
    event_type: str  # const "coverage_note"
    channel: str  # enum "visual_chest", "monitor_ocr", "audio_room"
    t_start_s: float
    t_end_s: float
    degradation_type: str  # e.g. "provider_crowding", "visual_occlusion"
    confidence: float


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

    def detect_from_vy_signal(
        self,
        vy_signal: np.ndarray | Sequence[float],
        fps: float = 30.0,
    ) -> list[CompressionMotionEvent]:
        """
        Detects CPR compression intervals from vertical velocity signal vy(t)
        using a Two-Stage architecture:
          Stage 1 (Window Gate): Scale-free frequency-domain discriminator on 60s windows
          Stage 2 (Continuous Segmentation): Continuous rolling RMS envelope thresholding
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
            if len(w_raw) / fps < 4.0:
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
                self.last_coverage_notes.append(
                    {
                        "type": "coverage_note",
                        "channel": "visual_chest",
                        "t_start_s": round(unm_start / fps, 2),
                        "t_end_s": round(len(cpr_window_mask) / fps, 2),
                        "duration_s": round(unm_dur, 2),
                        "note": "unmeasured_debrief_no_periodic_motion",
                    }
                )

        # --- Stage 2: Continuous Rolling RMS Segmentation ---
        nyq = fps / 2.0
        low = max(0.01, min(0.99, min_hz / nyq))
        high = max(low + 0.01, min(0.99, max_hz / nyq))
        b, a = signal.butter(2, [low, high], btype="band")
        filtered = signal.filtfilt(b, a, vy_arr_clean)

        win = max(1, int(fps * 0.1))
        kernel = np.ones(win, dtype=float) / float(win)
        energy = np.convolve(filtered**2, kernel, mode="same")

        valid_energy = energy[cpr_window_mask & (~bump_mask)]
        if len(valid_energy) == 0:
            raise NoPeriodicMotion("No valid non-bump frames in CPR window")

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

        raw_active = (energy > threshold) & cpr_window_mask & (~bump_mask)

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
                    cad = self._estimate_cadence_cpm(sub_sig, fps)
                    events.append(
                        CompressionMotionEvent(
                            id=f"s1_{idx_counter}",
                            event_type="compression_motion",
                            t_start_s=round(s_idx / fps, 2),
                            t_end_s=round(i / fps, 2),
                            cadence_cpm=cad,
                            confidence=conf_val,
                        )
                    )
                    idx_counter += 1

        if in_act:
            dur = (len(active_mask) - s_idx) / fps
            if dur >= min_active_s:
                sub_sig = filtered[s_idx:]
                cad = self._estimate_cadence_cpm(sub_sig, fps)
                events.append(
                    CompressionMotionEvent(
                        id=f"s1_{idx_counter}",
                        event_type="compression_motion",
                        t_start_s=round(s_idx / fps, 2),
                        t_end_s=round(len(active_mask) / fps, 2),
                        cadence_cpm=cad,
                        confidence=conf_val,
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
    ) -> dict[str, Any]:
        """
        Computes Chest Compression Fraction (CCF) per Q-012:
        first compression start to last compression end.
        """
        sorted_events = sorted(motion_events, key=lambda e: e.t_start_s)
        if not sorted_events:
            return {
                "ccf": 0.0,
                "t_first_s": 0.0,
                "t_last_s": 0.0,
                "denominator_s": 0.0,
                "cpr_duration_s": 0.0,
            }
        t_first = float(sorted_events[0].t_start_s)
        t_last = float(sorted_events[-1].t_end_s)
        denominator = max(t_last - t_first, 1e-6)
        cpr_duration = sum(float(e.t_end_s - e.t_start_s) for e in sorted_events)
        ccf = round(cpr_duration / denominator, 3)
        return {
            "ccf": ccf,
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

        first_t = float(sorted_events[0].t_start_s)
        if first_t >= min_pause_s:
            ccis.append(
                {
                    "id": f"cci_{idx}",
                    "type": "compression_interruption",
                    "t_start_s": 0.0,
                    "t_end_s": round(first_t, 2),
                    "duration_s": round(first_t, 2),
                    "confidence": conf_val,
                }
            )
            idx += 1

        for i in range(len(sorted_events) - 1):
            pause_start = float(sorted_events[i].t_end_s)
            pause_end = float(sorted_events[i + 1].t_start_s)
            dur = pause_end - pause_start
            if dur >= min_pause_s:
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
        chest ROI between timestamps t0 and t1.
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

        grid_y, grid_x = np.mgrid[
            ry : ry + rh : 40, rx : rx + rw : 40
        ].astype(np.float32)
        prev_pts = np.vstack((grid_x.flatten(), grid_y.flatten())).T.reshape(
            -1, 1, 2
        )

        start_frame = int(t0 * fps)
        if start_frame > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        vy_signal: list[float] = []
        ret, prev_frame = cap.read()
        if not ret or prev_frame is None:
            cap.release()
            return np.array([], dtype=float)

        prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
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
            next_pts, status, _ = cv2.calcOpticalFlowPyrLK(
                prev_gray, gray, prev_pts, None  # type: ignore[call-overload]
            )
            good_old = prev_pts[status == 1]
            good_new = next_pts[status == 1]
            if len(good_new) > 0 and len(good_old) > 0:
                vy_val = float(np.mean(good_new[:, 1] - good_old[:, 1]))
                vy_signal.append(vy_val)
            else:
                vy_signal.append(0.0)
            prev_gray = gray
            frame_count += 1

        cap.release()
        return np.array(vy_signal, dtype=float)

    def detect_from_video(
        self,
        video_path: str | Path,
        max_duration_s: float | None = None,
    ) -> list[CompressionMotionEvent]:
        """
        Executes S1 motion detection on a video recording.
        Accepts max_duration_s for rapid unit test verification.
        """
        path = Path(video_path)
        cap = cv2.VideoCapture(str(path))
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        cap.release()
        vy_signal = self.extract_vy_signal(
            video_path, t0=0.0, t1=max_duration_s
        )
        return self.detect_from_vy_signal(vy_signal, fps=fps)


class S6CoverageDetector:
    """
    Sensor S6: Detects visual occlusions and provider crowding degradation
    over the calibrated chest ROI.
    """

    def __init__(self, profile_name: str = "default") -> None:
        self.profile_name = profile_name
        self.profile = load_roi_config(profile_name)
        self.s6_config = dict(self.profile.get("s6_coverage", {}))

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
        Computes ROI pixel intensity variance across a video file to detect
        provider crowding and visual occlusions.
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

        std_signal: list[float] = []
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
            std_val = float(np.std(roi_gray))
            std_signal.append(std_val)
            timestamps_s.append(frame_idx / fps)
            frame_idx += 1

        cap.release()
        return self.detect_occlusion_from_metrics(std_signal, timestamps_s)


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
