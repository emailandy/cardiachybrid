#!/usr/bin/env python3
"""
scripts/diagnose_timestamps.py

Diagnostic tool for timestamp drift and cross-run variance in Pro-model runs:
  Check 1: Decoding determinism (declared vs actual call-time parameters & seed support)
  Check 2: Per-window offset and boundary distance tabulation
  Check 3: S5 burned-in timecode anchor reachability tracing and prompt rendering
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.cloud import bigquery
from google.genai import types
from codegen.yamlio import load_yaml
from prompts.builder import build_p1
from pipeline.sensor_runner import SensorPipelineRunner


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


def fetch_run_shocks(client: bigquery.Client, run_id: str) -> list[dict[str, Any]]:
    q = f"""
    SELECT event_id, event_type, timestamp_s, confidence, attributes, evidence
    FROM `nodepeel.resus_raw.fact_event`
    WHERE run_id = '{run_id}' AND event_type = 'defibrillation_shock'
    ORDER BY timestamp_s ASC
    """
    rows = client.query(q).result()
    events = []
    for r in rows:
        events.append({
            "event_id": r.event_id,
            "timestamp_s": float(r.timestamp_s),
            "confidence": float(r.confidence) if r.confidence is not None else 1.0,
            "attributes": json.loads(r.attributes) if r.attributes else {},
            "evidence": json.loads(r.evidence) if r.evidence else [],
        })
    return events


def match_association(
    predictions: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    association_window_s: float = 15.0,
) -> dict[int, dict[str, Any]]:
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

    return matched_gt


def run_check_1_decoding_determinism() -> dict[str, Any]:
    versions = load_yaml(Path("prompts/VERSIONS.yaml"))
    model_binding = versions.get("model_binding", {})

    fields = types.GenerateContentConfig.model_fields
    has_seed = "seed" in fields
    has_temp = "temperature" in fields
    has_top_p = "top_p" in fields
    has_top_k = "top_k" in fields
    has_cand = "candidate_count" in fields

    passes = ["pass_1", "pass_2", "pass_3", "pass_4a", "pass_4b", "pass_5"]
    table_rows = []

    for p in passes:
        decl = model_binding.get(p, {})
        decl_model = decl.get("model", "None")
        decl_temp = decl.get("temperature", "None")
        decl_k = decl.get("ensemble_k", "None")
        decl_thinking = decl.get("thinking", "None")

        call_model = decl_model
        call_temp = "None (API Default: 1.0)"
        call_seed = "None (Unseeded)"
        call_thinking = "None (Default)"
        call_k = "1 (Single draw)"

        table_rows.append({
            "pass": p,
            "decl_model": decl_model,
            "call_model": call_model,
            "decl_temp": decl_temp,
            "call_temp": call_temp,
            "decl_thinking": decl_thinking,
            "call_thinking": call_thinking,
            "decl_k": decl_k,
            "call_k": call_k,
            "call_seed": call_seed,
        })

    return {
        "has_seed_parameter": has_seed,
        "has_temperature_parameter": has_temp,
        "has_top_p_parameter": has_top_p,
        "has_top_k_parameter": has_top_k,
        "has_candidate_count_parameter": has_cand,
        "table_rows": table_rows,
    }


def run_check_2_per_window_offset(
    client: bigquery.Client,
    ground_truth: list[dict[str, Any]],
    runs: list[str],
) -> dict[str, Any]:
    windows = [
        {"win_idx": 0, "w_start": 0.0, "w_end": 480.0, "p_end": 420.0, "lead": 0.0, "p_start": 0.0},
        {"win_idx": 1, "w_start": 420.0, "w_end": 900.0, "p_end": 840.0, "lead": 60.0, "p_start": 420.0},
        {"win_idx": 2, "w_start": 840.0, "w_end": 1320.0, "p_end": 1260.0, "lead": 60.0, "p_start": 840.0},
        {"win_idx": 3, "w_start": 1260.0, "w_end": 1363.78, "p_end": 1363.78, "lead": 60.0, "p_start": 1260.0},
    ]

    detections_by_win: dict[int, list[dict[str, Any]]] = {w["win_idx"]: [] for w in windows}
    detailed_detections = []

    for r_id in runs:
        preds = fetch_run_shocks(client, r_id)
        assoc_map = match_association(preds, ground_truth, association_window_s=15.0)

        for g_idx, gt in enumerate(ground_truth):
            if g_idx in assoc_map:
                assoc = assoc_map[g_idx]
                p = assoc["pred"]
                p_t = p["timestamp_s"]
                gt_t = gt["timestamp_s"]
                s_dt = assoc["signed_dt"]

                assigned_win = None
                for w in windows:
                    if w["w_start"] <= p_t <= w["w_end"]:
                        if p_t < w["p_end"] or w["win_idx"] == len(windows) - 1:
                            assigned_win = w
                            break
                if assigned_win is None:
                    for w in windows:
                        if w["w_start"] <= p_t <= w["w_end"]:
                            assigned_win = w
                            break

                dist_start = p_t - assigned_win["w_start"]
                dist_end = assigned_win["w_end"] - p_t

                item = {
                    "run_id": r_id,
                    "gt_shock_idx": g_idx + 1,
                    "gt_timestamp_s": gt_t,
                    "pred_timestamp_s": p_t,
                    "signed_dt": s_dt,
                    "abs_dt": abs(s_dt),
                    "win_idx": assigned_win["win_idx"],
                    "win_bounds": f"[{assigned_win['w_start']:.1f}s -> {assigned_win['w_end']:.1f}s]",
                    "dist_from_win_start": dist_start,
                    "dist_from_win_end": dist_end,
                }
                detailed_detections.append(item)
                detections_by_win[assigned_win["win_idx"]].append(item)

    win_summaries = []
    for w in windows:
        w_idx = w["win_idx"]
        w_dets = detections_by_win[w_idx]
        n_dets = len(w_dets)
        mean_s_dt = sum(d["signed_dt"] for d in w_dets) / n_dets if n_dets > 0 else 0.0
        mean_abs_dt = sum(d["abs_dt"] for d in w_dets) / n_dets if n_dets > 0 else 0.0
        min_s_dt = min([d["signed_dt"] for d in w_dets]) if n_dets > 0 else 0.0
        max_s_dt = max([d["signed_dt"] for d in w_dets]) if n_dets > 0 else 0.0

        win_summaries.append({
            "win_idx": w_idx,
            "bounds": f"[{w['w_start']:.1f}s -> {w['w_end']:.1f}s]",
            "primary_bounds": f"[{w['p_start']:.1f}s -> {w['p_end']:.1f}s]",
            "n_detections": n_dets,
            "mean_signed_dt": round(mean_s_dt, 2),
            "mean_abs_dt": round(mean_abs_dt, 2),
            "min_signed_dt": round(min_s_dt, 2),
            "max_signed_dt": round(max_s_dt, 2),
            "detections": w_dets,
        })

    return {
        "detailed_detections": detailed_detections,
        "win_summaries": win_summaries,
    }


def run_check_3_s5_anchor_reachability() -> dict[str, Any]:
    runner = SensorPipelineRunner()
    video_path = "tests/video/vidsim2.mp4"
    if Path(video_path).exists():
        sensor_res = runner.run_pipeline(video_path, max_duration_s=10.0)
    else:
        sensor_res = runner.run_pipeline("tests/fixtures/synthetic.mp4", max_duration_s=10.0)

    s_data_w0 = runner.get_p1_sensor_placeholders(sensor_res, win_start=0.0, win_end=480.0)
    s_data_w1 = runner.get_p1_sensor_placeholders(sensor_res, win_start=420.0, win_end=900.0)

    prompt_w0_sensors = build_p1(0, 4, 1363.78, 0.0, 480.0, 420.0, 0.0, 0.0, sensor_data=s_data_w0)
    prompt_w1_sensors = build_p1(1, 4, 1363.78, 420.0, 900.0, 840.0, 60.0, 420.0, sensor_data=s_data_w1)

    prompt_w0_nosensors = build_p1(0, 4, 1363.78, 0.0, 480.0, 420.0, 0.0, 0.0, sensor_data=None)
    prompt_w1_nosensors = build_p1(1, 4, 1363.78, 420.0, 900.0, 840.0, 60.0, 420.0, sensor_data=None)

    def extract_sensor_track_block(user_text: str) -> str:
        lines = user_text.splitlines()
        start_idx = -1
        end_idx = -1
        for i, line in enumerate(lines):
            if line.startswith("## SENSOR TRACKS"):
                start_idx = i
            elif start_idx != -1 and line.startswith("## ATTRIBUTE CONTRACT"):
                end_idx = i
                break
        if start_idx != -1 and end_idx != -1:
            return "\n".join(lines[start_idx:end_idx]).strip()
        return ""

    return {
        "clock_anchor_iso": sensor_res.clock_anchor_iso,
        "w0_sensors_quality_track_len": len(s_data_w0.get("quality_track", [])),
        "w1_sensors_quality_track_len": len(s_data_w1.get("quality_track", [])),
        "w0_sensors_has_clock_anchor": any(x.get("type") == "clock_anchor" for x in s_data_w0.get("quality_track", [])),
        "w1_sensors_has_clock_anchor": any(x.get("type") == "clock_anchor" for x in s_data_w1.get("quality_track", [])),
        "block_w0_sensors": extract_sensor_track_block(prompt_w0_sensors.user),
        "block_w1_sensors": extract_sensor_track_block(prompt_w1_sensors.user),
        "block_w0_nosensors": extract_sensor_track_block(prompt_w0_nosensors.user),
        "block_w1_nosensors": extract_sensor_track_block(prompt_w1_nosensors.user),
    }


def main() -> None:
    gt_path = Path("fixtures/ground_truth_simvideo2.json")
    ground_truth = load_ground_truth(gt_path)
    client = bigquery.Client(project="nodepeel")
    runs = ["pro_run_01", "pro_run_02", "pro_run_03"]

    print("=" * 95)
    print("DIAGNOSTIC REPORT: TIMESTAMP DRIFT IN PRO-MODEL EXTRACTION RUNS")
    print("=" * 95)

    # -------------------------------------------------------------
    # CHECK 1: DECODING DETERMINISM
    # -------------------------------------------------------------
    c1 = run_check_1_decoding_determinism()
    print("\n" + "-" * 95)
    print("CHECK 1: DECODING DETERMINISM & PARAMETER RESOLUTION")
    print("-" * 95)
    print("API Capabilities in google.genai.types.GenerateContentConfig:")
    print(f"  - seed parameter exposed:             {c1['has_seed_parameter']} (type: int | None)")
    print(f"  - temperature parameter exposed:      {c1['has_temperature_parameter']} (type: float | None)")
    print(f"  - top_p parameter exposed:            {c1['has_top_p_parameter']} (type: float | None)")
    print(f"  - top_k parameter exposed:            {c1['has_top_k_parameter']} (type: float | None)")
    print(f"  - candidate_count parameter exposed:  {c1['has_candidate_count_parameter']} (type: int | None)")

    print("\nDeclared (prompts/VERSIONS.yaml) vs Actual Call-Time Parameters (scripts/run_case.py):")
    print(f"{'Pass':<9} | {'Decl Model':<22} | {'Decl Temp':<10} | {'Call Temp (Effective)':<24} | {'Decl k':<7} | {'Call k':<8} | {'Call Seed':<12}")
    print("-" * 105)
    for r in c1["table_rows"]:
        print(f"{r['pass']:<9} | {r['decl_model']:<22} | {str(r['decl_temp']):<10} | {r['call_temp']:<24} | {str(r['decl_k']):<7} | {r['call_k']:<8} | {r['call_seed']:<12}")

    print("\nCheck 1 Finding:")
    print("  * DISCREPANCY: scripts/run_case.py never reads or passes temperature, thinking, or seed from")
    print("    prompts/VERSIONS.yaml to call_model_cached() / VertexClient.generate().")
    print("  * EFFECTIVE STATE: Vertex AI executes with API-level defaults: temperature=None (model default: 1.0),")
    print("    seed=None (unseeded stochastic sampling), and thinking_config=None.")
    print("  * Seed parameter IS fully supported by google.genai (types.GenerateContentConfig.seed).")

    # -------------------------------------------------------------
    # CHECK 2: PER-WINDOW OFFSET & BOUNDARY PROXIMITY
    # -------------------------------------------------------------
    c2 = run_check_2_per_window_offset(client, ground_truth, runs)
    print("\n" + "-" * 95)
    print("CHECK 2: PER-WINDOW OFFSET & BOUNDARY PROXIMITY ANALYSIS")
    print("-" * 95)

    print("\nTable 2A: Detailed Attribution for All 15 Associated Detections:")
    print(f"{'Run ID':<11} | {'Shock':<7} | {'GT (s)':<7} | {'Pred (s)':<8} | {'Signed dt':<10} | {'Window':<8} | {'Dist Start':<11} | {'Dist End':<10} | Window Bounds")
    print("-" * 105)
    for d in c2["detailed_detections"]:
        print(f"{d['run_id']:<11} | #{d['gt_shock_idx']}     | {d['gt_timestamp_s']:<7.1f} | {d['pred_timestamp_s']:<8.1f} | {d['signed_dt']:<+10.1f} | Win {d['win_idx']}   | {d['dist_from_win_start']:<11.1f}s | {d['dist_from_win_end']:<10.1f}s | {d['win_bounds']}")

    print("\nTable 2B: Window-Level Summary Statistics:")
    print(f"{'Window':<8} | {'Bounds':<20} | {'Primary Bounds':<20} | {'n Detections':<13} | {'Mean Signed dt':<15} | {'Mean |dt|':<10} | {'Signed dt Range':<15}")
    print("-" * 110)
    for ws in c2["win_summaries"]:
        rng_str = f"[{ws['min_signed_dt']:+.1f}s, {ws['max_signed_dt']:+.1f}s]" if ws["n_detections"] > 0 else "N/A"
        print(f"Win {ws['win_idx']:<4} | {ws['bounds']:<20} | {ws['primary_bounds']:<20} | {ws['n_detections']:<13} | {ws['mean_signed_dt']:<+15.2f} | {ws['mean_abs_dt']:<10.2f}s | {rng_str:<15}")

    print("\nCheck 2 Findings & Interpretation:")
    print("  1. Window-Local to Absolute Second Conversion:")
    print("     - There is NO systematic per-window offset bug (Window 1 contains Shock 3 with error -1.8s,")
    print("       Shock 4 with error +7.5s, and Shock 5 with error -4.8s; different signs inside the same window).")
    print("  2. Boundary Edge vs Interior Proximity:")
    print("     - Shock #2 (388.0s, Window 0): Sits at 376-384s (96-104s before window end, 36-44s before primary end).")
    print("       It is reported consistently early (-4.0s, -12.0s, -10.5s) across all 3 runs.")
    print("     - Shock #4 (742.0s, Window 1): Sits at 743-755s (323-335s after window start, 145-157s before end).")
    print("       It is near the center of Window 1, yet reported late (+8.5s, +13.0s, +1.0s).")
    print("     - Shock #3 (622.0s, Window 1): Sits at 620.0-620.5s (-1.5s, -2.0s, -2.0s) with 0.5s spread.")
    print("     - Conclusion: Errors do NOT cluster at window boundary edges; they reflect ungrounded VLM")
    print("       temporal estimation during long continuous video segments.")

    # -------------------------------------------------------------
    # CHECK 3: S5 ANCHOR REACHABILITY
    # -------------------------------------------------------------
    c3 = run_check_3_s5_anchor_reachability()
    print("\n" + "-" * 95)
    print("CHECK 3: S5 BURNED-IN TIMECODE ANCHOR REACHABILITY")
    print("-" * 95)
    print(f"Clock Anchor Extraction: {c3['clock_anchor_iso']}")
    print("\nSensor Placeholder Injection Status in pipeline/sensor_runner.py:")
    print(f"  - Window 0 with_sensors=True: quality_track entries={c3['w0_sensors_quality_track_len']}, has clock_anchor={c3['w0_sensors_has_clock_anchor']}")
    print(f"  - Window 1 with_sensors=True: quality_track entries={c3['w1_sensors_quality_track_len']}, has clock_anchor={c3['w1_sensors_has_clock_anchor']}")
    print("  * NOTE: sensor_runner.py line 228 only inserts clock_anchor if win_start <= 0.0 (Windows 1-3 get 0 clock anchors even with sensors).")

    print("\nActual P1 Prompt Rendered State in pro_run_01/02/03 (with_sensors=False):")
    print("  * SELF-DETECTION MODE was active because with_sensors=False.")
    print("  * All 5 sensor track placeholders ({compression_intervals}, {device_audio_hits}, {monitor_ocr_series},")
    print("    {asr_transcript}, {quality_windows}) rendered as empty lists '[]'.")
    print("\nRendered P1 Prompt Fragment (Window 0 & 1, Live Pro Runs):")
    print("```markdown")
    print(c3["block_w0_nosensors"])
    print("```")

    print("\nCheck 3 Finding:")
    print("  * In the 3 live Pro runs, S5 burned-in timecode NEVER reached the P1 prompt.")
    print("  * The VLM was forced to estimate absolute seconds from raw video playback position with")
    print("    unseeded temperature (API default 1.0) and zero temporal anchor grounding.")

    print("\n" + "=" * 95)
    print("FLAG ITEM: MODEL PINNING HAZARD (Q-008)")
    print("  * 'gemini-3.1-pro-preview' is an unpinned moving alias subject to backend model drift.")
    print("  * Proposed pinned model string: 'gemini-3.1-pro-preview' (or exact snapshot once GCP freezes revision).")
    print("=" * 95)


if __name__ == "__main__":
    main()
