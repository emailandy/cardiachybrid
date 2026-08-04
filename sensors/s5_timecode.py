"""
Sensor S5: Deterministic Video Clock Anchor Synchronization (S01).
Derives initial zero-time T0 from clinical video feeds using three-point
verification. Raises `ClockDrift` when timecode samples across a video
disagree by more than tolerance. Enforces an explicit, logged fallback chain:
`burned_in` -> `monitor_clock` -> `manual` -> `none`. Never silently falls
through to the next source.
"""

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np

from codegen.yamlio import load_yaml


class ClockDrift(Exception):
    """Raised when three-point timecode verification detects clock drift exceeding tolerance."""


@dataclass(frozen=True)
class ClockAnchor:
    """Immutable clock anchor result for a clinical video feed."""

    t0_iso: str
    source: str  # "burned_in" | "monitor_clock" | "manual" | "none"
    confidence: float
    samples: list[dict[str, Any]]
    max_drift_s: float
    fallback_log: list[str]


_TIMECODE_COLS: Sequence[tuple[str, str, int, int]] = (
    ("d", "digits", 2, 11),
    ("d", "digits", 9, 18),
    ("s", "slash", 16, 24),
    ("d", "digits", 23, 32),
    ("s", "slash", 30, 38),
    ("d", "digits", 36, 45),
    ("d", "digits", 43, 52),
    ("d", "digits", 51, 60),
    ("d", "digits", 59, 68),
    ("d", "digits", 71, 80),
    ("d", "digits", 78, 87),
    ("c", "colon", 86, 94),
    ("d", "digits", 91, 100),
    ("d", "digits", 99, 108),
    ("c", "colon", 106, 114),
    ("d", "digits", 111, 120),
    ("d", "digits", 118, 127),
    ("dot", "dot", 125, 133),
    ("d", "digits", 130, 139),
    ("d", "digits", 138, 147),
    ("d", "digits", 145, 155),
    ("A", "A", 156, 167),
    ("M", "M", 167, 179),
)


def _get_timecode_templates(templates_dir: str | None = None) -> dict[str, dict[str, Any]]:
    """Loads character template PNGs from disk for OpenCV template matching."""
    if templates_dir is None:
        templates_dir = os.path.join(os.path.dirname(__file__), "calibration", "timecode")
    digits: dict[str, Any] = {
        str(d): cv2.imread(os.path.join(templates_dir, f"{d}.png"), cv2.IMREAD_GRAYSCALE)
        for d in range(10)
    }
    slash_tpl: Any = cv2.imread(os.path.join(templates_dir, "slash.png"), cv2.IMREAD_GRAYSCALE)
    colon_tpl: Any = cv2.imread(os.path.join(templates_dir, "colon.png"), cv2.IMREAD_GRAYSCALE)
    dot_tpl: Any = cv2.imread(os.path.join(templates_dir, "dot.png"), cv2.IMREAD_GRAYSCALE)
    A_tpl: Any = cv2.imread(os.path.join(templates_dir, "A.png"), cv2.IMREAD_GRAYSCALE)
    M_tpl: Any = cv2.imread(os.path.join(templates_dir, "M.png"), cv2.IMREAD_GRAYSCALE)
    return {
        "digits": digits,
        "slash": {"/": slash_tpl},
        "colon": {":": colon_tpl},
        "dot": {".": dot_tpl},
        "A": {"A": A_tpl},
        "M": {"M": M_tpl},
    }


def read_timecode(
    frame: Any,
    min_confidence: float = 0.60,
    roi_config_path: str | None = None,
    templates_dir: str | None = None,
) -> str | None:
    """Reads burned-in timecode overlay from a video frame using per-column OpenCV template matching.

    Returns None if any character column scores below min_confidence to prevent partial or guessed strings.
    """
    if roi_config_path is None:
        roi_config_path = os.path.join(
            os.path.dirname(__file__), "calibration", "roi_config.yaml"
        )

    cfg = load_yaml(Path(roi_config_path))
    roi_cfg = cfg.get("timecode_roi", {})
    x: int = int(roi_cfg.get("x", 80))
    y: int = int(roi_cfg.get("y", 120))
    w: int = int(roi_cfg.get("width", 184))
    h: int = int(roi_cfg.get("height", 24))

    sub_img: Any = frame[y : y + h, x : x + w]
    if len(sub_img.shape) == 3:
        roi: Any = cv2.cvtColor(sub_img, cv2.COLOR_BGR2GRAY)
    else:
        roi = sub_img

    tpls = _get_timecode_templates(templates_dir)
    result_str = ""

    for col_idx, (_col_type, cat_name, xs, xe) in enumerate(_TIMECODE_COLS):
        sub_col: Any = roi[:, xs:xe]
        best_char = "?"
        best_score = -1.0
        for char_name, tpl in tpls[cat_name].items():
            if tpl is None:
                return None
            res = cv2.matchTemplate(sub_col, tpl, cv2.TM_CCOEFF_NORMED)
            score = float(np.max(res))
            if score > best_score:
                best_score = score
                best_char = char_name
        if best_score < min_confidence:
            return None
        result_str += best_char
        if col_idx == 8 or col_idx == 20:
            result_str += " "

    return result_str


