import pytest
import yaml

from codegen.yamlio import load_yaml
from pathlib import Path

def load_registry():
    return load_yaml(Path("mapping/registry.yaml"))

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
    return load_yaml(Path("mapping/event_types.yaml"))

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
    rules = list(iter_all_rules(load_registry()))
    event_types = {r["event_type"] for r in rules if r.get("event_type")}
    interval_types = {r["interval_type"] for r in rules if r.get("interval_type")}
    owning_hints = {t for r in rules for t in r.get("owning_event_types", [])}

    assert not (interval_types & event_types), \
        f"interval_type names leaked into event types: {interval_types & event_types}"

    derived = event_types | owning_hints
    declared = set(load_event_types()["redcap_feeding"])
    assert declared == derived, (
        f"missing from event_types.yaml: {sorted(derived - declared)}\n"
        f"declared but unreferenced: {sorted(declared - derived)}")

def test_anchor_cards_required_count():
    et = load_event_types()
    required = set().union(et["redcap_feeding"], et["interval_boundary"],
                           et["negative_control"], et["context"])
    assert len(required) == 39
    assert not (required & set(et["meta"]))   # meta needs no card
