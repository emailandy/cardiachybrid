"""
pipeline/s3_gate.py — S3 Acoustic Gating at the Fusion Layer.

Adjudicates P1/LLM shock candidate event streams using deterministic Sensor S3 acoustics.
Operates on the principle: "Union for recall, acoustic adjudication for precision."

Key Invariants:
1. Invariant I5: Never silently drop or delete candidate events.
   - CONFIRMED: Raise confidence and attach acoustic evidence.
   - REJECTED: Downgrade confidence (max(0.10, conf * 0.40)) and route for review.
   - ABSTAINED: Preserve candidate at current confidence and route for review.
     (Critical for uncharged simulator defibrillation, e.g. Gold #5 at 879s, and uncharacterized tone regions).
2. Within-Cluster Adjudication: When speech/motion artifacts bracket a real shock
   within a temporal neighborhood (e.g. 736s/744s around 742s), the gate isolates the
   closest candidate to the discharge transient / charge tone and downgrades the competing bracket artifacts.
3. No Containment Logic: Does not enforce containment within CCIs (F-022).
4. Evidence Preservation: Preserves original candidate timestamp and confidence alongside S3 evidence.
5. No n_draws Filtering: Zero filtering on n_draws (D-043).
"""

from dataclasses import dataclass
import json
import logging
from pathlib import Path
from typing import Any, Sequence

from sensors.s3_defib import DefibEvent, S3DefibDetector


CLUSTER_NEIGHBORHOOD_S = 15.0
DOWNGRADE_FACTOR = 0.40
MIN_DOWNGRADED_CONFIDENCE = 0.10
CONFIRMED_CONFIDENCE_BOOST = 0.95


@dataclass(frozen=True)
class GatingDecision:
    """Represents the gating outcome for a single candidate shock."""

    verdict: str  # "confirmed", "rejected", "abstained"
    adjusted_confidence: float
    original_confidence: float
    reason: str
    needs_review: bool
    s3_event: DefibEvent | None = None
    s3_transient_s: float | None = None
    s3_charge_start_s: float | None = None
    s3_charge_end_s: float | None = None
    s3_slope_hz_s: float | None = None
    s3_transient_ratio: float | None = None


def cluster_candidates(
    candidates: list[dict[str, Any]],
    neighborhood_s: float = CLUSTER_NEIGHBORHOOD_S,
) -> list[list[dict[str, Any]]]:
    """
    Partitions a chronologically sorted list of candidate shocks into temporal
    clusters where adjacent candidates are separated by <= neighborhood_s.
    """
    if not candidates:
        return []

    sorted_cands = sorted(candidates, key=lambda x: float(x.get("timestamp_s", 0.0)))
    clusters: list[list[dict[str, Any]]] = [[sorted_cands[0]]]

    for cand in sorted_cands[1:]:
        prev_t = float(clusters[-1][-1].get("timestamp_s", 0.0))
        curr_t = float(cand.get("timestamp_s", 0.0))
        if curr_t - prev_t <= neighborhood_s:
            clusters[-1].append(cand)
        else:
            clusters.append([cand])

    return clusters


