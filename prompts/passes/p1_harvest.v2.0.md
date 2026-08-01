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

