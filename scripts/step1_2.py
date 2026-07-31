import os, glob, yaml, re

d_tasks_yaml = """
D00:
  title: "Scaffold verification and completion"
  creates: [README.md, codegen/known_bugs.py]
  modify: [pyproject.toml, .gitignore]
  reads: ["*"]
  depends: []
  gate: "check_invariants.sh exits 0; build.sh fails ONLY at codegen; zero overwrites"

D01:
  title: "REDCap dictionary parser"
  creates: [codegen/redcap_dict_to_code.py, tests/test_parser.py]
  modify: []
  reads: [dictionary/instrument.csv]
  depends: [D00]
  gate: "parser prints exactly `909 1889`; sanitize('-1') → '_1'; yesno asserted 1/0"

D02:
  title: "Branching logic transpiler"
  creates: [codegen/branching.py, codegen/emit_branching.py, tests/test_branching.py]
  modify: []
  reads: [dictionary/instrument.csv, codegen/known_bugs.py]
  depends: [D01]
  gate: "every branching expr in the dictionary compiles; eval-injection test raises"

D03:
  title: "Registry validator + coverage manifest"
  creates: [codegen/emit_manifest.py, mapping/registry_skeleton.yaml, tests/test_manifest.py]
  modify: []
  reads: [dictionary/instrument.csv, mapping/registry.yaml]
  depends: [D02]
  gate: "manifest reports 911 vars / 1891 cols / unmapped []; 3 corrupted-registry cases fail with line numbers"

D04:
  title: "Emit typed Python artifacts"
  creates: [codegen/emit_python.py, mapping/event_types.yaml, tests/test_emit_python.py]
  modify: []
  reads: [dictionary/instrument.csv, mapping/registry.yaml]
  depends: [D03]
  gate: "len(EXPORT_COLUMNS) == 1891; rebuild byte-identical; mypy --strict clean on generated/"

D14:
  title: "Extraction contract — the prompt↔reducer interface"
  creates: [codegen/emit_contract.py, tests/test_contract.py]
  modify: []
  reads: [mapping/registry.yaml, generated/redcap_fields.py]
  depends: [D04]
  gate: "every registry emit: key present exactly once; zero orphan attributes; no integer enum codes exposed"

D05:
  title: "Reducer engine — registry interpreter"
  creates: [reducer/engine.py, tests/test_reducer_primitives.py]
  modify: []
  reads: [generated/redcap_fields.py, generated/extraction_contract.json,
          generated/branching_compiled.py, mapping/registry.yaml, "fixtures/real/*.json"]
  depends: [D14, A04]
  gate: "engine.py <500 lines; grep for field-name literals returns nothing; all 5 real fixtures reduce without exception"
  gate_note: "May tighten after Phase 3 once real streams are observed."

D06:
  title: "Transforms and cross-field validators"
  creates: [reducer/transforms.py, reducer/validators.py, config/validators.yaml, tests/test_validators.py]
  modify: []
  reads: [generated/redcap_fields.py]
  depends: [D05]
  gate: "12 validators, each severity-tested; datetime emits %Y-%m-%d %H:%M:%S; no clamp/round on failure paths"

D07a:
  title: "BigQuery infrastructure (Terraform)"
  creates: [infra/bigquery.tf, infra/iam.tf, infra/README.md]
  modify: []
  reads: []
  depends: [D00]
  gate: "terraform plan clean on dev; sa-analyst CANNOT query fact_utterance (show the permission error)"

D07:
  title: "BigQuery DDL, seed, views, deploy"
  creates: [codegen/emit_sql.py, bq/deploy.py, tests/test_emit_sql.py]
  modify: []
  reads: [dictionary/DDL_SPEC.md, generated/redcap_fields.py]
  depends: [D04, D07a]
  gate: "13 tables + v_redcap_wide + v_exemplar_store + 5 audit views deploy clean to scratch"

D08:
  title: "Event ingestion and ensemble voting"
  creates: [ingest/loader.py, ingest/ensemble.py, tests/test_ensemble.py]
  modify: []
  reads: [generated/models.py, "fixtures/real/*.json"]
  depends: [D07]
  gate: "re-ingesting identical input yields zero new rows; 3-run disagreement produces expected votes/spread/routing"

D09:
  title: "Confidence router and HITL queue"
  creates: [router/policy.py, router/queue.py, config/routing.yaml, tests/test_router.py]
  modify: []
  reads: [generated/redcap_fields.py]
  depends: [D08]
  gate: "submit() idempotent; all-high-confidence synthetic case yields ≥85% auto-accept"
  gate_note: "Thresholds tune after observing the real t_precision_s distribution."

D10:
  title: "Derived QI metrics"
  creates: [metrics/compute.py, tests/test_metrics.py]
  modify: []
  reads: [generated/redcap_fields.py]
  depends: [D08]
  gate: "hand-computed 10-min / 3-interruption case matches CCF to 3dp; zero-shock case yields NULL not 0"
  gate_note: "CCF denominator convention is OPEN — see OPEN_QUESTIONS."

D11:
  title: "REDCap client and payload assembly"
  creates: [redcap/client.py, redcap/assemble.py, tests/test_assemble.py]
  modify: []
  reads: [generated/redcap_fields.py]
  depends: [D06]
  gate: "calc fields absent; every checkbox column present as 1 or 0; 400 not retried; re-submission idempotent"

D12:
  title: "Synthetic maximal fixture and coverage tests"
  creates: [fixtures/synthetic_maximal.py, fixtures/golden_case_01.py, tests/test_coverage.py]
  modify: []
  reads: [generated/redcap_fields.py, generated/extraction_contract.json]
  depends: [D05, D06]
  gate: "MILESTONE — every column in EXPORT_COLUMNS emitted (1891); failure message lists missing/phantom, first 25 each"

D13:
  title: "CI and REDCap round-trip"
  creates: [.github/workflows/ci.yml, tests/test_roundtrip.py, docs/RUNBOOK.md]
  modify: []
  reads: ["*"]
  depends: [D11, D12]
  gate: "CI green on clean checkout; exportFieldNames set-equals EXPORT_COLUMNS; round-trip byte-equal on scratch"
"""

