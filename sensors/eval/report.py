"""
Evaluation reporting utility for deterministic sensor scorecards (S00).
Formats and prints evaluation scorecards, ensuring that the provenance mix is
explicitly printed on every single metric line (e.g.,
`CCI F1: 0.83 (n=1 case, 3 intervals, ALL block_probe_unverified)`).
"""

from typing import Sequence
from sensors.eval.metrics import ScoreCard


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
