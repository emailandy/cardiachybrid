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

## 028 — S07 Sensor S2 Acoustic-Visual Fusion Contract & Definitive Negative Finding (`F-023`)
Date: 2026-08-05  Session: S07  Decided by: human, agent
1. **Retraction of Boolean OR-Fusion Artifact**: Formally retracted earlier reports of improved CCF error (`0.04`) under simple boolean union fusion (`compressions_active = S1 OR S2`). Because ambient room speech and alarms share the $1.3\text{–}3.0\text{ Hz}$ envelope band, OR-fusion allowed noisier acoustic detections to override clean optical signals, erasing 4 of 7 real clinical rhythm check pauses and collapsing $\pm 3\text{s}$ recall from `0.71` to `0.14`. The apparent CCF accuracy improvement arose entirely from over-detection ("never stopped" happens to approximate 90.7% on this case).
2. **Definitive Negative Finding for Sensor S2 on Mono Audio (`F-023`)**: Evaluated both Hilbert amplitude-envelope STFT periodicity and spectral flux onset detection (Inter-Onset Intervals / IOI) on quiet-room compression frames and true human pauses. Even restricted to the quietest tertile of S1 confirmed mechanical compressions, envelope peak IQR remained broad ($1.50\text{–}1.95\text{ Hz}$), overlapping completely with true human pauses ($1.50\text{–}2.40\text{ Hz}$). Similarly, inter-onset intervals during metronomic compressions showed wide, irregular distribution ($\text{std} = 0.137\text{s}$, vs $< 0.03\text{s}$ metronomic floor), indistinguishable from true pauses ($\text{std} = 0.279\text{s}$). Under strict data-derived lock ($1.70 \pm 0.08\text{ Hz}$), S2 contributes 0 bridged occlusions (`S1 alone (S2 inactive)`). This establishes a clean stopping point: single-channel acoustic cadence cannot function without Sensor S7a speech rejection first. Resolving S1's 39 visual occlusion dropouts requires either a 5-second reporting floor or LLM candidate adjudication, neither of which requires S2.

## 029 — S03a Three-Tier Consumer Duration Rules & S1 Evaluation Standards
Date: 2026-08-05  Session: S03a/S03b  Decided by: human, agent
1. **Three-Tier Consumer Duration Rules**: Formalized consumer-specific duration floor rules for Sensor S1 detected clinical pauses (`filter_ccis_by_consumer`): Consumer 1 (`ccf`) counts all unoccluded physical pauses $\ge 1.0\text{s}$ (`min_pause_duration_s`); Consumer 2 (`redcap` / `repeating_group`) enforces the dictionary $\ge 3.0\text{s}$ rule; Consumer 3 (`reporting`) applies the calibrated reporting floor (`cci_reporting_floor_s: 5.0` from `roi_config.yaml`). Three consumers, three rules, two measurements (the interval stream and an independently-derived CPR duration, which differ by 15.96s over the CCF window). All earlier evaluation baselines are formally superseded by commits `769269f` (scale-free frequency gate and MAD impulse rejection), `5017dbc` (decouple 1.0s detection floor), and `9da9e74` (F-021 envelope window smoothing and 40s cadence variance) and replaced by reproducible command `sensors.eval.report`.

## 030 — S03b Pytest Real-Video Deselection Configuration
Date: 2026-08-05  Session: S03b  Decided by: human, agent
1. **Pytest Real-Video Deselection Configuration**: Documented that default test invocation (`python -m pytest`) silently excludes all end-to-end integration and accuracy evaluations on real clinical video because `pyproject.toml` defines `addopts = "-m 'not integration and not network'"`. This deselection excludes the sole real-video OCR decoding evaluation for Sensor S5 (`test_read_timecode_decodes_a_real_frame`), deterministic accuracy evaluations for Sensor S1 (`test_s1_s6_deterministic_5_runs`, `test_s1_vidsim2_percentiles_and_shock_containment`), full-track audio parsing for Sensor S3, and REDCap round-trip integration suites. Executing with `-o 'addopts='` bypassed exclusions and collected all 229 tests (223 passed, 6 skipped: Q-014 external scratch REDCap live integration tests). Recorded as an architectural decision record without altering test suite configurations during session S03b.

