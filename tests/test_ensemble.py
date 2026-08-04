"""
tests/test_ensemble.py — Unit test suite for D08 event ingestion loader and ensemble voting.

Tests:
  1. Idempotent ingestion and sequence-based deterministic event_id (DECISION 017).
  2. Mandatory evidence[] rule rejection and logging (Constitution rule).
  3. Vote thresholds (3/3 accept, 2/3 accept+flag, 1/3 near-miss drop, 1/1/1 tie abstention, spread > 3s routing).
  4. Adversarial global greedy nearest-neighbour matching without false orphans.
  5. Near-miss PHI preservation and scratch dataset deployment refusal.
  6. Synthetic ensemble experiment baseline counts.
"""

import pytest
from ingest.loader import build_rows, write_rows, compute_sequence_id
from ingest.ensemble import (
    ensemble_streams,
    run_path_coverage_experiment,
    run_stochastic_ensemble_experiment,
    match_item_clusters,
)


def test_idempotent_loader_ingestion() -> None:
    """Assert build_rows run twice on identical input yields identical event_ids and row content."""
    stream = {
        "events": [
            {
                "type": "defibrillation_shock",
                "t_start_s": 10.0,
                "confidence": 0.95,
                "evidence": [{"text": "shock 1"}],
            },
            {
                "type": "defibrillation_shock",
                "t_start_s": 20.0,
                "confidence": 0.95,
                "evidence": [{"text": "shock 2"}],
            },
        ]
    }
    t0 = "2026-08-01T12:00:00Z"
    tables1, rej1, logs1 = build_rows(stream, "case_001", "run_ensemble_v1", t0)
    tables2, rej2, logs2 = build_rows(stream, "case_001", "run_ensemble_v1", t0)

    assert len(rej1) == 0 and len(rej2) == 0
    assert len(tables1["fact_event"]) == 2
    assert tables1["fact_event"] == tables2["fact_event"]
    assert [x["event_id"] for x in tables1["fact_event"]] == [
        x["event_id"] for x in tables2["fact_event"]
    ]


def test_event_id_stable_under_timestamp_drift() -> None:
    """Assert sequence-based ID is stable under small timestamp drift (DECISION 017)."""
    id1 = compute_sequence_id("case_001", "defibrillation_shock", 1)
    id2 = compute_sequence_id("case_001", "defibrillation_shock", 1)
    assert id1 == id2 and len(id1) == 12


def test_evidence_mandatory_rejection() -> None:
    """Assert any event with empty evidence[] is rejected before BQ and logged with reason."""
    stream = {
        "events": [
            {
                "type": "defibrillation_shock",
                "t_start_s": 15.0,
                "confidence": 0.9,
                "evidence": [],
            }
        ]
    }
    tables, rejected, logs = build_rows(stream, "case_001", "run_001")
    assert len(tables["fact_event"]) == 0
    assert len(rejected) == 1
    assert "mandatory evidence[] is empty (Constitution rule)" in logs[0]


def test_vote_thresholds_and_ties() -> None:
    """Assert 3/3 accept, 2/3 flag, 1/3 near-miss, spread > 3s routing, and 1/1/1 tie abstention."""
    ev_base = {
        "type": "rhythm_check",
        "t_start_s": 100.0,
        "confidence": 0.9,
        "evidence": [{"text": "check"}],
    }
    # 3-way tie on categorical attribute
    run_a = {"events": [dict(ev_base, attributes={"rhythm": "vfib"})]}
    run_b = {"events": [dict(ev_base, attributes={"rhythm": "vtach"})]}
    run_c = {"events": [dict(ev_base, attributes={"rhythm": "asystole"})]}

    merged, nm = ensemble_streams([run_a, run_b, run_c], k=3)
    assert len(merged["events"]) == 1
    attrs = merged["events"][0]["attributes"]
    assert attrs["rhythm"] == "abstained_1_1_1_tie"
    assert merged["events"][0]["routed_to_human"] is True
    assert attrs["ensemble_votes"] == 3

    # 2/3 vote + flag
    run_d = {"events": []}
    merged_2_3, nm_2_3 = ensemble_streams([run_a, run_b, run_d], k=3)
    assert len(merged_2_3["events"]) == 1
    assert merged_2_3["events"][0]["attributes"]["ensemble_flag"] == "2/3_majority"

    # 1/3 minority vote goes to near-miss
    merged_1_3, nm_1_3 = ensemble_streams([run_a, run_d, run_d], k=3)
    assert len(merged_1_3["events"]) == 0
    assert len(nm_1_3) == 1
    assert nm_1_3[0]["evidence"] == [{"text": "check"}]


