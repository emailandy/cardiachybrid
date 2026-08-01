# Clinical Review Queue

Every entry below represents an open clinical review question for anchor cards in this repository.
Answering these questions replaces generic extraction guidance with site-specific anchors.
None of these items block development or structural validation (`check_anchors`); all must be reviewed by the clinical lead before the first production run.

## CR-001 — Resuscitation bay camera configuration
Cards affected: compression_interruption, mccd_adjustment, vitals_reading, defibrillation_shock, airway_attempt, rosc_detected
Question: How many cameras cover a resuscitation bay, where are they mounted, and what is each one's field of view? Specifically: is the patient's chest reliably visible during compressions; is the monitor face legible; is the head-of-bed airway view unobstructed?
Why it matters: determines realistic abstain_if thresholds and expected unable-to-determine rates for pad position, monitor OCR, and airway device identification.
Blocks: nothing today. Cards ship with generic guidance; answering this replaces generic text with site-specific anchors and should measurably improve extraction.
Status: OPEN   Owner: clinical lead

## CR-002 — Resuscitation monitor make/model and OCR legibility
Cards affected: compression_interruption, vitals_reading, rosc_detected
Question: Which patient monitor make/model is used in the resuscitation bays? Are the numeric digits (HR, SBP, DBP, SpO2, EtCO2) and arterial/pleth waveforms reliably legible on camera? Does the monitor indicate arterial line BP vs NIBP with distinct screen labels?
Why it matters: governs whether monitor OCR is a viable primary detector for vital signs and SBP/DBP during compression pauses, and how waveform pulsatility is verified for ROSC detection.
Blocks: nothing today. Cards ship with generic guidance; answering this replaces generic text with site-specific anchors and should measurably improve extraction.
Status: OPEN   Owner: clinical lead

## CR-003 — Defibrillator make/model and charge/ready acoustic tones
Cards affected: compression_interruption, defibrillation_shock
Question: Which defibrillator make/model is used in the resuscitation bays? What are the specific audio tone sequences for charging, ready-to-shock, and discharge click? (e.g., ascending warble vs rising tone plus repeating ready beep).
Why it matters: distinguishes charging, holding charge, shock discharge, and aborted charge in audio_device.
Blocks: nothing today. Cards ship with generic guidance; answering this replaces generic text with site-specific anchors and should measurably improve extraction.
Status: OPEN   Owner: clinical lead

## CR-004 — Mechanical CPR device make/model and operational cues
Cards affected: compression_interruption, mccd_adjustment, rosc_detected
Question: Which mechanical CPR device make/model is deployed in the resuscitation bays? What are its specific audio and visual signatures for motor cycling, latching/clamping sounds, and battery replacement alarms?
Why it matters: distinguishes normal compression pauses from mechanical CPR adjustments (device_moved_up, latch_resecured, suction_cup_manipulated, battery_change) and confirms when compressions are stopped for ROSC pulse checks.
Blocks: nothing today. Cards ship with generic guidance; answering this replaces generic text with site-specific anchors and should measurably improve extraction.
Status: OPEN   Owner: clinical lead

## CR-005 — Microphone configuration and speech audio quality
Cards affected: compression_interruption, mccd_adjustment, vitals_reading, defibrillation_shock, airway_attempt, rosc_detected
Question: What is the microphone configuration (overhead boom mics, room mics) in the resuscitation bays, and what is the acoustic damping/noise floor during active CPR and suctioning? Are verbalized numbers (e.g., blood pressure, pulse checks) reliably audible over ambient room noise?
Why it matters: determines whether speech precursor/confirm/negation utterances can be relied upon as secondary anchors or if abstain_if must trigger more frequently on noisy audio.
Blocks: nothing today. Cards ship with generic guidance; answering this replaces generic text with site-specific anchors and should measurably improve extraction.
Status: OPEN   Owner: clinical lead
