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

## 017 — D08 Sequence-based event_id scoping and global nearest-neighbour ensemble matching
Date: 2026-08-01  Session: D08  Decided by: human, agent
1. **Sequence-based Event ID**: To ensure deterministic idempotency under small timestamp drift across pipeline re-runs, `event_id` is computed as `sha1(case_id|type|ordinal)[:12]`, where `ordinal` is the 1-based index of that event among all events of that type sorted by time (`t_start_s`). `detector` is excluded from the hash to prevent brittleness under merged detector combinations. `fact_event` stores POST-ENSEMBLE events only, keyed by `event_id`, with `run_id` indicating the ensemble run (`run_ensemble_v1`), not a member run.
2. **Global Nearest-Neighbour & Monotonic Matching**: When ensembling $k$ parallel runs, candidate event pairs across member runs are sorted by distance (`|Δt|` ascending) and greedily clustered within `sum(t_precision_s)` tolerance. Within any event type, matches are constrained to be MONOTONIC (order-preserving, no crossing edges), eliminating matching cascade across long sequential series. For intervals, tolerances check both start and end boundaries (`t_start_s` and `t_end_s`), preventing differing durations from pairing. Any unmatched event (singleton cluster) records `attributes["unmatched_log"]` noting the nearest rejected candidate timestamp and delta for human audit.
3. **1/1/1 Categorical Tie & Spread Routing**: On accepted events, categoricals take a majority vote; a 1/1/1 three-way tie abstains (`abstained_1_1_1_tie`) and sets `routed_to_human=True`. Any cluster where `ensemble_spread_s > 3.0s` also sets `routed_to_human=True`.
## 018 — D09 Confidence routing policy, mandatory TEAM review, deep-link ROI, and objective-first queue ordering
Date: 2026-08-01  Session: D09  Decided by: human, agent
1. **Dynamic YAML Configuration & Untuned Thresholds**: Difficulty confidence thresholds (`LOW: 0.80`, `MEDIUM: 0.85`, `HIGH: 0.92`) and routing parameters (`spread_threshold_s: 3.0`) reside in `config/routing.yaml`, editable by the clinical lead without code changes. We do not tune thresholds to force an 85% auto-accept rate on synthetic data; instead, we report the realized rate (24.6% on default synthetic stream; 97.1% on all-high-confidence synthetic stream) and calibrate thresholds empirically on real P1/P2 output.
2. **Mandatory TEAM Routing (Q-006)**: Until per-item ICC vs. two human raters exceeds 0.75, all 12 TEAM fields route unconditionally regardless of confidence. TEAM fields are identified by registry rule (`rule == 'team_score'`) across dictionary sections, avoiding form_name/source_class misconceptions.
3. **Deep-Link ROI Contract**: Every `QueueItem` provides `deep_link` formatted as `video_uri#t={max(0.0, t_start_s - 10.0)}`, landing the reviewer 10 seconds before the event to minimize scrubbing time.
4. **Objective-First Queue Ordering**: `ReviewQueue.next_item()` sorts unreviewed items by `(queue_class == 'subjective', not required, -difficulty_rank, confidence)` ascending. Subjective TEAM ratings (`queue_class = 'subjective'`) are ordered after objective timestamp/UTD items (`queue_class = 'objective'`), ensuring subjective ratings are evaluated with the whole case in mind.
5. **A3 Exemplar Few-Shot Feedback Loop**: Every human correction (`submit()`) where `human_value != ai_value` writes an `ExemplarRecord` (`{case_id, event_id, field_name, event_type, ai_value, human_value, clip_t0, clip_t1}`) retrievable by `event_type` to close the HITL learning loop.

