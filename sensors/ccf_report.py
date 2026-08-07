"""
sensors/ccf_report.py — Deterministic CCF (Chest Compression Fraction) Report Generator (Task S10).

Synthesizes Sensor S1 compression motion, Sensor S3 defibrillation shocks, and
Sensor S5 clock anchor synchronization into a clinical CCF quality report
without requiring any LLM calls.

Sensors are 100% DETERMINISTIC: same input, same output, bit-identical.
Case milestones (patient_enters_room_s, death_pronounced_s) and candidate shock
timestamps are operator-supplied parameters rather than ground-truth fixtures (H1, I4).
When death_pronounced_s is absent, CCF is ABSTAINED rather than computed ungated (I6).
"""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np

from sensors.eval.metrics import _match_intervals
from sensors.s1_s6_motion import (
    CompressionMotionEvent,
    S1ChestMotionDetector,
    S6CoverageDetector,
)
from sensors.s3_defib import DefibEvent, S3DefibDetector
from sensors.s5_timecode import (
    ClockAnchor,
    S5ClockAnchor,
    read_video_timecode_samples,
)


@dataclass(frozen=True)
class CCFShockDetail:
    """Detailed peri-shock pause metrics for a defibrillation shock candidate."""

    id: str
    candidate_timestamp_s: float
    candidate_source: str
    detected_timestamp_s: float | None
    iso_time: str | None
    confirmed: bool
    adjudication_status: str
    adjudication_verdict: str
    pre_shock_pause_s: float | None
    post_shock_pause_s: float | None
    shock_inside_cci: bool
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

    # Window boundaries & Provenance (H1, I6, P4)
    patient_enters_room_s: float | None
    patient_enters_room_source: str
    death_pronounced_s: float | None
    death_pronounced_source: str
    interval_window_s: tuple[float, float] | None
    intervals_abstained: bool
    intervals_abstain_reason: str | None
    ccf_window_s: tuple[float, float] | None
    t_first_s: float | None
    t_first_source: str
    ccf_denominator_s: float | None

    # CCF & CPR Motion Metrics (None when CCF is abstained per I6)
    total_cpr_duration_s: float | None
    total_cci_duration_s: float
    cpr_active_duration_s: float | None
    cpr_active_fraction: float | None
    ccf: float | None
    ccf_percent: float | None
    ccf_by_2min_epoch: list[float]
    ccf_abstained: bool
    ccf_abstain_reason: str | None

    # Interval Counts & Stats across Consumers
    n_cci_over_10s: int
    longest_cci_s: float
    median_cci_s: float

    # Events & Intervals
    shocks: list[CCFShockDetail]
    raw_intervals: list[dict[str, Any]]
    ccf_intervals: list[dict[str, Any]]
    redcap_intervals: list[dict[str, Any]]
    reported_intervals: list[dict[str, Any]]
    compression_intervals: list[dict[str, Any]]
    ground_truth: dict[str, Any] | None = None

    @property
    def cci_intervals(self) -> list[dict[str, Any]]:
        """Backwards-compatibility property returning CCF consumer intervals (>=1.0s)."""
        return self.ccf_intervals

    def to_dict(self) -> dict[str, Any]:
        # Unconditional sensor-derived two-measurement gap (N3)
        two_meas_caveat: str | None = None
        motion_non_cpr_dur: float = 0.0
        raw_cci_dur_in_ccf: float = 0.0
        measurement_gap: float = 0.0

        if self.ccf_window_s is not None and self.ccf_denominator_s is not None:
            raw_in_ccf_win = [
                c
                for c in self.raw_intervals
                if float(c["t_start_s"]) < self.ccf_window_s[1]
                and float(c["t_end_s"]) > self.ccf_window_s[0]
            ]
            raw_cci_dur_in_ccf = sum(
                max(
                    0.0,
                    min(self.ccf_window_s[1], float(c["t_end_s"]))
                    - max(self.ccf_window_s[0], float(c["t_start_s"])),
                )
                for c in raw_in_ccf_win
            )
            motion_non_cpr_dur = max(
                0.0, self.ccf_denominator_s - (self.cpr_active_duration_s or 0.0)
            )
            measurement_gap = abs(motion_non_cpr_dur - raw_cci_dur_in_ccf)
            two_meas_caveat = (
                f"Two-Measurement Gap: Non-CPR motion duration derived from compute_ccf ({motion_non_cpr_dur:.2f}s) "
                f"and emitted interval stream pause duration ({raw_cci_dur_in_ccf:.2f}s) differ by exactly {measurement_gap:.2f}s "
                f"over the {self.ccf_denominator_s:.2f}s CCF evaluation window."
            )

        # Derive validation metrics and caveats dynamically from ground truth
        if (
            self.ground_truth is not None
            and self.ccf_window_s is not None
            and self.ccf_denominator_s is not None
        ):
            gt_ccis = self.ground_truth.get("ccis") or self.ground_truth.get(
                "cci_intervals", []
            )
            gt_pause_s = 0.0
            for c in gt_ccis:
                cs = float(c.get("start_s", c.get("t_start_s", 0.0)))
                ce = float(c.get("end_s", c.get("t_end_s", 0.0)))
                ov_start = max(self.ccf_window_s[0], cs)
                ov_end = min(self.ccf_window_s[1], ce)
                if ov_end > ov_start:
                    gt_pause_s += ov_end - ov_start
            gt_cpr_s = max(0.0, self.ccf_denominator_s - gt_pause_s)
            gt_ccf = (
                gt_cpr_s / self.ccf_denominator_s
                if self.ccf_denominator_s > 0
                else 0.0
            )
            ccf_err = abs((self.ccf or 0.0) - gt_ccf)

            # Match reporting intervals (>=5.0s) against ground truth (M1)
            matched_rep = _match_intervals(self.reported_intervals, gt_ccis, tol_s=3.0)
            rep_matched_preds = [p for p, _, _, _ in matched_rep]
            tp_count = len(rep_matched_preds)
            fp_count = len(self.reported_intervals) - tp_count

            # S6 provider crowding breakdown on FP intervals
            s6_fp_count = 0
            s6_events = []
            if self.video_path and Path(self.video_path).exists():
                try:
                    s6_events = S6CoverageDetector(profile_name=getattr(self, "profile_name", "simvideo2")).detect_occlusion_from_video(self.video_path)
                except Exception:
                    s6_events = []

            for c in self.reported_intervals:
                if c not in rep_matched_preds:
                    cs, ce = float(c["t_start_s"]), float(c["t_end_s"])
                    has_s6 = bool(c.get("s6_crowding")) or any(max(cs, o.t_start_s) < min(ce, o.t_end_s) for o in s6_events)
                    if has_s6:
                        s6_fp_count += 1
            unexplained_fp_count = fp_count - s6_fp_count

            # Cancelling error magnitudes in CCF active window (M4)
            matched_ccf = _match_intervals(self.raw_intervals, gt_ccis, tol_s=3.0)
            ccf_matched_preds = [p for p, _, _, _ in matched_ccf]
            fp_pause_dur = sum(
                max(0.0, min(self.ccf_window_s[1], float(c["t_end_s"])) - max(self.ccf_window_s[0], float(c["t_start_s"])))
                for c in self.raw_intervals
                if c not in ccf_matched_preds
                and float(c["t_start_s"]) < self.ccf_window_s[1]
                and float(c["t_end_s"]) > self.ccf_window_s[0]
            )
            matched_gt_indices = set(gt_ccis.index(g) for _, g, _, _ in matched_ccf if g in gt_ccis)
            fn_pause_dur = sum(
                max(0.0, min(self.ccf_window_s[1], float(g.get("end_s", g.get("t_end_s", 0.0)))) - max(self.ccf_window_s[0], float(g.get("start_s", g.get("t_start_s", 0.0)))))
                for idx, g in enumerate(gt_ccis)
                if idx not in matched_gt_indices
                and float(g.get("start_s", g.get("t_start_s", 0.0))) < self.ccf_window_s[1]
                and float(g.get("end_s", g.get("t_end_s", 0.0))) > self.ccf_window_s[0]
            )

            # M3: Label accurately without claiming generic endorsement
            val_status = "COMPARED (against human-adjudicated ground truth for this case, Q-017)"
            val_dict: dict[str, Any] | None = {
                "gt_ccf_active": round(gt_ccf, 4),
                "ccf_error_active": round(ccf_err, 4),
                "non_cpr_motion_duration_s": round(motion_non_cpr_dur, 2),
                "interval_stream_pause_duration_s": round(raw_cci_dur_in_ccf, 2),
                "two_measurement_gap_s": round(measurement_gap, 2),
                "fp_pause_duration_active_s": round(fp_pause_dur, 2),
                "fn_missed_pause_duration_active_s": round(fn_pause_dur, 2),
                "reporting_reported_count": len(self.reported_intervals),
                "reporting_true_positives": tp_count,
                "reporting_false_positives": fp_count,
                "reporting_s6_explained_fps": s6_fp_count,
                "reporting_unexplained_fps": unexplained_fp_count,
            }
            caveats_list = [
                f"Cancelling Errors ({self.ccf_window_s[0]:.2f}-{self.ccf_window_s[1]:.2f}s): Observed CCF error {ccf_err:.2f} (S1 {self.ccf or 0.0:.4f} vs GT {gt_ccf:.4f}) reflects cancelling errors: +{fp_pause_dur:.1f}s of false-positive pause duration accumulated during detection vs -{fn_pause_dur:.1f}s of missed true pause duration.",
                two_meas_caveat or "",
                f"False Positive Rate: Under the >=5.0s reporting threshold, {fp_count} of {len(self.reported_intervals)} reported intervals are false positives under +/-3.0s monotonic tolerance matching ({s6_fp_count} coincide with S6-detected provider crowding; {unexplained_fp_count} unexplained).",
                "Single manikin case (n=1) validation basis. Device and bay calibration required before production (Q-017).",
            ]
        else:
            val_status = "Accuracy not validated for this case (no ground truth supplied)"
            val_dict = None
            caveats_list = []
            if two_meas_caveat:
                caveats_list.append(two_meas_caveat)
            caveats_list.append(
                "Single manikin case (n=1) validation basis. Device and bay calibration required before production (Q-017)."
            )

        return {
            "case_id": self.case_id,
            "video_path": self.video_path,
            "t0_iso": self.t0_iso,
            "t0_source": self.t0_source,
            "total_case_duration_s": round(self.total_case_duration_s, 2),
            "patient_enters_room_s": round(self.patient_enters_room_s, 2)
            if self.patient_enters_room_s is not None
            else None,
            "patient_enters_room_source": self.patient_enters_room_source,
            "death_pronounced_s": round(self.death_pronounced_s, 2)
            if self.death_pronounced_s is not None
            else None,
            "death_pronounced_source": self.death_pronounced_source,
            "interval_window_s": [
                round(self.interval_window_s[0], 2),
                round(self.interval_window_s[1], 2),
            ]
            if self.interval_window_s is not None
            else None,
            "intervals_abstained": self.intervals_abstained,
            "intervals_abstain_reason": self.intervals_abstain_reason,
            "ccf_window_s": [
                round(self.ccf_window_s[0], 2),
                round(self.ccf_window_s[1], 2),
            ]
            if self.ccf_window_s is not None
            else None,
            "t_first_s": round(self.t_first_s, 2)
            if self.t_first_s is not None
            else None,
            "t_first_source": self.t_first_source,
            "ccf_denominator_s": round(self.ccf_denominator_s, 2)
            if self.ccf_denominator_s is not None
            else None,
            "total_cpr_duration_s": round(self.total_cpr_duration_s, 2)
            if self.total_cpr_duration_s is not None
            else None,
            "total_cci_duration_s": round(self.total_cci_duration_s, 2),
            "cpr_active_duration_s": round(self.cpr_active_duration_s, 2)
            if self.cpr_active_duration_s is not None
            else None,
            "cpr_active_fraction": round(self.cpr_active_fraction, 4)
            if self.cpr_active_fraction is not None
            else None,
            "ccf": round(self.ccf, 4) if self.ccf is not None else None,
            "ccf_percent": round(self.ccf_percent, 2)
            if self.ccf_percent is not None
            else None,
            "ccf_by_2min_epoch": [
                round(val, 4) for val in self.ccf_by_2min_epoch
            ],
            "ccf_abstained": self.ccf_abstained,
            "ccf_abstain_reason": self.ccf_abstain_reason,
            "n_cci_over_10s": self.n_cci_over_10s,
            "longest_cci_s": round(self.longest_cci_s, 2),
            "median_cci_s": round(self.median_cci_s, 2),
            "readership_banner": [
                "NOT FOR CLINICAL OR PERFORMANCE ASSESSMENT.",
                "In the single manikin validation case, interval precision was 0.36 and the longest interruption was not detected. Accuracy on this case is unmeasured.",
            ],
            "validation_status": val_status,
            "validation": val_dict,
            "caveats": caveats_list,
            "shocks": [asdict(s) for s in self.shocks],
            "raw_intervals": self.raw_intervals,
            "ccf_intervals": self.ccf_intervals,
            "redcap_intervals": self.redcap_intervals,
            "reported_intervals": self.reported_intervals,
            "compression_intervals": self.compression_intervals,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert report to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def format_text_report(
        self, ground_truth: dict[str, Any] | None = None
    ) -> str:
        """
        Formats human-readable clinical CCF Quality Report with mandatory on-face caveats (H4).
        If ground_truth is provided, computes dynamic validation error metrics (H3).
        If ground_truth is None, explicitly notes accuracy is unvalidated for this case.
        """
        lines: list[str] = []

        # H4: Prominent Clinician Readership Banner (N0)
        lines.append("=" * 80)
        lines.append("NOT FOR CLINICAL OR PERFORMANCE ASSESSMENT.")
        lines.append(
            "In the single manikin validation case, interval precision was 0.36 and the longest"
        )
        lines.append(
            "interruption was not detected. Accuracy on this case is unmeasured."
        )
        lines.append("=" * 80)
        lines.append("")

        # Header Block
        lines.append("--- CASE & WINDOW METADATA ---")
        lines.append(f"Case ID: {self.case_id}")
        lines.append(f"Video Path: {self.video_path}")
        lines.append(f"T0 Clock Anchor: {self.t0_iso} (source: {self.t0_source})")
        if self.interval_window_s is not None:
            lines.append(
                f"Interval Reporting Window: {self.interval_window_s[0]:.2f}s - {self.interval_window_s[1]:.2f}s "
                f"(patient_enters_room_s: {self.patient_enters_room_source}, death_pronounced_s: {self.death_pronounced_source})"
            )
        else:
            lines.append(
                f"Interval Reporting Window: NONE (abstained: {self.intervals_abstain_reason})"
            )
        if self.ccf_window_s is not None and self.ccf_denominator_s is not None:
            lines.append(
                f"CCF Evaluation Window: {self.ccf_window_s[0]:.2f}s - {self.ccf_window_s[1]:.2f}s "
                f"(Denominator: {self.ccf_denominator_s:.2f}s, Q-012 Candidate c)"
            )
        else:
            lines.append(
                "CCF Evaluation Window: NONE (CCF calculation abstained per I6 / F-026)"
            )

        t_first_str = f"{self.t_first_s:.2f}s" if self.t_first_s is not None else "None"
        lines.append(
            f"Milestones Origin: t_first = {t_first_str} is SENSOR-DERIVED ({self.t_first_source}); "
            f"window bounds are OPERATOR-SUPPLIED ({self.patient_enters_room_source} / {self.death_pronounced_source})."
        )
        lines.append(
            f"Note on t_first Anchor (Q-012): t_first = {t_first_str} is the first detected compression bout "
            "accepted by the mode classifier."
        )
        lines.append(
            "Calibration Basis: Thresholds calibrated on n=1 manikin simulation screen-recorded video stack (F-017 / M4). "
            "Performance on real patients is unmeasured."
        )
        lines.append("")

        # Section 1: CCF Metrics (I6: Gated on death_pronounced_s)
        lines.append("--- SECTION 1: CHEST COMPRESSION FRACTION (CCF) ---")
        if self.ccf_abstained:
            lines.append(
                f"Chest Compression Fraction (CCF): ABSTAINED ({self.ccf_abstain_reason})"
            )
        else:
            lines.append(
                f"Chest Compression Fraction (CCF): {self.ccf:.4f} ({self.ccf_percent:.2f}%)"
            )
            lines.append(
                f"Active CPR Motion Duration: {self.cpr_active_duration_s:.2f}s / {self.ccf_denominator_s:.2f}s"
            )
            lines.append(
                f"CCF by 2-Minute Epochs: {[round(v, 4) for v in self.ccf_by_2min_epoch]}"
            )
        lines.append("")

        # Validation Block (H3 / I3: Gated strictly on ground_truth supplied, NEVER case_id)
        if ground_truth is not None and self.ccf_window_s is not None and self.ccf_denominator_s is not None:
            # Dynamically derive ground truth metrics over CCF window
            gt_ccis = ground_truth.get("ccis") or ground_truth.get(
                "cci_intervals", []
            )
            gt_pause_s = 0.0
            for c in gt_ccis:
                cs = float(c.get("start_s", c.get("t_start_s", 0.0)))
                ce = float(c.get("end_s", c.get("t_end_s", 0.0)))
                ov_start = max(self.ccf_window_s[0], cs)
                ov_end = min(self.ccf_window_s[1], ce)
                if ov_end > ov_start:
                    gt_pause_s += ov_end - ov_start
            gt_cpr_s = max(0.0, self.ccf_denominator_s - gt_pause_s)
            gt_ccf = (
                gt_cpr_s / self.ccf_denominator_s
                if self.ccf_denominator_s > 0
                else 0.0
            )
            ccf_err = abs((self.ccf or 0.0) - gt_ccf)

            # Measure difference between non-CPR motion duration and emitted raw CCIs over CCF window
            raw_in_ccf_win = [
                c
                for c in self.raw_intervals
                if float(c["t_start_s"]) < self.ccf_window_s[1]
                and float(c["t_end_s"]) > self.ccf_window_s[0]
            ]
            raw_cci_dur_in_ccf = sum(
                max(
                    0.0,
                    min(self.ccf_window_s[1], float(c["t_end_s"]))
                    - max(self.ccf_window_s[0], float(c["t_start_s"])),
                )
                for c in raw_in_ccf_win
            )
            motion_non_cpr_dur = max(
                0.0, self.ccf_denominator_s - (self.cpr_active_duration_s or 0.0)
            )
            measurement_gap = abs(motion_non_cpr_dur - raw_cci_dur_in_ccf)

            matched_rep = _match_intervals(self.reported_intervals, gt_ccis, tol_s=3.0)
            rep_matched_preds = [p for p, _, _, _ in matched_rep]
            tp_count = len(rep_matched_preds)
            fp_count = len(self.reported_intervals) - tp_count

            s6_fp_count = 0
            s6_events = []
            if self.video_path and Path(self.video_path).exists():
                try:
                    s6_events = S6CoverageDetector(profile_name=getattr(self, "profile_name", "simvideo2")).detect_occlusion_from_video(self.video_path)
                except Exception:
                    s6_events = []

            for c in self.reported_intervals:
                if c not in rep_matched_preds:
                    cs, ce = float(c["t_start_s"]), float(c["t_end_s"])
                    has_s6 = bool(c.get("s6_crowding")) or any(max(cs, o.t_start_s) < min(ce, o.t_end_s) for o in s6_events)
                    if has_s6:
                        s6_fp_count += 1
            unexplained_fp_count = fp_count - s6_fp_count

            matched_ccf = _match_intervals(self.raw_intervals, gt_ccis, tol_s=3.0)
            ccf_matched_preds = [p for p, _, _, _ in matched_ccf]
            fp_pause_dur = sum(
                max(0.0, min(self.ccf_window_s[1], float(c["t_end_s"])) - max(self.ccf_window_s[0], float(c["t_start_s"])))
                for c in self.raw_intervals
                if c not in ccf_matched_preds
                and float(c["t_start_s"]) < self.ccf_window_s[1]
                and float(c["t_end_s"]) > self.ccf_window_s[0]
            )
            matched_gt_indices = set(gt_ccis.index(g) for _, g, _, _ in matched_ccf if g in gt_ccis)
            fn_pause_dur = sum(
                max(0.0, min(self.ccf_window_s[1], float(g.get("end_s", g.get("t_end_s", 0.0)))) - max(self.ccf_window_s[0], float(g.get("start_s", g.get("t_start_s", 0.0)))))
                for idx, g in enumerate(gt_ccis)
                if idx not in matched_gt_indices
                and float(g.get("start_s", g.get("t_start_s", 0.0))) < self.ccf_window_s[1]
                and float(g.get("end_s", g.get("t_end_s", 0.0))) > self.ccf_window_s[0]
            )

            lines.append("Validation & Error Decomposition (Computed vs Ground Truth, Q-017):")
            lines.append(
                f"  - Ground Truth CCF ({self.ccf_window_s[0]:.2f}-{self.ccf_window_s[1]:.2f}s): {gt_ccf:.4f}"
            )
            lines.append(
                f"  - Absolute CCF Error: {ccf_err:.4f} (~{round(ccf_err, 2)})"
            )
            lines.append(
                f"  - Cancelling Error Decomposition: Observed CCF error {ccf_err:.2f} reflects cancelling errors: "
                f"+{fp_pause_dur:.1f}s of false-positive pause duration accumulated during detection vs -{fn_pause_dur:.1f}s of missed true pause duration."
            )
            lines.append(
                f"  - Two Independent Measurements: Over the CCF evaluation window, non-CPR duration derived from "
                f"motion events ({motion_non_cpr_dur:.2f}s) differs from emitted raw CCIs ({raw_cci_dur_in_ccf:.2f}s) "
                f"by exactly {measurement_gap:.2f}s due to sub-0.5s dropouts and boundary adjustments."
            )
            lines.append(
                f"  - False Positive Rate: Under the >=5.0s reporting threshold, {fp_count} of {len(self.reported_intervals)} reported intervals "
                f"are false positives under +/-3.0s monotonic matching ({s6_fp_count} coincide with S6 provider crowding; {unexplained_fp_count} unexplained)."
            )
            lines.append(
                "  - Interruption Detection Limits: Long clinical interruptions may be fragmented by "
                "optical flow without visual occlusion detected to explain it (F-028)."
            )
            lines.append(
                "  - Shock Containment vs Ground Truth: Defibrillation shocks evaluated against continuous "
                "mechanical CPR do not fall inside true pauses (F-029)."
            )
        else:
            lines.append(
                "Validation Status: Accuracy not validated for this case (no ground truth supplied)."
            )
        lines.append("")

        # Section 2: Defibrillation Shocks (I1, I2, J3, K1)
        lines.append("--- SECTION 2: DEFIBRILLATION SHOCKS ---")
        if self.shocks:
            contained_count = sum(1 for s in self.shocks if s.shock_inside_cci)
            lines.append(
                f"Shock Containment ({contained_count} of {len(self.shocks)} shocks fall inside detected intervals): "
                "Evaluated against CCF consumer tier intervals (>=1.0s, min_pause_duration_s). "
                "Under continuous mechanical CPR, true clinical pauses do not contain defibrillation shocks (F-029)."
            )
            for s in self.shocks:
                ts_str = (
                    f"{s.detected_timestamp_s:.2f}s"
                    if s.detected_timestamp_s is not None
                    else "None"
                )
                pre_str = (
                    f"{s.pre_shock_pause_s:.2f}s"
                    if s.pre_shock_pause_s is not None
                    else "None"
                )
                post_str = (
                    f"{s.post_shock_pause_s:.2f}s"
                    if s.post_shock_pause_s is not None
                    else "None"
                )
                lines.append(
                    f"  - {s.id}: Candidate={s.candidate_timestamp_s:.2f}s ({s.candidate_source}) | Acoustic={ts_str} | "
                    f"Status={s.adjudication_status} ({s.adjudication_verdict}) | "
                    f"Inside Pause={s.shock_inside_cci} (Pre-pause: {pre_str}, Post-pause: {post_str})"
                )
        else:
            lines.append("  (No candidate shock timestamps supplied by operator)")
        lines.append("")

        # Section 3: Clinical Interruptions (CCI) (I3: Unconditional system-level notes)
        lines.append(
            "--- SECTION 3: CLINICAL INTERRUPTIONS (CCI) & CONSUMER TIERS ---"
        )
        if self.intervals_abstained or self.interval_window_s is None:
            lines.append(
                f"Clinical Interruptions (CCI): ABSTAINED ({self.intervals_abstain_reason})"
            )
        else:
            lines.append(
                f"Total Intervals: {len(self.raw_intervals)} raw emitted in clinical window | "
                f"{len(self.ccf_intervals)} CCF tier (>=1.0s) | "
                f"{len(self.redcap_intervals)} REDCap tier (>=3.0s) | "
                f"{len(self.reported_intervals)} Reporting tier (>=5.0s)"
            )
            lines.append("")
            lines.append("System Calibration & Methodological Basis:")
            lines.append(
                "  - Thresholds calibrated on n=1 screen-recorded video stack (F-017). "
                "Interval precision, recall, and error characteristics are unvalidated for this case."
            )
            lines.append(
                "  - Three consumers, three rules, two measurements: CCF active duration and the interval stream "
                "derive independently from active compression motion events."
            )
            lines.append("")
            lines.append(
                "Reported Clinical Interruptions (>=5.0s Reporting Consumer Tier):"
            )
            if self.reported_intervals:
                for idx, cci in enumerate(self.reported_intervals, start=1):
                    lines.append(
                        f"  #{idx:02d}: {float(cci['t_start_s']):6.2f}s - {float(cci['t_end_s']):6.2f}s "
                        f"(dur={float(cci['duration_s']):5.2f}s, conf={float(cci.get('confidence', 0.0)):.2f})"
                    )
            else:
                lines.append("  (No interruptions >= 5.0s detected)")
        lines.append("=" * 80)

        return "\n".join(lines)


class CCFReportGenerator:
    """
    Generator that executes Sensor S1, S3, and S5 to build a CCF quality report.
    Operates strictly on video/audio inputs and operator parameters without reading ground truth.
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
        clinical_milestones: dict[str, float] | None = None,
        candidate_shock_times_s: Sequence[float] | None = None,
        ground_truth: dict[str, Any] | None = None,
    ) -> CCFReport:
        """
        Generates deterministic CCF report from clinical resuscitation video and audio.

        Args:
            video_path: Path to resuscitation video file.
            case_id: Case identifier string.
            clinical_milestones: Optional operator-supplied dictionary containing:
                - 'patient_enters_room_s': Start of clinical interval window (e.g. 36.0s).
                - 'death_pronounced_s': End of resuscitation window (e.g. 922.0s).
                If death_pronounced_s is omitted, CCF is ABSTAINED (I6 / F-026).
            candidate_shock_times_s: Optional operator-supplied candidate shock timestamps to adjudicate (I4).
        """
        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"Video file not found: {path}")

        # 1. Determine total video duration
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video file: {path}")
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        cap.release()
        total_dur = float(n_frames / fps) if fps > 0 and n_frames > 0 else 0.0

        # 2. Extract Operator-Supplied Clinical Milestones (H1, I6, P4)
        if clinical_milestones and "patient_enters_room_s" in clinical_milestones:
            patient_enters_room_s: float | None = float(
                clinical_milestones["patient_enters_room_s"]
            )
            patient_enters_room_source = "operator_supplied"
            intervals_abstained = False
            intervals_abstain_reason = None
        else:
            patient_enters_room_s = None
            patient_enters_room_source = "not_supplied"
            intervals_abstained = True
            intervals_abstain_reason = (
                "patient_enters_room_s milestone not supplied by operator "
                "(interval reporting window undefined, defaulting prohibited per P4)"
            )

        if clinical_milestones and "death_pronounced_s" in clinical_milestones:
            death_pronounced_s: float | None = float(
                clinical_milestones["death_pronounced_s"]
            )
            death_pronounced_source = "operator_supplied"
            ccf_abstained = False
            ccf_abstain_reason = None
        else:
            death_pronounced_s = None
            death_pronounced_source = "not_supplied"
            ccf_abstained = True
            ccf_abstain_reason = (
                "death_pronounced_s milestone not supplied by operator "
                "(ungated full-track CCF calculation prohibited per F-026 / Decision 027)"
            )

        # 3. Run Sensor S1 (CPR compression intervals and CCI pause intervals)
        events = self.s1_detector.detect_from_video(path)
        if total_dur == 0.0 and events:
            total_dur = max(float(e.t_end_s) for e in events)

        interval_end_s = (
            death_pronounced_s if death_pronounced_s is not None else total_dur
        )

        # Compute CCF over active CPR window (t_first -> death_pronounced_s, Q-012 Candidate c)
        if not ccf_abstained and death_pronounced_s is not None:
            ccf_dict = self.s1_detector.compute_ccf(
                events, death_pronounced_s=death_pronounced_s
            )
            ccf_val: float | None = float(ccf_dict.get("ccf", 0.0))
            ccf_pct: float | None = (
                (ccf_val * 100.0) if ccf_val is not None else None
            )
            t_first_s = ccf_dict.get("t_first_s")
            t_first_source = "sensor_derived (S1 first compression motion)"
            cpr_active_dur: float | None = float(
                ccf_dict.get("cpr_duration_s", 0.0)
            )
            ccf_denom: float | None = float(
                ccf_dict.get("denominator_s", 0.0)
            )
            ccf_window_s: tuple[float, float] | None = (
                float(t_first_s) if t_first_s is not None else 0.0,
                death_pronounced_s,
            )
            cpr_active_frac: float | None = (
                (cpr_active_dur / ccf_denom) if (ccf_denom and ccf_denom > 0) else 0.0
            )
        else:
            # I6: CCF calculation abstained
            ccf_val = None
            ccf_pct = None
            cpr_active_dur = None
            ccf_denom = None
            ccf_window_s = None
            cpr_active_frac = None
            # Derive t_first from first mode event if available
            valid_modes = ("mechanical", "manual")
            first_mode_ev = next(
                (
                    e
                    for e in sorted(events, key=lambda x: x.t_start_s)
                    if getattr(e, "compression_mode", None) in valid_modes
                ),
                None,
            )
            t_first_s = (
                float(first_mode_ev.t_start_s)
                if first_mode_ev is not None
                else (float(events[0].t_start_s) if events else 0.0)
            )
            t_first_source = "sensor_derived (S1 first compression motion)"

        # Window intervals if patient_enters_room_s is supplied; otherwise abstain per P4
        if not intervals_abstained and patient_enters_room_s is not None:
            interval_window_s: tuple[float, float] | None = (
                patient_enters_room_s,
                interval_end_s,
            )
            all_raw_ccis = self.s1_detector.detect_cci_intervals(
                events, total_duration_s=total_dur
            )
            raw_windowed_ccis = [
                c
                for c in all_raw_ccis
                if float(c["t_start_s"]) < interval_end_s
                and float(c["t_end_s"]) > patient_enters_room_s
            ]
            ccf_ccis = self.s1_detector.filter_ccis_by_consumer(
                raw_windowed_ccis, consumer="ccf"
            )
            redcap_ccis = self.s1_detector.filter_ccis_by_consumer(
                raw_windowed_ccis, consumer="redcap"
            )
            reporting_ccis = self.s1_detector.filter_ccis_by_consumer(
                raw_windowed_ccis, consumer="reporting"
            )
            total_cci_dur = sum(float(c.get("duration_s", 0.0)) for c in ccf_ccis)
        else:
            interval_window_s = None
            raw_windowed_ccis = []
            ccf_ccis = []
            redcap_ccis = []
            reporting_ccis = []
            total_cci_dur = 0.0

        # 4. Run Sensor S5 (Clock Anchor synchronization)
        t0_iso: str | None = None
        t0_source = "no timecode overlay found in ROI"
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
                else:
                    t0_source = "no timecode overlay found in ROI"
            else:
                t0_source = "no timecode overlay found in ROI"
        except Exception as e:
            logging.warning("S5 timecode extraction exception on %s: %s", path, e, exc_info=True)
            t0_iso = None
            t0_source = f"timecode extraction failed: {type(e).__name__}"

        # 5. Run Sensor S3 (Defibrillation Shocks & Adjudication, I1 & I4)
        shocks_detail: list[CCFShockDetail] = []
        is_profile_calibrated = not (
            self.s3_detector.profile_name in ("default", "UNKNOWN")
            or "UNKNOWN" in str(self.s3_detector.profile.get("device_model", ""))
        )

        if candidate_shock_times_s is not None:
            for idx, t_cand in enumerate(candidate_shock_times_s, start=1):
                verdict = self.s3_detector.adjudicate(path, t_cand, window_s=30.0)
                is_conf = verdict.confirmed and verdict.event is not None
                ev = verdict.event

                if not is_profile_calibrated:
                    # Invariant I5: uncalibrated device profile means adjudication is unavailable, not unconfirmed
                    status_str = "UNAVAILABLE"
                    verdict_str = "S3 adjudication unavailable: no calibrated profile for this device (Q-019)"
                else:
                    status_str = "CONFIRMED" if is_conf else "UNCONFIRMED"
                    verdict_str = verdict.reason

                shock_time = ev.timestamp_s if (is_conf and ev) else float(t_cand)
                enclosing_cci: dict[str, Any] | None = None
                for cci in raw_windowed_ccis:
                    if (
                        float(cci["t_start_s"])
                        <= shock_time
                        <= float(cci["t_end_s"])
                    ):
                        enclosing_cci = cci
                        break

                pre_pause: float | None = None
                post_pause: float | None = None
                cci_id: str | None = None
                is_contained = enclosing_cci is not None
                if enclosing_cci is not None:
                    cci_id = str(enclosing_cci.get("id", ""))
                    pre_pause = round(
                        shock_time - float(enclosing_cci["t_start_s"]), 2
                    )
                    post_pause = round(
                        float(enclosing_cci["t_end_s"]) - shock_time, 2
                    )

                iso_val: str | None = None
                if t0_iso is not None:
                    iso_val = f"{t0_iso} + {shock_time:.2f}s"

                shocks_detail.append(
                    CCFShockDetail(
                        id=f"shock_{idx}",
                        candidate_timestamp_s=round(float(t_cand), 2),
                        candidate_source="operator_supplied",
                        detected_timestamp_s=round(ev.timestamp_s, 2)
                        if (is_conf and ev)
                        else None,
                        iso_time=iso_val,
                        confirmed=is_conf,
                        adjudication_status=status_str,
                        adjudication_verdict=verdict_str,
                        pre_shock_pause_s=pre_pause,
                        post_shock_pause_s=post_pause,
                        shock_inside_cci=is_contained,
                        cci_id=cci_id,
                        peak_rms_ratio=round(ev.transient_ratio, 2)
                        if (is_conf and ev)
                        else 0.0,
                        tone_slope_hz_s=round(ev.slope_hz_per_s, 2)
                        if (is_conf and ev)
                        else 0.0,
                    )
                )

        # 6. Compute 2-minute epoch CCF over active CCF window
        ccf_by_epoch: list[float] = []
        if not ccf_abstained and ccf_denom is not None and death_pronounced_s is not None:
            epoch_win = 120.0
            n_epochs = (
                int(ccf_denom // epoch_win) if ccf_denom >= epoch_win else 1
            )
            cpr_events_in_ccf = [
                e
                for e in events
                if float(e.t_start_s) < death_pronounced_s
                and float(e.t_end_s) > (t_first_s or 0.0)
            ]
            for i in range(max(1, n_epochs)):
                w_start = (t_first_s or 0.0) + i * epoch_win
                w_end = min(death_pronounced_s, w_start + epoch_win)
                w_len = max(0.0, w_end - w_start)
                if w_len == 0.0:
                    continue
                epoch_cpr = 0.0
                for e in cpr_events_in_ccf:
                    es = float(e.t_start_s)
                    ee = float(e.t_end_s)
                    ov_s = max(w_start, es)
                    ov_e = min(w_end, ee)
                    if ov_e > ov_s:
                        epoch_cpr += ov_e - ov_s
                ccf_by_epoch.append(round(min(1.0, epoch_cpr / w_len), 4))

        n_over_10s = sum(
            1 for c in ccf_ccis if float(c.get("duration_s", 0.0)) > 10.0
        )
        cci_durs = [float(c.get("duration_s", 0.0)) for c in ccf_ccis]
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

        return CCFReport(
            case_id=case_id,
            video_path=str(path),
            t0_iso=t0_iso,
            t0_source=t0_source,
            total_case_duration_s=round(total_dur, 2),
            patient_enters_room_s=round(patient_enters_room_s, 2)
            if patient_enters_room_s is not None
            else None,
            patient_enters_room_source=patient_enters_room_source,
            death_pronounced_s=round(death_pronounced_s, 2)
            if death_pronounced_s is not None
            else None,
            death_pronounced_source=death_pronounced_source,
            interval_window_s=interval_window_s,
            intervals_abstained=intervals_abstained,
            intervals_abstain_reason=intervals_abstain_reason,
            ccf_window_s=ccf_window_s,
            t_first_s=round(t_first_s, 2) if t_first_s is not None else None,
            t_first_source=t_first_source,
            ccf_denominator_s=round(ccf_denom, 2)
            if ccf_denom is not None
            else None,
            total_cpr_duration_s=round(cpr_active_dur, 2)
            if cpr_active_dur is not None
            else None,
            total_cci_duration_s=round(total_cci_dur, 2),
            cpr_active_duration_s=round(cpr_active_dur, 2)
            if cpr_active_dur is not None
            else None,
            cpr_active_fraction=cpr_active_frac,
            ccf=ccf_val,
            ccf_percent=ccf_pct,
            ccf_by_2min_epoch=ccf_by_epoch,
            ccf_abstained=ccf_abstained,
            ccf_abstain_reason=ccf_abstain_reason,
            n_cci_over_10s=n_over_10s,
            longest_cci_s=round(longest_cci, 2),
            median_cci_s=round(median_cci, 2),
            shocks=shocks_detail,
            raw_intervals=raw_windowed_ccis,
            ccf_intervals=ccf_ccis,
            redcap_intervals=redcap_ccis,
            reported_intervals=reporting_ccis,
            compression_intervals=comp_dicts,
            ground_truth=ground_truth,
        )


def generate_ccf_report(
    video_path: str | Path,
    case_id: str = "case_01",
    profile_name: str = "default",
    clinical_milestones: dict[str, float] | None = None,
    candidate_shock_times_s: Sequence[float] | None = None,
    ground_truth: dict[str, Any] | None = None,
) -> CCFReport:
    """Convenience wrapper for generating a CCFReport."""
    generator = CCFReportGenerator(profile_name=profile_name)
    return generator.generate_report(
        video_path=video_path,
        case_id=case_id,
        clinical_milestones=clinical_milestones,
        candidate_shock_times_s=candidate_shock_times_s,
        ground_truth=ground_truth,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate Clinical CCF Report")
    parser.add_argument("--video", required=True, help="Path to video file")
    parser.add_argument("--case-id", default="simvideo2", help="Case identifier")
    parser.add_argument("--profile", default="simvideo2", help="Calibration profile name")
    parser.add_argument("--patient-arrival", type=float, default=36.0, help="Patient enters room offset (seconds)")
    parser.add_argument("--death-pronounced", type=float, default=922.0, help="Death pronounced offset (seconds)")
    parser.add_argument("--shocks", nargs="*", type=float, default=[165.0, 388.0, 622.0, 742.0, 879.0], help="Candidate shock times")
    parser.add_argument("--ground-truth", default=None, help="Path to ground truth JSON fixture")
    parser.add_argument("--output", default="demo/sample_simvideo2_ccf_report.json", help="Output JSON path")
    parser.add_argument("--text", action="store_true", help="Print human-readable text report")
    args = parser.parse_args()

    milestones = {
        "patient_enters_room_s": args.patient_arrival,
        "death_pronounced_s": args.death_pronounced,
    }
    gt_payload: dict[str, Any] | None = None
    if args.ground_truth:
        gt_path = Path(args.ground_truth)
        if gt_path.exists():
            gt_payload = json.loads(gt_path.read_text(encoding="utf-8"))

    report = generate_ccf_report(
        video_path=args.video,
        case_id=args.case_id,
        profile_name=args.profile,
        clinical_milestones=milestones,
        candidate_shock_times_s=args.shocks,
        ground_truth=gt_payload,
    )

    out_p = Path(args.output)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(report.to_json(), encoding="utf-8")
    print(f"✓ CCF Report successfully written to {out_p}")

    if args.text:
        print(report.format_text_report(ground_truth=gt_payload))

