"""
tests/test_s3_gate.py — Unit Tests for S3 Acoustic Gating at Fusion Layer.

Tests all five gating invariants:
1. Abstain preserves candidate confidence and routes for review (Gold #5 uncharged defib scenario).
2. Reject downgrades confidence (max(0.10, conf * 0.40)) but never deletes the candidate (Invariant I5).
3. Confirm raises confidence and attaches acoustic evidence.
4. Cluster adjudication isolates the primary discharge candidate and downgrades competing bracket artifacts.
5. Zero n_draws filtering exists anywhere in the gate logic.
6. Pure mocked S3 responses (no network, no video decode).
"""

import inspect
from pathlib import Path
import pytest

from pipeline import s3_gate
from pipeline.s3_gate import (
    adjudicate_candidate_cluster,
    cluster_candidates,
    gate_shock_candidates,
    GatingDecision,
)
from sensors.s3_defib import DefibEvent


def test_abstain_preserves_candidate_confidence_gold5_scenario():
    """
    Critical Test: S3 abstaining on an uncharged simulator defibrillator (Gold #5)
    or uncharacterized acoustic region must PRESERVE candidate confidence at 1.0,
    attach verdict='abstained', and route for review, rather than rejecting or deleting.
    """
    candidates = [
        {
            "event_id": "shock_gold5",
            "event_type": "defibrillation_shock",
            "timestamp_s": 876.5,
            "confidence": 1.0,
            "attributes": {"n_draws": 1, "clinical_phase": "phase_5"},
        }
    ]

    # No acoustic events in uncharged defib region
    gated = gate_shock_candidates(candidates, precomputed_s3_events=[])

    assert len(gated) == 1
    g = gated[0]
    assert g["s3_verdict"] == "abstained"
    assert g["confidence"] == 1.0  # Preserved unchanged!
    assert g["original_confidence"] == 1.0
    assert g["original_timestamp_s"] == 876.5
    assert g["needs_review"] is True
    assert "uncharged simulator defib" in g["s3_reason"]


def test_reject_downgrades_confidence_never_deletes():
    """
    Invariant I5: A false positive speech/pulse-check artifact (e.g. 257.0s or 856.0s)
    must be downgraded to confidence 0.40 and marked for review, but NEVER silently deleted.
    """
    candidates = [
        {
            "event_id": "fp_pulse_check",
            "event_type": "defibrillation_shock",
            "timestamp_s": 257.0,
            "confidence": 1.0,
            "attributes": {"n_draws": 1},
        },
        {
            "event_id": "fp_856_consensus",
            "event_type": "defibrillation_shock",
            "timestamp_s": 856.0,
            "confidence": 1.0,
            "attributes": {"n_draws": 3},  # Max consensus, still wrong
        },
    ]

    gated = gate_shock_candidates(candidates, precomputed_s3_events=[])

    assert len(gated) == 2  # Zero candidates deleted!
    for g in gated:
        assert g["s3_verdict"] == "rejected"
        assert g["confidence"] == 0.40  # Downgraded from 1.00
        assert g["original_confidence"] == 1.00
        assert g["needs_review"] is True
        assert "Rejected: no acoustic defibrillation shock confirmed" in g["s3_reason"]


def test_confirm_raises_confidence_and_attaches_evidence():
    """
    When S3 confirms an acoustic discharge transient, the candidate confidence is raised/boosted,
    needs_review is False, and all acoustic metrics are attached as evidence.
    """
    candidates = [
        {
            "event_id": "shock_cand_740",
            "event_type": "defibrillation_shock",
            "timestamp_s": 740.0,
            "confidence": 0.85,
            "attributes": {},
        }
    ]

    mock_s3_event = DefibEvent(
        event_type="defibrillation_shock",
        timestamp_s=742.21,
        charge_start_s=739.3,
        charge_end_s=742.1,
        slope_hz_per_s=191.3,
        r_value=0.88,
        transient_ratio=8.5,
        confidence=0.95,
    )

    gated = gate_shock_candidates(candidates, precomputed_s3_events=[mock_s3_event])

    assert len(gated) == 1
    g = gated[0]
    assert g["s3_verdict"] == "confirmed"
    assert g["confidence"] >= 0.95  # Raised confidence
    assert g["original_confidence"] == 0.85
    assert g["needs_review"] is False
    assert g["attributes"]["s3_transient_s"] == 742.21
    assert g["attributes"]["s3_slope_hz_s"] == 191.3
    assert g["attributes"]["s3_transient_ratio"] == 8.5
    assert "Confirmed by S3 acoustic discharge transient" in g["s3_reason"]


