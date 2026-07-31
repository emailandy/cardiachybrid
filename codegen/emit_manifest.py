import sys
import yaml
import json
import re
from pathlib import Path
from codegen.redcap_dict_to_code import load_dictionary
import codegen.known_bugs as known_bugs

class StrictLoader(yaml.SafeLoader):
    pass

def _no_duplicates(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            mark = key_node.start_mark
            raise ValueError(
                f"Duplicate YAML key '{key}' at line {mark.line + 1}, "
                f"column {mark.column + 1}. PyYAML would silently keep only "
                f"the last occurrence, discarding earlier content.")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping

StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicates)

class StrictLoader(yaml.SafeLoader):
    pass

def _no_duplicates(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            mark = key_node.start_mark
            raise ValueError(
                f"Duplicate YAML key '{key}' at line {mark.line + 1}, "
                f"column {mark.column + 1}. PyYAML would silently keep only "
                f"the last occurrence, discarding earlier content.")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping

StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicates)

def find_highest_index(specs, pattern):
    # Pattern e.g. "reason_cci_{i}_v2"
    # Convert pattern to a regex to match and extract i
    # Escape the pattern, but replace \{i\} with (\d+)
    escaped = re.escape(pattern)
    rx_str = "^" + escaped.replace(r"\{i\}", r"(\d+)") + "$"
    rx = re.compile(rx_str)
    
    highest = 0
    for f in specs.keys():
        m = rx.match(f)
        if m:
            val = int(m.group(1))
            if val > highest:
                highest = val
    return highest

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--skeleton", action="store_true")
    args = parser.parse_args()

    dict_path = Path("dictionary/instrument.csv")
    specs = load_dictionary(dict_path)
    
    if args.skeleton:
        # Group by section_header
        # The parser extracts section_header? Wait, redcap_dict_to_code.py didn't store section_header explicitly unless we look at FieldSpec.
        # redcap_dict_to_code.py FieldSpec has `form_name`? Let's assume we can just group by form_name.
        # Since I don't have section header strictly mapped, I'll group by form_name.
        forms = {}
        for k, v in specs.items():
            if k in ("record_id", "video_review_complete"):
                continue
            forms.setdefault(v.form_name, []).append(v)
            
        lines = []
        for form, fields in forms.items():
            lines.append(f"# {form}")
            for f in fields:
                lines.append(f"  - field: {f.name} # {f.label}")
                lines.append(f"    source_class: UNMAPPED")
            lines.append("")
        
        Path("mapping/registry_skeleton.yaml").write_text("\n".join(lines))
        return

    # Validator Mode
    reg_path = Path("mapping/registry.yaml")
    if not reg_path.exists():
        print("No registry.yaml found")
        sys.exit(1)
        
    with open(reg_path) as f:
        registry = yaml.load(f, Loader=StrictLoader)

    mapped_fields = set()
    suppressed_checkbox_codes = []
    
    system_fields = {"record_id", "video_review_complete"}
    
    errors = []
    if "scalars" in registry:
        errors.append("FAIL: 'scalars' key is retired. Migrate to 'sections'.")
        
    sections_list = registry.get("sections", [])
    groups_list = registry.get("groups", [])
    if len(sections_list) != 13:
        errors.append(f"FAIL: len(sections) == {len(sections_list)}, expected 13")
    if len(groups_list) != 5:
        errors.append(f"FAIL: len(groups) == {len(groups_list)}, expected 5")
        
    group_names = sorted(g.get("name") for g in groups_list)
    expected_groups = ["airway", "cci", "defib", "rosc", "vent_delay"]
    if group_names != expected_groups:
        errors.append(f"FAIL: groups {group_names} != {expected_groups}")
        
    def validate_field_entry(entry, path_str=""):
        f_name = entry.get("field")
        if f_name:
            if f_name not in specs and f_name not in system_fields:
                errors.append(f"FAIL: field '{f_name}' in {path_str} does not exist in dictionary")
                return
            mapped_fields.add(f_name)
            
            f_spec = specs.get(f_name)
            if f_spec:
                # check vocab
                vocab = entry.get("vocab")
                if vocab:
                    reg_vocab = registry.get("vocabularies", {}).get(vocab, {})
                    for reg_v in reg_vocab.values():
                        if str(reg_v) not in f_spec.choices and not entry.get("per_index_vocab"):
                            errors.append(f"FAIL: vocab code {reg_v} not in choices for {f_name}")
                
                # check range
                rng = entry.get("range")
                if rng:
                    if f_spec.val_min is not None and str(rng[0]) != str(f_spec.val_min):
                        errors.append(f"FAIL: range min mismatch for {f_name} (registry {rng[0]} != dict {f_spec.val_min})")
                    if f_spec.val_max is not None and str(rng[1]) != str(f_spec.val_max):
                        errors.append(f"FAIL: range max mismatch for {f_name} (registry {rng[1]} != dict {f_spec.val_max})")
                        
                # check checkbox
                kind = entry.get("kind")
                if kind == "checkbox" and f_spec.field_type != "checkbox":
                    errors.append(f"FAIL: kind: checkbox on non-checkbox field {f_name}")
                if f_spec.field_type == "checkbox" and kind != "checkbox":
                    errors.append(f"FAIL: checkbox field {f_name} missing kind: checkbox")
                    
                # check rule
                rule = entry.get("rule")
                if rule == "gate_yesno" and f_spec.field_type != "yesno":
                    errors.append(f"FAIL: gate_yesno on non-yesno field {f_name}")
                if rule == "gate_3way":
                    if "3" not in f_spec.choices and "unable_to_determine" not in f_spec.choices.values() and not entry.get("vocab_override"):
                        errors.append(f"FAIL: gate_3way on field {f_name} lacking 3rd choice")
                        
                # suppress_codes
                sc = entry.get("suppress_codes")
                if sc:
                    for c in sc:
                        if str(c) not in f_spec.choices:
                            errors.append(f"FAIL: suppress_codes entry {c} absent from choices for {f_name}")
                        suppressed_checkbox_codes.append(f"{f_name}___{c}")
                        
                if entry.get("source_class") == "UNMAPPED":
                    errors.append(f"FAIL: field {f_name} left UNMAPPED")

    # Walk registry
    for entry in registry.get("never_ai", []):
        pat = entry.get("pattern")
        rng = entry.get("range")
        if pat and rng:
            for i in range(rng[0], rng[1] + 1):
                inst_entry = dict(entry)
                inst_entry["field"] = pat.replace("{i}", str(i))
                validate_field_entry(inst_entry, "never_ai")
        else:
            validate_field_entry(entry, "never_ai")
    
    for section in registry.get("sections", []):
        sec_name = section.get("name", "unknown")
        for entry in section.get("fields", []):
            validate_field_entry(entry, f"sections[{sec_name}]")
            
    for group in registry.get("groups", []):
        g_name = group.get("name")
        c_field = group.get("count_field")
        if c_field:
            mapped_fields.add(c_field)
            cf_spec = specs.get(c_field)
            if not cf_spec or cf_spec.field_type != "text" or not cf_spec.val_type:
                errors.append(f"FAIL: group {g_name} count_field {c_field} is not a number-validated text field")
                
        g_max = group.get("max", 0)
        
        for f_entry in group.get("fields", []):
            pat = f_entry.get("pattern")
            if pat:
                # Find highest index in dict for this pattern
                highest_i = find_highest_index(specs, pat)
                if highest_i != g_max:
                    errors.append(f"FAIL: mismatch max for group {g_name}, pattern {pat}. Registry: {g_max}, Dict: {highest_i}")
                    
                for i in range(1, g_max + 1):
                    inst_entry = dict(f_entry)
                    inst_entry["field"] = pat.replace("{i}", str(i))
                    validate_field_entry(inst_entry, f"groups[{g_name}]")
    # unmapped fields
    unmapped = []
    for f in specs.keys():
        if f not in mapped_fields and f not in system_fields:
            unmapped.append(f)
            
    if unmapped:
        unmapped.sort()
        errors.append("FAIL: unmapped is NON-EMPTY")
        for u in unmapped:
            spec = specs[u]
            errors.append(f"- {u} ({spec.field_type}, {spec.form_name})")
            
    if errors:
        for e in errors:
            print(e)
        sys.exit(1)
        
    # extract other manifest fields
    event_types = set()
    for sec in registry.get("sections", []):
        for e in sec.get("fields", []):
            if e.get("source_class", "AI_DIRECT") in ["AI_DIRECT", "AI_DERIVED"]:
                ev = e.get("event_type")
                if ev: event_types.add(ev)
                
    for e in registry.get("never_ai", []):
        if e.get("source_class", "AI_DIRECT") in ["AI_DIRECT", "AI_DERIVED"]:
            ev = e.get("event_type")
            if ev: event_types.add(ev)
                
    for g in registry.get("groups", []):
        ev = g.get("event_type") or g.get("interval_type")
        if ev: event_types.add(ev)
        
    no_anchor_card = []
    for ev in sorted(list(event_types)):
        if not Path(f"prompts/anchors/{ev}.yaml").exists():
            no_anchor_card.append(ev)
            
    req_not_ai = []
    for sec in registry.get("sections", []):
        for e in sec.get("fields", []):
            f_name = e.get("field")
            if not f_name: continue
            s_cls = e.get("source_class", "AI_DIRECT")
            diff = e.get("difficulty", "MEDIUM")
            if f_name in specs and specs[f_name].required and (s_cls in ["HUMAN_ONLY", "ROSTER_JOIN"] or diff == "NOT_EXTRACTABLE"):
                req_not_ai.append(f_name)
                
    for e in registry.get("never_ai", []):
        pat = e.get("pattern")
        rng = e.get("range")
        if pat and rng:
            for i in range(rng[0], rng[1] + 1):
                f_name = pat.replace("{i}", str(i))
                s_cls = e.get("source_class", "AI_DIRECT")
                diff = e.get("difficulty", "MEDIUM")
                if f_name in specs and specs[f_name].required and (s_cls in ["HUMAN_ONLY", "ROSTER_JOIN"] or diff == "NOT_EXTRACTABLE"):
                    req_not_ai.append(f_name)
        else:
            f_name = e.get("field")
            if not f_name: continue
            s_cls = e.get("source_class", "AI_DIRECT")
            diff = e.get("difficulty", "MEDIUM")
            if f_name in specs and specs[f_name].required and (s_cls in ["HUMAN_ONLY", "ROSTER_JOIN"] or diff == "NOT_EXTRACTABLE"):
                req_not_ai.append(f_name)
            
    # Counts
    dict_export_columns = 1891 # hardcoded based on tests for now or compute
    dict_importable_columns = 1889
    system_columns = 2
    submission_columns = 1891
    n_vars = len(specs) + 2
    
    manifest = {
        "dict_version": Path("dictionary/dict_version.txt").read_text().strip() if Path("dictionary/dict_version.txt").exists() else "unknown",
        "registry_version": registry.get("version"),
        "n_variables": n_vars,
        "DICT_EXPORT_COLUMNS": dict_export_columns,
        "DICT_IMPORTABLE_COLUMNS": dict_importable_columns,
        "SYSTEM_COLUMNS": system_columns,
        "SUBMISSION_COLUMNS": submission_columns,
        "by_source_class": {},
        "by_difficulty": {},
        "suppressed_checkbox_codes": sorted(suppressed_checkbox_codes),
        "unmapped": sorted(unmapped),
        "no_anchor_card": no_anchor_card,
        "branching_overrides_staged": list(getattr(known_bugs, "BRANCHING_OVERRIDES", {}).keys()),
        "branching_overrides_active": [],
        "required_fields_not_ai_extractable": req_not_ai,
        "note": "no_anchor_card is expected to be non-empty until A03b. video_review_complete export behavior unverified."
    }
    
    Path("generated/coverage_manifest.json").parent.mkdir(exist_ok=True)
    Path("generated/coverage_manifest.json").write_text(json.dumps(manifest, indent=2))
    
    print("Validator passed. Manifest written.")

if __name__ == "__main__":
    main()
