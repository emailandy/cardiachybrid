<!-- Golden source for prompts/passes/p*.txt. Reconstruction from extracted passes must be byte-identical. Do not edit without updating both. -->
=== P1 ===
# TASK: EVENT HARVEST — WINDOW {chunk_index} of {chunk_total}
# contract_version: {contract_version}          # ▲ logged with every record

## WINDOW GEOMETRY
Source duration {video_duration_s}s. This window: {win_start} → {win_end}.
  PRIMARY  {win_start} → {primary_end}   you OWN these events
  OVERLAP  {primary_end} → {win_end}     emit with in_overlap_zone: true
  LEAD-IN  first {overlap_lead}s is the prior window's tail — context only
An interval event that starts before {win_start_primary} but ENDS in your
primary zone: emit with its true earlier start and in_overlap_zone: true.
ALL timestamps are ABSOLUTE video seconds.

## SENSOR TRACKS (authoritative — annotate, do not re-detect)
### compressions_active   {compression_intervals}
### device_audio          {device_audio_hits}
### monitor_ocr           {monitor_ocr_series}
### asr_diarized          {asr_transcript}
### quality_track         {quality_windows}

## ATTRIBUTE CONTRACT                                              # ▲ NEW
{contract_slice}
  ← generated/extraction_contract.md, sliced to the event types plausibly
    present in this window (from sensor hits + a keyword pre-scan). Names and
    values here are BINDING.

## PROCEDURE
1. ANNOTATE EVERY CANDIDATE CCI. One `compression_interruption` per INACTIVE
   interval ≥3.0s, using the sensor's boundaries verbatim. Then fill the
   contract attributes from all three channels. No determinable reason →
   reasons: ["unknown"].
2. RESOLVE EVERY DEVICE-AUDIO HIT into an event or explicitly dismiss it.
   A charge with no discharge → `defib_charge_aborted`.
3. SWEEP SPEECH: medications, ROSC/pulse statements, orders and readbacks,
   ECMO activation, pronouncement, DNR, findings, device problems.
4. SWEEP VISUAL for events with no audio signature: airway attempts, pad
   application and repositioning, line placement, MCCD milestones, POCUS probe
   placement, log rolls, transfers.
5. EMIT COVERAGE NOTES.                                            # ▲ NEW
   Walk the window in ~30s blocks. For each, ask: was the chest visible? the
   monitor legible? the airway in frame? the audio intelligible? Emit a
   coverage_note for every degraded interval. This determines whether a missing
   event is recorded as "did not occur" or "could not be observed". Omitting a
   note asserts a false negative.
6. CONTRACT SELF-CHECK.                                            # ▲ NEW
   Re-read every attribute you emitted against the contract block. Verify:
   exact attribute name · symbolic value from the permitted list · gated
   attributes present only when their gate is satisfied · no attribute absent
   from the contract · operator_pgy nowhere · no integer where a symbol belongs.
7. RE-READ against the KNOWN FAILURE MODES. Delete or downgrade anything you
   cannot defend with evidence.

## ANCHOR CARDS
{anchor_cards}

## OUTPUT
Conform exactly to the supplied JSON schema. Events sorted by t_start_s.
No prose.

=== P2 ===
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

=== P3 ===
# TASK: CASE-LEVEL ADJUDICATION
# contract_version: {contract_version}

Inputs: {events} {compression_track} {transcript} {monitor_ocr} {coverage}
        {clock_json}
No video. You may merge, split, reclassify, remove, re-time, or flag existing
events, and resolve case-level fields. You may not invent an event.

## JOB 1 — OVERLAP DEDUPLICATION
Merge when: same type AND |Δt| ≤ (sum of the two t_precision_s) AND compatible
attributes. Keep the P2-verified instance; if both, keep the tighter precision.
Log every merge.

## JOB 2 — TEMPORAL CONSISTENCY
Repair or flag: t_end < t_start · overlapping CCIs · overlapping ROSC episodes ·
MCCD adjustment window not contained in the application window · events outside
[patient_enters_room, patient_leaves_room].
Auto-repair only where a single unambiguous fix exists. Otherwise FLAG.

