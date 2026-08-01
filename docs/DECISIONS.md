# Decisions
## 001 — Registry gate syntax normalization
The registry gate syntax must be normalized to `<attr> <op> <typed_literal>` before D3, because the supplied registry mixes `== 1` and `is true` for the same condition.

## 002 — Normalized all gates in registry
Normalized all gates in mapping/registry.yaml to `<attr> <op> <typed_literal>` format. Changed 10 gates in total (added quotes around string literals, changed 'is true' to '== true').

## 003 — EXPORT_COLUMNS (1891) vs IMPORTABLE_COLUMNS (1889)
Date: 2026-07-31  Session: D01  Decided by: human
D01's original gate said 1889. The parser produced 1891. Root cause:
exportFieldNames excludes calc/file/descriptive; a CSV data export does not.
Both counts are correct for their purpose.
  EXPORT_COLUMNS     = 1891, everything a data export contains
  IMPORTABLE_COLUMNS = 1889, what exportFieldNames returns and what may be
                       POSTed to the import API
This dictionary has 2 calc fields and zero file/descriptive fields, so the
delta is exactly 2.
Consequence: D13 must compare against IMPORTABLE_COLUMNS. Comparing against
EXPORT_COLUMNS would report 2 phantom columns forever.

## 004 — Broken Gates in Registry Fix
Date: 2026-07-31  Session: D14  Decided by: human
Fixed four broken `conditional_text` gates that referenced attributes without emitting an event scope (e.g., `other_mccd_used_ems_v2`, `specify_other_mccd_ed_v2`, `mccd_obstacle_other`, and `other_mccd_adjust_v2`). The gates were fixed by explicitly declaring `event_type` and (if needed) `where` scope. A validator will be added to ensure this pattern doesn't recur.

## 005 — Unquoted yes/no booleans in YAML
Date: 2026-07-31  Session: D14  Decided by: agent
PyYAML silently evaluates unquoted 'yes' and 'no' in registry vocabularies as python booleans `True` and `False`. To accurately pass these exact keys down to the prompt contract, we implemented logic that reverses boolean serialization (`True -> "yes"`, `False -> "no"`) in `emit_contract.py` and `emit_python.py`. This ensures no `TypeError` occurs during set-operations and proper symbolic matching is maintained in `tests/test_coverage.py`.

## 006 — Interval Type Leak in Event Types
Date: 2026-07-31  Session: A01  Decided by: human
`interval_type` values (cci, rosc, vent_delay) must not leak into the derived `event_types` used for `redcap_feeding`. Separate `event_types_from_rules` and `event_types_from_hints` derivation lists are introduced, and we assert that interval types never overlap with event types.

## 007 — Fragment extraction and marker format
Date: 2026-07-31  Session: A02  Decided by: human
In `prompts/system/constitution.v2.0.md` and `prompts/fragments/*.md`, each fragment file contains the complete markdown block including its `## HEADING` line. The constitution uses `{{fragment:name}}` alone on the line where the block began. Reconstruction is a literal string replacement of `{{fragment:name}}` with the contents of the fragment file, which preserves byte-identical round-trip rendering and makes each fragment self-contained when injected individually into pass templates.

## 008 — Derivation of where-clause keys as extraction contract attributes & observable-vs-derived rule
**Observable vs. Derived Rule**: A `where` key becomes a MODEL attribute only if it is INDEPENDENTLY OBSERVABLE. If it is derivable from another attribute the model already emits, the reducer derives it — otherwise the model can emit a contradictory pair that nothing validates. Accordingly, `DERIVED_WHERE_KEYS` (`drug_class` derived from `drug`; `rhythm_shockable` derived from `rhythm`) are explicitly excluded from the contract. Total attribute count is 84, and a test (`test_no_derived_where_keys_in_contract`) asserts no derived where-key is exposed to the model. Also sorted `all_event_types` and `rule["where"]` keys to ensure 100% deterministic JSON generation.

## 009 — case_field keys must not collide with REDCap field names
Date: 2026-08-01  Session: D05  Decided by: human
case_field keys must not collide with REDCap field names, because the contract's case_fields block is injected into P3 and assert_no_field_names is absolute. Renamed `ohca_ihca` to `arrest_location` and `video_start_late` to `recording_started_late` in `mapping/registry.yaml`, and added a build-time codegen validator to ensure no case_field key ever collides with `EXPORT_COLUMNS`.

