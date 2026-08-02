"""
codegen/emit_sql.py — Generates BigQuery DDL, seed JSONL, wide pivot view, and audit views.

Artifacts produced in generated/:
  1. bq_ddl.sql: Thirteen physical tables in {raw_dataset} (CMEK-ready, partitioned/clustered).
  2. dim_redcap_field_seed.jsonl: Seed data for dim_redcap_field from REDCap dictionary.
  3. v_redcap_wide.sql: Parameterized wide view in {curated_dataset} (1,889 MAX(IF(...)) columns) with SHA-256 header checksum.
  4. audit_views.sql: Seven authorized/audit views in {curated_dataset} referencing {raw_dataset}.
"""

import json
import yaml
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
  dict_version STRING NOT NULL,
  field_name STRING NOT NULL,
  form_name STRING,
  domain STRING NOT NULL,
  field_type STRING,
  field_label STRING,
  choices JSON,
  validation STRING,
  val_min STRING,
  val_max STRING,
  branching_logic STRING,
  is_required BOOL,
  export_columns JSON,
  source_class STRING,
  extraction_difficulty STRING,
  target_accuracy FLOAT64,
  owning_event_types JSON,
  expected_utd_floor FLOAT64,
  repeat_group STRING,
  repeat_index INT64,
  is_importable BOOL,
  is_calc_field BOOL
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
  source_class STRING,
  branching_satisfied BOOL,
  abstained BOOL,
  source_event_ids ARRAY<STRING>,
  human_verified BOOL,
  human_value STRING,
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


def _get_field_domain_map() -> dict[str, str]:
    """Returns mapping of field_name -> 13 registry section domain names."""
    reg_path = Path("mapping/registry.yaml")
    reg = yaml.safe_load(reg_path.read_text())
    group_to_section = {
        "defib": "pad_and_defibrillation",
        "cci": "cci",
        "airway": "airway",
        "rosc": "rosc",
        "vent_delay": "ventilation",
    }
    domain_map = {}
    for sec in reg.get("sections", []):
        sec_name = sec["name"]
        for item in sec.get("fields", []):
            fname = item["field"] if isinstance(item, dict) else item
            domain_map[fname] = sec_name

    for f_name, spec in FIELDS.items():
        if spec.repeat_group in group_to_section:
            domain_map[f_name] = group_to_section[spec.repeat_group]
        elif spec.source_class in ("ROSTER_JOIN", "HUMAN_ONLY"):
            domain_map[f_name] = "redcap_internal"
        elif f_name == "dur_mccd_app_ed_secs_v2":
            domain_map[f_name] = "mccd"
        elif f_name == "duration_ventilator_place_v2":
            domain_map[f_name] = "ventilation"

    domain_map["record_id"] = "redcap_internal"
    domain_map["video_review_complete"] = "redcap_internal"
    return domain_map


def generate_field_seed_jsonl() -> str:
    """Produces JSONL seed rows for dim_redcap_field (909 dictionary fields + 2 REDCap system fields = 911 rows)."""
    dict_version = "v1.0.0"
    dict_ver_path = Path("dictionary/dict_version.txt")
    if dict_ver_path.exists():
        dict_version = dict_ver_path.read_text().strip()

    domain_map = _get_field_domain_map()

    system_fields = [
        {
            "dict_version": dict_version,
            "field_name": "record_id",
            "form_name": "video_review",
            "domain": "redcap_internal",
            "field_type": "text",
            "field_label": "Record ID (REDCap system field not present in dictionary export)",
            "choices": {},
            "validation": "",
            "val_min": "",
            "val_max": "",
            "branching_logic": "",
            "is_required": True,
            "export_columns": ["record_id"],
            "source_class": "AI_DERIVED",
            "extraction_difficulty": "LOW",
            "target_accuracy": 1.0,
            "owning_event_types": [],
            "expected_utd_floor": 1.0,
            "repeat_group": "",
            "repeat_index": None,
            "is_importable": True,
            "is_calc_field": False,
        },
        {
            "dict_version": dict_version,
            "field_name": "video_review_complete",
            "form_name": "video_review",
            "domain": "redcap_internal",
            "field_type": "radio",
            "field_label": "Complete? (REDCap system form completion field not present in dictionary export)",
            "choices": {"0": "Incomplete", "1": "Unverified", "2": "Complete"},
            "validation": "",
            "val_min": "",
            "val_max": "",
            "branching_logic": "",
            "is_required": False,
            "export_columns": ["video_review_complete"],
            "source_class": "AI_DERIVED",
            "extraction_difficulty": "LOW",
            "target_accuracy": 1.0,
            "owning_event_types": [],
            "expected_utd_floor": 1.0,
            "repeat_group": "",
            "repeat_index": None,
            "is_importable": True,
            "is_calc_field": False,
        },
    ]

    all_rows = list(system_fields)
    for f_name in sorted(FIELDS.keys()):
        spec = FIELDS[f_name]
        row = {
            "dict_version": dict_version,
            "field_name": spec.field_name,
            "form_name": spec.form_name,
            "domain": domain_map.get(spec.field_name, "redcap_internal"),
            "field_type": spec.field_type,
            "field_label": spec.field_label,
            "choices": spec.choices,
            "validation": spec.validation,
            "val_min": str(spec.val_min) if spec.val_min is not None else "",
            "val_max": str(spec.val_max) if spec.val_max is not None else "",
            "branching_logic": spec.branching_raw,
            "is_required": bool(spec.required),
            "export_columns": list(spec.export_columns),
            "source_class": spec.source_class,
            "extraction_difficulty": spec.difficulty,
            "target_accuracy": getattr(spec, "target_accuracy", 1.0),
            "owning_event_types": list(spec.owning_event_types),
            "expected_utd_floor": float(getattr(spec, "expected_utd_floor", 0.95)),
            "repeat_group": spec.repeat_group or "",
            "repeat_index": spec.repeat_index,
            "is_importable": bool(spec.carries_data and not spec.server_computed),
            "is_calc_field": bool(spec.server_computed),
        }
        all_rows.append(row)

    all_rows.sort(key=lambda r: r["field_name"])
    return "\n".join(json.dumps(r, sort_keys=True) for r in all_rows) + "\n"


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
  f.case_id,
  f.run_id,
  f.field_name,
  f.value AS ai_value,
  f.human_value,
  f.event_date
