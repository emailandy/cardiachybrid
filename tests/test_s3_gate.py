"""
tests/test_s3_gate.py — Unit Tests for S3 Acoustic Gating at Fusion Layer.

Tests all gating invariants:
1. Abstain preserves candidate confidence and routes for review (Gold #5 uncharged defib scenario).
2. Reject downgrades confidence (max(0.10, conf * 0.40)) but never deletes the candidate (Invariant I5).
3. Confirm raises confidence and attaches acoustic evidence.
4. Cluster adjudication isolates the primary discharge candidate and downgrades competing bracket artifacts.
5. Zero n_draws filtering exists anywhere in the gate logic.
6. A transient outside the derived window (+/- 2.0s from F-009) does NOT confirm.
7. Sensor contract: adjudicate() is the call path; detect_events() full-track is not used for gating.
8. Pure mocked S3 responses (no network, no video decode).
"""

import inspect
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from pipeline import s3_gate
from pipeline.s3_gate import (
    adjudicate_candidate_cluster,
    cluster_candidates,
    gate_shock_candidates,
    GatingDecision,
    DERIVED_CHARGE_TONE_WINDOW_S,
)
from sensors.s3_defib import DefibEvent, DefibVerdict, S3DefibDetector


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

    mock_verdicts = {
        876.5: DefibVerdict(
            confirmed=False,
            candidate_t=876.5,
            event=None,
            reason="No defibrillation_shock confirmed within candidate window",
        )
    }

    gated = gate_shock_candidates(candidates, precomputed_verdicts=mock_verdicts)

    assert len(gated) == 1
    g = gated[0]
    assert g["s3_verdict"] == "abstained"
    assert g["confidence"] == 1.0  # Preserved unchanged!
    assert g["original_confidence"] == 1.0
    assert g["original_timestamp_s"] == 876.5
    assert g["needs_review"] is True
    assert "acoustic abstention" in g["s3_reason"]


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

    mock_verdicts = {
        257.0: DefibVerdict(confirmed=False, candidate_t=257.0, event=None, reason="No shock confirmed"),
        856.0: DefibVerdict(confirmed=False, candidate_t=856.0, event=None, reason="No shock confirmed"),
    }

    gated = gate_shock_candidates(candidates, precomputed_verdicts=mock_verdicts)

    assert len(gated) == 2  # Zero candidates deleted!
    for g in gated:
        assert g["s3_verdict"] == "rejected"
        assert g["confidence"] == 0.40  # Downgraded from 1.00
        assert g["original_confidence"] == 1.00
        assert g["needs_review"] is True
        assert "Rejected: S3 adjudicate confirmed no acoustic shock" in g["s3_reason"]


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
        timestamp_s=740.5,
        charge_start_s=737.5,
        charge_end_s=740.3,
        slope_hz_per_s=191.3,
        r_value=0.88,
        transient_ratio=8.5,
        confidence=0.95,
    )
    mock_verdicts = {
        740.0: DefibVerdict(confirmed=True, candidate_t=740.0, event=mock_s3_event, reason="Confirmed")
    }

    gated = gate_shock_candidates(candidates, precomputed_verdicts=mock_verdicts)

    assert len(gated) == 1
    g = gated[0]
    assert g["s3_verdict"] == "confirmed"
    assert g["confidence"] >= 0.95  # Raised confidence
    assert g["original_confidence"] == 0.85
    assert g["needs_review"] is False
    assert g["attributes"]["s3_transient_s"] == 740.5
    assert g["attributes"]["s3_slope_hz_s"] == 191.3
    assert g["attributes"]["s3_transient_ratio"] == 8.5
    assert "Confirmed by S3 acoustic discharge transient" in g["s3_reason"]


def test_transient_outside_derived_window_does_not_confirm():
    """
    Physical Derivation (F-009): An acoustic transient > 2.0s away from a candidate
    (e.g. 15.0s gap at 794s vs 779.01s) is physically disconnected and must NOT confirm.
    """
    detector = S3DefibDetector()
    # Adjudicate candidate at 794.0s with derived window_s=4.0s (+/- 2.0s)
    # Mock detect_events returning transient at 779.01s
    mock_event = DefibEvent(
        event_type="defibrillation_shock",
        timestamp_s=779.01,
        charge_start_s=777.3,
        charge_end_s=778.5,
        slope_hz_per_s=271.5,
        r_value=0.63,
        transient_ratio=6.4,
        confidence=0.70,
    )
    detector.detect_events = MagicMock(return_value=[mock_event])

    # Candidate at 794.0s is 14.99s away from 779.01s (outside half-width of 6.5s)
    verdict = detector.adjudicate("mock_audio.wav", candidate_t=794.0, window_s=DERIVED_CHARGE_TONE_WINDOW_S)
    assert verdict.confirmed is False
    assert "No defibrillation_shock confirmed" in verdict.reason


def test_gate_uses_adjudicate_contract_not_full_track_scan():
    """
    Sensor Contract (F-014): Asserts that gate_shock_candidates calls detector.adjudicate()
    per candidate rather than invoking full-track detect_events().
    """
    detector = S3DefibDetector()
    detector.adjudicate = MagicMock(
        return_value=DefibVerdict(confirmed=False, candidate_t=740.0, event=None, reason="No shock")
    )
    detector.detect_events = MagicMock(side_effect=AssertionError("detect_events() full-track must NOT be called by gate!"))

    candidates = [{"event_id": "c1", "event_type": "defibrillation_shock", "timestamp_s": 740.0, "confidence": 1.0}]
    gated = gate_shock_candidates(candidates, audio_or_video_path="mock.wav", s3_detector=detector)

    assert len(gated) == 1
    assert detector.adjudicate.called
    assert detector.detect_events.call_count == 0


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

    mock_verdicts = {
        736.0: DefibVerdict(confirmed=False, candidate_t=736.0, event=None, reason="No shock"),
        740.0: DefibVerdict(confirmed=True, candidate_t=740.0, event=mock_s3_event, reason="Confirmed"),
        744.0: DefibVerdict(confirmed=False, candidate_t=744.0, event=None, reason="No shock"),
    }

    gated = gate_shock_candidates(candidates, precomputed_verdicts=mock_verdicts)

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
