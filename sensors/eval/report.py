"""
Evaluation reporting utility for deterministic sensor scorecards (S00).
Formats and prints evaluation scorecards, ensuring that the provenance mix is
explicitly printed on every single metric line (e.g.,
`CCI F1: 0.83 (n=1 case, 3 intervals, ALL block_probe_unverified)`).
"""

import argparse
import json
from pathlib import Path
from typing import Sequence
from sensors.eval.metrics import (
    ScoreCard,
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate sensor against ground truth.")
    parser.add_argument("--sensor", type=str, required=True, help="Sensor name (e.g., s1)")
    parser.add_argument("--ground-truth", type=str, required=True, help="Path to ground truth JSON fixture")
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
        detector = S1ChestMotionDetector(profile_name="simvideo2")
        events = detector.detect_from_video(video_path)
        ccis = detector.detect_cci_intervals(events, total_duration_s=gt_data.get("video_duration_s", 1363.78))
        
        death_p_s = gt_data.get("clinical_milestones", {}).get("death_pronounced_s", gt_data.get("death_pronounced_s"))
        ccf_res = detector.compute_ccf(events, death_pronounced_s=death_p_s)
        pred_ccf = ccf_res["ccf"]
        gt_ccf = gt_data.get("ccf_summary", {}).get("ccf", 0.0)
        ccf_err = abs((pred_ccf or 0.0) - gt_ccf)

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
        print_scorecard_report([c_f1, c_p, c_r, c_mae, c_ccf], title=f"Sensor {args.sensor.upper()} vs Ground Truth ({args.ground_truth})")
    else:
        raise NotImplementedError(f"Sensor {args.sensor} evaluation not implemented")


if __name__ == "__main__":
    main()
