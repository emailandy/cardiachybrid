"""
tests/test_s7b.py — Comprehensive Tests for Sensor S7b Gemini Semantic Annotation (S06).

Verifies that:
1. ts_source is 'stt_acoustic' on 100% of emitted rows.
2. Any model response attempting to rewrite acoustic timestamps is rejected by the parser.
3. Any model response emitting non-acoustic ts_source is rejected.
4. S7b prompt template renders without unfilled placeholders.
5. Integration with S7a Speech-to-Text v2 on simvideo2.mp4 produces authoritative
   clinical annotations.
"""

from __future__ import annotations

import pytest

from sensors.s7a_transcribe import S7aTranscriber, TokenTimestamp, TranscribedUtterance
from sensors.s7b_annotate import (
    AnnotatedUtterance,
    S7bAnnotator,
    TimestampRewriteError,
    run_s7b_annotation,
)


def _sample_stt_utterances() -> list[TranscribedUtterance]:
    return [
        TranscribedUtterance(
            utterance_id="utt_001",
            t_start_s=12.0,
            t_end_s=15.2,
            text="Stop CPR, rhythm check.",
            tokens=[
                TokenTimestamp("Stop", 12.0, 12.5, 0.95),
                TokenTimestamp("CPR,", 12.6, 13.2, 0.96),
            ],
            confidence=0.95,
        ),
        TranscribedUtterance(
            utterance_id="utt_002",
            t_start_s=168.1,
            t_end_s=171.0,
            text="Shock delivered, resume compressions.",
            tokens=[
                TokenTimestamp("Shock", 168.1, 168.9, 0.96),
                TokenTimestamp("delivered,", 169.0, 170.0, 0.95),
            ],
            confidence=0.95,
        ),
    ]


def test_s7b_ts_source_is_stt_acoustic_on_100_percent_of_rows() -> None:
    """
    Verifies that ts_source is explicitly 'stt_acoustic' on 100% of emitted rows,
    including both confident and abstained utterances.
    """
    stt = _sample_stt_utterances()
    stt.append(
        TranscribedUtterance(
            utterance_id="utt_abstained",
            t_start_s=200.0,
            t_end_s=205.0,
            text="",
            tokens=[],
            confidence=0.0,
            abstained=True,
            abstain_reason="Low SNR",
        )
    )

    annotator = S7bAnnotator()
    annotated = annotator.annotate(stt)

    assert len(annotated) == 3
    # Every single row must have ts_source == 'stt_acoustic'
    assert all(row.ts_source == "stt_acoustic" for row in annotated)
    assert annotated[2].abstained is True
    assert annotated[2].confidence == 0.0


def test_s7b_rejects_timestamp_rewriting() -> None:
    """
    Verifies that any model response attempting to rewrite acoustic t_start_s
    or t_end_s is REJECTED by parse_and_validate_annotations raising TimestampRewriteError.
    """
    stt = _sample_stt_utterances()
    annotator = S7bAnnotator()

    # 1. Model rewrites t_start_s from 12.0 to 11.5
    bad_start = [
        {
            "t_start_s": 11.5,
            "t_end_s": 15.2,
            "ts_source": "stt_acoustic",
            "speaker_role": "TEAM_LEADER",
            "is_directive": True,
        },
        {
            "t_start_s": 168.1,
            "t_end_s": 171.0,
            "ts_source": "stt_acoustic",
            "speaker_role": "DEFIB_MD",
            "is_directive": False,
        },
    ]

    with pytest.raises(TimestampRewriteError, match="attempted to rewrite t_start_s"):
        annotator.parse_and_validate_annotations(stt, bad_start)

    # 2. Model rewrites t_end_s from 171.0 to 172.0
    bad_end = [
        {
            "t_start_s": 12.0,
            "t_end_s": 15.2,
            "ts_source": "stt_acoustic",
            "speaker_role": "TEAM_LEADER",
            "is_directive": True,
        },
        {
            "t_start_s": 168.1,
            "t_end_s": 172.0,
            "ts_source": "stt_acoustic",
            "speaker_role": "DEFIB_MD",
            "is_directive": False,
        },
    ]

    with pytest.raises(TimestampRewriteError, match="attempted to rewrite t_end_s"):
        annotator.parse_and_validate_annotations(stt, bad_end)


def test_s7b_rejects_non_acoustic_ts_source() -> None:
    """
    Verifies that any model response emitting a ts_source other than
    'stt_acoustic' is rejected by parse_and_validate_annotations.
    """
    stt = _sample_stt_utterances()
    annotator = S7bAnnotator()

    bad_source = [
        {
            "t_start_s": 12.0,
            "t_end_s": 15.2,
            "ts_source": "model_inferred",
            "speaker_role": "TEAM_LEADER",
            "is_directive": True,
        },
        {
            "t_start_s": 168.1,
            "t_end_s": 171.0,
            "ts_source": "stt_acoustic",
            "speaker_role": "DEFIB_MD",
            "is_directive": False,
        },
    ]

    with pytest.raises(TimestampRewriteError, match="non-acoustic ts_source"):
        annotator.parse_and_validate_annotations(stt, bad_source)


def test_s7b_prompt_rendering_no_unfilled_placeholders() -> None:
    """
    Verifies that render_prompt formats prompts/passes/s7b_annotate.v1.0.md
    cleanly without leaving unfilled placeholders.
    """
    stt = _sample_stt_utterances()
    annotator = S7bAnnotator()
    prompt = annotator.render_prompt(stt, audio_duration_s=1363.78)

    assert "stt_acoustic_transcript" not in prompt or "### stt_acoustic_transcript" in prompt
    assert "- [12.00s - 15.20s] (utt_001): Stop CPR, rhythm check." in prompt
    assert "{audio_duration_s}" not in prompt
    assert "{stt_acoustic_transcript}" not in prompt
    assert "{contract_version}" not in prompt


def test_s7b_integration_with_s7a_simvideo2() -> None:
    """
    Integration test: runs S7a Speech-to-Text v2 on simvideo2 and feeds
    the authoritative acoustic transcript to S7b semantic annotation.
    Verifies 100% stt_acoustic ts_source and clinical role/directive accuracy.
    """
    transcriber = S7aTranscriber()
    stt_utterances = transcriber.transcribe("simvideo2.mp4")

    annotator = S7bAnnotator()
    annotated = annotator.annotate(stt_utterances)

    assert len(annotated) == 8
    assert all(utt.ts_source == "stt_acoustic" for utt in annotated)

    # Check clinical roles and directives
    utt1 = annotated[0]  # "Stop CPR, rhythm check."
    assert utt1.speaker_role == "TEAM_LEADER"
    assert utt1.is_directive is True

    utt3 = annotated[2]  # "Shock delivered, resume compressions."
    assert utt3.speaker_role == "DEFIB_MD"
    assert utt3.is_directive is False

    utt5 = annotated[4]  # "Give 1 milligram epinephrine IV now."
    assert utt5.speaker_role == "TEAM_LEADER"
    assert utt5.is_directive is True
    assert utt5.directive_target == "MED_RN"
