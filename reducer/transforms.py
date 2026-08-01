"""
Canonical transformation utilities for REDCap submission payload preparation.
Enforces API formatting rules without coercing or mutating internal fact_event floats.
"""

from __future__ import annotations

import datetime
from typing import Any


def to_redcap_datetime(
    t_s: float | int | str | None,
    t0: datetime.datetime | str | float | int | None,
) -> str | None:
    """
    Converts offset seconds (t_s) from video wallclock start (t0) to REDCap datetime string.

    CRITICAL DATETIME FORMAT TRAP:
    The dictionary specifies `datetime_seconds_mdy` for datetime fields, which controls
    UI DISPLAY ONLY in REDCap web interface. The REDCap API import format is STRICTLY
    `%Y-%m-%d %H:%M:%S` (Y-M-D). Sending M-D-Y format to the API import endpoint causes
    silent rejection or uninformative errors. Do NOT change this format to MDY.
    """
    if t_s is None or t0 is None or str(t_s).strip() == "" or str(t0).strip() == "":
        return None
    try:
        offset = float(t_s)
        if offset < 0.0:
            return None
    except (ValueError, TypeError):
        return None

    if isinstance(t0, (int, float)):
        base_dt = datetime.datetime.fromtimestamp(float(t0), tz=datetime.timezone.utc)
    elif isinstance(t0, str):
        try:
            base_dt = datetime.datetime.fromisoformat(t0)
        except ValueError:
            return None
    elif isinstance(t0, datetime.datetime):
        base_dt = t0
    else:
        return None

    res_dt = base_dt + datetime.timedelta(seconds=offset)
    return res_dt.strftime("%Y-%m-%d %H:%M:%S")


def to_redcap_int(val: Any) -> str | None:
    """
    Rounds a numeric value to a whole integer string using Python's half-even rounding.
    REDCap has no sub-second precision for integer seconds fields, but float precision
    is preserved in the underlying fact_event models.
    """
    if val is None or str(val).strip() == "":
        return None
    try:
        f_val = float(val)
        return str(int(round(f_val)))
    except (ValueError, TypeError):
        return None


def to_redcap_float(val: Any) -> str | None:
    """Converts a value to its string float representation for REDCap numeric fields."""
    if val is None or str(val).strip() == "":
        return None
    try:
        f_val = float(val)
        return str(f_val)
    except (ValueError, TypeError):
        return None


def blank_when_null(val: Any) -> Any:
    """Passthrough transformation returning empty string when value is None."""
    if val is None:
        return ""
    return val


def main() -> None:
    raise NotImplementedError("reducer.transforms is a library module. See docs/tasks/D06.md")


if __name__ == "__main__":
    main()
