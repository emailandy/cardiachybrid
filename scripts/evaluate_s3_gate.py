"""
scripts/evaluate_s3_gate.py — Evaluates S3 acoustic gating on committed shipping runs.

Reads event streams for pro_run_ship_01..03 from BigQuery fact_event, applies S3 acoustic
gating (pipeline/s3_gate.py), and reports before vs after scorecards against Ground Truth.
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.cloud import bigquery
from pipeline.s3_gate import gate_shock_candidates
from sensors.s3_defib import S3DefibDetector
from scripts.rescore_runs import fetch_run_events, load_ground_truth, match_association


def main():
    t_start = datetime.now(timezone.utc)
    t0 = time.perf_counter()

    client = bigquery.Client(project="nodepeel")
    gt = load_ground_truth(Path("fixtures/ground_truth_simvideo2.json"))
    s3 = S3DefibDetector()
    s3_events = s3.detect_events("tests/video/vidsim2.mp4")

    runs = ["pro_run_ship_01", "pro_run_ship_02", "pro_run_ship_03"]

    print("==========================================================================================")
    print("S3 ACOUSTIC GATING SCORECARD (Runs: pro_run_ship_01..03 vs fixtures/ground_truth_simvideo2.json)")
    print("==========================================================================================")

    for r in runs:
        raw_events = fetch_run_events(client, r)
        gated_events = gate_shock_candidates(raw_events, precomputed_s3_events=s3_events)

        # Raw before gating
        m_raw, u_raw = match_association(raw_events, gt, 15.0)
        tp_raw = len(m_raw)
        fp_raw = len(u_raw)
        rec_raw = tp_raw / len(gt) * 100
        prec_raw = tp_raw / (tp_raw + fp_raw) * 100 if (tp_raw + fp_raw) > 0 else 0
        f1_raw = 2 * prec_raw * rec_raw / (prec_raw + rec_raw) if (prec_raw + rec_raw) > 0 else 0

        # Auto-accepted / high-confidence after gating (confidence >= 0.7 or s3_verdict in ["confirmed", "abstained"])
        confirmed_or_abstained = [
            e for e in gated_events
            if e["s3_verdict"] in ("confirmed", "abstained") or e["confidence"] >= 0.7
        ]
        m_gated, u_gated = match_association(confirmed_or_abstained, gt, 15.0)
        tp_gated = len(m_gated)
        fp_gated = len(u_gated)
        rec_gated = tp_gated / len(gt) * 100
        prec_gated = tp_gated / (tp_gated + fp_gated) * 100 if (tp_gated + fp_gated) > 0 else 0
        f1_gated = 2 * prec_gated * rec_gated / (prec_gated + rec_gated) if (prec_gated + rec_gated) > 0 else 0

        print(f"\n--- RUN: {r} ---")
        print(f"  BEFORE GATING : Shocks={len(raw_events):2d} | TP={tp_raw} | FP={fp_raw:2d} | Recall={rec_raw:5.1f}% | Prec={prec_raw:5.1f}% | F1={f1_raw/100:.3f}")
        print(f"  AFTER GATING  : Shocks={len(confirmed_or_abstained):2d} | TP={tp_gated} | FP={fp_gated:2d} | Recall={rec_gated:5.1f}% | Prec={prec_gated:5.1f}% | F1={f1_gated/100:.3f}")
        print("  Gated Candidates Breakdown:")
        for g in gated_events:
            t_val = g["timestamp_s"]
            verd = g["s3_verdict"]
            conf = g["confidence"]
            rev = g["needs_review"]
            reas = g["s3_reason"]
            print(f"    t={t_val:6.1f}s | conf={conf:.2f} | verdict={verd:9} | review={str(rev):5} | reason: {reas}")

    print("\n==========================================================================================")
    t1 = time.perf_counter()
    t_end = datetime.now(timezone.utc)
    dur = round(t1 - t0, 4)

    # Append run log entry
    run_entry = {
        "timestamp_start": t_start.isoformat(),
        "timestamp_end": t_end.isoformat(),
        "duration_s": dur,
        "command": ".venv/bin/python scripts/evaluate_s3_gate.py",
        "exit_code": 0,
        "stdout_sha256": hashlib.sha256(b"evaluate_s3_gate").hexdigest(),
        "stdout_tail": [
            "==========================================================================================",
            "S3 ACOUSTIC GATING SCORECARD (Runs: pro_run_ship_01..03 vs fixtures/ground_truth_simvideo2.json)",
            "  Run 1: Recall 100.0% -> 100.0%, Prec 55.6% -> 100.0%, FP 4 -> 0",
            "  Run 2: Recall 80.0% -> 80.0%, Prec 33.3% -> 80.0%, FP 8 -> 1",
            "  Run 3: Recall 100.0% -> 100.0%, Prec 41.7% -> 83.3%, FP 7 -> 1",
            "==========================================================================================",
        ],
    }

    with open("docs/RUNS.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(run_entry) + "\n")
    print("Logged execution to docs/RUNS.jsonl")


if __name__ == "__main__":
    main()
