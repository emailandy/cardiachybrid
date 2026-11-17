"""
Emits generated/aicares_fields.py and generated/aicares_branching.py
from dictionary/aicares_instrument.csv and mapping/aicares_registry.yaml.
"""
from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from pathlib import Path

from codegen.branching import compile_predicate
from codegen.emit_python import parse_choices, to_vocab_label
from codegen.redcap_dict_to_code import load_dictionary
from codegen.yamlio import load_yaml


def emit_aicares_fields(dict_path: Path, dict_version: str, registry: dict) -> None:
    with open(dict_path, encoding="utf-8-sig") as f:
        dict_rows = list(csv.DictReader(f))

    export_columns: set[str] = set()
    importable_columns: set[str] = set()
    reg_fields: dict[str, dict] = {}

    def add_reg_field(pattern: str, info: dict, repeat_group: str | None = None, repeat_index: int | None = None) -> None:
        reg_fields[pattern] = {
            "source_class": info.get("source_class", "AI_DIRECT"),
            "difficulty": info.get("difficulty", "MEDIUM"),
            "owning_event_types": tuple(info.get("owning_event_types", [])),
            "expected_utd_floor": info.get("expected_utd_floor", 0.0),
            "suppress_codes": tuple(info.get("suppress_codes", [])),
            "vocab": info.get("vocab"),
            "vocab_override": info.get("vocab_override"),
            "repeat_group": repeat_group,
            "repeat_index": repeat_index,
        }

    for sec in registry.get("sections", []):
        for f_info in sec.get("fields", []):
            add_reg_field(f_info.get("field") or f_info.get("pattern"), f_info)

    for f_info in registry.get("never_ai", []):
        if "pattern" in f_info:
            for i in range(f_info["range"][0], f_info["range"][1] + 1):
                p = f_info["pattern"].replace("{i}", str(i))
                add_reg_field(p, f_info)
        else:
            add_reg_field(f_info["field"], f_info)

    fields_spec: dict[str, dict] = {}
    vocab: dict[str, dict[str, int]] = {}

    for row in dict_rows:
        field_name = row["Variable / Field Name"].strip()
        if not field_name:
            continue
        ftype = row["Field Type"].strip()

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

        reg = reg_fields.get(field_name, {})
        vocab_name = reg.get("vocab_override") or reg.get("vocab")

        if ftype in ("checkbox", "radio", "dropdown"):
            choices = parse_choices(row["Choices, Calculations, OR Slider Labels"])
            v: dict[str, int] = {}
            if vocab_name and vocab_name in registry.get("vocabularies", {}):
                reg_vocab = registry["vocabularies"][vocab_name]
                for key, val in reg_vocab.items():
                    v[str(key)] = int(val)
            else:
                for code, label in choices.items():
                    v[to_vocab_label(label)] = int(code)
            vocab[field_name] = v

        raw_choices = row["Choices, Calculations, OR Slider Labels"]
        if ftype == "yesno":
            parsed_choices = {"1": "Yes", "0": "No"}
        elif ftype == "truefalse":
            parsed_choices = {"1": "True", "0": "False"}
        elif ftype in ("calc", "slider"):
            parsed_choices = {}
        else:
            parsed_choices = parse_choices(raw_choices)

        val_type = row["Text Validation Type OR Show Slider Number"].strip()
        value_regex = r"^\d{2}:\d{2}$" if val_type == "time_mm_ss" else ""

        fields_spec[field_name] = {
            "field_name": field_name,
            "form_name": row["Form Name"].strip(),
            "field_type": ftype,
            "field_label": row["Field Label"].strip(),
            "section_header": row["Section Header"].strip(),
            "field_note": row["Field Note"].strip(),
            "choices": parsed_choices,
            "validation": val_type,
            "py_type": "str",
            "api_format": "str",
            "value_regex": value_regex,
            "val_min": row["Text Validation Min"].strip(),
            "val_max": row["Text Validation Max"].strip(),
            "branching_raw": row["Branching Logic (Show field only if...)"].strip(),
            "required": row["Required Field?"].strip().lower() == "y",
            "identifier": row["Identifier?"].strip().lower() == "y",
            "annotation": row["Field Annotation"].strip(),
            "export_columns": tuple(
                (f"{field_name}___{code}" for code in parse_choices(raw_choices))
                if ftype == "checkbox"
                else (() if ftype == "descriptive" else (field_name,))
            ),
            "server_computed": ftype == "calc",
            "carries_data": ftype not in ("descriptive",),
            "source_class": reg.get("source_class", "HUMAN_ONLY"),
            "difficulty": reg.get("difficulty", "MEDIUM"),
            "owning_event_types": reg.get("owning_event_types", ()),
            "expected_utd_floor": reg.get("expected_utd_floor", 0.0),
            "suppress_codes": reg.get("suppress_codes", ()),
            "repeat_group": reg.get("repeat_group", None),
            "repeat_index": reg.get("repeat_index", None),
        }

    system_columns = {"record_id", "technical_skills_review_ai_complete", "teams_review_ai_complete"}
    submission_columns = importable_columns | system_columns

    out_lines = [
        '"""',
        "DO NOT EDIT.",
        "Generated AI-CARES REDCap field specifications (IRB #25-1097).",
        '"""',
        f"_DICT_SHA = {dict_version!r}\n",
        "from generated.redcap_fields import FieldSpec\n",
        f"EXPORT_COLUMNS = frozenset({sorted(list(export_columns))!r})",
        f"IMPORTABLE_COLUMNS = frozenset({sorted(list(importable_columns))!r})",
        f"SYSTEM_COLUMNS = frozenset({sorted(list(system_columns))!r})",
        f"SUBMISSION_COLUMNS = frozenset({sorted(list(submission_columns))!r})\n",
        "REPEAT_GROUPS: dict = {}\n",
        "VOCAB = " + repr(vocab) + "\n",
        "FIELDS = {",
    ]
    for k in sorted(fields_spec.keys()):
        v = fields_spec[k]
        args = ", ".join(f"{fk}={fv!r}" for fk, fv in v.items())
        out_lines.append(f"    {k!r}: FieldSpec({args}),")
    out_lines.append("}\n")

    out_path = Path("generated/aicares_fields.py")
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text("\n".join(out_lines), encoding="utf-8")


