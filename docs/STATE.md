Phase: 1 (schema spine)
Last completed: A05
Next task: D05
Verified gates: A05 tests (test_prompt_builder.py): fail-safe anchor slicing across all paths (None, {}, quiet/degraded/malformed windows -> all 39 cards), BuiltPrompt dataclass return type and metadata, 100x prompt_hash determinism on identical inputs, Vertex AI structured output JSON schema flattening (0 $ref and 0 $defs), assert_no_field_names on assembled prompts, and idempotent snapshot writing. A04 tests: byte-identical round-trip reconstruction of P1 and P2 templates from tests/fixtures/passes_v2.0_source.md, bidirectional placeholder validation (undeclared and unused placeholders raise ValueError), assert_no_field_names on both templates, and prompt_set_sha(strict=True) raising with exactly 4 missing files (P3, P4a, P4b, P5). check_anchors(fail_on_gap=True) permanently enabled in CI and passes cleanly across all 39 anchor cards (6 from A03 + 33 from A03b). D14 tests (test_coverage.py) checked: Contract reads match registry perfectly, no integer codes exposed to model, malformed gates correctly trapped, and interval types resolved accurately. Boolean parsing from PyYAML in vocabularies corrected to 'yes'/'no'.
Environment: Python 3.11, TBD the rest

Known-broken/deferred:
- "check_anchors() proves structural coverage only. It cannot validate clinical accuracy. Anchor card content requires human clinical review before the first production run — see docs/CLINICAL_REVIEW_QUEUE.md."
- "D05 must implement drug->drug_class classification and rhythm->rhythm_shockable derivation in the reducer. Both are where filters the registry depends on, excluded from the model contract because they are computable from drug and rhythm."
- "D05 drug classification: drug=other + drug_name_text -> drug_class requires a synonym table. Thrombolytics: alteplase, tPA, TNK, tenecteplase, reteplase, retavase, activase, cathflo. Case-insensitive, substring match. Unmatched `other` drugs get drug_class=null and do not populate thrombolytic fields."
- "dictionary/DDL_SPEC.md not yet staged — blocks D07 only. Content must come from human user (was never staged in _inbox/)."
- "_inbox/ is scheduled for deletion after D13 (retaining only referenced task/contract docs until then)."
- "scripts/make_task.py UNVERIFIED — --dry-run produced no output, which does not distinguish 'works' from 'stub no-op'. Off the critical path; task bodies come from _inbox/. Verify before first real use."
- "docs/tasks/A02.md is only 7 lines. Before running A02, confirm its Task body names _inbox/20_constitution.md as the source. If it does not, the agent will write a constitution from scratch instead of placing the staged one."
- "pip index override in place (Q-007). Venv-scoped, repo-local. Must be resolved before production deployment."
- "Anchor cards required: 42, not the ~24 originally estimated. A03 covers the 6 highest-column-count types; A03b covers the remaining 36. Re-estimate A03b accordingly."

- "Do not create prompts/ content before D14 and A01."
- "Do not run scripts/bootstrap.sh again unless the venv is deleted."
- "Stub modules MUST have a `if __name__ == '__main__': main()` guard that raises. A stub without one exits 0 and is indistinguishable from a working module — this defeats every build gate that depends on 'fails at the expected step'."
- "bootstrap.sh must FAIL on incomplete install, never degrade. Fourth instance of the silent-degradation pattern — check every new script for it before committing."
- "Unknown fields referenced in branching logic evaluate to False (matching REDCap), rather than crashing. DO NOT special-case or force a build failure for them."
- "D07a (BigQuery infrastructure) has no code dependencies and should be started in parallel — the VPC-SC perimeter change needs an Org Policy Admin, who is never available the week you need them."
- "Interval types (e.g. cci, rosc, vent_delay) must not leak into event_types. event_types_from_rules and event_types_from_hints are kept distinct in manifest derivation. anchor_cards_required is 39."
- "NO non-existent files should be skipped in prompt_set_sha(). A partial hash is a lie about reproducibility. Raise on missing files."

Session summary: Completed A05 by implementing `prompts/builder.py` and test suite `tests/test_prompt_builder.py`. Implemented fail-safe recall-biased anchor card selector (`select_anchors`) defaulting to all 39 cards when sensor data is `None`, empty `{}`/quiet/degraded/malformed, or on any error. Implemented `to_vertex_schema()` to dereference Pydantic JSON schemas inline for Vertex AI structured outputs (0 `$ref`, 0 `$defs`). Implemented `BuiltPrompt` dataclass returning full reproducibility metadata (`constitution_hash`, `anchor_library_version`, `template_hash`, `prompt_hash`, `selected_anchors`, `selection_reasons`, `estimated_text_input_tokens`). Implemented `build_p1` and `build_p2` (deferring `build_p3`, `build_p4a`, `build_p4b`, `build_p5` to A06 per docstring). Verified `assert_no_field_names()` catches column name leakage on assembled prompts and fixed 8 anchor cards that contained REDCap column literals in comments. Added synthetic adversarial sensor fixtures (`quiet_window.json`, `dense_window.json`, `degraded_window.json`, `malformed.json`). Verified 100x prompt hash determinism. All 50 unit tests and invariants I1–I6 pass cleanly. Set Next-task to D05.

<!-- Updated by the agent as the LAST action of every session. If stale, the next session will redo or skip work. -->
