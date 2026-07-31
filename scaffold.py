import os
import re
import shutil

BASE_DIR = "/Users/emailandy/Documents/Code/Cardiac Memory/resus_qc"
INBOX_DIR = os.path.join(BASE_DIR, "_inbox")

def safe_write(path, content):
    if os.path.exists(path):
        print(f"SKIPPED (already exists): {path}")
        return
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    print(f"Created: {path}")

def safe_copy(src, dst):
    if os.path.exists(dst):
        print(f"SKIPPED (already exists): {dst}")
        return
    if not os.path.exists(src):
        safe_write(dst, f"<!-- TODO: paste from _inbox/{os.path.basename(src)}. See docs/tasks/UNKNOWN.md -->")
        print(f"GAP (missing source {src}) - Stubbed: {dst}")
        return
    dirname = os.path.dirname(dst)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"Copied: {src} -> {dst}")

os.chdir(BASE_DIR)

# STEP 1: Directories & __init__.py
dirs = [
    ".github", ".github/workflows",
    "dictionary", "mapping", "codegen", "codegen/templates",
    "generated", "generated/prompt_snapshots", "reducer", "ingest",
    "bq", "redcap", "router", "metrics", "prompts", "prompts/system",
    "prompts/passes", "prompts/anchors", "prompts/calibration",
    "prompts/fragments", "fixtures", "fixtures/real", "tests", "scripts",
    "config", "docs", "docs/tasks"
]
for d in dirs:
    os.makedirs(d, exist_ok=True)

# Add __init__.py to every Python package dir
package_dirs = ["codegen", "reducer", "ingest", "bq", "redcap", "router", "metrics", "prompts", "tests"]
for pd in package_dirs:
    safe_write(os.path.join(pd, "__init__.py"), "")
    # Add to subdirs if appropriate, though only prompt subdirs exist, tests, etc.
    # Instruction says "every Python package dir", I'll do main ones.

# STEP 2: Root files
safe_copy(os.path.join(INBOX_DIR, "00_agents.md"), "AGENTS.md")
safe_copy(os.path.join(INBOX_DIR, "01_build_order.md"), "docs/BUILD_ORDER.md")
safe_copy(os.path.join(INBOX_DIR, "03_check_invariants.sh"), "scripts/check_invariants.sh")
if os.path.exists("scripts/check_invariants.sh"):
    os.chmod("scripts/check_invariants.sh", 0o755)
safe_copy(os.path.join(INBOX_DIR, "30_registry.yaml"), "mapping/registry.yaml")
safe_copy(os.path.join(INBOX_DIR, "02_task_template.md"), "docs/tasks/_TEMPLATE.md")

pyproject_toml = """[project]
name = "resus_qc"
version = "0.1.0"
description = "resus_qc pipeline"
requires-python = ">=3.11"
dependencies = [
    "pyyaml",
    "pydantic>=2",
    "httpx",
    "google-cloud-bigquery"
]

[project.optional-dependencies]
dev = ["pytest", "ruff", "mypy"]

[tool.pytest.ini_options]
addopts = "-m 'not integration and not network'"
markers = [
    "integration: marks tests as integration",
    "network: marks tests as network"
]

[tool.ruff]

[tool.mypy]
strict = true
"""
safe_write("pyproject.toml", pyproject_toml)

gitignore = """__pycache__/
*.py[cod]
*$py.class
.pytest_cache/
.ruff_cache/
.mypy_cache/
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/
generated/*
!generated/coverage_manifest.json
"""
safe_write(".gitignore", gitignore)

codeowners = """/prompts/              @clinical-lead @eng-lead
/prompts/VERSIONS.yaml @clinical-lead @eng-lead @pi
/mapping/registry.yaml @clinical-lead @eng-lead
/dictionary/           @clinical-lead
"""
safe_write(".github/CODEOWNERS", codeowners)

# Load template for tasks
template_path = "docs/tasks/_TEMPLATE.md"
template_content = ""
if os.path.exists(template_path):
    with open(template_path, "r") as f:
        template_content = f.read()

