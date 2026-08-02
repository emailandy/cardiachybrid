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

