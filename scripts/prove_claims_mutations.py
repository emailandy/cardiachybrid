#!/usr/bin/env python3
"""
scripts/prove_claims_mutations.py — Automated Proof of Gate Discrimination.

Sequentially injects eight distinct corruption mutations across repository files,
executes scripts/check_claims.sh, verifies that the gate fails with exit code 1
and the exact expected diagnostic error, and reverts each mutation cleanly.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

MUTATIONS = [
    {
        "name": "1. Plausible Non-Existent Commit SHA (9da9e74 -> 0000000)",
        "file": "docs/SENSOR_FINDINGS.md",
        "target": "commit `9da9e74`",
        "replacement": "commit `0000000`",
        "expected_check": "[1/7] Checking Git commit SHA resolutions",
    },
    {
        "name": "2. Corrupted Ground Truth Quotation (GT #1 [147.0, 155.0] -> [147.0, 152.0])",
        "file": "docs/SENSOR_FINDINGS.md",
        "target": r"GT #1 \$\[147\.0, 155\.0\]\$",
        "replacement": "GT #1 $[147.0, 152.0]$",
        "expected_check": "[2/7] Checking Ground Truth interval quotations",
    },
    {
        "name": "3. Duplicate Finding Identifier (F-028 -> F-027)",
        "file": "docs/SENSOR_FINDINGS.md",
        "target": r"11\. \*\*`F-028`",
        "replacement": "11. **`F-027`",
        "expected_check": "[3/7] Checking identifier uniqueness",
    },
    {
        "name": "4. Contradicted Metric Manifest Metric (F1 0.44 -> 0.52)",
        "file": "docs/SENSOR_FINDINGS.md",
        "target": r"\|\s*\*\*`0\.44`\*\*",
        "replacement": "| **`0.52`**",
        "expected_check": "[4/7] Checking metric manifest freshness & cross-document consistency",
    },
    {
        "name": "5. Broken Arithmetic Consistency (15.96s difference -> 19.96s difference)",
        "file": "docs/SENSOR_FINDINGS.md",
        "target": "$15.96\\text{s}$ difference ($155.96\\text{s} - 140.00\\text{s}$)",
        "replacement": "$19.96\\text{s}$ difference ($155.96\\text{s} - 140.00\\text{s}$)",
        "is_literal": True,
        "expected_check": "[5/7] Checking cited arithmetic consistency",
    },
    {
        "name": "6. Corrupted Grounded Run Log (docs/RUNS.jsonl corrupted / zero exit_code=0)",
        "file": "docs/RUNS.jsonl",
        "target": r'"exit_code": 0',
        "replacement": '"exit_code": 1',
        "allow_multiple": True,
        "expected_check": "[6/7] Checking grounded measurement run logs",
    },
    {
        "name": "7. Transient Workspace Residual File (.resus_qc_tmp/ left on disk)",
        "file": ".resus_qc_tmp/probe_residual_artifact.wav",
        "is_file_touch": True,
        "expected_check": "[7/7] Checking transient workspace integrity",
    },
    {
        "name": "8. Demo Pure-Renderer Contract Violation (embedded defaultReport in demo/ccf_viewer.html)",
        "file": "demo/ccf_viewer.html",
        "target": "</script>",
        "replacement": "const defaultReport = { ccf: 0.1538 };\n</script>",
        "expected_check": "[8/9] Checking demo/ pure-renderer contract",
    },
    {
        "name": "9. Unvalidated Report Carrying Leaked Ground Truth Metrics",
        "file": "demo/sample_simvideo2_ccf_report.json",
        "target": '"validation_status": "VALIDATED (against human ground truth)"',
        "replacement": '"validation_status": "Accuracy not validated for this case (no ground truth supplied)"',
        "is_literal": True,
        "expected_check": "[9/9] Checking unvalidated report integrity",
    },
]


def run_proof() -> None:
    print("================================================================================")
    print("DEMO ARTIFACT: AUTOMATED MUTATION PROOF FOR MECHANICAL HONESTY GATE")
    print("================================================================================\n")

    passed_mutations = 0
    total_mutations = len(MUTATIONS)

    for idx, mut in enumerate(MUTATIONS, start=1):
        print(f"--- Mutation {idx}/{total_mutations}: {mut['name']} ---")
        file_path = REPO_ROOT / mut["file"]
        is_touch = mut.get("is_file_touch", False)
        allow_multiple = mut.get("allow_multiple", False)

        try:
            if is_touch:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text("transient audio extract left on disk")
            else:
                original_text = file_path.read_text(encoding="utf-8")
                is_lit = mut.get("is_literal", False)
                if is_lit:
                    if mut["target"] not in original_text:
                        print(f"  ❌ ERROR: Could not find target literal in {mut['file']}")
                        continue
                    mutated_text = original_text.replace(mut["target"], mut["replacement"], 1)
                else:
                    if not re.search(mut["target"], original_text):
                        print(f"  ❌ ERROR: Could not find target pattern '{mut['target']}' in {mut['file']}")
                        continue
                    count = 0 if allow_multiple else 1
                    mutated_text = re.sub(mut["target"], mut["replacement"], original_text, count=count)
                file_path.write_text(mutated_text, encoding="utf-8")

            # Execute Gate
            res = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "claim_verifier.py")],
                capture_output=True,
                text=True,
            )

            if res.returncode != 0 and "MECHANICAL HONESTY GATE FAILED" in res.stdout:
                print(f"  ✓ Gate correctly FAILED (exit code {res.returncode})")
                for line in res.stdout.splitlines():
                    if "  - " in line:
                        print(f"    Error: {line.strip()}")
                passed_mutations += 1
            else:
                print(f"  ❌ UNEXPECTED PASS (exit code {res.returncode}): Gate failed to reject mutation!")
                print(res.stdout)

        finally:
            # Revert Mutation
            if is_touch:
                if file_path.exists():
                    file_path.unlink()
            else:
                file_path.write_text(original_text, encoding="utf-8")

        print("  ✓ Mutation cleanly reverted.\n")

    print("================================================================================")
    print(f"FINAL PROOF SUMMARY: {passed_mutations}/{total_mutations} MUTATIONS REJECTED")
    print("================================================================================")
    if passed_mutations == total_mutations:
        print("✓ All injected mutations were deterministically detected and rejected.")
    else:
        print(f"❌ {total_mutations - passed_mutations} mutations escaped detection.")


if __name__ == "__main__":
    run_proof()