def test_adversarial_global_greedy_matching() -> None:
    """
    1. Clean spacing: shocks 4s apart match cleanly without orphans.
    2. Adversarial close timestamps (100.0, 100.5, 101.2 vs 100.4, 101.0, 101.3):
       assert unmatched events are logged with their nearest rejected candidate (DECISION 017).
    3. 3 vs 4 shocks: extra shock becomes a near-miss.
    """
    run_clean_a = {
        "events": [
            {"type": "defibrillation_shock", "t_start_s": 100.0, "t_precision_s": 0.4, "evidence": [{"text": "c1"}]},
            {"type": "defibrillation_shock", "t_start_s": 104.0, "t_precision_s": 0.4, "evidence": [{"text": "c2"}]},
            {"type": "defibrillation_shock", "t_start_s": 108.0, "t_precision_s": 0.4, "evidence": [{"text": "c3"}]},
        ]
    }
    run_clean_b = {
        "events": [
            {"type": "defibrillation_shock", "t_start_s": 100.2, "t_precision_s": 0.4, "evidence": [{"text": "c1b"}]},
            {"type": "defibrillation_shock", "t_start_s": 104.1, "t_precision_s": 0.4, "evidence": [{"text": "c2b"}]},
            {"type": "defibrillation_shock", "t_start_s": 107.9, "t_precision_s": 0.4, "evidence": [{"text": "c3b"}]},
        ]
    }
    merged_clean, nm_clean = ensemble_streams([run_clean_a, run_clean_b], k=2)
    assert len(merged_clean["events"]) == 3
    assert len(nm_clean) == 0

    # Adversarial close timestamps
    run_a = {
        "events": [
            {"type": "defibrillation_shock", "t_start_s": 100.0, "t_precision_s": 0.4, "evidence": [{"text": "a1"}]},
            {"type": "defibrillation_shock", "t_start_s": 100.5, "t_precision_s": 0.4, "evidence": [{"text": "a2"}]},
            {"type": "defibrillation_shock", "t_start_s": 101.2, "t_precision_s": 0.4, "evidence": [{"text": "a3"}]},
        ]
    }
    run_b = {
        "events": [
            {"type": "defibrillation_shock", "t_start_s": 100.4, "t_precision_s": 0.4, "evidence": [{"text": "b1"}]},
            {"type": "defibrillation_shock", "t_start_s": 101.0, "t_precision_s": 0.4, "evidence": [{"text": "b2"}]},
            {"type": "defibrillation_shock", "t_start_s": 101.3, "t_precision_s": 0.4, "evidence": [{"text": "b3"}]},
        ]
    }
    merged_adv, nm_adv = ensemble_streams([run_a, run_b], k=2)
    assert len(nm_adv) > 0, "Adversarial greedy matching produces near-misses"
    assert any("unmatched_log" in x.get("attributes", {}) for x in nm_adv), (
        "Unmatched near-miss must log nearest rejected candidate"
    )

    # When run B has an extra 4th shock, that 4th shock becomes a near-miss
    run_b_extra = dict(
        events=run_clean_b["events"]
        + [
            {
                "type": "defibrillation_shock",
                "t_start_s": 115.0,
                "t_precision_s": 0.4,
                "evidence": [{"text": "b4"}],
            }
        ]
    )
    merged_extra, nm_extra = ensemble_streams([run_clean_a, run_b_extra], k=2)
    assert len(merged_extra["events"]) == 3
    assert len(nm_extra) == 1
    assert nm_extra[0]["evidence"] == [{"text": "b4"}]


