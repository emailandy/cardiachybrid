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

def load_event_types():
    from codegen.emit_manifest import StrictLoader
    import yaml
    with open("mapping/event_types.yaml") as f:
        return yaml.load(f, Loader=StrictLoader)

def iter_all_rules(registry):
    for sec in registry.get("sections", []):
        yield from sec.get("fields", [])
    yield from registry.get("never_ai", [])
    for g in registry.get("groups", []):
        yield g
        yield from g.get("fields", [])

def test_event_types_redcap_feeding_matches_registry():
    """redcap_feeding is DERIVED, not authored. Any registry rule naming a
    new event_type must appear here or the closed vocabulary silently
    excludes it."""
    derived = set()
    for rule in iter_all_rules(load_registry()):
        if et := rule.get("event_type") or rule.get("interval_type"):
            derived.add(et)
        derived.update(rule.get("owning_event_types", []))
    declared = set(load_event_types()["redcap_feeding"])
    assert declared == derived, (
        f"missing from event_types.yaml: {sorted(derived - declared)}\n"
        f"declared but unreferenced: {sorted(declared - derived)}")

def test_anchor_cards_required_count():
    et = load_event_types()
    required = set().union(et["redcap_feeding"], et["interval_boundary"],
                           et["negative_control"], et["context"])
    assert len(required) == 42
    assert not (required & set(et["meta"]))   # meta needs no card
