#!/usr/bin/env python3
"""
scripts/rescore_runs.py

Re-scores existing committed runs (pro_run_01, pro_run_02, pro_run_03) against
fixtures/ground_truth_simvideo2.json.

Separates detection accuracy (association window) from timestamping error (signed dt),
and evaluates multi-tolerance matching (+/-2.0s, +/-3.0s, +/-5.0s) using
monotonic order-preserving matcher from sensors/eval/metrics.py.

Guarantees:
  Reported FP count == len(enumerated FP list)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.cloud import bigquery
from sensors.eval.metrics import _match_events


def load_ground_truth(gt_path: Path) -> list[dict[str, Any]]:
    data = json.loads(gt_path.read_text(encoding="utf-8"))
    shocks = []
    for s in data.get("shocks", []):
        shocks.append({
            "timestamp_s": float(s["timestamp_s"]),
            "provenance": s.get("provenance", "human_adjudicated"),
            "acoustic_measured": s.get("acoustic_measured"),
        })
    return sorted(shocks, key=lambda x: x["timestamp_s"])


def fetch_run_events(client: bigquery.Client, run_id: str) -> list[dict[str, Any]]:
    q = f"""
    SELECT event_id, event_type, timestamp_s, confidence, attributes
    FROM `nodepeel.resus_raw.fact_event`
    WHERE run_id = '{run_id}' AND event_type = 'defibrillation_shock'
    ORDER BY timestamp_s ASC
    """
    rows = client.query(q).result()
    events = []
    for r in rows:
        events.append({
            "event_id": r.event_id,
            "event_type": r.event_type,
            "timestamp_s": float(r.timestamp_s),
            "confidence": float(r.confidence) if r.confidence is not None else 1.0,
            "attributes": json.loads(r.attributes) if r.attributes else {},
        })
    return events


def match_association(
    predictions: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    association_window_s: float,
) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
    """
    Associates predictions to ground truth within association_window_s.
    Returns:
      associated: map from GT index (0..n-1) to matched prediction dict with signed_dt and abs_dt
      unmatched_preds: list of prediction dicts not associated with any GT shock
    """
    matched_gt: dict[int, dict[str, Any]] = {}
    matched_pred_ids = set()

    sorted_pred = sorted(predictions, key=lambda x: x["timestamp_s"])
    sorted_gt = sorted(ground_truth, key=lambda x: x["timestamp_s"])

    for g_idx, gt in enumerate(sorted_gt):
        gt_t = gt["timestamp_s"]
        best_p = None
        best_err = float("inf")
        for p in sorted_pred:
            if p["event_id"] in matched_pred_ids:
                continue
            err = abs(p["timestamp_s"] - gt_t)
            if err <= association_window_s and err < best_err:
                best_err = err
                best_p = p

        if best_p is not None:
            matched_pred_ids.add(best_p["event_id"])
            signed_dt = best_p["timestamp_s"] - gt_t
            matched_gt[g_idx] = {
                "pred": best_p,
                "signed_dt": signed_dt,
                "abs_dt": abs(signed_dt),
            }

    unmatched_preds = [p for p in sorted_pred if p["event_id"] not in matched_pred_ids]
    return matched_gt, unmatched_preds


def rescore_run(
    run_id: str,
    predictions: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    association_window_s: float,
    tolerances: list[float],
) -> dict[str, Any]:
    n_gt = len(ground_truth)
    n_pred = len(predictions)

    # 1. Association matching
    associated, unmatched_preds = match_association(predictions, ground_truth, association_window_s)
    tp_assoc = len(associated)
    fp_assoc = len(unmatched_preds)
    fn_assoc = n_gt - tp_assoc
    rec_assoc = tp_assoc / n_gt if n_gt > 0 else 0.0
    prec_assoc = tp_assoc / n_pred if n_pred > 0 else 0.0
    f1_assoc = 2 * prec_assoc * rec_assoc / (prec_assoc + rec_assoc) if (prec_assoc + rec_assoc) > 0 else 0.0

    # Timestamp errors
    abs_dts = [m["abs_dt"] for m in associated.values()]
    signed_dts = [m["signed_dt"] for m in associated.values()]
    mean_abs_dt = sum(abs_dts) / len(abs_dts) if abs_dts else 0.0
    sorted_abs = sorted(abs_dts)
    median_abs_dt = sorted_abs[len(sorted_abs) // 2] if sorted_abs else 0.0
    max_abs_dt = max(abs_dts) if abs_dts else 0.0

    # 2. Strict tolerance matching using monotonic matcher
    tol_scores = {}
    for tol in tolerances:
        matched_pairs = _match_events(predictions, ground_truth, tol_s=tol)
        tp = len(matched_pairs)
        fp = n_pred - tp
        fn = n_gt - tp
        rec = tp / n_gt if n_gt > 0 else 0.0
        prec = tp / n_pred if n_pred > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        tol_scores[f"{tol:.1f}s"] = {
            "tol_s": tol,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "recall": round(rec, 4),
            "precision": round(prec, 4),
            "f1": round(f1, 4),
            "matches": [(p.get("timestamp_s"), g.get("timestamp_s"), round(err, 2)) for p, g, err in matched_pairs],
        }

    return {
        "run_id": run_id,
        "n_predictions": n_pred,
        "n_ground_truth": n_gt,
        "association": {
            "window_s": association_window_s,
            "tp": tp_assoc,
            "fp": fp_assoc,
            "fn": fn_assoc,
            "recall": round(rec_assoc, 4),
            "precision": round(prec_assoc, 4),
            "f1": round(f1_assoc, 4),
            "mean_abs_dt": round(mean_abs_dt, 2),
            "median_abs_dt": round(median_abs_dt, 2),
            "max_abs_dt": round(max_abs_dt, 2),
            "associated": associated,
            "unmatched_predictions": unmatched_preds,
        },
        "tolerance_scores": tol_scores,
    }


def main():
    parser = argparse.ArgumentParser(description="Re-score committed Pro runs against ground truth.")
    parser.add_argument("--gt", default="fixtures/ground_truth_simvideo2.json", help="Path to ground truth JSON")
    parser.add_argument("--association-window", type=float, required=True, help="Association window in seconds (e.g. 15.0)")
    parser.add_argument("--tolerances", type=float, nargs="+", required=True, help="Strict matching tolerances in seconds (e.g. 2.0 3.0 5.0)")
    parser.add_argument("--project", default="nodepeel", help="BigQuery project ID")
    parser.add_argument("--runs", nargs="+", default=["pro_run_01", "pro_run_02", "pro_run_03"], help="Run IDs to score")
    args = parser.parse_args()

    gt_path = Path(args.gt)
    if not gt_path.exists():
        print(f"Error: GT path '{gt_path}' not found.", file=sys.stderr)
        sys.exit(1)

    ground_truth = load_ground_truth(gt_path)
    client = bigquery.Client(project=args.project)

    results = []
    for r_id in args.runs:
        preds = fetch_run_events(client, r_id)
        res = rescore_run(
            run_id=r_id,
            predictions=preds,
            ground_truth=ground_truth,
            association_window_s=args.association_window,
            tolerances=args.tolerances,
        )
        results.append(res)

    print("\n" + "=" * 90)
    print(f"RE-SCORING REPORT: PRO-MODEL EXTRACTION RUNS (n=3 runs, n={len(ground_truth)} gold shocks)")
    print(f"Ground Truth: {gt_path} | Association Window: ±{args.association_window:.1f}s")
    print("=" * 90)

    # 1. PER-SHOCK ATTRIBUTION TABLE
    print("\n--- TABLE 1: PER-SHOCK DETECTION & TIMESTAMP ERROR (signed dt = t_pred - t_gt) ---")
    header = f"{'Gold Shock':<12} | {'Acoustic':<10} | " + " | ".join([f"{r['run_id']:<20}" for r in results])
    print(header)
    print("-" * len(header))

    for g_idx, gt in enumerate(ground_truth):
        gt_t = gt["timestamp_s"]
        ac_t = f"{gt['acoustic_measured']:.1f}s" if gt["acoustic_measured"] is not None else "uncharged"
        row_str = f"#{g_idx+1} ({gt_t:5.1f}s)  | {ac_t:<10} | "
        cols = []
        for r in results:
            assoc = r["association"]["associated"].get(g_idx)
            if assoc:
                p_t = assoc["pred"]["timestamp_s"]
                s_dt = assoc["signed_dt"]
                cols.append(f"t={p_t:5.1f}s ({s_dt:+5.1f}s)")
            else:
                cols.append(f"{'MISSED':<20}")
        row_str += " | ".join(cols)
        print(row_str)

    # 2. ENUMERATED FALSE POSITIVES PER RUN
    print("\n--- TABLE 2: ENUMERATED UNASSOCIATED DETECTIONS (FALSE POSITIVES) ---")
    for r in results:
        fps = r["association"]["unmatched_predictions"]
        fp_strs = [f"t={p['timestamp_s']:.1f}s (conf={p['confidence']})" for p in fps]
        print(f"{r['run_id']} (FP count = {len(fps)}): {', '.join(fp_strs) if fp_strs else 'None (0 FP)'}")
        assert len(fps) == r["association"]["fp"], f"Integrity error: enumerated FP {len(fps)} != reported FP {r['association']['fp']}"

    # 3. DETECTION ACCURACY (Association Window)
    print(f"\n--- TABLE 3: DETECTION ACCURACY (Association Window ±{args.association_window:.1f}s) ---")
    print(f"{'Run ID':<12} | {'Shocks':<8} | {'TP':<4} | {'FP':<4} | {'FN':<4} | {'Recall':<8} | {'Precision':<10} | {'F1':<6} | {'|dt| Mean':<10} | {'|dt| Med':<10} | {'|dt| Max':<10}")
    print("-" * 105)
    for r in results:
        a = r["association"]
        print(f"{r['run_id']:<12} | {r['n_predictions']:<8} | {a['tp']:<4} | {a['fp']:<4} | {a['fn']:<4} | {a['recall']:<8.1%} | {a['precision']:<10.1%} | {a['f1']:<6.3f} | {a['mean_abs_dt']:<10.2f}s | {a['median_abs_dt']:<10.2f}s | {a['max_abs_dt']:<10.2f}s")

    # 4. STRICT TOLERANCE MATCHING
    print(f"\n--- TABLE 4: STRICT TOLERANCE MATCHING (Order-Preserving Monotonic Matcher) ---")
    for tol in args.tolerances:
        tol_key = f"{tol:.1f}s"
        print(f"\nTolerance ±{tol_key}:")
        print(f"{'Run ID':<12} | {'TP':<4} | {'FP':<4} | {'FN':<4} | {'Recall':<8} | {'Precision':<10} | {'F1':<6} | Matched Pairs (pred_t, gt_t, error)")
        print("-" * 85)
        for r in results:
            ts = r["tolerance_scores"][tol_key]
            pairs_str = ", ".join([f"({p:.1f}s, {g:.1f}s, {e:.1f}s)" for p, g, e in ts["matches"]])
            print(f"{r['run_id']:<12} | {ts['tp']:<4} | {ts['fp']:<4} | {ts['fn']:<4} | {ts['recall']:<8.1%} | {ts['precision']:<10.1%} | {ts['f1']:<6.3f} | {pairs_str}")

    print("\n" + "=" * 90)


if __name__ == "__main__":
    main()