## 019 — D10 Derived QI metrics layer, interim CCF denominator (Q-012), NULL vs zero representation, and declarative formula versioning
Date: 2026-08-01  Session: D10  Decided by: human, agent
1. **Interim Default CCF Denominator Option (c)**: CCF denominator candidate (c) (*first compression -> termination, excluding sustained-ROSC periods*) is implemented as the interim default (`Q-012`). This is configurable via `ccf_denominator_mode` in `config/metrics.yaml` so changing candidates is a 1-line change.
2. **NULL vs 0 Contract**: Non-computable metrics (e.g., peri-shock pauses when zero shocks occurred, first-pass success when zero airway attempts occurred) explicitly emit a `MetricRow` with `value = None` (`NULL`) and a descriptive `null_reason`. A value of `0` is strictly reserved for measured quantities that evaluate to zero.
3. **Numerator & Denominator Recording**: Every ratio or fraction metric records both `numerator` and `denominator` explicitly on the `MetricRow` so case aggregations sum numerators and denominators rather than averaging ratios.
4. **S7 Diarized ASR Dependencies**: ASR-dependent metrics (`closed_loop_completion_rate` and `n_unacknowledged_directives`) emit `value = None` with `null_reason: "requires S7 diarized ASR"`, ensuring prompt schema assembly finds all enumerated metric keys without KeyError.
5. **REDCap Calc Field Replacements**: The two REDCap server-computed calc fields (`dur_mccd_app_ed_secs_v2` and `duration_ventilator_place_v2`) are computed independently in `fact_metric` (`source = "REDCAP_CALC_REPLACEMENT"`), dynamically resolved from `FIELDS` by `source_class == "REDCAP_CALC"` to avoid field-name literals.
6. **Declarative Formula Versioning**: All QI formula specifications reside in prose in `metrics/definitions.yaml`. `metric_definition_version` is an 8-character SHA-256 hash computed over the prose statements only, so refactoring Python code without changing formulas leaves the version unchanged.

## 020 — D10 Architectural Decision on Emitted Column Scope (Option a) and Checkbox Repeating Group Expansion
Date: 2026-08-01  Session: D10  Decided by: human, agent
1. **Row for Every Exportable Column (Option a)**: `reduce_stream()` emits a `FieldValue` row for every single one of the 1,879 exportable dictionary columns (all non-server-computed, non-roster/human-only columns, including every repeating group slot up to max instances). Inactive repeating group slots emit with `is_null=True` (`value=None`) and `branching_satisfied=False` when branching predicates are evaluated.
2. **Repeating Group Checkbox Expansion**: Checkbox rules in repeating groups (`groups:` in `mapping/registry.yaml`) specify `kind: 'checkbox'`. `_execute_rule()` resolves `rule_type = rule.get('rule') or rule.get('kind') or 'attr'`, ensuring every repeating checkbox field expands into its individual binary export columns (`___1` ... `___N`).
3. **D12 Set Equality Check**: Because every exportable column is emitted by `reduce_stream()`, the D12 milestone coverage test is a strict set-equality assertion (`set(fv.export_column for fv in fvs) == expected_export_columns`).

## 021 — D11 REDCap Payload Assembly & Client Architecture
Date: 2026-08-01  Session: D11  Decided by: human, agent
1. **SUBMISSION_COLUMNS Ownership**: `assemble_submission` owns `record_id`, `video_review_complete`, and all 10 non-AI (`ROSTER_JOIN` + `HUMAN_ONLY`) columns, setting each of those 10 to `""` (present-and-blank) so REDCap `overwriteBehavior=overwrite` clears stale manual entries. Asserts exact set equality against `SUBMISSION_COLUMNS` (1,891 keys).
2. **Checkbox Completeness (I4)**: Iterates `FIELDS` after the main loop, defaulting unpopulated checkbox choice export columns to `"0"`, ensuring binary `"1"`/`"0"` across all 1,098 checkbox choice columns.
3. **HTTP 400 Non-Retry**: Client never retries HTTP 400 validation errors, instead attaching parsed field errors to `quarantine_reasons`. Only retries 5xx and connection errors with exponential backoff and jitter.
4. **Quarantine Blocking**: A single validation failure (`not validation_passed`) or unverified routed field (`routed_to_human and not human_verified`) blocks the entire record, returning `({}, quarantine_reasons)`.
5. **video_review_complete="1" Interim Default**: Hard-codes `"1"` (Unverified/Incomplete) until an affirmative case-level sign-off table is implemented (`Q-013`). Never emits `"2"` from field-level inference alone.

