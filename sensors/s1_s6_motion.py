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
from scipy import signal  # type: ignore[import-untyped]
from codegen.yamlio import StrictLoader


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

    def detect_from_vy_signal(
        self,
        vy_signal: np.ndarray | Sequence[float],
        fps: float = 30.0,
    ) -> list[CompressionMotionEvent]:
        """
        Detects CPR compression intervals from vertical velocity signal vy(t).
        """
        vy_arr = np.array(vy_signal, dtype=float)
        n_frames = len(vy_arr)
        if n_frames < 4 or fps <= 0:
            return []

        min_hz = float(self.s1_config.get("vy_bandpass_min_hz", 1.3))
        max_hz = float(self.s1_config.get("vy_bandpass_max_hz", 3.0))
        threshold_ratio = float(
            self.s1_config.get("energy_threshold_ratio", 0.05)
        )
        min_active_s = float(self.s1_config.get("min_active_duration_s", 2.0))
        conf_val = float(self.s1_config.get("confidence", 0.85))

        nyq = fps / 2.0
        low = max(0.01, min(0.99, min_hz / nyq))
        high = max(low + 0.01, min(0.99, max_hz / nyq))

        b, a = signal.butter(2, [low, high], btype="band")
        filtered = signal.filtfilt(b, a, vy_arr)

        win = max(1, int(fps * 0.1))
        kernel = np.ones(win, dtype=float) / float(win)
        energy = np.convolve(filtered**2, kernel, mode="same")

        max_energy = float(np.max(energy))
        if max_energy <= 1e-12:
            return []

        threshold = threshold_ratio * max_energy
        active_mask = energy > threshold

        gap_merge_s = float(self.s1_config.get("gap_merge_duration_s", 0.5))
        gap_merge_frames = int(gap_merge_s * fps)
        last_active = -100000
        for i in range(n_frames):
            if active_mask[i]:
                if 0 < (i - last_active) <= gap_merge_frames:
                    active_mask[last_active:i] = True
                last_active = i

        events: list[CompressionMotionEvent] = []
        in_active = False
        s_idx = 0
        idx_counter = 1
        t_axis = np.arange(n_frames) / float(fps)

        for i, is_act in enumerate(active_mask):
            if is_act and not in_active:
                in_active = True
                s_idx = i
            elif not is_act and in_active:
                in_active = False
                e_idx = i - 1
                dur = float(t_axis[e_idx] - t_axis[s_idx])
                if dur >= min_active_s:
                    seg_filtered = filtered[s_idx : e_idx + 1]
                    cadence = self._estimate_cadence_cpm(seg_filtered, fps)
                    events.append(
                        CompressionMotionEvent(
                            id=f"s1_{idx_counter}",
                            event_type="compression_motion",
                            t_start_s=float(t_axis[s_idx]),
                            t_end_s=float(t_axis[e_idx]),
                            cadence_cpm=cadence,
                            confidence=conf_val,
                        )
                    )
                    idx_counter += 1

        if in_active:
            e_idx = n_frames - 1
            dur = float(t_axis[e_idx] - t_axis[s_idx])
            if dur >= min_active_s:
                seg_filtered = filtered[s_idx : e_idx + 1]
                cadence = self._estimate_cadence_cpm(seg_filtered, fps)
                events.append(
                    CompressionMotionEvent(
                        id=f"s1_{idx_counter}",
                        event_type="compression_motion",
                        t_start_s=float(t_axis[s_idx]),
                        t_end_s=float(t_axis[e_idx]),
                        cadence_cpm=cadence,
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

    def detect_cci_intervals(
        self,
        motion_events: Sequence[CompressionMotionEvent] | str | Path,
        total_duration_s: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Emits Chest Compression Interruption (CCI) pause intervals
        with confidence scores between active compression periods.
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

        min_pause_s = float(self.s1_config.get("min_pause_duration_s", 3.0))
        conf_val = float(self.s1_config.get("confidence", 0.85))
        ccis: list[dict[str, Any]] = []
        idx = 1

        sorted_events = sorted(motion_events, key=lambda e: e.t_start_s)
        if not sorted_events:
            if total_duration_s >= min_pause_s:
                ccis.append(
                    {
                        "id": f"cci_{idx}",
                        "type": "compression_interruption",
                        "t_start_s": 0.0,
                        "t_end_s": float(total_duration_s),
                        "duration_s": float(total_duration_s),
                        "confidence": conf_val,
                    }
                )
            return ccis

        first_t = float(sorted_events[0].t_start_s)
        if first_t >= min_pause_s:
            ccis.append(
                {
                    "id": f"cci_{idx}",
                    "type": "compression_interruption",
                    "t_start_s": 0.0,
                    "t_end_s": first_t,
                    "duration_s": first_t,
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
                        "t_start_s": pause_start,
                        "t_end_s": pause_end,
                        "duration_s": dur,
                        "confidence": conf_val,
                    }
                )
                idx += 1

        last_t = float(sorted_events[-1].t_end_s)
        if total_duration_s - last_t >= min_pause_s:
            ccis.append(
                {
                    "id": f"cci_{idx}",
                    "type": "compression_interruption",
                    "t_start_s": last_t,
                    "t_end_s": float(total_duration_s),
                    "duration_s": float(total_duration_s - last_t),
                    "confidence": conf_val,
                }
            )

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

        vy_signal: list[float] = []
        ret, prev_frame = cap.read()
        if not ret or prev_frame is None:
            cap.release()
            return []

        prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
        frame_count = 1
        max_frames = (
            int(max_duration_s * fps) if max_duration_s is not None else None
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
