"""
Prompts registry for resus_qc.
"""

from pathlib import Path
import json
import hashlib
import re
from codegen.yamlio import load_yaml

def assert_no_field_names(text: str, where: str) -> None:
    """A05's builder calls this on every assembled prompt. A01 provides it
    and applies it to anchor cards at load time."""
    from generated.redcap_fields import EXPORT_COLUMNS
    hits = sorted(c for c in EXPORT_COLUMNS if c in text)
    if hits:
        raise ValueError(
            f"{where}: leaks REDCap field names into prompt text: "
            f"{hits[:5]}{'...' if len(hits) > 5 else ''}")

def manifest() -> dict:
    versions_path = Path("prompts/VERSIONS.yaml")
    data = load_yaml(versions_path)
    
    dict_ver_path = Path("dictionary/dict_version.txt")
    current_dict_version = dict_ver_path.read_text().strip() if dict_ver_path.exists() else ""
    if current_dict_version != data.get("requires_dict_version"):
        raise ValueError(f"VERSIONS.yaml requires dict_version {data.get('requires_dict_version')}, but current is {current_dict_version}")
        
    return data

def load(key: str) -> str:
    m = manifest()
    # Resolve the key through the manifest
    path_str = None
    if key in m:
        path_str = m[key]
    else:
        # Check sub-dictionaries
        for sub in ["pass_templates", "fragments", "team_anchors"]:
            if key in m.get(sub, {}):
                path_str = m[sub][key]
                break
    
    if not path_str:
        raise KeyError(f"Key {key} not found in manifest")
        
    file_path = Path(path_str)
    return file_path.read_text()

def anchor(event_type: str) -> str:
    m = manifest()
    anchors_dir = Path(m.get("anchors_dir", "prompts/anchors"))
    card_path = anchors_dir / f"{event_type}.yaml"
    
    if not card_path.exists():
        raise KeyError(f"Anchor card for {event_type} not found at {card_path}")
        
    text = card_path.read_text()
    assert_no_field_names(text, f"anchor card {event_type}")
    return text

def manifest_sha() -> str:
    versions_path = Path("prompts/VERSIONS.yaml")
    if not versions_path.exists():
        return ""
    text = versions_path.read_text()
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]

def prompt_set_sha(strict: bool = True) -> str:
    """Hash of the full active set: system prompt, all six pass templates,
    all fragments, all 39 anchor cards. This value is logged to dim_run and
    is what makes a six-month-old record reproducible.
    strict=True (default) RAISES if any referenced file is missing, listing
    every one. Only A06+ can call it successfully. There is no partial
    mode — a partial hash is a lie about reproducibility."""
    m = manifest()
    paths_to_hash = []
    
    if "system_prompt" in m:
        paths_to_hash.append(Path(m["system_prompt"]))
        
    for k, v in m.get("pass_templates", {}).items():
        paths_to_hash.append(Path(v))
        
    for k, v in m.get("fragments", {}).items():
        paths_to_hash.append(Path(v))
        
    cov_path = Path("generated/coverage_manifest.json")
    if cov_path.exists():
        et_path = Path("mapping/event_types.yaml")
        if et_path.exists():
            et_data = load_yaml(et_path)
            req_types = []
            for cat in ["redcap_feeding", "interval_boundary", "negative_control", "context"]:
                req_types.extend(et_data.get(cat, []))
            
            anchors_dir = Path(m.get("anchors_dir", "prompts/anchors"))
            for t in req_types:
                paths_to_hash.append(anchors_dir / f"{t}.yaml")
            
    missing_files = []
    for p in paths_to_hash:
        if not p.exists():
            missing_files.append(str(p))
            
    if strict and missing_files:
        raise FileNotFoundError(f"prompt_set_sha(strict=True) failed. Missing {len(missing_files)} files:\n" + "\n".join(missing_files))
        
    h = hashlib.sha256()
    # Hash VERSIONS.yaml itself too
    h.update(Path("prompts/VERSIONS.yaml").read_text().encode('utf-8'))
    
    if not missing_files:
        for p in sorted(paths_to_hash):
            h.update(p.read_text().encode('utf-8'))
            
    return h.hexdigest()[:16]

