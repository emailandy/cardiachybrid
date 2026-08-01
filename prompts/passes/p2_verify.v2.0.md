# TASK: SINGLE-EVENT VERIFICATION
# contract_version: {contract_version}

## CANDIDATE
{candidate_event_json}

## EXCERPT
Absolute seconds {clip_t0} → {clip_t1} at 5 fps, full resolution.
t_absolute = t_clip + {clip_t0}. Report absolute only.

## SENSOR EVIDENCE IN INTERVAL
{sensor_slice}

## ANCHOR CARD — {event_type}
{anchor_card}

## ATTRIBUTE CONTRACT — {event_type}                               # ▲ NEW
{contract_slice_single}
You must return a value or an explicit null+reason for EVERY attribute listed.
A missing key is a schema violation, not an abstention.

## VERIFIED EXEMPLARS FROM THIS DEPARTMENT                         # ▲ NEW
{retrieved_exemplars}
  ← k=3 nearest human-adjudicated exemplars for this event type, from the HITL
    correction store (router/queue.py). Each shows the clip context, the AI's
    original answer, the human's correction, and the reviewer's rationale.
    These reflect YOUR cameras, YOUR equipment, YOUR bay geometry. Where a
    retrieved exemplar conflicts with the generic anchor card, the exemplar wins
    — it was adjudicated by a clinician on this footage.

## YOUR FOUR JOBS
1. VERDICT: CONFIRMED | RECLASSIFIED | REFUTED | INDETERMINATE.
   The upstream pass is tuned for recall and is EXPECTED to over-call. REFUTED
   is as valuable as CONFIRMED. Do not confirm to be agreeable.
2. REFINED TIMESTAMP using the anchor card's defining instant, with
   t_anchor_desc naming the specific observable you locked onto. If you cannot
   improve on the candidate, say so and keep it.
3. ATTRIBUTES — every one in the contract, independently. Do NOT infer one
   attribute from another. Do NOT inherit any value from an earlier event in
   this case (pad position especially).
4. CONTRADICTING EVIDENCE — anything in this excerpt arguing against your
   verdict. "None observed" only if you genuinely looked.

## FRAME-BY-FRAME REQUIREMENT
Before the verdict, populate frame_observations[]: ≥4 discrete observations at
specific timestamps covering the 6s around the candidate instant. Physical state
only — hand positions, device state, body motion, screen contents. Write it
before you decide, not to justify a decision already made.

