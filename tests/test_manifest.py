import pytest
import yaml

def test_duplicate_yaml_keys_rejected():
    from codegen.emit_manifest import StrictLoader
    bad_yaml = "a: 1\nb: 2\na: 3\n"
    with pytest.raises(ValueError) as exc:
        yaml.load(bad_yaml, Loader=StrictLoader)
    assert "Duplicate YAML key 'a' at line 3" in str(exc.value)

def load_registry():
    from codegen.emit_manifest import StrictLoader
    with open("mapping/registry.yaml") as f:
        return yaml.load(f, Loader=StrictLoader)

def test_pulse_location_vocabularies_are_not_shared():
    """loc_initial_pulse_check_v2 is 3=Radial 4=Brachial.
    loc_pulse_check_cci_N is 3=Brachial 4=Radial. Codes 3 and 4 are SWAPPED
    in the source dictionary. Sharing one vocabulary would silently transpose
    radial and brachial on every compression interruption."""
    v = load_registry()["vocabularies"]
    assert v["pulse_loc_initial"]["radial"] == 3
    assert v["pulse_loc_initial"]["brachial"] == 4
    assert v["pulse_loc_cci"]["brachial"] == 3
    assert v["pulse_loc_cci"]["radial"] == 4
    assert v["pulse_loc_initial"] != v["pulse_loc_cci"]

def test_ecmo_gates_use_different_not_available_codes():
    v = load_registry()["vocabularies"]
    assert v["ecmo_gate_5"]["not_available"] == 5
    assert v["ecmo_gate_4"]["not_available"] == 4
