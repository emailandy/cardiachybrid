#!/usr/bin/env bash
# scripts/check_claims.sh — Mechanical Honesty & Consistency Gate Runner
#
# CRITICAL NOTICE:
# This script is a CONSISTENCY GATE, NOT A SCIENTIFIC CORRECTNESS GATE.
# It mechanically verifies that citations, SHAs, ground-truth quotes, manifest metrics,
# and arithmetic formulas agree across repository documents.
# It does NOT validate clinical assumptions or detect algorithmic regressions.
# True scientific validation requires empirical execution against human ground truth.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
if [ ! -f "${PYTHON_BIN}" ]; then
    PYTHON_BIN="python3"
fi

exec "${PYTHON_BIN}" "${REPO_ROOT}/scripts/claim_verifier.py" "$@"
