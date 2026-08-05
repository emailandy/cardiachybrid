"""
Cross-field validators for D06.
Provides validate_stream() for V1-V10 (stream-level checks) and validate_payload() for V11-V12 (payload-level checks).
All severities are loaded from config/validators.yaml.
Zero REDCap field name literals in code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codegen.yamlio import load_yaml
import generated.redcap_fields as rf
from generated.models import Event, Interval


@dataclass(slots=True, frozen=True)
class Result:
    validator_id: str
    severity: str
    field_name: str | None
    message: str

    def __iter__(self):
        return iter((self.severity, self.field_name, self.message))

    def __getitem__(self, idx: int):
        return (self.severity, self.field_name, self.message)[idx]


def _load_config() -> dict[str, Any]:
    return load_yaml(Path("config/validators.yaml"))


def _get_severity(cfg: dict[str, Any], validator_id: str) -> str:
    v_dict = cfg.get("validators", {}).get(validator_id, {})
    return str(v_dict.get("severity", "QUARANTINE"))


def validate_stream(
    record: dict[str, Any],
    events: list[Event],
    intervals: list[Interval],
    config: dict[str, Any] | None = None,
) -> list[Result]:
    """Runs cross-field stream validators V1-V10 against record and stream events/intervals."""
    if config is None:
        config = _load_config()

    # V00: timestamp in range [0, video_duration_s] (short-circuit on failure)
    sev = _get_severity(config, "V00_timestamp_in_range")
    dur_field = config.get("config_mappings", {}).get("video_duration_field", "")
    try:
        max_dur = float(record.get(dur_field, 3600.0))
    except (ValueError, TypeError):
        max_dur = 3600.0

    v00_results: list[Result] = []
    for e in events:
        if e.timestamp_s < 0.0 or e.timestamp_s > max_dur:
            v00_results.append(
                Result(
                    validator_id="V00_timestamp_in_range",
                    severity=sev,
                    field_name=None,
                    message=f"Event {e.type} attribute=timestamp_s value={e.timestamp_s} out of range [0.0, {max_dur}]",
                )
            )
        for k, val in e.attributes.items():
            if k.endswith("_s") or k.endswith("_ts") or k in {"t_decision_s", "t_confirmed_s", "vitals_t_s"}:
                try:
                    f_val = float(val)
                    if f_val < 0.0 or f_val > max_dur:
                        v00_results.append(
                            Result(
                                validator_id="V00_timestamp_in_range",
                                severity=sev,
                                field_name=None,
                                message=f"Event {e.type} attribute={k} value={f_val} out of range [0.0, {max_dur}]",
                            )
                        )
                except (ValueError, TypeError):
                    pass
    for iv in intervals:
        if iv.t_start_s < 0.0 or iv.t_start_s > max_dur:
            v00_results.append(
                Result(
                    validator_id="V00_timestamp_in_range",
                    severity=sev,
                    field_name=None,
                    message=f"Interval {iv.type} attribute=t_start_s value={iv.t_start_s} out of range [0.0, {max_dur}]",
                )
            )
        if iv.t_end_s is not None and (iv.t_end_s < 0.0 or iv.t_end_s > max_dur):
            v00_results.append(
                Result(
                    validator_id="V00_timestamp_in_range",
                    severity=sev,
                    field_name=None,
                    message=f"Interval {iv.type} attribute=t_end_s value={iv.t_end_s} out of range [0.0, {max_dur}]",
                )
            )
    if v00_results:
        return v00_results

    results: list[Result] = []

    # V01: every start < end
    sev = _get_severity(config, "V01_start_before_end")
    for iv in intervals:
        if iv.t_end_s is not None and iv.t_end_s < iv.t_start_s:
            results.append(
                Result(
                    validator_id="V01_start_before_end",
                    severity=sev,
                    field_name=None,
                    message=f"Interval {iv.type} start {iv.t_start_s} >= end {iv.t_end_s}",
                )
            )

    # V02: MCCD adjustment window ⊆ MCCD application window
    sev = _get_severity(config, "V02_mccd_adj_within_app")
    app_starts = [e.timestamp_s for e in events if e.type == "mccd_application_start"]
    app_ends = [e.timestamp_s for e in events if e.type in ("mccd_removed", "mccd_application_end")]
    min_app = min(app_starts) if app_starts else None
    max_app = max(app_ends) if app_ends else None
    for e in events:
        if e.type == "mccd_adjustment":
            if (min_app is not None and e.timestamp_s < min_app) or (max_app is not None and e.timestamp_s > max_app):
                results.append(
                    Result(
                        validator_id="V02_mccd_adj_within_app",
                        severity=sev,
                        field_name=None,
                        message=f"MCCD adjustment at {e.timestamp_s}s outside application window",
                    )
                )

    # V03: num_times_defib == count of populated defib timestamps
    sev = _get_severity(config, "V03_defib_count_match")
    defib_count_field = config.get("config_mappings", {}).get("defib_count_field", "")
    defib_group = config.get("config_mappings", {}).get("defib_group_name", "")
    try:
        expected_count = int(record.get(defib_count_field, 0))
    except (ValueError, TypeError):
        expected_count = 0
    # Find all populated defib timestamp fields in record
    populated_defib_ts = 0
    for k, val in record.items():
        f_spec = rf.FIELDS.get(k)
        if f_spec and f_spec.repeat_group == defib_group and "datetime" in str(f_spec.validation):
            if val is not None and str(val).strip() != "":
                try:
                    if float(val) >= 0.0:
                        populated_defib_ts += 1
                except (ValueError, TypeError):
                    populated_defib_ts += 1
    if expected_count != populated_defib_ts:
        results.append(
            Result(
                validator_id="V03_defib_count_match",
                severity=sev,
                field_name=defib_count_field,
                message=f"num_times_defib ({expected_count}) != populated defib timestamps ({populated_defib_ts})",
            )
        )

    # V04: every shock timestamp falls inside some CCI (only valid for manual compression mode)
    if record.get("compression_mode", "manual") == "manual":
        sev = _get_severity(config, "V04_shock_inside_cci")
        ccis = [iv for iv in intervals if iv.type == "compression_interruption"]
        for e in events:
            if e.type == "defibrillation_shock":
                in_cci = any(iv.t_start_s <= e.timestamp_s <= (iv.t_end_s or iv.t_start_s) for iv in ccis)
                if not in_cci:
                    results.append(
                        Result(
                            validator_id="V04_shock_inside_cci",
                            severity=sev,
                            field_name=None,
                            message=f"Shock at {e.timestamp_s}s outside any CCI interval",
                        )
                    )

    # V05: any shock present => shockable rhythm recorded SOMEWHERE in the case
    sev = _get_severity(config, "V05_shock_implies_shockable")
    shocks = [e for e in events if e.type == "defibrillation_shock"]
    if shocks:
        shock_set = {"vf", "pulseless_vt", "aed_shockable", "aicd_shockable"}
        has_shockable = False
        for e in events:
            if e.type == "rhythm_check":
                r_val = str(e.attributes.get("rhythm", "")).lower()
                if r_val in shock_set or e.attributes.get("rhythm_shockable") is True:
                    has_shockable = True
                    break
        if not has_shockable:
            results.append(
                Result(
                    validator_id="V05_shock_implies_shockable",
                    severity=sev,
                    field_name=None,
                    message="Shock present but no shockable rhythm recorded anywhere in stream",
                )
            )

    # V06: no medication event inside a ROSC window
    sev = _get_severity(config, "V06_no_med_in_rosc")
    roscs = [iv for iv in intervals if iv.type == "rosc"]
    for e in events:
        if e.type == "medication_administration":
            in_rosc = any(iv.t_start_s <= e.timestamp_s <= (iv.t_end_s or iv.t_start_s) for iv in roscs)
            if in_rosc:
                results.append(
                    Result(
                        validator_id="V06_no_med_in_rosc",
                        severity=sev,
                        field_name=None,
                        message=f"Medication administered at {e.timestamp_s}s during ROSC window",
                    )
                )

    # V07: CCIs non-overlapping and monotonic
    sev = _get_severity(config, "V07_cci_non_overlapping")
    sorted_ccis = sorted([iv for iv in intervals if iv.type == "compression_interruption"], key=lambda x: x.t_start_s)
    for i in range(len(sorted_ccis) - 1):
        iv1, iv2 = sorted_ccis[i], sorted_ccis[i + 1]
        if iv1.t_end_s is not None and iv2.t_start_s < iv1.t_end_s:
            results.append(
                Result(
                    validator_id="V07_cci_non_overlapping",
                    severity=sev,
                    field_name=None,
                    message=f"Overlapping CCI intervals: [{iv1.t_start_s}, {iv1.t_end_s}] and [{iv2.t_start_s}, ...]",
                )
            )

    # V08: ROSC episodes non-overlapping, end_i <= start_{i+1}
    sev = _get_severity(config, "V08_rosc_non_overlapping")
    sorted_roscs = sorted([iv for iv in intervals if iv.type == "rosc"], key=lambda x: x.t_start_s)
    for i in range(len(sorted_roscs) - 1):
        r1, r2 = sorted_roscs[i], sorted_roscs[i + 1]
        if r1.t_end_s is not None and r2.t_start_s < r1.t_end_s:
            results.append(
                Result(
                    validator_id="V08_rosc_non_overlapping",
                    severity=sev,
                    field_name=None,
                    message=f"Overlapping ROSC intervals: [{r1.t_start_s}, {r1.t_end_s}] and [{r2.t_start_s}, ...]",
                )
            )

    # V09: patient_enters_room <= every other timestamp
    sev = _get_severity(config, "V09_room_entry_first")
    entry_events = [e for e in events if e.type == "patient_enters_room"]
    if entry_events:
        t_entry = min(e.timestamp_s for e in entry_events)
        for e in events:
            if e.type != "patient_enters_room" and e.timestamp_s < t_entry:
                results.append(
                    Result(
                        validator_id="V09_room_entry_first",
                        severity=sev,
                        field_name=None,
                        message=f"Event {e.type} timestamp {e.timestamp_s} < patient_enters_room timestamp {t_entry}",
                    )
                )

    # V10: every airway attempt with successful=true has a subsequent confirmation
    sev = _get_severity(config, "V10_airway_confirmation")
    confirms = [e.timestamp_s for e in events if e.type == "airway_confirmation"]
    for e in events:
        if e.type == "airway_attempt" and e.attributes.get("successful") is True:
            has_subsequent = any(ts >= e.timestamp_s for ts in confirms)
            if not has_subsequent:
                results.append(
                    Result(
                        validator_id="V10_airway_confirmation",
                        severity=sev,
                        field_name=None,
                        message=f"Successful airway attempt at {e.timestamp_s}s lacks subsequent confirmation",
                    )
                )

    return results


def validate_payload(
    payload: dict[str, Any],
    dict_version: str | None = None,
    config: dict[str, Any] | None = None,
) -> list[Result]:
    """Runs payload validators V11-V12 against assembled REDCap payload dictionary."""
    if config is None:
        config = _load_config()

    results: list[Result] = []

    # V11: calc fields absent from the payload
    sev = _get_severity(config, "V11_no_calc_fields")
    for k in payload.keys():
        f_spec = rf.FIELDS.get(k)
        if f_spec and f_spec.field_type == "calc":
            results.append(
                Result(
                    validator_id="V11_no_calc_fields",
                    severity=sev,
                    field_name=k,
                    message=f"calc field {k!r} present in submitted payload",
                )
            )

    # V12: dict_version in payload matches dictionary/dict_version.txt
    sev = _get_severity(config, "V12_dict_version_match")
    ver_field = config.get("config_mappings", {}).get("dict_version_field", "dict_version")
    payload_ver = payload.get(ver_field, dict_version)
    expected_ver = ""
    ver_file = Path("dictionary/dict_version.txt")
    if ver_file.exists():
        expected_ver = ver_file.read_text().strip()
    if expected_ver and str(payload_ver).strip() != expected_ver:
        results.append(
            Result(
                validator_id="V12_dict_version_match",
                severity=sev,
                field_name=ver_field,
                message=f"dict_version {payload_ver!r} != expected {expected_ver!r}",
            )
        )

    return results


def main() -> None:
    raise NotImplementedError("reducer.validators is a library module. See docs/tasks/D06.md")


if __name__ == "__main__":
    main()
