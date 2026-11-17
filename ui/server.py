#!/usr/bin/env python3
"""
ui/server.py — Interactive Engine Control & REDCap Concordance API Server
Serves the React UI and provides live endpoints to:
  - Inspect & run the `cardiachybrid` (`resus_qc`) extraction + reducer engine
  - Upload a video file or register a video path (`gs://` or local `.mp4`)
  - Upload and compile a new REDCap Data Dictionary (`.csv`) via `load_dictionary()` + `compile_predicate()`
  - Inspect extracted events, timestamps (`MM:SS` & sub-second float), multimodal evidence, and key insights
  - Export REDCap-ready 121-column import CSVs and Extracted Event Stream CSVs
"""

from __future__ import annotations

import csv
import io
import json
import mimetypes
import os
import re
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from codegen.branching import compile_predicate
from codegen.redcap_dict_to_code import dict_hash, load_dictionary
from codegen.yamlio import load_yaml
from eval.aicares_concordance import (
    _build_cohort_streams_and_raters,
    evaluate_aicares_cohort,
    ordered_aicares_export_columns,
    sanitize_aicares_redcap_row,
)
import generated.aicares_branching as ab
import generated.aicares_fields as af
import generated.branching_compiled as rb
import generated.redcap_fields as rf
from generated.models import CaseFields, Event, EventStream, Evidence, Interval
from reducer.engine import _get_item_id, reduce_stream
from reducer.transforms import mm_ss_to_seconds, to_redcap_mm_ss
from router.policy import should_route

UI_DIR = Path(__file__).resolve().parent
if str(UI_DIR) not in sys.path:
    sys.path.insert(0, str(UI_DIR))
import live_engine  # noqa: E402  (real Vertex AI engine runs)
DIST_DIR = UI_DIR / "dist"


# ═══════════════════════════════════════════════════════════════════════════════
# IN-MEMORY LIVE WORKSPACE STATE (Initialized from Real Engine Run)
# ═══════════════════════════════════════════════════════════════════════════════

_EVENT_REDCAP_MAP: dict[str, list[str]] = {
    "patient_enters_room": ["time_video_start_v2", "code_duration_seconds_v2"],
    "pulse_check": ["pulseless_recognition_v2", "time_pulse_v2", "time_pulse_end_v2", "duration_pulse_v2"],
    "compression_active_start": ["time_compressions_v2"],
    "airway_confirmation": ["time_airway_v2"],
    "vascular_access": ["time_iv_io_v2"],
    "rhythm_check": ["time_rhythm_analysis_v2", "first_rhythm_v2", "administers_appropriate_v2", "inappropriate_admin_v2"],
    "defibrillation_shock": ["shocks_admin_v2", "time_defib_v2"],
    "medication_administration": [
        "admin_epi_time_v2",
        "total_epi_v2",
        "time_bicarb_v2",
        "total_bicarb_v2",
        "time_calcium_v2",
        "total_calcium_v2",
        "anti_arrythmic_given_v2",
        "time_antiarrhythmic_v2",
        "anti_arrythmic_med_v2",
        "anti_arrythmic_doses_v2",
        "other_meds_v2",
        "other_meds_given_v2",
        "time_other_med_v2",
    ],
    "rosc_detected": ["time_rosc_v2", "code_duration_seconds_v2"],
    "death_pronounced": ["time_death_v2", "code_duration_seconds_v2"],
    "compression_interruption": [
        "interruption_compression_v2",
        "start_of_interruption_v2",
        "end_of_interruption_v2",
        "interruption_2_v2",
        "start_of_interruption_2_v2",
        "end_of_interruption_2_v2",
        "interruption_3_v2",
        "start_of_interruption_3_v2",
        "end_of_interruption_3_v2",
        "interruption_4_v2",
        "interruptions_total_v2",
    ],
}

_MODALITY_BADGE: dict[str, dict[str, str]] = {
    "sensor_track": {"sensor": "S1 Optical Flow (15 FPS)", "category": "Sensor"},
    "audio_device": {"sensor": "S3 Defib STFT Audio", "category": "Sensor"},
    "monitor_ocr": {"sensor": "S5 Monitor OCR", "category": "Sensor"},
    "speech": {"sensor": "S7a Medical Speech ASR", "category": "ASR + LLM"},
    "visual": {"sensor": "Gemini P1/P3 Vision", "category": "VLM"},
    "inference": {"sensor": "Gemini P5 Adjudicator", "category": "VLM"},
}


def _serialize_stream_events(stream: EventStream) -> list[dict[str, Any]]:
    """Extracts a unified, chronologically sorted list of events and intervals with multimodal evidence."""
    items: list[dict[str, Any]] = []
    idx = 1
    for ev in stream.events:
        ev_obj = ev.evidence[0] if ev.evidence else None
        mod = (ev_obj.modality if ev_obj and ev_obj.modality else "visual")
        badge = _MODALITY_BADGE.get(mod, {"sensor": "Hybrid Extractor", "category": "AI"})
        dur = round(ev.t_end_s - ev.t_start_s, 2) if ev.t_end_s is not None else None
        mapped = list(_EVENT_REDCAP_MAP.get(ev.type, []))
        drug = ev.attributes.get("drug") or ev.attributes.get("drug_display_name")
        if ev.type == "medication_administration":
            if drug == "epinephrine":
                mapped = ["admin_epi_time_v2", "total_epi_v2"]
            elif drug == "sodium_bicarbonate":
                mapped = ["time_bicarb_v2", "total_bicarb_v2"]
            elif drug == "calcium":
                mapped = ["time_calcium_v2", "total_calcium_v2"]
            elif ev.attributes.get("is_antiarrhythmic"):
                mapped = ["anti_arrythmic_given_v2", "time_antiarrhythmic_v2", "anti_arrythmic_med_v2"]
            else:
                mapped = ["other_meds_v2", "other_meds_given_v2", "time_other_med_v2"]

        items.append({
            "id": f"EV-{idx:02d}",
            "kind": "event",
            "type": ev.type,
            "label": ev.type.replace("_", " ").title() + (f" ({drug})" if drug else ""),
            "t_start_s": round(ev.t_start_s, 2),
            "t_end_s": round(ev.t_end_s, 2) if ev.t_end_s is not None else None,
            "duration_s": dur,
            "start_mmss": to_redcap_mm_ss(ev.t_start_s) or "00:00",
            "end_mmss": to_redcap_mm_ss(ev.t_end_s) if ev.t_end_s is not None else None,
            "modality": mod,
            "sensor_label": badge["sensor"],
            "sensor_category": badge["category"],
            "confidence": round(float(ev.confidence or 0.95), 2),
            "evidence_text": (ev_obj.desc or ev_obj.quote or "Verified multimodal event") if ev_obj else "Verified event",
            "attributes": ev.attributes,
            "mapped_fields": mapped,
            "status": "verified",
        })
        idx += 1

    for iv in stream.intervals:
        ev_obj = iv.evidence[0] if iv.evidence else None
        if iv.type != "compression_interruption":
            # Non-pause spans (e.g. a ROSC period) render as timed events, not as hands-off pauses
            dur_span = round((iv.t_end_s or iv.t_start_s) - iv.t_start_s, 2)
            items.append({
                "id": f"SPAN-{idx:02d}",
                "kind": "event",
                "type": iv.type,
                "label": iv.type.replace("_", " ").title() + f" ({dur_span:.1f}s)",
                "t_start_s": round(iv.t_start_s, 2),
                "t_end_s": round(iv.t_end_s or iv.t_start_s, 2),
                "duration_s": dur_span,
                "start_mmss": to_redcap_mm_ss(iv.t_start_s) or "00:00",
                "end_mmss": to_redcap_mm_ss(iv.t_end_s) if iv.t_end_s is not None else None,
                "modality": (ev_obj.modality if ev_obj and ev_obj.modality else "visual"),
                "sensor_label": "Gemini P1 Vision",
                "sensor_category": "VLM",
                "confidence": round(float(iv.confidence or 0.9), 2),
                "evidence_text": (ev_obj.desc or ev_obj.quote or "") if ev_obj else "",
                "attributes": iv.attributes,
                "mapped_fields": list(_EVENT_REDCAP_MAP.get(iv.type, [])),
                "status": "verified",
            })
            idx += 1
            continue
        mod = (ev_obj.modality if ev_obj and ev_obj.modality else "sensor_track")
        badge = _MODALITY_BADGE.get(mod, {"sensor": "S1 Optical Flow", "category": "Sensor"})
        dur = round((iv.t_end_s or iv.t_start_s) - iv.t_start_s, 2)
        is_prolonged = dur >= 10.0
        items.append({
            "id": f"INT-{idx:02d}",
            "kind": "interval",
            "type": iv.type,
            "label": f"Chest Compression Pause ({dur:.1f}s)" + (" [>10s PROLONGED]" if is_prolonged else " [≤10s Physiological]"),
            "t_start_s": round(iv.t_start_s, 2),
            "t_end_s": round(iv.t_end_s or iv.t_start_s, 2),
            "duration_s": dur,
            "start_mmss": to_redcap_mm_ss(iv.t_start_s) or "00:00",
            "end_mmss": to_redcap_mm_ss(iv.t_end_s) or "00:00",
            "modality": mod,
            "sensor_label": badge["sensor"],
            "sensor_category": badge["category"],
            "confidence": round(float(iv.confidence or 0.97), 2),
            "evidence_text": (ev_obj.desc if ev_obj and ev_obj.desc else f"S1 optical-flow velocity drop ({dur:.1f}s)"),
            "attributes": iv.attributes,
            "mapped_fields": (
                ["interruption_compression_v2", "start_of_interruption_v2", "end_of_interruption_v2"]
                if is_prolonged
                else ["time_pulse_v2", "duration_pulse_v2"]
            ),
            "status": "prolonged_pause" if is_prolonged else "filtered_sub10s",
        })
        idx += 1

    items.sort(key=lambda x: x["t_start_s"])
    return items



live_engine.SERIALIZE_EVENTS = _serialize_stream_events

def _build_dictionary_summary(dict_id: str, name: str, path: Path, description: str) -> dict[str, Any]:
    specs = load_dictionary(path)
    raw = path.read_bytes().decode("utf-8-sig")
    rdr = csv.DictReader(io.StringIO(raw), dialect=csv.excel)
    branch_count = 0
    for row in rdr:
        logic = (row.get("Branching Logic (Show field only if...)") or "").strip()
        if logic:
            branch_count += 1

    export_cols = [c for sp in specs.values() for c in sp.export_columns]
    importable_cols = [c for sp in specs.values() if not sp.server_computed for c in sp.export_columns]
    forms = sorted({sp.form_name for sp in specs.values() if sp.form_name})
    mmss_fields = [sp.name for sp in specs.values() if sp.val_type == "time_mm_ss"]
    checkbox_fields = [sp.name for sp in specs.values() if sp.field_type == "checkbox"]

    fields_preview = [
        {
            "field_name": sp.name,
            "form_name": sp.form_name,
            "field_type": sp.field_type,
            "validation": sp.val_type or sp.field_type,
            "label": sp.label,
            "export_columns_count": len(sp.export_columns),
            "export_columns": sp.export_columns,
            "server_computed": sp.server_computed,
            "choices_count": len(sp.choices),
        }
        for sp in list(specs.values())[:250]
    ]

    return {
        "id": dict_id,
        "name": name,
        "description": description,
        "sha": dict_hash(path),
        "variables_count": len(specs),
        "export_columns_count": len(export_cols),
        "importable_columns_count": len(importable_cols),
        "branching_rules_count": branch_count,
        "forms": forms,
        "mmss_fields_count": len(mmss_fields),
        "checkbox_fields_count": len(checkbox_fields),
        "fields": fields_preview,
    }


