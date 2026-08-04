# BigQuery DDL Specification

This document outlines the schema for the thirteen core physical BigQuery tables and seven authorized/audit views in the Resuscitation Quality Control (`resus_qc`) data warehouse.
All physical tables reside in the `resus_raw` dataset (`us-east4`, CMEK-encrypted).

## 1. Dataset Mapping & Rules

- **`resus_raw` (Physical PHI Tables — 13 tables)**:
  - Holds all physical dimensions and facts, including `fact_near_miss` (PHI verbatim quotes from 1/3 minority-vote dropped events).
- **`resus_curated` (Authorized & Audit Views — 7 views)**:
  - Holds read-path views (`v_redcap_wide`, `v_exemplar_store`) and 5 audit views.
- **`resus_scratch` (Ephemeral Deployments — 0 tables from DDL)**:
  - **RULE**: `resus_scratch NEVER receives a table from generated/bq_ddl.sql. It exists solely as a --dataset-prefix target for ephemeral CI deployments, which create and destroy their own fully-prefixed dataset (e.g. ci_run_a1b2c3) rather than writing into a shared one.`

---

## 2. Core Physical Tables (`resus_raw` — 13 Tables)

1. **dim_case**: Case-level metadata and registry enrollment demographics, including `site STRING` and `is_synthetic BOOL` (default `FALSE`; strictly required to be `FALSE` in `resus_raw`).
2. **dim_run**: Execution metadata for individual AI pipeline runs.
3. **dim_redcap_field**: Metadata and dictionary definitions for REDCap export columns. Includes the 20 dictionary schema columns (`dict_version`, `field_name`, `form_name`, `domain`, `field_type`, `field_label`, `choices`, `validation`, `val_min`, `val_max`, `branching_logic`, `is_required`, `export_columns`, `source_class`, `extraction_difficulty`, `target_accuracy`, `owning_event_types`, `expected_utd_floor`, `repeat_group`, `repeat_index`) plus 2 explicit query optimization boolean flags (`is_importable`, `is_calc_field`).
   - **Why `is_importable` and `is_calc_field` are retained**: Derived strictly from `spec.carries_data and not spec.server_computed` and `spec.server_computed`; materializing these boolean flags directly on `dim_redcap_field` simplifies BigQuery audit view predicates and analytical queries without requiring string matching or UDFs. (`is_phi` was dropped as an unused classification to prevent maintenance rot).
   - **Why `domain` is included**: Mapped at seed time from the 13 registry section domains in `mapping/registry.yaml` (`ed_details`, `pad_and_defibrillation`, `mccd`, `initial_pulse_check`, `cci`, `airway`, `ventilation`, `drugs`, `ecmo`, `rosc`, `end_of_resuscitation`, `team_ratings`, `redcap_internal`) so that domain coverage queries group across clinical sections instead of the constant form `'video_review'`.
   - **System Fields**: Includes 2 REDCap system fields (`record_id`, `video_review_complete`) with `source_class: "AI_DERIVED"` (911 total rows).
4. **fact_event**: Video-observed clinical events and AI detections; `evidence` stored as JSON.
5. **fact_interval**: Clinical intervals (`compression_interruption`, `rosc`, etc.), including `duration_s FLOAT64` and `reasons ARRAY<STRING>`.
6. **fact_utterance**: Verbatim speech transcripts and speaker attributions (PHI restricted).
   - **NOTE (Q-011 DEFERRED)**: `text_embedding` (`ARRAY<FLOAT64>`) is explicitly DROPPED from this specification.
7. **fact_sensor_interval**: Monotonic time-series sensor intervals (`S1` optical flow, `S2` audio periodicity).
8. **fact_redcap_field**: Normalized EAV (Entity-Attribute-Value) fact records for REDCap field values. Includes `source_class STRING`, `confidence FLOAT64`, `source_event_ids ARRAY<STRING>`, `human_verified BOOL`, and `human_value STRING`.
9. **redcap_submission**: Assembled payload submission history and API response logs.
10. **fact_metric**: Derived clinical quality metrics (e.g., CCF, compression depth, time-to-defib), including `value FLOAT64`, `numerator FLOAT64`, `denominator FLOAT64`, `null_reason STRING`, and `unit STRING`.
11. **fact_coverage_note**: Coverage and truncation notes from anchor pass or windowing.
12. **fact_near_miss**: 1/3-vote dropped events from ensemble ingestion; contains `evidence` JSON (PHI) for threshold tuning.
13. **fact_team_score**: Resuscitation teamwork domain scores and rater metadata.

---

## 3. Curated and Audit Views (`resus_curated` — 10 Views)

1. **v_redcap_wide**: Generated pivot view over `fact_redcap_field`, containing exactly `len(IMPORTABLE_COLUMNS)` (1,889) `MAX(IF(...))` column expressions plus `case_id, run_id, event_date`. The two server-computed calc fields (`dur_mccd_app_ed_secs_v2`, `duration_ventilator_place_v2`) are excluded to prevent permanently-NULL extraction columns. Reducer-populated count fields (`num_cci_v2`, `num_times_defib_ed_v2`, etc.) are text fields with number validation and are present in `IMPORTABLE_COLUMNS`.
2. **v_exemplar_store**: Authorized view over `fact_redcap_field` for clinical review where `f.human_verified = TRUE AND f.human_value IS NOT NULL AND f.human_value != f.value`.
3. **v_audit_missing_fields**: Flags empty importable non-calc fields where `branching_satisfied = TRUE AND abstained = FALSE AND (confidence IS NULL OR confidence < 1.0)`, excluding `HUMAN_ONLY / ROSTER_JOIN / REDCAP_CALC` and clean nulls at confidence 1.0.
4. **v_audit_domain_coverage**: Aggregates populated vs. abstained field counts and percentages by `run_id, domain, source_class` over `branching_satisfied = TRUE` only.
5. **v_audit_hallucination**: Identifies `AI_DIRECT` fields via single-table scan (`f.source_class = 'AI_DIRECT'`) with non-null/non-empty values (`f.value IS NOT NULL AND f.value != ''`) and empty source events (`ARRAY_LENGTH(f.source_event_ids) = 0`).
6. **v_audit_low_utd**: Flags HIGH-difficulty importable fields (`df.extraction_difficulty = 'HIGH'`) whose abstention rate (`actual_utd_rate = abstained / total_cases`) falls below `expected_utd_floor` over `branching_satisfied = TRUE` only, grouped by `domain`. Requires `n >= 20` cases to be interpretable.
7. **v_audit_branching_violation**: Identifies fields where `branching_satisfied = FALSE AND value IS NOT NULL AND value != ''`.
8. **v_audit_source_class_drift**: Identifies any row where run-time `f.source_class` differs from schema-time `df.source_class` (`f.source_class != df.source_class`). Must always return zero rows.
9. **v_case_metrics**: Long-format view joining `fact_metric` with `dim_case` (`case_id, run_id, metric_name, value, numerator, denominator, unit, null_reason, event_date, site`).
10. **v_cci_reasons**: Long-format view joining `fact_interval` unnesting `reasons` with `dim_case` (`case_id, run_id, seq, duration_s, reason, event_date`).

---

## 4. Partitioning & Clustering
- `PARTITION BY event_date` where timestamp is present.
- `CLUSTER BY case_id, event_type` (or `case_id, field_name` for EAV tables).
- JSON data types used for `attributes`, `evidence`, `payload`, and `choices` columns instead of `STRING`.
