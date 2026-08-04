"""
Evaluation metric suite for deterministic sensor outputs (S00).
Scores sensor predictions against ground-truth fixtures and enforces strict provenance
reporting. Refuses to compute formal accuracy against unverified probe references
unless explicitly permitted (`allow_unverified=True`), labeling all such metrics
prominently in the output scorecard (Q-017).
"""

from dataclasses import dataclass
from typing import Any


UNVERIFIED_PROVENANCE_TAGS = {
    "block_probe_unverified",
    "probe_verified",
    "corroborated_both_runs",
    "run_02, unverified",
    "disputed",
    "unverified",
}


@dataclass(frozen=True)
class ScoreCard:
    """Immutable evaluation scorecard for a scored sensor metric."""

    metric_name: str
    value: float
    n_cases: int
    n_items: int
    provenance_mix: dict[str, int]
    is_unverified: bool
    caveat: str


def _analyze_provenance(
    items: list[dict[str, Any]],
    allow_unverified: bool = False,
) -> tuple[dict[str, int], bool, str]:
    """
    Analyzes provenance tags across ground-truth items.
    Returns (provenance_mix, is_unverified, caveat_string).
    Raises ValueError if allow_unverified=False and unverified items are present.
    """
    mix: dict[str, int] = {}
    is_unverified = False

    for item in items:
        prov = str(item.get("provenance", "unverified"))
        mix[prov] = mix.get(prov, 0) + 1
        if prov in UNVERIFIED_PROVENANCE_TAGS or "unverified" in prov.lower():
            is_unverified = True

    if not allow_unverified and is_unverified:
        raise ValueError(
            "Refusing to compute formal accuracy metric against unverified ground truth "
            "without allow_unverified=True (see Q-017). Provenance mix: "
            + str(mix)
        )

    if not mix:
        caveat = "NO_GROUND_TRUTH_ITEMS"
    elif len(mix) == 1 and is_unverified:
        only_tag = next(iter(mix))
        caveat = f"ALL {only_tag}"
    elif len(mix) == 1:
        only_tag = next(iter(mix))
        caveat = f"ALL {only_tag}"
    elif is_unverified:
        parts = [f"{count} {tag}" for tag, count in sorted(mix.items())]
        caveat = "MIXED: " + ", ".join(parts)
    else:
        parts = [f"{count} {tag}" for tag, count in sorted(mix.items())]
        caveat = "MIXED: " + ", ".join(parts)

    return mix, is_unverified, caveat


def _match_events(
    predictions: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    tol_s: float = 2.0,
) -> list[tuple[dict[str, Any], dict[str, Any], float]]:
    """
    Monotonic order-preserving matching of predicted point events to ground truth
    within tolerance tol_s. If pred[i] matches truth[j], then pred[i+1] may only
    match truth[>j]. Prevents greedy nearest-neighbor cascade errors.
    """
    matched: list[tuple[dict[str, Any], dict[str, Any], float]] = []
    sorted_pred = sorted(
        predictions, key=lambda x: float(x.get("timestamp_s", x.get("t_start_s", 0.0)))
    )
    sorted_gt = sorted(
        ground_truth, key=lambda x: float(x.get("timestamp_s", x.get("t_start_s", 0.0)))
    )
    last_gt_idx = -1

    for pred in sorted_pred:
        pred_t = float(pred.get("timestamp_s", pred.get("t_start_s", 0.0)))
        best_gt_idx = -1
        best_err = float("inf")

        for idx in range(last_gt_idx + 1, len(sorted_gt)):
            gt = sorted_gt[idx]
            gt_t = float(gt.get("timestamp_s", gt.get("t_start_s", 0.0)))
            err = abs(pred_t - gt_t)
            if err <= tol_s and err < best_err:
                best_err = err
                best_gt_idx = idx

        if best_gt_idx != -1:
            last_gt_idx = best_gt_idx
            matched.append((pred, sorted_gt[best_gt_idx], best_err))

    return matched