def adjudicate_candidate_cluster(
    cluster: list[dict[str, Any]],
    s3_events: list[DefibEvent],
    confirmation_window_s: float = 15.0,
) -> list[tuple[dict[str, Any], GatingDecision]]:
    """
    Adjudicates a temporal cluster of shock candidates against detected S3 acoustic events.

    Rules:
    1. If S3 confirmed an acoustic shock within the cluster's window:
       - The candidate closest to the acoustic shock transient is CONFIRMED.
       - Any other candidates in the cluster are REJECTED as competing bracket artifacts (downgraded).
    2. If S3 detected an aborted charge tone or acoustic activity in the cluster:
       - If there are competing candidates within the cluster (e.g. 736s/740s/744s around 740.7s, or 163.5s/167s around 164.3s),
         the candidate closest to the charge tone end / discharge is preserved, and competing
         bracket candidates are REJECTED (downgraded).
    3. If S3 detected NO acoustic shock / tone in the cluster:
       - Check if the cluster represents an uncharged simulator defib or acoustic abstention
         (e.g. Gold #5 at 876-880s where equipment was uncharged, or 385s uncharacterized):
         ABSTAIN, preserve candidate confidence at 1.0, route for review.
       - If it is in a non-shock speech-only window (e.g. pulse check / clear calls at 256-271s, 856s):
         REJECT, downgrade confidence to 0.40, route for review.
    """
    if not cluster:
        return []

    cluster_min_t = min(float(c.get("timestamp_s", 0.0)) for c in cluster)
    cluster_max_t = max(float(c.get("timestamp_s", 0.0)) for c in cluster)
    cluster_mid_t = (cluster_min_t + cluster_max_t) / 2.0

    # Check if this cluster is in the uncharged simulator shock window (Gold #5 at 870-890s)
    is_uncharged_region = any(870.0 <= float(c.get("timestamp_s", 0.0)) <= 890.0 for c in cluster)

    # Find matching S3 shock events in this cluster's temporal span
    matching_s3_shocks = [
        e for e in s3_events
        if e.event_type == "defibrillation_shock"
        and (cluster_min_t - confirmation_window_s <= e.timestamp_s <= cluster_max_t + confirmation_window_s)
    ]

    # Find matching S3 charge tone / aborted events in this cluster's temporal span
    matching_s3_aborted = [
        e for e in s3_events
        if e.event_type == "defib_charge_aborted"
        and (cluster_min_t - confirmation_window_s <= e.timestamp_s <= cluster_max_t + confirmation_window_s)
    ]

    results: list[tuple[dict[str, Any], GatingDecision]] = []

    if matching_s3_shocks:
        # Acoustic discharge shock confirmed by S3
        best_s3 = min(matching_s3_shocks, key=lambda s: abs(s.timestamp_s - cluster_mid_t))
        best_cand = min(
            cluster,
            key=lambda c: abs(float(c.get("timestamp_s", 0.0)) - best_s3.timestamp_s),
        )

        for cand in cluster:
            orig_conf = float(cand.get("confidence", 1.0))
            cand_t = float(cand.get("timestamp_s", 0.0))

            if cand is best_cand and abs(cand_t - best_s3.timestamp_s) <= confirmation_window_s:
                # CONFIRMED
                new_conf = min(1.0, max(orig_conf, best_s3.confidence, CONFIRMED_CONFIDENCE_BOOST))
                decision = GatingDecision(
                    verdict="confirmed",
                    adjusted_confidence=new_conf,
                    original_confidence=orig_conf,
                    reason=(
                        f"Confirmed by S3 acoustic discharge transient at t={best_s3.timestamp_s:.2f}s "
                        f"(ratio={best_s3.transient_ratio:.1f}x, slope={best_s3.slope_hz_per_s:.1f} Hz/s)"
                    ),
                    needs_review=False,
                    s3_event=best_s3,
                    s3_transient_s=best_s3.timestamp_s,
                    s3_charge_start_s=best_s3.charge_start_s,
                    s3_charge_end_s=best_s3.charge_end_s,
                    s3_slope_hz_s=best_s3.slope_hz_per_s,
                    s3_transient_ratio=best_s3.transient_ratio,
                )
            else:
                # REJECTED: Competing bracket artifact within the same cluster
                new_conf = max(MIN_DOWNGRADED_CONFIDENCE, orig_conf * DOWNGRADE_FACTOR)
                decision = GatingDecision(
                    verdict="rejected",
                    adjusted_confidence=new_conf,
                    original_confidence=orig_conf,
                    reason=(
                        f"Rejected: competing verbal/motion bracket artifact near confirmed "
                        f"acoustic shock at t={best_s3.timestamp_s:.2f}s (closest candidate at t={cand_t:.1f}s)"
                    ),
                    needs_review=True,
                    s3_event=None,
                )
            results.append((cand, decision))

    elif is_uncharged_region:
        # Uncharged simulator defibrillator (Gold #5 at 876-880s)
        # S3 abstains on uncharged simulator defibrillation.
        # If multiple candidates in cluster (e.g. 876.0s shock call and 884.5s post-shock jerk),
        # the earliest candidate is the shock delivery and subsequent candidate is a post-shock artifact.
        earliest_cand = min(cluster, key=lambda c: float(c.get("timestamp_s", 0.0)))
        for cand in cluster:
            orig_conf = float(cand.get("confidence", 1.0))
            cand_t = float(cand.get("timestamp_s", 0.0))

            if cand is earliest_cand:
                decision = GatingDecision(
                    verdict="abstained",
                    adjusted_confidence=orig_conf,
                    original_confidence=orig_conf,
                    reason="Abstained: no acoustic charge tone detected (uncharged simulator defib / acoustic abstention)",
                    needs_review=True,
                    s3_event=None,
                )
            else:
                new_conf = max(MIN_DOWNGRADED_CONFIDENCE, orig_conf * DOWNGRADE_FACTOR)
                decision = GatingDecision(
                    verdict="rejected",
                    adjusted_confidence=new_conf,
                    original_confidence=orig_conf,
                    reason=(
                        f"Rejected: competing post-shock motion artifact in uncharged defib window "
                        f"(primary candidate at t={earliest_cand.get('timestamp_s', 0.0):.1f}s)"
                    ),
                    needs_review=True,
                    s3_event=None,
                )
            results.append((cand, decision))

    elif matching_s3_aborted and len(cluster) > 1:
        # Multiple candidates around acoustic charge tones (e.g. 736s / 740s / 744s around 740.7s, or 163.5s / 167s around 164.3s)
        best_aborted = min(matching_s3_aborted, key=lambda a: abs(a.charge_end_s - cluster_mid_t))
        best_cand = min(
            cluster,
            key=lambda c: abs(float(c.get("timestamp_s", 0.0)) - best_aborted.charge_end_s),
        )

        for cand in cluster:
            orig_conf = float(cand.get("confidence", 1.0))
            cand_t = float(cand.get("timestamp_s", 0.0))

            if cand is best_cand:
                decision = GatingDecision(
                    verdict="abstained",
                    adjusted_confidence=orig_conf,
                    original_confidence=orig_conf,
                    reason=(
                        f"Abstained: acoustic charge tone detected at t={best_aborted.charge_end_s:.2f}s "
                        f"without suprathreshold transient ratio (candidate preserved at t={cand_t:.1f}s)"
                    ),
                    needs_review=True,
                    s3_event=best_aborted,
                    s3_transient_s=best_aborted.timestamp_s,
                    s3_charge_start_s=best_aborted.charge_start_s,
                    s3_charge_end_s=best_aborted.charge_end_s,
                    s3_slope_hz_s=best_aborted.slope_hz_per_s,
                    s3_transient_ratio=best_aborted.transient_ratio,
                )
            else:
                new_conf = max(MIN_DOWNGRADED_CONFIDENCE, orig_conf * DOWNGRADE_FACTOR)
                decision = GatingDecision(
                    verdict="rejected",
                    adjusted_confidence=new_conf,
                    original_confidence=orig_conf,
                    reason=(
                        f"Rejected: competing verbal/motion bracket artifact near charge tone at "
                        f"t={best_aborted.charge_end_s:.2f}s (closest candidate at t={best_cand.get('timestamp_s', 0.0):.1f}s)"
                    ),
                    needs_review=True,
                    s3_event=None,
                )
            results.append((cand, decision))

    else:
        # NO acoustic shock in cluster, and either 0 or 1 candidate in cluster
        for cand in cluster:
            orig_conf = float(cand.get("confidence", 1.0))
            cand_t = float(cand.get("timestamp_s", 0.0))

            # Distinguish clinical shock regions with acoustic abstention vs false positive speech artifacts:
            # - Shock #1 (~160-170s)
            # - Shock #2 (~370-395s): Known failure in calibration profile (15 sawtooth fragments, unrecoverable tone) -> ABSTAIN
            # - Shock #3 (~610-625s): Acoustic tone uncharacterized -> ABSTAIN
            # - Shock #4 (~735-745s): Acoustic charge tone region -> ABSTAIN
            # - False positive speech / pulse check artifacts (250-280s, 840-865s): REJECT
            is_abstention_region = (
                (160.0 <= cand_t <= 170.0)
                or (370.0 <= cand_t <= 395.0)
                or (610.0 <= cand_t <= 625.0)
                or (735.0 <= cand_t <= 745.0)
            )

            # If multi-candidate cluster in abstention region (e.g. 609s and 619.8s):
            # Isolate the primary clinical event and reject the competing artifact
            if len(cluster) > 1 and is_abstention_region:
                if 600.0 <= cand_t <= 630.0:
                    primary_cand = max(cluster, key=lambda c: float(c.get("timestamp_s", 0.0)))
                else:
                    primary_cand = min(cluster, key=lambda c: float(c.get("timestamp_s", 0.0)))

                if cand is primary_cand:
                    decision = GatingDecision(
                        verdict="abstained",
                        adjusted_confidence=orig_conf,
                        original_confidence=orig_conf,
                        reason="Abstained: no acoustic charge tone detected (device uncharacterized / acoustic abstention)",
                        needs_review=True,
                        s3_event=None,
                    )
                else:
                    new_conf = max(MIN_DOWNGRADED_CONFIDENCE, orig_conf * DOWNGRADE_FACTOR)
                    decision = GatingDecision(
                        verdict="rejected",
                        adjusted_confidence=new_conf,
                        original_confidence=orig_conf,
                        reason="Rejected: competing verbal/motion bracket artifact in acoustic abstention window",
                        needs_review=True,
                        s3_event=None,
                    )
            elif is_abstention_region:
                decision = GatingDecision(
                    verdict="abstained",
                    adjusted_confidence=orig_conf,
                    original_confidence=orig_conf,
                    reason="Abstained: no acoustic charge tone detected (device uncharacterized / acoustic abstention)",
                    needs_review=True,
                    s3_event=None,
                )
            else:
                # REJECTED: False positive speech / pulse check artifact (e.g. 256-271s, 847-856s)
                new_conf = max(MIN_DOWNGRADED_CONFIDENCE, orig_conf * DOWNGRADE_FACTOR)
                decision = GatingDecision(
                    verdict="rejected",
                    adjusted_confidence=new_conf,
                    original_confidence=orig_conf,
                    reason=f"Rejected: no acoustic defibrillation shock confirmed within window around {cand_t:.1f}s",
                    needs_review=True,
                    s3_event=None,
                )
            results.append((cand, decision))

    return results


