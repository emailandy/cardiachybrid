"""
Unit tests for prompts/builder.py (A05).
Verifies:
  1. Fail-safe anchor slicing across all 3 paths (None, {}, error/silent windows -> all 39 cards)
  2. BuiltPrompt dataclass return type and all audit/metadata fields
  3. 100x determinism of prompt_hash on identical inputs
  4. Vertex AI structured output JSON schema flattening (no $ref, no $defs, recursive detection)
  5. Assembled prompt field-name leakage trapping with a deliberately poisoned anchor card
  6. Idempotent snapshot writing and unfilled placeholder validation
"""

import json
from pathlib import Path
import pytest
from prompts.builder import (
    BuiltPrompt,
    select_anchors,
    to_vertex_schema,
    build_p1,
    build_p2,
    build_p3,
    build_p4a,
    build_p4b,
    build_p5,
    write_prompt_snapshot,
    _validate_no_unfilled_placeholders,
    _all_anchor_event_types,
)
from generated.models import EventStream, Event


def test_select_anchors_none_returns_all_39():
    selected, reasons = select_anchors(None)
    assert len(selected) == 39
    assert all("self_detection: all 39 cards included" in r for r in reasons.values())
    assert selected == sorted(selected)
    assert list(reasons.keys()) == sorted(reasons.keys())


def test_self_detection_mode_includes_all_anchors():
    """No sensors means no signal to slice on. Omitting a card makes that
    event type unemittable — silent total recall loss."""
    sel, _ = select_anchors(sensor_data=None)
    all_39 = _all_anchor_event_types()
    assert len(sel) == 39, f"dropped {39-len(sel)}: {sorted(set(all_39) - set(sel))}"


def test_select_anchors_empty_returns_all_39():
    selected, reasons = select_anchors({})
    assert len(selected) == 39
    assert reasons["compression_interruption"] == "self_detection: all 39 cards included (recall bias in absence of sensors)"
    assert selected == sorted(selected)


def test_select_anchors_quiet_window_returns_default_tier():
    data = json.loads(Path("tests/fixtures/sensors/quiet_window.json").read_text())
    selected, reasons = select_anchors(data)
    assert len(selected) == 16
    assert "self_detection: default resuscitation core tier" in reasons["airway_attempt"]


def test_build_p1_self_detection_mode():
    p1 = build_p1(
        chunk_index=1,
        chunk_total=4,
        video_duration_s=1363.78,
        win_start=0.0,
        win_end=480.0,
        primary_end=440.0,
        overlap_lead=0.0,
        win_start_primary=0.0,
        sensor_data=None,
    )
    assert "SELF-DETECTION MODE" in p1.user
    assert len(p1.selected_anchors) == 39



def test_select_anchors_dense_window_returns_triggered_subset():
    data = json.loads(Path("tests/fixtures/sensors/dense_window.json").read_text())
    selected, reasons = select_anchors(data)
    assert len(selected) < 39
    assert "compression_interruption" in selected
    assert "cpr_initiated_ed" in selected
    assert "defibrillation_shock" in selected
    assert reasons["cpr_initiated_ed"] == "sensor_trigger: compressions_active"


def test_select_anchors_degraded_and_malformed():
    deg = json.loads(Path("tests/fixtures/sensors/degraded_window.json").read_text())
    sel_deg, _ = select_anchors(deg)
    assert len(sel_deg) == 16

    mal = json.loads(Path("tests/fixtures/sensors/malformed.json").read_text())
    sel_mal, _ = select_anchors(mal)
    assert len(sel_mal) == 16


def test_select_anchors_error_fallback():
    class BrokenDict:
        def get(self, *args, **kwargs):
            raise RuntimeError("Simulated dictionary access error")

    selected, reasons = select_anchors(BrokenDict())
    assert len(selected) == 39
    assert all("fail_safe: selector error" in r for r in reasons.values())


def test_build_p1_returns_dataclass():
    data = json.loads(Path("tests/fixtures/sensors/quiet_window.json").read_text())
    p1 = build_p1(
        chunk_index=1,
        chunk_total=7,
        video_duration_s=600.0,
        win_start=0.0,
        win_end=60.0,
        primary_end=50.0,
        overlap_lead=0.0,
        win_start_primary=0.0,
        sensor_data=data,
    )
    assert isinstance(p1, BuiltPrompt)
    assert isinstance(p1.system, str) and len(p1.system) > 0
    assert isinstance(p1.user, str) and len(p1.user) > 0
    assert isinstance(p1.response_schema, dict)
    assert isinstance(p1.prompt_hash, str) and len(p1.prompt_hash) == 64
    assert isinstance(p1.selected_anchors, list) and len(p1.selected_anchors) == 16
    assert isinstance(p1.selection_reasons, dict)
    assert isinstance(p1.estimated_text_input_tokens, int) and p1.estimated_text_input_tokens > 0
    assert isinstance(p1.contract_version, str)
    assert isinstance(p1.dict_version, str)
    assert isinstance(p1.constitution_hash, str) and len(p1.constitution_hash) == 64
    assert isinstance(p1.anchor_library_version, str) and len(p1.anchor_library_version) == 64
    assert isinstance(p1.template_hash, str) and len(p1.template_hash) == 64