## 031 — S03b Ungated CCF Report Mismatch & Evaluation Window Reconciliation (`F-026`)
Date: 2026-08-05  Session: S03b/S03c  Decided by: human, agent
1. **Ungated CCF Report Disagreement & Window Mismatches (`F-026`)**: Discovered that `test_ccf.py::test_generate_ccf_report_vidsim2` passes while `ccf_report.py` runs over the full un-truncated video duration ($1,363.78\text{s}$), ungated on `death_pronounced_s` ($922.0\text{s}$) and without consumer duration floor filtering (`filter_ccis_by_consumer`). This directly contradicts Decision 027 / Q-012, producing **$\text{CCF} = 0.8766$**. Furthermore, when F-026 was originally documented, the evaluation path itself ($0.8170$, computed over $70.75\text{–}922.0\text{s}$) was comparing against GT across mismatched windows ($0.9074$, computed over $36.0\text{–}922.0\text{s}$). Reconciled evaluation to compare S1 ($0.8170$) against the true comparable GT CCF of $0.9037$ over the identical $70.75\text{–}922.0\text{s}$ window. Recorded as a silent-pass defect (green test, wrong window); repairing and wiring `ccf_report.py` is the established starting point for the upcoming CCF report task. Note: existing test assertions in `test_generate_ccf_report_vidsim2` (`assert report.total_case_duration_s == pytest.approx(1363.78, abs=0.5)` and `assert len(report.cci_intervals) >= 40`) actively encode this ungated full-track behavior and will need to change with the fix when gating is implemented, so the next session does not mistake a correct failure for a regression.

