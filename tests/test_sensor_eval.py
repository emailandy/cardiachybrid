"""
Unit tests for sensor evaluation metrics, calibration harness, and reporting (S00).
Verifies:
1. All evaluation metrics (recall, precision, f1, timing MAE, boundary MAE, OCR, WER, DER).
2. Provenance mix reporting and unverified ground-truth refusal (Q-017).
3. Minimum case count guard (n >= 5) in CalibrationHarness (Q-017).
4. Scorecard formatting with explicit provenance labeling.
"""

import pytest
from typing import Any
from sensors.eval.metrics import (
    ScoreCard,
    score_event_recall,
    score_event_precision,
    score_event_f1,
    score_event_timing_mae,
    score_interval_recall,
    score_interval_precision,
    score_interval_f1,
    score_boundary_mae,
    score_ocr_accuracy,
    score_wer,
    score_der,
    score_all_targets,
)
from sensors.eval.report import format_scorecard_line, format_scorecard_report
from sensors.eval.calibrate import CalibrationHarness


def test_event_metrics_hand_built_fixture() -> None:
    gt_shocks = [
        {"timestamp_s": 100.0, "provenance": "acoustic_confirmed"},
        {"timestamp_s": 200.0, "provenance": "acoustic_confirmed"},
        {"timestamp_s": 300.0, "provenance": "acoustic_confirmed"},
        {"timestamp_s": 400.0, "provenance": "acoustic_confirmed"},
    ]
    pred_shocks = [
        {"timestamp_s": 100.5},  # Match err 0.5s
        {"timestamp_s": 201.0},  # Match err 1.0s
        {"timestamp_s": 299.5},  # Match err 0.5s
        {"timestamp_s": 500.0},  # False positive
    ]

    recall = score_event_recall(pred_shocks, gt_shocks, tol_s=2.0)
    precision = score_event_precision(pred_shocks, gt_shocks, tol_s=2.0)
    f1 = score_event_f1(pred_shocks, gt_shocks, tol_s=2.0)
    mae = score_event_timing_mae(pred_shocks, gt_shocks, tol_s=2.0)

    assert recall.value == 0.75  # 3 of 4 GT matched
    assert precision.value == 0.75  # 3 of 4 pred matched
    assert f1.value == 0.75
    assert mae.value == pytest.approx((0.5 + 1.0 + 0.5) / 3.0, 0.001)
    assert "ALL acoustic_confirmed" in recall.caveat
    assert not recall.is_unverified


def test_interval_metrics_hand_built_fixture() -> None:
    gt_ccis = [
        {"start_s": 10.0, "end_s": 20.0, "provenance": "block_probe_unverified"},
        {"start_s": 30.0, "end_s": 45.0, "provenance": "block_probe_unverified"},
        {"start_s": 60.0, "end_s": 70.0, "provenance": "block_probe_unverified"},
    ]
    pred_ccis = [
        {"start_s": 10.5, "end_s": 19.5},  # Start err 0.5, end err 0.5
        {"start_s": 30.0, "end_s": 46.0},  # Start err 0.0, end err 1.0
        {"start_s": 60.0, "end_s": 70.0},  # Exact match err 0.0
    ]

    f1 = score_interval_f1(pred_ccis, gt_ccis, tol_s=2.0, allow_unverified=True)
    b_mae = score_boundary_mae(pred_ccis, gt_ccis, tol_s=2.0, allow_unverified=True)

    assert f1.value == 1.0
    # Boundary errors: 0.5, 0.5, 0.0, 1.0, 0.0, 0.0 -> sum 2.0 / 6 = 0.3333
    assert b_mae.value == pytest.approx(0.3333, 0.001)
    assert "ALL block_probe_unverified" in f1.caveat
    assert f1.is_unverified


def test_unverified_provenance_refusal() -> None:
    gt_unverified = [
        {"start_s": 10.0, "end_s": 20.0, "provenance": "block_probe_unverified"},
    ]
    with pytest.raises(ValueError, match="Refusing to compute formal accuracy metric.*Q-017"):
        score_interval_f1([], gt_unverified, allow_unverified=False)


