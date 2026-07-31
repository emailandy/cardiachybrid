#!/usr/bin/env bash
# Writes the first 16 hex chars of sha256(instrument.csv) to dict_version.txt.
# Format must match the comparison in scripts/check_invariants.sh exactly.
set -euo pipefail
cd "$(dirname "$0")/.."

if command -v sha256sum >/dev/null; then
  H=$(sha256sum dictionary/instrument.csv | cut -c1-16)
elif command -v shasum >/dev/null; then
  H=$(shasum -a 256 dictionary/instrument.csv | cut -c1-16)
else
  echo "ERROR: no sha256sum or shasum on PATH" >&2; exit 2
fi

printf '%s' "$H" > dictionary/dict_version.txt   # no trailing newline
echo "dict_version: $H"