## 032 — S03b Retraction of F-024, Establishment of F-027, F-028, and F-029
Date: 2026-08-05  Session: S03b  Decided by: human, agent
1. **Retraction of F-024 and Establishment of F-027 (GT #1 Floor Recall Loss)**: Retracted F-024 which wrongly claimed GT #5 was lost to the reporting floor (floored interval #7 cleanly matches GT #5). Established F-027: the true lost interruption is GT #1 ($147\text{–}155\text{s}$, $8.0\text{s}$), truncated by optical flow to $4.62\text{s}$ ($150.00\text{–}154.62\text{s}$) and discarded by the $\ge 5.0\text{s}$ floor (dropping recall $5/7 \to 4/7$).
2. **Total Fragmentation of GT #7 (`F-028`)**: Established F-028: the longest clinical pause ($844\text{–}874\text{s}$, $30.0\text{s}$, $36.6\%$ of all no-flow time) was fragmented into 4 sub-$5\text{s}$ slivers ($1.19\text{s}$, $2.25\text{s}$, $1.25\text{s}$, $3.82\text{s}$) by continuous provider movement during resuscitation termination, missing $71.6\%$ ($21.49\text{s}$) of no-flow duration.
3. **Structural Absence of Shock Containment in Mechanical CPR (`F-029`)**: Retracted earlier claims of shock containment. Confirmed 0 of 5 defibrillation shocks fall inside pauses during mechanical CPR (shocks land 5–17s after pauses end).

## 033 — Mandatory Repository-Local Transient Artifacts & Guaranteed Cleanup (`F-036`)
Date: 2026-08-06  Session: G1  Decided by: human, agent
1. **Repository-Local Restricted Scratch Space**: Intermediate media extractions (e.g. ffmpeg audio extracts) must never be written to shared, world-readable directories like `/tmp/` or system `tempfile.gettempdir()`. On clinical deployments, intermediate audio extracts contain unredacted resuscitation room speech (PHI). All transient extractions must target a project-local working directory (e.g. `.resus_qc_tmp/`), gitignored, and created with restrictive user-only permissions (`0700`).
2. **Guaranteed Cleanup Lifecycle**: All transient files must be managed within context managers or explicit `try ... finally` blocks that guarantee deletion on success, unhandled exceptions, and process interrupts (`SIGINT`/`SIGTERM`).
3. **No Non-Deterministic Caching**: Filenames based on process-randomized `hash(...)` that cannot be deterministically resolved across executions are prohibited. Intermediate extractions must either be strictly ephemeral (unlinked immediately after array loading) or indexed deterministically.

## 034 — Negative Control Video Provenance & S1 Optical Flow Floor Verification
Date: 2026-08-06  Session: S09  Decided by: human, agent
1. **Retraction of Room 2 Negative Control (`blankbayvideo.mp4`)**: Frame-to-frame pixel difference analysis across all 937 consecutive frame pairs proved that from $t=4.0\text{s}$ through $t=31.27\text{s}$, `blankbayvideo.mp4` is a static frozen still frame at the terminal DVR freeze timestamp (`08:15:30.818 AM`). Optical flow was zero ($\text{std} = 0.000764\text{ px}$) by construction. The earlier `AA5` explanation of "147x lower flow due to dark mattress texture and lighting" is falsified and retracted. Room 2 has zero empirical negative control in the codebase.
2. **Room 1 Negative Control Verification (`blankbayvideop1.mp4`)**: Verified as an active live video stream of the Room 1 empty resuscitation bay bed prior to patient entry. On the longest continuous unspliced segment ($t=18\text{–}30\text{s}$, 361 frames), S1 optical flow measures genuine camera noise with a windowed modulation of **`0.0043`**, safely below the `min_modulation: 0.010` floor (a factor of $2.3\times$).
3. **Clinical Calibration Prerequisite**: Calibration protocols must require empty-bay negative control clips to be verified live (monotonically advancing timecode at $1/\text{fps}$ and non-zero inter-frame pixel variance) prior to acceptance.

## 035 — S5 Vertical Projection Profile OCR Architecture & Clean Template Bootstrapping
Date: 2026-08-06  Session: S09  Decided by: human, agent
1. **Vertical Projection Profile Architecture**: Replaced rigid column slicing with vertical projection profile segmentation on active character rows ($y=4..20$, binary threshold $190$), partitioning the timecode overlay into 23–24 isolated glyph cells via zero-energy valley boundaries. Separator templates (`/`, `:`, `.`) partition the string into semantic fields, handling variable-width dates (`MM/D/YYYY` vs `MM/DD/YYYY`) and camera-specific horizontal offsets dynamically.
2. **Context-Free Template Bootstrapping**: Script `scripts/extract_timecode_templates.py` extracts clean, edge-uncontaminated grayscale glyph templates (`0-9`, `/`, `:`, `.`, `A`, `M`) directly from reference frames with background margin verification on both lateral borders. No synthetic `P.png` is created; S5 operates strictly in morning envelope (`AM`) and cleanly abstains on afternoon footage under Invariant I5.
3. **Acceptance & Validation**: Successfully decodes Patient 2 / Room 2 (`simvid3.mp4`) as `12/8/2023 07:54:26.840 AM` (resolving day digit `8` without manual x-offset) and Patient 1 / Room 1 (`vidsim2.mp4`) as `11/7/2023 07:55:57.072 AM` ($T_0 = \text{2023-11-07T07:55:57}$, matching human clock logs at $t=300\text{s}$) with 5-run bit-identical determinism.

## 036 — Mechanical Cadence Cross-Case Validation (n=2) & Frame-Rate Transferability
Date: 2026-08-07  Session: S09  Decided by: human, agent
1. **Mechanical Classifier Validation on Second Case ($n=2$)**: Evaluated S1 optical flow across Patient 2 (`simvid3.mp4`, Room 2, 30 fps) at the corrected epigastric bed zone ($x=850, y=650, 100\times 100\text{ px}$). During mechanical Interval #5 ($t=483.2\text{–}591.2\text{s}$), the S1 classifier output was **`mechanical`** with cadence **$103.4\text{ CPM}$** and standard deviation **$\sigma = 2.40\text{ CPM} \le 3.0\text{ CPM}$**, successfully matching Patient 1's measured $102\text{ CPM}$ ($\sigma = 0.00$) and confirming the mechanical branch across two rooms, two camera geometries, and two frame rates ($16\text{ fps}$ and $30\text{ fps}$).
2. **Frame-Rate Parameter Scaling (AA9 Partial Resolution)**: 30 fps transfer confirmed mathematical scaling for:
   - Bandpass filter normalization ($f / (f_s / 2)$)
   - Rolling RMS window length (`int(1.6 * fps)`)
   - Cadence variance window length (`int(20.0 * fps)`)
   - Farneback frame time normalization.
   *(Note: Spatial pixel thresholds such as `impulse_min_spike_px: 2.0` remain unscaled across camera resolutions).*
3. **Manual Branch Untested & Patient 2 Status**: The manual classifier branch remains untested across rooms because Patient 2's manual phase is sub-floor at the bed ROI due to compressor occlusion and the static torso window breaks under two-minute provider rotations. For Patient 2, the manual phase ($t=13\text{–}483\text{s}$) is **`unable_to_determine` (UTD)**, while the mechanical phase ($t=483\text{–}591\text{s}$) is measurable with verified mechanical CPR.

## 037 — VERSIONS.yaml Model Bindings as Single Source of Truth for Call-Time Decoding Parameters
Date: 2026-08-08  Session: Task 3  Decided by: human, agent
1. **Single Source of Truth**: All runtime model decoding parameters (`model`, `temperature`, `thinking`, `ensemble_k`, `seed`) are declared in `prompts/VERSIONS.yaml` under `model_binding` and accessed via `get_model_binding(pass_name)` in `prompts/registry.py`. No numeric temperature or thinking literals are permitted in execution scripts (`scripts/run_case.py`).
2. **Fail Loudly**: `get_model_binding()` raises `KeyError` immediately if a pass name is not declared in `VERSIONS.yaml`. Silent fallbacks to API defaults (such as unseeded sampling or default temperature 1.0) are prohibited.
3. **Plumbing to VertexClient**: Parameters are plumbed through `call_model_cached()` to `VertexClient.generate()`, constructing `GenerateContentConfig(temperature=..., seed=..., thinking_config=...)`.
4. **P3 Greedy Invariant**: Pass 3 adjudication is strictly bound to `temperature: 0.0` (greedy decoding) and `thinking: high` to ensure deterministic reconciliation of clinical intervals and event boundaries.

## 038 — Falsification of Multimodal Video Decoding Determinism via Seed Parameter (Task 4 Diagnostic)
Date: 2026-08-09  Session: Task 4  Decided by: human, agent
1. **Falsification of Seed Efficacy on Multimodal Payloads**: Controlled A/B probing on P1 Window 0 (`scripts/probe_seed_efficacy.py`) empirically demonstrated that `GenerateContentConfig(seed=42)` is inert on Vertex AI for multimodal video inputs (`gemini-3.1-pro-preview`). Consecutive calls with bit-identical input files (MD5 `8670427883332f487c1c25f6d2dc7198`), identical prompt text, identical temperature (`0.6`), and identical seed (`42`) produced divergent output tokens (2,527 chars vs 3,247 chars) and differing event streams.
2. **Correction of Task 3 Determinism Claim**: Task 3's initial interpretation that "variance was eliminated" is retracted and falsified. Apparent 0.0s spread on certain shocks was an artifact of $n=1$ single observations or stochastic coincidences; Shock #4 spread 12.0s across seeded runs, and overall recall degraded from 100% to 40–80%.
3. **Strict Spread/Variance Discipline**: Any spread or variance metric across runs must report sample size $n$ and emit `n/a` whenever $n < 2$. Single observations cannot define a zero spread.
4. **Architectural Consequence**: Bit-exact reproducibility cannot be achieved via client-side decoding parameters alone on multimodal video payloads. Non-determinism is a platform property to design around (via ensembling, deterministic sensor layers S1-S7, and temporal anchor grounding).