def test_ocr_wer_der_metrics() -> None:
    gt_ocr = [
        {"heart_rate_bpm": 80, "sbp_mmHg": 120, "provenance": "human"},
        {"heart_rate_bpm": 90, "sbp_mmHg": 130, "provenance": "human"},
    ]
    pred_ocr = [
        {"heart_rate_bpm": 80, "sbp_mmHg": 120},
        {"heart_rate_bpm": 90, "sbp_mmHg": 125},  # SBP mismatch
    ]
    ocr_card = score_ocr_accuracy(pred_ocr, gt_ocr)
    assert ocr_card.value == 0.5
    assert not ocr_card.is_unverified

    wer_card = score_wer(["patient", "in", "vf"], ["patient", "is", "in", "vf"])
    assert wer_card.value == pytest.approx(0.25, 0.01)

    gt_der = [{"speaker_id": "spk1", "t_start_s": 0.0, "t_end_s": 10.0, "provenance": "human"}]
    pred_der = [{"speaker_id": "spk1", "t_start_s": 0.0, "t_end_s": 8.0}]
    der_card = score_der(pred_der, gt_der)
    assert der_card.value == pytest.approx(0.20, 0.01)


def test_score_all_targets() -> None:
    gt: dict[str, Any] = {
        "shocks": [{"timestamp_s": 100.0, "provenance": "acoustic_confirmed"}],
        "ccis": [{"start_s": 10.0, "end_s": 20.0, "provenance": "block_probe_unverified"}],
        "ocr_readings": [],
    }
    pred: dict[str, Any] = {
        "shocks": [{"timestamp_s": 100.0}],
        "ccis": [{"start_s": 10.0, "end_s": 20.0}],
        "ocr_readings": [],
    }
    cards = score_all_targets(pred, gt, allow_unverified=True)
    expected_keys = {
        "event_recall",
        "event_precision",
        "event_f1",
        "event_timing_mae",
        "interval_recall",
        "interval_precision",
        "interval_f1",
        "boundary_mae",
        "ocr_accuracy",
    }
    assert set(cards.keys()) == expected_keys
    assert cards["event_f1"].value == 1.0
    assert cards["interval_f1"].value == 1.0
    assert cards["interval_f1"].is_unverified


def test_report_provenance_labeling() -> None:
    card = ScoreCard(
        metric_name="CCI F1",
        value=0.83,
        n_cases=1,
        n_items=3,
        provenance_mix={"block_probe_unverified": 3},
        is_unverified=True,
        caveat="ALL block_probe_unverified",
    )
    line = format_scorecard_line(card)
    assert line == "CCI F1               0.83   n=1 case, 3 intervals    ⚠ ALL block_probe_unverified"
    report = format_scorecard_report([card])
    assert "=== Sensor Evaluation Scorecard ===" in report
    assert line in report


def test_calibration_harness_n_less_than_5_refusal() -> None:
    dummy_cases = [{"shocks": []}] * 4  # n = 4 cases (< 5)
    candidate_thresholds = [{"th": 0.5}]

    def _dummy_score(cases: Any, gt: Any, th: Any) -> ScoreCard:
        return ScoreCard("test", 1.0, 1, 1, {}, False, "")

    with pytest.raises(ValueError, match="Calibration refused: n=4 cases provided.*minimum n=5 required.*Q-017"):
        CalibrationHarness.calibrate_thresholds(dummy_cases, candidate_thresholds, _dummy_score)


def test_calibration_harness_valid() -> None:
    dummy_cases = [{"id": i} for i in range(5)]  # n = 5 cases
    candidate_thresholds = [{"th": 0.2}, {"th": 0.8}]

    def _dummy_score(cases: Any, gt: Any, th: dict[str, Any]) -> ScoreCard:
        val = 1.0 if th["th"] == 0.8 else 0.5
        return ScoreCard("test", val, len(cases), 1, {}, False, "")

    best_th, best_card = CalibrationHarness.calibrate_thresholds(
        dummy_cases, candidate_thresholds, _dummy_score
    )
    assert best_th == {"th": 0.8}
    assert best_card.value == 1.0


