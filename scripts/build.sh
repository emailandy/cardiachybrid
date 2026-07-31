#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PY="$([[ -x .venv/bin/python ]] && echo .venv/bin/python \
      || command -v python3 || command -v python || true)"

bash scripts/hash_dict.sh
"$PY" -m codegen.redcap_dict_to_code --dict dictionary/instrument.csv --out generated/
"$PY" -m codegen.emit_manifest --dict dictionary/instrument.csv \
      --registry mapping/registry.yaml --out generated/
"$PY" -m pytest -q
