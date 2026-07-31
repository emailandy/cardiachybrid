# docs/tasks/{{TASK_ID}}.md — {{TASK_TITLE}}

## Preconditions — verify before starting
- [ ] `docs/STATE.md` shows {{PREVIOUS_TASKS}} complete
- [ ] `{{REQUIRED_FILES}}` exist
- [ ] `bash scripts/check_invariants.sh` passes
- [ ] {{ADDITIONAL_PRECONDITIONS}}

If any precondition fails: STOP, report which one, do not proceed.

## Scope
CREATE:  {{FILES_TO_CREATE}}
MODIFY:  {{FILES_TO_MODIFY}}
READ:    {{FILES_TO_READ}}

Touching any file outside this list requires stopping and asking.

## Task
<<< the full {{TASK_ID}} prompt text goes here, verbatim >>>

## Acceptance — all must pass
- [ ] `pytest {{TEST_FILES}}` green
- [ ] `wc -l {{MAIN_FILE}}` < {{LINE_LIMIT}}
- [ ] `grep -nE '"[a-z_]+(_v2)?"' {{MAIN_FILE}}` returns nothing
- [ ] `mypy --strict {{MODULE_DIR}}/` clean
- [ ] `bash scripts/check_invariants.sh` passes
- [ ] {{ADDITIONAL_ACCEPTANCE_CRITERIA}}

## Self-review before you report done
Answer each in writing:
1. Which of the six invariants does this code touch? How does it uphold each?
2. {{TASK_SPECIFIC_QUESTION_1}}
3. {{TASK_SPECIFIC_QUESTION_2}}
4. Name one input that would break this code. Is it tested?

## On completion
1. Update `docs/STATE.md` (position, gates, session summary, do-not-repeat)
2. Append any judgment call to `docs/DECISIONS.md`
3. Append any unresolved ambiguity to `docs/OPEN_QUESTIONS.md`
4. Commit with message `{{TASK_ID}}: {{COMMIT_MESSAGE}}`
