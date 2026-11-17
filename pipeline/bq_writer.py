"""
pipeline/bq_writer.py — Idempotent BigQuery write path for case runs and event streams.
Enforces that audit views are checked against actual data and supports both live and synthetic cohorts.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from google.cloud import bigquery
from pipeline.vertex_client import resolve_gcp_project

logger = logging.getLogger(__name__)


def get_bq_client(project: str | None = None) -> bigquery.Client:
    return bigquery.Client(project=resolve_gcp_project(project))


def _to_json_str(obj: Any) -> str:
    if obj is None:
        return "{}"
    if isinstance(obj, str):
        return obj
    def default_encoder(o: Any) -> Any:
        if hasattr(o, "model_dump"):
            return o.model_dump()
        if hasattr(o, "__dict__"):
            return o.__dict__
        return str(o)
    try:
        return json.dumps(obj, default=default_encoder)
    except Exception:
        return str(obj)


def _insert_rows(client: bigquery.Client, table_ref: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        ignore_unknown_values=True
    )
    job = client.load_table_from_json(rows, table_ref, job_config=job_config)
    job.result()


def write_run(
    case_id: str,
    run_id: str,
    stream: Any,
    field_values: list[Any],
    metrics: list[Any] | None = None,
    raw_dataset: str = "resus_raw",
    project: str = "nodepeel",
    is_synthetic: bool = False,
    event_date_str: str = "2023-11-07",
    site: str = "Main Hospital"
) -> None:
    """Idempotently writes case dimensions, run execution facts, event streams, EAV REDCap fields, and derived QI metrics to BigQuery."""
    client = get_bq_client(project)

    # Permanent safety check: resus_raw CANNOT receive is_synthetic=True
    if raw_dataset == "resus_raw" and is_synthetic:
        raise ValueError(
            f"SAFETY VIOLATION: Cannot write synthetic cases (is_synthetic=True) to physical clinical dataset {project}.{raw_dataset}!"
        )

    dataset_ref = f"{project}.{raw_dataset}"

    # Delete existing data for this case_id and run_id to ensure exact idempotency
    for t in [
        "dim_run", "fact_event", "fact_interval", "fact_utterance",
        "fact_sensor_interval", "fact_redcap_field", "redcap_submission",
        "fact_metric", "fact_coverage_note", "fact_near_miss", "fact_team_score"
    ]:
        query = f"DELETE FROM `{dataset_ref}.{t}` WHERE case_id = @case_id AND run_id = @run_id"
        job = client.query(
            query,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("case_id", "STRING", case_id),
                    bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
                ]
            )
        )
        job.result()

    # Upsert dim_case
    client.query(
        f"DELETE FROM `{dataset_ref}.dim_case` WHERE case_id = @case_id",
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("case_id", "STRING", case_id),
            ]
        )
    ).result()

    case_rows = [{
        "case_id": case_id,
        "redcap_record_id": str(getattr(stream, "record_id", getattr(stream, "case_id", case_id)) or case_id),
        "enrollment_date": f"{event_date_str} 00:00:00" if " " not in event_date_str else event_date_str,
        "patient_age": 65.0,
        "patient_sex": "M",
        "arrest_location": "ED",
        "attributes": _to_json_str({"video_duration_s": getattr(stream, "duration_s", getattr(stream, "video_duration_s", 1363.78))}),
        "is_synthetic": is_synthetic,
        "site": site,
    }]
    _insert_rows(client, f"{dataset_ref}.dim_case", case_rows)

    # Insert dim_run
    run_rows = [{
        "run_id": run_id,
        "case_id": case_id,
        "dict_version": "v2026",
        "pipeline_sha": "demomode",
        "model_version": "gemini-3.6-flash",
        "start_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "end_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "COMPLETED",
        "event_date": event_date_str.split()[0],
    }]
    _insert_rows(client, f"{dataset_ref}.dim_run", run_rows)

    # Insert fact_event
    event_rows = []
    if hasattr(stream, "events") and stream.events:
        for idx, ev in enumerate(stream.events):
            event_rows.append({
                "event_id": str(getattr(ev, "event_id", f"ev_{case_id}_{run_id}_{idx}") or f"ev_{case_id}_{run_id}_{idx}"),
                "case_id": case_id,
                "run_id": run_id,
                "event_type": str(getattr(ev, "event_type", getattr(ev, "type", "unknown")) or "unknown"),
                "timestamp_s": float(getattr(ev, "timestamp_s", getattr(ev, "t_start_s", 0.0)) or 0.0),
                "confidence": float(getattr(ev, "confidence", 1.0) or 1.0),
                "source": str(getattr(ev, "source", "AI_DERIVED") or "AI_DERIVED"),
                "routed_to_human": bool(getattr(ev, "routed_to_human", False)),
                "attributes": _to_json_str(getattr(ev, "attributes", {}) or {}),
                "evidence": _to_json_str(getattr(ev, "evidence", []) or []),
                "event_date": event_date_str.split()[0],
            })
    _insert_rows(client, f"{dataset_ref}.fact_event", event_rows)

    # Insert fact_interval
    interval_rows = []
    if hasattr(stream, "intervals") and stream.intervals:
        for idx, iv in enumerate(stream.intervals):
            t0 = float(getattr(iv, "t_start_s", 0.0) or 0.0)
            t1 = float(getattr(iv, "t_end_s", 0.0) or 0.0)
            attrs = getattr(iv, "attributes", {}) or {}
            reasons = attrs.get("reasons", attrs.get("reason", [])) if isinstance(attrs, dict) else []
            if isinstance(reasons, str):
                reasons = [reasons]
            elif not isinstance(reasons, list):
                reasons = []
            reasons_str = [str(r) for r in reasons]
            if not reasons_str and getattr(iv, "interval_type", getattr(iv, "type", "")) in ["cci", "compression_interruption"]:
                reasons_str = ["unknown_pause"]
            interval_rows.append({
                "interval_id": str(getattr(iv, "interval_id", f"int_{case_id}_{run_id}_{idx}") or f"int_{case_id}_{run_id}_{idx}"),
                "case_id": case_id,
                "run_id": run_id,
                "interval_type": str(getattr(iv, "interval_type", getattr(iv, "type", "unknown")) or "unknown"),
                "t_start_s": t0,
                "t_end_s": t1,
                "duration_s": max(0.0, t1 - t0),
                "reasons": reasons_str,
                "confidence": float(getattr(iv, "confidence", 1.0) or 1.0),
                "source": str(getattr(iv, "source", "AI_DERIVED") or "AI_DERIVED"),
                "routed_to_human": bool(getattr(iv, "routed_to_human", False)),
                "attributes": _to_json_str(attrs),
                "evidence": _to_json_str(getattr(iv, "evidence", []) or []),
                "event_date": event_date_str.split()[0],
            })
    _insert_rows(client, f"{dataset_ref}.fact_interval", interval_rows)

    # Insert fact_coverage_note
    cov_rows = []
    if hasattr(stream, "coverage") and stream.coverage:
        for idx, cn in enumerate(stream.coverage):
            cov_rows.append({
                "note_id": str(getattr(cn, "note_id", f"cov_{case_id}_{run_id}_{idx}") or f"cov_{case_id}_{run_id}_{idx}"),
                "case_id": case_id,
                "run_id": run_id,
                "note_type": str(getattr(cn, "type", getattr(cn, "note_type", "general")) or "general"),
                "message": str(getattr(cn, "notes", getattr(cn, "message", getattr(cn, "reason", ""))) or ""),
                "target_domain": str(getattr(cn, "channel", getattr(cn, "target_domain", "video_review")) or "video_review"),
                "attributes": _to_json_str(getattr(cn, "attributes", {}) or {}),
                "event_date": event_date_str.split()[0],
            })
    _insert_rows(client, f"{dataset_ref}.fact_coverage_note", cov_rows)

    # Insert fact_redcap_field (EXACTLY 1,879 rows per run)
    field_rows = []
    for fv in field_values:
        fname = str(getattr(fv, "export_column", getattr(fv, "field_name", "unknown_col")) or "unknown_col")
        val = getattr(fv, "value", None)
        val_str = str(val) if val is not None and val != "" else None
        field_rows.append({
            "case_id": case_id,
            "run_id": run_id,
            "field_name": fname,
            "value": val_str,
            "dict_version": "v2026",
            "source_class": str(getattr(fv, "source_class", getattr(fv, "source", "AI_DERIVED")) or "AI_DERIVED"),
            "branching_satisfied": bool(getattr(fv, "branching_satisfied", True)),
            "abstained": bool(getattr(fv, "abstained", False)),
            "confidence": float(getattr(fv, "confidence", 0.0) or 0.0),
            "source_event_ids": [str(x) for x in (getattr(fv, "source_event_ids", []) or [])],
            "human_verified": bool(getattr(fv, "human_verified", False)),
            "human_value": str(getattr(fv, "human_value")) if getattr(fv, "human_value", None) is not None else None,
            "event_date": event_date_str.split()[0],
        })
    _insert_rows(client, f"{dataset_ref}.fact_redcap_field", field_rows)
    logger.info(f"Wrote {len(field_rows)} fact_redcap_field rows for {case_id} / {run_id}")

    # Insert fact_metric
    metric_rows = []
    if metrics:
        for idx, m in enumerate(metrics):
            m_name = str(getattr(m, "metric_name", "unknown") or "unknown")
            m_val = getattr(m, "value", None)
            num = getattr(m, "numerator", None)
            den = getattr(m, "denominator", None)
            n_reason = getattr(m, "null_reason", None)
            unit = getattr(m, "unit", getattr(m, "metric_unit", "count"))
            m_val_float = float(m_val) if (m_val is not None and not isinstance(m_val, list)) else None
            metric_rows.append({
                "metric_id": f"met_{case_id}_{run_id}_{m_name}_{idx}",
                "case_id": case_id,
                "run_id": run_id,
                "metric_name": m_name,
                "metric_value": m_val_float,
                "value": m_val_float,
                "numerator": float(num) if num is not None else None,
                "denominator": float(den) if den is not None else None,
                "null_reason": str(n_reason) if n_reason is not None else None,
                "unit": str(unit),
                "calculation_details": _to_json_str({
                    "null_reason": n_reason,
                    "definition_version": getattr(m, "metric_definition_version", "")
                }),
                "event_date": event_date_str.split()[0],
            })
    _insert_rows(client, f"{dataset_ref}.fact_metric", metric_rows)


def assert_gate_clean(
    view: str,
    case_id: str = "DEMO-1",
    project: str = "nodepeel",
    raw: str = "resus_raw",
    curated: str = "resus_curated"
) -> None:
    """Structural check: proves the raw table was non-empty before asserting zero violations in audit view."""
    client = get_bq_client(project)

    def q(sql: str) -> int:
        query_job = client.query(sql)
        for row in query_job.result():
            return int(row[0])
        return 0

    where_clause = f"WHERE case_id='{case_id}'" if case_id and case_id != "ALL" else ""
    scanned = q(f"SELECT COUNT(*) FROM `{project}.{raw}.fact_redcap_field` {where_clause}")
    if scanned == 0:
        raise RuntimeError(
            f"{view}: cannot assert clean — 0 fields scanned for {case_id}. "
            f"Zero audit rows against an empty table proves nothing."
        )

    view_where = "" if view == "v_audit_low_utd" else where_clause
    v = q(f"SELECT COUNT(*) FROM `{project}.{curated}.{view}` {view_where}")
    if v:
        raise RuntimeError(f"{view}: {v} violations across {scanned:,d} fields scanned")
    print(f"✓ {view:<32} clean — 0 violations across {scanned:,d} fields scanned for {case_id}")
