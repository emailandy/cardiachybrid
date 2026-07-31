import yaml
import glob
import os
import re

with open('docs/tasks/specs.yaml', 'r') as f:
    specs = yaml.safe_load(f)

# Merge modify/reads
updates = {
    'A01':  {'modify': [], 'reads': ['generated/extraction_contract.json', 'mapping/event_types.yaml']},
    'A02':  {'modify': ['prompts/VERSIONS.yaml'], 'reads': ['_inbox/20_constitution.md']},
    'A03':  {'modify': [], 'reads': ['generated/extraction_contract.json', 'prompts/anchors/_SCHEMA.yaml', 'fixtures/real/*.json']},
    'A03b': {'modify': [], 'reads': ['generated/extraction_contract.json', 'prompts/anchors/_SCHEMA.yaml', 'fixtures/real/*.json']},
    'A04':  {'modify': ['prompts/VERSIONS.yaml'], 'reads': ['generated/extraction_contract.md', 'prompts/anchors/*.yaml', '_inbox/21_passes.md']},
    'A05':  {'modify': [], 'reads': ['prompts/VERSIONS.yaml', 'generated/redcap_fields.py', 'generated/extraction_contract.json']},
    'A06':  {'modify': ['prompts/VERSIONS.yaml'], 'reads': ['_inbox/21_passes.md', 'metrics/compute.py']},
}

for k, v in updates.items():
    if k in specs:
        specs[k]['modify'] = v['modify']
        specs[k]['reads'] = v['reads']

with open('docs/tasks/specs.yaml', 'w') as f:
    yaml.dump(specs, f, sort_keys=False)

open_questions = []
q_idx = 100
def add_q(task, slot):
    global q_idx
    q = f"Q{q_idx:03d}"
    open_questions.append(f"**{q} ({task})**: What is the correct value for '{slot}'? (specs.yaml does not determine this).")
    q_idx += 1
    return f"TBD (see {q})"

for filepath in glob.glob('docs/tasks/A*.md'):
    task = os.path.basename(filepath).replace('.md', '')
    if task not in specs: continue
    
    with open(filepath, 'r') as f:
        content = f.read()

    spec = specs[task]
    
    creates = spec.get('creates', [])
    creates_str = ", ".join(creates) if creates else "None"
    
    if 'modify' in spec:
        modify_str = ", ".join(spec['modify']) if spec['modify'] else "None"
    else:
        modify_str = add_q(task, 'Scope: MODIFY')
        
    if 'reads' in spec:
        read_str = ", ".join(spec['reads']) if spec['reads'] else "None"
    else:
        read_str = add_q(task, 'Scope: READ')
    
    scope_block = f"CREATE:  {creates_str}\nMODIFY:  {modify_str}\nREAD:    {read_str}"
    content = re.sub(
        r"## Scope\n.*?(?=\n## Task)",
        f"## Scope\n{scope_block}\n\nTouching any file outside this list requires stopping and asking.\n",
        content, flags=re.DOTALL
    )

    with open(filepath, 'w') as f:
        f.write(content)
