#!/usr/bin/env bash
# Exit 0 = all runnable invariants pass.
# Exit 1 = a real violation.
# Exit 2 = one or more checks COULD NOT RUN (env incomplete). Never treat as pass.
set -uo pipefail

PY="$([[ -x .venv/bin/python ]] && echo .venv/bin/python \
      || command -v python3 || command -v python || true)"
[[ -z "$PY" ]] && { printf '\033[31m✗ no python interpreter on PATH\033[0m\n'; exit 2; }

fail=0; cannot_run=0
red()   { printf '\033[31m✗ %s\033[0m\n' "$1"; fail=1; }
green() { printf '\033[32m✓ %s\033[0m\n' "$1"; }
skip()  { printf '\033[33m– %s (not yet built)\033[0m\n' "$1"; }
err()   { printf '\033[35m⚠ %s\033[0m\n' "$1"; cannot_run=1; }

have_yaml() { "$PY" -c "import yaml" 2>/dev/null; }

# ── I1  dictionary is the only schema source ────────────────────────────────
if [[ ! -f dictionary/instrument.csv ]]; then
  red "I1 dictionary/instrument.csv MISSING — stage it before any task"
elif [[ ! -f dictionary/dict_version.txt ]]; then
  skip "I1 dict_version.txt absent — run scripts/hash_dict.sh (bootstrap)"
elif command -v sha256sum >/dev/null; then
  H=$(sha256sum dictionary/instrument.csv | cut -c1-16)
elif command -v shasum >/dev/null; then
  H=$(shasum -a 256 dictionary/instrument.csv | cut -c1-16)
else
  err "I1 CANNOT RUN — no sha256sum or shasum on PATH"
  H=""
fi

if [[ -n "${H:-}" ]]; then
  if [[ "$H" != "$(cat dictionary/dict_version.txt)" ]]; then
    red "I1 dict_version.txt STALE — dictionary changed without rehash"
  else
    green "I1 dictionary hash current"
  fi
fi

# ── I2  no REDCap field names outside dictionary/ and mapping/ ──────────────
hits=$(grep -rnE '"[a-z][a-z0-9_]*_v2"|"(num_cci|record_id|reason_cci)[a-z0-9_]*"' \
       --include='*.py' reducer/ redcap/ router/ metrics/ ingest/ prompts/ \
       2>/dev/null | grep -v '^generated/' || true)
if [[ -n "$hits" ]]; then red "I2 field-name literals:"; echo "$hits"
else green "I2 no field-name literals"; fi

# ── I3  yesno is 1/0 ────────────────────────────────────────────────────────
if [[ ! -f generated/redcap_fields.py ]]; then
  skip "I3 requires generated/redcap_fields.py (D04)"
elif ! have_yaml; then
  err "I3 CANNOT RUN — PyYAML absent (needed for imports). Run scripts/bootstrap.sh"
else
  "$PY" - <<'PY'; rc=$?
from generated.redcap_fields import FIELDS
bad = [f for f, s in FIELDS.items()
       if s.field_type == "yesno" and set(s.choices) != {"1", "0"}]
if bad: print("  offending fields:", bad[:10])
raise SystemExit(1 if bad else 0)
PY
  [[ $rc -eq 0 ]] && green "I3 yesno fields are 1/0" || red "I3 yesno not 1/0"
fi

# ── I4  checkbox loops iterate the dictionary, not the selection ────────────
if [[ -d reducer && -n "$(ls -A reducer/*.py 2>/dev/null)" ]]; then
  if grep -rn "for .* in selected" reducer/ 2>/dev/null | grep -qi checkbox; then
    red "I4 checkbox loop iterates selection, not spec.choices"
  else green "I4 checkbox emission pattern ok"; fi
else
  skip "I4 requires reducer/ (D05)"
fi

# ── I5  every gate_3way supplies coverage_channels ──────────────────────────
if [[ ! -f mapping/registry.yaml ]]; then
  red "I5 mapping/registry.yaml MISSING"
elif ! have_yaml; then
  err "I5 CANNOT RUN — PyYAML absent. Run scripts/bootstrap.sh"
else
  "$PY" - <<'PY'; rc=$?
import sys, yaml
class StrictLoader(yaml.SafeLoader): pass
def _no_duplicates(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping: raise ValueError("Duplicate key")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping
StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicates)
reg = yaml.load(open("mapping/registry.yaml"), Loader=StrictLoader)
has_default = "coverage_channels" in (reg.get("defaults") or {})
bad = []
def walk(o, path=""):
    if isinstance(o, dict):
        if o.get("rule") == "gate_3way" and "coverage_channels" not in o and not has_default:
            bad.append(o.get("field") or o.get("pattern") or path)
        for k, v in o.items(): walk(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o): walk(v, f"{path}[{i}]")
walk(reg)
if bad: print("  gate_3way without coverage_channels:", bad[:10])
sys.exit(1 if bad else 0)
PY
  [[ $rc -eq 0 ]] && green "I5 gate_3way calls coverage-aware" \
                  || red "I5 gate_3way missing coverage_channels"
fi

# ── I6  no silent coercion on validation-failure paths ──────────────────────
if [[ -f reducer/validators.py ]]; then
  hits=$(grep -nE '\b(min\(max\(|clamp|round\()' reducer/validators.py || true)
  if [[ -n "$hits" ]]; then red "I6 possible coercion:"; echo "$hits"
  else green "I6 no coercion in validators"; fi
else
  skip "I6 requires reducer/validators.py (D06)"
fi

# ── codegen determinism ─────────────────────────────────────────────────────
if [[ -f generated/redcap_fields.py && -f codegen/redcap_dict_to_code.py ]]; then
  cp generated/redcap_fields.py /tmp/_inv_before.py
  "$PY" -m codegen.redcap_dict_to_code --quiet >/dev/null 2>&1 || true
  if diff -q /tmp/_inv_before.py generated/redcap_fields.py >/dev/null; then
    green "codegen redcap_fields deterministic"
  else
    red "codegen redcap_fields NOT deterministic — generated/ differs on rebuild"
  fi
else
  skip "determinism check requires D01+D04"
fi

if [[ -f generated/branching_compiled.py && -f codegen/emit_branching.py ]]; then
  cp generated/branching_compiled.py /tmp/_inv_before_br.py
  "$PY" -m codegen.emit_branching >/dev/null 2>&1 || true
  if diff -q /tmp/_inv_before_br.py generated/branching_compiled.py >/dev/null; then
    green "codegen branching deterministic"
  else
    red "codegen branching NOT deterministic"
  fi
fi

echo
if   [[ $fail -ne 0 ]];       then red   "INVARIANT VIOLATION — do not proceed"; exit 1
elif [[ $cannot_run -ne 0 ]]; then err   "CHECKS INCOMPLETE — environment problem, do not proceed"; exit 2
else                               green "INVARIANTS OK (skips are expected pre-build)"; exit 0
fi