def create_task(task_id, creates, depends, accept, body):
    if not template_content:
        content = f"# Task {task_id}\\n\\nPreconditions: {depends}\\nScope: {creates}\\nAcceptance: {accept}\\n\\n## Task\\n{body}"
    else:
        content = template_content
        content = content.replace("{{ID}}", task_id)
        content = content.replace("{{CREATES}}", creates if creates else "TBD — see docs/BUILD_ORDER.md")
        content = content.replace("{{DEPENDS}}", depends if depends else "TBD — see docs/BUILD_ORDER.md")
        content = content.replace("{{ACCEPTANCE}}", accept if accept else "TBD — see docs/BUILD_ORDER.md")
        
        # Replace task body
        if "## Task" in content:
            parts = content.split("## Task")
            content = parts[0] + "## Task\n" + body + ("\n## ⭐ MILESTONE — if the project stops anywhere, stop here." if task_id == "D12" else "")
        else:
            content += f"\n\n## Task\n{body}" + ("\n\n## ⭐ MILESTONE — if the project stops anywhere, stop here." if task_id == "D12" else "")
    
    safe_write(f"docs/tasks/{task_id}.md", content)

# Step 3 table
task_meta = {
    "D00": ("scaffold, scripts/, known_bugs.py", "—", "build.sh runs, fails only at codegen"),
    "D01": ("codegen/redcap_dict_to_code.py", "D00", "parser prints exactly `909 1889`"),
    "D02": ("codegen/branching.py, emit_branching.py", "D01", "all branching exprs compile; eval-injection test raises"),
    "D03": ("codegen/emit_manifest.py", "D02", "manifest 911/1891, unmapped []"),
    "D04": ("codegen/emit_python.py", "D03", "1891 export cols; rebuild byte-identical"),
    "D14": ("codegen/emit_contract.py", "D04", "every registry emit: key in contract exactly once"),
    "D05": ("reducer/engine.py", "D14+A04", "<500 lines; zero field-name literals"),
    "D06": ("reducer/{transforms,validators}.py", "D05", "12 validators, each severity-tested"),
    "D07": ("codegen/emit_sql.py, bq/deploy.py", "D04", "5 audit views execute"),
    "D08": ("ingest/{loader,ensemble}.py", "D07", "re-ingest yields zero new rows"),
    "D09": ("router/{policy,queue}.py", "D08", "submit() idempotent; ≥85% auto-accept"),
    "D10": ("metrics/compute.py", "D08", "CCF matches hand calc to 3dp"),
    "D11": ("redcap/{client,assemble}.py", "D06", "400 not retried; checkboxes all 1/0"),
    "D12": ("fixtures/, tests/test_coverage.py", "D05,D06", "ALL 1,891 columns emitted"),
    "D13": (".github/workflows/ci.yml, roundtrip test", "D11,D12", "round-trip byte-equal"),
}

# Parse D00-D13
inbox_10 = os.path.join(INBOX_DIR, "10_data_tasks.md")
if os.path.exists(inbox_10):
    with open(inbox_10, "r") as f:
        content_10 = f.read()
    # Split by ^=== (D\d\d) ===$
    sections = re.split(r'(?m)^===\s*(D\d\d)\s*===$', content_10)
    for i in range(1, len(sections), 2):
        tid = sections[i].strip()
        body = sections[i+1].strip()
        meta = task_meta.get(tid, ("", "", ""))
        create_task(tid, meta[0], meta[1], meta[2], body)
else:
    print(f"GAP: {inbox_10} missing")

inbox_11 = os.path.join(INBOX_DIR, "11_task_D14.md")
if os.path.exists(inbox_11):
    with open(inbox_11, "r") as f:
        body = f.read().strip()
    meta = task_meta.get("D14", ("", "", ""))
    create_task("D14", meta[0], meta[1], meta[2], body)
else:
    print(f"GAP: {inbox_11} missing")

# Step 4 table
task_meta_app = {
    "A01": ("prompts/ scaffold, VERSIONS.yaml, registry.py", "D14", "TBD — see docs/BUILD_ORDER.md"),
    "A02": ("Constitution v2.0 + 3 fragments", "A01", "TBD — see docs/BUILD_ORDER.md"),
    "A03": ("24 anchor cards, batch 1 = the 6 heaviest", "D14", "TBD — see docs/BUILD_ORDER.md"),
    "A04": ("P1 + P2 templates", "A02,A03", "TBD — see docs/BUILD_ORDER.md"),
    "A05": ("prompts/builder.py", "A04", "TBD — see docs/BUILD_ORDER.md"),
    "A06": ("P3, P4a, P4b, P5", "A05,D10", "TBD — see docs/BUILD_ORDER.md"),
}

