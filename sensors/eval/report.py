"""
Evaluation reporting utility for deterministic sensor scorecards (S00 / S03a).
Formats and prints reproducible evaluation scorecards across consumer reporting tiers,
ensuring explicit provenance, metadata preambles, and consistent matching definitions.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence
from sensors.eval.metrics import (
    ScoreCard,
    _match_intervals,
    score_interval_f1,
    score_interval_precision,
    score_interval_recall,
    score_boundary_mae,
)
from sensors.s1_s6_motion import S1ChestMotionDetector


def format_scorecard_line(card: ScoreCard) -> str:
    """
    Formats a single scorecard line with explicit provenance mix in the metric line:
    "CCI F1              0.83   n=1 case, 3 intervals    ⚠ ALL block_probe_unverified"
    """
    case_label = "case" if card.n_cases == 1 else "cases"
    item_label = "interval" if "Interval" in card.metric_name or "CCI" in card.metric_name else (
        "event" if "Event" in card.metric_name else "item"
    )
    if card.n_items != 1:
        item_label += "s"

    caveat_str = (
        f"⚠ {card.caveat}"
        if card.is_unverified or "SELF-COMPARISON" in card.caveat
        else card.caveat
    )
    counts_str = f"n={card.n_cases} {case_label}, {card.n_items} {item_label}"
    return f"{card.metric_name:<20} {card.value:<6.2f} {counts_str:<24} {caveat_str}"


def format_scorecard_report(
    scorecards: Sequence[ScoreCard],
    title: str = "Sensor Evaluation Scorecard",
) -> str:
    """
    Formats a full report across multiple scorecards.
    Every metric line includes its exact provenance mix.
    """
    lines = [f"=== {title} ==="]
    for card in scorecards:
        lines.append(format_scorecard_line(card))
    return "\n".join(lines)


def print_scorecard_report(
    scorecards: Sequence[ScoreCard],
    title: str = "Sensor Evaluation Scorecard",
) -> None:
    """Prints the formatted scorecard report to stdout."""
    print(format_scorecard_report(scorecards, title=title))


def evaluate_s1_consumers(gt_data: dict[str, Any], video_path: Path, gt_path_str: str) -> None:
    """
    Executes reproducible multi-consumer evaluation of Sensor S1 against ground truth,
    applying consistent matching definitions and reporting floor parameters.
    """
    profile_name = gt_data.get("profile", "simvideo2")
    detector = S1ChestMotionDetector(profile_name=profile_name)
    events = detector.detect_from_video(video_path)
    total_dur = float(gt_data.get("video_duration_s", 1363.78))
    ccis_all = detector.detect_cci_intervals(events, total_duration_s=total_dur)

    milestones = gt_data.get("clinical_milestones", {})
    t_start = float(milestones.get("patient_enters_room", gt_data.get("patient_enters_room", 36.0)))
    t_end = float(milestones.get("death_pronounced_s", gt_data.get("death_pronounced_s", 922.0)))

    # Gate on active clinical resuscitation window
    s1_clin = [c for c in ccis_all if t_start <= float(c["t_start_s"]) <= t_end]

    # Consumer representations
    s1_raw = detector.filter_ccis_by_consumer(s1_clin, "ccf")
    s1_floor = detector.filter_ccis_by_consumer(s1_clin, "reporting")

    gt_ccis = gt_data.get("ccis", [])
    ccf_res = detector.compute_ccf(events, death_pronounced_s=t_end)
    pred_ccf = float(ccf_res.get("ccf") or 0.0)
    t_first = float(ccf_res.get("t_first_s") or 70.75)
    denom_gt = max(t_end - t_first, 1e-6)
    gt_pauses = sum(max(0.0, min(t_end, float(g["end_s"])) - max(t_first, float(g["start_s"]))) for g in gt_ccis if float(g["start_s"]) < t_end and float(g["end_s"]) > t_first)
    gt_ccf = round((denom_gt - gt_pauses) / denom_gt, 4)
    ccf_err = abs(pred_ccf - gt_ccf)

    # Consistent tolerance matching metrics across both columns (+/- 3.0s default, +/- 2.0s shown)
    f1_2s_raw = score_interval_f1(s1_raw, gt_ccis, tol_s=2.0).value
    f1_3s_raw = score_interval_f1(s1_raw, gt_ccis, tol_s=3.0).value
    prec_3s_raw = score_interval_precision(s1_raw, gt_ccis, tol_s=3.0).value
    rec_3s_raw = score_interval_recall(s1_raw, gt_ccis, tol_s=3.0).value
    mae_raw = score_boundary_mae(s1_raw, gt_ccis, tol_s=2.0).value
    fp_raw = round(len(s1_raw) * (1.0 - prec_3s_raw))

    f1_2s_fl = score_interval_f1(s1_floor, gt_ccis, tol_s=2.0).value
    f1_3s_fl = score_interval_f1(s1_floor, gt_ccis, tol_s=3.0).value
    prec_3s_fl = score_interval_precision(s1_floor, gt_ccis, tol_s=3.0).value
    rec_3s_fl = score_interval_recall(s1_floor, gt_ccis, tol_s=3.0).value
    mae_fl = score_boundary_mae(s1_floor, gt_ccis, tol_s=2.0).value
    fp_fl = round(len(s1_floor) * (1.0 - prec_3s_fl))

    print(f"=== Sensor S1 Evaluation Scorecard vs Ground Truth ({gt_path_str}) ===")
    print("Preamble:")
    print(f"  - Video FPS: 16.0")
    print(f"  - Profile: {profile_name}")
    print(f"  - Interval Reporting Window: {t_start}s - {t_end}s (patient_enters_room to death_pronounced_s, denom 886.0s)")
    print(f"  - CCF Evaluation Window (Q-012): {t_first}s - {t_end}s (first compression event to death_pronounced_s, denom {denom_gt}s)")
    print(f"  - Total Duration: {total_dur}s")
    print("  - Tolerance: +/- 3.0s (default matcher tolerance; +/- 2.0s shown for strict comparisons)")
    print(f"  - Sample Size: n=1 case ({len(gt_ccis)} human-adjudicated CCIs, provenance: human_adjudicated)")
    print("  - Matching Definition: Consistent monotonic tolerance matching applied across Precision, Recall, F1, and FP counts.")
    print(f"  - Tier-Independent Metric: CCF error (70.75-922s) = {ccf_err:.2f} (derived independently from active motion events)")
    print("\n                          S1 (>=1.0s CCF)   S1 (>=5.0s Reporting)")
    print(f"CCI F1 (+/-3.0s)        {f1_3s_raw:6.2f}          {f1_3s_fl:6.2f}")
    print(f"Precision (+/-3.0s)     {prec_3s_raw:6.2f}          {prec_3s_fl:6.2f}")
    print(f"Recall (+/-3.0s)        {rec_3s_raw:6.2f}          {rec_3s_fl:6.2f}")
    print(f"False Positives (+/-3s) {fp_raw:6d}          {fp_fl:6d}")
    print(f"CCI F1 (+/-2.0s)        {f1_2s_raw:6.2f}          {f1_2s_fl:6.2f}")
    print(f"Boundary MAE            {mae_raw:5.2f}s          {mae_fl:5.2f}s")
    print(f"intervals reported      {len(s1_raw):6d}          {len(s1_floor):6d}")

    # E5: Print per-interval TP/FP/S6 audit table from committed matcher
    from sensors.s1_s6_motion import S6CoverageDetector
    d6 = S6CoverageDetector(profile_name)
    s6_events = d6.detect_occlusion_from_video(video_path)
    matched_rep = _match_intervals(s1_floor, gt_ccis, tol_s=3.0)
    rep_matched_preds = [p for p, _, _, _ in matched_rep]

    print("\n--- Per-Interval Audit Table (>=5.0s Reporting Consumer vs GT, +/-3.0s Monotonic Matcher) ---")
    for idx, c in enumerate(s1_floor):
        cs, ce = float(c["t_start_s"]), float(c["t_end_s"])
        dur = round(ce - cs, 2)
        is_tp = c in rep_matched_preds
        ov_s6 = [o for o in s6_events if max(cs, o.t_start_s) < min(ce, o.t_end_s)]
        s6_str = "True (" + ", ".join(o.degradation_type for o in ov_s6) + ")" if ov_s6 else "False (unexplained >=5s false positive)"
        status = "TP" if is_tp else "FP"
        print(f"#{idx+1:02d}: {cs:5.1f}-{ce:5.1f}s (dur={dur:4.1f}s) -> {status:2s} | S6={s6_str}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate sensor against ground truth.")
    parser.add_argument("--sensor", type=str, required=True, help="Sensor name (e.g., s1)")
    parser.add_argument("--ground-truth", type=str, required=True, help="Path to ground truth JSON fixture")
    parser.add_argument("--consumer", type=str, default="compare", choices=["compare", "ccf", "redcap", "reporting"], help="Consumer mode or compare view")
    args = parser.parse_args()

    gt_path = Path(args.ground_truth)
    if not gt_path.exists():
        raise FileNotFoundError(f"Ground truth file not found: {gt_path}")
    with open(gt_path) as f:
        gt_data = json.load(f)

    if args.sensor.lower() == "s1":
        video_path = Path("tests/video") / gt_data.get("case_id", "vidsim2.mp4")
        if not video_path.exists():
            video_path = Path("tests/video/vidsim2.mp4")

        if args.consumer == "compare":
            evaluate_s1_consumers(gt_data, video_path, args.ground_truth)
            return

        detector = S1ChestMotionDetector(profile_name="simvideo2")
        events = detector.detect_from_video(video_path)
        total_dur = float(gt_data.get("video_duration_s", 1363.78))
        ccis = detector.detect_cci_intervals(events, total_duration_s=total_dur)
        ccis = detector.filter_ccis_by_consumer(ccis, consumer=args.consumer)

        death_p_s = gt_data.get("clinical_milestones", {}).get("death_pronounced_s", gt_data.get("death_pronounced_s"))
        ccf_res = detector.compute_ccf(events, death_pronounced_s=death_p_s)
        pred_ccf = float(ccf_res.get("ccf") or 0.0)
        gt_ccf = float(gt_data.get("ccf_summary", {}).get("ccf", gt_data.get("ccf", 0.0)))
        ccf_err = abs(pred_ccf - gt_ccf)

        gt_ccis = gt_data.get("ccis", [])
        c_f1 = score_interval_f1(ccis, gt_ccis, tol_s=2.0)
        c_p = score_interval_precision(ccis, gt_ccis, tol_s=2.0)
        c_r = score_interval_recall(ccis, gt_ccis, tol_s=2.0)
        c_mae = score_boundary_mae(ccis, gt_ccis, tol_s=2.0)
        c_ccf = ScoreCard(
            metric_name="CCF Error",
            value=ccf_err,
            n_cases=1,
            n_items=1,
            provenance="human_adjudicated",
            is_unverified=False,
            caveat="",
        )
        print_scorecard_report([c_f1, c_p, c_r, c_mae, c_ccf], title=f"Sensor {args.sensor.upper()} [{args.consumer}] vs Ground Truth ({args.ground_truth})")
    else:
        raise NotImplementedError(f"Sensor {args.sensor} evaluation not implemented")


if __name__ == "__main__":
    main()