## 022 — D12 Fixture Architecture & Schema-Aware Coverage Degradation
Date: 2026-08-01  Session: D12  Decided by: human, agent
1. **Dynamic Maximal Stream Construction**: `build_event_stream()` in `fixtures/synthetic_maximal.py` dynamically inspects `FIELDS` to build a maximal case without hand-coding counts or literals, exercising all repeating groups at their cap (`defib`: 30, `cci`: 30, `airway`: 8, `rosc`: 20, `vent_delay`: 5), cycling all 21 reason codes across the 30 CCIs, and satisfying all branching conditions.
2. **Clinical Plausibility in Golden Case (`golden_case_01`)**: Built `fixtures/golden_case_01.py` from an explicit 22-minute clinical resuscitation narrative (`OHCA`, 12 CCIs, 3 defibrillations, 2 airway attempts, 1 ROSC episode, provider crowding occlusion 11:00–11:30, low-confidence arterial line reading at 14:22).
3. **Schema-Aware Coverage Degradation in `gate_3way`**: Resolved a schema mismatch where `gate_3way` coverage degradation previously emitted `'3'` (`Unable to determine`) for 2-choice REDCap radio fields (`{'1': 'Yes', '2': 'No'}` such as `mccd_applied_ems_v2`), causing REDCap dictionary validation failures. When `f_spec.choices` lacks choice `'3'`, `_check_coverage_degraded()` emits `value = None` (`is_null = True`), `abstained = True`, and `routed = True` with `abstain_reason="Channel coverage degraded"`.
4. **Split Coverage Assertions**: D12 milestone coverage suite (`tests/test_coverage.py`) splits the headline assertion into two distinct artifacts: `test_reducer_emits_every_expected_column()` proving `reduce_stream()` emits exactly 1,879 columns, and `test_payload_equals_submission_columns()` proving `assemble_submission()` produces exactly 1,891 keys (`IMPORTABLE_COLUMNS | {"record_id", "video_review_complete"}`).

## 023 — A06 Fixture Split & P4b Verbatim Placement
Date: 2026-08-01  Session: A06  Decided by: human, agent
1. `tests/fixtures/passes_v2.0_source.md` amended: `=== P4 ===` split into `=== P4A ===` and `=== P4B ===`, and the P4b template supplied in full. The original staging carried only a one-line pointer for Call B because the v2.0 prompt spec described it as a delta against v1 rather than restating it. Text supplied by the human author; not agent-generated. The fixture remains the golden source and the round-trip test now covers six sections.

## 024 — A06 P3 Case-Field Name Reconciliation (Agent-Initiated)
Date: 2026-08-01  Session: A06  Decided by: agent
1. **Agent-Initiated Case-Field Rename in P3**: In `tests/fixtures/passes_v2.0_source.md` and `prompts/passes/p3_adjudicate.v2.0.md`, updated `ohca_ihca` -> `arrest_location` and `video_start_late` -> `recording_started_late` to match D05 contract symbol renaming, and changed `review_trigger` -> `review trigger metadata` (without underscore) to prevent REDCap export column literal collisions (`assert_no_field_names`, Invariant I2). The semantic instruction that administrative review metadata is not determinable from video and is always null is preserved verbatim.

