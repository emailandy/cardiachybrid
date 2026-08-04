"""
tests/test_s7a.py — Comprehensive Tests for Sensor S7a Speech-to-Text v2 (S05).

Verifies word-level timestamps on every token, resuscitation phrase adaptation list
application, Word Error Rate (WER) measurement against hand transcripts, and
audio abstention on unusable/silent audio tracks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile as sf

from sensors.s7a_transcribe import (
    PHRASE_ADAPTATION_MAP,
    S7aTranscriber,
    TokenTimestamp,
    TranscribedUtterance,
    run_s7a_transcription,
)


def test_phrase_adaptation_multiword_merging() -> None:
    """
    Verifies that multi-word resuscitation phrases ('v fib', 'e t tube') are
    merged into standardized clinical terminology with correct timestamp spans
    and minimum confidence.
    """
    transcriber = S7aTranscriber()
    tokens = [
        TokenTimestamp(word="patient", t_start_s=0.0, t_end_s=0.5, confidence=0.95),
        TokenTimestamp(word="in", t_start_s=0.6, t_end_s=0.8, confidence=0.94),
        TokenTimestamp(word="v", t_start_s=0.9, t_end_s=1.0, confidence=0.88),
        TokenTimestamp(word="fib,", t_start_s=1.1, t_end_s=1.4, confidence=0.90),
        TokenTimestamp(word="charge", t_start_s=1.5, t_end_s=1.9, confidence=0.96),
    ]

    adapted = transcriber.apply_phrase_adaptation(tokens)
    assert len(adapted) == 4
    assert adapted[0].word == "patient"
    assert adapted[1].word == "in"

    # Multi-word match 'v fib' -> 'VF'
    assert adapted[2].word == "VF"
    assert adapted[2].t_start_s == 0.9
    assert adapted[2].t_end_s == 1.4
    assert adapted[2].confidence == 0.88  # min(0.88, 0.90)

    assert adapted[3].word == "charge"


def test_phrase_adaptation_singleword_and_punctuation() -> None:
    """
    Verifies that single-word adaptations ('epi', 'rosh') are standardized
    while preserving trailing punctuation and original token timestamps.
    """
    transcriber = S7aTranscriber()
    tokens = [
        TokenTimestamp(word="give", t_start_s=5.0, t_end_s=5.3, confidence=0.95),
        TokenTimestamp(word="epi,", t_start_s=5.4, t_end_s=5.8, confidence=0.92),
        TokenTimestamp(word="rosh", t_start_s=6.0, t_end_s=6.5, confidence=0.89),
        TokenTimestamp(word="achieved.", t_start_s=6.6, t_end_s=7.2, confidence=0.94),
    ]

    adapted = transcriber.apply_phrase_adaptation(tokens)
    assert len(adapted) == 4
    assert adapted[1].word == "epinephrine,"
    assert adapted[1].t_start_s == 5.4
    assert adapted[1].confidence == 0.92
    assert adapted[2].word == "ROSC"


def test_evaluate_wer_against_hand_transcript() -> None:
    """
    Verifies Word Error Rate (WER) calculation using Levenshtein distance
    against hand-annotated reference transcripts.
    """
    transcriber = S7aTranscriber()
    ref = ["stop", "cpr", "rhythm", "check"]

    # 1. Exact match -> WER 0.0
    hyp_exact = ["stop", "cpr", "rhythm", "check"]
    wer_0 = transcriber.evaluate_wer(hyp_exact, ref, provenance="human")
    assert wer_0 == 0.0

    # 2. One substitution out of 4 words -> WER 0.25
    hyp_sub = ["stop", "cpr", "pulse", "check"]
    wer_25 = transcriber.evaluate_wer(hyp_sub, ref, provenance="human")
    assert wer_25 == 0.25

    # 3. Empty hypothesis against reference -> WER 1.0
    wer_100 = transcriber.evaluate_wer([], ref, provenance="human")
    assert wer_100 == 1.0


def test_transcribe_and_evaluate_simvideo2_reference() -> None:
    """
    Verifies transcribe_and_evaluate on simvideo2 reference utterances,
    confirming word-level timestamps on every token and WER calculation.
    """
    transcriber = S7aTranscriber()

    # Reference hand transcript for simvideo2 CPR/defibrillation narrative
    hand_transcript = (
        "stop cpr rhythm check vf charge to 200 joules clear "
        "shock delivered resume compressions vf again charging clear "
        "give 1 milligram epinephrine iv now persistent vt charging 200 clear "
        "still in vf charging defibrillator clear prepare 300 milligrams amiodarone iv"
    )

    utterances, wer = transcriber.transcribe_and_evaluate(
        "simvideo2.mp4",
        reference_transcript=hand_transcript,
        provenance="human",
    )

    assert len(utterances) == 8
    assert wer == 0.0  # Perfect agreement after adaptation

    # Every token must have valid word-level timestamps and confidence
    total_tokens = 0
    for utt in utterances:
        assert not utt.abstained
        assert utt.t_start_s <= utt.t_end_s
        assert utt.confidence > 0.0
        for t in utt.tokens:
            total_tokens += 1
            assert t.word
            assert t.t_start_s <= t.t_end_s
            assert 0.0 <= t.confidence <= 1.0

    assert total_tokens >= 30


def test_transcribe_abstains_on_silent_audio(tmp_path: Path) -> None:
    """
    Verifies that S7aTranscriber abstains cleanly with confidence=0.0
    and abstain_reason when presented with a silent audio file.
    """
    silent_path = tmp_path / "silent.wav"
    sr = 16000
    data = np.zeros(sr * 2, dtype=np.float32)
    sf.write(str(silent_path), data, sr)

    transcriber = S7aTranscriber()
    res = transcriber.transcribe(silent_path)

    assert len(res) == 1
    assert res[0].abstained is True
    assert res[0].confidence == 0.0
    assert "silent" in str(res[0].abstain_reason).lower()


@pytest.mark.integration
def test_s7a_integration_vidsim2() -> None:
    """
    Integration test: runs S7aTranscriber on tests/video/vidsim2.mp4.
    Verifies word-level timestamps on every token, phrase adaptation list
    application, and WER measurement against hand transcript.
    """
    vp = Path("tests/video/vidsim2.mp4")
    if not vp.exists():
        pytest.skip("Integration video tests/video/vidsim2.mp4 not found")

    transcriber = S7aTranscriber()
    hand_transcript = (
        "stop cpr rhythm check vf charge to 200 joules clear "
        "shock delivered resume compressions vf again charging clear "
        "give 1 milligram epinephrine iv now persistent vt charging 200 clear "
        "still in vf charging defibrillator clear prepare 300 milligrams amiodarone iv"
    )
    utterances, wer = transcriber.transcribe_and_evaluate(
        vp, reference_transcript=hand_transcript, provenance="human"
    )
    assert wer == 0.0
    assert len(utterances) == 8
    for utt in utterances:
        assert utt.tokens
        for t in utt.tokens:
            assert t.word
            assert t.t_start_s <= t.t_end_s
            assert 0.0 <= t.confidence <= 1.0
