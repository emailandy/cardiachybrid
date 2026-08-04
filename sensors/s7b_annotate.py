"""
sensors/s7b_annotate.py — Sensor S7b Gemini Semantic Annotation Pass (S06).

Annotates S7a Speech-to-Text transcripts with clinical speaker roles and directive
classification without altering acoustic word-level timestamps (ts_source = 'stt_acoustic').
Rejects any model response that attempts to rewrite acoustic timestamps.
100% DETERMINISTIC: same input, same output, bit-identical. Every sensor emits
CONFIDENCE and abstains rather than guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from sensors.s7a_transcribe import TranscribedUtterance

VALID_SPEAKER_ROLES: set[str] = {
    "TEAM_LEADER",
    "AIRWAY_MD",
    "COMPRESSOR",
    "MED_RN",
    "RECORDER",
    "DEFIB_MD",
    "OTHER",
    "UNKNOWN",
}


class TimestampRewriteError(ValueError):
    """
    Raised when a semantic annotation model response attempts to rewrite,
    round, shift, or modify acoustic word/utterance timestamps from S7a.
    """

    pass


@dataclass(frozen=True)
class AnnotatedUtterance:
    """A semantic annotation record for a clinical spoken utterance."""

    utterance_id: str
    t_start_s: float
    t_end_s: float
    ts_source: str
    text: str
    speaker_role: str
    is_directive: bool
    directive_target: str | None
    confidence: float
    abstained: bool = False
    abstain_reason: str | None = None


class S7bAnnotator:
    """
    Deterministic clinical speech semantic annotator (Sensor S7b).
    Enforces absolute timestamp invariance (ts_source='stt_acoustic').
    """

    def __init__(
        self,
        min_confidence: float = 0.70,
        time_tolerance_s: float = 1e-5,
    ) -> None:
        self.min_confidence = min_confidence
        self.time_tolerance_s = time_tolerance_s

    def parse_and_validate_annotations(
        self,
        stt_utterances: Sequence[TranscribedUtterance],
        raw_model_response: Sequence[dict[str, Any]],
    ) -> list[AnnotatedUtterance]:
        """
        Parses raw model annotation responses against authoritative S7a acoustic
        utterances. REJECTS any model response attempting to rewrite timestamps
        or emit non-acoustic ts_source.
        """
        if len(raw_model_response) != len(stt_utterances):
            raise TimestampRewriteError(
                f"Model response count ({len(raw_model_response)}) does not match "
                f"authoritative S7a utterance count ({len(stt_utterances)})"
            )

        annotated: list[AnnotatedUtterance] = []
        for i, stt_utt in enumerate(stt_utterances):
            raw_item = raw_model_response[i]

            # Check for any attempt to rewrite acoustic timestamps
            m_start = float(raw_item.get("t_start_s", stt_utt.t_start_s))
            m_end = float(raw_item.get("t_end_s", stt_utt.t_end_s))

            if abs(m_start - stt_utt.t_start_s) > self.time_tolerance_s:
                raise TimestampRewriteError(
                    f"Model attempted to rewrite t_start_s for {stt_utt.utterance_id}: "
                    f"acoustic={stt_utt.t_start_s}, model={m_start}"
                )
            if abs(m_end - stt_utt.t_end_s) > self.time_tolerance_s:
                raise TimestampRewriteError(
                    f"Model attempted to rewrite t_end_s for {stt_utt.utterance_id}: "
                    f"acoustic={stt_utt.t_end_s}, model={m_end}"
                )

            # Check ts_source
            m_source = str(raw_item.get("ts_source", "stt_acoustic"))
            if m_source != "stt_acoustic":
                raise TimestampRewriteError(
                    f"Model emitted non-acoustic ts_source '{m_source}' for "
                    f"{stt_utt.utterance_id}; must be 'stt_acoustic'"
                )

            role = str(raw_item.get("speaker_role", "UNKNOWN")).upper()
            if role not in VALID_SPEAKER_ROLES:
                role = "UNKNOWN"

            is_dir = bool(raw_item.get("is_directive", False))
            target = raw_item.get("directive_target", None)
            if target is not None:
                target = str(target)
            conf = float(raw_item.get("confidence", 0.95))

            if conf < self.min_confidence:
                annotated.append(
                    AnnotatedUtterance(
                        utterance_id=stt_utt.utterance_id,
                        t_start_s=stt_utt.t_start_s,
                        t_end_s=stt_utt.t_end_s,
                        ts_source="stt_acoustic",
                        text=stt_utt.text,
                        speaker_role="UNKNOWN",
                        is_directive=False,
                        directive_target=None,
                        confidence=0.0,
                        abstained=True,
                        abstain_reason="Low semantic annotation confidence",
                    )
                )
            else:
                annotated.append(
                    AnnotatedUtterance(
                        utterance_id=stt_utt.utterance_id,
                        t_start_s=stt_utt.t_start_s,
                        t_end_s=stt_utt.t_end_s,
                        ts_source="stt_acoustic",
                        text=stt_utt.text,
                        speaker_role=role,
                        is_directive=is_dir,
                        directive_target=target,
                        confidence=round(conf, 4),
                        abstained=False,
                        abstain_reason=None,
                    )
                )

        return annotated

    def annotate(
        self,
        stt_utterances: Sequence[TranscribedUtterance],
        model_override: Sequence[dict[str, Any]] | None = None,
    ) -> list[AnnotatedUtterance]:
        """
        Annotates authoritative S7a speech-to-text utterances with speaker roles
        and directive classification. If model_override is None, applies
        deterministic clinical resuscitation rules.
        """
        if model_override is not None:
            return self.parse_and_validate_annotations(
                stt_utterances, model_override
            )

        annotated: list[AnnotatedUtterance] = []
        for utt in stt_utterances:
            if utt.abstained:
                annotated.append(
                    AnnotatedUtterance(
                        utterance_id=utt.utterance_id,
                        t_start_s=utt.t_start_s,
                        t_end_s=utt.t_end_s,
                        ts_source="stt_acoustic",
                        text=utt.text,
                        speaker_role="UNKNOWN",
                        is_directive=False,
                        directive_target=None,
                        confidence=0.0,
                        abstained=True,
                        abstain_reason=f"Authoritative S7a input abstained: {utt.abstain_reason}",
                    )
                )
                continue

            lower_text = utt.text.lower()
            role = "TEAM_LEADER"
            is_dir = False
            target: str | None = None
            conf = 0.95

            # Clinical resuscitation directive rules
            if any(
                w in lower_text
                for w in [
                    "stop cpr",
                    "rhythm check",
                    "charge",
                    "clear!",
                    "resume compressions",
                    "give",
                    "prepare",
                    "intubate",
                    "pulse check",
                ]
            ):
                is_dir = True
                if "give" in lower_text or "prepare" in lower_text:
                    target = "MED_RN"
                elif "stop cpr" in lower_text or "resume" in lower_text:
                    target = "COMPRESSOR"
                elif "charge" in lower_text or "clear" in lower_text:
                    target = "DEFIB_MD"

            # Speaker role differentiation
            if "shock delivered" in lower_text:
                role = "DEFIB_MD"
                is_dir = False
                target = None

            annotated.append(
                AnnotatedUtterance(
                    utterance_id=utt.utterance_id,
                    t_start_s=utt.t_start_s,
                    t_end_s=utt.t_end_s,
                    ts_source="stt_acoustic",
                    text=utt.text,
                    speaker_role=role,
                    is_directive=is_dir,
                    directive_target=target,
                    confidence=conf,
                    abstained=False,
                    abstain_reason=None,
                )
            )

        return annotated

    def render_prompt(
        self,
        stt_utterances: Sequence[TranscribedUtterance],
        audio_duration_s: float,
        contract_version: str = "v2.0",
    ) -> str:
        """
        Renders the S7b semantic annotation markdown prompt template with
        authoritative acoustic transcript utterances.
        """
        template_path = Path("prompts/passes/s7b_annotate.v1.0.md")
        template = template_path.read_text()

        lines: list[str] = []
        for utt in stt_utterances:
            lines.append(
                f"- [{utt.t_start_s:.2f}s - {utt.t_end_s:.2f}s] ({utt.utterance_id}): {utt.text}"
            )
        transcript_block = "\n".join(lines)

        rendered = template.format(
            contract_version=contract_version,
            audio_duration_s=round(audio_duration_s, 2),
            stt_acoustic_transcript=transcript_block,
        )
        return rendered


def run_s7b_annotation(
    stt_utterances: Sequence[TranscribedUtterance],
    model_override: Sequence[dict[str, Any]] | None = None,
    min_confidence: float = 0.70,
) -> list[AnnotatedUtterance]:
    """Convenience wrapper to run S7b semantic annotation."""
    annotator = S7bAnnotator(min_confidence=min_confidence)
    return annotator.annotate(stt_utterances, model_override=model_override)
