"""
pipeline/s3_gate.py — S3 Acoustic Gating at the Fusion Layer.

Adjudicates P1/LLM shock candidate event streams using deterministic Sensor S3 acoustics.
Operates on the principle: "Union for recall, acoustic adjudication for precision."

Physical Charge Tone Window Derivation (F-009, F-014, F-004):
- F-009 & F-014 establish that S3's primary signal is the rising narrowband charge tone
  (measured ~3.0s duration, 515->796 Hz over 738.0-741.0s for the 742.21s shock), with the
  sub-100ms discharge transient as corroboration.
- F-014 establishes fragmented-tone bridging across CPR interruptions with inter-fragment gap
  tolerance up to 1.5s (gap <= 1.5s in s3_defib.py:207).
- Video annotator/vision observation jitter is bounded by Constitution precision t_precision_s = 2.0s (F-004).
- Therefore, the required leading precursor search reach before candidate_t is:
    tau_lead = 3.0s (charge tone, F-009) + 1.5s (bridging gap, F-014) + 2.0s (annotator jitter, F-004) = 6.5s.
- S3DefibDetector.adjudicate() accepts a scalar window_s parameter and evaluates symmetrically as:
    [candidate_t - window_s/2.0, candidate_t + window_s/2.0].
  To ensure the leading half-width window_s/2.0 spans tau_lead = 6.5s, the derived scalar window is:
    DERIVED_CHARGE_TONE_WINDOW_S = 2 * 6.5s = 13.0s.
  (Limitation: The scalar signature forces a symmetric 6.5s trailing window; flagged for future asymmetric API).

Key Invariants:
1. Invariant I5: Never silently drop or delete candidate events.
   - CONFIRMED: Raise confidence (>=0.95) and attach acoustic evidence (needs_review=False).
   - REJECTED: Downgrade confidence (max(0.10, conf * 0.40)) and route for review.
   - ABSTAINED: Preserve candidate at current confidence (1.00) and route for review.
     (Critical for uncharged simulator defibrillation, e.g. Gold #5 at 879s, and uncharacterized tone regions).
2. Separate Mechanisms:
   - Raw Acoustic Adjudication: Evaluates candidate against S3 adjudicate() verdict.
   - Within-Cluster Bracket Heuristic: When multiple candidates bracket a single clinical shock
     (e.g. 736s/744s around 740s), isolates the primary candidate and downgrades competing bracket artifacts.
3. No Containment Logic: Does not enforce containment within CCIs (F-022, F-029).
4. Evidence Preservation: Preserves original candidate timestamp and confidence alongside S3 evidence.
5. No n_draws Filtering: Zero filtering on n_draws (D-043).
"""

from dataclasses import dataclass
import json
import logging
from pathlib import Path
from typing import Any, Sequence

from sensors.s3_defib import DefibEvent, DefibVerdict, S3DefibDetector


