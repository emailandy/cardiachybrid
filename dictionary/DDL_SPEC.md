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

1. **dim_case**: Case-level metadata and registry enrollment demographics.
2. **dim_run**: Execution metadata for individual AI pipeline runs.
3. **dim_redcap_field**: Metadata and dictionary definitions for REDCap export columns.
4. **fact_event**: Video-observed clinical events and AI detections; `evidence` stored as JSON.
5. **fact_interval**: Clinical intervals (`compression_interruption`, `rosc`, etc.).
6. **fact_utterance**: Verbatim speech transcripts and speaker attributions (PHI restricted).
   - **NOTE (Q-011 DEFERRED)**: `text_embedding` (`ARRAY<FLOAT64>`) is explicitly DROPPED from this specification.
7. **fact_sensor_interval**: Monotonic time-series sensor intervals (`S1` optical flow, `S2` audio periodicity).
8. **fact_redcap_field**: Normalized EAV (Entity-Attribute-Value) fact records for REDCap field values.
9. **redcap_submission**: Assembled payload submission history and API response logs.
10. **fact_metric**: Derived clinical quality metrics (e.g., CCF, compression depth, time-to-defib).
11. **fact_coverage_note**: Coverage and truncation notes from anchor pass or windowing.
12. **fact_near_miss**: 1/3-vote dropped events from ensemble ingestion; contains `evidence` JSON (PHI) for threshold tuning.
13. **fact_team_score**: Resuscitation teamwork domain scores and rater metadata.

---

## 3. Curated and Audit Views (`resus_curated` — 7 Views)

1. **v_redcap_wide**: Generated pivot view over `fact_redcap_field`, containing exactly `len(IMPORTABLE_COLUMNS)` (~1,889) `MAX(IF(...))` column expressions plus `case_id, run_id, event_date`. Calc fields are excluded to prevent permanently-NULL extraction columns.
2. **v_exemplar_store**: Authorized view joining `fact_event` and `fact_redcap_field` for clinical review.
3. **v_audit_missing_fields**: Returns zero rows when all importable fields are populated (coverage proof Q1).
4. **v_audit_domain_coverage**: Populated vs. abstained field counts aggregated by domain/form (Q2).
5. **v_audit_hallucination**: Identifies `AI_DIRECT` events with non-null values and empty `evidence` (Q3).
6. **v_audit_low_utd**: Flags HIGH-difficulty importable fields below `expected_utd_floor` (Q4).
7. **v_audit_branching_violation**: Identifies populated fields that should be hidden/suppressed by branching logic (Q5).

---

## 4. Partitioning & Clustering
- `PARTITION BY event_date` where timestamp is present.
- `CLUSTER BY case_id, event_type` (or `case_id, field_name` for EAV tables).
- JSON data types used for `attributes`, `evidence`, `payload`, and `choices` columns instead of `STRING`.
