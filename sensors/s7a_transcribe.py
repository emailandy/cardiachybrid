"""
sensors/s7a_transcribe.py — Sensor S7a Speech-to-Text v2 Transcription Engine (S05).

Transcribes clinical resuscitation audio tracks with word-level timestamps on
every token, applies resuscitation phrase adaptation lists to correct clinical
terminology, and measures Word Error Rate (WER) against hand-annotated transcripts.
100% DETERMINISTIC: same input, same output, bit-identical. Every sensor emits
CONFIDENCE and abstains rather than guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import soundfile as sf

from sensors.eval.metrics import score_wer


@dataclass(frozen=True)
class TokenTimestamp:
    """Word token with explicit start/end timestamp and ASR confidence."""

    word: str
    t_start_s: float
    t_end_s: float
    confidence: float


@dataclass(frozen=True)
class TranscribedUtterance:
    """A transcribed spoken utterance with word-level token timestamps."""

    utterance_id: str
    t_start_s: float
    t_end_s: float
    text: str
    tokens: list[TokenTimestamp]
    confidence: float
    abstained: bool = False
    abstain_reason: str | None = None


# Resuscitation phrase adaptation mapping from phonetic/ASR misrecognitions
# to standardized clinical resuscitation terminology.
PHRASE_ADAPTATION_MAP: dict[str, str] = {
    "v fib": "VF",
    "v-fib": "VF",
    "v tach": "VT",
    "v-tach": "VT",
    "epi": "epinephrine",
    "rosh": "ROSC",
    "ros k": "ROSC",
    "ros c": "ROSC",
    "bvm": "BVM",
    "cpr": "CPR",
    "et tube": "ET tube",
    "e t tube": "ET tube",
    "io": "IO",
    "i o": "IO",
    "iv": "IV",
    "i v": "IV",
    "pea": "PEA",
    "p e a": "PEA",
    "asystole": "asystole",
    "amio": "amiodarone",
    "bicarb": "sodium bicarbonate",
    "mag": "magnesium sulfate",
    "lucas": "LUCAS",
    "lma": "LMA",
    "king airway": "King airway",
    "i gel": "i-gel",
    "i-gel": "i-gel",
}


class S7aTranscriber:
    """
    Deterministic clinical speech-to-text transcription engine (Sensor S7a).
    """

    def __init__(
        self,
        profile_name: str = "default",
        min_confidence: float = 0.70,
        adaptation_map: dict[str, str] | None = None,
    ) -> None:
        self.profile_name = profile_name
        self.min_confidence = min_confidence
        self.adaptation_map = (
            adaptation_map
            if adaptation_map is not None
            else PHRASE_ADAPTATION_MAP
        )

    def apply_phrase_adaptation(
        self, tokens: list[TokenTimestamp]
    ) -> list[TokenTimestamp]:
        """
        Applies resuscitation phrase adaptation list to word-level tokens.
        Matches multi-word and single-word phonetic variations (case-insensitive)
        and replaces them with standardized clinical terminology while preserving
        timestamp boundaries and minimum confidence.
        """
        if not tokens:
            return []

        adapted: list[TokenTimestamp] = []
        n = len(tokens)
        i = 0

        # Sort adaptation keys by word count descending to match longest phrases first
        sorted_phrases = sorted(
            self.adaptation_map.items(),
            key=lambda item: len(item[0].split()),
            reverse=True,
        )

        while i < n:
            matched = False
            for phrase, target in sorted_phrases:
                phrase_words = phrase.split()
                w_len = len(phrase_words)
                if i + w_len <= n:
                    # Check if tokens[i : i+w_len] matches phrase_words case-insensitively
                    window_words = [
                        re.sub(r"[^\w\-]", "", t.word).lower()
                        for t in tokens[i : i + w_len]
                    ]
                    if window_words == [w.lower() for w in phrase_words]:
                        t_start = tokens[i].t_start_s
                        t_end = tokens[i + w_len - 1].t_end_s
                        min_conf = min(t.confidence for t in tokens[i : i + w_len])
                        trailing_punct = ""
                        if w_len == 1 and tokens[i].word and not tokens[i].word[-1].isalnum():
                            trailing_punct = tokens[i].word[-1]
                        adapted.append(
                            TokenTimestamp(
                                word=f"{target}{trailing_punct}",
                                t_start_s=t_start,
                                t_end_s=t_end,
                                confidence=min_conf,
                            )
                        )
                        i += w_len
                        matched = True
                        break

            if not matched:
                # Try single-word adaptation on punctuation-stripped word
                curr = tokens[i]
                clean_word = re.sub(r"[^\w\-]", "", curr.word).lower()
                if clean_word in self.adaptation_map:
                    target_val = self.adaptation_map[clean_word]
                    # Preserve any trailing punctuation if present
                    trailing_punct = ""
                    if curr.word and not curr.word[-1].isalnum():
                        trailing_punct = curr.word[-1]
                    adapted.append(
                        TokenTimestamp(
                            word=f"{target_val}{trailing_punct}",
                            t_start_s=curr.t_start_s,
                            t_end_s=curr.t_end_s,
                            confidence=curr.confidence,
                        )
                    )
                else:
                    adapted.append(curr)
                i += 1

        return adapted


    def transcribe(
        self,
        audio_path: str | Path,
        snr_db_threshold: float = 3.0,
    ) -> list[TranscribedUtterance]:
        """
        Transcribes audio track into structured utterances with word-level
        timestamps on every token and resuscitation phrase adaptation applied.
        Abstains with explicit confidence=0.0 and abstain_reason on unusable audio.
        """
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")

        # Check if audio file can be opened and check SNR
        try:
            data, sr = sf.read(str(path))
            if data.size == 0:
                return [
                    TranscribedUtterance(
                        utterance_id="utt_empty",
                        t_start_s=0.0,
                        t_end_s=0.0,
                        text="",
                        tokens=[],
                        confidence=0.0,
                        abstained=True,
                        abstain_reason="Audio file is empty",
                    )
                ]
            # Convert to mono if multichannel
            if data.ndim > 1:
                data = np.mean(data, axis=1)

            rms = float(np.sqrt(np.mean(data**2)))
            if rms < 1e-6:
                return [
                    TranscribedUtterance(
                        utterance_id="utt_silence",
                        t_start_s=0.0,
                        t_end_s=float(len(data) / sr),
                        text="",
                        tokens=[],
                        confidence=0.0,
                        abstained=True,
                        abstain_reason="Audio track is silent (RMS < 1e-6)",
                    )
                ]

            # Estimate SNR from p95 (speech/signal) vs p10 (noise floor)
            abs_data = np.abs(data)
            p95 = float(np.percentile(abs_data, 95))
            p10 = max(float(np.percentile(abs_data, 10)), 1e-9)
            snr_db = 20.0 * np.log10(p95 / p10)

            if snr_db < snr_db_threshold:
                return [
                    TranscribedUtterance(
                        utterance_id="utt_low_snr",
                        t_start_s=0.0,
                        t_end_s=float(len(data) / sr),
                        text="",
                        tokens=[],
                        confidence=0.0,
                        abstained=True,
                        abstain_reason=f"Audio SNR ({snr_db:.1f} dB) below threshold ({snr_db_threshold:.1f} dB)",
                    )
                ]
        except Exception as e:
            return [
                TranscribedUtterance(
                    utterance_id="utt_error",
                    t_start_s=0.0,
                    t_end_s=0.0,
                    text="",
                    tokens=[],
                    confidence=0.0,
                    abstained=True,
                    abstain_reason=f"Audio read failure: {e}",
                )
            ]

        raise NotImplementedError("S7a requires Speech-to-Text v2 — see S05")

    def evaluate_wer(
        self,
        hypothesis_tokens: list[str],
        reference_tokens: list[str],
        provenance: str = "human",
        allow_unverified: bool = False,
    ) -> float:
        """
        Computes Word Error Rate (WER) using Levenshtein distance against a
        hand-annotated reference transcript.
        """
        scorecard = score_wer(
            hypothesis_tokens=hypothesis_tokens,
            reference_tokens=reference_tokens,
            n_cases=1,
            provenance=provenance,
            allow_unverified=allow_unverified,
        )
        return float(scorecard.value)

    def transcribe_and_evaluate(
        self,
        audio_path: str | Path,
        reference_transcript: str | list[str],
        provenance: str = "human",
        allow_unverified: bool = False,
    ) -> tuple[list[TranscribedUtterance], float]:
        """
        Transcribes audio and evaluates Word Error Rate (WER) against a hand transcript.
        Returns tuple of (transcribed_utterances, wer_score).
        """
        utterances = self.transcribe(audio_path)

        # Extract all hypothesis word tokens across non-abstained utterances
        hyp_words: list[str] = []
        for utt in utterances:
            if not utt.abstained:
                for t in utt.tokens:
                    clean_w = re.sub(r"[^\w\-]", "", t.word).lower()
                    if clean_w:
                        hyp_words.append(clean_w)

        # Tokenize reference transcript
        ref_words: list[str] = []
        if isinstance(reference_transcript, str):
            ref_tokens = reference_transcript.split()
        else:
            ref_tokens = reference_transcript
        for w in ref_tokens:
            clean_w = re.sub(r"[^\w\-]", "", w).lower()
            if clean_w:
                ref_words.append(clean_w)

        wer_score = self.evaluate_wer(
            hypothesis_tokens=hyp_words,
            reference_tokens=ref_words,
            provenance=provenance,
            allow_unverified=allow_unverified,
        )

        return utterances, wer_score


def run_s7a_transcription(
    audio_path: str | Path,
    profile_name: str = "default",
    min_confidence: float = 0.70,
) -> list[TranscribedUtterance]:
    """Convenience wrapper to run S7a Speech-to-Text v2 transcription."""
    transcriber = S7aTranscriber(
        profile_name=profile_name, min_confidence=min_confidence
    )
    return transcriber.transcribe(audio_path)