FROM `{raw_dataset}.fact_redcap_field` f
WHERE f.human_verified = TRUE
  AND f.human_value IS NOT NULL
  AND f.human_value != f.value;

CREATE OR REPLACE VIEW `{curated_dataset}.v_audit_missing_fields` AS
SELECT
  f.case_id,
  f.run_id,
  f.field_name
FROM `{raw_dataset}.fact_redcap_field` f
JOIN `{raw_dataset}.dim_redcap_field` df
  ON f.field_name = df.field_name
WHERE df.is_importable = TRUE
  AND df.is_calc_field = FALSE
  AND df.source_class NOT IN ('HUMAN_ONLY', 'ROSTER_JOIN', 'REDCAP_CALC')
  AND f.branching_satisfied = TRUE
  AND f.abstained = FALSE
  AND (f.value IS NULL OR f.value = '');

CREATE OR REPLACE VIEW `{curated_dataset}.v_audit_domain_coverage` AS
SELECT
  f.run_id,
  df.domain,
  df.source_class,
  COUNTIF(f.value IS NOT NULL AND f.value != '' AND f.abstained = FALSE) AS populated_count,
  COUNTIF(f.abstained = TRUE) AS abstained_count,
  COUNT(*) AS total_fields,
  ROUND(COUNTIF(f.value IS NOT NULL AND f.value != '' AND f.abstained = FALSE) / NULLIF(COUNT(*), 0), 4) AS populated_pct
FROM `{raw_dataset}.fact_redcap_field` f
JOIN `{raw_dataset}.dim_redcap_field` df
  ON f.field_name = df.field_name
WHERE df.is_importable = TRUE
  AND df.is_calc_field = FALSE
  AND f.branching_satisfied = TRUE
GROUP BY f.run_id, df.domain, df.source_class;

CREATE OR REPLACE VIEW `{curated_dataset}.v_audit_hallucination` AS
SELECT
  f.case_id,
  f.run_id,
  f.field_name,
  f.value
FROM `{raw_dataset}.fact_redcap_field` f
WHERE f.source_class = 'AI_DIRECT'
  AND f.value IS NOT NULL AND f.value != ''
  AND (f.source_event_ids IS NULL OR ARRAY_LENGTH(f.source_event_ids) = 0);

CREATE OR REPLACE VIEW `{curated_dataset}.v_audit_source_class_drift` AS
SELECT
  f.case_id,
  f.run_id,
  f.field_name,
  f.source_class AS run_value,
  df.source_class AS schema_value
FROM `{raw_dataset}.fact_redcap_field` f
JOIN `{raw_dataset}.dim_redcap_field` df
  USING (field_name)
WHERE f.source_class != df.source_class;

CREATE OR REPLACE VIEW `{curated_dataset}.v_audit_low_utd` AS
SELECT
  df.field_name,
  df.domain,
  df.expected_utd_floor,
  COUNTIF(f.abstained = TRUE) AS abstained_count,
  COUNT(*) AS total_cases,
  ROUND(COUNTIF(f.abstained = TRUE) / NULLIF(COUNT(*), 0), 4) AS actual_utd_rate
FROM `{raw_dataset}.fact_redcap_field` f
JOIN `{raw_dataset}.dim_redcap_field` df
  ON f.field_name = df.field_name
WHERE df.is_importable = TRUE
  AND df.is_calc_field = FALSE
  AND df.extraction_difficulty = 'HIGH'
  AND df.expected_utd_floor > 0.0
  AND f.branching_satisfied = TRUE
GROUP BY df.field_name, df.domain, df.expected_utd_floor
HAVING actual_utd_rate < df.expected_utd_floor;

CREATE OR REPLACE VIEW `{curated_dataset}.v_audit_branching_violation` AS
SELECT
  f.case_id,
  f.run_id,
  f.field_name,
  f.value
FROM `{raw_dataset}.fact_redcap_field` f
JOIN `{raw_dataset}.dim_redcap_field` df
  ON f.field_name = df.field_name
WHERE f.branching_satisfied = FALSE
  AND f.value IS NOT NULL
  AND f.value != '';
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
