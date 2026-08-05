"""
sensors/ccf_report.py — Deterministic CCF (Chest Compression Fraction) Report Generator (S04).

Synthesizes S1 compression motion, S3 defibrillation shocks, and S5 clock anchor
synchronization into a clinical CCF quality report without requiring any LLM calls.
Sensors are 100% DETERMINISTIC: same input, same output, bit-identical.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np

from sensors.s1_s6_motion import S1ChestMotionDetector, CompressionMotionEvent
from sensors.s3_defib import S3DefibDetector, DefibEvent
from sensors.s5_timecode import (
    S5ClockAnchor,
    ClockAnchor,
    read_video_timecode_samples,
)


@dataclass(frozen=True)
class CCFShockDetail:
    """Detailed peri-shock pause metrics for a confirmed defibrillation shock."""

    id: str
    timestamp_s: float
    iso_time: str | None
    pre_shock_pause_s: float | None
    post_shock_pause_s: float | None
    cci_id: str | None
    peak_rms_ratio: float
    tone_slope_hz_s: float


@dataclass(frozen=True)
class CCFReport:
    """
    Structured clinical CCF Report generated deterministically from S1, S3, and S5.
    """

    case_id: str
    video_path: str
    t0_iso: str | None
    t0_source: str
    total_case_duration_s: float
    total_cpr_duration_s: float
    total_cci_duration_s: float
    cpr_active_duration_s: float
    cpr_active_fraction: float
    ccf: float
    ccf_percent: float
    ccf_by_2min_epoch: list[float]
    n_cci_over_10s: int
    longest_cci_s: float
    median_cci_s: float
    shocks: list[CCFShockDetail]
    cci_intervals: list[dict[str, Any]]
    compression_intervals: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        """Convert report to JSON-serializable dictionary."""
        return {
            "case_id": self.case_id,
            "video_path": self.video_path,
            "t0_iso": self.t0_iso,
            "t0_source": self.t0_source,
            "total_case_duration_s": round(self.total_case_duration_s, 2),
            "total_cpr_duration_s": round(self.total_cpr_duration_s, 2),
            "total_cci_duration_s": round(self.total_cci_duration_s, 2),
            "cpr_active_duration_s": round(self.cpr_active_duration_s, 2),
            "cpr_active_fraction": round(self.cpr_active_fraction, 4),
            "ccf": round(self.ccf, 4),
            "ccf_percent": round(self.ccf_percent, 2),
            "ccf_by_2min_epoch": [round(val, 4) for val in self.ccf_by_2min_epoch],
            "n_cci_over_10s": self.n_cci_over_10s,
            "longest_cci_s": round(self.longest_cci_s, 2),
            "median_cci_s": round(self.median_cci_s, 2),
            "shocks": [asdict(s) for s in self.shocks],
            "cci_intervals": self.cci_intervals,
            "compression_intervals": self.compression_intervals,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert report to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


class CCFReportGenerator:
    """
    Generator that executes Sensor S1, S3, and S5 to build a CCF quality report.
    """

    def __init__(
        self,
        profile_name: str = "default",
        s1_detector: S1ChestMotionDetector | None = None,
        s3_detector: S3DefibDetector | None = None,
    ) -> None:
        self.profile_name = profile_name
        self.s1_detector = s1_detector or S1ChestMotionDetector(profile_name)
        self.s3_detector = s3_detector or S3DefibDetector(profile_name)

    def generate_report(
        self,
        video_path: str | Path,
        case_id: str = "simvideo2",
        candidate_shock_times_s: Sequence[float] | None = (
            167.94,
            385.07,
            621.34,
            742.21,
        ),
    ) -> CCFReport:
        """
        Generates deterministic CCF report from clinical resuscitation video.
        """
        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"Video file not found: {path}")

        # 1. Determine video duration
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video file: {path}")
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        cap.release()
        total_dur = float(n_frames / fps) if fps > 0 and n_frames > 0 else 0.0

        # 2. Run Sensor S1 (CPR compression intervals and CCI pause intervals)
        events = self.s1_detector.detect_from_video(path)
        if total_dur == 0.0 and events:
            total_dur = max(float(e.t_end_s) for e in events)
        ccis = self.s1_detector.detect_cci_intervals(events, total_duration_s=total_dur)

        # 3. Run Sensor S5 (Clock Anchor synchronization)
        t0_iso: str | None = None
        t0_source = "none"
        try:
            samples = read_video_timecode_samples(
                str(path), sample_times_s=(10.0, 300.0, 600.0)
            )
            if samples:
                anchor = S5ClockAnchor.derive_t0(
                    {"burned_in": samples}, max_drift_tol_s=2.0
                )
                if anchor.source != "none" and anchor.t0_iso:
                    t0_iso = anchor.t0_iso
                    t0_source = anchor.source
        except Exception:
            # If S5 clock anchor OCR fails or drift occurs, fall back to unanchored relative time
            t0_iso = None
            t0_source = "none"

        # 4. Run Sensor S3 (Defibrillation Shocks & Adjudication)
        shocks_detail: list[CCFShockDetail] = []
        if candidate_shock_times_s is not None:
            for idx, t_cand in enumerate(candidate_shock_times_s):
                verdict = self.s3_detector.adjudicate(path, t_cand, window_s=30.0)
                if verdict.confirmed and verdict.event is not None:
                    ev = verdict.event
                    # Find enclosing or nearest preceding/succeeding CCI
                    enclosing_cci: dict[str, Any] | None = None
                    for cci in ccis:
                        if (
                            float(cci["t_start_s"])
                            <= ev.timestamp_s
                            <= float(cci["t_end_s"])
                        ):
                            enclosing_cci = cci
                            break

                    pre_pause: float | None = None
                    post_pause: float | None = None
                    cci_id: str | None = None
                    if enclosing_cci is not None:
                        cci_id = str(enclosing_cci.get("id", ""))
                        pre_pause = round(
                            ev.timestamp_s - float(enclosing_cci["t_start_s"]), 2
                        )
                        post_pause = round(
                            float(enclosing_cci["t_end_s"]) - ev.timestamp_s, 2
                        )

                    iso_val: str | None = None
                    if t0_iso is not None:
                        # Simple formatted ISO reference string
                        iso_val = f"{t0_iso} + {ev.timestamp_s:.2f}s"

                    shocks_detail.append(
                        CCFShockDetail(
                            id=f"shock_{idx + 1}",
                            timestamp_s=round(ev.timestamp_s, 2),
                            iso_time=iso_val,
                            pre_shock_pause_s=pre_pause,
                            post_shock_pause_s=post_pause,
                            cci_id=cci_id,
                            peak_rms_ratio=round(ev.transient_ratio, 2),
                            tone_slope_hz_s=round(ev.slope_hz_per_s, 2),
                        )
                    )
        else:
            # Standalone scan if no candidate timestamps provided
            s3_events = self.s3_detector.detect_events(path)
            for idx, ev in enumerate(
                e for e in s3_events if e.event_type == "defibrillation_shock"
            ):
                enclosing_cci = None
                for cci in ccis:
                    if (
                        float(cci["t_start_s"])
                        <= ev.timestamp_s
                        <= float(cci["t_end_s"])
                    ):
                        enclosing_cci = cci
                        break
                pre_pause = None
                post_pause = None
                cci_id = None
                if enclosing_cci is not None:
                    cci_id = str(enclosing_cci.get("id", ""))
                    pre_pause = round(
                        ev.timestamp_s - float(enclosing_cci["t_start_s"]), 2
                    )
                    post_pause = round(
                        float(enclosing_cci["t_end_s"]) - ev.timestamp_s, 2
                    )
                shocks_detail.append(
                    CCFShockDetail(
                        id=f"shock_{idx + 1}",
                        timestamp_s=round(ev.timestamp_s, 2),
                        iso_time=f"{t0_iso} + {ev.timestamp_s:.2f}s"
                        if t0_iso
                        else None,
                        pre_shock_pause_s=pre_pause,
                        post_shock_pause_s=post_pause,
                        cci_id=cci_id,
                        peak_rms_ratio=round(ev.transient_ratio, 2),
                        tone_slope_hz_s=round(ev.slope_hz_per_s, 2),
                    )
                )

        # 5. Compute CCF metrics
        total_cci_dur = sum(float(c.get("duration_s", 0.0)) for c in ccis)
        total_cpr_dur = max(0.0, total_dur - total_cci_dur)
        ccf_val = (total_cpr_dur / total_dur) if total_dur > 0 else 0.0
        ccf_pct = ccf_val * 100.0

        # Compute CCF by 2-minute epoch (120-second non-overlapping windows)
        epoch_win = 120.0
        n_epochs = int(total_dur // epoch_win)
        ccf_by_epoch: list[float] = []
        for i in range(n_epochs):
            w_start = i * epoch_win
            w_end = (i + 1) * epoch_win
            # Sum overlap of CCIs in this window
            cci_overlap = 0.0
            for c in ccis:
                cs = float(c["t_start_s"])
                ce = float(c["t_end_s"])
                ov_start = max(w_start, cs)
                ov_end = min(w_end, ce)
                if ov_end > ov_start:
                    cci_overlap += ov_end - ov_start
            epoch_cpr = max(0.0, epoch_win - cci_overlap)
            ccf_by_epoch.append(round(epoch_cpr / epoch_win, 4))

        n_over_10s = sum(1 for c in ccis if float(c.get("duration_s", 0.0)) > 10.0)
        cci_durs = [float(c.get("duration_s", 0.0)) for c in ccis]
        longest_cci = max(cci_durs) if cci_durs else 0.0
        median_cci = float(statistics.median(cci_durs)) if cci_durs else 0.0

        comp_dicts = [
            {
                "id": ev.id,
                "type": ev.event_type,
                "t_start_s": round(ev.t_start_s, 2),
                "t_end_s": round(ev.t_end_s, 2),
                "duration_s": round(ev.t_end_s - ev.t_start_s, 2),
                "cadence_cpm": ev.cadence_cpm,
                "confidence": ev.confidence,
            }
            for ev in events
        ]

        cpr_active_dur = sum(float(ev.t_end_s - ev.t_start_s) for ev in events)
        cpr_active_frac = (cpr_active_dur / total_dur) if total_dur > 0 else 0.0

        return CCFReport(
            case_id=case_id,
            video_path=str(path),
            t0_iso=t0_iso,
            t0_source=t0_source,
            total_case_duration_s=round(total_dur, 2),
            total_cpr_duration_s=round(total_cpr_dur, 2),
            total_cci_duration_s=round(total_cci_dur, 2),
            cpr_active_duration_s=round(cpr_active_dur, 2),
            cpr_active_fraction=round(cpr_active_frac, 4),
            ccf=round(ccf_val, 4),
            ccf_percent=round(ccf_pct, 2),
            ccf_by_2min_epoch=ccf_by_epoch,
            n_cci_over_10s=n_over_10s,
            longest_cci_s=round(longest_cci, 2),
            median_cci_s=round(median_cci, 2),
            shocks=shocks_detail,
            cci_intervals=ccis,
            compression_intervals=comp_dicts,
        )


def generate_ccf_report(
    video_path: str | Path,
    case_id: str = "simvideo2",
    profile_name: str | None = None,
    candidate_shock_times_s: Sequence[float] | None = (
        167.94,
        385.07,
        621.34,
        742.21,
    ),
) -> CCFReport:
    """Convenience wrapper for generating a CCFReport."""
    if profile_name is None:
        profile_name = "simvideo2" if case_id == "simvideo2" else "default"
    generator = CCFReportGenerator(profile_name=profile_name)
    return generator.generate_report(
        video_path=video_path,
        case_id=case_id,
        candidate_shock_times_s=candidate_shock_times_s,
    )