def score_event_recall(
    predictions: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    tol_s: float = 2.0,
    n_cases: int = 1,
    allow_unverified: bool = False,
) -> ScoreCard:
    """Computes recall for discrete event detection within timestamp tolerance."""
    mix, is_unverified, caveat = _analyze_provenance(ground_truth, allow_unverified=allow_unverified)
    n_gt = len(ground_truth)
    if n_gt == 0:
        val = 1.0 if not predictions else 0.0
    else:
        matched = _match_events(predictions, ground_truth, tol_s=tol_s)
        val = len(matched) / n_gt

    return ScoreCard(
        metric_name="Event Recall",
        value=round(val, 4),
        n_cases=n_cases,
        n_items=n_gt,
        provenance_mix=mix,
        is_unverified=is_unverified,
        caveat=caveat,
    )


def score_event_precision(
    predictions: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    tol_s: float = 2.0,
    n_cases: int = 1,
    allow_unverified: bool = False,
) -> ScoreCard:
    """Computes precision for discrete event detection within timestamp tolerance."""
    mix, is_unverified, caveat = _analyze_provenance(ground_truth, allow_unverified=allow_unverified)
    n_pred = len(predictions)
    if n_pred == 0:
        val = 1.0 if not ground_truth else 0.0
    else:
        matched = _match_events(predictions, ground_truth, tol_s=tol_s)
        val = len(matched) / n_pred

    return ScoreCard(
        metric_name="Event Precision",
        value=round(val, 4),
        n_cases=n_cases,
        n_items=len(ground_truth),
        provenance_mix=mix,
        is_unverified=is_unverified,
        caveat=caveat,
    )


def score_event_f1(
    predictions: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    tol_s: float = 2.0,
    n_cases: int = 1,
    allow_unverified: bool = False,
) -> ScoreCard:
    """Computes harmonic mean F1 score for discrete event detection."""
    mix, is_unverified, caveat = _analyze_provenance(ground_truth, allow_unverified=allow_unverified)
    matched = _match_events(predictions, ground_truth, tol_s=tol_s)
    n_gt = len(ground_truth)
    n_pred = len(predictions)

    if n_gt == 0 and n_pred == 0:
        val = 1.0
    elif n_gt == 0 or n_pred == 0:
        val = 0.0
    else:
        recall = len(matched) / n_gt
        precision = len(matched) / n_pred
        if recall + precision == 0.0:
            val = 0.0
        else:
            val = 2.0 * (precision * recall) / (precision + recall)

    return ScoreCard(
        metric_name="Event F1",
        value=round(val, 4),
        n_cases=n_cases,
        n_items=n_gt,
        provenance_mix=mix,
        is_unverified=is_unverified,
        caveat=caveat,
    )


def score_event_timing_mae(
    predictions: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    tol_s: float = 2.0,
    n_cases: int = 1,
    allow_unverified: bool = False,
) -> ScoreCard:
    """Computes Mean Absolute Error (MAE) in seconds for matched point events."""
    mix, is_unverified, caveat = _analyze_provenance(ground_truth, allow_unverified=allow_unverified)
    matched = _match_events(predictions, ground_truth, tol_s=tol_s)

    if not matched:
        val = 0.0
    else:
        errors = [err for _, _, err in matched]
        val = sum(errors) / len(errors)

    return ScoreCard(
        metric_name="Event Timing MAE",
        value=round(val, 4),
        n_cases=n_cases,
        n_items=len(matched),
        provenance_mix=mix,
        is_unverified=is_unverified,
        caveat=caveat,
    )


