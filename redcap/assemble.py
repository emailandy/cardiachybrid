"""
REDCap submission payload assembly.
Converts reducer FieldValue outputs into importable REDCap JSON payloads.
Upholds I2, I3, I4, I5, and I6.
"""
from __future__ import annotations

from typing import Any
import generated.redcap_fields as rf
from reducer.engine import FieldValue


def assemble_submission(
    case_id: str,
    run_id: str,
    field_values: list[FieldValue],
    fields_spec: dict[str, rf.FieldSpec] | None = None,
) -> tuple[dict[str, str], list[str]]:
    """
    Assembles a REDCap record payload from reduced field values.

    Returns:
        (payload, quarantine_reasons):
          - payload: dict mapping REDCap export column names to string values.
            If quarantined, payload is empty ({}).
          - quarantine_reasons: list of strings describing validation or
            review failures.
    """
    if fields_spec is None:
        fields_spec = rf.FIELDS

    quarantine_reasons: list[str] = []

    # 1. Quarantine checks: blocks the WHOLE submission
    for fv in field_values:
        if not fv.validation_passed:
            quarantine_reasons.append(
                f"Field {fv.field_name} failed validation"
            )
        if fv.routed_to_human and not getattr(fv, "human_verified", False):
            quarantine_reasons.append(
                f"Field {fv.field_name} routed to human review but unverified"
            )

    if quarantine_reasons:
        return {}, quarantine_reasons

    payload: dict[str, str] = {}

    # 2. System / case identity columns
    # Q-013 INTERIM DEFAULT: video_review_complete="1" (Unverified/Incomplete) is hard-coded
    # until affirmative case-level human sign-off table (case_signoff) is implemented.
    # Never emit "2" from field-level inference alone.
    payload["record_id"] = case_id
    payload["video_review_complete"] = "1"

    # 3. Non-AI columns (ROSTER_JOIN and HUMAN_ONLY): sent as "" (present and blank)
    # so REDCap overwriteBehavior=overwrite clears any stale manual entries.
    for f_name, spec in fields_spec.items():
        if (
            getattr(spec, "server_computed", False)
            or getattr(spec, "source_class", "") == "REDCAP_CALC"
        ):
            continue
        if getattr(spec, "source_class", "") in ("ROSTER_JOIN", "HUMAN_ONLY"):
            for col in spec.export_columns:
                payload[col] = ""

    # 4. Process AI-derived / conditional field values from reducer
    for fv in field_values:
        spec = fields_spec.get(fv.field_name) or fields_spec.get(
            fv.field_name.split("___")[0]
        )
        if spec:
            if (
                getattr(spec, "server_computed", False)
                or getattr(spec, "source_class", "") == "REDCAP_CALC"
            ):
                continue
            if getattr(spec, "source_class", "") in (
                "ROSTER_JOIN",
                "HUMAN_ONLY",
            ):
                continue

        # Inactive branching conditions emit explicit blank "" so REDCap clears them
        if getattr(fv, "branching_satisfied", True) is False:
            payload[fv.export_column] = ""
        else:
            val = fv.value
            payload[fv.export_column] = (
                str(val) if val is not None and val != "" else ""
            )

    # 5. CHECKBOX COMPLETENESS (I4): iterate FIELDS after main loop,
    # default every checkbox choice column to "0" if not already populated.
    for f_name, spec in fields_spec.items():
        if (
            getattr(spec, "server_computed", False)
            or getattr(spec, "source_class", "") == "REDCAP_CALC"
        ):
            continue
        if getattr(spec, "source_class", "") in ("ROSTER_JOIN", "HUMAN_ONLY"):
            continue
        if getattr(spec, "field_type", "") == "checkbox":
            for col in spec.export_columns:
                if payload.get(col, "") == "":
                    payload[col] = "0"

    # 6. Assert set-equality against SUBMISSION_COLUMNS (1,891 keys derived from FIELDS)
    expected_keys = set(rf.IMPORTABLE_COLUMNS) | {
        "record_id",
        "video_review_complete",
    }
    payload_keys = set(payload.keys())
    missing = expected_keys - payload_keys
    extra = payload_keys - expected_keys
    if missing or extra:
        missing_sample = sorted(list(missing))[:15]
        extra_sample = sorted(list(extra))[:15]
        raise ValueError(
            f"Payload keys do not match SUBMISSION_COLUMNS. "
            f"Missing ({len(missing)}): {missing_sample} | Extra ({len(extra)}): {extra_sample}"
        )

    return payload, []
