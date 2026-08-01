Phase: 1 (schema spine)
Last completed: A03
Next task: A03b
Verified gates: D14 tests (test_coverage.py) checked: Contract reads match registry perfectly, no integer codes exposed to model, malformed gates correctly trapped, and interval types resolved accurately. Boolean parsing from PyYAML in vocabularies corrected to 'yes'/'no'.
Environment: Python 3.11, TBD the rest

Known-broken/deferred:
- "check_anchors() proves structural coverage only. It cannot validate clinical accuracy. Anchor card content requires human clinical review before the first production run — see docs/CLINICAL_REVIEW_QUEUE.md."
- "dictionary/DDL_SPEC.md not yet staged — blocks D07 only. Human to paste from _inbox/40_ddl_spec.md."
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

Session summary: Implemented A03 (Batch 1 anchor cards). Wrote the 6 highest-column-count anchor cards (`compression_interruption`, `mccd_adjustment`, `vitals_reading`, `defibrillation_shock`, `airway_attempt`, `rosc_detected`) covering all contract attributes in code order. Upgraded `check_anchors()` to require required_attributes mappings and enforce rules, adding tests in `tests/test_prompts_registry.py`. Replaced inline TODOs with one-line CLINICAL_REVIEW pointers and consolidated real clinical review questions into `docs/CLINICAL_REVIEW_QUEUE.md`. Verified zero integer choice codes and 0 uncovered attributes across all 6 cards.

<!-- Updated by the agent as the LAST action of every session. If stale, the next session will redo or skip work. -->