def _match_intervals(
    predictions: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    tol_s: float = 2.0,
) -> list[tuple[dict[str, Any], dict[str, Any], float, float]]:
    """
    Monotonic order-preserving matching of predicted continuous intervals to ground truth
    within boundary tolerance. If pred[i] matches truth[j], then pred[i+1] may only
    match truth[>j]. Prevents greedy nearest-neighbor cascade errors.
    """
    matched: list[tuple[dict[str, Any], dict[str, Any], float, float]] = []
    sorted_pred = sorted(
        predictions, key=lambda x: float(x.get("start_s", x.get("t_start_s", 0.0)))
    )
    sorted_gt = sorted(
        ground_truth, key=lambda x: float(x.get("start_s", x.get("t_start_s", 0.0)))
    )
    last_gt_idx = -1

    for pred in sorted_pred:
        pred_start = float(pred.get("start_s", pred.get("t_start_s", 0.0)))
        pred_end = float(pred.get("end_s", pred.get("t_end_s", 0.0)))

        best_gt_idx = -1
        best_avg_err = float("inf")
        best_start_err = 0.0
        best_end_err = 0.0

        for idx in range(last_gt_idx + 1, len(sorted_gt)):
            gt = sorted_gt[idx]
            gt_start = float(gt.get("start_s", gt.get("t_start_s", 0.0)))
            gt_end = float(gt.get("end_s", gt.get("t_end_s", 0.0)))

            start_err = abs(pred_start - gt_start)
            end_err = abs(pred_end - gt_end)
            avg_err = (start_err + end_err) / 2.0

            if start_err <= tol_s and end_err <= tol_s and avg_err < best_avg_err:
                best_avg_err = avg_err
                best_gt_idx = idx
                best_start_err = start_err
                best_end_err = end_err

        if best_gt_idx != -1:
            last_gt_idx = best_gt_idx
            matched.append(
                (pred, sorted_gt[best_gt_idx], best_start_err, best_end_err)
            )

    return matched


def score_interval_recall(
    predictions: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    tol_s: float = 2.0,
    n_cases: int = 1,
    allow_unverified: bool = False,
) -> ScoreCard:
    """Computes recall for continuous interval detection within boundary tolerance."""
    mix, is_unverified, caveat = _analyze_provenance(ground_truth, allow_unverified=allow_unverified)
    n_gt = len(ground_truth)
    if n_gt == 0:
        val = 1.0 if not predictions else 0.0
    else:
        matched = _match_intervals(predictions, ground_truth, tol_s=tol_s)
        val = len(matched) / n_gt

    return ScoreCard(
        metric_name="Interval Recall",
        value=round(val, 4),
        n_cases=n_cases,
        n_items=n_gt,
        provenance_mix=mix,
        is_unverified=is_unverified,
        caveat=caveat,
    )


def score_interval_precision(
    predictions: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    tol_s: float = 2.0,
    n_cases: int = 1,
    allow_unverified: bool = False,
) -> ScoreCard:
    """Computes precision for continuous interval detection within boundary tolerance."""
    mix, is_unverified, caveat = _analyze_provenance(ground_truth, allow_unverified=allow_unverified)
    n_pred = len(predictions)
    if n_pred == 0:
        val = 1.0 if not ground_truth else 0.0
    else:
        matched = _match_intervals(predictions, ground_truth, tol_s=tol_s)
        val = len(matched) / n_pred

    return ScoreCard(
        metric_name="Interval Precision",
        value=round(val, 4),
        n_cases=n_cases,
        n_items=len(ground_truth),
        provenance_mix=mix,
        is_unverified=is_unverified,
        caveat=caveat,
    )


def score_interval_f1(
    predictions: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    tol_s: float = 2.0,
    n_cases: int = 1,
    allow_unverified: bool = False,
) -> ScoreCard:
    """Computes harmonic mean F1 score for continuous interval detection (e.g., CCIs)."""
    mix, is_unverified, caveat = _analyze_provenance(ground_truth, allow_unverified=allow_unverified)
    matched = _match_intervals(predictions, ground_truth, tol_s=tol_s)
    n_gt = len(ground_truth)
    n_pred = len(predictions)

    if n_gt == 0 and n_pred == 0:
        val = 1.0
    elif n_gt == 0 or n_pred == 0:
        val = 0.0
    else:
        recall = len(matched) / n_gt
        precision = len(matched) / n_pred
        if recall + precision == 0.0:
            val = 0.0
        else:
            val = 2.0 * (precision * recall) / (precision + recall)

    return ScoreCard(
        metric_name="CCI F1",
        value=round(val, 4),
        n_cases=n_cases,
        n_items=n_gt,
        provenance_mix=mix,
        is_unverified=is_unverified,
        caveat=caveat,
    )


