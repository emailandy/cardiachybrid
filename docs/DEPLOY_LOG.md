# resus_qc — BigQuery Deployment & Verification Log (DEMO-0)
**Date**: 2026-08-01  
**Project**: `nodepeel` (US-East4 Single-Region Deployment, Q-010)  
**Task**: DEMO-0 — Deploy BigQuery Schema to `nodepeel` and Verify  

---

## 1. What Was Created
Deployed the generated DDL (`generated/bq_ddl.sql` and `generated/audit_views.sql`) to the `nodepeel` BigQuery project:
* **`nodepeel:resus_raw` (13 physical tables)**:
  1. `dim_case` (clustered by `case_id`)
  2. `dim_run` (partitioned by `DAY(event_date)`, clustered by `case_id, run_id`)
  3. `dim_redcap_field` (clustered by `field_name, form_name`)
  4. `fact_event` (partitioned by `DAY(event_date)`, clustered by `case_id, event_type`)
  5. `fact_interval` (partitioned by `DAY(event_date)`, clustered by `case_id, interval_type`)
  6. `fact_utterance` (partitioned by `DAY(event_date)`, clustered by `case_id, run_id`)
  7. `fact_sensor_interval` (partitioned by `DAY(event_date)`, clustered by `case_id, sensor_type`)
  8. `fact_redcap_field` (partitioned by `DAY(event_date)`, clustered by `case_id, field_name`)
  9. `redcap_submission` (partitioned by `DAY(event_date)`, clustered by `case_id, run_id`)
  10. `fact_metric` (partitioned by `DAY(event_date)`, clustered by `case_id, metric_name`)
  11. `fact_coverage_note` (partitioned by `DAY(event_date)`, clustered by `case_id, target_domain`)
  12. `fact_near_miss` (partitioned by `DAY(event_date)`, clustered by `case_id, event_type`)
  13. `fact_team_score` (partitioned by `DAY(event_date)`, clustered by `case_id, domain`)
* **`nodepeel:resus_curated` (7 views)**:
  1. `v_redcap_wide` (pivots `1,889` non-server-computed `IMPORTABLE_COLUMNS`)
  2. `v_exemplar_store` (event feedback loop view)
  3. `v_audit_missing_fields`
  4. `v_audit_domain_coverage`
  5. `v_audit_hallucination`
  6. `v_audit_low_utd`
  7. `v_audit_branching_violation`

---

## 2. Verification Outputs

### A. Dataset Listing & Scratch Target Refusal
* `nodepeel:resus_raw`: **13 tables** present. All 13 physical tables were audited against `dictionary/DDL_SPEC.md` and match their specifications with zero mismatch.
* `nodepeel:resus_curated`: **7 views** present.
* `nodepeel:resus_scratch`: **Empty** (0 tables/views).
* **IMPORTANT — `--dataset` Flag Deployment Behavior**:
  * Passing `--dataset resus_raw` deploys **BOTH** raw physical tables to `resus_raw` **AND** curated/audit views to `resus_curated`.
  * Passing `--dataset resus_curated` raises an explicit refusal error (`ValueError: Cannot deploy raw tables directly to resus_curated.`). Do not attempt to deploy with `--dataset resus_curated`; always target `--dataset resus_raw`.
* **Scratch Target Refusal**: Running `python -m bq.deploy --project nodepeel --dataset resus_scratch --dry-run` raised the expected refusal error:
  ```
  ValueError: resus_scratch NEVER receives a table from generated/bq_ddl.sql. It exists solely as a --dataset-prefix target for ephemeral CI deployments (attempted dataset: resus_scratch).
  ```

### B. Seed Dictionary Table (`dim_redcap_field` — Reconciled 22-Column Schema)
Loaded `generated/dim_redcap_field_seed.jsonl` into `nodepeel:resus_raw.dim_redcap_field` via `bq load --source_format=NEWLINE_DELIMITED_JSON --replace`:
* **Reconciled Schema (21 columns)**: Includes all 19 original dictionary schema columns (`dict_version`, `field_name`, `form_name`, `field_type`, `field_label`, `choices`, `validation`, `val_min`, `val_max`, `branching_logic`, `is_required`, `export_columns`, `source_class`, `extraction_difficulty`, `target_accuracy`, `owning_event_types`, `expected_utd_floor`, `repeat_group`, `repeat_index`) plus 2 explicit boolean query optimization flags (`is_importable`, `is_calc_field`). Note: `is_phi` was dropped as an unused classification to prevent maintenance rot.
* **System Fields Included**: Contains the 909 data dictionary fields plus 2 REDCap system fields (`record_id`, `video_review_complete`) assigned `source_class: "AI_DERIVED"`, yielding exactly **911 rows**.
* **Verification Query**:
  ```sql
  SELECT COUNT(*) n, COUNT(DISTINCT source_class) sc
  FROM nodepeel.resus_raw.dim_redcap_field;
  ```
  **Output**:
  ```
  +-----+----+
  |  n  | sc |
  +-----+----+
  | 911 |  7 |
  +-----+----+
  ```

