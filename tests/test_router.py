"""
Unit tests for D09 confidence router and HITL review queue.
Verifies dynamic YAML thresholds, mandatory TEAM routing (Q-006),
deep link generation (-10s offset), A3 exemplar few-shot feedback loop,
and objective-first queue ordering.
"""

import yaml
import pytest
from pathlib import Path
from fixtures.synthetic_streams import get_maximal_stream
from reducer.engine import FieldValue, reduce_stream
from router.policy import (
    load_routing_config,
    should_route,
    evaluate_stream_routing,
    _get_field_rule_map,
)
from router.queue import ReviewQueue, QueueItem, ExemplarStore


def make_fv(
    field_name: str,
    confidence: float = 0.95,
    validation_passed: bool = True,
    abstained: bool = False,
    routed_to_human: bool = False,
    ensemble_spread_s: float = 0.0,
) -> FieldValue:
    fv = FieldValue(
        field_name=field_name,
        export_column=field_name,
        value="test_val",
        value_label="Test Val",
        is_null=False,
        abstained=abstained,
        abstain_reason="test" if abstained else None,
        confidence=confidence,
        source_class="AI_DIRECT",
        source_event_ids=["ev_101"],
        validation_passed=validation_passed,
        routed_to_human=routed_to_human,
    )
    return fv


def test_ensemble_spread_routes() -> None:
    """Test that ensemble spread > spread_threshold_s routes for human review."""
    fv = make_fv("defib_energy_v2", confidence=0.99)
    route_small, _ = should_route(fv, ensemble_spread_s=1.0)
    assert route_small is False

    route_large, reason = should_route(fv, ensemble_spread_s=3.5)
    assert route_large is True
    assert reason == "spread > 3.0s"


def test_dynamic_config_thresholds(tmp_path: Path) -> None:
    """Test that changing routing YAML config dynamically changes behavior — not merely that the file is read."""
    config_path = tmp_path / "custom_routing.yaml"
    custom_config = {
        "confidence_thresholds": {
            "LOW": 0.80,
            "MEDIUM": 0.85,
            "HIGH": 0.95,
            "default": 0.85,
        },
        "spread_threshold_s": 3.0,
    }
    with open(config_path, "w") as f:
        yaml.safe_dump(custom_config, f)
    loaded = load_routing_config(config_path)

    # A HIGH difficulty field (e.g. first_ed_rhythm_v2 has HIGH difficulty in dictionary)
    fv = make_fv("first_ed_rhythm_v2", confidence=0.93)

    # With default config (HIGH = 0.92), confidence 0.93 does not route
    route_default, reason_default = should_route(fv)
    assert route_default is False

    # With custom config (HIGH = 0.95), confidence 0.93 routes for low confidence
    route_custom, reason_custom = should_route(fv, config=loaded)
    assert route_custom is True
    assert reason_custom == "low confidence"


def test_all_team_score_fields_route() -> None:
    """
    Q-006 OPEN: TEAM fields route unconditionally until per-item ICC vs.
    two human raters exceeds 0.75. Identified by registry rule, not by form_name
    or source_class.
    """
    rule_map = _get_field_rule_map()
    team = [f for f, r in rule_map.items() if r == "team_score"]
    assert len(team) == 12, f"Expected 12 TEAM fields, got {len(team)}"
    for f in team:
        fv = make_fv(f, confidence=1.0, validation_passed=True, abstained=False)
        route, reason = should_route(fv, rule_map=rule_map)
        assert route is True, f"Field {f} must route unconditionally under Q-006"
        assert reason == "TEAM (Q-006)"