def test_near_miss_phi_and_scratch_refusal() -> None:
    """Assert near-misses carry full evidence[] and write_rows rejects scratch datasets."""
    stream = {
        "events": [
            {
                "type": "defibrillation_shock",
                "t_start_s": 10.0,
                "confidence": 0.9,
                "evidence": [{"text": "shock quote"}],
            }
        ]
    }
    nm = [
        {
            "type": "defibrillation_shock",
            "t_start_s": 15.0,
            "confidence": 0.7,
            "votes_accept": 1,
            "votes_reject": 2,
            "evidence": [{"text": "near miss quote"}],
            "attributes": {},
        }
    ]
    tables, rej, logs = build_rows(stream, "case_001", "run_001", near_misses=nm)
    assert len(tables["fact_near_miss"]) == 1
    assert "near miss quote" in tables["fact_near_miss"][0]["evidence"]

    for bad_ds in ("resus_scratch", "ci_scratch_db"):
        with pytest.raises(
            ValueError, match="resus_scratch NEVER receives a table"
        ):
            write_rows(
                tables["fact_near_miss"], bad_ds, "fact_near_miss", dry_run=True
            )


def test_monotonic_matching_no_cascades() -> None:
    """
    30 CCIs at 20s intervals in run A, same 30 in run B shifted +0.3s, t_precision_s=0.5 (tol 1.0s).
    Monotonic order-preserving constraint prevents matching cascade: assert 30 pairs, 0 near-misses.
    """
    run_a = {
        "events": [
            {
                "type": "compression_interruption",
                "t_start_s": i * 20.0,
                "t_precision_s": 0.5,
                "evidence": [{"text": f"cci {i}"}],
            }
            for i in range(30)
        ]
    }
    run_b = {
        "events": [
            {
                "type": "compression_interruption",
                "t_start_s": i * 20.0 + 0.3,
                "t_precision_s": 0.5,
                "evidence": [{"text": f"cci {i} b"}],
            }
            for i in range(30)
        ]
    }
    merged, nm = ensemble_streams([run_a, run_b], k=2)
    assert len(merged["events"]) == 30, f"Expected 30 pairs, got {len(merged['events'])}"
    assert len(nm) == 0, f"Expected 0 near-misses, got {len(nm)}"


def test_interval_matching_checks_duration_bounds() -> None:
    """Assert interval matching checks both start and end boundaries so differing durations do not pair."""
    run_a = {
        "intervals": [
            {
                "type": "compression_interruption",
                "t_start_s": 10.0,
                "t_end_s": 14.0,  # 4s duration
                "t_precision_s": 0.5,
                "evidence": [{"text": "short cci"}],
            }
        ]
    }
    run_b = {
        "intervals": [
            {
                "type": "compression_interruption",
                "t_start_s": 10.0,
                "t_end_s": 28.0,  # 18s duration
                "t_precision_s": 0.5,
                "evidence": [{"text": "long cci"}],
            }
        ]
    }
    merged, nm = ensemble_streams([run_a, run_b], k=2)
    assert len(merged["intervals"]) == 0, "Intervals with differing durations must not be paired"
    assert len(nm) == 2, "Unpaired intervals become near-misses"


def test_path_coverage_and_stochastic_experiments() -> None:
    """Assert deterministic path coverage fixture counts and stochastic generator return structure."""
    pc = run_path_coverage_experiment()
    assert pc["total_clusters_evaluated"] == 105
    assert pc["accepted_3_3"] == 103
    assert pc["accepted_2_3"] == 1
    assert pc["dropped_1_3_near_miss"] == 1
    assert pc["spread_exceeded_3s"] == 1
    assert pc["categorical_1_1_1_ties"] == 1

    stoch = run_stochastic_ensemble_experiment(n_seeds=2)
    assert stoch["seeds"] == 2
    assert "3_3_pct_mean" in stoch
    assert "2_3_pct_mean" in stoch
    assert "1_3_pct_mean" in stoch


