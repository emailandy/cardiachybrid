# TASK: S7b GEMINI SEMANTIC ANNOTATION PASS
# contract_version: {contract_version}          # ▲ logged with every record

## WINDOW GEOMETRY
Source audio duration {audio_duration_s}s.

## ACOUSTIC SPEECH-TO-TEXT TRANSCRIPT (authoritative — annotate, do not re-detect)
### stt_acoustic_transcript
{stt_acoustic_transcript}

## ANNOTATION CONTRACT
You receive an authoritative acoustic speech-to-text transcript produced by Sensor S7a.
Every utterance has explicit word-level and utterance-level timestamps and acoustic confidence.
Your role is exclusively to ANNOTATE each utterance with:
1. Clinical speaker role attribution (e.g., TEAM_LEADER, AIRWAY_MD, COMPRESSOR, MED_RN, RECORDER, DEFIB_MD, OTHER).
2. Directive classification boolean (true if the utterance is a clinical command/directive, false otherwise).
3. Directive target (intended clinical role receiving the directive, or null if broadcast/none).
4. Semantic annotation confidence (0.0 to 1.0).

## CRITICAL TIME INVARIANCE INSTRUCTION
1. YOU MUST PRESERVE ACOUSTIC TIMESTAMPS VERBATIM.
2. Every annotated record MUST emit ts_source as stt_acoustic.
3. Do NOT modify, round, shift, or rewrite timestamps from the input acoustic transcript.
4. Any response attempting to alter acoustic timestamps will be rejected by the ingestion parser.

## OUTPUT FORMAT
Return a JSON array of annotated utterances matching the input transcript length and order.