def test_deep_link_is_the_product() -> None:
    """Queue.next_item() deep link must return video_uri plus t_start_s - 10s."""
    item1 = QueueItem(
        case_id="case_001",
        event_id="ev_001",
        field_name="defib_energy_v2",
        field_label="Defib Energy",
        ai_value="200",
        ai_label="200J",
        confidence=0.82,
        abstain_reason=None,
        source_event_ids=["ev_001"],
        video_uri="gs://bucket/video.mp4",
        t_start_s=45.0,
    )
    assert item1.deep_link == "gs://bucket/video.mp4#t=35.0"

    item2 = QueueItem(
        case_id="case_002",
        event_id="ev_002",
        field_name="defib_energy_v2",
        field_label="Defib Energy",
        ai_value="200",
        ai_label="200J",
        confidence=0.82,
        abstain_reason=None,
        source_event_ids=["ev_002"],
        video_uri="gs://bucket/video.mp4",
        t_start_s=5.0,  # Starts early in video
    )
    assert item2.deep_link == "gs://bucket/video.mp4#t=0.0"


def test_exemplar_store_a3_loop_and_idempotency() -> None:
    """
    Every correction writes an exemplar row for retrieval-augmented few-shot (the A3 loop).
    Test retrievability immediately by event_type and submit() idempotency.
    """
    store = ExemplarStore()
    queue = ReviewQueue(exemplar_store=store)

    item = QueueItem(
        case_id="case_101",
        event_id="ev_101",
        field_name="defib_energy_v2",
        field_label="Defib Energy",
        ai_value="200",
        ai_label="200J",
        confidence=0.80,
        abstain_reason=None,
        source_event_ids=["ev_101"],
        video_uri="gs://bucket/video.mp4",
        t_start_s=60.0,
        event_type="defibrillation_shock",
    )
    queue.enqueue(item)

    # Submit correction: human_value != ai_value
    queue.submit(
        reviewer_id="rev_001",
        case_id="case_101",
        field_name="defib_energy_v2",
        human_value="360",
        note="Verified on defibrillator display",
    )
    assert item.reviewed is True
    assert item.human_value == "360"
    assert item.final_value == "360"

    # Retrievable by event_type immediately
    exemplars = store.get_by_event_type("defibrillation_shock")
    assert len(exemplars) == 1
    assert exemplars[0].human_value == "360"
    assert exemplars[0].clip_t0 == 50.0  # t_start_s - 10s
    assert exemplars[0].clip_t1 == 70.0  # t_start_s + 10s

    # Idempotent re-submission updates without duplicate exemplar records
    queue.submit(
        reviewer_id="rev_001",
        case_id="case_101",
        field_name="defib_energy_v2",
        human_value="360",
        note="Updated note",
    )
    assert len(store.get_by_event_type("defibrillation_shock")) == 1
    assert len(store.get_by_field("defib_energy_v2")) == 1


def test_next_item_ordering_objective_before_subjective() -> None:
    """
    ReviewQueue.next_item() orders objective items before subjective TEAM items
    so subjective ratings evaluate with the whole case in mind.
    """
    queue = ReviewQueue()
    team_item = QueueItem(
        case_id="case_201",
        event_id="ev_201",
        field_name="team1_v2",
        field_label="Team Leader",
        ai_value="1",
        ai_label="1",
        confidence=0.70,
        abstain_reason=None,
        source_event_ids=[],
        video_uri="gs://bucket/video.mp4",
        t_start_s=120.0,
    )
    obj_item = QueueItem(
        case_id="case_201",
        event_id="ev_202",
        field_name="defib_energy_v2",
        field_label="Defib Energy",
        ai_value="200",
        ai_label="200J",
        confidence=0.81,
        abstain_reason=None,
        source_event_ids=["ev_202"],
        video_uri="gs://bucket/video.mp4",
        t_start_s=45.0,
    )
    queue.enqueue(team_item)
    queue.enqueue(obj_item)

    first = queue.next_item()
    assert first is not None
    assert first.field_name == "defib_energy_v2"
    assert first.queue_class == "objective"


def test_synthetic_stream_routing_breakdown() -> None:
    """Assert routing breakdown on synthetic maximal stream."""
    stream = get_maximal_stream()
    field_values, _, _ = reduce_stream(stream)
    res = evaluate_stream_routing(field_values)

    assert res["total_fields_evaluated"] == 1879
    assert res["routed_team_q006"] == 12
    assert res["routed_validation_failed"] == 0
    assert "auto_accepted" in res
    assert "auto_accepted_pct" in res