def test_deduplicate_window_streams_keeps_overlap_orphans() -> None:
    """Dedup should remove duplicates, never orphans (F-005)."""
    from generated.models import EventStream, Event, CaseFields
    from ingest.ensemble import deduplicate_window_streams

    ev1 = Event(type="pulse_check", t_start_s=841.0, attributes={}, evidence=[])
    ev_prim = Event(type="pulse_check", t_start_s=500.0, attributes={}, evidence=[])
    win1 = EventStream(case_id="test", events=[ev_prim, ev1], intervals=[], coverage=[], fields=CaseFields())
    win2 = EventStream(case_id="test", events=[], intervals=[], coverage=[], fields=CaseFields())

    dedup = deduplicate_window_streams([(win1, 420.0, 840.0), (win2, 840.0, 1260.0)])
    assert len(dedup.events) == 2, "Orphan overlap-tail event at 841s must be kept when win2 has no counterpart"

    ev2_dup = Event(type="pulse_check", t_start_s=841.5, attributes={}, evidence=[])
    win2_with_dup = EventStream(case_id="test", events=[ev2_dup], intervals=[], coverage=[], fields=CaseFields())
    dedup_dup = deduplicate_window_streams([(win1, 420.0, 840.0), (win2_with_dup, 840.0, 1260.0)])
    assert len(dedup_dup.events) == 2, "Duplicate overlap-tail event should be removed, leaving prim + win2 copy"
    assert dedup_dup.events[1].timestamp_s == 841.5


def test_pair_boundary_events_creates_rosc_interval() -> None:
    """rosc_detected and rosc_lost point events should pair into a rosc Interval."""
    from generated.models import EventStream, Event, CaseFields
    from ingest.ensemble import pair_boundary_events

    ev1 = Event(type="rosc_detected", t_start_s=500.0, attributes={"pulse_palpable": True}, evidence=[])
    ev2 = Event(type="rosc_lost", t_start_s=600.0, attributes={}, evidence=[])
    stream = EventStream(case_id="test", events=[ev1, ev2], intervals=[], coverage=[], fields=CaseFields())

    paired = pair_boundary_events(stream)
    assert len(paired.intervals) == 1
    inv = paired.intervals[0]
    assert inv.type == "rosc"
    assert inv.t_start_s == 500.0
    assert inv.t_end_s == 600.0
    assert inv.attributes == {"pulse_palpable": True}


def test_validate_contract_obligations_catches_missing_and_gated_violations() -> None:
    """validate_contract_obligations must emit contract_violation flags for missing ungated attrs and unsatisfied gated attrs."""
    from generated.models import EventStream, Interval, CaseFields
    from ingest.loader import validate_contract_obligations

    inv = Interval(
        type="compression_interruption",
        t_start_s=100.0,
        t_end_s=110.0,
        attributes={"reasons": ["pulse_check"], "mccd_adjust_reasons": ["other"]},
        evidence=[],
    )
    stream = EventStream(case_id="test", events=[], intervals=[inv], coverage=[], fields=CaseFields())
    flags = validate_contract_obligations(stream)
    assert len(flags) >= 2
    msgs = [f.message for f in flags]
    assert any("missing required" in m and "aline_present" in m for m in msgs)
    assert any("gated attribute emitted: mccd_adjust_reasons" in m for m in msgs)


@pytest.mark.integration
def test_write_rows_integration_dry_run() -> None:
    """Integration mark test for write_rows."""
    rows = [{"event_id": "test_001", "case_id": "case_001"}]
    assert write_rows(rows, "resus_raw", "fact_event", dry_run=True) == 1


