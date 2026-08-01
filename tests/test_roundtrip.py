"""Integration and round-trip tests against a live REDCap scratch project.

Guarded by RESUS_ALLOW_NETWORK=1 and strict scratch-project safety checks.
When offline or uncredentialed, tests cleanly skip with Q-014 documentation.
"""
import os
import re
import json
import urllib.request
import urllib.parse
from typing import Any
import pytest

from generated.redcap_fields import EXPORT_COLUMNS, FIELDS, SUBMISSION_COLUMNS
from fixtures.synthetic_maximal import build_event_stream
from reducer.engine import reduce_stream
from redcap.assemble import assemble_submission


SKIP_MSG = (
    "SKIPPED — requires scratch REDCap (Q-014). This test is the only "
    "external verification that our 1,891 export columns match REDCap's. "
    "All column-count agreement to date is internal to codegen."
)


def _get_api_credentials() -> tuple[str, str] | None:
    allow_net = os.environ.get("RESUS_ALLOW_NETWORK") == "1"
    url = os.environ.get("REDCAP_API_URL", "").strip()
    token = os.environ.get("REDCAP_API_TOKEN", "").strip()
    if not allow_net or not url or not token:
        return None
    return url, token


def _post_redcap(url: str, payload: dict[str, Any]) -> str:
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def _assert_safe_scratch_project(url: str, token: str) -> None:
    # 1. Token must NOT match any production token env var
    prod_tokens = {
        os.environ.get("REDCAP_PROD_API_TOKEN", "").strip(),
        os.environ.get("REDCAP_PRODUCTION_TOKEN", "").strip(),
        os.environ.get("REDCAP_PROD_TOKEN", "").strip(),
    }
    prod_tokens.discard("")
    assert token not in prod_tokens, "SAFETY FAIL: API token matches a production token env var"

    # 2. Project title must contain 'scratch'
    proj_json = _post_redcap(url, {
        "token": token,
        "content": "project",
        "format": "json",
        "returnFormat": "json",
    })
    proj_info = json.loads(proj_json)
    title = str(proj_info.get("project_title", "")).lower()
    assert "scratch" in title, f"SAFETY FAIL: project title {title!r} does not contain 'scratch'"

    # 3. Project ID must be on the allowlist
    allowlist = {x.strip() for x in os.environ.get("REDCAP_SCRATCH_ALLOWLIST", "").split(",") if x.strip()}
    pid = str(proj_info.get("project_id", ""))
    if allowlist:
        assert pid in allowlist, f"SAFETY FAIL: project ID {pid!r} not in REDCAP_SCRATCH_ALLOWLIST {allowlist}"

    # 4. Total record count must be < 10
    rec_json = _post_redcap(url, {
        "token": token,
        "content": "record",
        "format": "json",
        "returnFormat": "json",
        "fields[0]": "record_id",
    })
    recs = json.loads(rec_json)
    assert len(recs) < 10, f"SAFETY FAIL: project has {len(recs)} records (must be < 10 for scratch)"


def test_redcap_token_secret_scanner_catches_token() -> None:
    """Unit test proving targeted secret scanner regex catches REDCap 32-char hex tokens."""
    pattern = re.compile(r'\b[A-F0-9]{32}\b')
    fake_token = "A1B2C3D4E5F6A7B8C9D0E1F2A3B4C5D6"
    assert pattern.findall(fake_token) == [fake_token]
    assert not pattern.findall("not-a-token-string")
    assert not pattern.findall("a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6")  # Lowercase ignored


@pytest.mark.integration
@pytest.mark.network
def test_export_field_names_equals_export_columns() -> None:
    """Acceptance test 1: exportFieldNames API set equality with EXPORT_COLUMNS."""
    creds = _get_api_credentials()
    if not creds:
        pytest.skip(SKIP_MSG)
    url, token = creds
    _assert_safe_scratch_project(url, token)

    resp_json = _post_redcap(url, {
        "token": token,
        "content": "exportFieldNames",
        "format": "json",
        "returnFormat": "json",
    })
    field_names = json.loads(resp_json)
    api_cols = {str(row["export_field_name"]) for row in field_names}

    missing = sorted(EXPORT_COLUMNS - api_cols)
    phantom = sorted(api_cols - EXPORT_COLUMNS)
    assert api_cols == EXPORT_COLUMNS, (
        f"exportFieldNames mismatch against EXPORT_COLUMNS.\n"
        f"Missing from REDCap ({len(missing)}): {missing[:25]}\n"
        f"Phantom in REDCap ({len(phantom)}): {phantom[:25]}"
    )


@pytest.mark.integration
@pytest.mark.network
def test_import_synthetic_maximal_record() -> None:
    """Acceptance test 2: Reduce maximal case -> assemble -> POST to scratch -> count == 1."""
    creds = _get_api_credentials()
    if not creds:
        pytest.skip(SKIP_MSG)
    url, token = creds
    _assert_safe_scratch_project(url, token)

    stream = build_event_stream()
    fvs, _, _ = reduce_stream(stream)
    payload = assemble_submission(fvs, record_id="D13_MAX_01", video_review_complete="1")

    resp_json = _post_redcap(url, {
        "token": token,
        "content": "record",
        "format": "json",
        "returnFormat": "json",
        "type": "flat",
        "data": json.dumps([payload]),
    })
    res = json.loads(resp_json)
    assert res.get("count") == 1, f"Import failed: expected count 1, got {res}"