def test_cluster_adjudication_isolates_discharge_among_neighbors():
    """
    When verbal artifacts bracket a real shock (e.g. 736s pre-shock verbal call, 740s shock,
    744s post-shock call), cluster adjudication confirms the single candidate matching the
    discharge and downgrades the competing bracket artifacts.
    """
    candidates = [
        {"event_id": "c1_preshock", "event_type": "defibrillation_shock", "timestamp_s": 736.0, "confidence": 1.0},
        {"event_id": "c2_discharge", "event_type": "defibrillation_shock", "timestamp_s": 740.0, "confidence": 1.0},
        {"event_id": "c3_postshock", "event_type": "defibrillation_shock", "timestamp_s": 744.0, "confidence": 1.0},
    ]

    mock_s3_event = DefibEvent(
        event_type="defibrillation_shock",
        timestamp_s=740.5,
        charge_start_s=737.5,
        charge_end_s=740.3,
        slope_hz_per_s=210.0,
        r_value=0.90,
        transient_ratio=9.2,
        confidence=0.97,
    )

    gated = gate_shock_candidates(candidates, precomputed_s3_events=[mock_s3_event])

    assert len(gated) == 3
    # c2 at 740.0s is closest to 740.5s -> CONFIRMED
    g_c2 = next(g for g in gated if g["event_id"] == "c2_discharge")
    assert g_c2["s3_verdict"] == "confirmed"
    assert g_c2["confidence"] >= 0.95
    assert g_c2["needs_review"] is False

    # c1 at 736.0s and c3 at 744.0s are competing bracket artifacts -> REJECTED
    g_c1 = next(g for g in gated if g["event_id"] == "c1_preshock")
    g_c3 = next(g for g in gated if g["event_id"] == "c3_postshock")
    assert g_c1["s3_verdict"] == "rejected"
    assert g_c1["confidence"] == 0.40
    assert g_c1["needs_review"] is True
    assert "competing verbal/motion bracket artifact" in g_c1["s3_reason"]

    assert g_c3["s3_verdict"] == "rejected"
    assert g_c3["confidence"] == 0.40
    assert g_c3["needs_review"] is True
    assert "competing verbal/motion bracket artifact" in g_c3["s3_reason"]


def test_no_n_draws_threshold_in_gate_source():
    """
    Assert by static inspection that pipeline/s3_gate.py contains ZERO references
    to n_draws filtering or thresholding (e.g. n_draws >= 2).
    """
    gate_source = inspect.getsource(s3_gate)
    assert "n_draws >=" not in gate_source
    assert "n_draws ==" not in gate_source
    assert "n_draws >" not in gate_source
    assert "min_draws" not in gate_source


def test_clustering_partition():
    """
    Verifies temporal clustering splits candidates separated by > neighborhood_s.
    """
    candidates = [
        {"timestamp_s": 162.0},
        {"timestamp_s": 166.2},
        {"timestamp_s": 257.0},
        {"timestamp_s": 266.2},
        {"timestamp_s": 386.0},
    ]

    clusters = cluster_candidates(candidates, neighborhood_s=15.0)
    assert len(clusters) == 3
    assert len(clusters[0]) == 2  # [162.0, 166.2]
    assert len(clusters[1]) == 2  # [257.0, 266.2]
    assert len(clusters[2]) == 1  # [386.0]