## JOB 3 — CROSS-EVENT COHERENCE (flag, never silently fix)
 a. Every shock inside a CCI. b. Any shock ⟹ a shockable rhythm somewhere.
 c. Medication inside a ROSC window → CLINICAL_REVIEW, never delete.
 d. MCCD application unpaired with effectiveness or abandonment.
 e. Successful airway attempt without a confirmation.
 f. ROSC detected without a matching loss or persistence to end of video.
 g. Any event asserted during a coverage window degraded for that modality →
    downgrade confidence and flag.

## JOB 4 — CASE FIELDS                                             # ▲ EXPANDED
Resolve each with cited evidence, using symbolic values from the contract:
  arrest_location · recording_started_late · cpr_in_progress_upon_arrival ·
  brought_by_ems · adv_airway_on_arrival · ems_pads_switched ·
  mccd_ed_provenance · ed_mccd_outcome · dnr_basis
recording_started_late: bias toward TRUE. If true, you MUST null
time_first_team_member_ent, time_pt_enters_room, and backboard_preplaced —
those observations are not in the recording.
review trigger metadata is administrative metadata, not in the video. Always null.

## JOB 5 — COVERAGE CONSOLIDATION                                  # ▲ NEW
Merge per-window coverage_notes into case-level intervals per issue code.
Then, for each of these channels — speech, visual, monitor, airway — state
whether coverage was ADEQUATE for the whole case.
This directly determines whether ~40 downstream yes/no fields resolve to "No"
or to "Unable to determine". Be conservative: if a channel was degraded for a
clinically meaningful interval, it was not adequate.

## JOB 6 — UNRESOLVED FLAGS
One entry per unresolvable concept: the affected attribute, the reason, and the
video interval a human should review. This list becomes the review work order.
Completeness beats brevity.

## OUTPUT
{"events":[...], "case_fields":{...}, "coverage_summary":{...},
 "merges":[...], "repairs":[...], "flags":[...], "unresolved":[...]}

=== P4A ===
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
  chest_compression_fraction ........ <value> (num <numerator> / den <denominator>)
  closed_loop_completion_rate ....... NULL (requires S7 diarized ASR)
  median_peri_shock_pause_s ......... NULL (zero shocks in case)
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

=== P4B ===
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

=== P5 ===
# TASK: SECTION NOTES — {section_name} → {target_field}

You are writing the free-text note for exactly one REDCap field. A
clinician-reviewer who has NOT watched the video will read it.

Inputs: {section_events} {section_flags} {section_abstentions}
        {coverage_windows} {truncation_report}

CONTENT, in this order:
 1. Clinically notable observations the structured fields cannot express.
 2. Every ABSTENTION in this section and why, specifically ("posterior pad never
    entered frame", not "unclear").
 3. Every FLAG raised by adjudication for this section.
 4. Every coverage limitation affecting this section.
 5. TRUNCATION DUTY — mandatory when {truncation_report} is non-empty:  # ▲ NEW
    State the TRUE count and describe each dropped item with its timestamp and
    duration. The database caps this section at {cap} entries; anything beyond
    exists only in this note and in the analytics warehouse.
    Template: "N interruptions were identified; the instrument records 30. The
    following were not captured: [t=MM:SS, 4.1s, pulse check]; ..."

HARD RULES
 - No patient identifiers, names, MRNs, ages, dates.
 - No staff names. Roles only ("the physician at the head of bed").
 - No clinical judgment, quality assessment, or recommendations.
 - Max 800 characters. If truncation content would exceed this, prioritize
   items 5 → 3 → 2 → 4 → 1.
 - If nothing notable, nothing abstained, no flags, no truncation, output
   exactly: "No additional findings. All fields in this section extracted with
   adequate coverage."

Output is passed through PHI scrubbing before storage. Do not rely on that as a
substitute for the rules above.
Bind to the seven section notes: defib · details · cci · airway · ventilation · drugs · rosc.
