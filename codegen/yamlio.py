"""The ONE YAML loader. Every YAML read in this repo goes through load_yaml().
Guards two silent-corruption hazards:
  1. Duplicate keys — PyYAML keeps the last, discarding earlier content.
  2. YAML 1.1 implicit booleans — unquoted yes/no/on/off/y/n become
     True/False as MAPPING KEYS, turning {yes: 1} into {True: 1}.
"""
import re, yaml
from pathlib import Path

YAML11_BOOL = re.compile(
    r"^(y|Y|yes|Yes|YES|n|N|no|No|NO"
    r"|true|True|TRUE|false|False|FALSE|on|On|ON|off|Off|OFF)$")

class StrictLoader(yaml.SafeLoader): pass

def _mapping(loader, node, deep=False):
    out = {}
    for k_node, v_node in node.value:
        raw = getattr(k_node, "value", None)
        if isinstance(raw, str) and k_node.style is None \
           and YAML11_BOOL.match(raw):
            m = k_node.start_mark
            raise ValueError(
                f"{m.name}:{m.line+1}:{m.column+1}: unquoted key {raw!r} is "
                f"a YAML 1.1 boolean and parses as True/False, not the "
                f"string {raw!r}. Quote it: '{raw}': ...")
        key = loader.construct_object(k_node, deep=deep)
        if key in out:
            m = k_node.start_mark
            raise ValueError(
                f"{m.name}:{m.line+1}:{m.column+1}: duplicate key {key!r}. "
                f"PyYAML silently keeps only the last occurrence.")
        out[key] = loader.construct_object(v_node, deep=deep)
    return out

StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)

def load_yaml(path: Path):
    with open(path) as f:
        return yaml.load(f, Loader=StrictLoader)
