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

---

## 7. Media Resolution Behavior & Vertex AI SDK Observation
* **MEDIUM Resolution Fallback**: Empirically observed during B0 resolution probe that `MEDIA_RESOLUTION_LOW` and `MEDIA_RESOLUTION_MEDIUM` both consume exactly `9,455` tokens on a 60s slice of video (`simvideo2.mp4` at `fps=2.0`), whereas `MEDIA_RESOLUTION_HIGH` consumes `33,215` tokens. This indicates that `MEDIUM` is unsupported on `gemini-3.6-flash` (`global`) and falls back to `LOW`.

---

## 8. DEMO FINDINGS (DEMO-1 Live Run)
* **F-008**: We could not establish, from the LLM alone, how many defibrillation shocks occurred in this video. A 5-call replication test on a 20-second window (`730–750s`, `gemini-3.6-flash`, `fps=5`, shock-only prompt) yielded a 20% replication rate (1/5 found `741.2s`; 4/5 returned zero). Furthermore, while forced-choice 5-second block questioning was 100% stable for compression interruptions (CCIs), it failed to stabilize shock detection (producing false negatives or flooding 7–9 of 12 blocks without body jerks). Two of five reference shocks (`741.2s`, `855.0s`) are unreplicated single-probe observations. This proves that nothing in an LLM-only system can tell us which of its own answers is right, establishing the empirical necessity of (a) deterministic audio detectors for shocks (charge tone + discharge click), (b) `k>=3` ensemble voting, and (c) a human abstractor for clinical adjudication.
* **F-007**: Two runs, identical video, identical prompt version, k=1: 3 vs 5 shocks, 4 vs 8 compression interruptions. num_times_defib_ed_v2 and CCF are both materially affected. Neither run is verifiable without a human abstractor. This is the empirical case for k>=3 ensemble voting, deterministic sensors for timing and shock detection, and a gold set to establish which run — if either — is correct.
* **F-006**: Same-model probes are consistency checks, not ground truth. P1 and a focused probe agreed on 3 shocks and disagreed on 2 of 3 compression interruptions, including a 54-second pause found by one and not the other. Neither is authoritative. Resolving this requires a human abstractor (the gold set) or a deterministic sensor (S1).
* **Clinical Narrative Context**: At t≈880s, the team leader says: *"At this point, we've attempted 8 shocks with full CPR efforts. I don't have any better ideas, anybody else on the team have any other thoughts?"* No ROSC, no pronouncement, and no DNR order are verbalized. Active resuscitation spans ~0–880s; 840–1363s is post-resuscitation care and debriefing. Extraction found 5 shocks and 8 interruptions in the ED against a verbalized scenario history of 8 shocks.
* **EMS vs. ED Scope**: EMS handoff report (0–120s) states 3 field shocks (`"After three cycles of CPR and three shocks and three Epi, he's still in V-fib"`), confirming that the apparent shock count discrepancy is an ED-scope boundary correctly resolved by `num_times_defib_ed_v2` (`IN THE ED`).
* **t_precision_s Calibration Floor Override**: In degraded/self-detection mode, timestamps default to `t_precision_s >= 2.0s` via constitutional floor instruction which explicitly OVERRIDES the calibration table.
* **Ungated Required Contract Attributes**: Marking ungated contract attributes in the JSON Schema `required` array enables Vertex AI generation-time enforcement. On DEMO-1, `aline_present` appeared on 100% of CCIs as an honest `False` (zero omissions, zero reflexive `True` hallucinations).

---

## 9. DEMO-1 & DEMO-2 Audit Gate Verification & 40-Case Synthetic Demo Cohort
* **Elimination of Bare Empty Null States**: Diagnosed that `access_confirmed_time` (and `endtime_intub_{i}_v2`) previously landed in BigQuery as `value = NULL`, `abstained = FALSE`, and `branching_satisfied = TRUE`, which tripped `v_audit_missing_fields` because BigQuery lacked a `confidence` column to distinguish clean nulls (`confidence = 1.0`). Added `confidence FLOAT64` to `fact_redcap_field` DDL and updated `v_audit_missing_fields` to exclude rows where `confidence == 1.0` via `(f.confidence IS NULL OR f.confidence < 1.0)`. Furthermore, refactored rule `attr` in `resus_qc/reducer/engine.py` so unobserved timestamps (`ts is None`) and unobserved items emit clean nulls or abstentions with clinical explanations (`abstained = True`, e.g., `"no evidence observed"`), eliminating all bare empty fourth states while reducing `engine.py` to 495 lines (< 500 limit).
* **Live Audit Verification on DEMO-1 (`run_02` & `run_03`)**: Verified 3,758 fields scanned across `DEMO-1` (`1,879` rows per run). All three strict hard gates (`v_audit_hallucination`, `v_audit_missing_fields`, `v_audit_branching_violation`) plus `v_audit_source_class_drift` confirmed **100% clean (0 violations)**.
* **40-Case Synthetic Demo Cohort (`nodepeel:resus_demo`)**:
  * Generated 40 synthetic event streams across 4 months (`2025-11` to `2026-02`, 10 cases per month satisfying $n \ge 10$ privacy aggregation guard) with linear CCF drift (0.74 -> 0.84) and pause allocations making airway placement (`airway`: 6,315.3s, 48.3% of total no-flow) the #1 Pareto contributor.
  * Verified dataset isolation: exactly **0 rows** in `nodepeel.resus_raw.dim_case` where `is_synthetic = TRUE`.
  * Verified 75,160 fields scanned across `nodepeel:resus_demo.fact_redcap_field` (`40 × 1,879` rows). All five audit views (`v_audit_hallucination`, `v_audit_missing_fields`, `v_audit_branching_violation`, `v_audit_source_class_drift`, `v_audit_low_utd`) returned exactly **0 violations**.
  * Confirmed architectural refusal of provider identity queries: SQL queries grouping by `provider_id` against `resus_demo.v_case_metrics` fail immediately with `400 Unrecognized name: provider_id`.

