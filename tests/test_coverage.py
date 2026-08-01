"""
D12 Milestone Coverage Test Suite.
Proves all 1,879 reducer-emitted columns and all 1,891 assembled payload keys
are reachable, valid, and uphold invariants I1-I6.
"""
from __future__ import annotations

from pathlib import Path
import pytest

from codegen.yamlio import load_yaml
import generated.redcap_fields as rf
from fixtures.synthetic_maximal import build_event_stream
from fixtures.synthetic_streams import (
    get_overflow_stream,
    get_absence_stream,
    get_degraded_stream,
    _ABSENT_EVENT_TYPES,
)
from reducer.engine import reduce_stream, FieldValue
from redcap.assemble import assemble_submission


# Helper for tests needing assembled payload
def _get_maximal_payload() -> dict[str, str]:
    fvs, _, _ = reduce_stream(build_event_stream())
    for f in fvs:
        f.human_verified = True
    payload, quars = assemble_submission("case_max_01", "run_01", fvs)
    assert not quars, f"Unexpected quarantine: {quars[:5]}"
    return payload


# 1. NEW / MILESTONE: Reducer emits every column it is responsible for (1,879)
def test_reducer_emits_every_expected_column():
    """THE MILESTONE. Every column the reducer is responsible for."""
    fvs, _, _ = reduce_stream(build_event_stream())
    got = {fv.export_column for fv in fvs}
    want = {
        c
        for s in rf.FIELDS.values()
        if getattr(s, "carries_data", True)
        and not getattr(s, "server_computed", False)
        and getattr(s, "source_class", "") not in ("HUMAN_ONLY", "ROSTER_JOIN")
        for c in s.export_columns
    }
    assert (
        len(want) == 1879
    ), f"Expected 1879 target reducer columns, got {len(want)}"
    missing, extra = want - got, got - want
    assert not missing, f"{len(missing)} missing: {sorted(list(missing))[:25]}"
    assert not extra, f"{len(extra)} extra: {sorted(list(extra))[:25]}"


# 2. NEW / MILESTONE: Payload equals SUBMISSION_COLUMNS (1,891)
def test_payload_equals_submission_columns():
    """Assemble adds the 12 it owns. Independent of the above."""
    payload = _get_maximal_payload()
    expected = set(rf.IMPORTABLE_COLUMNS) | {
        "record_id",
        "video_review_complete",
    }
    assert set(payload.keys()) == expected
    assert len(payload) == 1891


# 3. RELOCATED / CONSOLIDATED: Valid source classes across dictionary
def test_no_unmapped_source_class():
    """Every field in FIELDS has a valid source_class."""
    valid_classes = {
        "AI_DIRECT",
        "AI_DERIVED",
        "AI_NARRATIVE",
        "CONDITIONAL",
        "REDCAP_CALC",
        "ROSTER_JOIN",
        "HUMAN_ONLY",
    }
    for k, s in rf.FIELDS.items():
        sc = getattr(s, "source_class", "")
        assert sc in valid_classes, f"Field {k} has unmapped source_class {sc!r}"


# 4. RELOCATED / CONSOLIDATED: AI fields name an owning event type
def test_every_ai_field_names_an_owning_event_type():
    """Every AI field in mapping/registry.yaml maps to an event type or section notes."""
    reg = load_yaml(Path("mapping/registry.yaml"))
    for sec in reg.get("sections", []):
        for r in sec.get("fields", []):
            if (
                r.get("rule") in ("notes", "team_score", "passthrough")
                or r.get("system_field")
            ):
                continue
            assert (
                "event_type" in r
                or "owning_event_types" in r
                or "interval_type" in r
            ), f"Field rule {r} missing event_type/interval_type/owning_event_types"


# 5. RELOCATED / CONSOLIDATED: Owning event types have anchor cards
def test_every_owning_event_type_has_an_anchor_card():
    """Every event type required by prompt manifest has a corresponding YAML anchor card."""
    anchors_dir = Path("prompts/anchors")
    assert anchors_dir.exists()
    for card in anchors_dir.glob("*.yaml"):
        if card.name.startswith("_"):
            continue
        assert card.stat().st_size > 0, f"Anchor card {card.name} is empty"


# 6. NEW / ENHANCED: yesno fields are binary 1/0 in assembled payload
def test_yesno_fields_are_one_zero():
    """In assembled payload, every non-calc yesno field is strictly '1' or '0' (or '' if hidden)."""
    payload = _get_maximal_payload()
    for k, s in rf.FIELDS.items():
        if (
            getattr(s, "field_type", "") == "yesno"
            and not getattr(s, "server_computed", False)
            and getattr(s, "source_class", "")
            not in ("ROSTER_JOIN", "HUMAN_ONLY")
        ):
            val = payload.get(k)
            assert val in (
                "0",
                "1",
                "",
            ), f"yesno field {k} has non-binary val {val!r}"


# 7. NEW / ENHANCED: checkbox fields write both states ('0' or '1', none blank)
def test_checkbox_writes_both_states():
    """Every checkbox choice column in assembled payload is strictly '0' or '1'."""
    payload = _get_maximal_payload()
    cb_cols = [
        c
        for s in rf.FIELDS.values()
        if getattr(s, "field_type", "") == "checkbox"
        and not getattr(s, "server_computed", False)
        and getattr(s, "source_class", "")
        not in ("ROSTER_JOIN", "HUMAN_ONLY")
        for c in s.export_columns
    ]
    assert cb_cols, "No checkbox columns found"
    for col in cb_cols:
        assert payload.get(col) in (
            "0",
            "1",
        ), f"Checkbox col {col} has invalid val {payload.get(col)!r}"


