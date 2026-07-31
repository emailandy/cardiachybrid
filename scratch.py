from codegen.branching import compile_predicate
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
name_header = slug_to_header.get("variablefieldname") or slug_to_header.get("field_name")

count = 0
for row in rdr:
    logic = row[bl_header].strip()
    if logic:
        try:
            compile_predicate(logic)
            count += 1
        except Exception as e:
            print(f"FAILED on {row[name_header]}: {logic} -> {e}")

print("Total compiled:", count)
