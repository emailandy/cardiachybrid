#!/usr/bin/env python3
"""
scripts/record_run.py — Deterministic Measurement & Execution Logger

Executes a command, measures exact wall-clock runtime, captures exit code and stdout/stderr,
computes output SHA-256, and appends a structured record to docs/RUNS.jsonl.

Usage:
  python scripts/record_run.py <command ...>
"""

from __future__ import annotations

import datetime
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_FILE = REPO_ROOT / "docs" / "RUNS.jsonl"


def record_execution(command_args: list[str]) -> int:
    if not command_args:
        print("Usage: python scripts/record_run.py <command ...>", file=sys.stderr)
        return 1

    start_wall = time.time()
    t_start_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    proc = subprocess.run(
        command_args,
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    duration_s = round(time.time() - start_wall, 4)
    t_end_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    stdout_text = proc.stdout or ""
    stdout_hash = hashlib.sha256(stdout_text.encode("utf-8")).hexdigest()

    # Echo stdout directly to terminal
    sys.stdout.write(stdout_text)
    sys.stdout.flush()

    record = {
        "timestamp_start": t_start_iso,
        "timestamp_end": t_end_iso,
        "duration_s": duration_s,
        "command": " ".join(command_args),
        "exit_code": proc.returncode,
        "stdout_sha256": stdout_hash,
        "stdout_tail": stdout_text.strip().splitlines()[-5:] if stdout_text else [],
    }

    RUNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RUNS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    return proc.returncode


if __name__ == "__main__":
    sys.exit(record_execution(sys.argv[1:]))