def test_build_p2_returns_dataclass():
    candidate = {"type": "airway_attempt", "timestamp_s": 15.0}
    p2 = build_p2(
        candidate_event_json=candidate,
        clip_t0=10.0,
        clip_t1=20.0,
        sensor_slice={"asr_diarized": []},
        event_type="airway_attempt",
    )
    assert isinstance(p2, BuiltPrompt)
    assert p2.selected_anchors == ["airway_attempt"]
    assert p2.selection_reasons == {"airway_attempt": "candidate_event_type"}
    assert isinstance(p2.prompt_hash, str) and len(p2.prompt_hash) == 64


def test_builder_determinism_100x():
    data = json.loads(Path("tests/fixtures/sensors/quiet_window.json").read_text())
    hashes = set()
    for _ in range(100):
        p = build_p1(
            chunk_index=1,
            chunk_total=7,
            video_duration_s=600.0,
            win_start=0.0,
            win_end=60.0,
            primary_end=50.0,
            overlap_lead=0.0,
            win_start_primary=0.0,
            sensor_data=data,
        )
        hashes.add(p.prompt_hash)
    assert len(hashes) == 1, f"Expected exactly 1 prompt_hash across 100 calls, got {len(hashes)}"


def test_to_vertex_schema_flattening():
    # allow_empty_object=True because CaseFields is an open object schema representing REDCap fields
    s1 = to_vertex_schema(EventStream.model_json_schema(), allow_empty_object=True)
    str1 = json.dumps(s1)
    assert '"$ref"' not in str1
    assert '"$defs"' not in str1
    assert '"title"' not in str1
    assert '"default"' not in str1

    # allow_empty_object=True because Event.attributes is unpopulated before contract slicing
    s2 = to_vertex_schema(Event.model_json_schema(), allow_empty_object=True)
    str2 = json.dumps(s2)
    assert '"$ref"' not in str2
    assert '"$defs"' not in str2


def test_to_vertex_schema_recursive_model_raises():
    recursive_schema = {
        "$defs": {
            "Node": {
                "type": "object",
                "properties": {
                    "child": {"$ref": "#/$defs/Node"}
                }
            }
        },
        "$ref": "#/$defs/Node"
    }
    with pytest.raises(ValueError, match="Recursive model reference cannot be flattened"):
        to_vertex_schema(recursive_schema)


def test_assert_no_field_names_on_assembled_prompt(monkeypatch):
    # Poison anchor card retrieval to inject a literal REDCap field name
    monkeypatch.setattr(
        "prompts.builder.anchor",
        lambda et: "Poisoned card text with literal column name decision_time_thromb_ed inside it"
    )
    with pytest.raises(ValueError, match="leaks REDCap field names into prompt text"):
        build_p1(1, 1, 100.0, 0.0, 100.0, 100.0, 0.0, 0.0, None)


def test_snapshot_writer_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    h = "test_hash_0123456789abcdef"
    p1 = write_prompt_snapshot(h, "System Prompt", "User Prompt")
    assert p1.exists()
    content1 = p1.read_text(encoding="utf-8")
    assert "# prompt_hash: test_hash_0123456789abcdef" in content1
    assert "System Prompt\n---\nUser Prompt" in content1

    # Call again, verify idempotent
    p2 = write_prompt_snapshot(h, "System Prompt", "User Prompt")
    assert p1 == p2
    assert p2.read_text(encoding="utf-8") == content1


def test_no_unfilled_placeholders():
    with pytest.raises(ValueError, match="Unfilled placeholder '{chunk_index}'"):
        _validate_no_unfilled_placeholders("This text still has {chunk_index} unfilled.", "p1_harvest")


def test_p4a_metrics_block_inline_null_reason_no_zero():
    from metrics.compute import MetricRow
    rows = [
        MetricRow("c1", "chest_compression_fraction", 0.83, 1494, 1800, None, "v1"),
        MetricRow("c1", "closed_loop_completion_rate", None, None, None, "requires S7 diarized ASR", "v1"),
        MetricRow("c1", "median_peri_shock_pause_s", None, None, None, "zero shocks in case", "v1"),
    ]
    p4a = build_p4a(metrics_table=rows)
    assert "chest_compression_fraction          0.83 (num 1494 / den 1800)" in p4a.user
    assert "closed_loop_completion_rate         NULL (requires S7 diarized ASR)" in p4a.user
    assert "median_peri_shock_pause_s           NULL (zero shocks in case)" in p4a.user
    # Ensure NULL metrics do not render as 0, "0", "0.0", or empty string
    for line in p4a.user.splitlines():
        if "closed_loop_completion_rate" in line or "median_peri_shock_pause_s" in line:
            assert "NULL" in line
            assert " 0 " not in line and " 0.0 " not in line


