import sys
sys.path.insert(0, '.')
from codegen.redcap_dict_to_code import load_dictionary
from pathlib import Path

try:
    s = load_dictionary(Path('dictionary/instrument.csv'))
    n_fields = len(s)
    n_cols = sum(len(x.export_columns) for x in s.values())
    print(f"ACTUAL: {n_fields} {n_cols}")
    
    type_counts = {}
    for f in s.values():
        type_counts[f.field_type] = type_counts.get(f.field_type, 0) + 1
    print("TYPE COUNTS:", type_counts)
    
    non_checkbox = 0
    cb_codes = {}
    for f in s.values():
        if f.field_type == "checkbox":
            cb_codes[f.name] = len(f.choices)
        else:
            non_checkbox += len(f.export_columns)
            
    print(f"Non-checkbox columns: {non_checkbox}")
    print(f"Total checkbox codes: {sum(cb_codes.values())}")
    
except Exception as e:
    import traceback
    traceback.print_exc()

