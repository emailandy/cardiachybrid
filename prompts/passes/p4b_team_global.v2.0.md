# TASK: TEAM ITEM 12 — GLOBAL RATING (1 = Poor … 10 = Exceptional)
# metric_definition_version: {metric_definition_version}

You have NOT been shown the individual TEAM item scores for this case. This is
deliberate. The global rating is an independent gestalt judgment of overall
clinical safety and efficacy, not an average of the eleven items. Seeing them
first would anchor you.

## OBJECTIVE METRICS — from fact_metric. GROUND TRUTH. Do not recompute.
{objective_metrics_block}

A metric shown as NULL was not computable — the denominator was zero, an input
was missing, or it depends on a pipeline stage that does not yet exist. Treat
NULL as ABSENCE OF INFORMATION. It is never zero, never poor performance, and
never evidence of anything.

## COVERAGE
{coverage_summary}

Behaviour you could not observe is not behaviour that did not occur. If the
recording was degraded during a clinically significant interval, say so in your
justification and widen your uncertainty rather than scoring down.

## CASE
{event_summary}
{transcript_highlights}

## CALIBRATION ANCHORS
{three_anchor_cases}

## PROCEDURE — in this order
 1. Place this case against the anchors. State which two it falls between and
    why. If no anchors are available, say so explicitly and score in absolute
    terms, noting that absolute scoring is less well calibrated.
 2. Name the two strongest features of this team's performance, each with a
    timestamp and a concrete observation.
 3. Name the two most significant deficiencies, each with a timestamp and a
    concrete observation.
 4. Assign the global score, 1 to 10.
 5. State what would have had to be different for the score to be one point
    higher. If you cannot name something specific, your score is probably one
    point too low.

## SCOPE
You are rating TEAMWORK — coordination, communication, adaptability, composure
— not clinical correctness. A team can execute flawless ACLS with poor
communication, or communicate beautifully while deviating from protocol. The
objective metrics are evidence of coordination OUTCOMES, not a protocol
compliance grade.

## OUTPUT
{"score": 0,
 "placement": "",
 "strengths": [{"t": 0.0, "observation": ""}],
 "deficiencies": [{"t": 0.0, "observation": ""}],
 "justification": "",
 "one_point_higher": ""}

