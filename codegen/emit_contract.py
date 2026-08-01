import sys
from codegen.yamlio import load_yaml
from codegen.redcap_dict_to_code import load_dictionary
import json
import re
from pathlib import Path

# where-keys that are DERIVED by the reducer, not observed by the model.
# A where-key becomes a model attribute only if independently observable.
# If it is computable from another attribute, the reducer computes it —
# otherwise the model can emit a contradictory pair that nothing validates.
DERIVED_WHERE_KEYS = {
    "drug_class":       "derived from `drug` by the reducer's drug taxonomy",
    "rhythm_shockable": "derived from `rhythm` ∈ {vf, pulseless_vt, "
                        "aed_shockable, aicd_shockable}",
}

def load_registry():
    return load_yaml(Path("mapping/registry.yaml"))

def load_event_types():
    return load_yaml(Path("mapping/event_types.yaml"))

def parse_choices(choices_str):
    choices = {}
    if not choices_str: return choices
    for pair in choices_str.split('|'):
        if ',' in pair:
            code, label = pair.split(',', 1)
            choices[code.strip()] = label.strip()
    return choices

def to_vocab_label(label: str) -> str:
    s = label.lower()
    if "not available" in s or "not applicable" in s: return "not_available"
    if "unable to determine" in s: return "unable_to_determine"
    s = re.sub(r'[^a-z0-9]+', '_', s).strip('_')
    if not s or s[0].isdigit(): s = "code_" + s
    return s

def normalize_gate(gate_str, et_attributes):
    m = re.match(r'^([a-zA-Z0-9_]+)\s*(==|!=|>=|<=|>|<|contains|is)\s*(.+)$', gate_str)
    if not m:
        raise ValueError(f"Gate syntax error: {gate_str}")
    attr_name, op, val = m.groups()
    val = val.strip()
    
    if op == "is":
        op = "=="
        
    attr_spec = et_attributes.get(attr_name)
    if not attr_spec:
        raise ValueError(f"Gate references unknown attribute {attr_name} in {gate_str}")
        
    if attr_spec["kind"] == "bool":
        if val in ("1", "true", "True", "yes"):
            val = "true"
        elif val in ("0", "false", "False", "no"):
            val = "false"
    elif attr_spec["kind"] == "int":
        val = str(int(val))
        
    return f"{attr_name} {op} {val}"

def iter_all_rules(registry):
    for sec in registry.get("sections", []):
        yield from sec.get("fields", [])
    yield from registry.get("never_ai", [])
    for g in registry.get("groups", []):
        yield g
        group_et = g.get("event_type")
        if not group_et and g.get("interval_type"):
            it = g.get("interval_type")
            if it == "cci": group_et = "compression_interruption"
            elif it == "rosc": group_et = "rosc_detected"
            elif it == "vent_delay": group_et = "ventilation_delay"
        for gf in g.get("fields", []):
            gf_copy = dict(gf)
            if not gf_copy.get("rule") and gf_copy.get("emit"):
                gf_copy["rule"] = "attr"
            if not gf_copy.get("rule") and gf_copy.get("kind") == "checkbox":
                gf_copy["rule"] = "checkbox"
            if not gf_copy.get("emit") and gf_copy.get("rule") in ("gate_yesno", "gate_3way"):
                pat = str(gf_copy.get("pattern", ""))
                if "aline_present" in pat: gf_copy["emit"] = "aline_present"
                elif "vitals_obtained" in pat: gf_copy["emit"] = "vitals_obtained"
            if g.get("name") == "rosc" and ("vitals" in str(gf_copy.get("gate", "")) or gf_copy.get("emit") in ("hr", "sbp", "dbp", "spo2", "etco2", "vitals_t_s")):
                gf_copy["event_type"] = "vitals_reading"
            elif group_et and not gf_copy.get("event_type"):
                gf_copy["event_type"] = group_et
            yield gf_copy
            if gf_copy.get("emit") == "pocus_other_used":
                extra = dict(gf_copy)
                extra["event_type"] = "compression_interruption"
                yield extra