### C. Audit View Execution Against Empty Tables & Reconciled Predicates
Every curated view was audited against its stated purpose and corrected where necessary, then executed against empty base tables without raising an error or exceeding query limits:
* `v_audit_missing_fields`: flags `f.branching_satisfied = TRUE AND f.abstained = FALSE AND (f.value IS NULL OR f.value = '')`, excluding `df.source_class IN ('HUMAN_ONLY', 'ROSTER_JOIN', 'REDCAP_CALC')`.
* `v_audit_branching_violation`: flags `f.branching_satisfied = FALSE AND f.value IS NOT NULL AND f.value != ''`.
* `v_audit_low_utd`: flags `df.extraction_difficulty = 'HIGH'` fields whose population rate falls below `expected_utd_floor` over `branching_satisfied = TRUE`.
* `v_audit_domain_coverage`: aggregates populated/abstained counts and percentages by `(run_id, domain, source_class)` over `branching_satisfied = TRUE`.
* `v_exemplar_store`: selects corrected field values over `f.human_verified = TRUE AND f.human_value IS NOT NULL AND f.human_value != f.value`.
* `v_audit_hallucination`: flags `df.source_class = 'AI_DIRECT'` fields with `f.value IS NOT NULL AND f.value != '' AND ARRAY_LENGTH(f.source_event_ids) = 0`.
```bash
for v in v_audit_missing_fields v_audit_domain_coverage \
         v_audit_hallucination v_audit_low_utd \
         v_audit_branching_violation v_redcap_wide v_exemplar_store; do
  echo "── $v"
  bq query --nouse_legacy_sql --max_rows=1 \
    "SELECT * FROM nodepeel.resus_curated.$v LIMIT 1"
done
```
**Output**: All 7 views returned **0 rows cleanly without error**, including `v_redcap_wide` with `1,889` expressions.

### D. IAM Negative Proof Against Real PHI Tables (`infra/verify_iam.sh`)
Executed `bash infra/verify_iam.sh nodepeel` against the actual PHI tables in `nodepeel:resus_raw` (without creating or deleting temporary fixtures):
```
=== Resus QC IAM Verification Script (Project: nodepeel) ===
Real tables exist in resus_raw and resus_curated; testing against actual schema without temporary fixtures...
Executing negative proof queries against BigQuery...

--- Testing Service Account: sa-analyst@nodepeel.iam.gserviceaccount.com ---
  [SUCCESS - EXPECTED]   v_redcap_wide (curated view) -> 0 rows returned
  [SUCCESS - EXPECTED]   v_exemplar_store (curated view) -> 0 rows returned
  [DENIED - EXPECTED]    fact_utterance (base PHI table) -> 403 Access Denied: User does not have permission to query table nodepeel:resus_raw.fact_utterance
  [DENIED - EXPECTED]    fact_event.evidence (base PHI column) -> 403 Access Denied: User does not have permission to query table nodepeel:resus_raw.fact_event

--- Testing Service Account: sa-reviewer@nodepeel.iam.gserviceaccount.com ---
  [SUCCESS - EXPECTED]   v_redcap_wide (curated view) -> 0 rows returned
  [SUCCESS - EXPECTED]   v_exemplar_store (curated view) -> 0 rows returned
  [DENIED - EXPECTED]    fact_utterance (base PHI table) -> 403 Access Denied: User does not have permission to query table nodepeel:resus_raw.fact_utterance
  [DENIED - EXPECTED]    fact_event.evidence (base PHI column) -> 403 Access Denied: User does not have permission to query table nodepeel:resus_raw.fact_event

✓ IAM NEGATIVE PROOF VERIFIED (2 successes + 2 403 denials per SA).
```

---

## 3. CMEK Status
**CMEK (Customer-Managed Encryption Keys) is currently a PLACEHOLDER per D07a.**  
All tables deployed to `nodepeel:resus_raw` and `nodepeel:resus_curated` are currently encrypted with **default Google-managed encryption keys**. Cloud KMS customer-managed key integration is staged in architecture but has not been provisioned or applied to this deployment.

---

## 4. Teardown & Redeploy Commands

### Teardown (Remove All Tables & Views)
To wipe all physical tables and curated views from `nodepeel`:
```bash
# Wipe and recreate empty datasets
bq rm -f -r nodepeel:resus_raw
bq rm -f -r nodepeel:resus_curated
bq mk --dataset --location=us-east4 nodepeel:resus_raw
bq mk --dataset --location=us-east4 nodepeel:resus_curated
```

### Redeploy (Re-create Schema & Reload Seed Dictionary)
To deploy all 13 tables, 7 views, and reload the dictionary seed from scratch:
```bash
source .venv/bin/activate
python -m bq.deploy --project nodepeel --dataset resus_raw
bq load --source_format=NEWLINE_DELIMITED_JSON --replace \
  nodepeel:resus_raw.dim_redcap_field \
  generated/dim_redcap_field_seed.jsonl
```

---

## 5. Audit View Interpretability Guidelines
* `v_audit_low_utd`: "v_audit_low_utd requires n >= 20 cases to be interpretable. On a single case the rate is binary. Exclude it from single-case reports."

---

## 6. Video Storage & Cross-Region Sandbox Deviation
* **Bucket Location**: `gs://resus-qc-demo-video` is provisioned in `us-central1` to serve Vertex AI Gemini models (`gemini-2.5-flash` and `gemini-2.5-pro`) in region `us-central1`.
* **Cross-Region Deviation**: BigQuery is pinned to `us-east4` (`nodepeel:resus_raw` and `nodepeel:resus_curated`). This cross-region split (`us-central1` GCS/Vertex vs `us-east4` BigQuery) is a sandbox-only deviation due to regional availability of Gemini model garden endpoints. Production deployments must colocate GCS, Vertex AI endpoints, and BigQuery datasets within the same region.
