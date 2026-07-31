Phase: 1 (schema spine)
Last completed: D04
Next task: D05
Verified gates: D04 gate checked: generated/redcap_fields.py and models.py built deterministically, 4 counts verified (1891/1889/2/1891), per-field vocabularies correct, and no codegen imports in generated/.
Environment: Python 3.11, TBD the rest

Known-broken/deferred:
- "prompts/ not yet created — built by A01"
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

Session summary: Implemented codegen/emit_python.py to emit generated/redcap_fields.py (with typed FieldSpec) and generated/models.py. Fixed redcap_feeding count to include nested event_types (35 types), resulting in 42 anchor cards required. Removed codegen imports from generated/. Determinism check expanded.

<!-- Updated by the agent as the LAST action of every session. If stale, the next session will redo or skip work. -->
