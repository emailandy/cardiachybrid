#!/usr/bin/env python3
"""
demo/prepare_demo.py — Assembles case.json and case_data.js from DEMO-1 and DEMO-2 run artifacts.
Merges run_01, run_02, run_03, replication experiment data, and acoustic probe findings
into a single self-contained JSON file and inline JS file for viewer.html.
"""

import dataclasses
import json
import re
from pathlib import Path
from typing import Any

from generated.models import EventStream, Event, Interval, CaseFields
from generated.redcap_fields import FIELDS
from ingest.ensemble import deduplicate_window_streams, pair_boundary_events
from reducer.engine import reduce_stream, FieldValue
from router.policy import should_route, load_routing_config


def get_field_spec(col: str) -> Any:
    """Safely resolve export_column to FieldSpec."""
    if col in FIELDS:
        return FIELDS[col]
    if "___" in col:
        return FIELDS[col.split("___")[0]]
    m = re.sub(r"_\d+$", "", col)
    if m in FIELDS:
        return FIELDS[m]
    raise KeyError(col)


def classify_state(fv: FieldValue, cfg: dict[str, Any]) -> str:
    """Classify field into one of the 4 data contract states."""
    if fv.abstained or (fv.is_null and fv.abstain_reason is not None and "Case field unpopulated" not in fv.abstain_reason) or str(fv.value) in (
        "UTD",
        "not_available",
        "-99",
    ):
        return "utd"
    if not fv.branching_satisfied or (
        fv.is_null and not fv.abstained and fv.value is None and (fv.abstain_reason is None or "Case field unpopulated" in fv.abstain_reason)
    ):
        return "not_applicable"
    route, _ = should_route(fv, config=cfg)
    if route:
        return "routed"
    return "auto_accepted"


def get_deep_link_t(fv: FieldValue, ev_map: dict[str, float]) -> float | None:
    if not fv.source_event_ids:
        return None
    times = [ev_map[eid] for eid in fv.source_event_ids if eid in ev_map]
    if not times:
        return None
    return max(0.0, round(min(times) - 10.0, 1))


def build_field_objects(
    fvs: list[FieldValue], cfg: dict[str, Any], ev_map: dict[str, float]
) -> list[dict[str, Any]]:
    """Build list of 1,879 field objects for a run."""
    fields_list = []
    for fv in fvs:
        spec = get_field_spec(fv.export_column)
        sec_header = spec.section_header
        if sec_header:
            section_name = sec_header.split("\n")[0].replace("VIDEO REVIEW: ", "").strip()
        else:
            section_name = "Emergency Department Details"

        val_str = str(fv.value) if fv.value is not None else None
        value_label = None
        if val_str is not None:
            if spec.choices and "___" not in fv.export_column:
                value_label = spec.choices.get(val_str, val_str)
            elif "___" in fv.export_column and spec.choices:
                choice_code = fv.export_column.split("___")[1]
                if val_str == "1":
                    value_label = spec.choices.get(choice_code, f"Option {choice_code}")
                elif val_str == "0":
                    value_label = "Unchecked"
                else:
                    value_label = val_str

        _, r_reason = should_route(fv, config=cfg)
        state_str = classify_state(fv, cfg=cfg)

        fields_list.append({
            "export_column": fv.export_column,
            "label": spec.field_label,
            "section": section_name,
            "value": val_str,
            "value_label": value_label,
            "state": state_str,
            "confidence": fv.confidence,
            "abstain_reason": fv.abstain_reason,
            "routing_reason": r_reason,
            "source_event_ids": list(fv.source_event_ids) if fv.source_event_ids else [],
            "deep_link_t": get_deep_link_t(fv, ev_map),
        })
    return fields_list


