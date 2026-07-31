import os
import glob
import yaml
import re

def load_specs():
    with open('docs/tasks/specs.yaml', 'r') as f:
        return yaml.safe_load(f)

specs = load_specs()
open_questions = []
q_idx = 1

def add_q(task, slot):
    global q_idx
    q = f"Q{q_idx:03d}"
    open_questions.append(f"**{q} ({task})**: What is the correct value for '{slot}'? (specs.yaml does not determine this).")
    q_idx += 1
    return f"TBD (see {q})"

for filepath in glob.glob('docs/tasks/*.md'):
    if 'TEMPLATE' in filepath or 'specs' in filepath:
        continue
    
    task = os.path.basename(filepath).replace('.md', '')
    if task not in specs:
        # e.g., D00, D07a
        continue
    
    with open(filepath, 'r') as f:
        content = f.read()

    spec = specs[task]
    
    # 1. Preconditions
    depends = spec.get('depends', [])
    precond_lines = [f"- [ ] `docs/STATE.md` shows {d} complete" for d in depends]
    precond_lines.append("- [ ] `bash scripts/check_invariants.sh` exits 0")
    precond_block = "\n".join(precond_lines)
    
    content = re.sub(
        r"## Preconditions — verify before starting\n.*?(?=\n## Scope)",
        f"## Preconditions — verify before starting\n{precond_block}\n\nIf any precondition fails: STOP, report which one, do not proceed.\n",
        content, flags=re.DOTALL
    )

    # 2. Scope
    creates = spec.get('creates', [])
    creates_str = ", ".join(creates) if creates else "None"
    modify_str = add_q(task, 'Scope: MODIFY')
    read_str = add_q(task, 'Scope: READ')
    
    scope_block = f"CREATE:  {creates_str}\nMODIFY:  {modify_str}\nREAD:    {read_str}"
    content = re.sub(
        r"## Scope\n.*?(?=\n## Task)",
        f"## Scope\n{scope_block}\n\nTouching any file outside this list requires stopping and asking.\n",
        content, flags=re.DOTALL
    )

    # 3. Acceptance
    gate = spec.get('gate')
    if not gate:
        if task in ['D05', 'D09', 'D10', 'D12', 'D13', 'A06']:
            gate_str = add_q(task, 'Acceptance Gate (Unknowable until dependencies exist)')
        else:
            gate_str = add_q(task, 'Acceptance Gate')
    else:
        gate_str = gate
        
    acc_block = f"- [ ] {gate_str}\n- [ ] `bash scripts/check_invariants.sh` exits 0"
    content = re.sub(
        r"## Acceptance — all must pass\n.*?(?=\n## Self-review before you report done)",
        f"## Acceptance — all must pass\n{acc_block}\n",
        content, flags=re.DOTALL
    )

    # 4. Self-review
    q2 = add_q(task, 'Self-review Q2')
    q3 = add_q(task, 'Self-review Q3')
    sr_block = f"1. Which of the six invariants does this code touch? How does it uphold each?\n2. {q2}\n3. {q3}\n4. Name one input that would break this code. Is it tested?"
    content = re.sub(
        r"## Self-review before you report done\n.*?(?=\n## On completion)",
        f"## Self-review before you report done\nAnswer each in writing:\n{sr_block}\n",
        content, flags=re.DOTALL
    )

    # 5. On completion
    title = spec.get('title', '')
    msg = f"{task}: {title}" if title else task
    oc_block = f"1. Update `docs/STATE.md` (position, gates, session summary, do-not-repeat)\n2. Append any judgment call to `docs/DECISIONS.md`\n3. Append any unresolved ambiguity to `docs/OPEN_QUESTIONS.md`\n4. Commit with message `{msg}`"
    content = re.sub(
        r"## On completion\n.*",
        f"## On completion\n{oc_block}\n",
        content, flags=re.DOTALL
    )

    with open(filepath, 'w') as f:
        f.write(content)

# Patch _TEMPLATE.md
with open('docs/tasks/_TEMPLATE.md', 'r') as f:
    tpl = f.read()

tpl = re.sub(
    r"CREATE:  \{\{FILES_TO_CREATE\}\}\nMODIFY:  \{\{FILES_TO_MODIFY\}\}\nREAD:    \{\{FILES_TO_READ\}\}",
    "CREATE:\nMODIFY:\nREAD:", tpl
)
tpl = re.sub(
    r"- \[ \] `pytest \{\{TEST_FILES\}\}` green\n- \[ \] `wc -l \{\{MAIN_FILE\}\}` < \{\{LINE_LIMIT\}\}\n- \[ \] `grep -nE '\"\[a-z_\]\+\(_v2\)\?\"' \{\{MAIN_FILE\}\}` returns nothing\n- \[ \] `mypy --strict \{\{MODULE_DIR\}\}/` clean\n- \[ \] `bash scripts/check_invariants.sh` passes\n- \[ \] \{\{ADDITIONAL_ACCEPTANCE_CRITERIA\}\}",
    "- [ ] `bash scripts/check_invariants.sh` exits 0", tpl
)
tpl = re.sub(
    r"2\. \{\{TASK_SPECIFIC_QUESTION_1\}\}\n3\. \{\{TASK_SPECIFIC_QUESTION_2\}\}",
    "2.\n3.", tpl
)
with open('docs/tasks/_TEMPLATE.md', 'w') as f:
    f.write(tpl)

if open_questions:
    os.makedirs('docs', exist_ok=True)
    with open('docs/OPEN_QUESTIONS.md', 'a') as f:
        f.write("\n## Unresolved TBDs from Task Files\n")
        f.write("\n".join(open_questions) + "\n")

print("Branch A logic applied successfully")
