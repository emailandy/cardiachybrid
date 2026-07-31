# AGENTS.md — resus_qc

## READ THIS FIRST, EVERY SESSION
1. Read this file completely.
2. Read `docs/STATE.md` for where the build actually is.
3. Read `docs/tasks/<TASK_ID>.md` for the task you were given.
4. Run `bash scripts/check_invariants.sh`. If it fails, STOP and report —
   do not begin new work on a broken tree.
5. Confirm your understanding in 3 bullets before writing code.

## HOW TO WORK
- Run inside the venv: `source .venv/bin/activate`. If `scripts/check_invariants.sh`
  reports `⚠ cannot run`, the environment is incomplete — run `scripts/bootstrap.sh`.
  A check that cannot run is NOT a passing check.
- One task per session. Do not start the next one, even if it seems trivial.
- Plan before code. State the files you will touch and why. Wait if the plan
  changes materially mid-implementation.
- Small commits with real messages. `git commit -m "D5: gate_3way coverage
  asymmetry"` not `"updates"`.
- Run `bash scripts/check_invariants.sh` before every commit.
- Update `docs/STATE.md` as your LAST action. Never skip this.

## WHEN YOU ARE UNSURE — the escalation ladder
1. Re-read the dictionary / registry. It is the authority.
2. Check `docs/DECISIONS.md` — it may already be answered.
3. If still unresolved: STOP. Write the question into `docs/OPEN_QUESTIONS.md`
   with the file, line, and both candidate answers. Continue with other work
   or end the session.

DO NOT: guess a field name, invent a choice code, infer a vocabulary value,
or "reasonably assume" a branching rule. In this codebase a wrong guess does
not crash — it silently writes bad data into a clinical research database.

## THE SIX INVARIANTS (mechanically enforced by scripts/check_invariants.sh)
I1  `dictionary/instrument.csv` is the only hand-maintained schema artifact.
I2  No REDCap field name as a string literal outside dictionary/ and mapping/.
I3  `yesno` fields are 1/0. Never 1/2.
I4  Checkbox columns are `field___{sanitized_code}`; ALWAYS write both 1 and 0.
I5  Absence of evidence ≠ evidence of absence. Degraded coverage → UTD, not No.
I6  Never clamp, round, or coerce an out-of-range value. Fail and route.

Each has a check in scripts/check_invariants.sh. If you find yourself wanting
to disable one, that is the signal to stop and ask.

## ANTI-PATTERNS — you will be tempted by all five
| Tempting | Why it's wrong | Instead |
|---|---|---|
| `if field == "num_cci_v2"` | violates I2; breaks on dictionary change | read from FIELDS / registry |
| loop over selected checkbox codes | stale boxes never clear on re-import | loop over `spec.choices` |
| `f"reason_cci_{i}_v2"` | 7 CCI sub-fields have no `_v2` | use `spec.export_columns` |
| `return 2 if not events` | asserts False where UTD is correct | `gate_3way` with coverage |
| trimming `expected` to pass a test | destroys the only coverage proof | fix the mapping |

## SCOPE DISCIPLINE
If a task requires changing a file outside its declared scope, STOP and ask.
Scope creep in this codebase means an untested path into a research database.