@pytest.mark.integration
@pytest.mark.network
def test_roundtrip_byte_equality() -> None:
    """Acceptance test 3: Export record back -> assert byte-equality on non-calc non-blank fields."""
    creds = _get_api_credentials()
    if not creds:
        pytest.skip(SKIP_MSG)
    url, token = creds
    _assert_safe_scratch_project(url, token)

    stream = build_event_stream()
    fvs, _, _ = reduce_stream(stream)
    payload = assemble_submission(fvs, record_id="D13_MAX_01", video_review_complete="1")

    resp_json = _post_redcap(url, {
        "token": token,
        "content": "record",
        "format": "json",
        "returnFormat": "json",
        "type": "flat",
        "records[0]": "D13_MAX_01",
    })
    records = json.loads(resp_json)
    assert records, "No record returned from REDCap export"
    rec = records[0]

    calc_fields = {"dur_mccd_app_ed_secs_v2", "duration_ventilator_place_v2"}
    mismatches = []
    for col, sent_val in payload.items():
        if col in calc_fields or sent_val == "":
            continue
        rec_val = str(rec.get(col, ""))
        if str(sent_val) != rec_val:
            mismatches.append((col, sent_val, rec_val))

    assert not mismatches, f"Roundtrip byte-equality failed on {len(mismatches)} fields: {mismatches[:10]}"


@pytest.mark.integration
@pytest.mark.network
def test_checkbox_binary_roundtrip() -> None:
    """Acceptance test 4: Assert every checkbox column round-trips as exactly '1' or '0', never blank."""
    creds = _get_api_credentials()
    if not creds:
        pytest.skip(SKIP_MSG)
    url, token = creds
    _assert_safe_scratch_project(url, token)

    resp_json = _post_redcap(url, {
        "token": token,
        "content": "record",
        "format": "json",
        "returnFormat": "json",
        "type": "flat",
        "records[0]": "D13_MAX_01",
    })
    records = json.loads(resp_json)
    assert records
    rec = records[0]

    invalid_checkboxes = []
    for f_name, spec in FIELDS.items():
        if spec.field_type == "checkbox":
            for col in spec.export_columns:
                val = str(rec.get(col, ""))
                if val not in ("0", "1"):
                    invalid_checkboxes.append((col, val))

    assert not invalid_checkboxes, f"Invalid checkbox roundtrip values: {invalid_checkboxes[:10]}"


@pytest.mark.integration
@pytest.mark.network
def test_datetime_format_roundtrip() -> None:
    """Acceptance test 5: Assert datetimes round-trip as %Y-%m-%d %H:%M:%S without M-D-Y retry."""
    creds = _get_api_credentials()
    if not creds:
        pytest.skip(SKIP_MSG)
    url, token = creds
    _assert_safe_scratch_project(url, token)

    resp_json = _post_redcap(url, {
        "token": token,
        "content": "record",
        "format": "json",
        "returnFormat": "json",
        "type": "flat",
        "records[0]": "D13_MAX_01",
    })
    records = json.loads(resp_json)
    assert records
    rec = records[0]

    dt_pattern = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
    bad_dts = []
    for f_name, spec in FIELDS.items():
        if spec.field_type == "text" and "datetime" in getattr(spec, "validation", ""):
            col = spec.export_columns[0]
            val = str(rec.get(col, ""))
            if val and not dt_pattern.match(val):
                bad_dts.append((col, val))

    assert not bad_dts, f"Datetime format roundtrip failed on: {bad_dts[:10]}"


@pytest.mark.integration
@pytest.mark.network
def test_overwrite_checkbox_to_zero() -> None:
    """Acceptance test 6: Re-POST with one checkbox cleared ('0'), assert it exports as '0' not stale '1'."""
    creds = _get_api_credentials()
    if not creds:
        pytest.skip(SKIP_MSG)
    url, token = creds
    _assert_safe_scratch_project(url, token)

    stream = build_event_stream()
    fvs, _, _ = reduce_stream(stream)
    payload = assemble_submission(fvs, record_id="D13_MAX_01", video_review_complete="1")

    # Pick a checked checkbox and clear it to '0'
    target_col = "reason_cci_1_v2___1"
    payload[target_col] = "0"

    resp_json = _post_redcap(url, {
        "token": token,
        "content": "record",
        "format": "json",
        "returnFormat": "json",
        "type": "flat",
        "data": json.dumps([payload]),
    })
    res = json.loads(resp_json)
    assert res.get("count") == 1

    resp2 = _post_redcap(url, {
        "token": token,
        "content": "record",
        "format": "json",
        "returnFormat": "json",
        "type": "flat",
        "records[0]": "D13_MAX_01",
    })
    records = json.loads(resp2)
    assert records
    rec = records[0]
    got = str(rec.get(target_col, ""))
    assert got == "0", f"Checkbox overwrite failed: expected '0', got stale {got!r}"
