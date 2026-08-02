# TASK: TEAM RATINGS — ITEMS 1 THROUGH 11
# metric_definition_version: {metric_version}

Apply the published TEAM instrument descriptors. Do not substitute your own
standards and do not adopt a "be harsh" or "be generous" disposition — both are
miscalibration.

## LEADER
{leader_speaker_id} — {n_directive} of {n_total_directive} directive utterances;
present {leader_presence_pct}% of the case; role stability {leader_stability}.
Evaluate whoever held leadership longest; state this if it changed.

## OBJECTIVE METRICS — from fact_metric. GROUND TRUTH. Do not recompute.  # ▲
{metrics_table}
A metric shown as NULL was not computable (denominator zero or inputs
incomplete). Treat NULL as absence of information, never as zero.       # ▲

## COVERAGE CAVEAT                                                       # ▲ NEW
{coverage_summary}
Behaviour you could not observe is not behaviour that did not occur. If a
channel was degraded during the interval relevant to an item, score null with
an abstain_reason rather than scoring low.

## CALIBRATION ANCHORS
{anchor_case_low}   consensus global 2
{anchor_case_mid}   consensus global 6
{anchor_case_high}  consensus global 9
Place this case relative to these three BEFORE assigning any score.

## PER-ITEM PROCEDURE (mandatory order)
 1. positive_evidence[]  ≤4, each {t, quote_or_description}
 2. negative_evidence[]  ≤4, each {t, quote_or_description}
 3. relative_placement
 4. score 0–4
 5. justification referencing the evidence above

## EVIDENCE GATES
 4 requires ≥3 distinct positive observations AND zero unmitigated negatives
 3 requires ≥2 positive observations
 ≤1 requires ≥1 concrete negative observation — never score low on absence of
   evidence alone; if unobservable, score null with abstain_reason
Every score traces to timestamped observations. Never score from overall vibe.

## SCOPE
You are rating TEAMWORK, not clinical correctness. Objective metrics are
evidence of coordination outcomes, not a protocol-compliance grade.

