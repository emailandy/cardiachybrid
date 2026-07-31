#!/usr/bin/env bash
# scripts/bootstrap.sh — one-time dev environment setup.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip

if .venv/bin/python -m pip install -e ".[dev]" 2>/dev/null; then
  echo "installed from pyproject.toml"
else
  echo "pyproject.toml not yet complete — installing minimum for invariant checks"
  .venv/bin/python -m pip install pyyaml
fi

echo
echo "Activate with:  source .venv/bin/activate"
.venv/bin/python -c "import yaml; print('pyyaml', yaml.__version__)"
