Phase: 1 (schema spine)
Last completed: D00
Next task: D01
Verified gates: D00 gate checked
Environment: Python 3.11, TBD the rest

Known-broken/deferred:
- "prompts/ not yet created — built by A01"
- "dictionary/DDL_SPEC.md not yet staged — blocks D07 only. Human to paste from _inbox/40_ddl_spec.md."
- "scripts/make_task.py UNVERIFIED — --dry-run produced no output, which does not distinguish 'works' from 'stub no-op'. Off the critical path; task bodies come from _inbox/. Verify before first real use."
- "docs/tasks/A02.md is only 7 lines. Before running A02, confirm its Task body names _inbox/20_constitution.md as the source. If it does not, the agent will write a constitution from scratch instead of placing the staged one."

Do not repeat:
- "Do not create prompts/ content before D14 and A01."
- "Do not run scripts/bootstrap.sh again unless the venv is deleted."

Session summary: verify scaffold, add build.sh, known_bugs, README

<!-- Updated by the agent as the LAST action of every session. If stale, the next session will redo or skip work. -->
