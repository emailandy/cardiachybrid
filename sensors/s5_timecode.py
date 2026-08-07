"""
Sensor S5: Deterministic Video Clock Anchor Synchronization (S01).

Derives initial zero-time T0 from clinical video feeds using vertical projection profile
segmentation and dense monotonic verification. Raises `ClockDrift` when timecode samples across
a video disagree by more than tolerance. Enforces an explicit, logged fallback chain:
`burned_in` -> `monitor_clock` -> `manual` -> `none`. Never silently falls through to the
next source.
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np

from codegen.yamlio import load_yaml

logger = logging.getLogger(__name__)


class ClockDrift(Exception):
    """Raised when timecode verification detects clock drift or non-linear splice jumps exceeding tolerance."""


@dataclass(frozen=True)
class ClockAnchor:
    """Immutable clock anchor result for a clinical video feed."""

    t0_iso: str
    source: str  # "burned_in" | "monitor_clock" | "manual" | "none"
    confidence: float
    samples: list[dict[str, Any]]
    max_drift_s: float
    fallback_log: list[str]


def _get_timecode_templates(templates_dir: str | None = None) -> dict[str, dict[str, Any]]:
    """Loads clean character template PNGs from disk for OpenCV template matching."""
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

    # Note: P.png is omitted per P2/F-033 until genuine clinical PM footage is available.
    res: dict[str, dict[str, Any]] = {
        "digits": digits,
        "slash": {"/": slash_tpl},
        "colon": {":": colon_tpl},
        "dot": {".": dot_tpl},
        "A": {"A": A_tpl},
        "M": {"M": M_tpl},
    }
    return res


def read_timecode(
    frame: Any,
    min_confidence: float = 0.60,
    min_margin: float = 0.0070,
    roi_config_path: str | None = None,
    templates_dir: str | None = None,
) -> str | None:
    """Reads burned-in timecode overlay from a video frame using vertical projection segmentation.

    Automatically handles variable-width dates (MM/D/YYYY vs MM/DD/YYYY) and rigid horizontal
    translations across rooms. Verifies background margins on character cell edges and enforces
    minimum-margin thresholds on multi-candidate matches.
    Returns None if any character column scores below min_confidence, violates margin, or on PM footage.
    """
    if frame is None or getattr(frame, "size", 0) == 0:
        return None

    if roi_config_path is None:
        roi_config_path = os.path.join(
            os.path.dirname(__file__), "calibration", "roi_config.yaml"
        )

    base_x = 80
    base_y = 120
    base_h = 24
    if os.path.exists(roi_config_path):
        cfg = load_yaml(roi_config_path)
        tc_cfg = cfg.get("timecode_roi", {})
        base_x = tc_cfg.get("x", 80)
        base_y = tc_cfg.get("y", 120)
        base_h = tc_cfg.get("height", 24)
        if min_confidence is None:
            min_confidence = float(tc_cfg.get("min_confidence", 0.60))
        if min_margin is None:
            min_margin = float(tc_cfg.get("min_margin", 0.0070))

    if min_confidence is None:
        min_confidence = 0.60
    if min_margin is None:
        min_margin = 0.0070

    # Search horizontal band: y=120..144, x=60..380 (covers Room 1 x~80 and Room 2 x~178)
    y0, y1 = max(0, base_y), min(frame.shape[0], base_y + base_h)
    x0, x1 = max(0, base_x - 30), min(frame.shape[1], base_x + 300)

    band = frame[y0:y1, x0:x1]
    if band.size == 0:
        return None
    gray_band = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY) if len(band.shape) == 3 else band
    _, bin_band = cv2.threshold(gray_band, 190, 255, cv2.THRESH_BINARY)

    # Vertical projection profile on active character rows
    v_proj = np.sum(bin_band[4:20, :] > 0, axis=0)
    segs: list[tuple[int, int]] = []
    in_s = False
    s_start = 0
    for i, val in enumerate(v_proj):
        if val > 0 and not in_s:
            in_s = True
            s_start = i
        elif val == 0 and in_s:
            in_s = False
            segs.append((s_start, i))
    if in_s:
        segs.append((s_start, len(v_proj)))

    if len(segs) < 22:
        return None

    tpl_dict = _get_timecode_templates(templates_dir)
    slash_tpl = tpl_dict["slash"]["/"]

    best_decoded: str | None = None
    best_score: float = -1.0

    for seq_len in [23, 24]:
        for start_idx in range(len(segs) - seq_len + 1):
            sub_segs = segs[start_idx : start_idx + seq_len]
            span = sub_segs[-1][1] - sub_segs[0][0]
            if not (150 <= span <= 190):
                continue

            # Locate date slashes in leading segments
            s_candidates: list[tuple[int, float]] = []
            for idx, (cs, ce) in enumerate(sub_segs[:6]):
                pad_s = max(0, cs - 1)
                pad_e = min(gray_band.shape[1], ce + 1)
                crop = gray_band[:, pad_s:pad_e]
                if crop.shape[0] >= slash_tpl.shape[0] and crop.shape[1] >= slash_tpl.shape[1]:
                    res = cv2.matchTemplate(crop, slash_tpl, cv2.TM_CCOEFF_NORMED)
                    s_candidates.append((idx, float(np.max(res))))

            s_candidates.sort(key=lambda x: x[1], reverse=True)
            if len(s_candidates) < 2 or s_candidates[1][1] < 0.80:
                continue

            slash_indices = sorted([s_candidates[0][0], s_candidates[1][0]])
            s1_idx, s2_idx = slash_indices[0], slash_indices[1]

            # Construct field layout
            layout: list[tuple[str, str]] = []
            for i in range(0, s1_idx): layout.append(("d", "digits"))
            layout.append(("/", "slash"))
            for i in range(s1_idx + 1, s2_idx): layout.append(("d", "digits"))
            layout.append(("/", "slash"))
            for i in range(s2_idx + 1, s2_idx + 5): layout.append(("d", "digits"))
            layout.append(("d", "digits"))
            layout.append(("d", "digits"))
            layout.append((":", "colon"))
            layout.append(("d", "digits"))
            layout.append(("d", "digits"))
            layout.append((":", "colon"))
            layout.append(("d", "digits"))
            layout.append(("d", "digits"))
            layout.append((".", "dot"))
            layout.append(("d", "digits"))
            layout.append(("d", "digits"))
            layout.append(("d", "digits"))
            layout.append(("A", "A"))
            layout.append(("M", "M"))

            if len(layout) != len(sub_segs):
                continue

            chars: list[str] = []
            scores: list[float] = []
            failed = False

            for char_pos, ((sym, ctype), (cs, ce)) in enumerate(zip(layout, sub_segs)):
                # Verify background valley margins on both edges
                if cs > 0 and v_proj[cs - 1] > 0:
                    failed = True
                    break
                if ce < len(v_proj) and v_proj[ce] > 0:
                    failed = True
                    break

                pad_s = max(0, cs - 1)
                pad_e = min(gray_band.shape[1], ce + 1)
                crop = gray_band[:, pad_s:pad_e]
                candidates = tpl_dict[ctype]

                cand_scores: list[tuple[str, float]] = []
                for k, tpl in candidates.items():
                    if crop.shape[0] < tpl.shape[0] or crop.shape[1] < tpl.shape[1]:
                        continue
                    res = cv2.matchTemplate(crop, tpl, cv2.TM_CCOEFF_NORMED)
                    val = float(np.max(res))
                    cand_scores.append((k, val))

                if not cand_scores:
                    logger.warning("S5 OCR match failed at position %d (%s): no matching templates fit crop %s", char_pos, ctype, crop.shape)
                    failed = True
                    break

                cand_scores.sort(key=lambda x: x[1], reverse=True)
                best_c, best_s = cand_scores[0]

                # Check absolute confidence floor
                if best_s < min_confidence:
                    logger.warning(
                        "S5 OCR match failed at position %d (%s): best_score=%.4f (char %r) < min_confidence=%.4f",
                        char_pos, ctype, best_s, best_c, min_confidence
                    )
                    failed = True
                    break

                # Check multi-candidate minimum margin
                if len(cand_scores) >= 2:
                    second_c, second_s = cand_scores[1]
                    margin = best_s - second_s
                    if margin < min_margin:
                        logger.warning(
                            "S5 OCR margin ambiguous at position %d (%s): top-1 %r (%.4f) vs top-2 %r (%.4f), margin=%.4f < min_margin=%.4f",
                            char_pos, ctype, best_c, best_s, second_c, second_s, margin, min_margin
                        )
                        failed = True
                        break

                chars.append(best_c)
                scores.append(best_s)

            if failed or len(chars) != len(layout):
                continue

            min_s = min(scores) if scores else 0.0
            if min_s >= min_confidence and min_s > best_score:
                date_str = "".join(chars[: s2_idx + 5])
                time_str = "".join(chars[s2_idx + 5 : -2])
                period_str = "".join(chars[-2:])
                
                # Grammar & Domain Range Validation (W2)
                is_valid, err_msg = validate_timecode_fields(date_str, time_str, period_str)
                if not is_valid:
                    logger.warning(
                        "S5 OCR grammar validation failed: %s (decoded %s %s %s)",
                        err_msg, date_str, time_str, period_str
                    )
                    continue

                best_score = min_s
                best_decoded = f"{date_str} {time_str} {period_str}"

    return best_decoded


def validate_timecode_fields(date_str: str, time_str: str, period_str: str) -> tuple[bool, str | None]:
    """Validates calendar and clock domain ranges for 12-hour AM/PM timecode format."""
    try:
        month_s, day_s, year_s = date_str.split("/")
        month, day, year = int(month_s), int(day_s), int(year_s)
        if not (1 <= month <= 12):
            return False, f"month={month} outside [1, 12]"
        if not (1 <= day <= 31):
            return False, f"day={day} outside [1, 31]"
        if not (2000 <= year <= 2099):
            return False, f"year={year} outside [2000, 2099]"

        time_toks = time_str.split(":")
        if len(time_toks) != 3:
            return False, f"time token count={len(time_toks)} != 3"
        hour_s, min_s = time_toks[0], time_toks[1]
        sec_toks = time_toks[2].split(".")
        sec_s = sec_toks[0]
        ms_s = sec_toks[1] if len(sec_toks) > 1 else "0"

        hour, minute, second, ms = int(hour_s), int(min_s), int(sec_s), int(ms_s)
        if not (1 <= hour <= 12):
            return False, f"hour={hour} outside [1, 12] for 12-hour format"
        if not (0 <= minute <= 59):
            return False, f"minute={minute} outside [0, 59]"
        if not (0 <= second <= 59):
            return False, f"second={second} outside [0, 59]"
        if not (0 <= ms <= 999):
            return False, f"millisecond={ms} outside [0, 999]"
        if period_str not in ("AM", "PM"):
            return False, f"period={period_str!r} not in ('AM', 'PM')"
        return True, None
    except Exception as e:
        return False, str(e)


def parse_timecode_to_iso(timecode_str: str) -> str:
    """Parses burned-in timecode string to ISO 8601 UTC timestamp format."""
    try:
        s = timecode_str.strip()
        tokens = s.split()
        if len(tokens) == 3:
            date_part, time_part, period = tokens
        elif len(tokens) == 2:
            date_part, time_part = tokens
            period = "AM"
        else:
            raise ValueError(f"Unexpected token count in timecode: {timecode_str!r}")

        month_str, day_str, year_str = date_part.split("/")
        time_tokens = time_part.split(":")
        hour_str = time_tokens[0]
        min_str = time_tokens[1]
        sec_tokens = time_tokens[2].split(".")
        sec_str = sec_tokens[0]
        ms_str = sec_tokens[1] if len(sec_tokens) > 1 else "0"

        year = int(year_str)
        month = int(month_str)
        day = int(day_str)
        hour = int(hour_str)
        minute = int(min_str)
        second = int(sec_str)
        microsecond = int(ms_str.ljust(6, "0")[:6])

        if period == "PM" and hour < 12:
            hour += 12
        elif period == "AM" and hour == 12:
            hour = 0

        dt = datetime(year, month, day, hour, minute, second, microsecond, tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception as err:
        raise ValueError(f"Could not parse timecode string: {timecode_str!r}") from err


def read_video_timecode_samples(
    video_path: str,
    sample_times_s: Sequence[float] = (10.0, 300.0, 600.0),
    min_confidence: float = 0.60,
    min_margin: float = 0.0070,
    roi_config_path: str | None = None,
    templates_dir: str | None = None,
) -> list[dict[str, Any]]:
    """Samples video frames at specified offsets and extracts OCR timecode strings."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0.0:
        fps = 30.0

    samples: list[dict[str, Any]] = []
    try:
        for t_s in sample_times_s:
            frame_idx = int(float(t_s) * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
            raw_str = read_timecode(
                frame,
                min_confidence=min_confidence,
                min_margin=min_margin,
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
                        "frame": frame_idx,
                    }
                )
    finally:
        cap.release()

    return samples


