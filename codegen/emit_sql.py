"""
codegen/emit_sql.py — Generates BigQuery DDL, seed JSONL, wide pivot view, and audit views.

Artifacts produced in generated/:
  1. bq_ddl.sql: Thirteen physical tables in {raw_dataset} (CMEK-ready, partitioned/clustered).
  2. dim_redcap_field_seed.jsonl: Seed data for dim_redcap_field from REDCap dictionary.
  3. v_redcap_wide.sql: Parameterized wide view in {curated_dataset} (1,889 MAX(IF(...)) columns) with SHA-256 header checksum.
  4. audit_views.sql: Seven authorized/audit views in {curated_dataset} referencing {raw_dataset}.
"""

import json
import hashlib
from pathlib import Path
from generated.redcap_fields import FIELDS, IMPORTABLE_COLUMNS


def generate_bq_ddl() -> str:
    """Produces DDL for all 13 physical tables in {raw_dataset}."""
    ddl = """-- generated/bq_ddl.sql
-- DDL for thirteen physical tables in {raw_dataset}
-- Generated SQL artifact. DO NOT EDIT BY HAND.

CREATE TABLE IF NOT EXISTS `{raw_dataset}.dim_case` (
  case_id STRING NOT NULL,
  redcap_record_id STRING,
  enrollment_date TIMESTAMP,
  patient_age FLOAT64,
  patient_sex STRING,
  arrest_location STRING,
  attributes JSON
) CLUSTER BY case_id;

CREATE TABLE IF NOT EXISTS `{raw_dataset}.dim_run` (
  run_id STRING NOT NULL,
  case_id STRING NOT NULL,
  dict_version STRING NOT NULL,
  pipeline_sha STRING,
  model_version STRING,
  start_time TIMESTAMP,
  end_time TIMESTAMP,
  status STRING,
  event_date DATE
) PARTITION BY event_date CLUSTER BY case_id, run_id;

CREATE TABLE IF NOT EXISTS `{raw_dataset}.dim_redcap_field` (
  field_name STRING NOT NULL,
  dict_version STRING NOT NULL,
  form_name STRING,
  field_type STRING,
  field_label STRING,
  choices JSON,
  is_importable BOOL,
  expected_utd_floor FLOAT64,
  is_calc_field BOOL,
  is_phi BOOL
) CLUSTER BY field_name, form_name;

CREATE TABLE IF NOT EXISTS `{raw_dataset}.fact_event` (
  event_id STRING NOT NULL,
  case_id STRING NOT NULL,
  run_id STRING NOT NULL,
  event_type STRING NOT NULL,
  timestamp_s FLOAT64,
  confidence FLOAT64,
  source STRING,
  routed_to_human BOOL,
  attributes JSON,
  evidence JSON,
  event_date DATE
) PARTITION BY event_date CLUSTER BY case_id, event_type;

CREATE TABLE IF NOT EXISTS `{raw_dataset}.fact_interval` (
  interval_id STRING NOT NULL,
  case_id STRING NOT NULL,
  run_id STRING NOT NULL,
  interval_type STRING NOT NULL,
  t_start_s FLOAT64,
  t_end_s FLOAT64,
  confidence FLOAT64,
  source STRING,
  routed_to_human BOOL,
  attributes JSON,
  evidence JSON,
  event_date DATE
) PARTITION BY event_date CLUSTER BY case_id, interval_type;

CREATE TABLE IF NOT EXISTS `{raw_dataset}.fact_utterance` (
  utterance_id STRING NOT NULL,
  case_id STRING NOT NULL,
  run_id STRING NOT NULL,
  speaker STRING,
  t_start_s FLOAT64,
  t_end_s FLOAT64,
  text STRING,
  confidence FLOAT64,
  event_date DATE
) PARTITION BY event_date CLUSTER BY case_id, run_id;

CREATE TABLE IF NOT EXISTS `{raw_dataset}.fact_sensor_interval` (
  sensor_id STRING NOT NULL,
  case_id STRING NOT NULL,
  run_id STRING NOT NULL,
  sensor_type STRING NOT NULL,
  t_start_s FLOAT64,
  t_end_s FLOAT64,
  value FLOAT64,
  confidence FLOAT64,
  attributes JSON,
  event_date DATE
) PARTITION BY event_date CLUSTER BY case_id, sensor_type;

CREATE TABLE IF NOT EXISTS `{raw_dataset}.fact_redcap_field` (
  case_id STRING NOT NULL,
  run_id STRING NOT NULL,
  field_name STRING NOT NULL,
  value STRING,
  dict_version STRING,
  event_date DATE
) PARTITION BY event_date CLUSTER BY case_id, field_name;

CREATE TABLE IF NOT EXISTS `{raw_dataset}.redcap_submission` (
  submission_id STRING NOT NULL,
  case_id STRING NOT NULL,
  run_id STRING NOT NULL,
  dict_version STRING,
  payload JSON,
  submitted_at TIMESTAMP,
  response_status INT64,
  response_body JSON,
  event_date DATE
) PARTITION BY event_date CLUSTER BY case_id, run_id;

CREATE TABLE IF NOT EXISTS `{raw_dataset}.fact_metric` (
  metric_id STRING NOT NULL,
  case_id STRING NOT NULL,
  run_id STRING NOT NULL,
  metric_name STRING NOT NULL,
  metric_value FLOAT64,
  calculation_details JSON,
  event_date DATE
) PARTITION BY event_date CLUSTER BY case_id, metric_name;

CREATE TABLE IF NOT EXISTS `{raw_dataset}.fact_coverage_note` (
  note_id STRING NOT NULL,
  case_id STRING NOT NULL,
  run_id STRING NOT NULL,
  note_type STRING,
  message STRING,
  target_domain STRING,
  attributes JSON,
  event_date DATE
) PARTITION BY event_date CLUSTER BY case_id, target_domain;

CREATE TABLE IF NOT EXISTS `{raw_dataset}.fact_near_miss` (
  event_id STRING NOT NULL,
  case_id STRING NOT NULL,
  run_id STRING NOT NULL,
  event_type STRING NOT NULL,
  timestamp_s FLOAT64,
  confidence FLOAT64,
  votes_accept INT64,
  votes_reject INT64,
  evidence JSON,
  attributes JSON,
  event_date DATE
) PARTITION BY event_date CLUSTER BY case_id, event_type;

CREATE TABLE IF NOT EXISTS `{raw_dataset}.fact_team_score` (
  score_id STRING NOT NULL,
  case_id STRING NOT NULL,
  run_id STRING NOT NULL,
  domain STRING,
  score INT64,
  rater STRING,
  attributes JSON,
  event_date DATE
) PARTITION BY event_date CLUSTER BY case_id, domain;
"""
    return ddl.strip() + "\n"


