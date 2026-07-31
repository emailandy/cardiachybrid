=== D00 ===
D0 — Scaffold
Create the repo skeleton for `resus_qc`. Read AGENTS.md first; it governs
everything.

Directories: dictionary/ codegen/ codegen/templates/ mapping/ generated/
reducer/ ingest/ bq/ redcap/ router/ metrics/ fixtures/ tests/ scripts/

Files to create:
- pyproject.toml — Python 3.11, ruff + mypy strict config, pytest with markers
  `integration` and `network` (both deselected by default), package deps:
  pyyaml, pydantic>=2, httpx, google-cloud-bigquery. dev: pytest, ruff, mypy.
- .gitignore — ignore generated/* EXCEPT generated/coverage_manifest.json
  (use a negation rule and verify it works with `git check-ignore -v`).
- scripts/hash_dict.sh — writes sha256 of dictionary/instrument.csv to
  dictionary/dict_version.txt.
- scripts/build.sh — hash → codegen → manifest → pytest, failing fast.
- codegen/known_bugs.py — BRANCHING_OVERRIDES dict with the four staged
  overrides (RC-1041 sono_window_cci_1, RC-1042 rhythm_rosc_15_v2, RC-1043
  mccd_type_ems_v2 cross-form ref, RC-1044 reason_cci_1_v2 missing code 21)
  and APPLY_OVERRIDES = False.
- Empty __init__.py in each package dir.
- README.md — 20 lines: what this is, how to build, where the invariants live.

DO NOT write any parsing, reducing, or BigQuery logic yet.

ACCEPTANCE: `bash scripts/build.sh` runs and fails only because codegen does not
exist yet. `git check-ignore -v generated/redcap_fields.py` reports ignored;
`generated/coverage_manifest.json` reports NOT ignored.

=== D01 ===
D1 — Dictionary parser
Implement `codegen/redcap_dict_to_code.py`: parse a REDCap Data Dictionary CSV
into typed FieldSpec objects. Read AGENTS.md.

INPUT: dictionary/instrument.csv — standard 18-column REDCap export. May be
comma- or tab-delimited. May carry a UTF-8 BOM. Header wording varies by REDCap
version.

Implement: FieldSpec dataclass, sanitize_choice_code, parse_choices,
implicit_choices, build_spec, tag_repeats, load_dictionary, dict_hash.

HARD REQUIREMENTS — each of these has cost a real project real data:
1. Match headers by slug (lowercase, strip non-alphanumeric), never exact string.
2. Choice parsing splits on the FIRST comma only. Labels contain commas:
   "3, Dual defibrillation (two sets of pads were used in anterolateral, and
   anteroposterior locations)" must parse to code "3".
3. sanitize_choice_code: lowercase then re.sub(r"[^a-z0-9_]", "_", code).
   Write a unit test asserting "-1" → "_1" → column "field____1" (FOUR
   underscores). This one is easy to get subtly wrong.
4. yesno → {"1":"Yes","0":"No"}. truefalse → {"1":"True","0":"False"}.
   Assert this in a test with an explicit comment on why.
5. field_type "calc" → server_computed=True (excluded from import payloads).
   field_type "descriptive" → carries_data=False, zero export columns.
6. Raise ValueError WITH THE CSV LINE NUMBER on: duplicate field name, export
   column collision across two fields, invalid variable name (must match
   ^[a-z_][a-z0-9_]*$), unknown validation type, duplicate choice code within
   one field.
7. Strip HTML from field_label and section_header (several labels are
   rich-text divs with embedded <img> tags).
8. tag_repeats: the CCI group has TWO regex patterns because seven sub-fields
   (sono_window_cci_N, echo_success_cci_N, us_pulse_cci_N, us_pulse_present_cci_N,
   aline_cci_N, aline_sbp_cci_N, aline_dbp_cci_N, loc_pulse_check_cci_N) have NO
   _v2 suffix while their siblings do. Same inconsistency affects
   time_ecmo_called / time_ecmo_initiated / time_ecmo_success and
   decision_time_thromb_ed. Do not "normalize" these.

DO NOT: hardcode any field name from this instrument; special-case any variable;
write a REDCap API client; import outside the stdlib.

ACCEPTANCE: `python -c "from codegen.redcap_dict_to_code import load_dictionary;
s=load_dictionary(Path('dictionary/instrument.csv'));
print(len(s), sum(len(x.export_columns) for x in s.values()))"`
prints exactly `909 1889`. (record_id and video_review_complete are added later
by the registry, bringing totals to 911 / 1891.)
Tests in tests/test_parser.py cover every numbered requirement above.

=== D02 ===
D2 — Branching transpiler
Implement `codegen/branching.py`: REDCap branching logic → sandboxed Python
predicate. Read AGENTS.md.

Grammar to support:
  [field]              scalar reference
  [field(code)]        checkbox reference → the "1"/"0" of that export column
  = <> < <= > >=       comparison (= means ==, <> means !=)
  and or not           boolean
  ( )                  grouping
  'str' "str" 123 1.5  literals

Implement: transpile(expr) -> python_source, validate(src) -> ast.Expression,
compile_predicate(expr) -> Callable[[dict], bool].

HARD REQUIREMENTS:
1. NEVER eval the raw REDCap string. Transpile → ast.parse → walk the tree →
   reject any node type outside a hardcoded allowlist → compile. The only
   permitted Call targets are _v, _cb, _cmp, _truthy.
2. Comparison semantics must match REDCap: numeric comparison if BOTH operands
   coerce to float, otherwise lexical. A blank left operand is False for
   < <= > >= (a missing count is not "greater than 1").
3. A bare [field] used as a boolean is truthy unless "" or "0".
4. _cb must route the code through sanitize_choice_code from D1 so that
   [reason_cci_1_v2(4)] resolves to reason_cci_1_v2___4.
5. Raise on: unparseable token (report the offset and 40 chars of context),
   operator with no left operand, dangling comparison.
6. Attach .source and .redcap attributes to the returned predicate for
   debugging and for emission into generated/branching_compiled.py.

Then write `codegen/emit_branching.py` producing generated/branching_compiled.py
with one entry per field that has branching logic, plus a build-time warning
listing any active entry from known_bugs.BRANCHING_OVERRIDES.

ACCEPTANCE: every non-empty branching expression in instrument.csv compiles
without error (assert this over the full dictionary in a test).
tests/test_branching.py includes: numeric vs lexical comparison, blank-left-side
returns False, checkbox sanitization, a nested and/or/not expression, and a
malicious input like `[x] = __import__('os')` which must raise.

=== D03 ===
D3 — Registry validator + manifest
Implement `codegen/emit_manifest.py`. Read AGENTS.md and mapping/registry.yaml.

Three jobs:

1. SKELETON EMITTER (`--skeleton`): write mapping/registry_skeleton.yaml with
   every dictionary field, grouped by REDCap section header, each defaulted to
   source_class: UNMAPPED, with the field label as a YAML comment. This is the
   worklist a human fills. Never overwrite mapping/registry.yaml.

2. VALIDATOR: load mapping/registry.yaml and check it against the parsed
   dictionary. FAIL THE BUILD, with the field name and registry line number, on
   any of:
   - a `field:` or expanded `pattern:` that does not exist in the dictionary
   - a `vocab:` whose integer values are not a subset of that field's choices
   - a `range:` disagreeing with the field's val_min/val_max
   - `kind: checkbox` on a non-checkbox field, or a checkbox field without it
   - `rule: gate_yesno` on a field whose type is not yesno
   - `rule: gate_3way` on a field whose choices lack a third (UTD) code, unless
     vocab_override is supplied
   - any field left UNMAPPED
   - a `suppress_codes` entry naming a code absent from that field's choices
   - a group whose count_field is not a number-validated text field
   - a group whose max exceeds the highest index present in the dictionary

3. PER-INDEX VOCABULARIES: repeating-group vocabularies are NOT uniform.
   reason_cci_1_v2 has 20 codes; reason_cci_2..30_v2 have 21 (code 21 = ROSC).
   ecmo_called_ed_v2 uses code 5 for "not available" while the other two ECMO
   gates use 4. Derive every vocabulary PER FIELD from the dictionary and
   validate the registry's named vocab is a subset. Never assume uniformity
   across a group.

4. Emit generated/coverage_manifest.json:
   dict_version, registry_version, n_variables, n_export_columns,
   by_source_class{}, by_difficulty{}, suppressed_checkbox_codes[],
   unmapped[], no_anchor_card[], branching_overrides_staged[],
   branching_overrides_active[], required_fields_not_ai_extractable[].
   This file is COMMITTED so its diff surfaces in every schema-change PR.

ACCEPTANCE: against the supplied registry, manifest reports n_variables 911,
n_export_columns 1891, unmapped []. Then deliberately corrupt three things in a
COPY of the registry (a vocab value not in choices, a range mismatch, a
nonexistent field) and show the build failing with three distinct line-numbered
messages.

=== D04 ===
D4 — Emit Python artifacts
Implement `codegen/emit_python.py` → generated/redcap_fields.py and
generated/models.py.

generated/redcap_fields.py must contain:
- FIELDS: dict[str, FieldSpec] — every field, with registry governance merged in
  (source_class, difficulty, owning_event_types, expected_utd_floor,
  suppress_codes).
- EXPORT_COLUMNS: frozenset[str] — all 1891.
- REPEAT_GROUPS: dict with count_field, max, per-index field patterns.
- VOCAB: dict[str, dict[str, int]] — per-field resolved vocabularies (NOT the
  registry's named ones; the per-field resolution from D3).
- IMPORTABLE_COLUMNS: frozenset — export columns minus REDCAP_CALC and
  descriptive fields. This is what the REDCap client is allowed to POST.
- A module docstring carrying dict_version and a "DO NOT EDIT" banner.

generated/models.py: pydantic v2 models for the CANONICAL EVENT STREAM (not
REDCap): Evidence, Event, Interval, CoverageNote, CaseFields, EventStream.
The event `type` field is a Literal over the 40-value closed vocabulary read
from mapping/event_types.yaml (create that file from the registry's
owning_event_types union, sorted, if it does not exist).

HARD REQUIREMENTS:
- Emitted files are deterministic: sorted keys, stable formatting, so a rebuild
  with an unchanged dictionary produces a byte-identical file. Assert this in a
  test (build twice, compare hashes).
- No runtime dependency from generated/ back into codegen/.
- Emit a `_DICT_SHA` constant; a runtime assertion elsewhere will compare it to
  dictionary/dict_version.txt and refuse to run on drift.

ACCEPTANCE: `from generated.redcap_fields import FIELDS, EXPORT_COLUMNS` works;
len(EXPORT_COLUMNS) == 1891; rebuilding twice yields identical bytes; mypy
--strict clean on generated/.

=== D05 ===
D5 — Reducer engine
Implement `reducer/engine.py`: canonical event stream → list[FieldValue].
Read AGENTS.md. This is the highest-risk module in the codebase.

The engine is a REGISTRY INTERPRETER. It must contain ZERO references to any
specific REDCap field name, event type, or vocabulary value. A reviewer will
reject `if field == "..."`, `if event_type == "..."`, or any hardcoded index.

FieldValue dataclass: field_name, export_column, value, value_label, is_null,
abstained, abstain_reason, confidence, source_class, source_event_ids,
branching_satisfied, validation_passed, validation_error, routed_to_human.

Implement exactly these 12 rule primitives, dispatched from registry.yaml:
  case_field, first_of, last_of, nth_distinct_attribute, gate_3way, gate_yesno,
  count, attr, checkbox, notes, team_score, const_null, conditional_text
(13 including conditional_text — the registry's closed set).

NON-NEGOTIABLE SEMANTICS:
a. gate_3way returns 3 (UTD), not 2 (No), when zero events match AND any
   coverage_note overlaps the case on a channel listed in coverage_channels.
   Map channels→issues: speech→{audio_unintelligible};
   visual→{chest_occluded, provider_crowding, camera_motion, frame_dropout};
   monitor→{monitor_not_visible}; airway→{airway_not_visible}.
b. gate_yesno emits 1 or 0. Assert at runtime that the target field's type is
   yesno; raise if not.
c. checkbox iterates the DICTIONARY's choice codes for that specific field and
   emits "1" or "0" for EVERY code. Never iterate the selection. Honor
   suppress_codes by forcing "0" regardless of the event stream.
d. Repeating groups: filter by min_duration_s → sort by order_by → if count >
   max apply the truncation policy (longest_duration | earliest) → re-sort
   chronologically → assign 1-based indices. Emit count_field from the
   TRUNCATED length, write the TRUE count into overflow_note_field, and set
   routed_to_human on every field in that group.
e. gate: expressions in the registry ("reasons contains chest_us",
   "aline_present == 1") are evaluated against the event/interval attributes.
   Implement a tiny, closed evaluator — do not eval.
   When a gate is False and default_when_gated_null is set, emit that default;
   otherwise emit null with branching_satisfied=False.
f. Branching: after the full record is assembled, evaluate every compiled
   predicate from generated/branching_compiled.py. Set branching_satisfied. If a
   non-null value sits on a field whose predicate is False, blank it and append
   a Repair record. Order matters — build first, then gate.
g. Validation: enforce range, regex, and choice membership. On failure set
   validation_passed=False with a specific message. NEVER clamp, round, or
   coerce.
h. Provenance: every FieldValue carries source_event_ids. An AI_DIRECT field
   with a non-null value and an empty source_event_ids list is a bug — raise
   immediately, do not emit.

Return (list[FieldValue], list[Repair], list[Flag]).

ACCEPTANCE: engine.py under 500 lines. `grep -E '"[a-z_]+_v2"' reducer/engine.py`
returns nothing. tests/test_reducer_primitives.py covers each of a–h with a
minimal synthetic stream.

=== D06 ===
D6 — Transforms and cross-field validators
Implement `reducer/transforms.py` and `reducer/validators.py`.

transforms.py:
- Clock: video_t0_wallclock + offset seconds → "%Y-%m-%d %H:%M:%S".
  ⚠ REDCap's datetime_seconds_mdy controls DISPLAY only; the API format is
  Y-M-D. Encode this in a docstring so nobody "fixes" it later.
- to_redcap_datetime(t_s, t0), to_redcap_int, to_redcap_float,
  blank_when_null passthrough.
- Round to whole seconds (REDCap has no sub-second precision) but preserve the
  float in fact_event. Rounding is half-even.

validators.py — cross-field checks run before submission. Each returns
(severity, field, message) where severity ∈ {QUARANTINE, FLAG, REPAIR}:
1. every start < end                                        QUARANTINE
2. MCCD adjustment window ⊆ MCCD application window          QUARANTINE
3. num_times_defib == count of populated defib timestamps    QUARANTINE
4. every shock timestamp falls inside some CCI               FLAG
5. any shock present ⟹ shockable rhythm recorded             FLAG (never auto-fix)
6. no medication event inside a ROSC window                  FLAG (CLINICAL_REVIEW)
7. CCIs non-overlapping and monotonic                        REPAIR (merge, log)
8. ROSC episodes non-overlapping, end_i ≤ start_{i+1}        QUARANTINE
9. patient_enters_room ≤ every other timestamp               QUARANTINE
10. every airway attempt with successful=true has a
    subsequent confirmation                                  FLAG
11. calc fields absent from the payload                      QUARANTINE
12. dict_version in the payload matches dictionary/dict_version.txt  QUARANTINE

Read thresholds and the rule list from a YAML config, not from code, so the
clinical lead can adjust severity without a code change.

ACCEPTANCE: tests/test_validators.py builds a deliberately broken record
triggering each of the 12 and asserts the exact severity and message.

=== D07 ===
D7 — BigQuery layer
Implement `codegen/emit_sql.py` and `bq/deploy.py`.

emit_sql.py produces four artifacts:

1. generated/bq_ddl.sql — ten tables per dictionary/DDL_SPEC.md: dim_case,
   dim_run, fact_event, fact_interval, fact_utterance, fact_sensor_interval,
   dim_redcap_field, fact_redcap_field, redcap_submission, fact_metric.
   PARTITION BY event_date, CLUSTER as specified. attributes / evidence /
   payload / choices columns are JSON type, not STRING.

2. generated/dim_redcap_field_seed.jsonl — one row per variable including the
   governance columns. The loader must TRUNCATE-AND-REPLACE scoped to
   dict_version, never append.

3. generated/v_redcap_wide.sql — a generated pivot view over fact_redcap_field,
   one MAX(IF(...)) column per importable export column (~1,889). Emit a
   checksum comment in the header; deploy.py refuses to apply if the file has
   been hand-edited.

4. generated/audit_views.sql — five views:
   v_audit_missing_fields      Q1, must return zero rows
   v_audit_domain_coverage     Q2, populated/abstained/human %, by domain
   v_audit_hallucination       Q3, AI_DIRECT + non-null + empty source_event_ids
   v_audit_low_utd             Q4, HIGH-difficulty fields below expected_utd_floor
   v_audit_branching_violation Q5, non-null value on an unsatisfied field

bq/deploy.py: idempotent apply, `--dry-run` printing a schema diff, refuses to
run if sha256(instrument.csv) != dict_version.txt, `--dataset` required with no
default (never let a stray run hit production).

DO NOT create a wide physical table. EAV is the write path; the view is the read
path. A 1,891-column table hits schema-mutation friction on every dictionary
change.

ACCEPTANCE: deploy to a scratch dataset; all five audit views execute; after
loading the synthetic maximal case (D12) v_audit_missing_fields returns zero rows.

=== D08 ===
D8 — Event-stream ingestion and ensemble voting
Implement `ingest/loader.py` and `ingest/ensemble.py`.

loader.py: validate raw LLM output against generated/models.py, then write
fact_event / fact_interval / fact_utterance / fact_sensor_interval.
- Reject any event whose evidence[] is empty (Constitution rule).
- Reject any event whose type is outside the closed vocabulary.
- Assign deterministic event_ids: sha1(case_id|type|round(t_start_s,1)|detector)
  truncated to 12 hex — so re-ingesting the same run is idempotent.
- Compute t_start_wallclock from the clock anchor.
- Append-only. Merges set superseded_by; never DELETE.

ensemble.py: merge k parallel runs of P1/P2 into one stream.
- Categorical attributes → majority vote; 3/3 → confidence 0.95+,
  2/3 → 0.75 and flag, 1/1/1 → abstain and route to human.
- Timestamps → median; ensemble_spread_s = max-min; spread > 3.0 s forces
  routed_to_human.
- Event existence → 3/3 accept; 2/3 accept + flag; 1/3 drop but write to a
  `near_miss` table for eval (do not discard silently — near-misses are the
  training signal for threshold tuning).
- Matching across runs: same type AND |Δt| ≤ (sum of the two t_precision_s).
  Greedy nearest-neighbour, each event matched at most once.
- Record ensemble_votes, ensemble_k, ensemble_spread_s on every output event.

ACCEPTANCE: tests/test_ensemble.py — three synthetic runs with a known
disagreement pattern produce the expected votes, spread, and routing decisions.
Re-running loader.py on identical input produces zero new rows.

=== D09 ===
D9 — Confidence router and HITL queue
Implement `router/policy.py` and `router/queue.py`.

policy.py: decide routed_to_human per FieldValue. Rules, read from
config/routing.yaml (not hardcoded):
- confidence < threshold_for(difficulty)  → route
  (LOW 0.80, MEDIUM 0.85, HIGH 0.92 as defaults)
- ensemble_spread_s > 3.0                 → route
- validation_passed == False              → route
- source_class == TEAM                    → always route (until ICC ≥ 0.75)
- abstained == True on a REQUIRED field   → route
- field belongs to a truncated group      → route
- expected_utd_floor set and this case's
  UTD rate for that field is far below it → route (possible hallucination)
Target: ~85% auto-accepted. Emit the realized rate per run into dim_run so
drift is visible.

queue.py: a review work-queue API over fact_redcap_field.
- next_item(reviewer_id) → the highest-value unreviewed field, ordered by
  (REQUIRED desc, difficulty desc, confidence asc)
- Each item carries: field label, AI value + label, confidence, abstain_reason,
  source_event_ids, and a DEEP LINK — video_uri plus t_start_s minus 10 s —
  so the reviewer lands 10 seconds before the event.
- submit(reviewer_id, field, human_value, note) → writes human_value,
  human_verified_at, human_verified_by; recomputes final_value =
  COALESCE(human_value, value).
- Every human correction also writes an exemplar row for retrieval-augmented
  few-shot (the A3 loop): {case_id, event_id, field, ai_value, human_value,
  clip_t0, clip_t1}.
- Idempotent: re-submitting the same field updates, never duplicates.

DO NOT build a UI. This is the API layer only.

ACCEPTANCE: tests/test_router.py asserts routing decisions for each rule and
that submit() is idempotent. A synthetic case with all-high confidence yields
≥85% auto-accepted.

=== D10 ===
D10 — Metrics layer
Implement `metrics/compute.py` → rows in fact_metric. Read AGENTS.md.

These are COMPUTED from fact_interval / fact_event, never extracted by a model,
and never re-derived by the TEAM prompt. Definitions are versioned; every row
carries metric_definition_version.

Implement:
- chest_compression_fraction — (total_case_time − Σ CCI duration) / total_case_time,
  where total_case_time spans first compression to last compression or
  termination. Document the denominator choice in the docstring; it is the most
  argued-about definition in resuscitation QI.
- ccf_by_2min_epoch — array, for run charts
- n_cci_over_10s, longest_cci_s, median_cci_s
- peri_shock_pause_pre_s / _post_s per shock, plus medians
- n_pre_charged_shocks (charge started before the CCI began) / n_shocks
- arrival_to_pads_s, arrival_to_first_epi_s, shockable_to_first_shock_s
- n_airway_attempts, first_pass_success, cci_seconds_attributable_to_airway
- mccd_deployment_noflow_s
- closed_loop_completion_rate, n_unacknowledged_directives (from fact_utterance)
- Also emit the two REDCap calc fields (dur_mccd_app_ed_secs_v2,
  duration_ventilator_place_v2) into fact_metric — NOT into the REDCap payload.

Every metric records numerator and denominator, not just the ratio, so an
analyst can re-aggregate across cases correctly.
Return None (not 0) when the denominator is zero or the inputs are incomplete;
write a fact_metric row with value NULL and a reason.

ACCEPTANCE: tests/test_metrics.py — a hand-computed 10-minute case with three
known interruptions yields the expected CCF to 3 decimals. A case with zero
shocks yields NULL, not 0, for peri-shock metrics.

=== D11 ===
D11 — REDCap client
Implement `redcap/client.py` and `redcap/assemble.py`.

assemble.py — assemble_submission(case_id, run_id) → (payload, quarantine[]):
- Read fact_redcap_field. Skip source_class REDCAP_CALC entirely.
- branching_satisfied == False → send "" (explicit blank, so REDCap clears it).
- validation_passed == False → quarantine, do not send.
- routed_to_human and not human_verified → quarantine, do not send.
- Otherwise send final_value, or "" when null.
- CHECKBOX COMPLETENESS: after the main loop, for every checkbox field in
  FIELDS, setdefault every one of its export columns to "0". Missing columns
  leave stale values set on re-import.
- payload["video_review_complete"] = "2" if every routed field is verified,
  else "1".
- Assert every key is in IMPORTABLE_COLUMNS; raise on any stray key.

client.py:
- POST with content=record, format=json, type=flat,
  overwriteBehavior=overwrite (so blanks actually clear),
  returnContent=count, returnFormat=json.
- Retry with exponential backoff + jitter on 5xx and connection errors only.
  NEVER retry a 400 — REDCap returns field-level validation errors in the body;
  parse them, attach to quarantine_reasons, and fail loudly.
- Idempotency keyed on (case_id, run_id): re-running is safe and updates.
- Log the full request and response into redcap_submission, with the token
  redacted.
- Token from env / Secret Manager only. A literal token anywhere in the repo is
  a build failure — add a pre-commit grep for it.

ACCEPTANCE: tests/test_assemble.py uses a mocked transport and asserts: calc
fields absent; every checkbox column present as "1" or "0"; a quarantined field
blocks the whole submission; a 400 is not retried; re-submission is idempotent.

=== D12 ===
D12 — Fixtures and coverage tests
Implement `fixtures/synthetic_maximal.py` and `tests/test_coverage.py`.
This is the highest-value test in the project — it is the proof that all 1,891
columns are reachable.

synthetic_maximal.py — build_event_stream() constructs a case that:
- exercises every repeating group at its cap: 30 CCIs, 30 shocks, 8 airway
  attempts, 20 ROSC episodes, 5 ventilation delays
- cycles CCI reason codes so every one of the 21 (20 on index 1) is selected at
  least once across the 30 interruptions
- selects every mccd_adjust_reason code, every pulse location, every airway
  confirmation method, every access type
- satisfies every branching condition in the dictionary (so no field is skipped
  for being hidden)
- emits every one of the 40 event types at least once
- has empty coverage_notes (so gate_3way returns 2, never 3)
Generate indices and vocabularies FROM generated/redcap_fields.py — do not
hand-type 30 of anything.

Also build fixtures/golden_case_01.py: a realistic 22-minute case with known
ground truth, including deliberate imperfections (one occlusion window, one
low-confidence a-line reading, one truncation-free 12-CCI stream) for
regression testing the router and validators.

tests/test_coverage.py:
  test_synthetic_maximal_emits_every_column   — set equality, prints missing and
                                                phantom separately, first 25 each
  test_no_unmapped_source_class
  test_every_ai_field_names_an_owning_event_type
  test_every_owning_event_type_has_an_anchor_card
  test_yesno_fields_are_one_zero
  test_checkbox_writes_both_states             — every code "1" or "0", none blank
  test_calc_fields_never_in_payload
  test_suppressed_codes_forced_zero            — mccd_obstacles___1 / ___2
  test_operator_fields_always_null             — all 8, on the maximal case
  test_review_trigger_always_null
  test_truncation_sets_human_review            — 35 CCIs → 30 emitted, note
                                                 written, group flagged
  test_coverage_degraded_yields_utd_not_no     — the asymmetry in AGENTS.md §5

ACCEPTANCE: all green. The first test's failure message must be immediately
actionable — a sorted list of unmapped export columns, not a bare assert.

=== D13 ===
D13 — CI and round-trip
Implement `.github/workflows/ci.yml` and `tests/test_roundtrip.py`.

CI (on every PR):
1. scripts/hash_dict.sh; fail if dict_version.txt is stale
2. codegen; fail if generated/coverage_manifest.json differs from the committed
   copy WITHOUT a corresponding change to dictionary/ or mapping/ (this makes
   every schema change visible in review)
3. ruff, mypy --strict
4. pytest (unit only; integration and network markers deselected)
5. determinism check: run codegen twice, assert byte-identical output
6. secret scan: fail on anything resembling a REDCap token
7. publish coverage_manifest.json as a build artifact and post the
   by_source_class / by_difficulty diff as a PR comment

tests/test_roundtrip.py — marked `integration` and `network`, guarded by
RESUS_ALLOW_NETWORK=1 AND a scratch-project assertion so it can never touch
production:
1. exportFieldNames API → assert set equality with EXPORT_COLUMNS. Report
   missing and phantom separately. THIS IS THE DEFINITIVE COVERAGE PROOF;
   everything else is inference.
2. Reduce the synthetic maximal case → assemble → POST to scratch →
   assert count_imported == 1.
3. Export the record back → assert byte-equality on every non-calc,
   non-blank field. On mismatch print field / sent / received.
4. Assert every checkbox column round-trips as exactly "1" or "0", never blank.
5. Assert datetimes round-trip as "%Y-%m-%d %H:%M:%S". If the instance rejects
   it, FAIL LOUDLY with the server error — do not silently retry with M-D-Y.
6. Re-POST with one checkbox cleared; assert it exports as "0", not stale "1".

Also write docs/RUNBOOK.md: how to add a REDCap variable end-to-end (edit
dictionary → rehash → fill registry → rebuild → extend anchor card → rerun
coverage test → deploy BQ → round-trip), and what each audit view means when it
returns rows.

ACCEPTANCE: CI green on a clean checkout. Round-trip passes against a scratch
project. A deliberate one-field registry deletion turns CI red with a clear
message.