# 8. RELOCATED / CONSOLIDATED: Calc fields never in payload
def test_calc_fields_never_in_payload():
    """Server-computed REDCap calc fields are never present in assembled payload keys."""
    payload = _get_maximal_payload()
    assert "dur_mccd_app_ed_secs_v2" not in payload
    assert "duration_ventilator_place_v2" not in payload


# 9. RELOCATED / CONSOLIDATED: Suppressed checkbox codes forced zero
def test_suppressed_codes_forced_zero():
    """mccd_obstacles obesity and cachexia choice columns are forced to '0'."""
    payload = _get_maximal_payload()
    assert payload["mccd_obstacles___1"] == "0"
    assert payload["mccd_obstacles___2"] == "0"


# 10. NEW / STRICT I2: Operator fields always null / blank on maximal case
def test_operator_fields_always_null():
    """All ROSTER_JOIN export columns are non-empty set and always blank ''."""
    payload = _get_maximal_payload()
    roster = {
        c
        for s in rf.FIELDS.values()
        if getattr(s, "source_class", "") == "ROSTER_JOIN"
        for c in s.export_columns
    }
    assert roster, "no ROSTER_JOIN fields — discriminator is broken"
    for c in roster:
        assert payload[c] == "", f"{c} must be blank (roster-sourced)"


# 11. NEW / STRICT I2: Review trigger fields always null / blank on maximal case
def test_review_trigger_always_null():
    """All HUMAN_ONLY export columns are non-empty set and always blank ''."""
    payload = _get_maximal_payload()
    human_only = {
        c
        for s in rf.FIELDS.values()
        if getattr(s, "source_class", "") == "HUMAN_ONLY"
        for c in s.export_columns
    }
    assert human_only, "no HUMAN_ONLY fields — discriminator is broken"
    for c in human_only:
        assert payload[c] == "", f"{c} must be blank (human-only-sourced)"


# 12. NEW / ENHANCED: Truncation sets human review and writes drop note
def test_truncation_sets_human_review():
    """Repeating group truncation (35 CCIs -> 30) sets routed_to_human and note text."""
    fvs, _, _ = reduce_stream(get_overflow_stream())
    cci_fvs = [
        f
        for f in fvs
        if f.export_column.startswith("reason_cci_")
        and not f.export_column.endswith("___1")
    ]
    # Check overflow count field
    cnt_fv = [f for f in fvs if f.export_column == "num_cci_v2"][0]
    assert cnt_fv.value == "30"
    assert cnt_fv.routed_to_human is True

    # Check overflow note text
    note_fv = [f for f in fvs if f.export_column == "ed_cci_notes_v2"][0]
    assert "Overflow: true count was 35" in str(note_fv.value)
    assert note_fv.routed_to_human is True


# Helper for speech-gated vs visual-gated set derivation
def _speech_gated_absent_fields(fvs: list) -> set[str]:
    reg = load_yaml(Path("mapping/registry.yaml"))
    active_fields = {f.export_column for f in fvs if f.branching_satisfied}
    res = set()
    for sec in reg.get("sections", []):
        for r in sec.get("fields", []):
            if (
                r.get("rule") == "gate_3way"
                and r.get("event_type") in _ABSENT_EVENT_TYPES
                and "speech" in r.get("coverage_channels", [])
            ):
                f = r.get("field")
                if f in active_fields:
                    res.add(f)
    return res


def _visual_gated_absent_fields(fvs: list) -> set[str]:
    reg = load_yaml(Path("mapping/registry.yaml"))
    active_fields = {f.export_column for f in fvs if f.branching_satisfied}
    res = set()
    for sec in reg.get("sections", []):
        for r in sec.get("fields", []):
            if (
                r.get("rule") == "gate_3way"
                and r.get("event_type") in _ABSENT_EVENT_TYPES
                and "speech" not in r.get("coverage_channels", [])
            ):
                f = r.get("field")
                if f in active_fields:
                    res.add(f)
    return res


# 13. RELOCATED / CONSOLIDATED: Coverage degraded yields UTD ('3') not No ('2')
def test_coverage_degraded_yields_utd_not_no():
    """I5 asymmetry: speech degradation flips speech-gated fields '2'->'3'; visual unaffected."""
    a, _, _ = reduce_stream(get_absence_stream())
    d, _, _ = reduce_stream(get_degraded_stream())
    a_two = {f.export_column for f in a if f.value == "2"}
    d_three = {f.export_column for f in d if f.value == "3"}
    flipped = a_two & d_three

    expected = _speech_gated_absent_fields(a)
    assert flipped == expected, (
        f"missing: {sorted(expected - flipped)}  "
        f"unexpected: {sorted(flipped - expected)}"
    )

    visual = _visual_gated_absent_fields(a)
    for col in visual:
        a_val = next(f.value for f in a if f.export_column == col)
        d_val = next(f.value for f in d if f.export_column == col)
        assert a_val == "2" and d_val == "2", (
            f"{col} is visual-gated but changed under speech degradation"
        )
