import pytest
from importlib import import_module
from pathlib import Path
import subprocess
import os

def test_columns():
    redcap = import_module("generated.redcap_fields")
    
    assert len(redcap.EXPORT_COLUMNS) == 1891
    assert redcap.SUBMISSION_COLUMNS == redcap.IMPORTABLE_COLUMNS | {"record_id", "video_review_complete"}
    assert len(redcap.SUBMISSION_COLUMNS) == 1891
    assert redcap.EXPORT_COLUMNS != redcap.SUBMISSION_COLUMNS
    
    calc_fields = redcap.EXPORT_COLUMNS - redcap.IMPORTABLE_COLUMNS
    assert len(calc_fields) == 2
    for f in calc_fields:
        assert redcap.FIELDS[f].server_computed

def test_determinism():
    # Ensure they exist first
    subprocess.run(["python", "codegen/emit_python.py"], check=True)
    
    redcap_before = Path("generated/redcap_fields.py").read_bytes()
    models_before = Path("generated/models.py").read_bytes()
    
    subprocess.run(["python", "codegen/emit_python.py"], check=True)
    
    redcap_after = Path("generated/redcap_fields.py").read_bytes()
    models_after = Path("generated/models.py").read_bytes()
    
    assert redcap_before == redcap_after
    assert models_before == models_after

def test_vocabularies():
    redcap = import_module("generated.redcap_fields")
    vocab = redcap.VOCAB
    assert len(vocab["reason_cci_1_v2"]) == 21
    assert len(vocab["reason_cci_2_v2"]) == 21
    
    assert vocab["ecmo_called_ed_v2"]["not_available"] == 5
    assert vocab["ecmo_initiated_ed_v2"]["not_available"] == 4
    
    assert vocab["loc_initial_pulse_check_v2"]["radial"] == 3
    assert vocab["loc_pulse_check_cci_1"]["brachial"] == 3

def test_no_codegen_import():
    # grep test: no runtime dependency from generated/ back into codegen/
    output = subprocess.run(["grep", "-r", "codegen", "generated/"], capture_output=True, text=True)
    assert not output.stdout.strip(), "Found forbidden 'codegen' import in generated/"
