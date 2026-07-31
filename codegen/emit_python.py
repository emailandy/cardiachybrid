import csv
import json
import hashlib
from pathlib import Path
from codegen.yamlio import load_yaml

def parse_choices(raw: str) -> dict[str, str]:
    if not raw: return {}
    choices = {}
    for part in raw.split("|"):
        if "," in part:
            code, label = part.split(",", 1)
            choices[code.strip()] = label.strip()
    return choices

def to_vocab_label(label: str) -> str:
    import re
    s = label.lower()
    if "not available" in s or "not applicable" in s:
        return "not_available"
    if "unable to determine" in s:
        return "unable_to_determine"
    s = re.sub(r'[^a-z0-9]+', '_', s).strip('_')
    if not s or s[0].isdigit():
        s = "code_" + s
    return s

def main():
    dict_version = Path("dictionary/dict_version.txt").read_text().strip()
    with open("dictionary/instrument.csv") as f:
        reader = csv.DictReader(f)
        dict_rows = list(reader)
        
    registry = load_yaml(Path("mapping/registry.yaml"))
        
    event_types_yaml = load_yaml(Path("mapping/event_types.yaml"))
        
    req_cats = ["redcap_feeding", "interval_boundary", "negative_control", "context"]
    all_event_types = set()
    for cat in req_cats:
        all_event_types.update(event_types_yaml.get(cat, []))
    all_event_types = sorted(list(all_event_types))

    export_columns = set()
    importable_columns = set()
    
    # Pre-parse registry
    reg_fields = {}
    
    def add_reg_field(pattern, info, repeat_group=None, repeat_index=None):
        reg_fields[pattern] = {
            "source_class": info.get("source_class", "AI_DIRECT"),
            "difficulty": info.get("difficulty", "MEDIUM"),
            "owning_event_types": tuple(info.get("owning_event_types", [])),
            "expected_utd_floor": info.get("expected_utd_floor", 0.0),
            "suppress_codes": tuple(info.get("suppress_codes", [])),
            "vocab": info.get("vocab"),
            "vocab_override": info.get("vocab_override"),
            "repeat_group": repeat_group,
            "repeat_index": repeat_index
        }

    for sec in registry.get("sections", []):
        for f in sec.get("fields", []):
            add_reg_field(f.get("field") or f.get("pattern"), f)
            
    for f in registry.get("never_ai", []):
        if "pattern" in f:
            for i in range(f["range"][0], f["range"][1] + 1):
                p = f["pattern"].replace("{i}", str(i))
                add_reg_field(p, f)
        else:
            add_reg_field(f["field"], f)
            
    repeat_groups = {}
    for g in registry.get("groups", []):
        count_field = g["count_field"]
        rg_max = g["max"]
        repeat_groups[g["name"]] = {
            "count_field": count_field,
            "max": rg_max,
            "fields": []
        }
        for f in g.get("fields", []):
            repeat_groups[g["name"]]["fields"].append(f["pattern"])
            for i in range(1, rg_max + 1):
                p = f["pattern"].replace("{i}", str(i))
                add_reg_field(p, f, repeat_group=g["name"], repeat_index=i)

    fields_spec = {}
    vocab = {}
    
    for row in dict_rows:
        field_name = row["Variable / Field Name"]
        if field_name in ("record_id", "video_review_complete"):
            continue
            
        ftype = row["Field Type"]
        
        # Calculate export columns
        if ftype not in ("descriptive", "file"):
            if ftype == "checkbox":
                choices = parse_choices(row["Choices, Calculations, OR Slider Labels"])
                for code in choices:
                    export_columns.add(f"{field_name}___{code}")
                    importable_columns.add(f"{field_name}___{code}")
            else:
                export_columns.add(field_name)
                if ftype != "calc":
                    importable_columns.add(field_name)
                    
        # Registry info
        reg = reg_fields.get(field_name, {})
        
        vocab_name = reg.get("vocab_override") or reg.get("vocab")
        
        # Add to vocab
        if ftype in ("checkbox", "radio", "dropdown"):
            choices = parse_choices(row["Choices, Calculations, OR Slider Labels"])
            v = {}
            if vocab_name and vocab_name in registry.get("vocabularies", {}):
                # Use registry vocab verbatim (invert keys/values)
                reg_vocab = registry["vocabularies"][vocab_name]
                for key, val in reg_vocab.items():
                    v[str(key)] = int(val)
            else:
                # Fallback to normalizer
                for code, label in choices.items():
                    v[to_vocab_label(label)] = int(code)
            vocab[field_name] = v
        
        
        # Parse choices explicitly
        raw_choices = row["Choices, Calculations, OR Slider Labels"]
        if ftype == "yesno":
            parsed_choices = {"1": "Yes", "0": "No"}
        elif ftype == "truefalse":
            parsed_choices = {"1": "True", "0": "False"}
        else:
            parsed_choices = parse_choices(raw_choices)
            
        fields_spec[field_name] = {
            "field_name": field_name,
            "form_name": row["Form Name"],
            "field_type": ftype,
            "field_label": row["Field Label"],
            "section_header": row["Section Header"],
            "field_note": row["Field Note"],
            "choices": parsed_choices,
            "validation": row["Text Validation Type OR Show Slider Number"],
            "py_type": "str", # Simplified for stub
            "api_format": "str", # Simplified for stub
            "value_regex": "", # Simplified
            "val_min": row["Text Validation Min"],
            "val_max": row["Text Validation Max"],
            "branching_raw": row["Branching Logic (Show field only if...)"],
            "required": row["Required Field?"] == "y",
            "identifier": row["Identifier?"] == "y",
            "annotation": row["Field Annotation"],
            "export_columns": tuple(
                (f"{field_name}___{code}" for code in parse_choices(row["Choices, Calculations, OR Slider Labels"]))
                if ftype == "checkbox" else (field_name,)
            ),
            "server_computed": ftype == "calc",
            "carries_data": ftype not in ("descriptive",),
            "source_class": reg.get("source_class", "HUMAN_ONLY"),
            "difficulty": reg.get("difficulty", "MEDIUM"),
            "owning_event_types": reg.get("owning_event_types", ()),
            "expected_utd_floor": reg.get("expected_utd_floor", 0.0),
            "suppress_codes": reg.get("suppress_codes", ()),
            "repeat_group": reg.get("repeat_group", None),
            "repeat_index": reg.get("repeat_index", None)
        }

    system_columns = {"record_id", "video_review_complete"}
    submission_columns = importable_columns | system_columns

    # Write generated/redcap_fields.py
    out_redcap = []
    out_redcap.append('"""\nDO NOT EDIT.\nGenerated module.\n"""')
    out_redcap.append(f'_DICT_SHA = {dict_version!r}\n')
    
    out_redcap.append('from dataclasses import dataclass')
    out_redcap.append('from typing import Literal\n')
    
    out_redcap.append('@dataclass(slots=True, frozen=True)')
    out_redcap.append('class FieldSpec:')
    out_redcap.append('    field_name: str')
    out_redcap.append('    form_name: str')
    out_redcap.append('    field_type: str')
    out_redcap.append('    field_label: str')
    out_redcap.append('    section_header: str')
    out_redcap.append('    field_note: str')
    out_redcap.append('    choices: dict[str, str]')
    out_redcap.append('    validation: str')
    out_redcap.append('    py_type: str')
    out_redcap.append('    api_format: str')
    out_redcap.append('    value_regex: str')
    out_redcap.append('    val_min: str')
    out_redcap.append('    val_max: str')
    out_redcap.append('    branching_raw: str')
    out_redcap.append('    required: bool')
    out_redcap.append('    identifier: bool')
    out_redcap.append('    annotation: str')
    out_redcap.append('    export_columns: tuple[str, ...]')
    out_redcap.append('    server_computed: bool')
    out_redcap.append('    carries_data: bool')
    out_redcap.append('    source_class: str')
    out_redcap.append('    difficulty: str')
    out_redcap.append('    owning_event_types: tuple[str, ...]')
    out_redcap.append('    expected_utd_floor: float')
    out_redcap.append('    suppress_codes: tuple[str, ...]')
    out_redcap.append('    repeat_group: str | None')
    out_redcap.append('    repeat_index: int | None\n')

    out_redcap.append(f"EXPORT_COLUMNS = frozenset({sorted(list(export_columns))!r})")
    out_redcap.append(f"IMPORTABLE_COLUMNS = frozenset({sorted(list(importable_columns))!r})")
    out_redcap.append(f"SYSTEM_COLUMNS = frozenset({sorted(list(system_columns))!r})")
    out_redcap.append(f"SUBMISSION_COLUMNS = frozenset({sorted(list(submission_columns))!r})\n")
    
    out_redcap.append("REPEAT_GROUPS = " + repr(repeat_groups) + "\n")
    out_redcap.append("VOCAB = " + repr(vocab) + "\n")
    
    out_redcap.append("FIELDS = {")
    for k in sorted(fields_spec.keys()):
        v = fields_spec[k]
        args = ", ".join(f"{fk}={fv!r}" for fk, fv in v.items())
        out_redcap.append(f"    {k!r}: FieldSpec({args}),")
    out_redcap.append("}\n")
    
    Path("generated/redcap_fields.py").write_text("\n".join(out_redcap))

    # Write generated/models.py
    out_models = []
    out_models.append('"""\nDO NOT EDIT.\nGenerated module.\n"""')
    out_models.append(f'_DICT_SHA = {dict_version!r}\n')
    out_models.append('from pydantic import BaseModel, ConfigDict, Field')
    out_models.append('from typing import Literal, Any\n')
    
    event_type_literals = ", ".join(repr(e) for e in all_event_types)
    out_models.append(f"EventType = Literal[{event_type_literals}]\n")
    
    out_models.append("class Evidence(BaseModel):")
    out_models.append("    timestamp_s: float | None = None")
    out_models.append("    duration_s: float | None = None")
    out_models.append("    text: str | None = None")
    out_models.append("    attributes: dict[str, Any] | None = None\n")
    
    out_models.append("class Event(BaseModel):")
    out_models.append("    type: EventType")
    out_models.append("    timestamp_s: float")
    out_models.append("    attributes: dict[str, Any]")
    out_models.append("    evidence: list[Evidence]\n")

    out_models.append("class Interval(BaseModel):")
    out_models.append("    type: str")
    out_models.append("    t_start_s: float")
    out_models.append("    t_end_s: float | None = None")
    out_models.append("    attributes: dict[str, Any]\n")

    out_models.append("class CoverageNote(BaseModel):")
    out_models.append("    type: str")
    out_models.append("    text: str\n")

    out_models.append("class CaseFields(BaseModel):")
    out_models.append("    model_config = ConfigDict(extra='allow')\n")

    out_models.append("class EventStream(BaseModel):")
    out_models.append("    case_id: str")
    out_models.append("    events: list[Event]")
    out_models.append("    intervals: list[Interval]")
    out_models.append("    coverage: list[CoverageNote]")
    out_models.append("    fields: CaseFields\n")
    
    Path("generated/models.py").write_text("\n".join(out_models))

if __name__ == "__main__":
    main()
