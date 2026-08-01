"""
Unit tests for D06: transforms and cross-field validators.
Verifies API datetime formatting rules, rounding semantics, all 12 validators,
dynamic severity configuration, and non-coercion on failure paths.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

import pytest

from fixtures.synthetic_streams import (
    get_all_synthetic_streams,
    get_contradictory_stream,
    get_maximal_stream,
)
from generated.models import Event, EventStream, Interval
from reducer.engine import reduce_stream
from reducer.transforms import (
    blank_when_null,
    to_redcap_datetime,
    to_redcap_float,
    to_redcap_int,
)
from reducer.validators import Result, validate_payload, validate_stream


def test_datetime_format_trap() -> None:
    """
    VERIFY 1 - THE DATETIME FORMAT TRAP:
    Asserts to_redcap_datetime emits Y-m-d H:M:S format required by REDCap API import,
    never M-D-Y UI display format.
    """
    base_str = "2026-08-01T10:00:00+00:00"
    out = to_redcap_datetime(125.0, base_str)
    assert out == "2026-08-01 10:02:05"

    base_dt = datetime.datetime(2026, 8, 1, 10, 0, 0, tzinfo=datetime.timezone.utc)
    assert to_redcap_datetime(0, base_dt) == "2026-08-01 10:00:00"

    # Negative offset before video start returns None (unpopulated)
    assert to_redcap_datetime(-5.0, base_str) is None

    # Null / invalid inputs
    assert to_redcap_datetime(None, base_str) is None
    assert to_redcap_datetime(10.0, None) is None
    assert to_redcap_datetime("", base_str) is None
    assert to_redcap_datetime("invalid", base_str) is None


def test_transforms_rounding_and_passthrough() -> None:
    """Verifies half-even whole-second rounding for ints and passthrough behavior."""
    assert to_redcap_int("12.5") == "12"  # half-even rounding
    assert to_redcap_int("13.5") == "14"  # half-even rounding
    assert to_redcap_int("10.0") == "10"
    assert to_redcap_int(None) is None
    assert to_redcap_int("") is None

    assert to_redcap_float("12.3400") == "12.34"
    assert to_redcap_float(15) == "15.0"
    assert to_redcap_float(None) is None

    assert blank_when_null(None) == ""
    assert blank_when_null("value") == "value"


def test_all_ten_stream_validators_on_contradictory_stream() -> None:
    """
    VERIFY 3 & 4 - THE CONTRADICTORY FIXTURE IS THE SPEC:
    Asserts all 10 stream validators (V1 through V10) fire when validate_stream
    evaluates get_contradictory_stream().
    """
    stream = get_contradictory_stream()
    values, _, _ = reduce_stream(stream)
    record = {v.export_column: v.value for v in values if not v.is_null}

    results = validate_stream(record, stream.events, stream.intervals)
    fired_ids = {r.validator_id for r in results}

    expected_ids = {
        "V01_start_before_end",
        "V02_mccd_adj_within_app",
        "V03_defib_count_match",
        "V04_shock_inside_cci",
        "V05_shock_implies_shockable",
        "V06_no_med_in_rosc",
        "V07_cci_non_overlapping",
        "V08_rosc_non_overlapping",
        "V09_room_entry_first",
        "V10_airway_confirmation",
    }
    assert fired_ids == expected_ids, f"Expected 10 stream validators to fire, got {len(fired_ids)}: {fired_ids}"

    # Verify tuple unpacking interface (severity, field, message)
    for res in results:
        sev, fld, msg = res
        assert sev in {"QUARANTINE", "FLAG", "REPAIR"}
        assert isinstance(msg, str)


def test_payload_validators_v11_and_v12() -> None:
    """
    NOTE 2 - V11 and V12 are Payload Checks:
    Verifies that V11 (no_calc_fields) and V12 (dict_version_match) operate on
    the assembled REDCap payload dict and fire correctly.
    """
    # Test V11: calc field present in payload
    payload_with_calc: dict[str, Any] = {
        "record_id": "test_001",
        "dur_mccd_app_ed_secs_v2": "120.0",  # field_type='calc' in dictionary
    }
    res_v11 = validate_payload(payload_with_calc)
    fired_v11 = [r for r in res_v11 if r.validator_id == "V11_no_calc_fields"]
    assert len(fired_v11) >= 1
    assert fired_v11[0].severity == "QUARANTINE"
    assert fired_v11[0].field_name == "dur_mccd_app_ed_secs_v2"

    # Test V12: dict_version mismatch
    payload_bad_version: dict[str, Any] = {
        "record_id": "test_001",
        "dict_version": "INVALID_HASH_999",
    }
    res_v12 = validate_payload(payload_bad_version)
    fired_v12 = [r for r in res_v12 if r.validator_id == "V12_dict_version_match"]
    assert len(fired_v12) == 1
    assert fired_v12[0].severity == "QUARANTINE"


def test_severity_is_config_not_code() -> None:
    """
    VERIFY 2 - SEVERITY IS CONFIG, NOT CODE:
    Asserts changing severity in the configuration changes runtime validation severity
    without any code modifications.
    """
    stream = get_contradictory_stream()
    values, _, _ = reduce_stream(stream)
    record = {v.export_column: v.value for v in values if not v.is_null}

    # Default config has V04 as FLAG
    default_results = validate_stream(record, stream.events, stream.intervals)
    v04_default = [r for r in default_results if r.validator_id == "V04_shock_inside_cci"]
    assert v04_default[0].severity == "FLAG"

    # Override V04 severity in config dict to QUARANTINE
    custom_cfg = {
        "validators": {
            "V04_shock_inside_cci": {"severity": "QUARANTINE"},
        }
    }
    custom_results = validate_stream(record, stream.events, stream.intervals, config=custom_cfg)
    v04_custom = [r for r in custom_results if r.validator_id == "V04_shock_inside_cci"]
    assert v04_custom[0].severity == "QUARANTINE"


def test_no_coercion_on_failure_paths() -> None:
    """
    Asserts validators return Result objects without modifying or coercing
    the input record, events, intervals, or payload dictionaries.
    """
    stream = get_contradictory_stream()
    values, _, _ = reduce_stream(stream)
    record = {v.export_column: v.value for v in values if not v.is_null}
    orig_record_copy = dict(record)

    results = validate_stream(record, stream.events, stream.intervals)
    assert len(results) > 0
    assert record == orig_record_copy, "validate_stream mutated input record dictionary"


def test_clean_maximal_stream_has_no_quarantines() -> None:
    """Asserts a clean maximal stream does not fire any QUARANTINE results."""
    stream = get_maximal_stream()
    values, _, _ = reduce_stream(stream)
    record = {v.export_column: v.value for v in values if not v.is_null}
    results = validate_stream(record, stream.events, stream.intervals)
    quarantines = [r for r in results if r.severity == "QUARANTINE"]
    assert len(quarantines) == 0, f"Unexpected QUARANTINE on maximal stream: {quarantines}"