def score_boundary_mae(
    predictions: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    tol_s: float = 2.0,
    n_cases: int = 1,
    allow_unverified: bool = False,
) -> ScoreCard:
    """Computes Mean Absolute Error (MAE) in seconds across start and end boundaries."""
    mix, is_unverified, caveat = _analyze_provenance(ground_truth, allow_unverified=allow_unverified)
    matched = _match_intervals(predictions, ground_truth, tol_s=tol_s)

    if not matched:
        val = 0.0
    else:
        errors = []
        for _, _, s_err, e_err in matched:
            errors.append(s_err)
            errors.append(e_err)
        val = sum(errors) / len(errors)

    return ScoreCard(
        metric_name="Boundary MAE",
        value=round(val, 4),
        n_cases=n_cases,
        n_items=len(matched),
        provenance_mix=mix,
        is_unverified=is_unverified,
        caveat=caveat,
    )


def score_ocr_accuracy(
    predictions: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    n_cases: int = 1,
    allow_unverified: bool = False,
) -> ScoreCard:
    """Computes exact numeric match accuracy for monitor OCR readings."""
    mix, is_unverified, caveat = _analyze_provenance(ground_truth, allow_unverified=allow_unverified)
    if not ground_truth:
        val = 1.0 if not predictions else 0.0
    else:
        correct = 0
        for idx, gt in enumerate(ground_truth):
            gt_hr = gt.get("heart_rate_bpm")
            gt_sbp = gt.get("sbp_mmHg")
            if idx < len(predictions):
                pred = predictions[idx]
                if pred.get("heart_rate_bpm") == gt_hr and pred.get("sbp_mmHg") == gt_sbp:
                    correct += 1
        val = correct / len(ground_truth)

    return ScoreCard(
        metric_name="OCR Accuracy",
        value=round(val, 4),
        n_cases=n_cases,
        n_items=len(ground_truth),
        provenance_mix=mix,
        is_unverified=is_unverified,
        caveat=caveat,
    )


def score_wer(
    hypothesis_tokens: list[str],
    reference_tokens: list[str],
    n_cases: int = 1,
    provenance: str = "human",
    allow_unverified: bool = False,
) -> ScoreCard:
    """Computes Word Error Rate (WER) using Levenshtein distance on token lists."""
    dummy_item = {"provenance": provenance}
    mix, is_unverified, caveat = _analyze_provenance([dummy_item], allow_unverified=allow_unverified)

    if not reference_tokens:
        val = 0.0 if not hypothesis_tokens else 1.0
    else:
        # Compute Levenshtein distance
        r_len = len(reference_tokens)
        h_len = len(hypothesis_tokens)
        dp = [[0] * (h_len + 1) for _ in range(r_len + 1)]
        for i in range(r_len + 1):
            dp[i][0] = i
        for j in range(h_len + 1):
            dp[0][j] = j
        for i in range(1, r_len + 1):
            for j in range(1, h_len + 1):
                cost = 0 if reference_tokens[i - 1] == hypothesis_tokens[j - 1] else 1
                dp[i][j] = min(
                    dp[i - 1][j] + 1,      # deletion
                    dp[i][j - 1] + 1,      # insertion
                    dp[i - 1][j - 1] + cost,  # substitution
                )
        val = dp[r_len][h_len] / r_len

    return ScoreCard(
        metric_name="WER",
        value=round(val, 4),
        n_cases=n_cases,
        n_items=len(reference_tokens),
        provenance_mix=mix,
        is_unverified=is_unverified,
        caveat=caveat,
    )


