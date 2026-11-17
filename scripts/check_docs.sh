#!/usr/bin/env bash
# Resuscitation Quality Improvement Pipeline — Documentation Package Verification Script
# Verifies that every claim, number, finding ID, task file, and file reference in docs/*.md
# matches executable codebase artifacts and manifest counts.
set -euo pipefail

echo "=== Verifying Developer Documentation Package (docs/*.md) ==="

python3 -c "
import os
import re
import json
import urllib.parse
from pathlib import Path
from prompts.registry import prompt_set_sha

errors = 0

def log_err(msg):
    global errors
    print(f'\033[0;31m[FAIL]\033[0m {msg}')
    errors += 1

def log_ok(msg):
    print(f'\033[0;32m[PASS]\033[0m {msg}')

# 1. Check dict_version and prompt_set_sha in verification footers
dict_version = Path('dictionary/dict_version.txt').read_text().strip()
prompt_sha = prompt_set_sha(strict=True)

docs_to_verify = [
    '00_START_HERE.md',
    '01_ARCHITECTURE.md',
    '02_DATA_MODEL.md',
    '03_SENSOR_SPECS.md',
    '04_PROMPT_LAYER.md',
    '05_GCP_DEPLOYMENT.md',
    '06_ONBOARDING.md',
    '07_TESTING.md',
    '08_GLOSSARY.md',
    'RUNBOOK.md',
]

for name in docs_to_verify:
    p = Path('docs') / name
    if not p.exists():
        log_err(f'Required document docs/{name} does not exist.')
        continue
    content = p.read_text().strip()
    expected_substr = f'against dict_version {dict_version}, prompt_set_sha {prompt_sha}'
    if expected_substr not in content:
        log_err(f'docs/{name} footer does not match current dict_version ({dict_version}) and prompt_set_sha ({prompt_sha}).')
    else:
        log_ok(f'docs/{name} footer verification SHA match.')

# 2. Check every number in 02_DATA_MODEL.md against generated/coverage_manifest.json
with open('generated/coverage_manifest.json') as f:
    manifest = json.load(f)

dm_content = Path('docs/02_DATA_MODEL.md').read_text()
for key in ['n_fields', 'n_variables', 'DICT_IMPORTABLE_COLUMNS', 'DICT_EXPORT_COLUMNS', 'SUBMISSION_COLUMNS']:
    val = str(manifest[key])
    val_comma = f'{int(val):,}' if val.isdigit() else val
    if val not in dm_content and val_comma not in dm_content:
        log_err(f'docs/02_DATA_MODEL.md missing number {val} ({key} from coverage_manifest.json)')

for sc, count in manifest.get('by_source_class', {}).items():
    if str(count) not in dm_content:
        log_err(f'docs/02_DATA_MODEL.md missing source_class count {count} for {sc}')

for diff, count in manifest.get('by_difficulty', {}).items():
    if str(count) not in dm_content:
        log_err(f'docs/02_DATA_MODEL.md missing difficulty count {count} for {diff}')

log_ok('docs/02_DATA_MODEL.md numbers match generated/coverage_manifest.json.')

# 3. Check finding IDs cited exist in DEMO_FINDINGS.md or SENSOR_FINDINGS.md
valid_findings = set()
for findings_doc in ('docs/DEMO_FINDINGS.md', 'docs/SENSOR_FINDINGS.md'):
    fp = Path(findings_doc)
    if fp.exists():
        valid_findings.update(re.findall(r'F-\d{3}', fp.read_text()))

for p in Path('docs').glob('*.md'):
    if p.name in ('DEMO_FINDINGS.md', 'SENSOR_FINDINGS.md'): continue
    content = p.read_text()
    cited = set(re.findall(r'F-\d{3}', content))
    invalid = cited - valid_findings
    if invalid:
        log_err(f'docs/{p.name} cites undefined finding IDs: {invalid}')

log_ok(f'All finding citations across docs/*.md valid against DEMO_FINDINGS.md & SENSOR_FINDINGS.md ({len(valid_findings)} findings).')

# 4. Check every task file referenced exists in docs/tasks/
for p in Path('docs').glob('*.md'):
    content = p.read_text()
    task_refs = set(re.findall(r'docs/tasks/([A-Z]\d{2}[a-z]?)\.md', content))
    for t_id in task_refs:
        task_path = Path('docs/tasks') / f'{t_id}.md'
        if not task_path.exists():
            log_err(f'docs/{p.name} references non-existent task file: {task_path}')

log_ok('All task file references across docs/*.md exist in docs/tasks/.')

# 5. Check every file path referenced exists
for p in Path('docs').glob('*.md'):
    content = p.read_text()
    file_urls = re.findall(r'file://(/[^#\s)]+)', content)
    for url in file_urls:
        decoded_url = urllib.parse.unquote(url)
        if not os.path.exists(decoded_url):
            log_err(f'docs/{p.name} references non-existent file path: {decoded_url}')

log_ok('All file:// links across docs/*.md exist on disk.')

if errors > 0:
    print(f'\033[0;31m=== Documentation verification failed with {errors} error(s) ===\033[0m')
    exit(1)
else:
    print('\033[0;32m=== All documentation assertions passed successfully! ===\033[0m')
    exit(0)
"