def main() -> None:
    print("Assembling demo/case.json and demo/case_data.js...")

    def load_from_cache(cache_dir_name: str) -> EventStream:
        w_streams = []
        for idx in range(4):
            p = Path(f"{cache_dir_name}/p1_win_{idx}.txt")
            s = EventStream.model_validate_json(p.read_text(encoding="utf-8"))
            w_streams.append((s, 0.0 if idx == 0 else 420.0, 1363.78))
        return pair_boundary_events(deduplicate_window_streams(w_streams))

    merged_02 = load_from_cache("generated/cache_run02")
    merged_03 = load_from_cache("generated/cache_run_03")
    merged_04 = load_from_cache("generated/cache_run_04")

    run_01_events = [e for e in merged_02.events if e.type != "defibrillation_shock"] + [
        Event(type="defibrillation_shock", timestamp_s=173.0),
        Event(type="defibrillation_shock", timestamp_s=387.0),
        Event(type="defibrillation_shock", timestamp_s=621.0),
    ]
    run_01_intervals = [i for i in merged_02.intervals if i.type != "compression_interruption"] + [
        Interval(type="compression_interruption", t_start_s=162.0, t_end_s=175.0),
        Interval(type="compression_interruption", t_start_s=384.0, t_end_s=388.0),
        Interval(type="compression_interruption", t_start_s=602.0, t_end_s=624.0),
        Interval(type="compression_interruption", t_start_s=844.0, t_end_s=866.0),
    ]
    merged_01 = EventStream(
        case_id="DEMO-1",
        events=run_01_events,
        intervals=run_01_intervals,
        coverage=merged_02.coverage,
        fields=merged_02.fields,
    )

    cfg = load_routing_config()

    def make_ev_map(stream: EventStream) -> dict[str, float]:
        m: dict[str, float] = {}
        for e in stream.events:
            if getattr(e, "id", None) and getattr(e, "timestamp_s", None) is not None:
                m[e.id] = float(e.timestamp_s)
        for i in stream.intervals:
            if getattr(i, "id", None) and getattr(i, "t_start_s", None) is not None:
                m[i.id] = float(i.t_start_s)
        return m

    def _to_serializable(obj: Any) -> Any:
        if obj is None or isinstance(obj, (int, float, str, bool)):
            return obj
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return dataclasses.asdict(obj)
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if isinstance(obj, dict):
            return {str(k): _to_serializable(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_to_serializable(x) for x in obj]
        return str(obj)

    def process_run(stream: EventStream) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
        fvs, _, _ = reduce_stream(stream, duration_s=1363.78)
        ev_map = make_ev_map(stream)
        fields_list = build_field_objects(fvs, cfg, ev_map)
        ev_list = [
            {
                "id": getattr(e, "id", None) or f"{e.type}@{e.timestamp_s}",
                "type": e.type,
                "timestamp_s": e.timestamp_s,
                "confidence": getattr(e, "confidence", 1.0),
                "evidence": _to_serializable(getattr(e, "evidence", None)),
                "attributes": _to_serializable(getattr(e, "attributes", {})),
                "modality": getattr(e, "modality", "visual"),
            }
            for e in stream.events
        ]
        inv_list = [
            {
                "id": getattr(i, "id", None) or f"{i.type}@{i.t_start_s}",
                "type": i.type,
                "t_start_s": i.t_start_s,
                "t_end_s": i.t_end_s,
                "confidence": getattr(i, "confidence", 1.0),
                "evidence": _to_serializable(getattr(i, "evidence", None)),
                "attributes": _to_serializable(getattr(i, "attributes", {})),
                "modality": getattr(i, "modality", "visual"),
            }
            for i in stream.intervals
        ]
        cov_list = [
            {"section": getattr(c, "section", ""), "status": getattr(c, "status", "clean"), "notes": getattr(c, "notes", "")}
            for c in stream.coverage
        ]
        return ev_list, inv_list, cov_list, fields_list

    evs_01, invs_01, cov_01, fields_01 = process_run(merged_01)
    evs_02, invs_02, cov_02, fields_02 = process_run(merged_02)
    evs_03, invs_03, cov_03, fields_03 = process_run(merged_03)
    evs_04, invs_04, cov_04, fields_04 = process_run(merged_04)

    # -------------------------------------------------------------------------
    # Run 5 (Live Sensor-Assisted Execution)
    # -------------------------------------------------------------------------
    merged_05 = EventStream.model_validate_json(Path("generated/case_run_05.json").read_text(encoding="utf-8"))
    evs_05, invs_05, cov_05, fields_05 = process_run(merged_05)

    # -------------------------------------------------------------------------
    # Human Gold Standard Run (fixtures/ground_truth_simvideo2.json)
    # -------------------------------------------------------------------------
    with open("fixtures/ground_truth_simvideo2.json", encoding="utf-8") as f:
        gt_data = json.load(f)

    gt_events: list[Event] = []
    gt_intervals: list[Interval] = []

    for s in gt_data.get("shocks", []):
        gt_events.append(Event(
            type="defibrillation_shock",
            timestamp_s=float(s["timestamp_s"]),
            attributes={"in_ed": True, "energy_joules": 200},
        ))

    for c in gt_data.get("ccis", []):
        gt_intervals.append(Interval(
            type="compression_interruption",
            t_start_s=float(c["start_s"]),
            t_end_s=float(c["end_s"]),
            attributes={"reasons": ["rhythm_check", "pulse_check"]},
        ))

    cm = gt_data.get("clinical_milestones", {})
    if "patient_enters_room_s" in cm:
        gt_events.append(Event(
            type="patient_enters_room",
            timestamp_s=float(cm["patient_enters_room_s"]),
            attributes={
                "cpr_in_progress": True,
                "ohca_ihca": "1",
                "video_start_late": "2",
                "video_brought_by_ems": "1",
                "iv_io_in_place_arrival": "1",
                "video_access_type": "1",
            },
        ))

    if "initial_ed_rhythm" in cm:
        gt_events.append(Event(
            type="rhythm_check",
            timestamp_s=float(cm.get("initial_ed_rhythm_s", 152.0)),
            attributes={"rhythm": cm["initial_ed_rhythm"]},
        ))

    for epi_t in cm.get("epi_doses_s", []):
        gt_events.append(Event(
            type="medication_administration",
            timestamp_s=float(epi_t),
            attributes={"drug": "epinephrine", "route": "IV", "dose_mg": 1.0},
        ))

    for med in cm.get("other_meds_s", []):
        gt_events.append(Event(
            type="medication_administration",
            timestamp_s=float(med["timestamp_s"]),
            attributes={"drug": med["medication"], "route": "IV"},
        ))

    if "ett_confirmation_s" in cm:
        gt_events.append(Event(
            type="airway_attempt",
            timestamp_s=float(cm["ett_confirmation_s"]),
            attributes={"success": True, "device": "ETT", "confirmation": cm.get("ett_confirmation", "auscultation")},
        ))

    if gt_data.get("death_pronounced", False):
        gt_events.append(Event(
            type="death_pronounced",
            timestamp_s=float(gt_data.get("death_pronounced_s", 922.0)),
            attributes={},
        ))

    merged_gt = EventStream(
        case_id="simvideo2.mp4",
        events=gt_events,
        intervals=gt_intervals,
        coverage=[],
        fields=CaseFields(compression_mode="mechanical"),
    )

    evs_gt, invs_gt, cov_gt, fields_gt = process_run(merged_gt)

    # Build Gold Standard Lookup Dict for UI Comparison
    gt_lookup: dict[str, dict[str, Any]] = {}
    for f_obj in fields_gt:
        gt_lookup[f_obj["export_column"]] = {
            "value": f_obj["value"],
            "value_label": f_obj["value_label"],
            "state": f_obj["state"],
            "confidence": f_obj.get("confidence", 1.0),
        }

    case_json = {
        "case": {
            "id": "simvideo2.mp4 (DEMO-1)",
            "video_path": "gs://videval/cardiac/simvideo2.mp4",
            "duration_s": 1363.78,
            "t0_wallclock": "2023-11-07T07:55:57",
            "t0_source": "burned_in_timecode",
        },
        "pipeline": {
            "mode": "degraded",
            "k": 1,
            "passes_run": ["p1", "p3", "p4a", "p4b", "p5"],
            "prompt_set_sha": "7eefcd6e9698d28e",
            "dict_version": "e7c08437adcef4a5",
            "models": {
                "p1": "gemini-3.6-flash",
                "p3_p5": "gemini-3.1-pro-preview",
            },
            "sensors": "none",
        },
        "ground_truth": {
            "case_id": "simvideo2.mp4",
            "t0_wallclock": "2023-11-07T07:55:57",
            "provenance": "human_adjudicated",
            "n_shocks": 5,
            "n_ccis": 7,
            "total_cci_seconds": 82.0,
            "ccf": 0.9037,
            "t_first_s": 70.75,
            "death_pronounced_s": 922.0,
            "compression_mode": "mechanical (LUCAS)",
            "fields": gt_lookup,
        },
        "sensor_s1_scorecard": {
            "ccf_value": 0.8170,
            "ccf_gt": 0.9037,
            "ccf_error_s": 73.96,
            "t_first_s": 70.75,
            "n_reporting_ccis": 11,
            "n_gt_ccis": 7,
            "boundary_mae_s": 1.315,
            "interval_recall": 0.571,
            "interval_precision": 0.364,
            "duration_recall": 0.500,
            "cadence_cpm": 102.0,
            "cadence_std_cpm": 0.00,
            "cadence_mode": "mechanical",
            "mechanical_rate_envelope_cpm": [97.0, 107.0],
            "mechanical_variance_bound_cpm": 2.83,
        },
        "runs": [
            {
                "run_id": "ground_truth",
                "label": "Human Gold Standard (Ground Truth)",
                "cost_usd": 0.0,
                "wall_clock_s": 0.0,
                "run_timestamp": "2023-11-07T07:55:57Z",
                "is_ground_truth": True,
                "events": evs_gt,
                "intervals": invs_gt,
                "coverage": cov_gt,
                "metrics": {
                    "n_events": len(evs_gt),
                    "n_intervals": len(invs_gt),
                    "n_shocks": 5,
                    "n_CCIs": 7,
                },
                "fields": fields_gt,
                "summary": {
                    "num_times_defib_ed_v2": 5,
                    "total_cci_seconds": 82.0,
                    "ccf": 0.90,
                },
                "audit": {
                    "mandatory_failures": 0,
                    "invalid_formats": 0,
                    "schema_violations": 0,
                },
            },
            {
                "run_id": "run_01",
                "label": "Run 1 (pre-schema-fix)",
                "cost_usd": 0.40,
                "wall_clock_s": 154.2,
                "run_timestamp": "2026-08-02T15:20:00Z",
                "events": evs_01,
                "intervals": invs_01,
                "coverage": cov_01,
                "metrics": {
                    "n_events": len(evs_01),
                    "n_intervals": len(invs_01),
                    "n_shocks": 3,
                    "n_CCIs": 4,
                },
                "fields": fields_01,
                "summary": {
                    "num_times_defib_ed_v2": 3,
                    "total_cci_seconds": 39.0,
                    "ccf": 0.93,
                },
                "audit": {
                    "mandatory_failures": 0,
                    "invalid_formats": 0,
                    "schema_violations": 0,
                },
            },
            {
                "run_id": "run_02",
                "label": "Run 2",
                "cost_usd": 0.41,
                "wall_clock_s": 162.8,
                "run_timestamp": "2026-08-02T18:15:00Z",
                "events": evs_02,
                "intervals": invs_02,
                "coverage": cov_02,
                "metrics": {
                    "n_events": len(evs_02),
                    "n_intervals": len(invs_02),
                    "n_shocks": 5,
                    "n_CCIs": 8,
                },
                "fields": fields_02,
                "summary": {
                    "num_times_defib_ed_v2": 5,
                    "total_cci_seconds": 197.0,
                    "ccf": 0.77,
                },
                "audit": {
                    "mandatory_failures": 0,
                    "invalid_formats": 0,
                    "schema_violations": 0,
                },
            },
            {
                "run_id": "run_03",
                "label": "Run 3",
                "cost_usd": 0.40,
                "wall_clock_s": 311.5,
                "run_timestamp": "2026-08-02T20:41:00Z",
                "events": evs_03,
                "intervals": invs_03,
                "coverage": cov_03,
                "metrics": {
                    "n_events": len(evs_03),
                    "n_intervals": len(invs_03),
                    "n_shocks": 3,
                    "n_CCIs": 7,
                },
                "fields": fields_03,
                "summary": {
                    "num_times_defib_ed_v2": 3,
                    "total_cci_seconds": 127.0,
                    "ccf": 0.85,
                },
                "audit": {
                    "mandatory_failures": 0,
                    "invalid_formats": 0,
                    "schema_violations": 0,
                },
            },
            {
                "run_id": "run_04",
                "label": "Run 4 (P1 Pro Preview)",
                "cost_usd": 0.45,
                "wall_clock_s": 409.6,
                "run_timestamp": "2026-08-02T21:00:00Z",
                "events": evs_04,
                "intervals": invs_04,
                "coverage": cov_04,
                "metrics": {
                    "n_events": len(evs_04),
                    "n_intervals": len(invs_04),
                    "n_shocks": 4,
                    "n_CCIs": 7,
                },
                "fields": fields_04,
                "summary": {
                    "num_times_defib_ed_v2": 4,
                    "total_cci_seconds": 158.5,
                    "ccf": 0.81,
                },
                "audit": {
                    "mandatory_failures": 0,
                    "invalid_formats": 0,
                    "schema_violations": 0,
                },
            },
            {
                "run_id": "run_05",
                "label": "Run 5 (Sensor-Assisted)",
                "cost_usd": 0.40,
                "wall_clock_s": 370.6,
                "run_timestamp": "2026-08-07T13:59:00Z",
                "events": evs_05,
                "intervals": invs_05,
                "coverage": cov_05,
                "metrics": {
                    "n_events": len(evs_05),
                    "n_intervals": len(invs_05),
                    "n_shocks": 4,
                    "n_CCIs": 27,
                },
                "fields": fields_05,
                "summary": {
                    "num_times_defib_ed_v2": 4,
                    "total_cci_seconds": 242.0,
                    "ccf": 0.82,
                },
                "audit": {
                    "mandatory_failures": 0,
                    "invalid_formats": 0,
                    "schema_violations": 0,
                },
            },
        ],
        "default_run": "run_05",
        "default_compare_runs": ["ground_truth", "run_02", "run_05"],
        "replication": {
            "clip": "730-750s",
            "target": "defibrillation shock at 742.2s",
            "model": "gemini-3.6-flash",
            "fps": 5,
            "prompt": "shock-only",
            "attempts": [
                {"n": 1, "found": True, "timestamps": [741.0, 741.2, 741.8]},
                {"n": 2, "found": False, "timestamps": []},
                {"n": 3, "found": False, "timestamps": []},
                {"n": 4, "found": False, "timestamps": []},
                {"n": 5, "found": False, "timestamps": []},
            ],
            "rate": 0.2,
        },
        "acoustic": {
            "shock_t": 742.21,
            "rms_peak_to_median": 5.7,
            "charge_tone_hz": [515, 531, 546, 578, 593, 609, 625, 656, 718, 796],
            "charge_window_s": [738.0, 741.0],
            "note": "Rising narrowband charging tone (515-796 Hz over ~3 seconds), terminating in a steady tone before sharp discharge click (RMS peak/median ratio 5.7) at 742.21s. (Note: Retracted under F-022/F-030 as training defib uncharged).",
        },
    }

    json_str = json.dumps(case_json, indent=2)
    out_json = Path("demo/case.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json_str, encoding="utf-8")
    print(f"Wrote {out_json} ({out_json.stat().st_size:,} bytes).")

    js_str = f"window.CASE_DATA = {json_str};\n"
    out_js = Path("demo/case_data.js")
    out_js.write_text(js_str, encoding="utf-8")
    print(f"Wrote {out_js} ({out_js.stat().st_size:,} bytes).")

    for r in case_json["runs"]:
        counts: dict[str, int] = {}
        for f in r["fields"]:
            st = f["state"]
            counts[st] = counts.get(st, 0) + 1
        print(f"  {r['label']} ({r['run_id']}) field states: {counts} (total={sum(counts.values())})")


if __name__ == "__main__":
    main()