# Append to specs.yaml if not already there
with open('docs/tasks/specs.yaml', 'r') as f:
    existing_specs = f.read()

if "D01:" not in existing_specs:
    with open('docs/tasks/specs.yaml', 'a') as f:
        f.write("\n" + d_tasks_yaml)

with open('docs/tasks/specs.yaml', 'r') as f:
    specs = yaml.safe_load(f)

# Create D07a.md
if not os.path.exists('docs/tasks/D07a.md'):
    with open('docs/tasks/_TEMPLATE.md', 'r') as f:
        template = f.read()
    template = template.replace("<<< the full {{TASK_ID}} prompt text goes here, verbatim >>>", "<!-- TODO: task body pending -->")
    template = template.replace("{{TASK_ID}}", "D07a")
    template = template.replace("{{TASK_TITLE}}", "BigQuery infrastructure (Terraform)")
    with open('docs/tasks/D07a.md', 'w') as f:
        f.write(template)

open_questions = []
q_idx = 29
def add_q(task, slot):
    global q_idx
    q = f"Q{q_idx:03d}"
    open_questions.append(f"**{q} ({task})**: What is the correct value for '{slot}'? (specs.yaml does not determine this).")
    q_idx += 1
    return f"TBD (see {q})"

for filepath in glob.glob('docs/tasks/D*.md'):
    task = os.path.basename(filepath).replace('.md', '')
    if task not in specs or task == 'D00':
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

    # 3. Acceptance
    gate = spec.get('gate')
    gate_note = spec.get('gate_note')
    if not gate:
        if task in ['D05', 'D09', 'D10', 'D12', 'D13', 'A06']:
            gate_str = add_q(task, 'Acceptance Gate (Unknowable until dependencies exist)')
        else:
            gate_str = add_q(task, 'Acceptance Gate')
    else:
        gate_str = gate
        
    acc_block = f"- [ ] {gate_str}\n- [ ] `bash scripts/check_invariants.sh` exits 0"
    if gate_note:
        acc_block += f"\n*Note: {gate_note}*"
        
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

if open_questions:
    with open('docs/OPEN_QUESTIONS.md', 'a') as f:
        f.write("\n## Unresolved TBDs from D-Task Files\n")
        f.write("\n".join(open_questions) + "\n")