def synchronize_clock_anchor(
    video_path: str,
    roi_config_path: str | None = None,
    t_start: float | None = None,
    t_end: float | None = None,
    max_drift_tolerance_s: float = 0.50,
    sample_stride_s: float = 30.0,
) -> ClockAnchor:
    """Synchronizes video T0 using dense monotonic verification across recording duration.

    Enforces logged fallback chain: burned_in -> monitor_clock -> manual -> none.
    Raises ClockDrift if timecode timestamps exhibit non-linear jumps or drift > tolerance.
    """
    fallback_log: list[str] = []
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        fallback_log.append(f"Failed to open video container: {video_path}")
        return ClockAnchor(
            t0_iso="1970-01-01T00:00:00+00:00",
            source="none",
            confidence=0.0,
            samples=[],
            max_drift_s=0.0,
            fallback_log=fallback_log,
        )

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0.0:
        fps = 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_s = total_frames / fps if total_frames > 0 else 0.0

    win_start = float(t_start) if t_start is not None else (5.0 if duration_s <= 35.0 else 10.0)
    win_end = float(t_end) if t_end is not None else duration_s

    # 1. Dense monotonic sampling (every sample_stride_s, plus bounds)
    fallback_log.append(f"Attempting dense burned_in timecode verification across {win_start:.1f}s..{win_end:.1f}s window (video duration {duration_s:.1f}s)...")
    
    if (win_end - win_start) <= 35.0:
        sample_times = [float(s) for s in range(int(win_start), int(win_end), 5)]
    else:
        sample_times = [float(s) for s in range(int(win_start), int(win_end), int(sample_stride_s))]

    samples: list[dict[str, Any]] = []
    implied_t0_timestamps: list[float] = []

    for ts in sample_times:
        frame_idx = int(ts * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret or frame is None:
            continue
        raw_tc = read_timecode(frame, roi_config_path=roi_config_path)
        if raw_tc is not None:
            iso_str = parse_timecode_to_iso(raw_tc)
            dt = datetime.fromisoformat(iso_str)
            implied_t0 = dt.timestamp() - ts
            implied_t0_timestamps.append(implied_t0)
            samples.append(
                {
                    "video_time_s": ts,
                    "frame_idx": frame_idx,
                    "raw_string": raw_tc,
                    "wall_clock_iso": iso_str,
                    "implied_t0_timestamp": implied_t0,
                }
            )

    cap.release()

    if len(samples) >= 2:
        # Check monotonicity across consecutive samples
        for i in range(len(samples) - 1):
            s1, s2 = samples[i], samples[i + 1]
            dt_wall = datetime.fromisoformat(s2["wall_clock_iso"]).timestamp() - datetime.fromisoformat(s1["wall_clock_iso"]).timestamp()
            dt_vid = s2["video_time_s"] - s1["video_time_s"]
            step_drift = abs(dt_wall - dt_vid)
            if step_drift > max_drift_tolerance_s:
                msg = (
                    f"Clock discontinuity / splice jump detected: t={s1['video_time_s']:.1f}s -> t={s2['video_time_s']:.1f}s "
                    f"(wall delta {dt_wall:.2f}s vs video delta {dt_vid:.2f}s, drift {step_drift:.2f}s > {max_drift_tolerance_s:.2f}s)."
                )
                fallback_log.append(msg)
                raise ClockDrift(msg)

        max_drift = float(max(implied_t0_timestamps) - min(implied_t0_timestamps))
        if max_drift > max_drift_tolerance_s:
            msg = (
                f"Dense timecode verification failed: maximum clock drift of {max_drift:.3f}s "
                f"exceeds tolerance ({max_drift_tolerance_s:.3f}s) across video {video_path}."
            )
            fallback_log.append(msg)
            raise ClockDrift(msg)

        base_sample = samples[0]
        t0_iso = datetime.fromtimestamp(base_sample["implied_t0_timestamp"], tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        fallback_log.append(f"Burned-in clock synchronized successfully: T0={t0_iso} (drift: {max_drift:.3f}s)")
        return ClockAnchor(
            t0_iso=t0_iso,
            source="burned_in",
            confidence=0.98,
            samples=samples,
            max_drift_s=max_drift,
            fallback_log=fallback_log,
        )

    fallback_log.append(f"Burned-in timecode unavailable (found {len(samples)} valid samples).")
    fallback_log.append("Falling back to monitor_clock (not implemented, skipped).")
    fallback_log.append("Falling back to manual operator entry (none provided).")
    fallback_log.append("Terminal fallback reached: returning unanchored source='none'.")

    return ClockAnchor(
        t0_iso="",
        source="none",
        confidence=0.0,
        samples=samples,
        max_drift_s=0.0,
        fallback_log=fallback_log,
    )


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

            implied_t0s: list[float] = []
            for idx, sample in enumerate(samples):
                v_time = float(sample.get("video_time_s", 0.0))
                wall_iso = str(sample.get("wall_clock_iso", ""))
                epoch = cls._parse_iso_to_epoch(wall_iso)
                implied_t0s.append(epoch - v_time)

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

            sorted_t0s = sorted(implied_t0s)
            mid = len(sorted_t0s) // 2
            median_t0 = sorted_t0s[mid]
            t0_iso = cls._epoch_to_iso(median_t0)

            fallback_log.append(
                f"{source}: Validated {len(samples)} samples with max drift {max_drift:.2f}s (T0={t0_iso})."
            )

            conf = 0.98 if source == "burned_in" else (0.90 if source == "monitor_clock" else 0.85)

            return ClockAnchor(
                t0_iso=t0_iso,
                source=source,
                confidence=conf,
                samples=samples,
                max_drift_s=round(max_drift, 4),
                fallback_log=fallback_log,
            )

        raise RuntimeError("Fallback order did not terminate with 'none'.")