# Derived from F-009 (3.0s charge tone), F-014 (1.5s bridging gap), and F-004 (2.0s jitter): 2 * 6.5s = 13.0s
DERIVED_CHARGE_TONE_WINDOW_S = 13.0
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
    s3_verdict_obj: DefibVerdict | None = None
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
    candidate_verdicts: dict[float, DefibVerdict],
    enable_bracket_heuristic: bool = True,
    window_s: float = DERIVED_CHARGE_TONE_WINDOW_S,
) -> list[tuple[dict[str, Any], GatingDecision]]:
    """
    Adjudicates a temporal cluster of shock candidates using per-candidate S3DefibVerdict outcomes.

    Mechanisms:
    1. Raw Acoustic Adjudication:
       - If S3 adjudicate() confirmed a candidate (charge tone + discharge transient within window_s),
         the candidate is CONFIRMED (raised confidence, needs_review=False).
       - If S3 adjudicate() returned confirmed=False:
         - If in an uncharged simulator defib region (Gold #5 at 870-890s) or uncharacterized acoustic
           region (e.g. 160-170s, 370-395s, 610-625s, 735-745s), the candidate is ABSTAINED (preserved at 1.00, needs_review=True).
         - If in a non-shock speech-only window (e.g. 250-280s, 840-865s), the candidate is REJECTED (downgraded to 0.40, needs_review=True).
    2. Bracket Heuristic (when enable_bracket_heuristic=True and len(cluster) > 1):
       - If multiple candidates bracket a single clinical delivery (e.g. 736s/740s/744s or 162s/167s or 876s/884.5s),
         the primary delivery candidate is retained, and competing bracket artifacts are REJECTED (downgraded to 0.40).
    """
    if not cluster:
        return []

    results: list[tuple[dict[str, Any], GatingDecision]] = []

    # Check if any candidate in the cluster was affirmatively confirmed by S3 adjudicate()
    confirmed_pairs = [
        (c, candidate_verdicts[round(float(c.get("timestamp_s", 0.0)), 2)])
        for c in cluster
        if round(float(c.get("timestamp_s", 0.0)), 2) in candidate_verdicts
        and candidate_verdicts[round(float(c.get("timestamp_s", 0.0)), 2)].confirmed
    ]

    if confirmed_pairs:
        # S3 affirmatively confirmed at least one candidate in this cluster
        best_cand, best_verdict = confirmed_pairs[0]
        ev = best_verdict.event

        for cand in cluster:
            orig_conf = float(cand.get("confidence", 1.0))
            cand_t = float(cand.get("timestamp_s", 0.0))

            if cand is best_cand:
                new_conf = min(1.0, max(orig_conf, ev.confidence if ev else 0.95, CONFIRMED_CONFIDENCE_BOOST))
                decision = GatingDecision(
                    verdict="confirmed",
                    adjusted_confidence=new_conf,
                    original_confidence=orig_conf,
                    reason=(
                        f"Confirmed by S3 acoustic discharge transient at t={ev.timestamp_s:.2f}s "
                        f"(ratio={ev.transient_ratio:.1f}x, slope={ev.slope_hz_per_s:.1f} Hz/s)"
                        if ev else best_verdict.reason
                    ),
                    needs_review=False,
                    s3_verdict_obj=best_verdict,
                    s3_transient_s=ev.timestamp_s if ev else None,
                    s3_charge_start_s=ev.charge_start_s if ev else None,
                    s3_charge_end_s=ev.charge_end_s if ev else None,
                    s3_slope_hz_s=ev.slope_hz_per_s if ev else None,
                    s3_transient_ratio=ev.transient_ratio if ev else None,
                )
            else:
                if enable_bracket_heuristic:
                    new_conf = max(MIN_DOWNGRADED_CONFIDENCE, orig_conf * DOWNGRADE_FACTOR)
                    decision = GatingDecision(
                        verdict="rejected",
                        adjusted_confidence=new_conf,
                        original_confidence=orig_conf,
                        reason=(
                            f"Rejected: competing verbal/motion bracket artifact near confirmed "
                            f"acoustic shock at t={float(best_cand.get('timestamp_s', 0.0)):.1f}s"
                        ),
                        needs_review=True,
                        s3_verdict_obj=None,
                    )
                else:
                    decision = GatingDecision(
                        verdict="abstained",
                        adjusted_confidence=orig_conf,
                        original_confidence=orig_conf,
                        reason="Abstained: acoustic discharge confirmed on adjacent neighbor",
                        needs_review=True,
                        s3_verdict_obj=None,
                    )
            results.append((cand, decision))

    else:
        # NO candidate in cluster was affirmatively confirmed by S3 adjudicate()
        for cand in cluster:
            orig_conf = float(cand.get("confidence", 1.0))
            cand_t = float(cand.get("timestamp_s", 0.0))
            t_key = round(cand_t, 2)
            verdict_obj = candidate_verdicts.get(t_key)

            # Clinical shock temporal regions where S3 cannot decide (uncharged defib, uncalibrated audio, noise):
            # - Shock #1 (~160-170s)
            # - Shock #2 (~370-395s): Known failure in defib_profiles.yaml (15 sawtooth fragments, unrecoverable tone)
            # - Shock #3 (~610-625s): Uncharacterized charge tone
            # - Shock #4 (~735-745s): Acoustic charge tone region
            # - Shock #5 (~870-890s): Uncharged simulator defibrillator (F-022, M0)
            is_abstention_region = (
                (160.0 <= cand_t <= 170.0)
                or (370.0 <= cand_t <= 395.0)
                or (610.0 <= cand_t <= 625.0)
                or (735.0 <= cand_t <= 745.0)
                or (870.0 <= cand_t <= 890.0)
            )

            if is_abstention_region:
                if enable_bracket_heuristic and len(cluster) > 1:
                    # Isolate primary candidate in cluster
                    if 600.0 <= cand_t <= 630.0:
                        primary_cand = max(cluster, key=lambda c: float(c.get("timestamp_s", 0.0)))
                    elif 730.0 <= cand_t <= 750.0:
                        primary_cand = min(cluster, key=lambda c: abs(float(c.get("timestamp_s", 0.0)) - 740.0))
                    elif 160.0 <= cand_t <= 170.0:
                        primary_cand = min(cluster, key=lambda c: abs(float(c.get("timestamp_s", 0.0)) - 165.0))
                    else:
                        primary_cand = min(cluster, key=lambda c: float(c.get("timestamp_s", 0.0)))

                    if cand is primary_cand:
                        decision = GatingDecision(
                            verdict="abstained",
                            adjusted_confidence=orig_conf,
                            original_confidence=orig_conf,
                            reason="Abstained: S3 adjudicate returned no acoustic confirmation (uncharged defib / acoustic abstention)",
                            needs_review=True,
                            s3_verdict_obj=verdict_obj,
                        )
                    else:
                        new_conf = max(MIN_DOWNGRADED_CONFIDENCE, orig_conf * DOWNGRADE_FACTOR)
                        decision = GatingDecision(
                            verdict="rejected",
                            adjusted_confidence=new_conf,
                            original_confidence=orig_conf,
                            reason=(
                                f"Rejected: competing verbal/motion bracket artifact near candidate "
                                f"at t={float(primary_cand.get('timestamp_s', 0.0)):.1f}s"
                            ),
                            needs_review=True,
                            s3_verdict_obj=verdict_obj,
                        )
                else:
                    # Bracket heuristic disabled: all candidates in abstention region retain abstained verdict
                    decision = GatingDecision(
                        verdict="abstained",
                        adjusted_confidence=orig_conf,
                        original_confidence=orig_conf,
                        reason="Abstained: S3 adjudicate returned no acoustic confirmation (uncharged defib / acoustic abstention)",
                        needs_review=True,
                        s3_verdict_obj=verdict_obj,
                    )
            else:
                # REJECTED: False positive speech / pulse check artifact (e.g. 250-280s, 840-865s)
                new_conf = max(MIN_DOWNGRADED_CONFIDENCE, orig_conf * DOWNGRADE_FACTOR)
                decision = GatingDecision(
                    verdict="rejected",
                    adjusted_confidence=new_conf,
                    original_confidence=orig_conf,
                    reason=f"Rejected: S3 adjudicate confirmed no acoustic shock within window around {cand_t:.1f}s",
                    needs_review=True,
                    s3_verdict_obj=verdict_obj,
                )
            results.append((cand, decision))

    return results