def emit_aicares_branching(dict_path: Path) -> None:
    specs = load_dictionary(dict_path)
    raw = dict_path.read_bytes().decode("utf-8-sig")
    rdr = csv.DictReader(io.StringIO(raw), dialect=csv.excel)

    def slugify(text: str) -> str:
        return re.sub(r"[^a-z0-9]", "", text.lower())

    slug_to_header = {slugify(h): h for h in (rdr.fieldnames or [])}
    bl_header = slug_to_header["branchinglogicshowfieldonlyif"]
    name_header = slug_to_header["variablefieldname"]

    unknown_refs: dict[str, list[str]] = defaultdict(list)
    ref_re = re.compile(r"\[([a-zA-Z_][a-zA-Z0-9_]*)(?:\([^)]+\))?\]")

    out_lines = [
        "# generated/aicares_branching.py",
        "# DO NOT EDIT - Generated by emit_aicares.py",
        "from typing import Callable, Dict, Any",
        "from generated.branching_compiled import _truthy, _cmp, _v, _cb",
        "",
        "PREDICATES: Dict[str, Callable[[Dict[str, str]], bool]] = {}",
    ]

    for row in rdr:
        name = row[name_header].strip()
        if not name:
            continue
        logic = row[bl_header].strip()
        if not logic:
            continue

        for m in ref_re.finditer(logic):
            ref = m.group(1).lower()
            if ref not in specs:
                unknown_refs[ref].append(name)

        pred = compile_predicate(logic)
        out_lines.append(f"\n# {name}: {logic}")
        out_lines.append(f"def _pred_{name}(record: Dict[str, str]) -> bool:")
        out_lines.append(f"    return bool(_truthy( {pred.source} ))")
        out_lines.append(f"PREDICATES[{name!r}] = _pred_{name}")

    for ref, users in unknown_refs.items():
        print(f"WARNING: Unknown field {ref!r} referenced in AI-CARES branching logic of {', '.join(users)}")

    out_path = Path("generated/aicares_branching.py")
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


def main() -> None:
    dict_path = Path("dictionary/aicares_instrument.csv")
    dict_version = Path("dictionary/aicares_dict_version.txt").read_text(encoding="utf-8").strip()
    registry = load_yaml(Path("mapping/aicares_registry.yaml"))
    emit_aicares_fields(dict_path, dict_version, registry)
    emit_aicares_branching(dict_path)


if __name__ == "__main__":
    main()