def parse_timecode_to_iso(timecode_str: str) -> str:
    """Parses a raw OCR timecode string (e.g., '11/7/2023 08:00:57.072 AM') to ISO-8601 UTC string."""
    try:
        dt = datetime.strptime(timecode_str, "%m/%d/%Y %I:%M:%S.%f %p")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except ValueError as err:
        raise ValueError(f"Could not parse timecode string: {timecode_str!r}") from err


def read_video_timecode_samples(
    video_path: str,
    sample_times_s: Sequence[float] = (10.0, 300.0, 600.0),
    min_confidence: float = 0.60,
    roi_config_path: str | None = None,
    templates_dir: str | None = None,
) -> list[dict[str, Any]]:
    """Reads authoritative timecode samples from an MP4 video file at specified timestamps."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video file: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0.0:
        fps = 16.0  # Fallback to known default

    samples: list[dict[str, Any]] = []
    try:
        for t_s in sample_times_s:
            cap.set(cv2.CAP_PROP_POS_MSEC, float(t_s) * 1000.0)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
            raw_str = read_timecode(
                frame,
                min_confidence=min_confidence,
                roi_config_path=roi_config_path,
                templates_dir=templates_dir,
            )
            if raw_str is not None:
                iso_str = parse_timecode_to_iso(raw_str)
                samples.append(
                    {
                        "video_time_s": float(t_s),
                        "wall_clock_iso": iso_str,
                        "raw_string": raw_str,
                        "frame": int(float(t_s) * fps),
                    }
                )
    finally:
        cap.release()

    return samples


class S5ClockAnchor:
    """Deterministic S5 clock anchor synchronization engine."""

    FALLBACK_ORDER: Sequence[str] = ("burned_in", "monitor_clock", "manual", "none")

    @classmethod
    def _parse_iso_to_epoch(cls, iso_str: str) -> float:
        """Parses an ISO-8601 string to UTC epoch seconds."""
        clean_iso = iso_str.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(clean_iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError as err:
            raise ValueError(f"Invalid ISO-8601 timestamp string: {iso_str!r}") from err

    @classmethod
    def _epoch_to_iso(cls, epoch_s: float) -> str:
        """Converts UTC epoch seconds to standard ISO-8601 string without microseconds."""
        dt = datetime.fromtimestamp(epoch_s, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S")

    @classmethod
    def derive_t0(
        cls,
        samples_by_source: dict[str, list[dict[str, Any]]],
        max_drift_tol_s: float = 2.0,
        min_samples: int = 3,
    ) -> ClockAnchor:
        """
        Derives initial T0 by testing candidates in strict FALLBACK_ORDER.
        Logs every step of the fallback chain explicitly.
        Raises ClockDrift if any candidate source with >= min_samples exhibits drift > tol.
        """
        fallback_log: list[str] = []

        for source in cls.FALLBACK_ORDER:
            if source == "none":
                fallback_log.append("none: No reliable clock anchor found across all candidate sources.")
                return ClockAnchor(
                    t0_iso="",
                    source="none",
                    confidence=0.0,
                    samples=[],
                    max_drift_s=0.0,
                    fallback_log=fallback_log,
                )

            samples = samples_by_source.get(source, [])
            if len(samples) < min_samples:
                fallback_log.append(
                    f"{source}: Insufficient samples (n={len(samples)}, required >= {min_samples}); falling back to next source."
                )
                continue

            # Compute implied zero-time T0 for each sample
            implied_t0s: list[float] = []
            for idx, sample in enumerate(samples):
                v_time = float(sample.get("video_time_s", 0.0))
                wall_iso = str(sample.get("wall_clock_iso", ""))
                epoch = cls._parse_iso_to_epoch(wall_iso)
                implied_t0s.append(epoch - v_time)

            # Compute maximum pairwise drift
            max_drift = 0.0
            for i in range(len(implied_t0s)):
                for j in range(i + 1, len(implied_t0s)):
                    drift = abs(implied_t0s[i] - implied_t0s[j])
                    if drift > max_drift:
                        max_drift = drift

            if max_drift > max_drift_tol_s:
                fallback_log.append(
                    f"{source}: FAILED three-point verification (max drift {max_drift:.2f}s > {max_drift_tol_s:.2f}s)."
                )
                raise ClockDrift(
                    f"Clock drift detected in source '{source}': max drift {max_drift:.2f}s exceeds "
                    f"tolerance {max_drift_tol_s:.2f}s across {len(samples)} samples."
                )

            # Validated anchor! Compute median implied T0
            sorted_t0s = sorted(implied_t0s)
            mid = len(sorted_t0s) // 2
            median_t0 = sorted_t0s[mid]
            t0_iso = cls._epoch_to_iso(median_t0)

            fallback_log.append(
                f"{source}: Validated {len(samples)} samples with max drift {max_drift:.2f}s (T0={t0_iso})."
            )

            # Assign confidence based on source tier
            conf = 0.98 if source == "burned_in" else (0.90 if source == "monitor_clock" else 0.85)

            return ClockAnchor(
                t0_iso=t0_iso,
                source=source,
                confidence=conf,
                samples=samples,
                max_drift_s=round(max_drift, 4),
                fallback_log=fallback_log,
            )

        # Unreachable due to 'none' fallback terminal
        raise RuntimeError("Fallback order did not terminate with 'none'.")