body_a01 = '''Create prompts/VERSIONS.yaml (manifest listing active system prompt, six pass
templates, three fragments, anchors_dir, three TEAM calibration anchors, and
per-pass model binding with pinned model version, temperature, k, thinking
budget). Create prompts/registry.py exposing manifest(), load(key),
anchor(event_type), prompt_set_sha(), check_anchors(). Nothing may read a
prompt file by path — everything resolves through the manifest. Create
prompts/anchors/_SCHEMA.yaml defining required anchor-card keys:
defining_instants, audio_device, speech, visual, required_attributes,
disambiguation, hard_rules, abstain_if.'''

body_a02 = '''Instruct the agent to place _inbox/20_constitution.md into
prompts/system/constitution.v2.0.md, then extract the reusable blocks
(coverage rules, timestamp calibration, failure modes) into
prompts/fragments/ and replace them in the constitution with
{{fragment:name}} markers.'''

body_a03 = '''For each event type write prompts/anchors/<type>.yaml conforming to
_SCHEMA.yaml. The card must cover EVERY attribute in
generated/extraction_contract.json for that type — run
`python -m prompts.registry check-anchors` to find gaps. Defining instants
must be physically specific ("audible discharge click coincident with
whole-body myoclonic jerk", not "when the shock happens"). Speech blocks need
three banks: precursor, confirm, and negation-that-must-not-trigger. Enum
values are SYMBOLIC only — a card containing an integer choice code is a bug.'''

body_a05 = '''Implement prompts/builder.py with build_p1/p2/p3/p4a/p4b/p5, each returning
(system, user, response_schema, prompt_hash). Requirements: every built prompt
carries a header with contract_version, dict_version, constitution_hash,
anchor_library_version, template_hash; prompt_hash is sha256 of the assembled
text and must be identical for identical inputs (no dict-order leakage, no
timestamps); contract slices are per-event-type and asserted to be strict
subsets of the full contract; assert_no_field_names() greps every assembled
prompt against EXPORT_COLUMNS and raises on any hit.'''

inbox_21 = os.path.join(INBOX_DIR, "21_passes.md")
content_21 = ""
if os.path.exists(inbox_21):
    with open(inbox_21, "r") as f:
        content_21 = f.read()

# Extract passes
passes = {}
if content_21:
    sections = re.split(r'(?m)^===\s*(P\d[AB]?)\s*===$', content_21)
    for i in range(1, len(sections), 2):
        pid = sections[i].strip()
        passes[pid] = sections[i+1].strip()

body_a04 = f"=== P1 ===\\n{passes.get('P1', '')}\\n\\n=== P2 ===\\n{passes.get('P2', '')}"
body_a06 = f"=== P3 ===\\n{passes.get('P3', '')}\\n\\n=== P4A ===\\n{passes.get('P4A', '')}\\n\\n=== P4B ===\\n{passes.get('P4B', '')}\\n\\n=== P5 ===\\n{passes.get('P5', '')}"

create_task("A01", task_meta_app["A01"][0], task_meta_app["A01"][1], task_meta_app["A01"][2], body_a01)
create_task("A02", task_meta_app["A02"][0], task_meta_app["A02"][1], task_meta_app["A02"][2], body_a02)
create_task("A03", task_meta_app["A03"][0], task_meta_app["A03"][1], task_meta_app["A03"][2], body_a03)
create_task("A04", task_meta_app["A04"][0], task_meta_app["A04"][1], task_meta_app["A04"][2], body_a04)
create_task("A05", task_meta_app["A05"][0], task_meta_app["A05"][1], task_meta_app["A05"][2], body_a05)
create_task("A06", task_meta_app["A06"][0], task_meta_app["A06"][1], task_meta_app["A06"][2], body_a06)