def score_der(
    hypothesis_diarization: list[dict[str, Any]],
    reference_diarization: list[dict[str, Any]],
    n_cases: int = 1,
    allow_unverified: bool = False,
) -> ScoreCard:
    """Computes Diarization Error Rate (DER) for speaker attribution segments."""
    mix, is_unverified, caveat = _analyze_provenance(reference_diarization, allow_unverified=allow_unverified)
    if not reference_diarization:
        val = 0.0 if not hypothesis_diarization else 1.0
    else:
        correct_dur = 0.0
        total_dur = 0.0
        for ref in reference_diarization:
            r_start = float(ref.get("t_start_s", 0.0))
            r_end = float(ref.get("t_end_s", 0.0))
            dur = max(0.0, r_end - r_start)
            total_dur += dur
            for hyp in hypothesis_diarization:
                h_start = float(hyp.get("t_start_s", 0.0))
                h_end = float(hyp.get("t_end_s", 0.0))
                if ref.get("speaker_id") == hyp.get("speaker_id"):
                    ov_start = max(r_start, h_start)
                    ov_end = min(r_end, h_end)
                    if ov_end > ov_start:
                        correct_dur += ov_end - ov_start
        val = max(0.0, 1.0 - (correct_dur / total_dur)) if total_dur > 0.0 else 0.0

    return ScoreCard(
        metric_name="DER",
        value=round(val, 4),
        n_cases=n_cases,
        n_items=len(reference_diarization),
        provenance_mix=mix,
        is_unverified=is_unverified,
        caveat=caveat,
    )


def score_all_targets(
    predictions: dict[str, Any],
    ground_truth: dict[str, Any],
    tol_s: float = 2.0,
    n_cases: int = 1,
    allow_unverified: bool = False,
) -> dict[str, ScoreCard]:
    """
    Scores a complete case dictionary across all target evaluation metrics.
    Returns a dictionary mapping metric names to immutable ScoreCard objects.
    """
    pred_shocks = predictions.get("shocks", [])
    gt_shocks = ground_truth.get("shocks", [])

    pred_ccis = predictions.get("ccis", [])
    gt_ccis = ground_truth.get("ccis", [])

    pred_ocr = predictions.get("ocr_readings", [])
    gt_ocr = ground_truth.get("ocr_readings", [])

    return {
        "event_recall": score_event_recall(pred_shocks, gt_shocks, tol_s=tol_s, n_cases=n_cases, allow_unverified=allow_unverified),
        "event_precision": score_event_precision(pred_shocks, gt_shocks, tol_s=tol_s, n_cases=n_cases, allow_unverified=allow_unverified),
        "event_f1": score_event_f1(pred_shocks, gt_shocks, tol_s=tol_s, n_cases=n_cases, allow_unverified=allow_unverified),
        "event_timing_mae": score_event_timing_mae(pred_shocks, gt_shocks, tol_s=tol_s, n_cases=n_cases, allow_unverified=allow_unverified),
        "interval_recall": score_interval_recall(pred_ccis, gt_ccis, tol_s=tol_s, n_cases=n_cases, allow_unverified=allow_unverified),
        "interval_precision": score_interval_precision(pred_ccis, gt_ccis, tol_s=tol_s, n_cases=n_cases, allow_unverified=allow_unverified),
        "interval_f1": score_interval_f1(pred_ccis, gt_ccis, tol_s=tol_s, n_cases=n_cases, allow_unverified=allow_unverified),
        "boundary_mae": score_boundary_mae(pred_ccis, gt_ccis, tol_s=tol_s, n_cases=n_cases, allow_unverified=allow_unverified),
        "ocr_accuracy": score_ocr_accuracy(pred_ocr, gt_ocr, n_cases=n_cases, allow_unverified=allow_unverified),
    }