def test_p4a_p4b_calibration_stubs_q015_substring():
    p4a = build_p4a()
    p4b = build_p4b()
    assert "Q-015" in p4a.user
    assert "Q-015" in p4b.user
    assert "status: BLOCKED" not in p4a.user and "status: BLOCKED" not in p4b.user
    assert "blocked_by:" not in p4a.user and "blocked_by:" not in p4b.user


def test_p5_truncation_report_names_all_five_dropped_items():
    from fixtures.synthetic_streams import get_overflow_stream
    stream = get_overflow_stream()
    p5 = build_p5(target_field="cci_notes", truncation_report=stream)
    assert "35 interruptions were identified; the instrument records 30." in p5.user
    for expected_ts in ["05:05", "05:15", "05:25", "05:35", "05:45"]:
        assert expected_ts in p5.user
    assert p5.user.count("pulse check") >= 5


def test_builder_determinism_100x_all_four():
    from fixtures.synthetic_streams import get_overflow_stream
    stream = get_overflow_stream()
    for builder, kwargs in [
        (build_p3, {"events": "ev", "compression_track": "comp", "transcript": "trn", "monitor_ocr": "ocr", "coverage": "cov", "clock_json": "{}"}),
        (build_p4a, {"leader_speaker_id": "SPK_01"}),
        (build_p4b, {"coverage_summary": "cov"}),
        (build_p5, {"target_field": "cci_notes", "truncation_report": stream}),
    ]:
        hashes = set()
        for _ in range(100):
            res = builder(**kwargs)
            hashes.add(res.prompt_hash)
        assert len(hashes) == 1, f"Builder {builder.__name__} was not 100x deterministic"


def test_response_schema_declares_contract_attributes():
    """The contract must reach the SCHEMA, not just the prompt text. A free-form attributes object means the model has no binding guidance and can emit {} — which validates, reduces to null, and is indistinguishable from honest abstention."""
    bp_default = build_p1(0, 1, 1000.0, 0.0, 480.0, 420.0, 0.0, 0.0, None)
    events_items = bp_default.response_schema["properties"]["events"]["items"]
    # In self-detection mode (>30 event types), Option (b)(ii) unified contract attribute schema is used to stay within Vertex AI's schema complexity limit
    declared_attrs = set(events_items["properties"]["attributes"]["properties"].keys())
    assert "access_types" in declared_attrs
    assert "applied_by" in declared_attrs
    assert "pad_position" in declared_attrs
    assert "locations" in declared_attrs
    assert "rhythm" in declared_attrs
    assert "device" in declared_attrs

    bp_triggered = build_p1(0, 1, 1000.0, 0.0, 480.0, 420.0, 0.0, 0.0, None, keywords=["shock", "pulse"])
    events_items_trig = bp_triggered.response_schema["properties"]["events"]["items"]
    assert "properties" in events_items_trig, "events.items uses unified schema to avoid Vertex AI INVALID_ARGUMENT"
    trig_attrs = set()
    trig_attrs = set(events_items_trig["properties"]["attributes"]["properties"].keys())
    assert "pad_position" in trig_attrs
    assert "locations" in trig_attrs


def test_event_and_interval_enums_are_disjoint():
    """EventType and IntervalType must be disjoint and their union must equal all non-meta event types."""
    import generated.models as m
    ev_types = set(m.EventType.__args__)
    inv_types = set(m.IntervalType.__args__)
    assert ev_types.isdisjoint(inv_types), f"Enums overlap: {ev_types & inv_types}"
    assert "defibrillation_shock" in ev_types
    assert "compression_interruption" in inv_types
    assert "rosc" in inv_types
    assert "ventilation_delay" in inv_types


def test_extra_forbid_rejects_unknown_key():
    """extra='forbid' must reject unknown keys on Evidence and Event."""
    import pytest
    from pydantic import ValidationError
    import generated.models as m

    with pytest.raises(ValidationError) as exc_info:
        m.Evidence(t=10.0, quote="hi", unknown_field=123)
    assert "extra_forbidden" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        m.Event(type="defibrillation_shock", t_start_s=10.0, unknown_field="bad")
    assert "extra_forbidden" in str(exc_info.value)
