#!/usr/bin/env bash
# scripts/bootstrap.sh — one-time dev environment setup.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .venv

cat > .venv/pip.conf <<'EOF'
# Temporary: the inherited index (artifact-foundry-prod) does not carry
# setuptools or pytest. Scoped to this venv only; no global pip config is
# modified. If the inherited index is a deliberate institutional
# supply-chain control, this override must be REVERTED and the packages
# mirrored upstream instead. See docs/OPEN_QUESTIONS.md Q-007.
[global]
index-url = https://pypi.org/simple
EOF

source .venv/bin/activate

if ! pip install -e ".[dev]"; then
    echo "ERROR: pip install failed. Cannot proceed with incomplete environment." >&2
    exit 1
fi

.venv/bin/python - <<'PY'
import importlib.util, sys
missing = [m for m in ("yaml","pytest","pydantic","httpx")
           if not importlib.util.find_spec(m)]
if missing:
    print("MISSING:", missing); sys.exit(1)
print("env OK")
PY
