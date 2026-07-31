#!/usr/bin/env bash
# scripts/check_invariants.sh — the six invariants, mechanically
set -uo pipefail
fail=0
red()  { printf '\033[31m✗ %s\033[0m\n' "$1"; fail=1; }
green(){ printf '\033[32m✓ %s\033[0m\n' "$1"; }

# I1 — dictionary is the only schema source
if [[ "$(sha256sum dictionary/instrument.csv | cut -c1-16)" \
      != "$(cat dictionary/dict_version.txt)" ]]; then
  red "I1 dict_version.txt is stale — run scripts/hash_dict.sh"
else green "I1 dictionary hash current"; fi

# I2 — no REDCap field names outside dictionary/ and mapping/
hits=$(grep -rnE '"[a-z][a-z0-9_]*_v2"|"(num_cci|record_id|reason_cci)[a-z0-9_]*"' \
       --include='*.py' reducer/ redcap/ router/ metrics/ ingest/ prompts/ \
       2>/dev/null | grep -v '^generated/' || true)
if [[ -n "$hits" ]]; then red "I2 field-name literals:"; echo "$hits"
else green "I2 no field-name literals"; fi

# I3 — yesno is 1/0
python - <<'PY' || fail=1
from generated.redcap_fields import FIELDS
bad = [f for f,s in FIELDS.items()
       if s.field_type=="yesno" and set(s.choices)!={"1","0"}]
print("\033[31m✗ I3 yesno not 1/0:", bad, "\033[0m") if bad else \
print("\033[32m✓ I3 yesno fields are 1/0\033[0m")
raise SystemExit(1 if bad else 0)
PY

# I4 — checkbox loops iterate the dictionary, not the selection
if grep -rn "for .* in selected" reducer/ 2>/dev/null | grep -qi checkbox; then
  red "I4 checkbox loop appears to iterate selection, not spec.choices"
else green "I4 checkbox emission pattern ok"; fi

# I5 — every gate_3way call supplies coverage_channels
python - <<'PY' || fail=1
import yaml, sys
reg = yaml.safe_load(open("mapping/registry.yaml"))
bad = []
def walk(o, path=""):
    if isinstance(o, dict):
        if o.get("rule")=="gate_3way" and "coverage_channels" not in o \
           and "coverage_channels" not in reg.get("defaults",{}):
            bad.append(o.get("field") or o.get("pattern") or path)
        for k,v in o.items(): walk(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i,v in enumerate(o): walk(v, f"{path}[{i}]")
walk(reg)
print("\033[31m✗ I5 gate_3way without coverage_channels:", bad[:10], "\033[0m") if bad else \
print("\033[32m✓ I5 all gate_3way calls coverage-aware\033[0m")
sys.exit(1 if bad else 0)
PY

# I6 — no silent coercion on validation-failure paths
hits=$(grep -rnE '\b(min\(max\(|clamp|round\()' reducer/validators.py 2>/dev/null || true)
if [[ -n "$hits" ]]; then red "I6 possible coercion in validators:"; echo "$hits"
else green "I6 no coercion in validators"; fi

# generated/ must be reproducible
if [[ -f generated/redcap_fields.py ]]; then
  cp generated/redcap_fields.py /tmp/_before.py
  python -m codegen.redcap_dict_to_code --quiet 2>/dev/null || true
  diff -q /tmp/_before.py generated/redcap_fields.py >/dev/null \
    && green "codegen deterministic" \
    || red "codegen not deterministic — generated/ differs on rebuild"
fi

exit $fail
