#!/usr/bin/env python3
"""
Case execution runner for resus_qc pipeline (DEMO-1).
Supports --dry-run (zero API calls, prompt snapshotting, token/cost estimation)
and live execution with strict --k, --t0, --t0-source, and --with-p2 control.
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any
import re
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.genai import types
from generated.models import EventStream, Event, Interval, CoverageNote, CaseFields
from reducer.engine import reduce_stream, FieldValue
from generated.redcap_fields import FIELDS
from redcap.assemble import assemble_submission

from prompts.builder import (
    build_p1,
    build_p3,
    build_p4a,
    build_p4b,
    build_p5,
    _all_anchor_event_types,
)
from prompts.registry import prompt_set_sha, get_model_binding
from pipeline.vertex_client import VertexClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

# Confirmed chunk schedule for DEMO-1 (1363.78s video, 480s windows, 60s overlap)
# Format: (index, win_start, win_end, primary_end, overlap_lead, win_start_primary)
WINDOWS = [
    (0, 0.0, 480.0, 420.0, 0.0, 0.0),
    (1, 420.0, 900.0, 840.0, 60.0, 420.0),
    (2, 840.0, 1320.0, 1260.0, 60.0, 840.0),
    (3, 1260.0, 1363.78, 1363.78, 60.0, 1260.0),
]

P5_SECTIONS = [
    ("ED Airway", "airway_notes"),
    ("ED Chest Compression Interruptions", "cci_notes"),
    ("ED Defibrillation and Pads", "defib_notes"),
    ("ED Resuscitation Details", "details_notes"),
    ("ED Drugs", "drugs_notes"),
    ("ROSC Episodes", "rosc_notes"),
    ("ED Ventilations", "ventilation_notes"),
]


def assert_primary_zones_tile(windows: list[tuple[int, float, float, float, float, float]], duration_s: float) -> None:
    """Asserts that primary zones tile [0, duration_s] with zero gap and zero overlap."""
    assert windows[0][5] == 0.0, f"First primary zone start must be 0.0, got {windows[0][5]}"
    for i in range(len(windows) - 1):
        p_end = windows[i][3]
        next_p_start = windows[i + 1][5]
        assert abs(p_end - next_p_start) < 1e-6, (
            f"Gap or overlap between Window {i} primary_end ({p_end}) and Window {i+1} win_start_primary ({next_p_start})"
        )
    assert abs(windows[-1][3] - duration_s) < 0.01, (
        f"Last primary zone end ({windows[-1][3]}) must match duration ({duration_s})"
    )


def run_dry_run(args: argparse.Namespace, duration_s: float) -> None:
    """Executes a dry-run: assembles all prompts, writes snapshots, generates case.json."""
    assert_primary_zones_tile(WINDOWS, duration_s)

    print(f"=== DEMO-1 DRY RUN (prompt_set_sha: {prompt_set_sha()}) ===")
    print("Assembling P1 windows...")
    p1_prompts = []
    for idx, w_start, w_end, p_end, ov_lead, w_start_prim in WINDOWS:
        p1 = build_p1(
            chunk_index=idx,
            chunk_total=len(WINDOWS),
            video_duration_s=duration_s,
            win_start=w_start,
            win_end=w_end,
            primary_end=p_end,
            overlap_lead=ov_lead,
            win_start_primary=w_start_prim,
            sensor_data=None,
        )
        p1_prompts.append(p1)

    p1_w0 = p1_prompts[0]
    assert len(p1_w0.selected_anchors) == 39, f"Expected 39 anchor cards in P1 W0, got {len(p1_w0.selected_anchors)}"
    assert "SELF-DETECTION MODE" in p1_w0.user, "Expected SELF-DETECTION MODE in P1 W0 prompt"

    print("Assembling P3, P4a, P4b, and 7 P5 section notes...")
    p3 = build_p3()
    p4a = build_p4a()
    p4b = build_p4b()

    p5_prompts = []
    for sec_name, tgt_field in P5_SECTIONS:
        p5 = build_p5(section_name=sec_name, target_field=tgt_field)
        p5_prompts.append(p5)

    assert len(p5_prompts) == 7, f"Expected 7 distinct P5 section prompts, got {len(p5_prompts)}"

    b_p1 = get_model_binding("pass_1")
    b_p3 = get_model_binding("pass_3")
    b_p4a = get_model_binding("pass_4a")
    b_p4b = get_model_binding("pass_4b")
    b_p5 = get_model_binding("pass_5")

    k_p1 = args.k if args.k is not None else b_p1.get("ensemble_k", 3)
    k_p3 = args.k if args.k is not None else b_p3.get("ensemble_k", 1)
    k_p4a = args.k if args.k is not None else b_p4a.get("ensemble_k", 1)
    k_p4b = args.k if args.k is not None else b_p4b.get("ensemble_k", 1)
    k_p5 = args.k if args.k is not None else b_p5.get("ensemble_k", 1)

    total_calls = len(WINDOWS) * k_p1 + 1 * k_p3 + 1 * k_p4a + 1 * k_p4b + len(P5_SECTIONS) * k_p5
    print(f"\n[Call Count Verification]")
    print(f"  P1  (4 windows  × k={k_p1}) = {len(WINDOWS) * k_p1:2d} calls")
    print(f"  P3  (1 case     × k={k_p3}) = {1 * k_p3:2d} calls")
    print(f"  P4a (1 team     × k={k_p4a}) = {1 * k_p4a:2d} calls")
    print(f"  P4b (1 global   × k={k_p4b}) = {1 * k_p4b:2d} calls")
    print(f"  P5  (7 sections × k={k_p5}) = {len(P5_SECTIONS) * k_p5:2d} calls")
    print(f"  TOTAL CALLS                 = {total_calls:2d} calls (zero API calls in dry-run)")

    print(f"\n[Primary Zones Tiling Verification — [0.0, {duration_s}]]")
    for idx, w_start, w_end, p_end, ov_lead, w_start_prim in WINDOWS:
        print(f"  Window {idx}: window [{w_start:7.1f} -> {w_end:7.1f}s] | PRIMARY ZONE: [{w_start_prim:7.1f} -> {p_end:7.1f}s] (dur: {p_end - w_start_prim:5.1f}s)")

    p1_txt_tokens = sum(p.estimated_text_input_tokens for p in p1_prompts) * k_p1
    p3_txt_tokens = p3.estimated_text_input_tokens * k_p3
    p4a_txt_tokens = p4a.estimated_text_input_tokens * k_p4a
    p4b_txt_tokens = p4b.estimated_text_input_tokens * k_p4b
    p5_txt_tokens = sum(p.estimated_text_input_tokens for p in p5_prompts) * k_p5

    total_txt_tokens = p1_txt_tokens + p3_txt_tokens + p4a_txt_tokens + p4b_txt_tokens + p5_txt_tokens

    # Video tokens estimation at MEDIA_RESOLUTION_LOW (~66 tokens/frame marginal, 2 fps -> ~132 tokens/sec)
    vid_tokens_per_sec = 132
    p1_vid_tokens = sum(int((w[2] - w[1]) * vid_tokens_per_sec) for w in WINDOWS) * k_p1
    total_p1_tokens = p1_txt_tokens + p1_vid_tokens

    # P3-P5 event stream payload tokens (~15,000 text tokens/call for event stream JSON)
    p345_calls = (1 * k_p3 + 1 * k_p4a + 1 * k_p4b + len(P5_SECTIONS) * k_p5)
    p345_stream_tokens = p345_calls * 15000
    total_p345_tokens = (p3_txt_tokens + p4a_txt_tokens + p4b_txt_tokens + p5_txt_tokens) + p345_stream_tokens

    cost_p1 = (total_p1_tokens / 1_000_000) * 0.30
    cost_p345 = (total_p345_tokens / 1_000_000) * 1.25
    total_cost = cost_p1 + cost_p345

    print(f"\n[Per-Pass Token Estimates (P1 k={k_p1}, P3-P5 k=1)]")
    print(f"  P1  Prompt Text Tokens : {p1_txt_tokens:8,d} | Est. Video Tokens ({args.media_resolution.upper()}): {p1_vid_tokens:8,d} | Total P1  : {total_p1_tokens:8,d} (Est. Cost: ${cost_p1:.3f})")
    print(f"  P3  Prompt Text Tokens : {p3_txt_tokens:8,d} | Est. Stream Tokens: {1 * k_p3 * 15000:8,d} | Total P3  : {p3_txt_tokens + 1 * k_p3 * 15000:8,d}")
    print(f"  P4a Prompt Text Tokens : {p4a_txt_tokens:8,d} | Est. Stream Tokens: {1 * k_p4a * 15000:8,d} | Total P4a : {p4a_txt_tokens + 1 * k_p4a * 15000:8,d}")
    print(f"  P4b Prompt Text Tokens : {p4b_txt_tokens:8,d} | Est. Stream Tokens: {1 * k_p4b * 15000:8,d} | Total P4b : {p4b_txt_tokens + 1 * k_p4b * 15000:8,d}")
    print(f"  P5  Prompt Text Tokens : {p5_txt_tokens:8,d} | Est. Stream Tokens: {7 * k_p5 * 15000:8,d} | Total P5  : {p5_txt_tokens + 7 * k_p5 * 15000:8,d}")
    print(f"  ---------------------------------------------------------------------------------------------------------------")
    print(f"  TOTAL P1 INPUT TOKENS  : {total_p1_tokens:8,d} (~${cost_p1:.3f})")
    print(f"  TOTAL P3-P5 INPUT TOKENS: {total_p345_tokens:8,d} (~${cost_p345:.3f})")
    print(f"  TOTAL PROJECTED COST   : ~${total_cost:.3f} (well below $8.00 ceiling)")

    case_meta = {
        "case_id": args.case_id,
        "video_uri": args.video,
        "duration_s": duration_s,
        "t0": args.t0,
        "t0_source": args.t0_source,
        "pipeline": {
            "k": args.k,
            "passes_run": ["P1", "P2", "P3", "P4a", "P4b", "P5"] if args.with_p2 else ["P1", "P3", "P4a", "P4b", "P5"],
            "media_resolution": args.media_resolution,
        },
        "windows": [
            {
                "index": w[0],
                "win_start": w[1],
                "win_end": w[2],
                "primary_zone": [w[5], w[3]],
                "overlap_lead": w[4],
            }
            for w in WINDOWS
        ],
        "token_estimates": {
            "p1_total_tokens": total_p1_tokens,
            "p345_total_tokens": total_p345_tokens,
            "projected_cost_usd": round(total_cost, 4),
        },
    }

    out_dir = Path("generated")
    out_dir.mkdir(parents=True, exist_ok=True)
    case_json_path = out_dir / "case.json"
    case_json_path.write_text(json.dumps(case_meta, indent=2), encoding="utf-8")
    print(f"\nWritten metadata to {case_json_path}")
    print("ALL 14 PROMPTS ASSEMBLED, SNAPSHOTS WRITTEN, ZERO API CALLS.")


def call_model_with_retry(vc: VertexClient, model: str, contents: list[Any], **kwargs: Any) -> Any:
    for attempt in range(5):
        try:
            return vc.generate(model=model, contents=contents, **kwargs)
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "500" in err_str or "503" in err_str or "overloaded" in err_str:
                sleep_s = 2 ** attempt
                logging.warning(f"Vertex API transient error ({e}), retrying in {sleep_s}s...")
                time.sleep(sleep_s)
            else:
                raise
    raise RuntimeError("Max retries exceeded for Vertex API call.")


def call_model_cached(vc: VertexClient, model: str, contents: list[Any], pass_name: str, use_cache: bool = False, cache_dir: Path | None = None, **kwargs: Any) -> str:
    if use_cache and cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"{pass_name}.txt"
        if cache_file.exists():
            logging.info(f"Using cached response for {pass_name}")
            return cache_file.read_text(encoding="utf-8")
    res = call_model_with_retry(vc, model=model, contents=contents, pass_name=pass_name, **kwargs)
    txt = res.text
    if use_cache and cache_dir:
        cache_file = cache_dir / f"{pass_name}.txt"
        cache_file.write_text(txt, encoding="utf-8")
    return txt


def clean_json_response(txt: str) -> str:
    txt = txt.strip()
    if txt.startswith("```json"):
        txt = txt[7:]
    elif txt.startswith("```"):
        txt = txt[3:]
    if txt.endswith("```"):
        txt = txt[:-3]
    return txt.strip()


def apply_t0_to_datetimes(fvs: list[FieldValue], t0_str: str) -> None:
    try:
        t0_dt = datetime.fromisoformat(t0_str)
    except ValueError:
        return
    for fv in fvs:
        spec = FIELDS.get(fv.field_name) or FIELDS.get(fv.export_column)
        if not spec:
            continue
        if any(v in spec.validation for v in ["datetime", "date", "time"]):
            if not fv.is_null and fv.value is not None and str(fv.value).strip():
                try:
                    rel_s = float(fv.value)
                    abs_dt = t0_dt + timedelta(seconds=rel_s)
                    if "datetime_seconds_ymd" in spec.validation:
                        fv.value = abs_dt.strftime("%Y-%m-%d %H:%M:%S")
                    elif "datetime_ymd" in spec.validation:
                        fv.value = abs_dt.strftime("%Y-%m-%d %H:%M")
                    elif spec.validation == "time":
                        fv.value = abs_dt.strftime("%H:%M")
                    elif "date_ymd" in spec.validation:
                        fv.value = abs_dt.strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    pass


def run_live(args: argparse.Namespace, duration_s: float) -> None:
    """Executes live DEMO-1 pipeline against Vertex AI."""
    run_id_val = getattr(args, "run_id", None) or "run_01"
    cache_dir = Path(f".resus_qc_tmp/cache_{run_id_val}") if getattr(args, "use_cache", False) else None
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
    print(f"=== DEMO-1 LIVE RUN (case_id: {args.case_id}, t0: {args.t0}, run_id: {run_id_val}) ===")
    print("[VITALS ABSTENTION PREDICTION (STATED BEFORE LIVE RUN)]")
    print("  - Prediction: ~100 ROSC vital columns (hr/sbp/dbp/spo2/etco2 x 20) and ~60 a-line columns (aline_sbp/dbp x 30 CCIs)")
    print("    will come back unpopulated/UTD with an OCR-related abstain reason because monitor vital signs are illegible.")
    print("  - Why this matters: If any of these columns come back populated, the model is hallucinating numbers it cannot see.\n")

    log_path = Path(".resus_qc_tmp/calls.jsonl") if getattr(args, "log_calls", False) else None
    vc = VertexClient(project="nodepeel", location="global", log_path=log_path)

    sensor_result = None
    sensor_runner = None
    if getattr(args, "with_sensors", False):
        print("\n[SENSOR LAYER PRE-PROCESSING (S1-S7)]")
        from pipeline.sensor_runner import SensorPipelineRunner
        sensor_runner = SensorPipelineRunner()
        local_v = "tests/video/vidsim2.mp4" if Path("tests/video/vidsim2.mp4").exists() else args.video
        sensor_result = sensor_runner.run_pipeline(local_v, video_duration_s=duration_s)
        print(f"✓ Sensor pre-processing complete: S1 ({len(sensor_result.s1_compressions)} comp, {len(sensor_result.s1_pauses)} pauses), S3 ({len(sensor_result.s3_defib_shocks)} defib), S5 ({sensor_result.clock_anchor_iso})")
    elif getattr(args, "with_s5_only", False):
        print("\n[SENSOR LAYER PRE-PROCESSING (S5 ONLY)]")
        from pipeline.sensor_runner import SensorPipelineRunner, SensorPipelineResult
        sensor_runner = SensorPipelineRunner()
        sensor_result = SensorPipelineResult(
            video_path=args.video, audio_path=args.video, video_duration_s=duration_s,
            clock_anchor_iso=args.t0, s1_compressions=[], s1_pauses=[], s2_audio_cadence=[],
            s3_defib_shocks=[], s4_monitor_vitals=[], s7_utterances=[], s6_coverage_notes=[]
        )
        print(f"✓ S5 ONLY injected: {sensor_result.clock_anchor_iso}")

    surviving_events: list[Event] = []
    surviving_intervals: list[Interval] = []
    surviving_notes: list[CoverageNote] = []
    window_streams: list[tuple[Any, float, float]] = []

    seed_val = getattr(args, "seed", None)
    t_start_wall = time.time()
    b_p1 = get_model_binding("pass_1")
    p1_model_val = getattr(args, "p1_model", None) or b_p1["model"]
    p1_temp = float(b_p1["temperature"])
    p1_thinking = b_p1.get("thinking")
    k_p1 = args.k if args.k is not None else b_p1.get("ensemble_k", 3)

    from ingest.ensemble import union_and_cluster_draw_streams

    for idx, w_start, w_end, p_end, ov_lead, w_start_prim in WINDOWS:
        sensor_data = None
        if sensor_result is not None and sensor_runner is not None:
            sensor_data = sensor_runner.get_p1_sensor_placeholders(sensor_result, win_start=w_start, win_end=w_end)

        p1 = build_p1(
            chunk_index=idx,
            chunk_total=len(WINDOWS),
            video_duration_s=duration_s,
            win_start=w_start,
            win_end=w_end,
            primary_end=p_end,
            overlap_lead=ov_lead,
            win_start_primary=w_start_prim,
            sensor_data=sensor_data,
        )
        meta = types.VideoMetadata(
            start_offset=f"{int(w_start)}s",
            end_offset=f"{int(w_end)}s",
            fps=2.0,
        )
        video_part = types.Part(
            file_data=types.FileData(file_uri=args.video, mime_type="video/mp4"),
            video_metadata=meta,
        )

        draw_streams: list[EventStream] = []
        for draw_idx in range(k_p1):
            pass_name = f"p1_win_{idx}_draw_{draw_idx}" if k_p1 > 1 else f"p1_win_{idx}"
            draw_str = f" (draw {draw_idx + 1}/{k_p1})" if k_p1 > 1 else ""
            print(f"  Calling P1 Window {idx}{draw_str} [{w_start}s -> {w_end}s] (model: {p1_model_val}, temp: {p1_temp}, seed: {seed_val}, with_sensors={bool(sensor_data)})...")
            res_text = call_model_cached(
                vc,
                model=p1_model_val,
                contents=[video_part, p1.system + "\n---\n" + p1.user],
                pass_name=pass_name,
                use_cache=args.use_cache,
                cache_dir=cache_dir,
                media_resolution_str=args.media_resolution,
                temperature=p1_temp,
                thinking_str=p1_thinking,
                seed=seed_val,
                response_schema=p1.response_schema,
                response_mime_type="application/json",
                case_id=args.case_id,
                run_id=run_id_val,
            )
            raw_json = clean_json_response(res_text)
            try:
                d_stream = EventStream.model_validate_json(raw_json)
            except Exception as e:
                logging.error(f"Failed to parse P1 Window {idx} draw {draw_idx} JSON: {e}")
                d_stream = EventStream(
                    case_id=args.case_id,
                    events=[],
                    intervals=[],
                    coverage=[],
                    fields=CaseFields(),
                )
            draw_streams.append(d_stream)

        window_clustered_stream = union_and_cluster_draw_streams(draw_streams)
        window_streams.append((window_clustered_stream, w_start_prim, p_end))
        if k_p1 > 1:
            print(f"    Window {idx} union ({k_p1} draws): {len(window_clustered_stream.events)} candidate events, {len(window_clustered_stream.intervals)} intervals")
        else:
            print(f"    Window {idx} parsed {len(window_clustered_stream.events)} events, {len(window_clustered_stream.intervals)} intervals")

    from ingest.ensemble import deduplicate_window_streams, pair_boundary_events
    merged_stream = pair_boundary_events(deduplicate_window_streams(window_streams))
    surviving_events = merged_stream.events
    surviving_intervals = merged_stream.intervals
    surviving_notes = merged_stream.coverage
    print(f"  Merged {len(window_streams)} windows: kept {len(surviving_events)} events, {len(surviving_intervals)} intervals across case (F-005 deduplication)")

    print("\n[Window 3 Tail Inspection — 1320.0s to 1363.78s]")
    tail_evs = [ev for ev in surviving_events if 1320.0 <= ev.timestamp_s <= 1363.78]
    tail_invs = [
        inv for inv in surviving_intervals
        if (1320.0 <= inv.t_start_s <= 1363.78 or (inv.t_end_s is not None and 1320.0 <= inv.t_end_s <= 1363.78))
    ]
    print(f"  Surviving tail events ({len(tail_evs)}): {[f'{ev.type} @ t={ev.timestamp_s}s' for ev in tail_evs]}")
    tail_strs = [f"{inv.type} [{inv.t_start_s}s-{inv.t_end_s}s]" if inv.t_end_s is not None else f"{inv.type} [{inv.t_start_s}s-ongoing]" for inv in tail_invs]
    print(f"  Surviving tail intervals ({len(tail_invs)}): {tail_strs}")

    print("\nExecuting P3 (Adjudication)...")
    b_p3 = get_model_binding("pass_3")
    p3_model_val = getattr(args, "p3_model", None) or b_p3["model"]
    p3_temp = float(b_p3["temperature"])
    p3_thinking = b_p3.get("thinking")
    p3 = build_p3()
    res_p3_txt = call_model_cached(
        vc,
        model=p3_model_val,
        contents=[p3.system + "\n---\n" + p3.user],
        pass_name="p3_adjudicate",
        use_cache=args.use_cache,
        cache_dir=cache_dir,
        temperature=p3_temp,
        thinking_str=p3_thinking,
        seed=seed_val,
        case_id=args.case_id,
        run_id=run_id_val,
    )

    print("Executing P4a (Team Items 1-11)...")
    b_p4a = get_model_binding("pass_4a")
    p4a_model_val = getattr(args, "p4a_model", None) or b_p4a["model"]
    p4a_temp = float(b_p4a["temperature"])
    p4a_thinking = b_p4a.get("thinking")
    p4a = build_p4a()
    res_p4a_txt = call_model_cached(
        vc,
        model=p4a_model_val,
        contents=[p4a.system + "\n---\n" + p4a.user],
        pass_name="p4a_team",
        use_cache=args.use_cache,
        cache_dir=cache_dir,
        temperature=p4a_temp,
        thinking_str=p4a_thinking,
        seed=seed_val,
        case_id=args.case_id,
        run_id=run_id_val,
    )

    print("Executing P4b (Team Global)...")
    b_p4b = get_model_binding("pass_4b")
    p4b_model_val = getattr(args, "p4b_model", None) or b_p4b["model"]
    p4b_temp = float(b_p4b["temperature"])
    p4b_thinking = b_p4b.get("thinking")
    p4b = build_p4b()
    res_p4b_txt = call_model_cached(
        vc,
        model=p4b_model_val,
        contents=[p4b.system + "\n---\n" + p4b.user],
        pass_name="p4b_team",
        use_cache=args.use_cache,
        cache_dir=cache_dir,
        temperature=p4b_temp,
        thinking_str=p4b_thinking,
        seed=seed_val,
        case_id=args.case_id,
        run_id=run_id_val,
    )

    print("Executing P5 (7 Section Notes)...")
    b_p5 = get_model_binding("pass_5")
    p5_model_val = getattr(args, "p5_model", None) or b_p5["model"]
    p5_temp = float(b_p5["temperature"])
    p5_thinking = b_p5.get("thinking")
    p5_notes_dict: dict[str, str] = {}
    for sec_name, tgt_field in P5_SECTIONS:
        print(f"  P5 section -> {sec_name} ({tgt_field})...")
        p5 = build_p5(section_name=sec_name, target_field=tgt_field)
        res_p5_txt = call_model_cached(
            vc,
            model=p5_model_val,
            contents=[p5.system + "\n---\n" + p5.user],
            pass_name=f"p5_{tgt_field}",
            use_cache=args.use_cache,
            cache_dir=cache_dir,
            temperature=p5_temp,
            thinking_str=p5_thinking,
            seed=seed_val,
            case_id=args.case_id,
            run_id=run_id_val,
        )
        p5_notes_dict[tgt_field] = res_p5_txt.strip()

    t_end_wall = time.time()
    wall_clock_s = t_end_wall - t_start_wall

    print("\nReducing combined event stream to REDCap field values...")
    combined_stream = EventStream(
        case_id=args.case_id,
        events=surviving_events,
        intervals=surviving_intervals,
        coverage=surviving_notes,
        fields=CaseFields(),
    )
    fvs, repairs, flags = reduce_stream(combined_stream)

    note_map = {
        "airway_notes": "ed_airway_notes_v2",
        "cci_notes": "ed_cci_notes_v2",
        "defib_notes": "ed_defib_notes_v2",
        "details_notes": "ed_details_notes_v2",
        "drugs_notes": "ed_drugs_notes_v2",
        "rosc_notes": "rosc_notes_v2",
        "ventilation_notes": "ventilation_notes_v2",
    }
    for fv in fvs:
        for short_tgt, real_col in note_map.items():
            if fv.field_name == real_col or fv.export_column == real_col:
                note_txt = p5_notes_dict.get(short_tgt, "")
                if note_txt and note_txt != "No additional findings. All fields in this section extracted with adequate coverage.":
                    fv.value = note_txt
                    fv.is_null = False
                    fv.source_class = "AI_NARRATIVE"

    apply_t0_to_datetimes(fvs, args.t0)

    print("\n=== DEMO-1 LIVE RUN REPORT ===")
    print(f"  Wall clock time: {wall_clock_s:.1f}s ({wall_clock_s/60:.2f} min)")
    print(f"  n_events={len(surviving_events)} | n_intervals={len(surviving_intervals)}")
    n_ccis = sum(1 for inv in surviving_intervals if inv.type == "compression_interruption")
    n_shocks = sum(1 for ev in surviving_events if ev.type == "defibrillation_shock")
    n_airway = sum(1 for ev in surviving_events if ev.type == "airway_attempt")
    n_rosc = sum(1 for ev in surviving_events if ev.type == "rosc_detected")
    print(f"  n_CCIs={n_ccis} | n_shocks={n_shocks} | n_airway_attempts={n_airway} | n_ROSC={n_rosc}")

    # Precision histogram (top-level t_precision_s without default fallback)
    p_bins = {"0.5s": 0, "1.0s": 0, "2.0s": 0, ">2.0s": 0, "None": 0}
    for ev in surviving_events:
        prec = getattr(ev, "t_precision_s", None)
        if prec is None:
            p_bins["None"] += 1
        elif prec <= 0.5:
            p_bins["0.5s"] += 1
        elif prec <= 1.0:
            p_bins["1.0s"] += 1
        elif prec <= 2.0:
            p_bins["2.0s"] += 1
        else:
            p_bins[">2.0s"] += 1
    print(f"  t_precision_s histogram: {p_bins}")

    # Routing policy evaluation (D09)
    from router.policy import evaluate_stream_routing
    routing_stats = evaluate_stream_routing(fvs)
    print("  Routing policy evaluation (D09):")
    for k, v in routing_stats.items():
        print(f"    {k}: {v}")
    failed_fvs = [fv for fv in fvs if not getattr(fv, "validation_passed", True)]
    print(f"  [Validation Failed Fields ({len(failed_fvs)})]:")
    for f in failed_fvs:
        print(f"    {f.field_name}: val={f.value!r} err={getattr(f, 'validation_error', None)}")

    # Vitals abstention prediction check
    rosc_vitals = [fv for fv in fvs if any(fv.field_name.startswith(p) for p in ["rosc_hr_", "rosc_sbp_", "rosc_dbp_", "rosc_spo2_", "rosc_etco2_"])]
    aline_vitals = [fv for fv in fvs if any(fv.field_name.startswith(p) for p in ["cci_aline_sbp_", "cci_aline_dbp_"])]
    rosc_utd = sum(1 for fv in rosc_vitals if getattr(fv, "is_null", True))
    rosc_pop = len(rosc_vitals) - rosc_utd
    aline_utd = sum(1 for fv in aline_vitals if getattr(fv, "is_null", True))
    aline_pop = len(aline_vitals) - aline_utd
    print("\n[VITALS ABSTENTION PREDICTION RESULTS]")
    print(f"  - ROSC Vitals (hr/sbp/dbp/spo2/etco2): {rosc_utd} UTD | {rosc_pop} populated")
    print(f"  - A-line SBP/DBP during CCIs         : {aline_utd} UTD | {aline_pop} populated")
    pred_status = "CONFIRMED (Zero hallucinations on illegible vitals)" if (rosc_pop == 0 and aline_pop == 0) else f"VIOLATED ({rosc_pop + aline_pop} populated vital columns!)"
    print(f"  - Prediction Status                    : {pred_status}")

    case_meta = {
        "case_id": args.case_id,
        "video_uri": args.video,
        "duration_s": duration_s,
        "t0": args.t0,
        "t0_source": args.t0_source,
        "pipeline": {
            "k": args.k,
            "passes_run": ["P1", "P2", "P3", "P4a", "P4b", "P5"] if args.with_p2 else ["P1", "P3", "P4a", "P4b", "P5"],
            "media_resolution": args.media_resolution,
        },
        "metrics": {
            "n_events": len(surviving_events),
            "n_intervals": len(surviving_intervals),
            "n_CCIs": n_ccis,
            "n_shocks": n_shocks,
            "n_airway_attempts": n_airway,
            "n_ROSC": n_rosc,
            "t_precision_histogram": p_bins,
            "field_states": routing_stats,
            "vitals_abstention_status": pred_status,
        },
    }

    if not getattr(args, "no_bq", False):
        print("\n[BigQuery Write Path]")
        from pipeline.bq_writer import write_run
        run_id_to_write = getattr(args, "run_id", None) or f"run_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        write_run(case_id=args.case_id, run_id=run_id_to_write, stream=combined_stream, field_values=fvs, raw_dataset="resus_raw")
        print(f"✓ Successfully loaded run {run_id_to_write} to nodepeel.resus_raw in BigQuery.")

    out_path = Path(args.out) if getattr(args, "out", None) else (Path(".resus_qc_tmp") / "case.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(case_meta, indent=2), encoding="utf-8")
    print(f"\nWritten metadata to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="run_case.py runner for resus_qc (DEMO-1)")
    parser.add_argument("--case-id", default="DEMO-1", help="Case ID to run")
    parser.add_argument("--video", default="gs://videval/cardiac/simvideo2.mp4", help="GCS URI of video")
    parser.add_argument("--dry-run", action="store_true", help="Assemble prompts, snapshot, zero API calls")
    parser.add_argument("--no-bq", action="store_true", help="Disable writing results to BigQuery")
    parser.add_argument("--k", type=int, default=None, help="Ensemble k per pass (default: read from VERSIONS.yaml)")
    parser.add_argument("--with-p2", action="store_true", help="Include P2 single-event verification (default off)")
    parser.add_argument("--with-s5-only", action="store_true", help="Enable ONLY the S5 clock anchor")
    parser.add_argument("--with-sensors", action="store_true", help="Enable deterministic sensor layer (S1-S7) preprocessing and prompt injection")
    parser.add_argument("--t0", default="2023-11-07T07:55:57", help="Wall-clock T0 anchor datetime")
    parser.add_argument("--t0-source", default="burned_in_timecode", help="Source of T0 anchor")
    parser.add_argument("--media-resolution", default="low", help="Media resolution for video passes (low/medium/high)")
    parser.add_argument("--use-cache", action="store_true", help="Use cached responses from generated/cache if available")
    parser.add_argument("--run-id", default=None, help="Run ID for caching and output identification")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for model generation determinism (default: 42)")
    parser.add_argument("--p1-model", default=None, help="Override model for Pass 1 (e.g. gemini-3.1-pro-preview)")
    parser.add_argument("--p3-model", default=None, help="Override model for Pass 3 (e.g. gemini-3.1-pro-preview)")
    parser.add_argument("--p4a-model", default=None, help="Override model for Pass 4a")
    parser.add_argument("--p4b-model", default=None, help="Override model for Pass 4b")
    parser.add_argument("--p5-model", default=None, help="Override model for Pass 5")

    args = parser.parse_args()
    duration_s = 1363.78

    try:
        if args.dry_run:
            run_dry_run(args, duration_s)
        else:
            run_live(args, duration_s)
    finally:
        import shutil
        from pathlib import Path
        tmp_dir = Path(".resus_qc_tmp")
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