def get_field_vocab(f_spec, rule, registry):
    vocab_name = rule.get("vocab_override") or rule.get("vocab")
    if vocab_name and vocab_name in registry.get("vocabularies", {}):
        res = {}
        for key, val in registry["vocabularies"][vocab_name].items():
            res[str(val)] = str(key)
        return res
    
    # Fallback to dictionary
    if f_spec.field_type == "yesno":
        return {"1": "yes", "0": "no"}
    elif f_spec.field_type == "truefalse":
        return {"1": "true", "0": "false"}
    
    choices = f_spec.choices if isinstance(f_spec.choices, dict) else parse_choices(f_spec.choices)
    res = {}
    for code, label in choices.items():
        res[str(code)] = to_vocab_label(label)
    return res

def main():
    specs = load_dictionary(Path("dictionary/instrument.csv"))
    registry = load_registry()
    et_yaml = load_event_types()
    
    # Pre-parse attributes for their kind and build the contract
    contract = {
        "event_types": {},
        "case_fields": {},
        "narrative_sections": [],
        "team_items": [],
        "contract_excluded": []
    }
    
    req_cats = ["redcap_feeding", "interval_boundary", "negative_control", "context"]
    all_event_types = set()
    for cat in req_cats:
        all_event_types.update(et_yaml.get(cat, []))
    all_event_types = sorted(list(all_event_types))
    
    # Initialize the 42 event types
    for et in all_event_types:
        contract["event_types"][et] = {
            "event_type": et,
            "scope": "event", # default, will upgrade to interval if applicable
            "attributes": {},
            "suppressed": [],
            "inference_permitted": [],
            "coverage_channels": []
        }
        
    # Read anchor cards for defining_instants
    for et in all_event_types:
        p = Path(f"prompts/anchors/{et}.yaml")
        if p.exists():
            anchor = load_yaml(p)
            if anchor and "defining_instants" in anchor:
                contract["event_types"][et]["defining_instants"] = anchor["defining_instants"]
        if "defining_instants" not in contract["event_types"][et]:
            contract["event_types"][et]["defining_instants"] = {}
            
    # Interval mapping
    interval_types = {}
    for g in registry.get("groups", []):
        if g.get("source") == "interval":
            interval_types[g["interval_type"]] = g
            
    assert len(interval_types) == 3, f"Expected 3 interval types, got {len(interval_types)}"
    
    # Build a lookup for (event_type, emit) -> {kind, values, required, feeds, difficulty, ...}
    # and case_fields, narrative_sections, team_items
    
    # First pass: map everything
    for rule in iter_all_rules(registry):
        r_type = rule.get("rule")
        if not r_type: continue
        
        # We process 'groups' (which have source: interval)
        if "name" in rule and "count_field" in rule:
            # this is a group
            if rule.get("source") == "interval":
                i_type = rule.get("interval_type")
                if i_type == "cci":
                    start, end = "compression_interruption", None
                    mode = "self"
                elif i_type == "rosc":
                    start, end = "rosc_detected", "rosc_lost"
                    mode = "paired"
                elif i_type == "vent_delay":
                    start, end = "ventilation_delay", None
                    mode = "self"
                else:
                    raise ValueError(f"Unknown interval type {i_type}")
                    
                et = start
                contract["event_types"][et]["scope"] = "interval"
                contract["event_types"][et]["boundary_mode"] = mode
                contract["event_types"][et]["boundary_events"] = {"start": start, "end": end}
            continue

        if r_type in ("const_null", "passthrough"):
            contract["contract_excluded"].append(rule)
            continue
            
        f_name = rule.get("field") or rule.get("pattern")
        if not f_name: continue
        
        if r_type == "notes":
            contract["narrative_sections"].append(rule)
            continue
        if r_type == "team_score":
            contract["team_items"].append(rule)
            continue
            
        # For fields, we might have {i}
        if "{i}" in f_name:
            base_field = f_name.replace("{i}", "1")
        else:
            base_field = f_name
            
        f_spec = specs.get(base_field)
        if not f_spec: continue
        
        if r_type == "case_field":
            key = rule.get("key")
            from generated.redcap_fields import EXPORT_COLUMNS
            if key in EXPORT_COLUMNS:
                raise ValueError(f"case_field key '{key}' collides with REDCap field name in EXPORT_COLUMNS")
            contract["case_fields"][key] = {
                "vocab": list(get_field_vocab(f_spec, rule, registry).values()),
                "owning_event_types": rule.get("owning_event_types", []),
                "feeds": f_name
            }
            continue
            
        emit = rule.get("emit")
        et = rule.get("event_type") or rule.get("interval_type")
        
        # Some fields might not have event_type directly (e.g., inherited from group)
        if not et and rule.get("repeat_group"):
            # Wait, repeat_group is not available in rule dict directly unless I pass it.
            # I can lookup from registry.groups
            for g in registry.get("groups", []):
                for gf in g.get("fields", []):
                    if gf.get("pattern") == rule.get("pattern"):
                        et = g.get("event_type") or g.get("interval_type")
                        
        if et and isinstance(rule.get("where"), dict):
            for k in sorted(rule["where"]):
                if k in DERIVED_WHERE_KEYS:
                    continue
                if k not in contract["event_types"][et]["attributes"]:
                    kind = "string"
                    values = None
                    if k in ("confirmed", "present_on_arrival", "rhythm_shockable", "pocus_other_used", "aline_present", "vitals_obtained"):
                        kind = "bool"
                        values = [True, False]
                    elif k == "applied_by":
                        kind = "enum"
                        values = ["ed_team", "ems_team", "unable_to_determine"]
                    elif k in ("from", "to"):
                        kind = "enum"
                        values = ["manual", "mechanical", "unable_to_determine"]
                    elif k == "drug":
                        kind = "enum"
                        values = ["epinephrine", "lidocaine", "amiodarone", "other", "unable_to_determine"]
                    elif k == "drug_class":
                        kind = "enum"
                        values = ["vasopressor", "antiarrhythmic", "thrombolytic", "other", "unable_to_determine"]

                    contract["event_types"][et]["attributes"][k] = {
                        "kind": kind,
                        "required": False,
                        "feeds": [f_name],
                        "n_export_columns": 1,
                        "difficulty": rule.get("difficulty", "HIGH")
                    }
                    if values:
                        contract["event_types"][et]["attributes"][k]["values"] = values
                else:
                    if f_name not in contract["event_types"][et]["attributes"][k]["feeds"]:
                        contract["event_types"][et]["attributes"][k]["feeds"].append(f_name)

        if emit and et:
            # It's an attribute!
            kind = "string"
            values = None
            
            vocab = get_field_vocab(f_spec, rule, registry)
            if rule.get("kind") == "checkbox" or f_spec.field_type == "checkbox":
                kind = "multi_enum"
                values = list(vocab.values())
            elif vocab and len(vocab) == 2 and set(vocab.values()) == {"yes", "no"}:
                kind = "bool"
                values = [True, False]
            elif vocab and len(vocab) == 2 and set(vocab.values()) == {"true", "false"}:
                kind = "bool"
                values = [True, False]
            elif rule.get("rule") == "gate_3way":
                kind = "bool"
                values = [True, False]
            elif vocab and len(vocab) >= 3:
                kind = "enum"
                values = list(vocab.values())
            elif "range" in rule:
                kind = "int"
            elif rule.get("transform") == "to_redcap_datetime":
                kind = "timestamp"
                
            attr = {
                "kind": kind,
                "required": f_spec.required if hasattr(f_spec, "required") else False,
                "feeds": [f_name],
                "n_export_columns": len(f_spec.export_columns) if hasattr(f_spec, "export_columns") else 1,
                "difficulty": rule.get("difficulty", "MEDIUM"),
            }
            if values:
                # Remove suppressed codes from values
                sc = rule.get("suppress_codes", [])
                suppressed_symbols = [vocab[str(c)] for c in sc if str(c) in vocab]
                values = [v for v in values if v not in suppressed_symbols]
                attr["values"] = values
                
            if "range" in rule:
                attr["range"] = rule["range"]
            if rule.get("detector") or rule.get("detector_hint"):
                attr["detector_hint"] = rule.get("detector") or rule.get("detector_hint")
            if "gate" in rule:
                attr["gated_by"] = rule["gate"] # Will normalize in pass 2
                
            # If pattern has {i}, calculate index_exceptions
            if "{i}" in f_name and kind in ("enum", "multi_enum"):
                # We need to union all indices up to group max
                g_max = 0
                for g in registry.get("groups", []):
                    for gf in g.get("fields", []):
                        if gf.get("pattern") == rule.get("pattern"):
                            g_max = g.get("max", 0)
                
                ordered_union = []
                index_vocabs = {}
                for i in range(1, g_max + 1):
                    real_field = f_name.replace("{i}", str(i))
                    if real_field in specs:
                        ivocab = get_field_vocab(specs[real_field], rule, registry)
                        ivocab_symbols = [ivocab[str(c)] for c in ivocab if str(c) not in [str(x) for x in rule.get("suppress_codes", [])]]
                        for sym in ivocab_symbols:
                            if sym not in ordered_union:
                                ordered_union.append(sym)
                        index_vocabs[str(i)] = ivocab_symbols
                        
                attr["values"] = ordered_union
                exc = {}
                for idx, syms in index_vocabs.items():
                    missing = set(attr["values"]) - set(syms)
                    if missing:
                        exc[idx] = sorted(list(missing))
                if exc:
                    attr["index_exceptions"] = exc
                    
            if emit not in contract["event_types"][et]["attributes"]:
                contract["event_types"][et]["attributes"][emit] = attr
            else:
                # Merge feeds
                contract["event_types"][et]["attributes"][emit]["feeds"].extend(attr["feeds"])
                contract["event_types"][et]["attributes"][emit]["n_export_columns"] += attr["n_export_columns"]
                
            if "coverage_channels" in rule:
                for c in rule["coverage_channels"]:
                    if c not in contract["event_types"][et]["coverage_channels"]:
                        contract["event_types"][et]["coverage_channels"].append(c)

    for et, spec in contract["event_types"].items():
        for attr_name, attr in spec["attributes"].items():
            if "gated_by" in attr:
                try:
                    attr["gated_by"] = normalize_gate(attr["gated_by"], spec["attributes"])
                except Exception as e:
                    print(f"Error normalizing gate for {et}.{attr_name}: {e}")
                    sys.exit(1)
                    
    Path("generated").mkdir(exist_ok=True)
    Path("generated/extraction_contract.json").write_text(json.dumps(contract, indent=2))
    
    # Generate markdown
    md = ["# Extraction Contract\n"]
    for et, spec in contract["event_types"].items():
        md.append(f"## {et}")
        md.append(f"**Scope**: {spec['scope']}")
        if spec.get("boundary_mode"):
            md.append(f"**Boundary Mode**: {spec['boundary_mode']}")
            md.append(f"**Boundary Events**: {spec['boundary_events']}")
        md.append("")
        for a_name, a_spec in spec["attributes"].items():
            md.append(f"### {a_name}")
            md.append(f"- **Kind**: {a_spec['kind']}")
            if "values" in a_spec:
                md.append(f"- **Values**: {', '.join(str(v) for v in a_spec['values'])}")
            if "gated_by" in a_spec:
                md.append(f"- **Gated By**: {a_spec['gated_by']}")
        md.append("")
        
    Path("generated/extraction_contract.md").write_text("\n".join(md))
    print("Contract built.")

if __name__ == "__main__":
    main()
