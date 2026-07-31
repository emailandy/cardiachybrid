import pytest
from pathlib import Path
from codegen.yamlio import load_yaml
import tempfile

def test_duplicate_keys():
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write("a: 1\nb: 2\na: 3\n")
        name = f.name
    try:
        with pytest.raises(ValueError, match="duplicate key 'a'"):
            load_yaml(Path(name))
    finally:
        Path(name).unlink()

def test_unquoted_boolean():
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write("vocab:\n  yes: 1\n  no: 2\n")
        name = f.name
    try:
        with pytest.raises(ValueError, match="unquoted key 'yes' is a YAML 1.1 boolean"):
            load_yaml(Path(name))
    finally:
        Path(name).unlink()