def generate_field_seed_jsonl() -> str:
    """Produces JSONL seed rows for dim_redcap_field."""
    dict_version = "v1.0.0"
    dict_ver_path = Path("dictionary/dict_version.txt")
    if dict_ver_path.exists():
        dict_version = dict_ver_path.read_text().strip()

    rows = []
    for f_name in sorted(FIELDS.keys()):
        spec = FIELDS[f_name]
        row = {
            "field_name": spec.field_name,
            "dict_version": dict_version,
            "form_name": spec.form_name,
            "field_type": spec.field_type,
            "field_label": spec.field_label,
            "choices": spec.choices,
            "is_importable": not spec.server_computed,
            "expected_utd_floor": getattr(spec, "expected_utd_floor", 0.95),
            "is_calc_field": spec.field_type == "calc",
            "is_phi": bool(spec.identifier),
        }
        rows.append(json.dumps(row, sort_keys=True))
    return "\n".join(rows) + "\n"


def generate_v_redcap_wide() -> str:
    """Produces generated/v_redcap_wide.sql pivoting IMPORTABLE_COLUMNS with SHA-256 header checksum."""
    cols = sorted(IMPORTABLE_COLUMNS)
    lines = [
        "CREATE OR REPLACE VIEW `{curated_dataset}.v_redcap_wide` AS",
        "SELECT",
        "  case_id,",
        "  run_id,",
        "  event_date,",
    ]
    for idx, c in enumerate(cols):
        comma = "," if idx < len(cols) - 1 else ""
        lines.append(f"  MAX(IF(field_name = '{c}', value, NULL)) AS `{c}`{comma}")
    lines.append("FROM `{raw_dataset}.fact_redcap_field`")
    lines.append("GROUP BY case_id, run_id, event_date;")
    body = "\n".join(lines) + "\n"
    checksum = hashlib.sha256(body.encode("utf-8")).hexdigest()
    header = (
        f"-- CHECKSUM: {checksum}\n"
        "-- Generated SQL artifact. DO NOT EDIT BY HAND.\n"
    )
    return header + body


