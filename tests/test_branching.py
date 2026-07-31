import pytest
import ast
from codegen.branching import compile_predicate, _cmp

def test_malicious_inputs_rejected():
    malicious = [
        "[x] = __import__('os')",
        "[x] = (lambda: 1)()",
        "[x] = record.get('foo')",  # attribute access
        "[x] = 1; import os",
        "[x] = globals()"
    ]
    for expr in malicious:
        with pytest.raises(ValueError):
            compile_predicate(expr)

def test_comparison_semantics():
    # numeric/numeric
    assert _cmp("=", "1.0", "1") is True
    assert _cmp("<", "1", "2") is True
    
    # string/string
    assert _cmp("=", "a", "a") is True
    assert _cmp("<", "a", "b") is True
    
    # numeric/string (lexical)
    assert _cmp("=", "1", "1.0a") is False
    assert _cmp("<", "10", "2a") is True # lexically 10 < 2a
    
    # blank-left with < <= > >=
    for op in ("<", "<=", ">", ">="):
        assert _cmp(op, "", "2") is False
        assert _cmp(op, "   ", "2") is False
        
    # blank-left with = and <>
    assert _cmp("=", "", "") is True
    assert _cmp("<>", "", "1") is True

def test_checkbox_routing():
    pred = compile_predicate("[reason_cci_1_v2(4)] = '1'")
    assert pred({"reason_cci_1_v2___4": "1"}) is True
    assert pred({"reason_cci_1_v2___4": "0"}) is False
    
    pred2 = compile_predicate("[mccd_obstacles(6)] =1")
    assert pred2({"mccd_obstacles___6": "1"}) is True
    assert pred2({"mccd_obstacles___6": "0"}) is False

def test_unknown_field_reference():
    pred = compile_predicate("[onset_ca_occur] = '1' and [mccd_applied_ems_v2] = '1'")
    assert pred({}) is False

def test_nested_logic():
    expr = "[a] = '1' and not ([b] = '2' or [c] = '3')"
    pred = compile_predicate(expr)
    assert pred({"a": "1", "b": "0", "c": "0"}) is True
    assert pred({"a": "1", "b": "2", "c": "0"}) is False
    assert pred({"a": "0", "b": "0", "c": "0"}) is False

def test_truthy_behavior():
    pred = compile_predicate("[a] and not [b]")
    assert pred({"a": "1", "b": "0"}) is True
    assert pred({"a": "1", "b": "1"}) is False
    assert pred({"a": "0", "b": "0"}) is False
    assert pred({"a": "", "b": ""}) is False

def test_compile_all_dictionary():
    import csv
    import io
    import re
    from pathlib import Path
    
    dict_path = Path("dictionary/instrument.csv")
    raw = dict_path.read_bytes().decode("utf-8-sig")
    try:
        dialect = csv.Sniffer().sniff(raw[:8192], delimiters=",\t")
    except csv.Error:
        dialect = csv.excel
        
    rdr = csv.DictReader(io.StringIO(raw), dialect=dialect)
    if not rdr.fieldnames or len(rdr.fieldnames) < 10:
        rdr = csv.DictReader(io.StringIO(raw), dialect=csv.excel)
        
    slug_to_header = {re.sub(r"[^a-z0-9]", "", h.lower()): h for h in rdr.fieldnames}
    bl_header = slug_to_header.get("branchinglogicshowfieldonlyif")
    
    count = 0
    for row in rdr:
        logic = row[bl_header].strip()
        if logic:
            compile_predicate(logic)
            count += 1
            
    assert count == 858