def check_anchors(types=None, fail_on_gap: bool = True) -> dict[str, dict[str, list[str]]]:
    """Returns {event_type: {attr: [uncovered reasons]}}.
    fail_on_gap=False during A01-A03; A03b's acceptance flipped it True.
    Gaps are reported against generated/extraction_contract.json — every
    card as a detailed mapping.
    
    check_anchors() proves structural coverage only. It cannot validate
    clinical accuracy. Anchor card content requires human clinical review
    before the first production run — see docs/CLINICAL_REVIEW_QUEUE.md."""
    
    contract_path = Path("generated/extraction_contract.json")
    if not contract_path.exists():
        return {}
        
    contract = json.loads(contract_path.read_text())
    event_types = contract.get("event_types", {})
    
    types_to_check = types if types is not None else list(event_types.keys())
    
    schema_path = Path("prompts/anchors/_SCHEMA.yaml")
    required_keys = []
    if schema_path.exists():
        schema = load_yaml(schema_path)
        required_keys = schema.get("required_keys", [])
        
    m = manifest()
    anchors_dir = Path(m.get("anchors_dir", "prompts/anchors"))
    
    gaps = {}
    
    for t in types_to_check:
        card_path = anchors_dir / f"{t}.yaml"
        if not card_path.exists():
            gaps[t] = {"_card": ["<no anchor card>"]}
            continue
            
        card_yaml = load_yaml(card_path)
        type_gaps = {}
        
        for key in required_keys:
            if key not in card_yaml:
                type_gaps.setdefault("_schema", []).append(f"Missing schema key: {key}")
                
        req_attrs = card_yaml.get("required_attributes", {})
        is_mapping = isinstance(req_attrs, dict)
        
        contract_attrs = event_types.get(t, {}).get("attributes", {})
        for attr_name, contract_attr in contract_attrs.items():
            if attr_name in ("t_start_s", "t_end_s") or contract_attr.get("kind") == "timestamp":
                continue
            attr_reasons = []
            if not is_mapping or attr_name not in req_attrs:
                attr_reasons.append("absent from required_attributes mapping")
            else:
                card_attr = req_attrs[attr_name]
                if not isinstance(card_attr, dict):
                    attr_reasons.append("attribute entry is not a mapping")
                else:
                    how = card_attr.get("how_to_determine", "")
                    if not how or len(str(how).strip()) < 40:
                        attr_reasons.append("how_to_determine missing, empty, or under 40 characters")
                        
                    kind = contract_attr.get("kind")
                    if kind in ("enum", "multi_enum"):
                        c_vals = set(contract_attr.get("values", []))
                        a_vals = set(card_attr.get("values", []))
                        if "values" not in card_attr or a_vals != c_vals:
                            attr_reasons.append(f"enum values mismatch: card {sorted([str(x) for x in a_vals])} != contract {sorted([str(x) for x in c_vals])}")
                            
                    if "gated_by" in contract_attr:
                        if "gate" not in card_attr:
                            attr_reasons.append(f"contract declares gate ({contract_attr['gated_by']}) but card omits it")
                            
                    if "detector_hint" in contract_attr:
                        if "source" not in card_attr:
                            attr_reasons.append(f"contract declares detector hint ({contract_attr['detector_hint']}) but card omits source")
                            
                    if contract_attr.get("difficulty") == "HIGH":
                        abstain = card_attr.get("abstain_if", "")
                        if not abstain or not str(abstain).strip():
                            attr_reasons.append("difficulty is HIGH and abstain_if is missing")
                            
            if attr_reasons:
                type_gaps[attr_name] = attr_reasons
                
        if type_gaps:
            gaps[t] = type_gaps
            
    if fail_on_gap and gaps:
        raise ValueError(f"Anchor card gaps detected:\n{json.dumps(gaps, indent=2)}")
        
    return gaps

def validate_template_placeholders(template_text: str, pass_name: str) -> None:
    """Validates that template_text uses exactly the placeholders declared in
    prompts/passes/_PLACEHOLDERS.yaml under pass_name.
    Raises ValueError if there is an undeclared placeholder or an unused declared placeholder.
    """
    placeholders_path = Path("prompts/passes/_PLACEHOLDERS.yaml")
    if not placeholders_path.exists():
        raise FileNotFoundError(f"Missing {placeholders_path}")
    data = load_yaml(placeholders_path)
    if pass_name not in data:
        raise KeyError(f"Pass {pass_name} not found in _PLACEHOLDERS.yaml")
    
    declared = set(data[pass_name].keys())
    used = set(re.findall(r'\{([a-zA-Z0-9_]+)\}', template_text))
    
    undeclared = used - declared
    if undeclared:
        raise ValueError(f"Template for {pass_name} uses undeclared placeholders: {sorted(undeclared)}")
        
    unused = declared - used
    if unused:
        raise ValueError(f"Template for {pass_name} declares unused placeholders: {sorted(unused)}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "prompt-set-sha":
        try:
            print(prompt_set_sha())
        except Exception as e:
            print(str(e))
            sys.exit(1)
    elif len(sys.argv) > 1 and sys.argv[1] == "check-anchors":
        types = None
        if "--types" in sys.argv:
            idx = sys.argv.index("--types")
            types = sys.argv[idx + 1:]
        gaps = check_anchors(types=types)
        if gaps:
            print(json.dumps(gaps, indent=2))
            sys.exit(1)
        else:
            print("0 uncovered")