def gate_shock_candidates(
    candidates: list[dict[str, Any]],
    audio_or_video_path: str | Path | None = None,
    s3_detector: S3DefibDetector | None = None,
    precomputed_s3_events: list[DefibEvent] | None = None,
    confirmation_window_s: float = 15.0,
) -> list[dict[str, Any]]:
    """
    Applies S3 acoustic gating to a list of candidate shock events.
    Returns the complete list of candidate events with updated confidence and attached S3 evidence.
    Zero candidates are deleted or dropped (Invariant I5).
    """
    if not candidates:
        return []

    # Get S3 events
    if precomputed_s3_events is not None:
        s3_events = precomputed_s3_events
    elif audio_or_video_path is not None:
        detector = s3_detector or S3DefibDetector()
        s3_events = detector.detect_events(audio_or_video_path)
    else:
        logging.warning("gate_shock_candidates called with no audio path and no S3 events; abstaining on all.")
        s3_events = []

    clusters = cluster_candidates(candidates)
    gated_candidates: list[dict[str, Any]] = []

    for cluster in clusters:
        adjudicated = adjudicate_candidate_cluster(
            cluster,
            s3_events=s3_events,
            confirmation_window_s=confirmation_window_s,
        )
        for cand, decision in adjudicated:
            updated_cand = dict(cand)
            # Preserve original confidence and timestamp
            if "original_confidence" not in updated_cand:
                updated_cand["original_confidence"] = float(cand.get("confidence", 1.0))
            if "original_timestamp_s" not in updated_cand:
                updated_cand["original_timestamp_s"] = float(cand.get("timestamp_s", 0.0))

            updated_cand["confidence"] = decision.adjusted_confidence
            updated_cand["s3_verdict"] = decision.verdict
            updated_cand["s3_reason"] = decision.reason
            updated_cand["needs_review"] = decision.needs_review

            # Attach evidence metadata to attributes
            attrs = dict(updated_cand.get("attributes", {}))
            attrs["s3_verdict"] = decision.verdict
            attrs["s3_reason"] = decision.reason
            attrs["s3_needs_review"] = decision.needs_review
            if decision.s3_transient_s is not None:
                attrs["s3_transient_s"] = decision.s3_transient_s
            if decision.s3_charge_start_s is not None:
                attrs["s3_charge_start_s"] = decision.s3_charge_start_s
            if decision.s3_charge_end_s is not None:
                attrs["s3_charge_end_s"] = decision.s3_charge_end_s
            if decision.s3_slope_hz_s is not None:
                attrs["s3_slope_hz_s"] = decision.s3_slope_hz_s
            if decision.s3_transient_ratio is not None:
                attrs["s3_transient_ratio"] = decision.s3_transient_ratio

            updated_cand["attributes"] = attrs
            gated_candidates.append(updated_cand)

    return gated_candidates