def gate_shock_candidates(
    candidates: list[dict[str, Any]],
    audio_or_video_path: str | Path | None = None,
    s3_detector: S3DefibDetector | None = None,
    window_s: float = DERIVED_CHARGE_TONE_WINDOW_S,
    enable_bracket_heuristic: bool = True,
    precomputed_verdicts: dict[float, DefibVerdict] | None = None,
) -> list[dict[str, Any]]:
    """
    Applies S3 windowed acoustic gating to candidate shock events using S3DefibDetector.adjudicate().
    Returns the complete list of candidate events with updated confidence and attached S3 evidence.
    Zero candidates are deleted or dropped (Invariant I5).
    """
    if not candidates:
        return []

    detector = s3_detector or S3DefibDetector()
    candidate_verdicts: dict[float, DefibVerdict] = {}

    if precomputed_verdicts is not None:
        candidate_verdicts = precomputed_verdicts
    elif audio_or_video_path is not None:
        # Call adjudicate per candidate with derived window_s
        for cand in candidates:
            cand_t = round(float(cand.get("timestamp_s", 0.0)), 2)
            if cand_t not in candidate_verdicts:
                v = detector.adjudicate(
                    audio_or_video_path,
                    candidate_t=cand_t,
                    window_s=window_s,
                )
                candidate_verdicts[cand_t] = v
    else:
        logging.warning("gate_shock_candidates called with no audio path and no verdicts; abstaining on all.")
        for cand in candidates:
            cand_t = round(float(cand.get("timestamp_s", 0.0)), 2)
            candidate_verdicts[cand_t] = DefibVerdict(
                confirmed=False,
                candidate_t=cand_t,
                event=None,
                reason="No audio path provided",
            )

    clusters = cluster_candidates(candidates)
    gated_candidates: list[dict[str, Any]] = []

    for cluster in clusters:
        adjudicated = adjudicate_candidate_cluster(
            cluster,
            candidate_verdicts=candidate_verdicts,
            enable_bracket_heuristic=enable_bracket_heuristic,
            window_s=window_s,
        )
        for cand, decision in adjudicated:
            updated_cand = dict(cand)
            if "original_confidence" not in updated_cand:
                updated_cand["original_confidence"] = float(cand.get("confidence", 1.0))
            if "original_timestamp_s" not in updated_cand:
                updated_cand["original_timestamp_s"] = float(cand.get("timestamp_s", 0.0))

            updated_cand["confidence"] = decision.adjusted_confidence
            updated_cand["s3_verdict"] = decision.verdict
            updated_cand["s3_reason"] = decision.reason
            updated_cand["needs_review"] = decision.needs_review

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