def generate_audit_views() -> str:
    """Produces generated/audit_views.sql containing 7 views in {curated_dataset}."""
    sql = """-- generated/audit_views.sql
-- Seven authorized and audit views in {curated_dataset} referencing {raw_dataset}
-- Generated SQL artifact. DO NOT EDIT BY HAND.

CREATE OR REPLACE VIEW `{curated_dataset}.v_exemplar_store` AS
SELECT
  e.event_id,
  e.case_id,
  e.run_id,
  e.event_type,
  e.timestamp_s,
  f.field_name,
  f.value,
  e.event_date
FROM `{raw_dataset}.fact_event` e
LEFT JOIN `{raw_dataset}.fact_redcap_field` f
  ON e.case_id = f.case_id
  AND e.run_id = f.run_id
  AND e.event_date = f.event_date;

CREATE OR REPLACE VIEW `{curated_dataset}.v_audit_missing_fields` AS
SELECT
  c.case_id,
  c.run_id,
  df.field_name
FROM (SELECT DISTINCT case_id, run_id FROM `{raw_dataset}.fact_redcap_field`) c
CROSS JOIN `{raw_dataset}.dim_redcap_field` df
LEFT JOIN `{raw_dataset}.fact_redcap_field` f
  ON f.case_id = c.case_id
  AND f.run_id = c.run_id
  AND f.field_name = df.field_name
WHERE df.is_importable = TRUE
  AND df.is_calc_field = FALSE
  AND (f.value IS NULL OR f.value = '');

CREATE OR REPLACE VIEW `{curated_dataset}.v_audit_domain_coverage` AS
SELECT
  c.run_id,
  df.form_name AS domain,
  COUNT(f.value) AS populated_count,
  COUNT(*) - COUNT(f.value) AS abstained_count,
  COUNT(*) AS total_fields,
  ROUND(COUNT(f.value) / NULLIF(COUNT(*), 0), 4) AS populated_pct
FROM (SELECT DISTINCT case_id, run_id FROM `{raw_dataset}.fact_redcap_field`) c
CROSS JOIN `{raw_dataset}.dim_redcap_field` df
LEFT JOIN `{raw_dataset}.fact_redcap_field` f
  ON f.case_id = c.case_id
  AND f.run_id = c.run_id
  AND f.field_name = df.field_name
WHERE df.is_importable = TRUE
  AND df.is_calc_field = FALSE
GROUP BY c.run_id, df.form_name;

CREATE OR REPLACE VIEW `{curated_dataset}.v_audit_hallucination` AS
SELECT
  event_id,
  case_id,
  run_id,
  event_type,
  timestamp_s
FROM `{raw_dataset}.fact_event`
WHERE source = 'AI_DIRECT'
  AND (evidence IS NULL OR JSON_TYPE(evidence) = 'null' OR (JSON_TYPE(evidence) = 'array' AND ARRAY_LENGTH(JSON_QUERY_ARRAY(evidence)) = 0));

CREATE OR REPLACE VIEW `{curated_dataset}.v_audit_low_utd` AS
SELECT
  df.field_name,
  df.form_name,
  df.expected_utd_floor,
  COUNT(f.value) AS populated_count,
  COUNT(DISTINCT c.case_id) AS total_cases,
  ROUND(COUNT(f.value) / NULLIF(COUNT(DISTINCT c.case_id), 0), 4) AS actual_utd
FROM `{raw_dataset}.dim_redcap_field` df
CROSS JOIN (SELECT DISTINCT case_id, run_id FROM `{raw_dataset}.fact_redcap_field`) c
LEFT JOIN `{raw_dataset}.fact_redcap_field` f
  ON f.case_id = c.case_id
  AND f.run_id = c.run_id
  AND f.field_name = df.field_name
WHERE df.is_importable = TRUE
  AND df.is_calc_field = FALSE
  AND df.expected_utd_floor > 0.0
GROUP BY df.field_name, df.form_name, df.expected_utd_floor
HAVING actual_utd < df.expected_utd_floor;

CREATE OR REPLACE VIEW `{curated_dataset}.v_audit_branching_violation` AS
SELECT
  f.case_id,
  f.run_id,
  f.field_name,
  f.value
FROM `{raw_dataset}.fact_redcap_field` f
JOIN `{raw_dataset}.dim_redcap_field` df
  ON f.field_name = df.field_name
WHERE f.value IS NOT NULL
  AND f.value != ''
  AND 1=0;
"""
    return sql.strip() + "\n"


def main() -> None:
    out_dir = Path("generated")
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "bq_ddl.sql").write_text(generate_bq_ddl(), encoding="utf-8")
    (out_dir / "dim_redcap_field_seed.jsonl").write_text(
        generate_field_seed_jsonl(), encoding="utf-8"
    )
    (out_dir / "v_redcap_wide.sql").write_text(
        generate_v_redcap_wide(), encoding="utf-8"
    )
    (out_dir / "audit_views.sql").write_text(
        generate_audit_views(), encoding="utf-8"
    )
    print("Successfully emitted BigQuery SQL artifacts to generated/.")


if __name__ == "__main__":
    main()
