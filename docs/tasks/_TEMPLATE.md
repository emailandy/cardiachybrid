# docs/tasks/{{TASK_ID}}.md — {{TASK_TITLE}}

## Preconditions — verify before starting
- [ ] `docs/STATE.md` shows {{PREVIOUS_TASKS}} complete
- [ ] `{{REQUIRED_FILES}}` exist
- [ ] `bash scripts/check_invariants.sh` passes
- [ ] {{ADDITIONAL_PRECONDITIONS}}

If any precondition fails: STOP, report which one, do not proceed.

## Scope
CREATE:
MODIFY:
READ:

Touching any file outside this list requires stopping and asking.

## Task
<<< the full {{TASK_ID}} prompt text goes here, verbatim >>>

## Acceptance — all must pass
- [ ] `bash scripts/check_invariants.sh` exits 0

## Self-review before you report done
Answer each in writing:
1. Which of the six invariants does this code touch? How does it uphold each?
2.
3.
4. Name one input that would break this code. Is it tested?

## On completion
1. Update `docs/STATE.md` (position, gates, session summary, do-not-repeat)
2. Append any judgment call to `docs/DECISIONS.md`
3. Append any unresolved ambiguity to `docs/OPEN_QUESTIONS.md`
4. Commit with message `{{TASK_ID}}: {{COMMIT_MESSAGE}}`