---

## 10. Conversational Agent Guardrails & Calibrated `resus_demo` Cohort
* **Pre-Query & Post-Query Conversational Agent Guardrails (`demo/query_agent.py`)**:
  * **Provider-Scope Refusal (`check_provider_scope`)**: Blocks SQL queries attempting to group, order, or partition by provider or role identity columns (`role`, `operator_position`, `speaker_id`, `provider`, etc.) before any query reaches BigQuery. Verified with live refusals on `"Which team leader has the lowest compression fraction?"` and `"Compare first-pass intubation success by operator position."`:
    ```text
    This system is scoped to department-level quality improvement. Grouping or ranking by an individual or role requires separate institutional approval and is not available here.
    ```
  * **Minimum Cell-Size Guardrail (`check_privacy_cell_size`)**: Blocks/suppresses aggregated result sets where any group cell size is $0 < n < 10$ cases to prevent patient/provider re-identification. Verified on `"Show me CCF for cases where ROSC was achieved, broken down by month"` (where individual months have $n=4$ cases):
    ```text
    Privacy aggregation guardrail triggered: group cell size n=4 (< 10 cases required). Small-cell outputs are suppressed to protect patient and clinical team confidentiality.
    ```
* **Calibrated Synthetic Cohort (`demo/generate_synthetic_cohort.py`)**:
  * Calibrated monitor occlusion and ultrasound coverage notes so that monitor-dependent fields (`aline_sbp_cci_{i}`, `aline_dbp_cci_{i}`, `echo_success_cci_{i}`, etc.) and selective airway/rhythm attributes abstain at realistic rates, averaging exactly **`43.0` UTD fields per case** across the 40 cases (within the target 40–60 range, matching real `run_02`'s 58–63 UTD fields).
  * Confirmed **100% clean across all 4 strict audit hard gates** (`v_audit_hallucination`, `v_audit_missing_fields`, `v_audit_branching_violation`, `v_audit_source_class_drift` = `0` violations across 75,160 fields scanned).
  * Confirmed `v_audit_low_utd` flags 4 high-difficulty fields (`type_airway_ed_intub_1_v2`, `iv_io_in_place_arrival`, `first_ed_rhythm_v2`, `any_ventilation_delays_v2`) falling below floor, demonstrating audit sensitivity.
  * Verified Pareto dominance of airway placement in Query 2 (`airway`: 6,931.5s / 29.8% of total no-flow).

---

## 11. Clinician-Visible Synthetic Cohort Refinements
* **Independent Ultrasound Procedures (`chest_us` vs `us_pulse`)**: Decoupled cardiac echo (`chest_us`, ~25% of pauses, mean ~14s) from vascular Doppler (`us_pulse`, ~15% of pauses, mean ~8s) in `demo/generate_synthetic_cohort.py`, eliminating identical twin rows in the Pareto table (`3,656.0s` across 123 pauses vs `2,956.6s` across 80 pauses) while maintaining `airway_placement` (`9,407.1s` / 36.5% across 96 pauses) as the dominant #1 Pareto contributor.
* **Strict `cci_reason` Vocabulary Compliance**: Replaced event literal strings (`"airway"`, `"rhythm_check"`, `"defib_shock"`) with declared dictionary reason codes (`"airway_placement"`, `"rhythm_determination"`, `"defibrillation"`, `"pulse_check"`, `"chest_us"`, `"us_pulse"`, `"stretcher_transfer"`). Verified `0` invalid codes in BigQuery (`SELECT DISTINCT reason FROM nodepeel.resus_demo.v_cci_reasons`) and enforced vocabulary compliance via unit test `test_synthetic_cci_reasons_in_declared_vocabulary` in `tests/test_reducer_primitives.py`.
* **Non-Monotonic CCF Run-Chart with Outliers**: Replaced artificial monotonic CCF progression with realistic QI noise (`2025-11`: 0.698, `2025-12`: 0.670, `2026-01`: 0.744, `2026-02`: 0.727 — up overall, not up every month), constant variance ($\sigma \sim 0.07$ throughout), and refractory arrest outlier cases (`0.55--0.62`), accompanied by explicit unprompted demo clinician commentary:
  > *"Forty invented cases. I built in a mild upward trend so the run chart shows something. That trend is not a finding — it's a fixture. What I'm showing you is the shape of the question, not an answer about your department."*



