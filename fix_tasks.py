import os
import re

BASE_DIR = "/Users/emailandy/Documents/Code/Cardiac Memory/resus_qc"
os.chdir(BASE_DIR)

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

task_meta_app = {
    "A01": ("prompts/ scaffold, VERSIONS.yaml, registry.py", "D14", "TBD — see docs/BUILD_ORDER.md"),
    "A02": ("Constitution v2.0 + 3 fragments", "A01", "TBD — see docs/BUILD_ORDER.md"),
    "A03": ("24 anchor cards, batch 1 = the 6 heaviest", "D14", "TBD — see docs/BUILD_ORDER.md"),
    "A04": ("P1 + P2 templates", "A02,A03", "TBD — see docs/BUILD_ORDER.md"),
    "A05": ("prompts/builder.py", "A04", "TBD — see docs/BUILD_ORDER.md"),
    "A06": ("P3, P4a, P4b, P5", "A05,D10", "TBD — see docs/BUILD_ORDER.md"),
}

task_bodies = {}

# Parse D00-D13
with open("_inbox/10_data_tasks.md", "r") as f:
    c = f.read()
    # Find all sections D00-D13. Note: re.split might leave empty or missing chunks at the end if no newline
    # A safer way:
    matches = list(re.finditer(r'(?m)^===\s*(D\d\d)\s*===\n', c))
    for i in range(len(matches)):
        tid = matches[i].group(1)
        start = matches[i].end()
        end = matches[i+1].start() if i+1 < len(matches) else len(c)
        task_bodies[tid] = c[start:end].strip()

# D14
with open("_inbox/11_task_D14.md", "r") as f:
    task_bodies["D14"] = f.read().strip()

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

with open("_inbox/21_passes.md", "r") as f:
    c21 = f.read()

passes = {}
matches_p = list(re.finditer(r'(?m)^===\s*(P\d[AB]?)\s*===\n', c21))
for i in range(len(matches_p)):
    pid = matches_p[i].group(1)
    start = matches_p[i].end()
    end = matches_p[i+1].start() if i+1 < len(matches_p) else len(c21)
    passes[pid] = c21[start:end].strip()

body_a04 = f"=== P1 ===\n{passes.get('P1', '')}\n\n=== P2 ===\n{passes.get('P2', '')}"
body_a06 = f"=== P3 ===\n{passes.get('P3', '')}\n\n=== P4A ===\n{passes.get('P4A', '')}\n\n=== P4B ===\n{passes.get('P4B', '')}\n\n=== P5 ===\n{passes.get('P5', '')}"

task_bodies["A01"] = body_a01
task_bodies["A02"] = body_a02
task_bodies["A03"] = body_a03
task_bodies["A04"] = body_a04
task_bodies["A05"] = body_a05
task_bodies["A06"] = body_a06

all_meta = {}
all_meta.update(task_meta)
all_meta.update(task_meta_app)

with open("_inbox/02_task_template.md", "r") as f:
    template_content = f.read()

for tid, (creates, depends, accept) in all_meta.items():
    c = template_content
    c = c.replace("{{TASK_ID}}", tid)
    c = c.replace("{{TASK_TITLE}}", "")
    c = c.replace("{{PREVIOUS_TASKS}}", depends if depends else "TBD — see docs/BUILD_ORDER.md")
    c = c.replace("{{REQUIRED_FILES}}", "TBD — see docs/BUILD_ORDER.md")
    c = c.replace("{{ADDITIONAL_PRECONDITIONS}}", "TBD — see docs/BUILD_ORDER.md")
    
    c = c.replace("{{FILES_TO_CREATE}}", creates if creates else "TBD — see docs/BUILD_ORDER.md")
    c = c.replace("{{FILES_TO_MODIFY}}", "TBD — see docs/BUILD_ORDER.md")
    c = c.replace("{{FILES_TO_READ}}", "TBD — see docs/BUILD_ORDER.md")
    
    # Replace body
    body = task_bodies.get(tid, "")
    if tid == "D12":
        body += "\n\n## ⭐ MILESTONE — if the project stops anywhere, stop here."
    c = c.replace(f"<<< the full {tid} prompt text goes here, verbatim >>>", body)
    
    c = c.replace("{{ADDITIONAL_ACCEPTANCE_CRITERIA}}", accept if accept else "TBD — see docs/BUILD_ORDER.md")
    
    # Fill in dummy for others so it looks clean
    c = c.replace("{{TEST_FILES}}", "TBD")
    c = c.replace("{{MAIN_FILE}}", "TBD")
    c = c.replace("{{LINE_LIMIT}}", "TBD")
    c = c.replace("{{MODULE_DIR}}", "TBD")
    c = c.replace("{{TASK_SPECIFIC_QUESTION_1}}", "TBD")
    c = c.replace("{{TASK_SPECIFIC_QUESTION_2}}", "TBD")
    c = c.replace("{{COMMIT_MESSAGE}}", "TBD")
    
    with open(f"docs/tasks/{tid}.md", "w") as f:
        f.write(c)