def test_monotonic_matching_no_cascade_clean() -> None:
    """30 intervals at 20s spacing in truth, same 30 in pred shifted +0.3s -> 30 pairs, 0 orphans, F1 = 1.0."""
    gt_ccis = [
        {"start_s": i * 20.0, "end_s": i * 20.0 + 10.0, "provenance": "human"}
        for i in range(30)
    ]
    pred_ccis = [
        {"start_s": i * 20.0 + 0.3, "end_s": i * 20.0 + 10.3} for i in range(30)
    ]

    recall = score_interval_recall(pred_ccis, gt_ccis, tol_s=1.0)
    precision = score_interval_precision(pred_ccis, gt_ccis, tol_s=1.0)
    f1 = score_interval_f1(pred_ccis, gt_ccis, tol_s=1.0)

    assert recall.value == 1.0
    assert precision.value == 1.0
    assert f1.value == 1.0


def test_monotonic_matching_no_cascade_dropped_index_15() -> None:
    """Drop truth[15] -> 29 pairs, exactly 1 orphan in pred, no cascade after index 15."""
    gt_ccis = [
        {"start_s": i * 20.0, "end_s": i * 20.0 + 10.0, "provenance": "human"}
        for i in range(30)
        if i != 15
    ]
    pred_ccis = [
        {"start_s": i * 20.0 + 0.3, "end_s": i * 20.0 + 10.3} for i in range(30)
    ]

    recall = score_interval_recall(pred_ccis, gt_ccis, tol_s=1.0)
    precision = score_interval_precision(pred_ccis, gt_ccis, tol_s=1.0)

    # 29 matched out of 29 GT -> recall = 1.0
    # 29 matched out of 30 pred (1 orphan: pred[15]) -> precision = 29/30 = 0.9667
    assert recall.value == 1.0
    assert precision.value == pytest.approx(29.0 / 30.0, 0.0001)


def test_scorecard_metric_discrimination() -> None:
    """Verifies that scorecard metrics discriminate deliberately wrong predictions (not scoring 1.0/0.0)."""
    gt_ccis = [
        {"start_s": i * 20.0, "end_s": i * 20.0 + 10.0, "provenance": "block_probe_unverified"}
        for i in range(8)
    ]
    # 1. Shift every interval +3.0s -> boundary MAE should be 3.0
    pred_shifted = [
        {"start_s": float(iv["start_s"]) + 3.0, "end_s": float(iv["end_s"]) + 3.0}
        for iv in gt_ccis
    ]
    mae_card = score_boundary_mae(pred_shifted, gt_ccis, tol_s=5.0, allow_unverified=True)
    assert mae_card.value == pytest.approx(3.0, 0.001)

    # 2. Drop two intervals -> recall drops to 6/8 = 0.75, precision holds at 1.0
    pred_dropped = gt_ccis[:-2]
    r_card = score_interval_recall(pred_dropped, gt_ccis, tol_s=1.0, allow_unverified=True)
    p_card = score_interval_precision(pred_dropped, gt_ccis, tol_s=1.0, allow_unverified=True)
    assert r_card.value == pytest.approx(0.75, 0.001)
    assert p_card.value == 1.0

    # 3. Add two spurious intervals -> recall holds at 1.0, precision drops to 8/10 = 0.80
    pred_spurious = list(gt_ccis) + [
        {"start_s": 500.0, "end_s": 510.0},
        {"start_s": 600.0, "end_s": 610.0},
    ]
    r_spur_card = score_interval_recall(pred_spurious, gt_ccis, tol_s=1.0, allow_unverified=True)
    p_spur_card = score_interval_precision(pred_spurious, gt_ccis, tol_s=1.0, allow_unverified=True)
    assert r_spur_card.value == 1.0
    assert p_spur_card.value == pytest.approx(0.80, 0.001)


def test_self_comparison_guard_f016() -> None:
    """
    Verifies F-016: Any metric computed where prediction and ground truth share a
    source must be labelled SELF-COMPARISON and cannot be reported as performance.
    """
    data = [{"timestamp_s": 10.0, "provenance": "probe_verified"}]
    card = score_event_recall(data, data, allow_unverified=True)
    assert card.caveat == "⚠ SELF-COMPARISON"