# Step 5: State and memory files
state_md = """Phase: 1 (schema spine)
Last completed: scaffolding
Next task: D00
Verified gates: all unchecked, listed from the STEP 3 table
Environment: Python 3.11, TBD the rest
Known-broken/deferred: "prompts/ not yet created — built by A01"
Do not repeat: "Do not create prompts/ content before D14 and A01."

<!-- Updated by the agent as the LAST action of every session. If stale, the next session will redo or skip work. -->
"""
safe_write("docs/STATE.md", state_md)

decisions_md = """# Decisions
001 - The registry gate syntax must be normalized to `<attr> <op> <typed_literal>` before D3, because the supplied registry mixes `== 1` and `is true` for the same condition.
"""
safe_write("docs/DECISIONS.md", decisions_md)

open_qs_md = """# Open Questions
Q-001 CCI truncation policy when >30 
  - options: TBD 
  - default: 30 longest by duration
  - owner: clinical lead
  - status: OPEN
  - blocks: TBD

Q-002 new_pad_position when repositioned twice 
  - options: TBD
  - default: last
  - owner: clinical lead
  - status: OPEN
  - blocks: TBD

Q-003 mccd_obstacles obesity/cachexia 
  - options: TBD
  - default: hard-suppressed, GOV-07
  - owner: clinical lead
  - status: OPEN
  - blocks: TBD

Q-004 MCCD adjustment window with multiple adjustments 
  - options: TBD
  - default: envelope
  - owner: clinical lead
  - status: OPEN
  - blocks: TBD

Q-005 intub_assist bougie + fiberoptic 
  - options: TBD
  - default: bougie precedence
  - owner: clinical lead
  - status: OPEN
  - blocks: TBD

Q-006 TEAM autonomy threshold 
  - options: TBD
  - default: always human until ICC ≥ 0.75
  - owner: clinical lead
  - status: OPEN
  - blocks: TBD
"""
safe_write("docs/OPEN_QUESTIONS.md", open_qs_md)

runbook_md = """# Runbook

## Adding a REDCap variable

## Interpreting each audit view

## Rotating a prompt version

## Recovering a quarantined case
"""
safe_write("docs/RUNBOOK.md", runbook_md)

# Step 6: Stubs
def create_stub(path, task_id):
    content = f'''"""See docs/tasks/{task_id}.md"""

def stub():
    raise NotImplementedError("See docs/tasks/{task_id}.md")
'''
    safe_write(path, content)

stubs_python = {
    "codegen/redcap_dict_to_code.py": "D01",
    "codegen/branching.py": "D02",
    "codegen/emit_branching.py": "D02",
    "codegen/emit_manifest.py": "D03",
    "codegen/emit_python.py": "D04",
    "codegen/emit_contract.py": "D14",
    "reducer/engine.py": "D05",
    "reducer/transforms.py": "D06",
    "reducer/validators.py": "D06",
    "codegen/emit_sql.py": "D07",
    "bq/deploy.py": "D07",
    "ingest/loader.py": "D08",
    "ingest/ensemble.py": "D08",
    "router/policy.py": "D09",
    "router/queue.py": "D09",
    "metrics/compute.py": "D10",
    "redcap/client.py": "D11",
    "redcap/assemble.py": "D11",
    "tests/test_coverage.py": "D12",
    "prompts/registry.py": "A01",
    "prompts/builder.py": "A05"
}

for path, tid in stubs_python.items():
    create_stub(path, tid)

safe_write("scripts/hash_dict.sh", "#!/bin/bash\nsha256sum dictionary/instrument.csv > dictionary/dict_version.txt\n")
if os.path.exists("scripts/hash_dict.sh"):
    os.chmod("scripts/hash_dict.sh", 0o755)

safe_write("scripts/build.sh", "#!/bin/bash\nset -euo pipefail\nbash scripts/hash_dict.sh\n# codegen\n# manifest\n# pytest\n")
if os.path.exists("scripts/build.sh"):
    os.chmod("scripts/build.sh", 0o755)

safe_write("scripts/make_task.py", "# stub for make_task.py\n")
safe_write("docs/tasks/specs.yaml", "# specs.yaml stub\n")
safe_write("config/routing.yaml", "# TODO: Populated by D09\n")
safe_write("config/validators.yaml", "# TODO: Populated by D06\n")
safe_write("mapping/event_types.yaml", "# TODO: Populated by D14 from the union of registry owning_event_types.\n")

print("Scaffold done.")
