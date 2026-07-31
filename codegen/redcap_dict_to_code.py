"""
Parses a REDCap Data Dictionary CSV into typed FieldSpec objects.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# Exception to I2: Structural regexes enumerating field-name prefixes
# to identify repeating groups. These are structural patterns, not field names.
REPEAT_PATTERNS = [
    # CCI sub-fields with NO _v2 suffix
    re.compile(r"^(sono_window_cci|echo_success_cci|us_pulse_cci|us_pulse_present_cci|aline_cci|aline_sbp_cci|aline_dbp_cci|loc_pulse_check_cci)_(\d+)$"),
    # CCI sub-fields with _v2 suffix
    re.compile(r"^([a-z0-9_]+_cci)_(\d+)_v2$")
]

VALID_VALIDATION_TYPES = {
    "integer", "number", "datetime_seconds_mdy", "date_mdy", "date_dmy", "date_ymd",
    "datetime_mdy", "datetime_dmy", "datetime_ymd", "email", "phone", "time", "number_1dp",
    "time_mm_ss", "signature", "zipcode", "alpha_only"
}

@dataclass
class FieldSpec:
    name: str
    field_type: str
    label: str
    choices: Dict[str, str] = field(default_factory=dict)
    server_computed: bool = False
    carries_data: bool = True
    repeat_group: Optional[str] = None
    repeat_index: Optional[int] = None
    export_columns: List[str] = field(default_factory=list)
    val_type: str = ""
    val_min: Optional[str] = None
    val_max: Optional[str] = None
    form_name: str = ""
    required: bool = False

def dict_hash(path: Path) -> str:
    """Must match scripts/hash_dict.sh: first 16 hex of sha256."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]

def sanitize_choice_code(code: str) -> str:
    code = code.lower()
    return re.sub(r"[^a-z0-9_]", "_", code)

def parse_choices(choices_str: str, line_num: int) -> Dict[str, str]:
    if not choices_str or not choices_str.strip():
        return {}
    choices = {}
    for part in choices_str.split("|"):
        part = part.strip()
        if not part:
            continue
        if "," in part:
            code, label = part.split(",", 1)
            code = code.strip()
            label = label.strip()
        else:
            code = part.strip()
            label = part.strip()
            
        if code in choices:
            raise ValueError(f"Line {line_num}: duplicate choice code '{code}'")
        choices[code] = label
    return choices

def implicit_choices(field_type: str) -> Dict[str, str]:
    if field_type == "yesno":
        return {"1": "Yes", "0": "No"}
    if field_type == "truefalse":
        return {"1": "True", "0": "False"}
    return {}

def strip_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text)

def tag_repeats(name: str) -> tuple[Optional[str], Optional[int]]:
    # Singletons that look like repeats but are not
    if name in ["decision_time_thromb_ed", "time_ecmo_called", "time_ecmo_initiated", "time_ecmo_success"]:
        return None, None
        
    for pattern in REPEAT_PATTERNS:
        match = pattern.match(name)
        if match:
            return "cci", int(match.group(2))
    return None, None

def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())

def load_dictionary(path: Path) -> Dict[str, FieldSpec]:
    raw = path.read_bytes().decode("utf-8-sig")
    try:
        dialect = csv.Sniffer().sniff(raw[:8192], delimiters=",\t")
    except csv.Error:
        dialect = csv.excel
        
    rdr = csv.DictReader(io.StringIO(raw), dialect=dialect)
    if not rdr.fieldnames or len(rdr.fieldnames) < 10:
        rdr = csv.DictReader(io.StringIO(raw), dialect=csv.excel)
        
    fieldnames = rdr.fieldnames
    if not fieldnames:
        return {}
        
    slug_to_header = {slugify(h): h for h in fieldnames}
    
    def get_val(row: Dict[str, str], slug: str) -> str:
        orig = slug_to_header.get(slug)
        if not orig:
            return ""
        return row[orig]

    specs: Dict[str, FieldSpec] = {}
    export_cols_seen = set()
    valid_name_re = re.compile(r"^[a-z_][a-z0-9_]*$")
    
    line_num = 1
    for row in rdr:
        line_num += 1
        name = get_val(row, "variablefieldname")
        if not name:
            name = get_val(row, "field_name") or get_val(row, "variablename")
            
        if not name:
            continue
            
        if not valid_name_re.match(name):
            raise ValueError(f"Line {line_num}: invalid variable name '{name}'")
            
        if name in specs:
            raise ValueError(f"Line {line_num}: duplicate field name '{name}'")
            
        val_type = get_val(row, "textvalidationtypeorshowslidernumber").strip()
        if val_type and val_type not in VALID_VALIDATION_TYPES:
            raise ValueError(f"Line {line_num}: unknown validation type '{val_type}'")
            
        val_min = get_val(row, "textvalidationmin").strip() or None
        val_max = get_val(row, "textvalidationmax").strip() or None
        form_name = get_val(row, "formname").strip() or get_val(row, "form_name").strip()
        required = get_val(row, "requiredfield").strip().lower() == "y"
            
        field_type = get_val(row, "fieldtype").strip()
        label = strip_html(get_val(row, "fieldlabel"))
        
        # choicescalculationsorsliderlabels OR choicescalculationsorridersliderlabels
        choices_str = get_val(row, "choicescalculationsorsliderlabels")
        if not choices_str:
            choices_str = get_val(row, "choicescalculationsorridersliderlabels")
            
        if field_type in ("calc", "slider"):
            choices = {}
        else:
            choices = parse_choices(choices_str, line_num)
            
        if not choices:
            choices = implicit_choices(field_type)
            
        server_computed = (field_type == "calc")
        carries_data = (field_type != "descriptive")
        
        export_columns = []
        if carries_data:
            if field_type == "checkbox":
                for code in choices.keys():
                    col = f"{name}___{sanitize_choice_code(code)}"
                    if col in export_cols_seen:
                        raise ValueError(f"Line {line_num}: export column collision '{col}'")
                    export_cols_seen.add(col)
                    export_columns.append(col)
            else:
                if name in export_cols_seen:
                    raise ValueError(f"Line {line_num}: export column collision '{name}'")
                export_cols_seen.add(name)
                export_columns.append(name)
                
        rep_group, rep_idx = tag_repeats(name)
        
        specs[name] = FieldSpec(
            name=name,
            field_type=field_type,
            label=label,
            choices=choices,
            server_computed=server_computed,
            carries_data=carries_data,
            repeat_group=rep_group,
            repeat_index=rep_idx,
            export_columns=export_columns,
            val_type=val_type,
            val_min=val_min,
            val_max=val_max,
            form_name=form_name,
            required=required
        )
        
    return specs

def main() -> None:
    raise NotImplementedError("codegen.redcap_dict_to_code is a stub. See docs/tasks/D01.md")

if __name__ == "__main__":
    main()