## 010 — abstain_reason is a closed vocabulary in its own namespace
Date: 2026-08-01  Session: D05  Decided by: human
`abstain_reason` is a closed vocabulary in its own namespace (`prompts/anchors/_ABSTAIN_REASONS.yaml`). It must not overlap `case_field` keys or REDCap field names. The router classifies abstentions by this token, so an unregistered value is silently unroutable. Enforced by `check_anchors()`.

## 011 — V7 sensor rationale and QUARANTINE severity
Date: 2026-08-01  Session: D06  Decided by: human
CCI boundaries are supplied by S1 (chest-ROI optical flow) and S2 (compression-audio periodicity). Both are monotonic time-series; overlapping intervals cannot arise from correct sensor output. An overlap therefore indicates a sensor defect, timestamp drift, or a chunk-boundary merge error — not a clinical ambiguity. Merging would distort total no-flow time and mask the upstream bug. QUARANTINE.

## 012 — Cross-field validator emission: per-instance vs. aggregate
Date: 2026-08-01  Session: D06  Decided by: human, agent
Cross-field validators emit results per-instance rather than aggregating N affected events into a single result. While aggregate results reduce item count in a review queue, per-instance emission provides precise timestamp and event attribution for every violation, enabling exact filtering and root-cause localization without string parsing.

## 013 — V00 short-circuiting on out-of-range timestamps
Date: 2026-08-01  Session: D06  Decided by: human, agent
Validator `V00_timestamp_in_range` (`0 <= t <= video_duration_s`) runs first in `validate_stream` and short-circuits immediately if any event or interval timestamp is out of range or negative. A stream with out-of-range timestamps has a broken clock or ingestion error, rendering all downstream interval comparisons and sequence checks unreliable. Short-circuiting prevents downstream validators (such as V03 or V04) from emitting spurious clinical count or interval mismatch flags when the root fault is upstream clock/ingestion corruption.

## 014 — BigQuery Terraform Region, Embedding Exclusion, and IAM Access Model
Date: 2026-08-01  Session: D07a  Decided by: human
1. **Region**: Single region `us-east4` is fixed across all three datasets (`resus_raw`, `resus_curated`, `resus_scratch`) to provide the narrowest defensible institutional PHI footprint for IRB compliance.
2. **Embeddings**: `fact_utterance.text_embedding` (`ARRAY<FLOAT64>`) is dropped from table schemas per Q-011 (deferred to retrieval layer; audio/voice embeddings are derived PHI / biometric identifiers requiring independent IRB review).
3. **IAM & Authorized Views**: `sa-analyst` and `sa-reviewer` get `roles/bigquery.dataViewer` access strictly on the curated dataset (`resus_curated`), which exposes authorized views over `resus_raw` (`v_redcap_wide`, `v_exemplar_store`, `v_fact_event`). Both accounts have zero direct IAM bindings on `resus_raw`, ensuring queries against `fact_utterance` or `fact_event.evidence` return `PERMISSION_DENIED`.
4. **Deployer SA**: `sa-deploy` on production has no human-assumable binding, restricted strictly to CI OIDC workflow federation.

## 015 — D07 BigQuery dataset mapping and scratch exclusion rule
Date: 2026-08-01  Session: D07  Decided by: human, agent
All thirteen physical tables generated by `bq_ddl.sql` reside in `resus_raw` (including `fact_near_miss`, which stores verbatim clinical speech quotes from 1/3-vote dropped events as PHI for threshold tuning). The seven read-path and audit views reside in `resus_curated`. `resus_scratch` never receives tables from `bq_ddl.sql`; it serves strictly as a `--dataset-prefix` target for ephemeral CI deployments. `bq/deploy.py` structurally rejects any deployment target ending in `_scratch` or containing `scratch`.

## 016 — Wide view pivot columns and SHA-256 checksum enforcement
Date: 2026-08-01  Session: D07  Decided by: human, agent
`v_redcap_wide` pivots strictly on `IMPORTABLE_COLUMNS` (1,889 expressions derived dynamically from `not server_computed` on `FieldSpec`), including reducer-populated text count fields (`num_cci_v2`, `num_times_defib_ed_v2`, etc.) and excluding only the two server-computed `calc` fields (`dur_mccd_app_ed_secs_v2`, `duration_ventilator_place_v2`). The generated view includes a SHA-256 header comment (`-- CHECKSUM: <sha256>`); `bq/deploy.py` verifies this checksum before applying and refuses deployment if `v_redcap_wide.sql` has been hand-edited.




