# BigQuery DDL Specification

This document outlines the schema for the ten core BigQuery tables in the Resuscitation Quality Control (`resus_qc`) data warehouse.
All physical tables reside in the `resus_raw` dataset (`us-east4`, CMEK-encrypted).

## Core Tables

1. **dim_case**
   - Case-level metadata and registry enrollment demographics.
2. **dim_run**
   - Execution metadata for individual AI pipeline runs.
3. **fact_event**
   - Video-observed clinical events and AI detections.
   - `evidence` column stored as JSON (verbatim quotes/audit trail; PHI restricted).
4. **fact_interval**
   - Clinical intervals (`compression_interruption`, `rosc`, etc.).
5. **fact_utterance**
   - Verbatim speech transcripts and speaker attributions (PHI restricted).
   - **NOTE (Q-011 DEFERRED)**: `text_embedding` (`ARRAY<FLOAT64>`) is explicitly DROPPED from this specification. Embedding storage is deferred to the retrieval layer. When added, requires separate governance review — derived embeddings of clinical audio are PHI and voice embeddings may be biometric identifiers.
6. **fact_sensor_interval**
   - Monotonic time-series sensor intervals (`S1` optical flow, `S2` compression audio periodicity).
7. **dim_redcap_field**
   - Metadata and dictionary definitions for REDCap export columns.
8. **fact_redcap_field**
   - Normalized EAV (Entity-Attribute-Value) fact records for REDCap field values.
9. **redcap_submission**
   - Assembled payload submission history and API response logs.
10. **fact_metric**
    - Derived clinical quality metrics (e.g., CCF, compression depth, time-to-defib).

## Partitioning & Clustering
- `PARTITION BY event_date` where timestamp is present.
- `CLUSTER BY case_id, event_type` (or `case_id, field_name` for EAV tables).
- JSON data types used for `attributes`, `evidence`, `payload`, and `choices` columns instead of `STRING`.
