import os
import re
import yaml
import glob

# 1. Update AGENTS.md
agents_file = "AGENTS.md"
with open(agents_file, "r") as f:
    agents_content = f.read()
if "scripts/bootstrap.sh" not in agents_content:
    agents_content = agents_content.replace(
        "## HOW TO WORK",
        "## HOW TO WORK\n- Run inside the venv: `source .venv/bin/activate`. If `scripts/check_invariants.sh`\n  reports `⚠ cannot run`, the environment is incomplete — run `scripts/bootstrap.sh`.\n  A check that cannot run is NOT a passing check."
    )
    with open(agents_file, "w") as f:
        f.write(agents_content)

# 2. Update all task files preconditions
for path in glob.glob("docs/tasks/*.md"):
    with open(path, "r") as f:
        content = f.read()
    if "check_invariants.sh passes" in content:
        content = content.replace("check_invariants.sh passes", "check_invariants.sh exits 0")
        with open(path, "w") as f:
            f.write(content)

# 3. Append to specs.yaml
specs_file = "docs/tasks/specs.yaml"
append_data = """
A01:
  title: "prompts/ scaffold, VERSIONS.yaml, registry.py"
  creates: [prompts/VERSIONS.yaml, prompts/registry.py, prompts/anchors/_SCHEMA.yaml]
  depends: [D14]
  gate: "python3 -m prompts.registry prompt-set-sha returns a stable 16-char hash"

A02:
  title: "Constitution v2.0 + fragments"
  creates: [prompts/system/constitution.v2.0.md, prompts/fragments/coverage_rules.md,
            prompts/fragments/timestamp_calibration.md, prompts/fragments/failure_modes.md]
  depends: [A01]
  gate: "constitution references each fragment via {{fragment:name}}; no duplicated text"

A03:
  title: "Anchor cards — batch 1 (6 highest-column-count event types)"
  creates: [prompts/anchors/mccd_adjustment.yaml, prompts/anchors/vitals_reading.yaml,
            prompts/anchors/compression_interruption.yaml,
            prompts/anchors/defibrillation_shock.yaml,
            prompts/anchors/airway_attempt.yaml, prompts/anchors/rosc_detected.yaml]
  depends: [D14, A01]
  gate: "python3 -m prompts.registry check-anchors --types <the six> → 0 uncovered"

A03b:
  title: "Anchor cards — batch 2 (remaining 18)"
  creates: [prompts/anchors/*.yaml]
  depends: [A03]
  gate: "python3 -m prompts.registry check-anchors --fail-on-gap → 0 gaps, all types"

A04:
  title: "P1 harvest + P2 verify templates"
  creates: [prompts/passes/p1_harvest.v2.0.md, prompts/passes/p2_verify.v2.0.md]
  depends: [A02, A03]
  gate: "templates contain no EXPORT_COLUMNS string; contract slice markers present"

A05:
  title: "prompts/builder.py"
  creates: [prompts/builder.py, tests/test_prompt_builder.py]
  depends: [A04]
  gate: "determinism 100x identical hash; assert_no_field_names passes on all passes"

A06:
  title: "P3, P4a, P4b, P5 templates"
  creates: [prompts/passes/p3_adjudicate.v2.0.md, prompts/passes/p4a_team_items.v2.0.md,
            prompts/passes/p4b_team_global.v2.0.md, prompts/passes/p5_notes.v2.0.md,
            prompts/calibration/team_anchor_{low,mid,high}.yaml]
  depends: [A05, D10]
  gate: "P4a renders NULL metrics as NULL not 0; P5 emits truncation paragraph on 35-CCI fixture"

D07a:
  title: "Infrastructure Setup (VPC-SC perimeter change)"
  creates: []
  depends: []
  gate: "Org Policy Admin approves perimeter change"
"""
with open(specs_file, "r") as f:
    existing_specs = f.read()

if "A01:" not in existing_specs:
    with open(specs_file, "a") as f:
        f.write(append_data)

# 4. Sweep TBDs against docs/tasks/A*.md and create A03b.md
with open(specs_file, "r") as f:
    specs = yaml.safe_load(f)

for path in glob.glob("docs/tasks/A*.md"):
    if path == "docs/tasks/A03b.md":
        continue
    task_id = os.path.basename(path).replace(".md", "")
    with open(path, "r") as f:
        content = f.read()
    
    # Check if we need to split A03
    if task_id == "A03" and not os.path.exists("docs/tasks/A03b.md"):
        with open("docs/tasks/_TEMPLATE.md", "r") as f:
            template = f.read()
        a03b_content = template.replace("TASK_ID", "A03b")
        with open("docs/tasks/A03b.md", "w") as f:
            f.write(a03b_content)
        print("Created A03b.md")

    if task_id not in specs:
        continue
        
    spec = specs[task_id]
    depends = spec.get("depends", [])
    creates = spec.get("creates", [])
    gate = spec.get("gate", "TBD")
    
    # 1. Preconditions
    precond = "\n".join([f"- [ ] STATE.md shows {d} complete" for d in depends])
    if not precond: precond = "- [ ] No dependencies"
    content = re.sub(r"## Preconditions\n(?:- \[ \] TBD\n)?", f"## Preconditions\n{precond}\n", content)
    
    # 2. Scope
    creates_str = ", ".join(creates) if creates else "None"
    scope_content = f"CREATE: {creates_str}\nMODIFY: TBD\nREAD: TBD"
    content = re.sub(r"## Scope\n(?:.*(?:CREATE|MODIFY|READ).*\n)+", f"## Scope\n{scope_content}\n", content)
    
    # 3. Acceptance
    content = re.sub(r"## Acceptance\n(?:- \[ \] TBD\n)?", f"## Acceptance\n- [ ] {gate}\n", content)
    
    with open(path, "w") as f:
        f.write(content)

# Do the same for A03b since we just created it
if "A03b" in specs:
    path = "docs/tasks/A03b.md"
    with open(path, "r") as f:
        content = f.read()
    spec = specs["A03b"]
    depends = spec.get("depends", [])
    creates = spec.get("creates", [])
    gate = spec.get("gate", "TBD")
    precond = "\n".join([f"- [ ] STATE.md shows {d} complete" for d in depends])
    content = re.sub(r"## Preconditions\n(?:- \[ \] TBD\n)?", f"## Preconditions\n{precond}\n", content)
    creates_str = ", ".join(creates) if creates else "None"
    scope_content = f"CREATE: {creates_str}\nMODIFY: TBD\nREAD: TBD"
    content = re.sub(r"## Scope\n(?:.*(?:CREATE|MODIFY|READ).*\n)+", f"## Scope\n{scope_content}\n", content)
    content = re.sub(r"## Acceptance\n(?:- \[ \] TBD\n)?", f"## Acceptance\n- [ ] {gate}\n", content)
    with open(path, "w") as f:
        f.write(content)

# Update STATE.md
state_file = "docs/STATE.md"
with open(state_file, "r") as f:
    state = f.read()

broken = "dictionary/DDL_SPEC.md not yet staged — blocks D07 only. Human to paste from _inbox/40_ddl_spec.md."
repeat = "Do not run scripts/bootstrap.sh again unless the venv is deleted."

if broken not in state:
    state = state.replace("## Known-broken / Deferred", f"## Known-broken / Deferred\n- {broken}")
if repeat not in state:
    state = state.replace("## Do Not Repeat", f"## Do Not Repeat\n- {repeat}")
with open(state_file, "w") as f:
    f.write(state)

print("Fixes applied successfully")
