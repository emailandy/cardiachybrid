import json
import yaml
from pathlib import Path

def load_registry():
    with open("mapping/registry.yaml") as f:
        return yaml.safe_load(f)

def iter_all_rules(registry):
    for sec in registry.get("sections", []):
        yield from sec.get("fields", [])
    yield from registry.get("never_ai", [])
    for g in registry.get("groups", []):
        yield g
        yield from g.get("fields", [])
        
def get_rule_et(r, registry):
    et = r.get("event_type") or r.get("interval_type")
    if not et and r.get("repeat_group"):
        for g in registry.get("groups", []):
            for gf in g.get("fields", []):
                if gf.get("pattern") == r.get("pattern"):
                    return g.get("event_type") or g.get("interval_type")
    return et

def test_prompt_contract_covers_every_reducer_read():
    registry = load_registry()
    contract = json.loads(Path("generated/extraction_contract.json").read_text())
    
    reads = set()
    for r in iter_all_rules(registry):
        if r.get("emit"):
            et = get_rule_et(r, registry)
            if et:
                reads.add((et, r["emit"]))
                
    contract_set = set()
    for et, spec in contract["event_types"].items():
        for a in spec["attributes"]:
            contract_set.add((et, a))
            
    assert reads <= contract_set, f"reducer reads attributes absent from contract: {reads - contract_set}"

def test_no_integer_codes_in_contract():
    contract = json.loads(Path("generated/extraction_contract.json").read_text())
    for et, spec in contract["event_types"].items():
        for name, a in spec["attributes"].items():
            if a["kind"].endswith("enum"):
                assert not any(str(v).isdigit() for v in a.get("values", [])), \
                    f"{et}.{name} exposes REDCap integer codes to the model: {a.get('values')}"

def test_normalize_gate_malformed():
    import pytest
    from codegen.emit_contract import normalize_gate
    
    attr = {"foo": {"kind": "bool"}}
    
    # invalid syntax
    with pytest.raises(ValueError, match="syntax error"):
        normalize_gate("foo ~ 1", attr)
        
    # unknown attribute
    with pytest.raises(ValueError, match="unknown attribute"):
        normalize_gate("bar == 1", attr)

def test_no_derived_where_keys_in_contract():
    from codegen.emit_contract import DERIVED_WHERE_KEYS
    contract = json.loads(Path("generated/extraction_contract.json").read_text())
    for et, spec in contract.get("event_types", {}).items():
        for attr_name in spec.get("attributes", {}):
            assert attr_name not in DERIVED_WHERE_KEYS, \
                f"{et}.{attr_name} is a derived where-key ({DERIVED_WHERE_KEYS[attr_name]}) and must not be a model attribute"
