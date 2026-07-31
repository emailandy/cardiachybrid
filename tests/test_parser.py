import pytest
from pathlib import Path
import tempfile
import io
import csv

from codegen.redcap_dict_to_code import (
    sanitize_choice_code, 
    implicit_choices,
    parse_choices,
    tag_repeats,
    dict_hash,
    load_dictionary,
    FieldSpec
)

# 1. sanitize_choice_code("-1") → "_1" → column "field____1"
def test_sanitize_choice_code():
    code = "-1"
    sanitized = sanitize_choice_code(code)
    assert sanitized == "_1"
    # test column construction
    col = f"field___{sanitized}"
    assert col == "field____1"

# 2. yesno choices == {"1":"Yes","0":"No"}. Never 1/2.
def test_yesno_choices():
    s = load_dictionary(Path('dictionary/instrument.csv'))
    for f in s.values():
        if f.field_type == "yesno":
            assert f.choices == {"1": "Yes", "0": "No"}, f"Field {f.name} failed yesno choice assert"

# 3. Choice parsing splits on the FIRST comma only.
def test_choice_parsing_first_comma():
    val = "3, Dual defibrillation (two sets of pads were used in anterolateral, and anteroposterior locations)"
    res = parse_choices(val, 1)
    assert res == {"3": "Dual defibrillation (two sets of pads were used in anterolateral, and anteroposterior locations)"}

# 4. tag_repeats handles BOTH CCI patterns
def test_tag_repeats_cci():
    # 7 subfields without _v2 suffix (actually 8 are listed in the task)
    for prefix in ["sono_window_cci", "echo_success_cci", "us_pulse_cci", "us_pulse_present_cci", "aline_cci", "aline_sbp_cci", "aline_dbp_cci", "loc_pulse_check_cci"]:
        group, idx = tag_repeats(f"{prefix}_3")
        assert group == "cci", f"Failed for {prefix}_3"
        assert idx == 3
    # Subfields with _v2 suffix
    group, idx = tag_repeats("reason_cci_1_v2")
    assert group == "cci"
    assert idx == 1

# 5. Every raised ValueError includes the CSV line number.
def test_value_error_line_number():
    bad_csv = """Variable / Field Name,Field Type,Text Validation Type OR Show Slider Number
invalid-name,text,
valid_name,text,unknown_val
"""
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv") as f:
        f.write(bad_csv)
        path = Path(f.name)
        
    try:
        with pytest.raises(ValueError, match="Line 2: invalid variable name 'invalid-name'"):
            load_dictionary(path)
    finally:
        path.unlink()

# 6. tag_repeats leaves singletons alone
def test_tag_repeats_singletons():
    singletons = ["decision_time_thromb_ed", "time_ecmo_called", "time_ecmo_initiated", "time_ecmo_success"]
    for s in singletons:
        group, idx = tag_repeats(s)
        assert group is None
        assert idx is None

# 7. dict_hash() equals the contents of dictionary/dict_version.txt
def test_dict_hash_matches_shell():
    assert dict_hash(Path("dictionary/instrument.csv")) == Path("dictionary/dict_version.txt").read_text().strip()

def test_importable_excludes_calc_file_descriptive():
    """exportFieldNames omits calc/file/descriptive. D13's round-trip
    compares against THAT list, so IMPORTABLE_COLUMNS must match it."""
    specs = load_dictionary(Path("dictionary/instrument.csv"))
    exportable = {c for s in specs.values() for c in s.export_columns}
    importable = {c for s in specs.values()
                  if s.carries_data and not s.server_computed
                  for c in s.export_columns}
    assert len(exportable) == 1891
    assert len(importable) == 1889
    assert len(exportable - importable) == 2   # exactly the two calc fields