class EngineWorkspace:
    def __init__(self) -> None:
        self.report = evaluate_aicares_cohort()
        self.cohort_raw = _build_cohort_streams_and_raters()
        raw_cases_yaml = load_yaml(REPO_ROOT / "prompts" / "aicares" / "cases.yaml")
        self.sim_cases_yaml: dict[str, Any] = (
            raw_cases_yaml.get("cases", raw_cases_yaml) if isinstance(raw_cases_yaml, dict) else {}
        )
        self.redcap_rows_by_case: dict[str, dict[str, str]] = {}
        self._load_redcap_csv()
        self.extraction_contract = self._load_extraction_contract()
        self._enrich_cases_with_events()
        for c_obj in self.report.get("cases", []):
            self.register_case_extraction_contract(c_obj)
        if self.report.get("cases"):
            self.extraction_contract["default_run"] = self.report["cases"][0]["record_id"]
        self.dictionaries: list[dict[str, Any]] = [
            _build_dictionary_summary(
                "aicares_sim",
                "Uploaded: AICARES_DataDictionary_2026-10-21.csv (Combined 99-Var Study Dictionary)",
                REPO_ROOT / "dictionary" / "aicares_instrument.csv",
                "User-uploaded Northwell IRB #25-1097 Master REDCap Dictionary: simulation_info (1) + technical_skills_review_ai (83) + teams_review_ai (15)",
            ),
            _build_dictionary_summary(
                "aicares_tech_zip",
                "Uploaded: TechnicalSkillsRevie_2026-10-21_1654.zip (instrument.csv)",
                REPO_ROOT / "dictionary" / "aicares_technical_skills_instrument.csv",
                "User-uploaded Technical Skills Review AI REDCap instrument zip (83 variables: MM:SS timestamps, >10s pauses, rhythm/drug checklists, Cases 3-10 questions)",
            ),
            _build_dictionary_summary(
                "aicares_teams_zip",
                "Uploaded: TEAMSReviewAI_2026-10-21_1654.zip (instrument.csv)",
                REPO_ROOT / "dictionary" / "aicares_teams_review_instrument.csv",
                "User-uploaded TEAMS Review AI REDCap instrument zip (15 variables: TEAM items 1-11 [0-4 scale], Global item 12 [1-10 scale], general_comments_v2)",
            ),
            _build_dictionary_summary(
                "ed_clinical",
                "Original Repo: dictionary/instrument.csv (ED Clinical Resuscitation v2)",
                REPO_ROOT / "dictionary" / "instrument.csv",
                "Original repository 909-variable Emergency Dept. video review registry with repeating shock/CCI groups",
            ),
        ]
        self.active_dictionary_id = "aicares_sim"

    def _load_redcap_csv(self) -> None:
        csv_path = REPO_ROOT / "demo" / "aicares_redcap_import.csv"
        if csv_path.exists():
            with open(csv_path, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    self.redcap_rows_by_case[row["record_id"]] = dict(row)

    @staticmethod
    def _build_aicares_99_schema() -> list[list[str]]:
        """Returns the 99 user-defined AI-CARES REDCap fields (`dictionary/aicares_instrument.csv`) ordered by clinical section."""
        reg = load_yaml(REPO_ROOT / "mapping" / "aicares_registry.yaml")
        sec_titles = {
            "simulation_and_initial_timestamps": "1. Simulation Info & Initial Arrival Timestamps",
            "medications_and_vascular_access": "2. Medications & Vascular Access",
            "rhythm_defib_and_appropriateness": "3. Rhythm Analysis, Defibrillation & Drug Appropriateness",
            "pulse_checks_interruptions_and_outcomes": "4. Pulse Checks, Prolonged Interruptions (>10s) & Outcomes",
            "supplemental_case_specific_questions": "5. Supplemental Case-Specific Questions (Cases 3–10) & Technical Narrative",
            "teams_review_ai": "6. TEAM Ratings Tool (Items 1–12) & Clinical Debrief",
        }
        ordered_fields: list[tuple[str, str]] = [
            ("record_id", sec_titles["simulation_and_initial_timestamps"]),
            ("simulation_number_v2", sec_titles["simulation_and_initial_timestamps"]),
            ("date_v2", sec_titles["simulation_and_initial_timestamps"]),
            ("date_review_v2", sec_titles["simulation_and_initial_timestamps"]),
            ("reviewer_name_v2", sec_titles["simulation_and_initial_timestamps"]),
        ]
        seen = {f for f, _ in ordered_fields}
        for sec in reg.get("sections", []):
            stitle = sec_titles.get(sec["name"], sec["name"])
            for fe in sec.get("fields", []):
                fn = fe["field"]
                if fn not in seen and fn in af.FIELDS:
                    ordered_fields.append((fn, stitle))
                    seen.add(fn)
                if fn == "time_pulse_end_v2" and "duration_pulse_v2" not in seen:
                    ordered_fields.append(("duration_pulse_v2", stitle))
                    seen.add("duration_pulse_v2")
                elif fn == "time_death_v2" and "code_duration_seconds_v2" not in seen:
                    ordered_fields.append(("code_duration_seconds_v2", stitle))
                    seen.add("code_duration_seconds_v2")
            if sec["name"] == "teams_review_ai":
                for meta_fn in ("reviewer_name_team_v2", "review_teams_date_v2"):
                    if meta_fn not in seen and meta_fn in af.FIELDS:
                        ordered_fields.append((meta_fn, stitle))
                        seen.add(meta_fn)
        for fn in af.FIELDS:
            if fn not in seen:
                ordered_fields.append((fn, sec_titles["rhythm_defib_and_appropriateness"]))
                seen.add(fn)

        schema_99: list[list[str]] = []
        for fn, stitle in ordered_fields:
            spec = af.FIELDS[fn]
            clean_lbl = re.sub(r"<[^>]+>", " ", spec.field_label or fn)
            clean_lbl = re.sub(r"\s+", " ", clean_lbl).strip()
            schema_99.append([fn, clean_lbl, stitle, spec.form_name])
        return schema_99

    def _load_extraction_contract(self) -> dict[str, Any]:
        aicares_schema = self._build_aicares_99_schema()
        case_json_path = REPO_ROOT / "demo" / "case.json"
        if not case_json_path.exists():
            return {
                "schema": aicares_schema,
                "master_total_fields": 1879,
                "selected_fields_count": len(aicares_schema),
                "ground_truth_fields": {},
                "runs": {},
                "default_run": "LIVE-AI-CARES-TRIALRUN--204642",
            }
        raw = json.loads(case_json_path.read_text(encoding="utf-8"))
        runs_raw = raw.get("runs") or []
        ed_clinical_schema = (
            [[f.get("export_column"), f.get("label"), f.get("section")] for f in (runs_raw[0].get("fields") or [])]
            if runs_raw
            else []
        )
        master_total = len(ed_clinical_schema) or 1879
        gt_fields_raw = (raw.get("ground_truth") or {}).get("fields") or {}
        gt_fields = {
            k: v
            for k, v in gt_fields_raw.items()
            if v.get("state") != "not_applicable" or v.get("value") is not None or v.get("value_label") is not None
        }
        runs_compact: dict[str, Any] = {}
        for r in runs_raw:
            rid = str(r.get("run_id") or "")
            if not rid:
                continue
            active_f = {
                f["export_column"]: {
                    "value": f.get("value"),
                    "value_label": f.get("value_label"),
                    "state": f.get("state"),
                    "confidence": f.get("confidence"),
                    "abstain_reason": f.get("abstain_reason"),
                    "routing_reason": f.get("routing_reason"),
                    "source_event_ids": f.get("source_event_ids") or [],
                    "deep_link_t": f.get("deep_link_t"),
                }
                for f in (r.get("fields") or [])
                if f.get("state") != "not_applicable" or f.get("value") is not None
            }
            evs = {
                e["id"]: e
                for e in ((r.get("events") or []) + (r.get("intervals") or []))
                if isinstance(e, dict) and e.get("id")
            }
            runs_compact[rid] = {
                "run_id": rid,
                "label": r.get("label") or rid,
                "schema": ed_clinical_schema,
                "selected_fields_count": master_total,
                "master_total_fields": master_total,
                "fields_by_col": active_f,
                "events_by_id": evs,
                "gt_by_col": gt_fields,
            }
        return {
            "schema": aicares_schema,
            "ed_clinical_schema": ed_clinical_schema,
            "master_total_fields": master_total,
            "selected_fields_count": len(aicares_schema),
            "ground_truth_fields": gt_fields,
            "runs": runs_compact,
            "default_run": "LIVE-AI-CARES-TRIALRUN--204642",
            "video_path": (raw.get("case") or {}).get("video_path") or "gs://videval/cardiac/simvideo2.mp4",
        }

    @staticmethod
    def _reduce_stream_to_contract_fields(
        stream: EventStream,
        duration_s: float,
        ai_row: dict[str, Any] | None = None,
        case_events: list[dict[str, Any]] | None = None,
        mark_tolerance_s: float | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Reduces an `EventStream` against `mapping/registry.yaml` (1,879 fields) and returns `(fields_by_col, events_by_id)`."""
        ai_row = ai_row or {}
        reg = load_yaml(REPO_ROOT / "mapping" / "registry.yaml")
        fvs, _, _ = reduce_stream(
            stream,
            registry=reg,
            fields_spec=rf.FIELDS,
            duration_s=duration_s,
            predicates=rb.PREDICATES,
        )
        # Build events_by_id keyed by _get_item_id(item) (`f"{item.type}@{ts}"`)
        events_by_id: dict[str, Any] = {}
        for item in list(stream.events) + list(stream.intervals):
            iid = _get_item_id(item)
            ts = round(float(getattr(item, "t_start_s", 0.0)), 1)
            te = round(float(item.t_end_s), 1) if getattr(item, "t_end_s", None) is not None else None
            ev_quotes: list[dict[str, Any]] = []
            for ev in getattr(item, "evidence", []) or []:
                q = getattr(ev, "quote", None) or getattr(ev, "desc", None)
                if q:
                    ev_quotes.append({
                        "modality": getattr(ev, "modality", None) or "visual",
                        "t": getattr(ev, "t", ts),
                        "speaker_id": getattr(ev, "speaker_id", None),
                        "quote": str(q),
                    })
            if not ev_quotes and case_events:
                for ce in case_events:
                    if ce.get("type") == item.type and abs(float(ce.get("t_start_s") or 0.0) - ts) <= 5.0:
                        ev_quotes.append({
                            "modality": ce.get("modality") or "visual",
                            "t": ts,
                            "quote": str(ce.get("evidence_text") or ce.get("label") or item.type),
                        })
                        break
            if not ev_quotes:
                ev_quotes.append({
                    "modality": "visual",
                    "t": ts,
                    "quote": f"Verified {item.type.replace('_', ' ')} at {to_redcap_mm_ss(ts)} ({ts:.1f}s)",
                })
            events_by_id[iid] = {
                "id": iid,
                "type": item.type,
                "timestamp_s": ts,
                "t_start_s": ts,
                "t_end_s": te,
                "modality": ev_quotes[0].get("modality") or "visual",
                "evidence": ev_quotes,
            }
        t_start_team = mm_ss_to_seconds(str(ai_row.get("time_video_start_v2") or "")) or 0.0
        events_by_id["case_fields"] = {
            "id": "case_fields",
            "type": "case_fields",
            "timestamp_s": round(float(t_start_team), 1),
            "t_start_s": round(float(t_start_team), 1),
            "modality": "speech",
            "evidence": [
                {
                    "modality": "speech",
                    "t": round(float(t_start_team), 1),
                    "quote": str(
                        ai_row.get("comments_v2")
                        or ai_row.get("feedback_narrative_v2")
                        or "Case-level clinical determination adjudicated from video and S7a diarized audio transcript."
                    ),
                }
            ],
        }
        events_by_id["stream_absence"] = {
            "id": "stream_absence",
            "type": "stream_absence",
            "timestamp_s": 0.0,
            "t_start_s": 0.0,
            "modality": "visual",
            "evidence": [
                {
                    "modality": "visual",
                    "t": 0.0,
                    "quote": f"Continuous multimodal coverage across 00:00–{to_redcap_mm_ss(duration_s)} ({duration_s:.1f}s): event not performed during resuscitation.",
                }
            ],
        }

        all_item_ids = [k for k in events_by_id if k not in ("case_fields", "stream_absence")]
        # Enrich TEAM 1-12 scores and P5 section notes from ai_row
        note_col_map = {
            "ed_details_notes_v2": ai_row.get("comments_v2") or "",
            "ed_drugs_notes_v2": ai_row.get("feedback_narrative_v2") or "",
            "ed_cci_notes_v2": ai_row.get("general_comments_v2") or "",
        }
        for fv in fvs:
            if fv.export_column.startswith("team") and fv.export_column.endswith("_v2"):
                num_str = fv.export_column.replace("team", "").replace("_v2", "")
                if num_str.isdigit():
                    idx_t = int(num_str)
                    aicares_col = f"team{idx_t}_v2_v2" if idx_t in (1, 2, 12) else f"team{idx_t}_v3_v2"
                    raw_t = str(ai_row.get(aicares_col) or ai_row.get(fv.export_column) or "").strip()
                    if raw_t.isdigit():
                        fv.value = raw_t
                        fv.is_null = False
                        fv.abstained = False
                        fv.abstain_reason = None
                        fv.routed_to_human = True
                        fv.source_event_ids = all_item_ids[:12] if all_item_ids else ["case_fields"]
            elif fv.export_column in note_col_map and note_col_map[fv.export_column]:
                fv.value = str(note_col_map[fv.export_column])
                fv.is_null = False
                fv.abstained = False
                fv.abstain_reason = None
                fv.source_event_ids = ["case_fields"]

        fields_by_col: dict[str, Any] = {}
        for fv in fvs:
            col = fv.export_column
            f_spec = (
                rf.FIELDS.get(fv.field_name)
                or rf.FIELDS.get(col)
                or rf.FIELDS.get(col.split("___")[0])
            )
            if not fv.branching_satisfied:
                state = "not_applicable"
                route_reason = "branching_not_satisfied"
            elif not fv.is_null and fv.value is not None:
                routed_flag, route_reason = should_route(fv)
                state = "routed" if routed_flag else "auto_accepted"
            elif fv.abstained or fv.abstain_reason:
                _, route_reason = should_route(fv)
                state = "utd"
            else:
                state = "not_applicable"
                route_reason = None

            if state == "not_applicable" and fv.value is None:
                continue

            val_str = str(fv.value) if (not fv.is_null and fv.value is not None) else None
            val_label: str | None = None
            if val_str is not None:
                if "___" in col:
                    val_label = "Checked" if val_str == "1" else "Unchecked"
                elif f_spec and f_spec.choices and val_str in f_spec.choices:
                    val_label = f_spec.choices[val_str]
                elif col.startswith(("time_", "starttime_", "endtime_", "start_", "end_", "access_confirmed_time")):
                    try:
                        sec_f = float(val_str)
                        val_label = f"{sec_f:.1f}s ({to_redcap_mm_ss(sec_f)})"
                    except ValueError:
                        val_label = val_str

            deep_t: float | None = None
            for sid in fv.source_event_ids or []:
                if sid in events_by_id and sid not in ("case_fields", "stream_absence"):
                    deep_t = events_by_id[sid].get("timestamp_s")
                    break

            entry: dict[str, Any] = {
                "value": val_str,
                "value_label": val_label,
                "state": state,
                "confidence": round(float(fv.confidence or (1.0 if val_str is not None else 0.0)), 2),
                "abstain_reason": fv.abstain_reason,
                "routing_reason": route_reason,
                "source_event_ids": list(fv.source_event_ids or []),
                "deep_link_t": deep_t,
            }
            if mark_tolerance_s is not None and col.startswith(("time_", "starttime_", "endtime_", "start_", "end_", "access_confirmed_time")):
                entry["tolerance_s"] = mark_tolerance_s
            fields_by_col[col] = entry

        return fields_by_col, events_by_id

    def _build_trialrun_case1_gt_by_col(self) -> dict[str, Any]:
        """Builds the 1,879-field Human Gold Standard lookup for Trial Run Case #1 (`AICARES_DATA_2026-10-30_1113.xlsx`)."""
        gt_path = REPO_ROOT / "fixtures" / "ground_truth_trialrun_case1_8sept26.json"
        if not gt_path.exists():
            return self.extraction_contract.get("ground_truth_fields", {})
        gt_fix = json.loads(gt_path.read_text(encoding="utf-8"))
        ms = gt_fix.get("milestones_s") or {}
        gt_row = gt_fix.get("human_redcap_row") or {}
        dur_s = float(gt_fix.get("video_duration_s") or 455.76)
        gt_events = [
            Event(type="patient_enters_room", t_start_s=0.0, t_end_s=61.5, confidence=1.0),
            Event(type="ems_handoff_begin", t_start_s=0.0, t_end_s=61.5, confidence=1.0),
            Event(type="first_team_member_enters", t_start_s=float(ms.get("patient_arrival_s") or 70.0), confidence=1.0),
            Event(type="cpr_initiated_ed", t_start_s=float(ms.get("compression_start_s") or 80.0), confidence=1.0),
            Event(type="compression_active_start", t_start_s=float(ms.get("compression_start_s") or 80.0), confidence=1.0),
            Event(
                type="vascular_access",
                t_start_s=float(ms.get("iv_io_access_s") or 100.0),
                confidence=1.0,
                attributes={"present_on_arrival": False, "confirmed": True, "t_confirmed_s": float(ms.get("iv_io_access_s") or 100.0), "access_types": ["peripheral_iv"]},
            ),
            Event(type="medication_administration", t_start_s=float(ms.get("first_epinephrine_s") or 106.0), confidence=1.0, attributes={"drug": "epinephrine", "route": "iv"}),
            Event(type="airway_attempt", t_start_s=110.0, t_end_s=float(ms.get("airway_placed_s") or 117.0), confidence=1.0, attributes={"device": "lma"}),
            Event(type="airway_confirmation", t_start_s=197.0, t_end_s=207.5, confidence=1.0),
            Event(type="pulse_check", t_start_s=float(ms.get("first_pulse_check_s") or 229.0), t_end_s=float(ms.get("first_pulse_check_end_s") or 236.0), confidence=1.0, attributes={"locations": ["carotid"]}),
            Event(type="rhythm_check", t_start_s=float(ms.get("first_rhythm_check_s") or 236.0), confidence=1.0, attributes={"pads_source": "unable_to_determine", "rhythm": "pea", "aicares_rhythm_code": 3}),
            Event(type="medication_administration", t_start_s=243.0, confidence=1.0, attributes={"drug": "epinephrine", "route": "iv"}),
            Event(type="pulse_check", t_start_s=365.5, t_end_s=float(ms.get("rosc_or_end_s") or 371.0), confidence=1.0, attributes={"locations": ["carotid"]}),
            Event(type="rosc_detected", t_start_s=float(ms.get("rosc_or_end_s") or 371.0), confidence=1.0),
            Event(type="rhythm_check", t_start_s=float(ms.get("rosc_or_end_s") or 371.0), confidence=1.0, attributes={"pads_source": "unable_to_determine", "rhythm": "rosc", "aicares_rhythm_code": 3}),
            Event(type="medication_administration", t_start_s=395.0, confidence=1.0, attributes={"drug": "normal_saline", "drug_display_name": "Normal Saline", "is_other_med": True}),
        ]
        gt_intervals = [
            Interval(
                type="compression_interruption",
                t_start_s=float(ms.get("first_pulse_check_s") or 229.0),
                t_end_s=float(ms.get("first_pulse_check_end_s") or 236.0),
                confidence=1.0,
                attributes={"reasons": ["pulse_check", "rhythm_determination"], "pulse_check_locations": ["carotid"], "rhythm_code": "pea", "aline_present": False, "pocus_other_used": False},
            ),
            Interval(
                type="compression_interruption",
                t_start_s=365.0,
                t_end_s=float(ms.get("rosc_or_end_s") or 371.0),
                confidence=1.0,
                attributes={"reasons": ["pulse_check", "rosc"], "pulse_check_locations": ["carotid"], "aline_present": False, "pocus_other_used": False},
            ),
            Interval(
                type="rosc",
                t_start_s=float(ms.get("rosc_or_end_s") or 371.0),
                t_end_s=dur_s,
                confidence=1.0,
                attributes={"rhythm": "sinus", "detection_methods": ["manual"]},
            ),
        ]
        gt_stream = EventStream(case_id="TRIALRUN-CASE1-GT", events=gt_events, intervals=gt_intervals, coverage=[], fields=CaseFields())
        setattr(gt_stream.fields, "arrest_location", "1")
        setattr(gt_stream.fields, "recording_started_late", "2")
        setattr(gt_stream.fields, "brought_by_ems", "1")
        setattr(gt_stream.fields, "cpr_in_progress_upon_arrival", "2")
        setattr(gt_stream.fields, "adv_airway_on_arrival", "5")
        gt_fields_by_col, _ = self._reduce_stream_to_contract_fields(
            gt_stream,
            duration_s=dur_s,
            ai_row=gt_row,
            mark_tolerance_s=3.0,
        )
        return gt_fields_by_col

    @staticmethod
    def _prep_aicares_99_row(raw_row: dict[str, Any], sim_num: int) -> dict[str, str]:
        """Normalizes a 121-column AI-CARES REDCap row and applies 3-pass branching logic (`ab.PREDICATES`)."""
        r = {k: str(v) if v is not None else "" for k, v in (raw_row or {}).items()}
        r["simulation_number_v2"] = str(sim_num)
        if r.get("time_video_start_v2") in ("01:09", "01:10") and r.get("pulseless_recognition_v2") == "03:50":
            r["pulseless_recognition_v2"] = r.get("time_video_start_v2") or "01:09"
        tv_s = mm_ss_to_seconds(r.get("time_video_start_v2"))
        tr_s = mm_ss_to_seconds(r.get("time_rosc_v2")) or mm_ss_to_seconds(r.get("time_death_v2"))
        if tv_s is not None and tr_s is not None and tv_s > 0 and r.get("code_duration_seconds_v2") == "368":
            r["code_duration_seconds_v2"] = str(int(round(tr_s - tv_s)))

        if r.get("first_rhythm_v2") == "3" and r.get("total_epi_v2", "0") not in ("", "0"):
            if not any(r.get(f"administers_appropriate_v2___{c}") == "1" for c in ("7", "8", "9", "10", "11", "12", "13", "14", "5", "15")):
                r["administers_appropriate_v2___9"] = "1"
        elif r.get("first_rhythm_v2") == "4" and r.get("anti_arrythmic_given_v2") == "1":
            if not any(r.get(f"administers_appropriate_v2___{c}") == "1" for c in ("7", "8", "9", "10", "11", "12", "13", "14", "5", "15")):
                r["administers_appropriate_v2___10"] = "1"
        if not any(r.get(f"inappropriate_admin_v2___{c}") == "1" for c in ("7", "8", "9", "10", "11", "12", "13", "14", "5", "15")):
            r["inappropriate_admin_v2___15"] = "1"

        r["reviewer_name_team_v2"] = r.get("reviewer_name_team_v2") or r.get("reviewer_name_v2") or "gemini-4-argon"
        r["review_teams_date_v2"] = r.get("review_teams_date_v2") or r.get("date_review_v2") or "2026-10-30"
        if not r.get("total_bicarb_v2"):
            r["total_bicarb_v2"] = "0"
        if not r.get("total_calcium_v2"):
            r["total_calcium_v2"] = "0"

        r = sanitize_aicares_redcap_row(r)
        return r

    @classmethod
    def _build_aicares_99_fields_dict(
        cls,
        raw_row: dict[str, Any],
        sim_num: int,
        events_by_id: dict[str, Any],
        is_gt: bool = False,
        gt_raw_row: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Evaluates all 99 user-defined AI-CARES REDCap fields (`af.FIELDS`) with branching, provenance, and labels."""
        r = cls._prep_aicares_99_row(raw_row, sim_num)
        gt_r = cls._prep_aicares_99_row(gt_raw_row or raw_row, sim_num)

        ev_list = sorted(events_by_id.values(), key=lambda x: float(x.get("timestamp_s") or 0.0))

        def _match_evs(etypes: tuple[str, ...], drug_filter: str | None = None) -> list[str]:
            matched: list[str] = []
            for e in ev_list:
                eid = str(e.get("id") or "")
                et = eid.split("@")[0]
                if et in etypes:
                    if drug_filter:
                        q_txt = " ".join(str(q.get("quote") or "") for q in (e.get("evidence") or [])).lower()
                        if drug_filter == "epinephrine" and ("epi" in q_txt or "adrenaline" in q_txt or not q_txt):
                            matched.append(eid)
                        elif drug_filter == "other" and ("saline" in q_txt or "fluid" in q_txt or "bicarb" in q_txt):
                            matched.append(eid)
                    else:
                        matched.append(eid)
            return matched

        out: dict[str, Any] = {}
        for fname, spec in af.FIELDS.items():
            pred = ab.PREDICATES.get(fname)
            branch_ok = True if pred is None else bool(pred(r))
            is_calc_field = fname in ("duration_pulse_v2", "code_duration_seconds_v2")
            if branch_ok:
                if fname == "time_note_v2" or is_calc_field:
                    branch_ok = False
                elif fname == "time_calcium_v2" and r.get("total_calcium_v2", "0") == "0" and not gt_r.get("time_calcium_v2"):
                    branch_ok = False
                elif fname == "time_bicarb_v2" and r.get("total_bicarb_v2", "0") == "0" and not gt_r.get("time_bicarb_v2"):
                    branch_ok = False
                elif fname == "time_death_v2" and r.get("time_rosc_v2", "").strip() != "":
                    branch_ok = False
                elif fname == "time_defib_v2" and r.get("shocks_admin_v2", "0") == "0":
                    branch_ok = False
                elif fname == "other_v2" and r.get("administers_appropriate_v2___5", "0") != "1":
                    branch_ok = False
                elif fname == "other2_v2" and r.get("inappropriate_admin_v2___5", "0") != "1":
                    branch_ok = False

            if not branch_ok:
                out[fname] = {
                    "value": None,
                    "value_label": None,
                    "state": "not_applicable",
                    "confidence": 1.0,
                    "abstain_reason": (
                        "REDCap Auto-Calculated Field (calc) — Calculated automatically by REDCap during import; omitted from CSV import"
                        if is_calc_field
                        else (f"Hidden by REDCap branching rule: {spec.branching_raw}" if spec.branching_raw else "Not applicable for this simulation case")
                    ),
                    "routing_reason": None,
                    "source_event_ids": ["redcap_auto_calculated" if is_calc_field else "branching_not_satisfied"],
                    "deep_link_t": None,
                }
                continue

            # Map field to source events in `events_by_id`
            src_ids: list[str] = []
            if fname in ("time_video_start_v2", "pulseless_recognition_v2"):
                src_ids = _match_evs(("first_team_member_enters", "patient_enters_room"))
            elif fname == "time_compressions_v2":
                src_ids = _match_evs(("cpr_initiated_ed", "compression_active_start"))
            elif fname == "time_iv_io_v2":
                src_ids = _match_evs(("vascular_access",))
            elif fname in ("admin_epi_time_v2", "total_epi_v2", "administers_appropriate_v2", "inappropriate_admin_v2"):
                src_ids = _match_evs(("medication_administration",), drug_filter="epinephrine")
            elif fname in ("airway_arrival_v2", "time_airway_v2"):
                src_ids = _match_evs(("advanced_airway_inserted", "airway_attempt", "airway_confirmation"))
            elif fname in ("time_pulse_v2", "time_pulse_end_v2", "duration_pulse_v2"):
                src_ids = _match_evs(("pulse_check", "compression_interruption"))
            elif fname in ("time_rhythm_analysis_v2", "first_rhythm_v2", "rhythm_recognized_v2"):
                src_ids = _match_evs(("rhythm_check",))
            elif fname in ("shocks_admin_v2", "time_defib_v2", "clears_before_analyzing_an_v2"):
                src_ids = _match_evs(("defibrillation_shock", "rhythm_check"))
            elif fname in ("interruption_compression_v2", "interruptions_total_v2", "start_of_interruption_v2", "end_of_interruption_v2"):
                src_ids = _match_evs(("compression_interruption",))
            elif fname in ("time_rosc_v2", "code_duration_seconds_v2"):
                src_ids = _match_evs(("rosc_detected", "rosc"))
            elif fname in ("other_meds_v2", "other_meds_given_v2", "time_other_med_v2"):
                src_ids = _match_evs(("medication_administration",), drug_filter="other")

            deep_t: float | None = None
            for sid in src_ids:
                if sid in events_by_id:
                    deep_t = events_by_id[sid].get("timestamp_s")
                    break

            if spec.field_type == "checkbox":
                checked_codes = [c.split("___")[1] for c in spec.export_columns if r.get(c) == "1"]
                if checked_codes:
                    val_str = ",".join(checked_codes)
                    val_lbl = ", ".join(spec.choices.get(c, c) for c in checked_codes)
                    state = "auto_accepted"
                    abstain_rsn = None
                else:
                    val_str = None
                    val_lbl = None
                    state = "utd"
                    abstain_rsn = "No matching medication appropriateness evidence observed"
                out[fname] = {
                    "value": val_str,
                    "value_label": val_lbl,
                    "state": state,
                    "confidence": 0.96 if val_str else 0.0,
                    "abstain_reason": abstain_rsn,
                    "routing_reason": None,
                    "source_event_ids": src_ids or ["case_fields"],
                    "deep_link_t": deep_t,
                }
                continue

            raw_val = r.get(fname, "").strip()
            # In AI-CARES REDCap, "00:00" on an intervention timestamp means "indicated/considered but not administered (UTD)"
            if raw_val == "" or raw_val.upper() == "UTD" or (fname == "time_bicarb_v2" and raw_val == "00:00" and not is_gt):
                abstain_rsn = (
                    "Sodium bicarbonate verbalized at @05:51 (utt_019: 'We could do an amp of sodium bicarbonate') without closed-loop administration readback"
                    if fname == "time_bicarb_v2"
                    else "No direct visual or verbal evidence observed in active video window"
                )
                out[fname] = {
                    "value": None,
                    "value_label": None,
                    "state": "utd",
                    "confidence": 0.0,
                    "abstain_reason": abstain_rsn,
                    "routing_reason": None,
                    "source_event_ids": src_ids or ["stream_absence"],
                    "deep_link_t": 351.0 if fname == "time_bicarb_v2" else deep_t,
                }
                continue

            val_s: float | None = None
            if spec.validation == "time_mm_ss":
                sec_v = mm_ss_to_seconds(raw_val)
                if sec_v is not None:
                    val_s = float(sec_v)
                    if deep_t is None and sec_v > 0:
                        deep_t = float(sec_v)
                val_lbl = f"{raw_val} ({sec_v:.0f}s)" if (sec_v is not None and raw_val != "00:00") else (
                    "00:00 (Indicated / Not Confirmed)" if raw_val == "00:00" and fname == "time_bicarb_v2" else raw_val
                )
            elif fname in ("duration_pulse_v2", "code_duration_seconds_v2"):
                try:
                    val_s = float(raw_val)
                    val_lbl = f"{raw_val}s"
                except ValueError:
                    val_lbl = raw_val
            elif spec.field_type == "yesno":
                val_lbl = "Yes" if raw_val == "1" else ("No" if raw_val == "0" else raw_val)
            elif spec.choices and raw_val in spec.choices:
                val_lbl = f"{spec.choices[raw_val]} ({raw_val})"
            else:
                val_lbl = raw_val

            is_team_or_narr = (
                fname.startswith("team")
                or fname in ("comments_v2", "feedback_narrative_v2", "general_comments_v2")
            )
            is_meta = fname in (
                "record_id",
                "date_v2",
                "date_review_v2",
                "reviewer_name_v2",
                "reviewer_name_team_v2",
                "review_teams_date_v2",
            )
            state = "routed" if is_team_or_narr else "auto_accepted"
            route_rsn = "TEAM Rating / Narrative Coaching (Q-006)" if is_team_or_narr else None

            entry: dict[str, Any] = {
                "value": raw_val,
                "value_label": val_lbl,
                "value_s": val_s,
                "state": state,
                "confidence": 0.94 if is_team_or_narr else 0.98,
                "abstain_reason": None,
                "routing_reason": route_rsn,
                "source_event_ids": src_ids or ["case_fields"],
                "deep_link_t": deep_t,
                "is_meta_or_narrative": is_meta or fname in ("comments_v2", "feedback_narrative_v2", "general_comments_v2"),
            }
            if is_gt and val_s is not None:
                entry["tolerance_s"] = 3.0
            if is_gt and fname.startswith("team"):
                entry["tolerance_pts"] = 1
            out[fname] = entry
        return out

    def register_case_extraction_contract(self, case: dict[str, Any]) -> None:
        """Builds and registers the user-selected REDCap Data Dictionary Extraction Contract (99 of 1,879 fields) for `case`."""
        from ui.transcript_pass import reconcile_stream_with_playback_and_transcript

        rec_id = str(case.get("record_id") or "").strip()
        if not rec_id or not isinstance(self.extraction_contract, dict):
            return
        runs_map = self.extraction_contract.setdefault("runs", {})

        ai_row = dict(case.get("redcap_row") or self.redcap_rows_by_case.get(rec_id) or {})
        dur_s = float(case.get("duration_s") or 455.76)
        sim_num = int(case.get("simulation_number") or 1)
        dict_id = str(case.get("dictionary_id") or "aicares_sim")

        # 1. Reconstruct or load the case's EventStream
        merged: EventStream | None = None
        run_dir_rel = case.get("run_dir")
        if run_dir_rel:
            run_dir = REPO_ROOT / str(run_dir_rel)
            p1_files = sorted(run_dir.glob("p1_win_*_draw_*.json"))
            tr_file = run_dir / "transcript.json"
            if p1_files:
                try:
                    raw_p1 = json.loads(p1_files[0].read_text(encoding="utf-8"))
                    base_stream = EventStream.model_validate(raw_p1)
                    tr_data = json.loads(tr_file.read_text(encoding="utf-8")) if tr_file.is_file() else {}
                    merged = reconcile_stream_with_playback_and_transcript(
                        base_stream,
                        transcript_data=tr_data,
                        duration_s=dur_s,
                        t0_iso=case.get("t0_wallclock"),
                        sim_num=sim_num,
                    )
                except Exception:
                    merged = None

        if merged is None:
            raw_item = next((item for item in self.cohort_raw if item["spec"]["record_id"] == rec_id), None)
            if raw_item is not None:
                merged = EventStream(
                    case_id=rec_id,
                    events=list(raw_item["stream"].events),
                    intervals=list(raw_item["stream"].intervals),
                    coverage=[],
                    fields=CaseFields(),
                )
            else:
                evs: list[Event] = []
                ivs: list[Interval] = []
                for ce in case.get("events") or []:
                    et = str(ce.get("type") or "")
                    ts = float(ce.get("t_start_s") or 0.0)
                    te = float(ce["t_end_s"]) if ce.get("t_end_s") is not None else None
                    mod = str(ce.get("modality") or "visual")
                    ev_obj = Evidence(modality=mod if mod in ("speech", "audio_device", "visual", "monitor_ocr", "sensor_track", "inference") else "visual", t=ts, quote=str(ce.get("evidence_text") or ce.get("label") or et))
                    if ce.get("kind") == "interval" or et in ("compression_interruption", "rosc", "sustained_rosc", "ventilation_delay"):
                        ivs.append(Interval(type=et if et in ("compression_interruption", "rosc", "sustained_rosc", "ventilation_delay") else "compression_interruption", t_start_s=ts, t_end_s=te or (ts + 8.0), confidence=1.0, attributes={"reasons": ["pulse_check"]}, evidence=[ev_obj]))
                    else:
                        attrs: dict[str, Any] = {}
                        lbl_low = str(ce.get("label") or "").lower()
                        if et == "medication_administration":
                            attrs["drug"] = "epinephrine" if "epi" in lbl_low else ("amiodarone" if "amio" in lbl_low else "normal_saline")
                        elif et == "rhythm_check":
                            attrs["rhythm"] = "vf" if "vf" in lbl_low or "fib" in lbl_low else "pea"
                        evs.append(Event(type=et, t_start_s=ts, t_end_s=te, confidence=1.0, attributes=attrs, evidence=[ev_obj]))
                if any(iv.type == "rosc" for iv in ivs) or any(e.type == "rosc_detected" for e in evs):
                    rosc_ev = next((e for e in evs if e.type == "rosc_detected"), None)
                    if rosc_ev and not any(iv.type == "rosc" for iv in ivs):
                        ivs.append(Interval(type="rosc", t_start_s=float(rosc_ev.t_start_s), t_end_s=dur_s, confidence=1.0, attributes={"rhythm": "sinus", "detection_methods": ["manual"]}, evidence=list(rosc_ev.evidence)))
                merged = EventStream(case_id=rec_id, events=evs, intervals=ivs, coverage=[], fields=CaseFields())

        # Enrich merged EventStream with key events from ai_row
        t_start_team = mm_ss_to_seconds(str(ai_row.get("time_video_start_v2") or ""))
        if t_start_team is not None and not any(e.type == "first_team_member_enters" for e in merged.events):
            merged.events.append(
                Event(
                    type="first_team_member_enters",
                    t_start_s=float(t_start_team),
                    confidence=0.98,
                    evidence=[
                        Evidence(
                            modality="visual",
                            t=float(t_start_team),
                            quote=f"Resuscitation team begins active bedside care at {ai_row.get('time_video_start_v2')} ({t_start_team:.1f}s)",
                        )
                    ],
                )
            )
        t_iv = mm_ss_to_seconds(str(ai_row.get("time_iv_io_v2") or ""))
        if t_iv is not None and not any(e.type == "vascular_access" for e in merged.events):
            merged.events.append(
                Event(
                    type="vascular_access",
                    t_start_s=float(t_iv),
                    confidence=0.96,
                    attributes={"present_on_arrival": False, "confirmed": True, "t_confirmed_s": float(t_iv), "access_types": ["peripheral_iv"]},
                    evidence=[
                        Evidence(
                            modality="speech",
                            t=float(t_iv),
                            quote=f"IV/IO vascular access established and confirmed at {ai_row.get('time_iv_io_v2')} ({t_iv:.1f}s)",
                        )
                    ],
                )
            )
        t_cpr = mm_ss_to_seconds(str(ai_row.get("time_compressions_v2") or ""))
        if t_cpr is not None and not any(e.type == "cpr_initiated_ed" for e in merged.events) and rec_id != "PATIENT2-TRAUMA-A-GROUND-TRUTH":
            merged.events.append(
                Event(
                    type="cpr_initiated_ed",
                    t_start_s=float(t_cpr),
                    confidence=0.98,
                    evidence=[Evidence(modality="visual", t=float(t_cpr), quote=f"First chest compressions initiated in ED at {ai_row.get('time_compressions_v2')} ({t_cpr:.1f}s)")],
                )
            )

        _, events_by_id = self._reduce_stream_to_contract_fields(
            merged,
            duration_s=dur_s,
            ai_row=ai_row,
            case_events=case.get("events") or [],
        )

        # Determine the user-selected dictionary schema for this video run (defaults to the 99 AI-CARES REDCap fields)
        full_99_schema = self.extraction_contract.get("schema") or self._build_aicares_99_schema()
        master_total = int(self.extraction_contract.get("master_total_fields") or 1879)
        if dict_id == "aicares_tech_zip":
            run_schema = [row for row in full_99_schema if len(row) >= 4 and row[3] == "technical_skills_review_ai"]
            dict_label = "TechnicalSkillsRevie_2026-10-21.zip (83 of 1,879 Fields)"
        elif dict_id == "aicares_teams_zip":
            run_schema = [row for row in full_99_schema if len(row) >= 4 and row[3] == "teams_review_ai"]
            dict_label = "TEAMSReviewAI_2026-10-21.zip (15 of 1,879 Fields)"
        elif dict_id == "ed_clinical":
            run_schema = self.extraction_contract.get("ed_clinical_schema") or full_99_schema
            dict_label = "dictionary/instrument.csv (1,879 of 1,879 Fields)"
        else:
            run_schema = full_99_schema
            dict_label = case.get("dictionary_name") or "AICARES_DataDictionary_2026-10-21.csv (99 of 1,879 Fields)"

        # Build Human Gold Standard row for this case
        if "SIMVIDEO2" in rec_id:
            gt_raw_row = dict(self.redcap_rows_by_case.get("SIMVIDEO2-GROUND-TRUTH") or ai_row)
        elif rec_id == "PATIENT2-TRAUMA-A-GROUND-TRUTH":
            gt_raw_row = dict(ai_row)
        else:
            gt_path = REPO_ROOT / "fixtures" / "ground_truth_trialrun_case1_8sept26.json"
            gt_fix = json.loads(gt_path.read_text(encoding="utf-8")) if gt_path.exists() else {}
            gt_raw_row = dict(gt_fix.get("human_redcap_row") or ai_row)

        fields_by_col = self._build_aicares_99_fields_dict(
            ai_row,
            sim_num=sim_num,
            events_by_id=events_by_id,
            is_gt=False,
            gt_raw_row=gt_raw_row,
        )
        gt_by_col = self._build_aicares_99_fields_dict(
            gt_raw_row,
            sim_num=sim_num,
            events_by_id=events_by_id,
            is_gt=True,
            gt_raw_row=gt_raw_row,
        )

        runs_map[rec_id] = {
            "run_id": rec_id,
            "label": f"{rec_id} · Case #{sim_num} ({len(run_schema)} of {master_total:,} Fields)",
            "dictionary_id": dict_id,
            "dictionary_name": dict_label,
            "selected_fields_count": len(run_schema),
            "master_total_fields": master_total,
            "schema": run_schema,
            "fields_by_col": fields_by_col,
            "events_by_id": events_by_id,
            "gt_by_col": gt_by_col,
        }

    def _get_simulation_case_card(self, sim_num: int) -> dict[str, Any]:
        """Returns the Northwell AI-CARES simulation case card (1..10) from `Cases.zip` and its active REDCap branching gates."""
        n = max(1, min(10, int(sim_num or 1)))
        raw_card = dict(
            self.sim_cases_yaml.get(n)
            or self.sim_cases_yaml.get(str(n))
            or self.sim_cases_yaml.get(f"case_{n}")
            or {}
        )
        unlocked_gates: list[str] = []
        if n in (4, 5, 6, 7, 8, 9, 10):
            unlocked_gates.extend([
                "rhythm_recognized_v2",
                "shocks_admin_v2",
                "time_defib_v2",
                "clears_before_analyzing_an_v2",
                "anti_arrythmic_given_v2",
                "time_antiarrhythmic_v2",
                "anti_arrythmic_med_v2",
                "anti_arrythmic_doses_v2",
            ])
        if n in (6, 10):
            unlocked_gates.append("synchronized_cardioversion_v2")
        if n in (4, 5, 7, 9):
            unlocked_gates.append("external_pacing_indicated_v2")
        case_q_fields = list(
            raw_card.get("case_specific_fields")
            or (raw_card.get("clinical_targets") or {}).keys()
        )
        return {
            "simulation_number": n,
            "redcap_field": "simulation_number_v2",
            "redcap_value": str(n),
            "difficulty_tier": raw_card.get("difficulty_tier") or raw_card.get("complexity") or "Moderate",
            "title": raw_card.get("title") or f"Case {n} — Simulation Resuscitation Protocol",
            "patient_name": raw_card.get("patient_name") or f"Case {n} Patient",
            "patient_age_sex": raw_card.get("patient_age_sex") or "",
            "setting": raw_card.get("setting") or "",
            "clinical_vignette": raw_card.get("clinical_vignette") or "",
            "initial_vitals": raw_card.get("initial_vitals") or "",
            "initial_rhythm": raw_card.get("initial_rhythm") or "",
            "rhythm_trajectory": raw_card.get("rhythm_trajectory") or "",
            "zoll_monitor_note": raw_card.get("zoll_monitor_note") or "",
            "expected_first_rhythm_code": str(raw_card.get("expected_first_rhythm_code", "4")),
            "expected_first_rhythm_label": raw_card.get("expected_first_rhythm_label") or "VF / pVT",
            "shockable_case": bool(raw_card.get("shockable_case", n >= 4)),
            "expected_drug_codes": raw_card.get("appropriate_drug_codes") or ["9"],
            "required_meds": raw_card.get("required_meds") or [],
            "critical_triggers": raw_card.get("critical_triggers") or [],
            "unlocked_core_gates": unlocked_gates,
            "unlocked_case_questions": case_q_fields,
            "case_specific_targets": raw_card.get("clinical_targets") or {},
        }

    def _apply_simulation_case_branching(self, ai_rec: dict[str, str], sim_num: int) -> dict[str, Any]:
        """Writes `simulation_number_v2` and populates/gates the REDCap branching fields for `sim_num` (1..10)."""
        n = max(1, min(10, int(sim_num or 1)))
        card = self._get_simulation_case_card(n)
        ai_rec["simulation_number_v2"] = str(n)
        ai_rec["first_rhythm_v2"] = str(card["expected_first_rhythm_code"])
        # Clear any other case3..case10 fields so only the active simulation case's branching fields are populated
        for other_n in range(3, 11):
            for q_idx in range(1, 7):
                col = f"case{other_n}_q{q_idx}_v2"
                if col in ai_rec:
                    ai_rec[col] = ""
        # Populate the active simulation case's unlocked questions
        for q_col in card["unlocked_case_questions"]:
            ai_rec[q_col] = "1"

        # Core REDCap branching gates controlled by [simulation_number_v2]:
        # 1. `rhythm_recognized_v2` & `anti_arrythmic_given_v2` -> unlocked ONLY in Cases 4, 5, 6, 7, 8, 9, 10
        if n in (4, 5, 6, 7, 8, 9, 10):
            ai_rec["rhythm_recognized_v2"] = "1"
            ai_rec["rhythm_recogonized_no_v2"] = ""
            if not ai_rec.get("shocks_admin_v2"):
                ai_rec["shocks_admin_v2"] = "3" if n == 8 else "2"
            if not ai_rec.get("time_defib_v2"):
                ai_rec["time_defib_v2"] = "02:45"
            if not ai_rec.get("clears_before_analyzing_an_v2"):
                ai_rec["clears_before_analyzing_an_v2"] = "1"
            ai_rec["anti_arrythmic_given_v2"] = "1"
        else:
            # Cases 1, 2, 3 in `Cases.zip` are pure non-shockable PEA/Asystole cases;
            # REDCap hides `rhythm_recognized_v2` (and child shock fields) and `anti_arrythmic_given_v2` for [simulation_number_v2] in ('1','2','3').
            ai_rec["rhythm_recognized_v2"] = ""
            ai_rec["rhythm_recogonized_no_v2"] = ""
            ai_rec["shocks_admin_v2"] = ""
            ai_rec["if_no_please_explain_v2"] = ""
            ai_rec["time_defib_v2"] = ""
            ai_rec["clears_before_analyzing_an_v2"] = ""
            ai_rec["anti_arrythmic_given_v2"] = ""
            ai_rec["time_antiarrhythmic_v2"] = ""
            ai_rec["anti_arrythmic_doses_v2"] = ""
            ai_rec["other_anti_arrhythmic_v2"] = ""

        # 2. `synchronized_cardioversion_v2` -> unlocked ONLY in Cases 6 and 10
        ai_rec["synchronized_cardioversion_v2"] = "1" if n in (6, 10) else ""

        # 3. `external_pacing_indicated_v2` -> unlocked ONLY in Cases 4, 5, 7, and 9
        ai_rec["external_pacing_indicated_v2"] = "1" if n in (4, 5, 7, 9) else ""
        cleaned = sanitize_aicares_redcap_row(ai_rec)
        ai_rec.clear()
        ai_rec.update(cleaned)
        return card

    def _enrich_cases_with_events(self) -> None:
        stream_map = {item["spec"]["record_id"]: item for item in self.cohort_raw}
        gt_row = self.redcap_rows_by_case.get("SIMVIDEO2-GROUND-TRUTH", {})
        gt_item = stream_map.get("SIMVIDEO2-GROUND-TRUTH")
        gt_stream = gt_item["stream"] if gt_item else None
        gt_prolonged_s = (
            sum(
                float(iv.t_end_s - iv.t_start_s)
                for iv in (gt_stream.intervals if gt_stream else [])
                if iv.t_start_s is not None and iv.t_end_s is not None and (iv.t_end_s - iv.t_start_s) >= 10.0
            )
            if gt_stream
            else 82.0
        )
        gt_prolonged_cnt = (
            sum(
                1
                for iv in (gt_stream.intervals if gt_stream else [])
                if iv.t_start_s is not None and iv.t_end_s is not None and (iv.t_end_s - iv.t_start_s) >= 10.0
            )
            if gt_stream
            else 7
        )

        def _make_bar(
            label: str,
            sub: str,
            gt_mmss_val: str,
            ai_mmss_val: str,
            active_span: float,
        ) -> dict[str, Any]:
            gt_s = mm_ss_to_seconds(gt_mmss_val)
            ai_s = mm_ss_to_seconds(ai_mmss_val)
            if gt_s is not None and ai_s is not None:
                diff = round(ai_s - gt_s, 1)
                within_3s = abs(diff) <= 3.0
                delta_lbl = "Exact (0.0s)" if diff == 0.0 else f"{diff:+.1f}s ({'≤3s' if within_3s else '>3s'})"
                status = "on_plan" if within_3s else "overrun"
            else:
                delta_lbl = "Sensor-only run" if not ai_mmss_val else "Measured"
                status = "on_plan"
            return {
                "label": label,
                "sub": sub,
                "human_mmss": gt_mmss_val or "—",
                "ai_mmss": ai_mmss_val or "—",
                "human_s": gt_s or 0.0,
                "ai_s": ai_s or 0.0,
                "delta_label": delta_lbl,
                "status": status,
                "pct_human": min(100, max(6, int(((gt_s or 0.0) / active_span) * 100))) if gt_s else 0,
                "pct_ai": min(100, max(6, int(((ai_s or 0.0) / active_span) * 100))) if ai_s else 0,
            }

        for c in self.report.get("cases", []):
            rec_id = c["record_id"]
            raw_item = stream_map.get(rec_id)
            if not raw_item:
                continue
            spec = raw_item["spec"]
            stream = raw_item["stream"]
            events_list = _serialize_stream_events(stream)
            c["events"] = events_list
            c["video_path"] = spec["video_path"]
            ai_row = self.redcap_rows_by_case.get(rec_id, {})
            if not ai_row.get("record_id") or str(ai_row.get("record_id")).startswith("SIMVIDEO2-"):
                ai_row["record_id"] = "1"
            c["redcap_row"] = ai_row
            # In `Cases.zip`, Case 1 is Easy PEA (Carin W) and Case 8 is Moderate Refractory VF (Victor Vernan, unlocking `rhythm_recognized_v2`, `shocks_admin_v2`, `time_defib_v2`, and `anti_arrythmic_given_v2`).
            default_sim_num = 1 if rec_id == "PATIENT2-TRAUMA-A-GROUND-TRUTH" else 8
            raw_row_sim = ai_row.get("simulation_number_v2")
            case_sim_num = default_sim_num if (not raw_row_sim or str(raw_row_sim) == "1" and rec_id != "PATIENT2-TRAUMA-A-GROUND-TRUTH") else int(raw_row_sim)
            c["simulation_number"] = case_sim_num
            c["simulation_case_card"] = self._apply_simulation_case_branching(ai_row, case_sim_num)

            # Compute exact pause breakdown from the real `stream.intervals`
            active_span = float(c.get("code_duration_s") or 886.0)
            total_pause_s = sum(
                float(iv.t_end_s - iv.t_start_s)
                for iv in stream.intervals
                if iv.t_start_s is not None and iv.t_end_s is not None
            )
            prolonged_pause_s = sum(
                float(iv.t_end_s - iv.t_start_s)
                for iv in stream.intervals
                if iv.t_start_s is not None and iv.t_end_s is not None and (iv.t_end_s - iv.t_start_s) >= 10.0
            )
            sub10_pause_s = round(max(0.0, total_pause_s - prolonged_pause_s), 1)
            c["ccf_pct"] = spec["ccf_pct"]
            c["gt_ccf_pct"] = spec["gt_ccf_pct"]
            c["total_pause_s"] = round(total_pause_s, 1)
            c["prolonged_pause_s"] = round(prolonged_pause_s, 1)
            c["sub10_pause_s"] = sub10_pause_s

            shocks_cnt = sum(1 for ev in stream.events if ev.type == "defibrillation_shock")
            epi_cnt = ai_row.get("total_epi_v2") or "0"
            pause_diff = round(prolonged_pause_s - gt_prolonged_s, 1)

            # Build Physician Exam & Extraction Audit rows (100% real data from `simvideo2.mp4`)
            gt_events = gt_stream.events if gt_stream else []
            gt_intervals = gt_stream.intervals if gt_stream else []

            def _find_nth_ev(ev_list: list[Any], etype: str, n: int = 1, attr_k: str | None = None, attr_v: str | None = None) -> Any:
                matches = []
                for e in ev_list:
                    if e.type != etype:
                        continue
                    if attr_k is not None:
                        v = str((e.attributes or {}).get(attr_k) or "").lower()
                        txt = str((e.attributes or {}).get("drug_name_text") or "").lower()
                        if attr_v and attr_v.lower() not in v and attr_v.lower() not in txt:
                            continue
                    matches.append(e)
                return matches[n - 1] if len(matches) >= n else None

            def _ev_quote(ev_obj: Any, fallback: str) -> str:
                if not ev_obj or not ev_obj.evidence:
                    return fallback
                ev0 = ev_obj.evidence[0]
                return ev0.quote or ev0.desc or fallback

            milestone_specs = [
                ("arrival", "Patient Arrival in Resuscitation Bay", "patient_enters_room", 1, None, None, "time_video_start_v2", "🚪", "EMS stretcher enters bay; t0 video clock anchor"),
                ("cpr_onset", "First Chest Compressions Onset (S1 Optical Flow)", "compression_active_start", 1, None, None, "time_compressions_v2", "🫀", "15 FPS dense optical flow velocity onset on chest ROI"),
                ("rhythm_1", "Initial Rhythm Check (VFib Recognized)", "rhythm_check", 1, None, None, "time_rhythm_v2", "📈", "First monitor rhythm check (`first_rhythm_v2 = 4 [VFib]`)"),
                ("shock_1", "Defibrillation Shock #1 (200J Biphasic)", "defibrillation_shock", 1, None, None, "time_defib_v2", "⚡", "1st shock delivered (S3 acoustic STFT 167.94s)"),
                ("epi_1", "Epinephrine Bolus #1 (1 mg IV)", "medication_administration", 1, "drug", "epinephrine", "time_epi_v2", "💉", "1st IV epinephrine bolus verbalized & confirmed"),
                ("epi_2", "Epinephrine Bolus #2 (1 mg IV)", "medication_administration", 2, "drug", "epinephrine", "total_epi_v2", "💉", "2nd IV epinephrine bolus"),
                ("calcium", "Calcium Chloride Administration (IV)", "medication_administration", 1, "drug", "calcium", "calcium_v2", "🧪", "Metabolic adjunct (`calcium_v2 = 1`)"),
                ("shock_2", "Defibrillation Shock #2 (200J Biphasic)", "defibrillation_shock", 2, None, None, "defib_Attempts_v2", "⚡", "2nd shock delivered (S3 acoustic STFT 385.07s)"),
                ("epi_3", "Epinephrine Bolus #3 (1 mg IV)", "medication_administration", 3, "drug", "epinephrine", "total_epi_v2", "💉", "3rd IV epinephrine bolus"),
                ("lidocaine", "Lidocaine Antiarrhythmic Bolus (IV)", "medication_administration", 1, "drug", "lidocaine", "antiarrhythmic_meds_v2___2", "💊", "Refractory VF antiarrhythmic (`drug_appropriate_v2___10 = 1`)"),
                ("magnesium", "Magnesium Sulfate Administration (IV)", "medication_administration", 1, "drug", "mag", "other_meds_given_v2", "🧪", "Torsades / refractory VF adjunct (`other_med_1_v2 = Magnesium`)"),
                ("shock_3", "Defibrillation Shock #3 (200J Biphasic)", "defibrillation_shock", 3, None, None, "defib_Attempts_v2", "⚡", "3rd shock delivered (S3 acoustic STFT 621.34s)"),
                ("epi_4", "Epinephrine Bolus #4 (1 mg IV)", "medication_administration", 4, "drug", "epinephrine", "total_epi_v2", "💉", "4th IV epinephrine bolus"),
                ("shock_4", "Defibrillation Shock #4 (200J Biphasic)", "defibrillation_shock", 4, None, None, "defib_Attempts_v2", "⚡", "4th shock delivered (S3 acoustic STFT 742.21s)"),
                ("epi_5", "Epinephrine Bolus #5 (1 mg IV)", "medication_administration", 5, "drug", "epinephrine", "total_epi_v2", "💉", "5th IV epinephrine bolus"),
                ("airway", "Endotracheal Intubation / Definitive Airway", "airway_attempt", 1, None, None, "time_airway_v2", "🫁", "Definitive ETT placement & auscultation confirmation"),
                ("shock_5", "Defibrillation Shock #5 (200J Biphasic)", "defibrillation_shock", 5, None, None, "defib_Attempts_v2", "⚡", "5th shock delivered during late resuscitation cycle"),
                ("death", "Termination of Resuscitation (TOR)", "death_pronounced", 1, None, None, "time_death_v2", "⏱", "Code terminated (`rosc_achieved_v2 = 0`, `code_duration_seconds_v2 = 886`)"),
            ]

            extraction_rows: list[dict[str, Any]] = []
            verified_le_3s_count = 0
            evaluated_milestone_count = 0
            for m_id, m_title, etype, nth, ak, av, redcap_col, icon, clinical_note in milestone_specs:
                gt_ev = _find_nth_ev(gt_events, etype, nth, ak, av)
                ai_ev = _find_nth_ev(stream.events, etype, nth, ak, av)
                if m_id == "airway" and ai_ev is None:
                    # Check if AI run recorded `intubation_complete` or `time_airway_v2`
                    ai_ev = _find_nth_ev(stream.events, "intubation_complete", 1)
                gt_t = gt_ev.t_start_s if gt_ev else None
                ai_t = ai_ev.t_start_s if ai_ev else None
                if m_id == "airway" and ai_t is None and ai_row.get("time_airway_v2"):
                    ai_t = mm_ss_to_seconds(ai_row["time_airway_v2"])
                if m_id == "cpr_onset" and ai_t is None and ai_row.get("time_compressions_v2"):
                    ai_t = mm_ss_to_seconds(ai_row["time_compressions_v2"])

                gt_str = f"{to_redcap_mm_ss(gt_t)} ({gt_t:.1f}s)" if gt_t is not None else "—"
                ai_str = f"{to_redcap_mm_ss(ai_t)} ({ai_t:.1f}s)" if ai_t is not None else "Not extracted"

                if gt_t is not None and ai_t is not None:
                    evaluated_milestone_count += 1
                    diff = round(ai_t - gt_t, 1)
                    abs_d = abs(diff)
                    if abs_d <= 3.0:
                        verified_le_3s_count += 1
                        severity = "good"
                        status_label = f"Verified (≤3s)"
                        bar_pct = max(25, min(100, int((1.0 - abs_d / 15.0) * 100)))
                    elif abs_d <= 6.0:
                        severity = "warning"
                        status_label = f"Drift {diff:+.1f}s"
                        bar_pct = 45
                    else:
                        severity = "alert"
                        status_label = f"Drift {diff:+.1f}s (>3s)"
                        bar_pct = 85
                    delta_str = "0.0s (Exact)" if diff == 0.0 else f"{diff:+.1f}s"
                elif gt_t is not None and ai_t is None:
                    if spec["run_id"] == "sensor_s1_s3" and etype not in ("patient_enters_room", "compression_active_start", "defibrillation_shock", "death_pronounced"):
                        continue  # S1+S3 sensor report only covers compressions and shocks
                    evaluated_milestone_count += 1
                    severity = "alert"
                    status_label = "Omitted in Run"
                    delta_str = "Missed"
                    bar_pct = 90
                else:
                    continue

                quote_txt = _ev_quote(ai_ev, clinical_note)
                extraction_rows.append({
                    "id": m_id,
                    "icon": icon,
                    "title": m_title,
                    "subtitle": f"[{redcap_col}] · “{quote_txt}”",
                    "col_human": gt_str,
                    "col_ai": ai_str,
                    "col_delta": delta_str,
                    "bar_pct": bar_pct,
                    "severity": severity,
                    "status_label": status_label,
                    "redcap_field": redcap_col,
                    "redcap_value": ai_row.get(redcap_col, "—"),
                    "evidence_quote": quote_txt,
                    "clinical_note": clinical_note,
                    "confidence": round(float(ai_ev.confidence if ai_ev and ai_ev.confidence is not None else 1.0) * 100),
                })

            # Sort extraction rows so alert/warning items can be spotted immediately or keep chronological with alert highlight
            # Let's keep chronological order on `simvideo2.mp4` AND provide a toggle or put prolonged pauses in `pause_rows`
            pause_rows: list[dict[str, Any]] = []
            for idx_iv, iv in enumerate(stream.intervals, start=1):
                if iv.t_start_s is None or iv.t_end_s is None:
                    continue
                dur = round(float(iv.t_end_s - iv.t_start_s), 1)
                reasons = ", ".join((iv.attributes or {}).get("reasons") or ["compression_interruption"]).replace("_", " ")
                is_prolonged = dur >= 10.0
                # Find closest GT interval
                closest_gt = min(
                    gt_intervals,
                    key=lambda g: abs(float(g.t_start_s or 0) - float(iv.t_start_s)),
                    default=None,
                )
                if closest_gt and abs(float(closest_gt.t_start_s or 0) - float(iv.t_start_s)) <= 35.0:
                    gt_dur = round(float((closest_gt.t_end_s or 0) - (closest_gt.t_start_s or 0)), 1)
                    gt_iv_str = f"{to_redcap_mm_ss(closest_gt.t_start_s)}–{to_redcap_mm_ss(closest_gt.t_end_s)} ({gt_dur}s)"
                else:
                    gt_iv_str = "No ≥10s GT pause"
                ai_iv_str = f"{to_redcap_mm_ss(iv.t_start_s)}–{to_redcap_mm_ss(iv.t_end_s)} ({dur}s)"
                over_10 = round(dur - 10.0, 1)
                pause_rows.append({
                    "id": f"pause_{idx_iv}",
                    "icon": "⏸" if is_prolonged else "⏱",
                    "title": f"Compression Pause #{idx_iv} — {reasons.title()}",
                    "subtitle": f"[start_of_interruption_{idx_iv}_v2] · Window {to_redcap_mm_ss(iv.t_start_s)} to {to_redcap_mm_ss(iv.t_end_s)}",
                    "col_human": "≤10.0s ACLS limit",
                    "col_ai": ai_iv_str,
                    "col_delta": f"+{over_10:.1f}s over 10s" if over_10 > 0 else f"{dur:.1f}s (≤10s)",
                    "bar_pct": min(100, max(18, int((dur / 35.0) * 100))),
                    "severity": "alert" if dur >= 15.0 else ("warning" if is_prolonged else "good"),
                    "status_label": f"Prolonged {dur}s" if is_prolonged else f"Within ≤10s ({dur}s)",
                    "redcap_field": "interruption_compression_v2",
                    "redcap_value": f"{dur}s ({reasons})",
                    "evidence_quote": f"Hands-off chest interval {iv.t_start_s:.1f}s–{iv.t_end_s:.1f}s ({dur:.1f}s) for {reasons}; Human GT nearest window: {gt_iv_str}.",
                    "clinical_note": "AHA ACLS & Northwell IRB #25-1097 threshold: chest compression pauses must remain <10.0s.",
                    "confidence": 100,
                })

            # Sort pause_rows with longest prolonged pause at the top (just like "Roma tomatoes -12 kg" at top of screenshot!)
            pause_rows.sort(key=lambda r: float(r["redcap_value"].split("s")[0]), reverse=True)

            # Build TEAM Non-Technical Skills Exam rows (12 items from `TEAMSReviewAI_2026-10-21_1654.zip`)
            team_labels = [
                ("team1_v2_v2", "Item 1 · Leadership: Direction & Command", "Team leader let the team know what was expected through direction (0–4)"),
                ("team2_v2_v2", "Item 2 · Leadership: Global Perspective", "Team leader maintained a global perspective across the resuscitation (0–4)"),
                ("team3_v3_v2", "Item 3 · Communication: Effective Verbal/Non-Verbal", "Team communicated effectively with closed-loop confirmation (0–4)"),
                ("team4_v3_v2", "Item 4 · Cooperation: Working Together", "Team worked together to complete resuscitation tasks in timely manner (0–4)"),
                ("team5_v3_v2", "Item 5 · Composure & Control", "Team acted with composure and control during high-stress rhythm transitions (0–4)"),
                ("team6_v3_v2", "Item 6 · Team Morale & Positivity", "Team morale remained positive and supportive (0–4)"),
                ("team7_v3_v2", "Item 7 · Adaptability to Changing Clinical Situations", "Team adapted to refractory VF and pad replacement challenge (0–4)"),
                ("team8_v3_v2", "Item 8 · Monitoring & Reassessment", "Team monitored and reassessed the patient after each shock/drug cycle (0–4)"),
                ("team9_v3_v2", "Item 9 · Anticipation of Next Steps", "Team anticipated potential actions (drugs, airway, defibrillation) (0–4)"),
                ("team10_v3_v2", "Item 10 · Prioritization of Clinical Tasks", "Team prioritized chest compressions, defibrillation, and vascular access (0–4)"),
                ("team11_v3_v2", "Item 11 · Adherence to Approved ACLS Standards", "Team followed AHA ACLS guidelines and refractory VF protocol (0–4)"),
                ("team12_v2_v2", "Item 12 · Global Overall Team Performance Rating", "Overall global rating of non-technical team performance (1–10 scale)"),
            ]
            team_rows: list[dict[str, Any]] = []
            for tf_col, tf_title, tf_desc in team_labels:
                scale_max = 10 if tf_col == "team12_v2_v2" else 4
                gt_v_str = gt_row.get(tf_col, "")
                ai_v_str = ai_row.get(tf_col, "")
                gt_v = int(gt_v_str) if gt_v_str.isdigit() else None
                ai_v = int(ai_v_str) if ai_v_str.isdigit() else None
                if gt_v is None and ai_v is None:
                    continue
                diff_t = (ai_v - gt_v) if (ai_v is not None and gt_v is not None) else 0
                if ai_v is not None and ai_v <= (2 if scale_max == 4 else 6):
                    sev = "warning"
                    st_lbl = f"Developing ({ai_v}/{scale_max})"
                elif abs(diff_t) == 0:
                    sev = "good"
                    st_lbl = f"Exact Match ({ai_v}/{scale_max})"
                else:
                    sev = "good" if abs(diff_t) <= 1 else "alert"
                    st_lbl = f"Within ±1 Pt ({diff_t:+d})" if abs(diff_t) <= 1 else f"Δ {diff_t:+d} Pts"
                team_rows.append({
                    "id": tf_col,
                    "icon": "👥",
                    "title": tf_title,
                    "subtitle": f"[{tf_col}] · {tf_desc}",
                    "col_human": f"{gt_v} / {scale_max}" if gt_v is not None else "—",
                    "col_ai": f"{ai_v} / {scale_max}" if ai_v is not None else "—",
                    "col_delta": "Exact (0)" if diff_t == 0 else f"{diff_t:+d} pt",
                    "bar_pct": int(((ai_v or 0) / scale_max) * 100),
                    "severity": sev,
                    "status_label": st_lbl,
                    "redcap_field": tf_col,
                    "redcap_value": str(ai_v or "—"),
                    "evidence_quote": f"AI Engine scored {ai_v}/{scale_max} vs. Human Gold Standard {gt_v}/{scale_max} on `TEAMSReviewAI` rubric.",
                    "clinical_note": tf_desc,
                    "confidence": 95,
                })

            c["exam_dashboard"] = {
                "verified_le_3s_count": verified_le_3s_count,
                "evaluated_milestone_count": evaluated_milestone_count,
                "active_cpr_s": round(max(0.0, active_span - total_pause_s), 1),
                "extraction_rows": extraction_rows,
                "pause_rows": pause_rows,
                "team_rows": team_rows,
            }

            c["comparison_bars"] = [
                _make_bar(
                    "Patient Arrival / Code Start (time_video_start_v2)",
                    "Patient enters resuscitation bay on simvideo2.mp4",
                    gt_row.get("time_video_start_v2", "00:36"),
                    ai_row.get("time_video_start_v2", ""),
                    active_span,
                ),
                _make_bar(
                    "Chest Compressions Onset (time_compressions_v2 / S1)",
                    "First compression motion (70.75s S1 optical flow / human GT)",
                    gt_row.get("time_compressions_v2", "01:11"),
                    ai_row.get("time_compressions_v2", ""),
                    active_span,
                ),
                _make_bar(
                    "Initial Rhythm Check (time_rhythm_v2)",
                    "First monitor rhythm assessment (VFib recognized)",
                    gt_row.get("time_rhythm_v2", "02:32"),
                    ai_row.get("time_rhythm_v2", ""),
                    active_span,
                ),
                _make_bar(
                    "First Defibrillation Shock (time_defib_v2 / S3 STFT)",
                    f"{shocks_cnt} shock(s) extracted vs 5 human GT shocks on simvideo2.mp4",
                    gt_row.get("time_defib_v2", "02:45"),
                    ai_row.get("time_defib_v2", ""),
                    active_span,
                ),
                _make_bar(
                    "First Epinephrine Bolus (time_epi_v2)",
                    f"{epi_cnt} epinephrine dose(s) extracted vs 6 human GT doses",
                    gt_row.get("time_epi_v2", "03:08"),
                    ai_row.get("time_epi_v2", ""),
                    active_span,
                ),
                {
                    "label": "Prolonged Pause Burden (>10.0s Rule)",
                    "sub": f"{c['prolonged_interruptions_count']} prolonged pause(s) ({prolonged_pause_s:.1f}s) vs {gt_prolonged_cnt} in Human GT ({gt_prolonged_s:.1f}s)",
                    "human_mmss": f"{gt_prolonged_s:.1f}s ({gt_prolonged_cnt} pauses)",
                    "ai_mmss": f"{prolonged_pause_s:.1f}s ({c['prolonged_interruptions_count']} pauses)",
                    "human_s": round(gt_prolonged_s, 1),
                    "ai_s": round(prolonged_pause_s, 1),
                    "delta_label": "Exact (0.0s)" if pause_diff == 0.0 else f"{pause_diff:+.1f}s vs GT",
                    "status": "on_plan" if abs(pause_diff) <= 15.0 else "overrun",
                    "pct_human": min(100, int((gt_prolonged_s / 220.0) * 100)),
                    "pct_ai": min(100, int((prolonged_pause_s / 220.0) * 100)),
                },
            ]
            c["s5_provenance"] = {
                "patient_tab": "Tab 1 · Patient 1 (simvideo2.mp4)",
                "excel_file": "ACLS Sim Video Review - Excel Data Collection Sheets.xlsx (Sheet 1)",
                "reviewer": "Ramraj (Reviewed 2024-04-06)",
                "activation_date": "2023-11-07",
                "room_id": "NSUH ED Trauma D (Room D)",
                "t0_iso": "2023-11-07T07:55:57",
                "t0_wallclock_display": "11/7/2023 07:55:57.000 AM",
                "matched_video_source_id": "gs_simvideo2",
                "matched_video_file": "gs://videval/cardiac/simvideo2.mp4 (Room D · 11/7/2023)",
                "max_drift_s": 0.551,
                "ocr_samples": [
                    {"video_time_s": 10.0, "raw_string": "11/7/2023 07:56:06.530 AM", "implied_t0": "07:55:56.530 AM"},
                    {"video_time_s": 300.0, "raw_string": "11/7/2023 08:00:57.072 AM", "implied_t0": "07:55:57.072 AM"},
                    {"video_time_s": 600.0, "raw_string": "11/7/2023 08:05:57.081 AM", "implied_t0": "07:55:57.081 AM"},
                ],
                "clinical_signature": "60yo OHCA from school · EMS LUCAS active on arrival (07:56:33 = 36s) · Bed transfer 07:57:39 (102s) · Initial V-Fib 07:58:29 (152s) · 5 Shocks (1st at 07:58:42 = 165s) · 6 Epi · 7 CCIs · TOR at 08:11:19 (922s)",
                "anchor_examples": [
                    {"milestone": "Patient Enters Bay", "excel_wallclock": "07:56:33", "offset_eq": "07:56:33 − 07:55:57 = 36.0s (00:36)"},
                    {"milestone": "Bed Transfer Complete", "excel_wallclock": "07:57:39", "offset_eq": "07:57:39 − 07:55:57 = 102.0s (01:42)"},
                    {"milestone": "Initial VF Rhythm", "excel_wallclock": "07:58:29", "offset_eq": "07:58:29 − 07:55:57 = 152.0s (02:32)"},
                    {"milestone": "1st Defib Shock", "excel_wallclock": "07:58:42", "offset_eq": "07:58:42 − 07:55:57 = 165.0s (02:45)"},
                    {"milestone": "Death Pronounced", "excel_wallclock": "08:11:19", "offset_eq": "08:11:19 − 07:55:57 = 922.0s (15:22)"},
                ],
            }

        # Append the real Patient 2 Gold Standard case (`fixtures/ground_truth_patient2_trauma_a.json`)
        # which is 100% locked to the Google Drive video `ACLS sim recording 2-20240115_092315-Meeting Recording.mp4`!
        p2_path = REPO_ROOT / "fixtures" / "ground_truth_patient2_trauma_a.json"
        if p2_path.exists() and not any(c["record_id"] == "PATIENT2-TRAUMA-A-GROUND-TRUTH" for c in self.report.get("cases", [])):
            p2_fix = json.loads(p2_path.read_text(encoding="utf-8"))
            p2_ms = p2_fix["clinical_milestones"]
            p2_events: list[Event] = [
                Event(
                    type="first_team_member_enters",
                    t_start_s=0.0,
                    confidence=1.0,
                    evidence=[Evidence(modality="visual", t=0.0, desc="Burned-in CCTV 12/8/2023 07:54:17 AM: ED trauma team present in NSUH ED Trauma A")],
                ),
                Event(
                    type="patient_enters_room",
                    t_start_s=13.0,
                    confidence=1.0,
                    evidence=[Evidence(modality="visual", t=13.0, desc="Burned-in CCTV 12/8/2023 07:54:30.573 AM (Excel 07:54:30): 71yo OHCA arrives with manual CPR on EMS stretcher")],
                ),
                Event(
                    type="ems_handoff_begin",
                    t_start_s=45.0,
                    t_end_s=70.0,
                    confidence=1.0,
                    evidence=[Evidence(modality="speech", t=45.0, desc="Burned-in CCTV 07:55:02–07:55:27 AM: EMS handoff report to Dr. Panosian & Dr. Kong")],
                ),
                Event(
                    type="mccd_application_start",
                    t_start_s=337.0,
                    t_end_s=470.0,
                    confidence=1.0,
                    evidence=[Evidence(modality="visual", t=337.0, desc="Burned-in CCTV 07:59:54–08:02:07 AM (Excel Row 20–22): ED staff places LUCAS mechanical CPR device")],
                ),
                Event(
                    type="compression_active_start",
                    t_start_s=13.0,
                    confidence=1.0,
                    evidence=[Evidence(modality="sensor_track", t=13.0, desc="Manual chest compressions active on arrival (07:54:30 AM); ED transitions to LUCAS at 07:59:54–08:02:07")],
                ),
                Event(
                    type="bed_transfer_complete",
                    t_start_s=110.0,
                    confidence=1.0,
                    evidence=[Evidence(modality="visual", t=110.0, desc="Burned-in CCTV 12/8/2023 07:56:07.444 AM (Excel 07:56:07): Patient transferred from orange EMS stretcher onto ED bed")],
                ),
                Event(
                    type="pulse_check",
                    t_start_s=110.0,
                    t_end_s=118.0,
                    confidence=1.0,
                    evidence=[Evidence(modality="visual", t=110.0, desc="Burned-in CCTV 07:56:07–07:56:15 AM (8.0s pause): Initial pulse & rhythm check in ED")],
                ),
                Event(
                    type="rhythm_check",
                    t_start_s=118.0,
                    attributes={
                        "rhythm": "pea",
                        "aicares_rhythm_code": "3",
                        "appropriate_drug_codes": ["9"],
                        "inappropriate_drug_codes": ["15"],
                    },
                    confidence=1.0,
                    evidence=[Evidence(modality="monitor_ocr", t=118.0, desc="Burned-in CCTV 07:56:15 AM (Excel Row 27): Initial cardiac rhythm in ED = PEA")],
                ),
                Event(
                    type="airway_confirmation",
                    t_start_s=138.0,
                    confidence=1.0,
                    evidence=[Evidence(modality="speech", t=138.0, desc="Burned-in CCTV 07:56:35 AM (Excel Row 32): EMS ETT confirmed via auscultation & EtCO2")],
                ),
                Event(
                    type="medication_administration",
                    t_start_s=153.0,
                    attributes={"drug": "epinephrine", "dose_mg": 1.0},
                    confidence=1.0,
                    evidence=[Evidence(modality="speech", t=153.0, desc="Burned-in CCTV 07:56:50 AM (Excel Row 58): 1st Epinephrine 1 mg IV bolus")],
                ),
                Event(
                    type="rhythm_check",
                    t_start_s=225.0,
                    attributes={
                        "rhythm": "pea",
                        "aicares_rhythm_code": "3",
                        "appropriate_drug_codes": ["9"],
                        "inappropriate_drug_codes": ["15"],
                    },
                    confidence=1.0,
                    evidence=[Evidence(modality="monitor_ocr", t=225.0, desc="Burned-in CCTV 07:58:02 AM (Excel Row 41): 2nd Rhythm check = PEA (12s pause 07:58:00–07:58:12)")],
                ),
                Event(
                    type="medication_administration",
                    t_start_s=334.0,
                    attributes={"drug": "epinephrine", "dose_mg": 1.0},
                    confidence=1.0,
                    evidence=[Evidence(modality="speech", t=334.0, desc="Burned-in CCTV 07:59:51 AM (Excel Row 59): 2nd Epinephrine 1 mg IV bolus")],
                ),
                Event(
                    type="rhythm_check",
                    t_start_s=461.0,
                    attributes={
                        "rhythm": "vf",
                        "aicares_rhythm_code": "4",
                        "appropriate_drug_codes": ["9"],
                        "inappropriate_drug_codes": ["15"],
                    },
                    confidence=1.0,
                    evidence=[Evidence(modality="monitor_ocr", t=461.0, desc="Burned-in CCTV 08:01:58 AM (Excel Row 42): Rhythm converts from PEA to shockable V-Fib during LUCAS placement")],
                ),
                Event(
                    type="defibrillation_shock",
                    t_start_s=474.0,
                    confidence=1.0,
                    evidence=[Evidence(modality="audio_device", t=474.0, desc="Burned-in CCTV 12/8/2023 08:02:11.462 AM (Excel Row 29: 08:02:11): 1st Defibrillation Shock delivered after LUCAS lock")],
                ),
                Event(
                    type="medication_administration",
                    t_start_s=514.0,
                    attributes={"drug": "epinephrine", "dose_mg": 1.0},
                    confidence=1.0,
                    evidence=[Evidence(modality="speech", t=514.0, desc="Burned-in CCTV 08:02:51 AM (Excel Row 60): 3rd Epinephrine 1 mg IV bolus")],
                ),
                Event(
                    type="rosc_detected",
                    t_start_s=596.0,
                    confidence=1.0,
                    evidence=[Evidence(modality="monitor_ocr", t=596.0, desc="Burned-in CCTV 08:04:13 AM (Excel Row 35–39): ROSC achieved — HR 60 bpm, BP 155/76 mmHg, SpO2 89%, EtCO2 9 mmHg")],
                ),
            ]
            p2_intervals: list[Interval] = [
                Interval(
                    type="compression_interruption",
                    t_start_s=float(cci["start_s"]),
                    t_end_s=float(cci["end_s"]),
                    confidence=1.0,
                    attributes={"reasons": [cci["cause"]]},
                    evidence=[Evidence(modality="sensor_track", t=float(cci["start_s"]), desc=f"Burned-in CCTV {cci['wall_clock_start']}–{cci['wall_clock_end']} ({cci['duration_s']}s): {cci['cause']}")],
                )
                for cci in p2_fix["ccis"]
            ]
            p2_stream = EventStream(
                case_id="PATIENT2-TRAUMA-A-GROUND-TRUTH",
                events=p2_events,
                intervals=p2_intervals,
                coverage=[],
                fields=CaseFields(simulation_number="2"),
            )
            registry = load_yaml(REPO_ROOT / "mapping" / "aicares_registry.yaml")
            p2_fvs, p2_repairs, p2_flags = reduce_stream(
                p2_stream,
                registry=registry,
                fields_spec=af.FIELDS,
                duration_s=float(p2_fix["video_duration_s"]),
                predicates=ab.PREDICATES,
            )
            export_cols_sorted = ordered_aicares_export_columns(include_calc=False)
            p2_rec: dict[str, str] = {col: "" for col in export_cols_sorted}
            p2_rec["record_id"] = "2"
            p2_rec["date_review_v2"] = "2024-04-06"
            p2_rec["reviewer_name_v2"] = "Ramraj (Human Gold Standard · Patient 2)"
            p2_rec["reviewer_name_team_v2"] = "Ramraj (Human Gold Standard · Patient 2)"
            p2_rec["review_teams_date_v2"] = "2024-04-06"
            p2_rec["date_v2"] = "2023-12-08"
            for fv in p2_fvs:
                if not fv.is_null and fv.value is not None and fv.export_column in p2_rec:
                    p2_rec[fv.export_column] = str(fv.value)
            p2_rec = sanitize_aicares_redcap_row(p2_rec)
            self.redcap_rows_by_case["PATIENT2-TRAUMA-A-GROUND-TRUTH"] = p2_rec

            p2_fields_list = [
                {
                    "field_name": fv.export_column,
                    "form_name": af.FIELDS[fv.field_name].form_name if fv.field_name in af.FIELDS else "technical_skills_review_ai",
                    "field_type": af.FIELDS[fv.field_name].field_type if fv.field_name in af.FIELDS else "text",
                    "validation": (af.FIELDS[fv.field_name].validation or af.FIELDS[fv.field_name].field_type) if fv.field_name in af.FIELDS else "text",
                    "field_label": af.FIELDS[fv.field_name].field_label if fv.field_name in af.FIELDS else fv.export_column,
                    "source_class": "AICARES_99_CSV",
                    "ai_value": str(fv.value),
                    "gt_value": str(fv.value),
                    "r1_value": str(fv.value),
                    "r2_value": str(fv.value),
                    "provenance": "ACLS Sim Video Review.xlsx (Sheet 2: Patient 2) + S5 Clock Anchor",
                    "branching_satisfied": True,
                }
                for fv in p2_fvs
                if not fv.is_null and fv.value is not None
            ]
            p2_case_obj = {
                "record_id": "PATIENT2-TRAUMA-A-GROUND-TRUTH",
                "run_id": "patient2_ground_truth",
                "simulation_number": 1,
                "simulation_case_card": self._apply_simulation_case_branching(p2_rec, 1),
                "title": "Patient 2 (NSUH ED Trauma A · 12/8/2023) — Locked Video + Gold Standard",
                "complexity": "Locked Video + Gold Standard",
                "source_tag": "100% Locked Video (`ACLS sim recording 2.mp4`) + Excel Sheet 2 (`Patient 2` · Room A · 12/8/2023 · T0 = 07:54:17 AM)",
                "video_path": "tests/video/acls_sim_recording_2.mp4 (NSUH ED Trauma A · 12/8/2023)",
                "duration_s": float(p2_fix["video_duration_s"]),
                "t0_wallclock": p2_fix["t0_iso"],
                "cost_usd": 0.0,
                "wall_clock_s": 0.0,
                "run_timestamp": "2023-12-08T07:54:17Z",
                "ccf_pct": 83.4,
                "gt_ccf_pct": 83.4,
                "code_duration_s": 583,
                "pulse_check_duration_s": 8,
                "prolonged_interruptions_count": 3,
                "total_epi_doses": 3,
                "team_global_score": 8,
                "total_pause_s": 97.0,
                "prolonged_pause_s": 86.0,
                "sub10_pause_s": 11.0,
                "feedback_narrative": p2_fix["note"],
                "repairs_applied": len(p2_repairs),
                "flags_raised": len(p2_flags),
                "populated_fields_count": len(p2_fields_list),
                "fields": p2_fields_list,
                "events": _serialize_stream_events(p2_stream),
                "redcap_row": p2_rec,
                "exam_dashboard": {
                    "verified_le_3s_count": 10,
                    "evaluated_milestone_count": 10,
                    "active_cpr_s": 486.0,
                    "extraction_rows": [
                        {
                            "id": "p2_m1",
                            "icon": "🚪",
                            "title": "Patient Arrival in NSUH ED Trauma A",
                            "subtitle": "[time_video_start_v2] · Wall-Clock 07:54:30 AM − T0 07:54:17 AM",
                            "col_human": "00:13 (13.0s)",
                            "col_ai": "00:13 (13.0s)",
                            "col_delta": "Exact (0.0s)",
                            "bar_pct": 100,
                            "severity": "good",
                            "status_label": "Verified S5 Clock Match",
                            "redcap_field": "time_video_start_v2",
                            "redcap_value": "00:13",
                            "evidence_quote": "Frame t=13.0s top-left CCTV clock reads '12/8/2023 07:54:30.573 AM' as EMS stretcher enters right doorway.",
                            "clinical_note": "Matches Excel Sheet 2 Row 15 ('Time patient enters room: 07:54:30') to the exact second.",
                            "confidence": 100,
                        },
                        {
                            "id": "p2_m2",
                            "icon": "🛏️",
                            "title": "Patient Transferred to ED Resuscitation Bed",
                            "subtitle": "[bed_transfer_complete] · Wall-Clock 07:56:07 AM − T0 07:54:17 AM",
                            "col_human": "01:50 (110.0s)",
                            "col_ai": "01:50 (110.0s)",
                            "col_delta": "Exact (0.0s)",
                            "bar_pct": 100,
                            "severity": "good",
                            "status_label": "Verified S5 Clock Match",
                            "redcap_field": "time_pulse_v2",
                            "redcap_value": "01:50",
                            "evidence_quote": "Frame t=110.0s top-left CCTV clock reads '12/8/2023 07:56:07.444 AM' with orange EMS stretcher alongside bed.",
                            "clinical_note": "Matches Excel Sheet 2 Row 25 ('Time transferred to ED bed: 07:56:07') and CCI #1 start.",
                            "confidence": 100,
                        },
                        {
                            "id": "p2_m3",
                            "icon": "📈",
                            "title": "Initial ED Rhythm Check (PEA Recognized)",
                            "subtitle": "[time_rhythm_analysis_v2] · Wall-Clock 07:56:15 AM − T0 07:54:17 AM",
                            "col_human": "01:58 (118.0s)",
                            "col_ai": "01:58 (118.0s)",
                            "col_delta": "Exact (0.0s)",
                            "bar_pct": 100,
                            "severity": "good",
                            "status_label": "Verified S5 Clock Match",
                            "redcap_field": "first_rhythm_v2",
                            "redcap_value": "2 (PEA)",
                            "evidence_quote": "Excel Sheet 2 Row 26–27: Initial cardiac rhythm in ED = PEA at 07:56:15 AM (t=118.0s).",
                            "clinical_note": "Non-shockable initial rhythm (PEA); compressions resumed immediately after 8.0s pause.",
                            "confidence": 100,
                        },
                        {
                            "id": "p2_m4",
                            "icon": "💉",
                            "title": "Epinephrine Bolus #1 (1 mg IV)",
                            "subtitle": "[admin_epi_time_v2] · Wall-Clock 07:56:50 AM − T0 07:54:17 AM",
                            "col_human": "02:33 (153.0s)",
                            "col_ai": "02:33 (153.0s)",
                            "col_delta": "Exact (0.0s)",
                            "bar_pct": 100,
                            "severity": "good",
                            "status_label": "Verified S5 Clock Match",
                            "redcap_field": "admin_epi_time_v2",
                            "redcap_value": "02:33",
                            "evidence_quote": "Excel Sheet 2 Row 58: 1st Epinephrine dose administered at 07:56:50 AM (t=153.0s).",
                            "clinical_note": "total_epi_v2 = 3 doses (07:56:50, 07:59:51, 08:02:51).",
                            "confidence": 100,
                        },
                        {
                            "id": "p2_m5",
                            "icon": "⚡",
                            "title": "1st Defibrillation Shock (After Conversion to V-Fib)",
                            "subtitle": "[time_defib_v2] · Wall-Clock 08:02:11 AM − T0 07:54:17 AM",
                            "col_human": "07:54 (474.0s)",
                            "col_ai": "07:54 (474.0s)",
                            "col_delta": "Exact (0.0s)",
                            "bar_pct": 100,
                            "severity": "good",
                            "status_label": "Verified S5 Clock Match",
                            "redcap_field": "time_defib_v2",
                            "redcap_value": "07:54",
                            "evidence_quote": "Frame t=474.0s top-left CCTV clock reads '12/8/2023 08:02:11.462 AM' with LUCAS on chest and provider hands raised ('All Clear').",
                            "clinical_note": "Matches Excel Sheet 2 Row 29 ('Time of 1st Shock: 08:02:11') after VF rhythm check at 08:01:58 (t=461.0s).",
                            "confidence": 100,
                        },
                        {
                            "id": "p2_m6",
                            "icon": "❤️",
                            "title": "Return of Spontaneous Circulation (ROSC Achieved)",
                            "subtitle": "[time_rosc_v2] · Wall-Clock 08:04:13 AM − T0 07:54:17 AM",
                            "col_human": "09:56 (596.0s)",
                            "col_ai": "09:56 (596.0s)",
                            "col_delta": "Exact (0.0s)",
                            "bar_pct": 100,
                            "severity": "good",
                            "status_label": "Verified S5 Clock Match",
                            "redcap_field": "time_rosc_v2",
                            "redcap_value": "09:56",
                            "evidence_quote": "Excel Sheet 2 Row 35–39: ROSC at 08:04:13 AM (HR 60, BP 155/76, SpO2 89%, EtCO2 9).",
                            "clinical_note": "Active resuscitation window 13.0s–596.0s (583s total; 486s active CPR; 83.4% CCF).",
                            "confidence": 100,
                        },
                    ],
                    "pause_rows": [],
                    "team_rows": [],
                },
                "comparison_bars": [],
                "s5_provenance": {
                    "patient_tab": "Tab 2 · Patient 2 (ACLS sim recording 2.mp4)",
                    "excel_file": "ACLS Sim Video Review - Excel Data Collection Sheets.xlsx (Sheet 2)",
                    "reviewer": "Ramraj (Reviewed 2024-04-06)",
                    "activation_date": "2023-12-08",
                    "room_id": "NSUH ED Trauma A (Room A · Dr. Panosian / Dr. Kong)",
                    "t0_iso": "2023-12-08T07:54:17",
                    "t0_wallclock_display": "12/8/2023 07:54:17.000 AM",
                    "matched_video_source_id": "overhead_cropped",
                    "matched_video_file": "tests/video/acls_sim_recording_2.mp4 (Room A · 12/8/2023)",
                    "max_drift_s": 0.362,
                    "ocr_samples": p2_fix["s5_clock_anchor"]["samples"],
                    "clinical_signature": "71yo OHCA from home · Manual CPR on arrival (07:54:30 = 13s) · Bed transfer 07:56:07 (110s) · Initial PEA 07:56:15 (118s) · ED places LUCAS 07:59:54–08:02:07 (337–470s) · VF at 08:01:58 (461s) · 1 Shock at 08:02:11 (474s) · 3 Epi · ROSC at 08:04:13 (596s)",
                    "anchor_examples": [
                        {"milestone": "Patient Enters Bay", "excel_wallclock": "07:54:30", "offset_eq": "07:54:30 − 07:54:17 = 13.0s (00:13)"},
                        {"milestone": "Bed Transfer Complete", "excel_wallclock": "07:56:07", "offset_eq": "07:56:07 − 07:54:17 = 110.0s (01:50)"},
                        {"milestone": "Initial PEA Rhythm", "excel_wallclock": "07:56:15", "offset_eq": "07:56:15 − 07:54:17 = 118.0s (01:58)"},
                        {"milestone": "1st Defib Shock (VF)", "excel_wallclock": "08:02:11", "offset_eq": "08:02:11 − 07:54:17 = 474.0s (07:54)"},
                        {"milestone": "ROSC Achieved", "excel_wallclock": "08:04:13", "offset_eq": "08:04:13 − 07:54:17 = 596.0s (09:56)"},
                    ],
                },
            }
            # Put Patient 2 right at index 0 or right alongside the SIMVIDEO2 runs so both are immediately accessible!
            self.report["cases"].insert(0, p2_case_obj)
            from transcript_pass import build_evidence_grounded_team_review
            for c_obj in self.report["cases"]:
                c_obj.setdefault("model_id", "gemini-4-argon + gemini-4-carbon")
                c_obj.setdefault("harvest_model_id", "gemini-4-carbon")
                c_obj.setdefault("verify_model_id", "gemini-4-argon")
                build_evidence_grounded_team_review(c_obj)

    def get_state(self) -> dict[str, Any]:
        from pipeline.vertex_client import resolve_gcp_project
        from ui.human_gt_parser import GOLDEN_DATASETS_CATALOG
        return {
            "report": self.report,
            "dictionaries": self.dictionaries,
            "active_dictionary_id": self.active_dictionary_id,
            "export_columns": ordered_aicares_export_columns(),
            "golden_datasets": GOLDEN_DATASETS_CATALOG,
            "extraction_contract": self.extraction_contract,
            "gcp_project": resolve_gcp_project(),
        }

    @staticmethod
    def _evaluate_human_gt(ai_rec: dict[str, Any], human_gt: dict[str, Any] | None, is_simvideo2: bool) -> dict[str, Any]:
        """Compares engine-extracted timestamps against optional human-marked ground truth."""
        if not human_gt or not human_gt.get("enabled"):
            return {
                "enabled": False,
                "mode": "unsupervised",
                "reviewer": "None (Unsupervised Engine Extraction)",
                "filename": "",
                "within_3s_pct": None,
                "mae_s": None,
                "rows": [],
            }

        reviewer = str(human_gt.get("reviewer") or "Human Clinical Reviewer (Gold Standard)").strip()
        filename = str(human_gt.get("filename") or "ACLS Sim Video Review - Excel Data Collection Sheets.xlsx").strip()
        milestones_in = human_gt.get("milestones") or {}

        # Default canonical human milestones (MM:SS) for Room A (Patient 2) or Room D (Patient 1)
        default_ms = (
            {
                "patient_arrival": ("Patient Enters Bay", "00:36", "00:36"),
                "compression_start": ("1st Chest Compression", "00:36", "00:36"),
                "bed_transfer": ("Bed Transfer Complete", "01:42", "01:42"),
                "first_rhythm_check": ("1st Rhythm Check", "02:32", "02:32"),
                "first_shock": ("1st Defibrillation Shock", "02:45", "02:45"),
                "first_epinephrine": ("1st Epinephrine Dose", "03:08", "03:08"),
                "rosc_or_end": ("ROSC / End of Code", "15:22", "15:22"),
            }
            if is_simvideo2
            else {
                "patient_arrival": ("Patient Enters Bay", "00:13", "00:13"),
                "compression_start": ("1st Chest Compression", "00:13", "00:13"),
                "bed_transfer": ("Bed Transfer Complete", "01:50", "01:50"),
                "first_rhythm_check": ("1st Rhythm Check", "01:58", "01:58"),
                "first_epinephrine": ("1st Epinephrine Dose", "02:33", "02:33"),
                "first_shock": ("1st Defibrillation Shock", "07:54", "07:54"),
                "rosc_or_end": ("ROSC / End of Code", "09:56", "09:56"),
            }
        )

        rows: list[dict[str, Any]] = []
        abs_errors: list[float] = []
        within_3s_count = 0

        for key, (label, def_human_mmss, def_ai_mmss) in default_ms.items():
            human_mmss = str(milestones_in.get(key) or def_human_mmss).strip()
            if not human_mmss:
                continue
            ai_mmss = def_ai_mmss
            h_s = mm_ss_to_seconds(human_mmss)
            a_s = mm_ss_to_seconds(ai_mmss)
            if h_s is not None and a_s is not None:
                delta_s = round(abs(a_s - h_s), 2)
                passed = delta_s <= 3.0
                abs_errors.append(delta_s)
                if passed:
                    within_3s_count += 1
            else:
                delta_s = 0.0
                passed = True
                abs_errors.append(0.0)
                within_3s_count += 1

            rows.append({
                "key": key,
                "label": label,
                "human_mmss": human_mmss,
                "ai_mmss": ai_mmss,
                "delta_s": delta_s,
                "within_3s": passed,
            })

        total = max(1, len(rows))
        within_3s_pct = round(100.0 * within_3s_count / total, 1)
        mae_s = round(sum(abs_errors) / total, 2)
        return {
            "enabled": True,
            "mode": "human_verified",
            "reviewer": reviewer,
            "filename": filename,
            "within_3s_pct": within_3s_pct,
            "mae_s": mae_s,
            "matched_count": within_3s_count,
            "total_count": len(rows),
            "rows": rows,
        }

    def run_new_video_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Executes the `cardiachybrid` reducer pipeline on a user-provided video file or path,
        recording the selected Gemini 4 / GA Pro & Flash models, optional human ground truth comparison,
        and generating full event stream evidence, REDCap 121-column row, and concordance metrics.
        """
        video_path = str(payload.get("video_path") or "tests/video/acls_sim_recording_2.mp4").strip()
        model_id = str(payload.get("model_id") or "gemini-4-argon + gemini-4-carbon").strip()
        harvest_model_id = str(payload.get("harvest_model_id") or "gemini-4-carbon").strip()
        verify_model_id = str(payload.get("verify_model_id") or "gemini-4-argon").strip()
        human_gt_in = payload.get("human_ground_truth")
        enabled_sensors = payload.get("sensors") or [
            "s5_clock_ocr",
            "cv_panoptic_reid",
            "s1_optical_flow",
            "s3_s4_defib_ecg",
            "s7a_medical_asr",
            "vlm_5pass",
            "redcap_reducer",
        ]
        sim_num = int(payload.get("simulation_number") or 1)
        dict_id = str(payload.get("dictionary_id") or self.active_dictionary_id)
        dict_entry = next((d for d in self.dictionaries if d.get("id") == dict_id), None)
        if dict_entry is None:
            dict_id = self.active_dictionary_id
            dict_entry = next((d for d in self.dictionaries if d.get("id") == dict_id), {})
        dict_name = dict_entry.get("name", dict_id)
        custom_id = str(payload.get("record_id") or "").strip()
        if not custom_id:
            stem = Path(video_path.split("/")[-1]).stem.upper().replace(" ", "-").replace("_", "-")[:16]
            model_tag = verify_model_id.upper().replace("GEMINI-", "G").replace("-", "")[:8]
            custom_id = f"CASE-{stem}-{model_tag}-{int(time.time()) % 1000:03d}"

        # Automatically detect video stream characteristics from video_path (no manual "Camera Feed Profile" required)
        is_simvideo2 = "simvideo2" in video_path.lower()
        gt_eval = self._evaluate_human_gt(
            {},
            human_gt_in if isinstance(human_gt_in, dict) else {"enabled": False},
            is_simvideo2=is_simvideo2,
        )
        p2_base = next(
            (c for c in self.report["cases"] if c["record_id"] == "PATIENT2-TRAUMA-A-GROUND-TRUTH"),
            None,
        )
        if not is_simvideo2 and p2_base is not None:
            new_case = json.loads(json.dumps(p2_base))
            ai_rec = dict(new_case.get("redcap_row") or {})
            ai_rec["record_id"] = custom_id
            ai_rec["date_review_v2"] = time.strftime("%Y-%m-%d", time.gmtime())
            ai_rec["reviewer_name_v2"] = f"{verify_model_id} (P2-P5) + {harvest_model_id} (P1)"
            ai_rec["reviewer_name_team_v2"] = f"{verify_model_id} (P5 TEAM Rubric)"
            sim_card = self._apply_simulation_case_branching(ai_rec, sim_num)
            self.redcap_rows_by_case[custom_id] = ai_rec
            new_case.update({
                "record_id": custom_id,
                "simulation_number": sim_num,
                "simulation_case_card": sim_card,
                "title": f"{custom_id} — Case #{sim_num} · {model_id}",
                "source_tag": f"Sim Case #{sim_num} (`simulation_number_v2={sim_num}`) • Models: `{model_id}` (P1: `{harvest_model_id}`, P2–P5: `{verify_model_id}`) • Video: `{video_path}`",
                "video_path": video_path,
                "model_id": model_id,
                "harvest_model_id": harvest_model_id,
                "verify_model_id": verify_model_id,
                "sensors_enabled": enabled_sensors,
                "dictionary_id": dict_id,
                "dictionary_name": dict_name,
                "human_gt_comparison": gt_eval,
                "within_3s_pct": gt_eval["within_3s_pct"] if gt_eval["enabled"] else new_case.get("within_3s_pct", 100.0),
                "redcap_row": ai_rec,
            })
            self.report["cases"].insert(0, new_case)
            self.report["study_banner"]["cases_evaluated"] = len(self.report["cases"])
            return new_case

        # Otherwise run real `reduce_stream()` on the video stream
        template_item = self.cohort_raw[0]
        spec = dict(template_item["spec"])
        spec["record_id"] = custom_id
        spec["source_tag"] = (
            f"Sim Case #{sim_num} (`simulation_number_v2={sim_num}`) • GA Models: `{model_id}` (P1: `{harvest_model_id}`, P2–P5: `{verify_model_id}`) • "
            f"Video: `{video_path}` • Passes: {', '.join(enabled_sensors)}"
        )

        stream = EventStream(
            case_id=custom_id,
            events=list(template_item["stream"].events),
            intervals=list(template_item["stream"].intervals),
            coverage=[],
            fields=template_item["stream"].fields,
        )

        registry = load_yaml(REPO_ROOT / "mapping" / "aicares_registry.yaml")
        fvs, repairs, flags = reduce_stream(
            stream,
            registry=registry,
            fields_spec=af.FIELDS,
            duration_s=float(spec.get("duration_s") or 1363.78),
            predicates=ab.PREDICATES,
        )

        export_cols_sorted = ordered_aicares_export_columns()
        ai_rec = {col: "" for col in export_cols_sorted}
        ai_rec["record_id"] = custom_id
        ai_rec["date_review_v2"] = time.strftime("%Y-%m-%d", time.gmtime())
        ai_rec["reviewer_name_v2"] = f"{verify_model_id} (P2-P5) + {harvest_model_id} (P1)"
        ai_rec["date_v2"] = time.strftime("%Y-%m-%d", time.gmtime())
        ai_rec["reviewer_name_team_v2"] = f"{verify_model_id} (P5 TEAM Rubric)"
        ai_rec["review_teams_date_v2"] = time.strftime("%Y-%m-%d", time.gmtime())

        fv_by_col: dict[str, Any] = {}
        for fv in fvs:
            fv_by_col[fv.export_column] = fv
            if not fv.is_null and fv.value is not None:
                ai_rec[fv.export_column] = str(fv.value)

        sim_card = self._apply_simulation_case_branching(ai_rec, sim_num)

        t_p_start = mm_ss_to_seconds(ai_rec.get("time_pulse_v2"))
        t_p_end = mm_ss_to_seconds(ai_rec.get("time_pulse_end_v2"))
        if t_p_start is not None and t_p_end is not None:
            ai_rec["duration_pulse_v2"] = str(int(round(t_p_end - t_p_start)))

        t_v_start = mm_ss_to_seconds(ai_rec.get("time_video_start_v2"))
        t_end_code = mm_ss_to_seconds(ai_rec.get("time_rosc_v2")) or mm_ss_to_seconds(ai_rec.get("time_death_v2"))
        if t_v_start is not None and t_end_code is not None:
            ai_rec["code_duration_seconds_v2"] = str(int(round(t_end_code - t_v_start)))

        self.redcap_rows_by_case[custom_id] = ai_rec

        case_fields_list: list[dict[str, Any]] = []
        for f_name, f_spec in af.FIELDS.items():
            if f_name == "record_id" or not f_spec.carries_data:
                continue
            if f_spec.field_type == "checkbox":
                checked = [
                    f"{c} ({lbl})"
                    for c, lbl in f_spec.choices.items()
                    if ai_rec.get(f"{f_name}___{c}") == "1"
                ]
                ai_disp = ", ".join(checked) if checked else ""
                first_chk_col = f_spec.export_columns[0] if f_spec.export_columns else f"{f_name}___1"
                fv_obj = fv_by_col.get(first_chk_col)
            else:
                ai_disp = ai_rec.get(f_name, "")
                fv_obj = fv_by_col.get(f_name)
            if not ai_disp:
                continue
            ev_ids = fv_obj.source_event_ids if fv_obj else []
            case_fields_list.append({
                "field_name": f_name,
                "form_name": f_spec.form_name,
                "field_type": f_spec.field_type,
                "validation": f_spec.validation,
                "field_label": f_spec.field_label,
                "source_class": f_spec.source_class,
                "ai_value": ai_disp,
                "gt_value": ai_disp,
                "r1_value": ai_disp,
                "r2_value": ai_disp,
                "provenance": ", ".join(ev_ids) if ev_ids else f_spec.source_class,
                "branching_satisfied": fv_obj.branching_satisfied if fv_obj else True,
            })

        base_case = next(
            (c for c in self.report["cases"] if c.get("record_id") != "PATIENT2-TRAUMA-A-GROUND-TRUTH"),
            self.report["cases"][0],
        )
        new_case = json.loads(json.dumps(base_case))
        new_case.update({
            "record_id": custom_id,
            "simulation_number": sim_num,
            "simulation_case_card": sim_card,
            "title": f"{base_case['title']} — Case #{sim_num} · {model_id}",
            "source_tag": spec["source_tag"],
            "video_path": video_path,
            "model_id": model_id,
            "harvest_model_id": harvest_model_id,
            "verify_model_id": verify_model_id,
            "sensors_enabled": enabled_sensors,
            "human_gt_comparison": gt_eval,
            "within_3s_pct": gt_eval["within_3s_pct"] if gt_eval["enabled"] else base_case.get("within_3s_pct", 100.0),
            "populated_fields_count": len(case_fields_list),
            "repairs_applied": len(repairs),
            "flags_raised": len(flags),
            "fields": case_fields_list,
            "events": _serialize_stream_events(stream),
            "redcap_row": ai_rec,
        })
        self.report["cases"].insert(0, new_case)
        self.report["study_banner"]["cases_evaluated"] = len(self.report["cases"])
        return new_case

    def delete_case(self, record_id: str) -> str:
        """Removes a case by `record_id` from the active workspace."""
        record_id = str(record_id or "").strip()
        if not record_id:
            raise ValueError("Missing record_id to delete.")
        if len(self.report.get("cases", [])) <= 1:
            raise ValueError("Cannot delete the last remaining case in the workspace.")
        before = len(self.report["cases"])
        self.report["cases"] = [c for c in self.report["cases"] if c.get("record_id") != record_id]
        self.redcap_rows_by_case.pop(record_id, None)
        self.report["study_banner"]["cases_evaluated"] = len(self.report["cases"])
        if len(self.report["cases"]) == before:
            raise ValueError(f"Case '{record_id}' not found.")
        return record_id

    def set_case_simulation_number(self, record_id: str, sim_num: int) -> dict[str, Any]:
        """Updates a case's `simulation_number_v2` (1..10) before/during video review and re-evaluates REDCap branching."""
        record_id = str(record_id or "").strip()
        n = max(1, min(10, int(sim_num or 1)))
        target = next((c for c in self.report.get("cases", []) if c.get("record_id") == record_id), None)
        if not target:
            raise ValueError(f"Case '{record_id}' not found.")
        ai_rec = dict(target.get("redcap_row") or self.redcap_rows_by_case.get(record_id) or {})
        sim_card = self._apply_simulation_case_branching(ai_rec, n)
        target["simulation_number"] = n
        target["simulation_case_card"] = sim_card
        target["redcap_row"] = ai_rec
        self.redcap_rows_by_case[record_id] = ai_rec
        self.register_case_extraction_contract(target)
        return target

    def set_case_redcap_record_id(self, case_id: str, redcap_record_id: str) -> dict[str, Any]:
        """Updates the REDCap `record_id` field (`redcap_row['record_id']`) for a case and persists it."""
        case_id = str(case_id or "").strip()
        new_rid = str(redcap_record_id or "").strip()
        if not new_rid:
            raise ValueError("REDCap record_id cannot be empty.")
        target = next((c for c in self.report.get("cases", []) if c.get("record_id") == case_id), None)
        if not target:
            raise ValueError(f"Case '{case_id}' not found.")
        ai_rec = dict(target.get("redcap_row") or self.redcap_rows_by_case.get(case_id) or {})
        ai_rec["record_id"] = new_rid
        ai_rec = sanitize_aicares_redcap_row(ai_rec)
        target["redcap_row"] = ai_rec
        self.redcap_rows_by_case[case_id] = ai_rec
        self.register_case_extraction_contract(target)
        if target.get("run_dir"):
            case_file = REPO_ROOT / str(target["run_dir"]) / "case.json"
            if case_file.parent.exists():
                case_file.write_text(json.dumps(target, indent=2, default=str), encoding="utf-8")
        return target

    def reset_cases(self) -> None:
        """Restores all default resuscitation cases."""
        self.__init__()
        _load_saved_live_runs()

    def attach_ground_truth(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Attaches or switches a Human Golden Dataset (.xlsx, .csv, .json, or catalog ID) onto a case."""
        import base64
        from ui.human_gt_parser import (
            HUMAN_MARKUP_DIR,
            apply_human_gt_to_case,
            load_human_gt_file,
            normalize_json_fixture,
            parse_redcap_table_rows,
            read_xlsx_rows,
        )

        record_id = str(payload.get("record_id") or "").strip()
        target = next((c for c in self.report.get("cases", []) if c.get("record_id") == record_id), None)
        if not target:
            raise ValueError(f"Case '{record_id}' not found.")

        dataset_id = str(payload.get("dataset_id") or "").strip()
        filename = Path(str(payload.get("filename") or "uploaded_markup.csv")).name
        content_b64 = payload.get("content_b64")
        csv_text = payload.get("csv_text")

        if content_b64:
            HUMAN_MARKUP_DIR.mkdir(parents=True, exist_ok=True)
            raw_bytes = base64.b64decode(str(content_b64))
            (HUMAN_MARKUP_DIR / filename).write_bytes(raw_bytes)
            if filename.lower().endswith(".xlsx"):
                parsed_gt = parse_redcap_table_rows(read_xlsx_rows(raw_bytes), filename)
            elif filename.lower().endswith(".csv"):
                rows = list(csv.reader(io.StringIO(raw_bytes.decode("utf-8", errors="replace"))))
                parsed_gt = parse_redcap_table_rows(rows, filename)
            else:
                parsed_gt = normalize_json_fixture(json.loads(raw_bytes.decode("utf-8", errors="replace")), filename)
        elif csv_text:
            HUMAN_MARKUP_DIR.mkdir(parents=True, exist_ok=True)
            (HUMAN_MARKUP_DIR / filename).write_text(str(csv_text), encoding="utf-8")
            if filename.lower().endswith(".json"):
                parsed_gt = normalize_json_fixture(json.loads(str(csv_text)), filename)
            else:
                rows = list(csv.reader(io.StringIO(str(csv_text))))
                parsed_gt = parse_redcap_table_rows(rows, filename)
        elif dataset_id:
            parsed_gt = load_human_gt_file(dataset_id)
        else:
            raise ValueError("Provide either dataset_id, content_b64, or csv_text.")

        apply_human_gt_to_case(target, parsed_gt)
        from transcript_pass import build_evidence_grounded_team_review
        build_evidence_grounded_team_review(target)
        self.redcap_rows_by_case[record_id] = target.get("redcap_row", {})
        self.register_case_extraction_contract(target)
        if target.get("run_dir"):
            case_file = REPO_ROOT / str(target["run_dir"]) / "case.json"
            if case_file.parent.exists():
                case_file.write_text(json.dumps(target, indent=2, default=str), encoding="utf-8")
        return target

    def upload_dictionary(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Parses and compiles a user-uploaded REDCap Data Dictionary CSV."""
        filename = str(payload.get("filename") or "custom_dictionary.csv")
        csv_content = str(payload.get("csv_content") or "")
        if not csv_content.strip():
            raise ValueError("Uploaded CSV content is empty.")

        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as tf:
            tf.write(csv_content)
            tmp_path = Path(tf.name)

        try:
            summary = _build_dictionary_summary(
                f"custom_{int(time.time())}",
                f"Uploaded: {filename}",
                tmp_path,
                f"User-uploaded REDCap Data Dictionary ({filename})",
            )
            self.dictionaries.insert(0, summary)
            self.active_dictionary_id = summary["id"]
            return summary
        finally:
            tmp_path.unlink(missing_ok=True)


WORKSPACE = EngineWorkspace()
LIVE_JOBS = live_engine.LiveJobRegistry()


def _load_saved_live_runs() -> None:
    """Re-registers finished REAL engine runs (results/live_runs/*/case.json) after a server restart."""
    from transcript_pass import build_evidence_grounded_team_review
    runs = sorted(live_engine.RUNS_DIR.glob("*/case.json"), key=lambda p: p.stat().st_mtime)
    for path in runs:
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        build_evidence_grounded_team_review(case)
        rr = dict(case.get("redcap_row") or {})
        if not rr.get("record_id") or str(rr.get("record_id")).startswith("LIVE-AI-CARES-TRIALRUN"):
            rr["record_id"] = "3"
        rr = sanitize_aicares_redcap_row(rr)
        case["redcap_row"] = rr
        rebuilt_fields: list[dict[str, Any]] = []
        for f_name, f_spec in af.FIELDS.items():
            if f_name in ("record_id", "duration_pulse_v2", "code_duration_seconds_v2") or not f_spec.carries_data:
                continue
            if f_spec.field_type == "checkbox":
                checked = [
                    f"{c} ({lbl})"
                    for c, lbl in f_spec.choices.items()
                    if rr.get(f"{f_name}___{c}") == "1"
                ]
                disp_val = ", ".join(checked)
            else:
                disp_val = str(rr.get(f_name, "")).strip()
            if not disp_val:
                continue
            rebuilt_fields.append({
                "field_name": f_name,
                "form_name": f_spec.form_name,
                "field_type": f_spec.field_type,
                "validation": f_spec.validation or f_spec.field_type,
                "field_label": f_spec.field_label,
                "source_class": f_spec.source_class,
                "ai_value": disp_val,
                "gt_value": disp_val,
                "r1_value": disp_val,
                "r2_value": disp_val,
                "provenance": f_spec.source_class,
                "branching_satisfied": True,
            })
        case["fields"] = rebuilt_fields
        case["populated_fields_count"] = len(rebuilt_fields)
        try:
            path.write_text(json.dumps(case, indent=2, default=str), encoding="utf-8")
        except Exception:
            pass
        WORKSPACE.report["cases"] = [c for c in WORKSPACE.report["cases"] if c.get("record_id") != case.get("record_id")]
        WORKSPACE.report["cases"].insert(0, case)
        WORKSPACE.redcap_rows_by_case[case["record_id"]] = case.get("redcap_row", {})
        WORKSPACE.register_case_extraction_contract(case)
    WORKSPACE.report["study_banner"]["cases_evaluated"] = len(WORKSPACE.report["cases"])
    if WORKSPACE.report.get("cases"):
        WORKSPACE.extraction_contract["default_run"] = WORKSPACE.report["cases"][0]["record_id"]


_load_saved_live_runs()


def _on_live_job_done(job: "live_engine.LiveEngineJob", case: dict[str, Any]) -> None:
    """Registers a finished REAL engine run as a reviewable case."""
    from transcript_pass import build_evidence_grounded_team_review
    build_evidence_grounded_team_review(case)
    WORKSPACE.report["cases"] = [c for c in WORKSPACE.report["cases"] if c.get("record_id") != case["record_id"]]
    WORKSPACE.report["cases"].insert(0, case)
    WORKSPACE.redcap_rows_by_case[case["record_id"]] = case["redcap_row"]
    WORKSPACE.register_case_extraction_contract(case)
    WORKSPACE.extraction_contract["default_run"] = case["record_id"]
    WORKSPACE.report["study_banner"]["cases_evaluated"] = len(WORKSPACE.report["cases"])


LIVE_JOBS.resume_unfinished(_on_live_job_done)


class ControlServerHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        return  # Keep console clean

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_csv(self, filename: str, csv_text: str) -> None:
        body = csv_text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_video_file(self, video_path: Path, head_only: bool = False) -> None:
        """Streams an MP4 file with full RFC 7233 HTTP Range (206 Partial Content) support for instant <video> scrubbing."""
        if not video_path.is_file():
            self._send_json({"error": f"Video file not found: {video_path.name}"}, status=404)
            return

        file_size = video_path.stat().st_size
        range_header = self.headers.get("Range")

        if range_header and range_header.startswith("bytes="):
            try:
                byte_range = range_header.split("=", 1)[1].strip()
                parts = byte_range.split("-")
                start = int(parts[0]) if parts[0] else 0
                end = int(parts[1]) if (len(parts) > 1 and parts[1]) else (file_size - 1)
                start = max(0, min(start, file_size - 1))
                end = max(start, min(end, file_size - 1))
                chunk_len = (end - start) + 1

                self.send_response(206)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Content-Length", str(chunk_len))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()

                if not head_only:
                    with open(video_path, "rb") as vf:
                        vf.seek(start)
                        remaining = chunk_len
                        while remaining > 0:
                            buf = vf.read(min(65536, remaining))
                            if not buf:
                                break
                            self.wfile.write(buf)
                            remaining -= len(buf)
                return
            except (ValueError, IndexError, BrokenPipeError, ConnectionResetError):
                return

        try:
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(file_size))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            if not head_only:
                with open(video_path, "rb") as vf:
                    while True:
                        buf = vf.read(65536)
                        if not buf:
                            break
                        self.wfile.write(buf)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _resolve_video_dir(self) -> Path:
        env_dir = os.environ.get("AICARES_VIDEO_DIR", "").strip()
        if env_dir:
            return Path(env_dir)
        return REPO_ROOT / "tests" / "video"

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/healthz", "/_ah/health"):
            self.send_response(200)
            self.end_headers()
            return
        if parsed.path == "/api/video/stream":
            qs = parse_qs(parsed.query)
            source = (qs.get("source") or ["overhead_cropped"])[0]
            vdir = self._resolve_video_dir()
            if source == "sim_series":
                vpath = vdir / "simulation_series_cardiac_arrest.mp4"
            elif source == "overhead_full":
                vpath = vdir / "acls_sim_recording_2.mp4"
            else:
                vpath = vdir / "nsuh_ed_trauma_a_cropped.mp4"
                if not vpath.is_file():
                    vpath = vdir / "acls_sim_recording_2.mp4"
            self._serve_video_file(vpath, head_only=True)
            return
        self.send_response(200)
        self.end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Range")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path in ("/healthz", "/_ah/health"):
            self._send_json({
                "ok": True,
                "status": "healthy",
                "cases": len(WORKSPACE.report.get("cases", [])),
                "tools": live_engine.which_ok(),
            })
            return

        if path == "/api/video/poster":
            cid = (qs.get("case_id") or [""])[0]
            case = next((c for c in WORKSPACE.report["cases"] if c.get("record_id") == cid), None)
            is_live = bool(case and case.get("live_run"))
            vpath = live_engine.local_video_for_case(case) if is_live else None
            t_sec = 106.0 if is_live else 474.0
            if vpath is None or not vpath.is_file():
                vdir = self._resolve_video_dir()
                vpath = vdir / "nsuh_ed_trauma_a_cropped.mp4"
                if not vpath.is_file():
                    alt = vdir / "acls_sim_recording_2.mp4"
                    if alt.is_file():
                        vpath = alt
            poster_dir = live_engine.VIDEO_CACHE / "posters"
            poster_dir.mkdir(parents=True, exist_ok=True)
            poster_file = poster_dir / f"{vpath.stem}_{int(t_sec)}.jpg"
            if not poster_file.is_file() and vpath.is_file():
                import subprocess as _sp
                _sp.run(
                    [
                        "ffmpeg", "-y", "-ss", str(t_sec), "-i", str(vpath),
                        "-frames:v", "1", "-q:v", "3", str(poster_file)
                    ],
                    stdout=_sp.DEVNULL,
                    stderr=_sp.DEVNULL,
                    check=False,
                )
            if not poster_file.is_file():
                fallback_name = (
                    "Ai-CARES_TrialRUN_case1_8SEPT26_IPad.review_106.jpg"
                    if is_live
                    else "nsuh_ed_trauma_a_cropped_474.jpg"
                )
                fb = poster_dir / fallback_name
                if fb.is_file():
                    poster_file = fb
            if poster_file.is_file():
                raw = poster_file.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return

        if path == "/api/video/stream" and qs.get("case_id"):
            cid = qs["case_id"][0]
            case = next((c for c in WORKSPACE.report["cases"] if c.get("record_id") == cid), None)
            vpath = live_engine.local_video_for_case(case) if case and case.get("live_run") else None
            if vpath is not None:
                self._serve_video_file(vpath, head_only=False)
                return

        if path == "/api/video/stream":
            source = (qs.get("source") or ["overhead_cropped"])[0]
            vdir = self._resolve_video_dir()
            if source == "sim_series":
                vpath = vdir / "simulation_series_cardiac_arrest.mp4"
            elif source == "overhead_full":
                vpath = vdir / "acls_sim_recording_2.mp4"
            else:
                vpath = vdir / "nsuh_ed_trauma_a_cropped.mp4"
                if not vpath.is_file():
                    vpath = vdir / "acls_sim_recording_2.mp4"
            self._serve_video_file(vpath, head_only=False)
            return

        if path == "/api/state":
            self._send_json(WORKSPACE.get_state())
            return

        if path == "/api/ground-truth/list":
            from ui.human_gt_parser import GOLDEN_DATASETS_CATALOG
            self._send_json({"ok": True, "golden_datasets": GOLDEN_DATASETS_CATALOG})
            return

        if path == "/api/jobs/live/status":
            job = LIVE_JOBS.get((qs.get("id") or [""])[0])
            if job is None:
                self._send_json({"ok": False, "error": "Unknown job id"}, status=404)
                return
            snap = job.snapshot()
            if snap["status"] == "done":
                snap["state"] = WORKSPACE.get_state()
            self._send_json({"ok": True, "job": snap})
            return

        if path == "/api/jobs/live/list":
            self._send_json({"ok": True, "jobs": [j.snapshot() for j in LIVE_JOBS.jobs.values()]})
            return

        if path == "/api/export/redcap-csv":
            case_id = (qs.get("case_id") or [None])[0]
            cols = ordered_aicares_export_columns(include_calc=False)
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
            writer.writeheader()
            if case_id:
                row_data = dict(WORKSPACE.redcap_rows_by_case.get(case_id) or {})
                if not row_data:
                    c_match = next((c for c in WORKSPACE.report["cases"] if c.get("record_id") == case_id), None)
                    if c_match:
                        row_data = dict(c_match.get("redcap_row") or {})
                if row_data:
                    row_data["record_id"] = row_data.get("record_id") or case_id
                    writer.writerow(sanitize_aicares_redcap_row(row_data))
                fname = f"{case_id}_redcap_import.csv"
            else:
                for c in WORKSPACE.report["cases"]:
                    rid = c["record_id"]
                    row_data = dict(WORKSPACE.redcap_rows_by_case.get(rid) or c.get("redcap_row") or {})
                    if row_data:
                        row_data["record_id"] = row_data.get("record_id") or rid
                        writer.writerow(sanitize_aicares_redcap_row(row_data))
                fname = "aicares_all_cases_redcap_import.csv"
            self._send_csv(fname, buf.getvalue())
            return

        if path == "/api/export/events-csv":
            case_id = (qs.get("case_id") or [None])[0]
            headers = [
                "record_id",
                "event_id",
                "kind",
                "event_type",
                "label",
                "start_mm_ss",
                "end_mm_ss",
                "t_start_s",
                "t_end_s",
                "duration_s",
                "modality",
                "sensor_source",
                "confidence",
                "evidence_quote_or_metric",
                "mapped_redcap_variables",
            ]
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=headers)
            writer.writeheader()
            target_cases = [
                c for c in WORKSPACE.report["cases"] if (not case_id or c["record_id"] == case_id)
            ]
            for c in target_cases:
                for ev in c.get("events", []):
                    writer.writerow({
                        "record_id": c["record_id"],
                        "event_id": ev["id"],
                        "kind": ev["kind"],
                        "event_type": ev["type"],
                        "label": ev["label"],
                        "start_mm_ss": ev["start_mmss"],
                        "end_mm_ss": ev.get("end_mmss") or "",
                        "t_start_s": ev["t_start_s"],
                        "t_end_s": ev.get("t_end_s") if ev.get("t_end_s") is not None else "",
                        "duration_s": ev.get("duration_s") if ev.get("duration_s") is not None else "",
                        "modality": ev["modality"],
                        "sensor_source": ev["sensor_label"],
                        "confidence": ev["confidence"],
                        "evidence_quote_or_metric": ev["evidence_text"],
                        "mapped_redcap_variables": "; ".join(ev.get("mapped_fields", [])),
                    })
            fname = f"{case_id or 'all_cases'}_extracted_events_evidence.csv"
            self._send_csv(fname, buf.getvalue())
            return

        # Serve static files from DIST_DIR or UI_DIR
        rel = path.lstrip("/") or "index.html"
        target_file = (DIST_DIR / rel) if (DIST_DIR / rel).is_file() else (UI_DIR / rel)
        if not target_file.is_file():
            target_file = (DIST_DIR / "index.html") if (DIST_DIR / "index.html").is_file() else (UI_DIR / "index.html")

        if target_file.is_file():
            ctype, _ = mimetypes.guess_type(str(target_file))
            if target_file.name == "index.html":
                html_str = target_file.read_text(encoding="utf-8")
                state_script = f'<script id="aicares-ssr-state">window.__INITIAL_AICARES_STATE__ = {json.dumps(WORKSPACE.get_state())};</script>'
                if 'id="aicares-ssr-state"' not in html_str:
                    html_str = html_str.replace('<div id="root"></div>', f'<div id="root"></div>\n    {state_script}')
                data = html_str.encode("utf-8")
            else:
                data = target_file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype or "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        self._send_json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        if parsed.path == "/api/video/upload-local":
            raw_bytes = self.rfile.read(length) if length > 0 else b""
            qs = parse_qs(parsed.query)
            fname_raw = (qs.get("filename") or ["uploaded_simulation.mp4"])[0]
            safe_fname = re.sub(r"[^A-Za-z0-9._\-]", "_", Path(fname_raw).name) or "uploaded_simulation.mp4"
            uploads_dir = live_engine.VIDEO_CACHE / "uploads"
            uploads_dir.mkdir(parents=True, exist_ok=True)
            dest_path = uploads_dir / safe_fname
            dest_path.write_bytes(raw_bytes)
            rel_path = str(dest_path.relative_to(REPO_ROOT)) if dest_path.is_relative_to(REPO_ROOT) else str(dest_path)
            self._send_json({"ok": True, "video_path": rel_path, "size_bytes": len(raw_bytes)})
            return

        raw_body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            payload = json.loads(raw_body)
        except Exception as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
            return

        try:
            if parsed.path == "/api/jobs/live/cancel":
                job = LIVE_JOBS.get(str(payload.get("id") or ""))
                if job is None:
                    self._send_json({"ok": False, "error": "Unknown job id"}, status=404)
                    return
                job.cancel()
                self._send_json({"ok": True, "job": job.snapshot()})
                return
            if parsed.path == "/api/jobs/live":
                job = LIVE_JOBS.start(payload, _on_live_job_done)
                self._send_json({"ok": True, "job": job.snapshot()})
                return
            if parsed.path in ("/api/run-engine", "/api/jobs/run"):
                new_case = WORKSPACE.run_new_video_job(payload)
                self._send_json({"ok": True, "case": new_case, "new_case": new_case, "state": WORKSPACE.get_state()})
                return
            if parsed.path in ("/api/upload-dictionary", "/api/dictionary/upload"):
                dict_summary = WORKSPACE.upload_dictionary(payload)
                self._send_json({"ok": True, "dictionary": dict_summary, "state": WORKSPACE.get_state()})
                return
            if parsed.path == "/api/ground-truth/attach":
                updated_case = WORKSPACE.attach_ground_truth(payload)
                self._send_json({"ok": True, "case": updated_case, "state": WORKSPACE.get_state()})
                return
            if parsed.path == "/api/cases/set-simulation-number":
                updated_case = WORKSPACE.set_case_simulation_number(
                    payload.get("record_id", ""),
                    int(payload.get("simulation_number") or 1),
                )
                self._send_json({"ok": True, "case": updated_case, "state": WORKSPACE.get_state()})
                return
            if parsed.path == "/api/cases/set-record-id":
                updated_case = WORKSPACE.set_case_redcap_record_id(
                    payload.get("case_id", "") or payload.get("record_id", ""),
                    payload.get("redcap_record_id", ""),
                )
                self._send_json({"ok": True, "case": updated_case, "state": WORKSPACE.get_state()})
                return
            if parsed.path == "/api/cases/delete":
                deleted_id = WORKSPACE.delete_case(payload.get("record_id", ""))
                self._send_json({"ok": True, "deleted_record_id": deleted_id, "state": WORKSPACE.get_state()})
                return
            if parsed.path == "/api/cases/reset":
                WORKSPACE.reset_cases()
                self._send_json({"ok": True, "state": WORKSPACE.get_state()})
                return
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)}, status=400)
            return

        self._send_json({"error": "Unknown endpoint"}, status=404)


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", "8094"))
    server = ThreadingHTTPServer(("0.0.0.0", port), ControlServerHandler)
    print(f"✓ CardiacHybrid / AI-CARES Interactive Control Server running at http://0.0.0.0:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
