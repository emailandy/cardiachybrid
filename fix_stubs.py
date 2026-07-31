import glob
import os
import re

directories = ['codegen', 'reducer', 'ingest', 'bq', 'redcap', 'router', 'metrics']
for d in directories:
    for f in glob.glob(f'{d}/*.py'):
        if os.path.basename(f) in ['__init__.py', 'known_bugs.py']:
            continue
        
        with open(f, 'r') as file:
            content = file.read()
        
        task_match = re.search(r'(D\d+[a-z]?)', content)
        task_id = task_match.group(1) if task_match else "UNKNOWN"
        module_path = f.replace('/', '.').replace('.py', '')
        
        new_content = f'''"""Stub module. Not implemented — see docs/tasks/{task_id}.md"""
from __future__ import annotations

def main() -> None:
    raise NotImplementedError(
        "{module_path} is a stub. See docs/tasks/{task_id}.md")

if __name__ == "__main__":
    main()
'''
        with open(f, 'w') as file:
            file.write(new_content)
