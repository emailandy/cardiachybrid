"""
Prompt builder module for resus_qc (A05).

This module implements the prompt builder for multimodal video forensic annotation passes.
Currently implemented:
  - build_p1: Chunked harvest pass across video windows (P1)
  - build_p2: Single-event zoom verification pass (P2)
  - Shared machinery: BuiltPrompt dataclass, select_anchors (fail-safe recall-biased anchor slicing),
    to_vertex_schema (dereferencing pydantic/JSON schemas for Vertex AI structured outputs),
    snapshot writing, placeholder validation, and cryptographic hashing.

DEFERRED PASSES:
  - build_p3 (Case-level adjudication), build_p4a (Team items), build_p4b (Team global), and build_p5 (Notes)
    are deferred to A06, when their prompt templates are created.

NOTE ON SENSOR INPUTS:
  - Sensors S1–S7 are unbuilt at this stage. This module defines the input interface and is tested
    against synthetic fixtures in tests/fixtures/sensors/. Live sensor inputs are supplied by D08.

NOTE ON TOKEN ESTIMATION:
  - `estimated_text_input_tokens` is estimated as `(len(system) + len(user)) // 4` for the text portion.
    Video tokens are NOT estimated here; they are a function of fps and duration, computed by the caller.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json
import logging
import re
import copy

from codegen.yamlio import load_yaml
from prompts.registry import (
    assert_no_field_names,
    manifest,
    load,
    anchor,
    validate_template_placeholders,
)
from generated.models import EventStream, Event


@dataclass
class BuiltPrompt:
    """Dataclass holding an assembled prompt and its audit/reproducibility metadata."""
    system: str
    user: str
    response_schema: dict[str, Any]
    prompt_hash: str
    selected_anchors: list[str]
    selection_reasons: dict[str, str]
    estimated_text_input_tokens: int
    contract_version: str
    dict_version: str
    constitution_hash: str
    anchor_library_version: str
    template_hash: str


ALWAYS_INCLUDE_TIER = [
    "compression_interruption",
    "medication_administration",
    "pulse_check",
    "rhythm_check",
]


def _all_anchor_event_types() -> list[str]:
    """Returns a sorted list of all 39 anchor card event types."""
    return sorted(
        p.stem
        for p in Path("prompts/anchors").glob("*.yaml")
        if p.stem != "_SCHEMA"
    )


def select_anchors(
    sensor_data: dict[str, Any] | None,
    keywords: list[str] | None = None,
) -> tuple[list[str], dict[str, str]]:
    """
    Recall-biased anchor card selector for P1 window harvesting.
    
    Omitting a card makes that event type unemittable in the window (silent total recall loss).
    Therefore, selection defaults fail-safe to including ALL 39 cards when sensor_data is None,
    when sensor_data is empty ({}), or when any parsing error occurs.
    
    Returns:
        (selected_event_types, selection_reasons) where both collections are sorted by key.
    """
    all_types = _all_anchor_event_types()
    
    if sensor_data is None:
        reasons = {t: "fail_safe: sensor_data is None" for t in all_types}
        return all_types, reasons
        
    if sensor_data == {}:
        reasons = {}
        for t in all_types:
            if t in ALWAYS_INCLUDE_TIER:
                reasons[t] = "always_include: high frequency default"
            else:
                reasons[t] = "fail_safe: empty sensor_data (suspicious/uninformative)"
        return all_types, reasons

    try:
        selected_set: set[str] = set()
        reasons: dict[str, str] = {}

        # 1. Always-include tier
        for t in ALWAYS_INCLUDE_TIER:
            selected_set.add(t)
            reasons[t] = "always_include: high frequency default"

        # 2. Compressions track trigger
        comps = sensor_data.get("compressions_active")
        if isinstance(comps, list) and len(comps) > 0:
            for t in [
                "compression_interruption",
                "cpr_initiated_ed",
                "compression_mode_change",
                "compression_active_start",
            ]:
                if t not in selected_set:
                    selected_set.add(t)
                    reasons[t] = "sensor_trigger: compressions_active"

        # 3. Device audio trigger
        audio = sensor_data.get("device_audio")
        if isinstance(audio, list) and len(audio) > 0:
            for t in ["defibrillation_shock", "defib_charge_aborted"]:
                if t not in selected_set:
                    selected_set.add(t)
                    reasons[t] = "sensor_trigger: device_audio"

        # 4. Keyword pre-scan trigger
        if keywords:
            for kw in keywords:
                kw_lower = kw.lower()
                for t in all_types:
                    if t not in selected_set:
                        # Check type name or card content
                        if kw_lower in t.lower() or kw_lower in anchor(t).lower():
                            selected_set.add(t)
                            reasons[t] = f"keyword_trigger: '{kw}'"

        # 5. Fail-safe protection against empty sensors / no triggers fired
        if selected_set == set(ALWAYS_INCLUDE_TIER):
            reasons = {}
            for t in all_types:
                if t in ALWAYS_INCLUDE_TIER:
                    reasons[t] = "always_include: high frequency default"
                else:
                    reasons[t] = "fail_safe: empty sensor_data (suspicious/uninformative)"
            return all_types, reasons

        sorted_types = sorted(selected_set)
        sorted_reasons = dict(sorted(reasons.items()))
        return sorted_types, sorted_reasons

    except Exception as e:
        logging.warning(
            f"select_anchors encountered an error/malformed input: {e}. "
            "Falling back to all 39 cards."
        )
        reasons = {t: f"fail_safe: selector error/malformed input ({e})" for t in all_types}
        return all_types, dict(sorted(reasons.items()))


def to_vertex_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """
    Dereferences $defs and $ref inline and strips unsupported keywords
    from a JSON Schema so it is accepted by Vertex AI structured outputs.
    
    Raises:
        ValueError: if recursive references are encountered or if any $ref / $defs remain.
    """
    schema_copy = copy.deepcopy(schema)
    defs = schema_copy.pop("$defs", {})
    if "definitions" in schema_copy:
        defs.update(schema_copy.pop("definitions", {}))

    def dereference(obj: Any, stack: list[str]) -> Any:
        if isinstance(obj, dict):
            if "$ref" in obj:
                ref = obj["$ref"]
                name = ref.split("/")[-1]
                if name in stack:
                    raise ValueError(
                        f"Recursive model reference cannot be flattened for Vertex AI schema: {name}"
                    )
                if name not in defs:
                    raise KeyError(f"Missing $ref definition in schema: {name}")
                resolved = copy.deepcopy(defs[name])
                resolved = dereference(resolved, stack + [name])
                for k, v in obj.items():
                    if k not in ("$ref", "title", "default", "additionalProperties"):
                        resolved[k] = dereference(v, stack)
                return resolved
            else:
                new_dict = {}
                for k, v in obj.items():
                    if k in (
                        "$ref",
                        "$defs",
                        "definitions",
                        "title",
                        "default",
                        "additionalProperties",
                    ):
                        continue
                    new_dict[k] = dereference(v, stack)
                return new_dict
        elif isinstance(obj, list):
            return [dereference(item, stack) for item in obj]
        return obj

    flattened = dereference(schema_copy, [])
    serialized = json.dumps(flattened)
    if '"$ref"' in serialized or '"$defs"' in serialized:
        raise ValueError(
            "to_vertex_schema failed to remove all $ref or $defs from schema"
        )
    return flattened


def slice_extraction_contract_md(selected_types: list[str]) -> str:
    """Returns the extraction_contract.md sections for the selected event types."""
    content = Path("generated/extraction_contract.md").read_text()
    sections: dict[str, str] = {}
    current_et = None
    current_lines: list[str] = []

    for line in content.splitlines():
        if line.startswith("## "):
            if current_et:
                sections[current_et] = "\n".join(current_lines).strip()
            current_et = line[3:].strip()
            current_lines = [line]
        else:
            if current_et:
                current_lines.append(line)
    if current_et:
        sections[current_et] = "\n".join(current_lines).strip()

    out: list[str] = []
    for et in sorted(selected_types):
        if et in sections:
            out.append(sections[et])
        else:
            raise KeyError(
                f"Event type '{et}' not found in generated/extraction_contract.md"
            )
    return "\n\n".join(out)


def compute_prompt_hash(system: str, user: str) -> str:
    """Computes a deterministic SHA-256 hash of the assembled prompt text."""
    h = hashlib.sha256()
    h.update(system.encode("utf-8"))
    h.update(b"\n---\n")
    h.update(user.encode("utf-8"))
    return h.hexdigest()


def write_prompt_snapshot(prompt_hash: str, system: str, user: str) -> Path:
    """Writes the assembled prompt to generated/prompt_snapshots/<hash>.txt idempotently."""
    snapshot_dir = Path("generated/prompt_snapshots")
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_file = snapshot_dir / f"{prompt_hash}.txt"
    if not snapshot_file.exists():
        content = f"# prompt_hash: {prompt_hash}\n{system}\n---\n{user}"
        snapshot_file.write_text(content, encoding="utf-8")
    return snapshot_file


def _get_versions_metadata() -> tuple[str, str, str, str]:
    """Returns (contract_version, dict_version, constitution_hash, anchor_library_version)."""
    m = manifest()
    contract_version = str(m.get("requires_contract_version", "1"))
    dict_version = str(m.get("requires_dict_version", ""))

    system_text = load("system_prompt")
    constitution_hash = hashlib.sha256(system_text.encode("utf-8")).hexdigest()

    # Compute anchor library hash across all sorted anchor YAMLs
    h = hashlib.sha256()
    for p in sorted(Path("prompts/anchors").glob("*.yaml")):
        if p.stem != "_SCHEMA":
            h.update(p.stem.encode("utf-8"))
            h.update(p.read_text().encode("utf-8"))
    anchor_library_version = h.hexdigest()

    return contract_version, dict_version, constitution_hash, anchor_library_version


def _validate_no_unfilled_placeholders(text: str, pass_name: str) -> None:
    """Raises ValueError if any declared placeholder {name} remains unfilled."""
    placeholders_path = Path("prompts/passes/_PLACEHOLDERS.yaml")
    if placeholders_path.exists():
        data = load_yaml(placeholders_path).get(pass_name, {})
        for ph in data.keys():
            pattern = f"{{{ph}}}"
            if pattern in text:
                raise ValueError(
                    f"Unfilled placeholder '{pattern}' in assembled {pass_name} prompt"
                )


def build_p1(
    chunk_index: int,
    chunk_total: int,
    video_duration_s: float,
    win_start: float,
    win_end: float,
    primary_end: float,
    overlap_lead: float,
    win_start_primary: float,
    sensor_data: dict[str, Any] | None = None,
    keywords: list[str] | None = None,
) -> BuiltPrompt:
    """
    Builds the P1 (chunked harvest) prompt and metadata.
    """
    (
        contract_version,
        dict_version,
        constitution_hash,
        anchor_library_version,
    ) = _get_versions_metadata()

    system_template = load("system_prompt")
    system = (
        system_template.replace("{contract_version}", contract_version)
        .replace("{dict_version}", dict_version)
    )

    template = load("pass_1")
    validate_template_placeholders(template, "p1_harvest")
    template_hash = hashlib.sha256(template.encode("utf-8")).hexdigest()

    selected_anchors, selection_reasons = select_anchors(sensor_data, keywords)

    # Concatenate YAML cards
    cards_list = [anchor(et) for et in selected_anchors]
    anchor_cards_str = "\n---\n".join(cards_list)

    # Slice extraction contract
    contract_slice_str = slice_extraction_contract_md(selected_anchors)

    # Prepare sensor block formatting
    def _format_sensor_channel(key: str) -> str:
        if sensor_data and key in sensor_data:
            return json.dumps(sensor_data[key], indent=2, sort_keys=True)
        return "[]"

    user = template
    user = user.replace("{chunk_index}", str(chunk_index))
    user = user.replace("{chunk_total}", str(chunk_total))
    user = user.replace("{video_duration_s}", str(video_duration_s))
    user = user.replace("{win_start}", str(win_start))
    user = user.replace("{win_end}", str(win_end))
    user = user.replace("{primary_end}", str(primary_end))
    user = user.replace("{overlap_lead}", str(overlap_lead))
    user = user.replace("{win_start_primary}", str(win_start_primary))
    user = user.replace(
        "{compression_intervals}", _format_sensor_channel("compressions_active")
    )
    user = user.replace(
        "{device_audio_hits}", _format_sensor_channel("device_audio")
    )
    user = user.replace(
        "{monitor_ocr_series}", _format_sensor_channel("monitor_ocr")
    )
    user = user.replace(
        "{asr_transcript}", _format_sensor_channel("asr_diarized")
    )
    user = user.replace(
        "{quality_windows}", _format_sensor_channel("quality_track")
    )
    user = user.replace("{contract_slice}", contract_slice_str)
    user = user.replace("{anchor_cards}", anchor_cards_str)
    user = user.replace("{contract_version}", contract_version)

    _validate_no_unfilled_placeholders(user, "p1_harvest")
    assert_no_field_names(
        f"{system}\n---\n{user}", "p1_harvest assembled prompt"
    )

    prompt_hash = compute_prompt_hash(system, user)
    write_prompt_snapshot(prompt_hash, system, user)

    response_schema = to_vertex_schema(EventStream.model_json_schema())
    estimated_text_input_tokens = (len(system) + len(user)) // 4

    return BuiltPrompt(
        system=system,
        user=user,
        response_schema=response_schema,
        prompt_hash=prompt_hash,
        selected_anchors=selected_anchors,
        selection_reasons=selection_reasons,
        estimated_text_input_tokens=estimated_text_input_tokens,
        contract_version=contract_version,
        dict_version=dict_version,
        constitution_hash=constitution_hash,
        anchor_library_version=anchor_library_version,
        template_hash=template_hash,
    )


def build_p2(
    candidate_event_json: dict[str, Any] | str,
    clip_t0: float,
    clip_t1: float,
    sensor_slice: dict[str, Any] | str | None,
    event_type: str,
    retrieved_exemplars: str = "",
    keywords: list[str] | None = None,
) -> BuiltPrompt:
    """
    Builds the P2 (single-event zoom verification) prompt and metadata.
    """
    (
        contract_version,
        dict_version,
        constitution_hash,
        anchor_library_version,
    ) = _get_versions_metadata()

    system_template = load("system_prompt")
    system = (
        system_template.replace("{contract_version}", contract_version)
        .replace("{dict_version}", dict_version)
    )

    template = load("pass_2")
    validate_template_placeholders(template, "p2_verify")
    template_hash = hashlib.sha256(template.encode("utf-8")).hexdigest()

    anchor_card_str = anchor(event_type)
    contract_slice_single_str = slice_extraction_contract_md([event_type])

    if isinstance(candidate_event_json, dict):
        candidate_str = json.dumps(candidate_event_json, indent=2, sort_keys=True)
    else:
        candidate_str = str(candidate_event_json)

    if isinstance(sensor_slice, dict):
        sensor_str = json.dumps(sensor_slice, indent=2, sort_keys=True)
    elif sensor_slice is None:
        sensor_str = "[]"
    else:
        sensor_str = str(sensor_slice)

    user = template
    user = user.replace("{candidate_event_json}", candidate_str)
    user = user.replace("{clip_t0}", str(clip_t0))
    user = user.replace("{clip_t1}", str(clip_t1))
    user = user.replace("{sensor_slice}", sensor_str)
    user = user.replace("{anchor_card}", anchor_card_str)
    user = user.replace("{contract_slice_single}", contract_slice_single_str)
    user = user.replace("{retrieved_exemplars}", retrieved_exemplars)
    user = user.replace("{contract_version}", contract_version)
    user = user.replace("{event_type}", event_type)

    _validate_no_unfilled_placeholders(user, "p2_verify")
    assert_no_field_names(
        f"{system}\n---\n{user}", "p2_verify assembled prompt"
    )

    prompt_hash = compute_prompt_hash(system, user)
    write_prompt_snapshot(prompt_hash, system, user)

    response_schema = to_vertex_schema(Event.model_json_schema())
    estimated_text_input_tokens = (len(system) + len(user)) // 4

    return BuiltPrompt(
        system=system,
        user=user,
        response_schema=response_schema,
        prompt_hash=prompt_hash,
        selected_anchors=[event_type],
        selection_reasons={event_type: "candidate_event_type"},
        estimated_text_input_tokens=estimated_text_input_tokens,
        contract_version=contract_version,
        dict_version=dict_version,
        constitution_hash=constitution_hash,
        anchor_library_version=anchor_library_version,
        template_hash=template_hash,
    )