## 025 — A06 P4a Illustrative Metric Tokens Without Braces
Date: 2026-08-01  Session: A06  Decided by: human, agent
1. **Brace-Free Illustrative Metric Format Tokens**: Replaced `{v}`, `{n}`, `{d}` in `p4a_team_items` illustrative objective metrics example block with brace-free `<value>`, `<numerator>`, `<denominator>` formatting tokens in both `tests/fixtures/passes_v2.0_source.md` and `prompts/passes/p4a_team_items.v2.0.md`, and deleted `d`, `n`, `v` declarations from `prompts/passes/_PLACEHOLDERS.yaml`. This prevents illustrative sub-tokens from being swept into placeholder declarations and ensures `validate_template_placeholders` and `_validate_no_unfilled_placeholders` operate strictly on builder-supplied values.

## 026 — S03 Sensor S1 and S6 Calibrated Threshold Profiles
Date: 2026-08-04  Session: S03  Decided by: agent
1. **Calibrated ROI Configuration Surface (`S03`)**: Implemented `profiles` mapping in `sensors/calibration/roi_config.yaml` supporting `default`, `UNKNOWN`, and `simvideo2` profiles for Sensor S1 (chest-ROI optical flow CPR compression motion detection) and Sensor S6 (visual occlusion and provider crowding coverage notes). In S1, a Butterworth bandpass filter (`1.5-2.5 Hz`, corresponding to `90-150 cpm`) applies to vertical optical flow velocity over the chest ROI, emitting `compression_motion` intervals and deriving pause intervals as `compression_interruption` (CCI) intervals with confidence scores. In S6, ROI standard deviation thresholding (`< 15.0`) emits `coverage_note` events (`provider_crowding`). Both sensors strictly enforce determinism across repeated executions and expose their entire threshold surface via `report_calibration_surface()`.

## 027 — Q-012 Sub-Decision: Gating CCF t_last on death_pronounced
Date: 2026-08-05  Session: S03  Decided by: human, agent
1. **Gating `t_last` on Pronouncement of Death**: In CCF calculations (`compute_ccf`), when a confirmed `death_pronounced_s` timestamp is present in clinical milestones or ground truth, `t_last` is strictly gated at that timestamp rather than relying solely on the final observed compression interval boundary. This aligns CCF measurement bounds ($t_{\text{first}} = 36\text{s}$ upon patient room entry with active mechanical CPR to $t_{\text{last}} = 922\text{s}$ upon death pronouncement) with clinical termination and excludes post-resuscitation artifacts or debriefing motion.

## 028 — S07 Sensor S2 Acoustic-Visual Fusion Contract & Occlusion-Gated Operator
Date: 2026-08-05  Session: S07  Decided by: human, agent
1. **Retraction of Boolean OR-Fusion Artifact**: Formally retracted earlier reports of improved CCF error (`0.04`) under simple boolean union fusion (`compressions_active = S1 OR S2`). Because ambient room speech and alarms share the $1.3\text{–}3.0\text{ Hz}$ envelope band, OR-fusion allowed noisier acoustic detections to override clean optical signals, erasing 4 of 7 real clinical rhythm check pauses and collapsing $\pm 3\text{s}$ recall from `0.71` to `0.14`. The apparent CCF accuracy improvement arose entirely from over-detection ("never stopped" happens to approximate 90.7% on this case).
2. **Canonical Occlusion-Gated Fusion Operator**: Adopted strict occlusion-gated arbitration where Sensor S2 arbitrates **ONLY** inside confirmed Sensor S6 visual occlusion windows (`provider_crowding` signatures identified by massive bounding pixel shifts). Where S1 is confident and unoccluded, S1 decides and S2 is ignored; unoccluded S1 gaps remain genuine pauses. Inside S6 occlusion windows, S2 evaluates frequency lock ($| \text{peak\_hz} - \text{device\_hz} | \le 0.08\text{ Hz}$) and frame stability ($\text{std} \le 0.05\text{ Hz}$ over 3 consecutive STFT frames), separating metronomic mechanical LUCAS thumps ($1.70\text{ Hz}$) from wandering speech peaks. This architecture preserves $100\%$ of true recall (`0.71`) while elevating interval precision from `0.07` to `0.10` and $\pm 3\text{s}$ F1 from `0.19` to `0.21`.






