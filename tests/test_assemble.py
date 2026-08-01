"""
Acceptance test suite for D11 REDCap client and payload assembly.
Verifies set-equality against SUBMISSION_COLUMNS, checkbox default completeness,
non-AI blank column presence, quarantine submission blocking, HTTP 400 non-retry,
exponential backoff on 5xx, and token redaction in audit logs.
"""
from __future__ import annotations

import io
import json
import urllib.error
from typing import Any
import pytest

import generated.redcap_fields as rf
from fixtures.synthetic_streams import get_maximal_stream
from reducer.engine import reduce_stream, FieldValue
from redcap.assemble import assemble_submission
from redcap.client import (
    submit_record,
    REDCapSubmissionError,
    REDCapSubmissionLog,
    redact_token,
)


def test_assemble_submission_set_equality():
    """1. Payload is exactly set-equal to SUBMISSION_COLUMNS, both directions."""
    fvs, _, _ = reduce_stream(get_maximal_stream())
    payload, quars = assemble_submission("case_eq_01", "run_01", fvs)
    assert not quars, f"Unexpected quarantine reasons: {quars}"

    expected_set = set(rf.IMPORTABLE_COLUMNS) | {
        "record_id",
        "video_review_complete",
    }
    payload_set = set(payload.keys())

    missing = expected_set - payload_set
    extra = payload_set - expected_set

    assert payload_set == expected_set, (
        f"Payload keys do not match SUBMISSION_COLUMNS.\n"
        f"Missing ({len(missing)}): {sorted(list(missing))[:15]}\n"
        f"Extra ({len(extra)}): {sorted(list(extra))[:15]}"
    )
    assert len(payload) == 1891, f"Expected 1891 keys, got {len(payload)}"


def test_checkbox_completeness_and_overwrite():
    """2. Every checkbox choice column defaults to '0' if unselected."""
    fvs, _, _ = reduce_stream(get_maximal_stream())

    # Find a checkbox column that is set to '1' in maximal stream
    cb_cols = [
        c
        for s in rf.FIELDS.values()
        if getattr(s, "field_type", "") == "checkbox"
        and not getattr(s, "server_computed", False)
        for c in s.export_columns
    ]
    assert cb_cols, "No checkbox columns found in dictionary"
    target_col = cb_cols[0]

    # First submission: set target_col to "1"
    fv1 = [f for f in fvs if f.export_column == target_col]
    if fv1:
        fv1[0].value = "1"
    else:
        fvs.append(
            FieldValue(
                field_name=target_col,
                export_column=target_col,
                value="1",
                value_label="Checked",
                source_class="AI_DERIVED",
                source_event_ids=["e1"],
                validation_passed=True,
            )
        )
    payload1, quars1 = assemble_submission("case_cb_01", "run_01", fvs)
    assert not quars1
    assert payload1[target_col] == "1"

    # Second submission: remove target_col from field_values (simulate unchecking)
    fvs2 = [f for f in fvs if f.export_column != target_col]
    payload2, quars2 = assemble_submission("case_cb_01", "run_02", fvs2)
    assert not quars2
    assert (
        target_col in payload2
    ), f"Checkbox col {target_col} omitted from payload"
    assert (
        payload2[target_col] == "0"
    ), f"Expected '0', got {payload2[target_col]!r}"


def test_ten_non_ai_columns_present_and_blank():
    """3. ROSTER_JOIN and HUMAN_ONLY columns are present and blank (''). Calc fields absent."""
    fvs, _, _ = reduce_stream(get_maximal_stream())
    payload, quars = assemble_submission("case_nonai_01", "run_01", fvs)
    assert not quars

    # Assert calc fields are absent
    assert "dur_mccd_app_ed_secs_v2" not in payload
    assert "duration_ventilator_place_v2" not in payload

    # Assert 10 non-AI columns are present with value ""
    non_ai_cols = [
        c
        for s in rf.FIELDS.values()
        if getattr(s, "source_class", "") in ("ROSTER_JOIN", "HUMAN_ONLY")
        for c in s.export_columns
    ]
    assert (
        len(non_ai_cols) == 10
    ), f"Expected 10 non-AI columns, found {len(non_ai_cols)}"
    for col in non_ai_cols:
        assert (
            col in payload
        ), f"Non-AI column {col} missing from assembled payload"
        assert (
            payload[col] == ""
        ), f"Non-AI column {col} should be blank '', got {payload[col]!r}"


def test_quarantine_blocks_whole_submission():
    """4. Quarantine blocks the entire submission if any field fails validation or is unverified."""
    fvs, _, _ = reduce_stream(get_maximal_stream())

    # Case A: Validation failure
    fvs_bad_val = list(fvs)
    fvs_bad_val[0].validation_passed = False
    payload_a, quars_a = assemble_submission(
        "case_bad_val", "run_01", fvs_bad_val
    )
    assert (
        payload_a == {}
    ), "Payload must be empty ({}) when quarantine fires on validation failure"
    assert len(quars_a) >= 1
    assert "failed validation" in quars_a[0]

    # Case B: Unverified routed field
    fvs[0].validation_passed = True
    fvs_unver = list(fvs)
    fvs_unver[0].routed_to_human = True
    fvs_unver[0].human_verified = False
    payload_b, quars_b = assemble_submission(
        "case_unverified", "run_01", fvs_unver
    )
    assert (
        payload_b == {}
    ), "Payload must be empty ({}) when field is routed but unverified"
    assert len(quars_b) >= 1
    assert "unverified" in quars_b[0]


def test_400_is_never_retried():
    """5. HTTP 400 validation error is parsed, attached to quarantine, and never retried."""
    fvs, _, _ = reduce_stream(get_maximal_stream())
    payload, _ = assemble_submission("case_400", "run_01", fvs)

    call_count = 0

    def mock_opener(req: Any, timeout: int = 30) -> Any:
        nonlocal call_count
        call_count += 1
        err_body = (
            r'{"error": "Field [video_access_type] has invalid choice code 99"}'
        ).encode("utf-8")
        fp = io.BytesIO(err_body)
        raise urllib.error.HTTPError(
            req.full_url, 400, "Bad Request", {}, fp  # type: ignore[arg-type]
        )

    with pytest.raises(REDCapSubmissionError) as exc_info:
        submit_record(
            "https://mock.redcap.org/api/",
            "SUPERSECRETTOKEN1234567890",
            payload,
            case_id="case_400",
            run_id="run_01",
            transport_opener=mock_opener,
        )

    assert exc_info.value.status_code == 400
    assert call_count == 1, f"Expected exactly 1 call (no retry on 400), got {call_count}"
    assert any(
        "invalid choice code" in str(r)
        for r in exc_info.value.quarantine_reasons
    )


def test_500_retries_with_backoff():
    """5b. HTTP 500 server errors retry up to max_retries."""
    fvs, _, _ = reduce_stream(get_maximal_stream())
    payload, _ = assemble_submission("case_500", "run_01", fvs)

    call_count = 0

    class MockResponse:
        def __init__(self, body: bytes):
            self._body = body

        def getcode(self) -> int:
            return 200

        def read(self) -> bytes:
            return self._body

        def __enter__(self) -> MockResponse:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

    def mock_opener(req: Any, timeout: int = 30) -> Any:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            fp = io.BytesIO(b"Internal Server Error")
            raise urllib.error.HTTPError(
                req.full_url, 500, "Server Error", {}, fp  # type: ignore[arg-type]
            )
        return MockResponse(b'{"count": 1}')

    resp, log_entry = submit_record(
        "https://mock.redcap.org/api/",
        "SUPERSECRETTOKEN1234567890",
        payload,
        case_id="case_500",
        run_id="run_01",
        max_retries=3,
        backoff_base_s=0.01,
        transport_opener=mock_opener,
    )
    assert call_count == 3
    assert resp == {"count": 1}
    assert log_entry.response_status == 200


def test_idempotency_and_token_redaction():
    """6. API token is redacted from logged payload and overwriteBehavior is set."""
    fvs, _, _ = reduce_stream(get_maximal_stream())
    payload, _ = assemble_submission("case_idemp", "run_01", fvs)
    secret_token = "MYSECRETREDCAPTOKEN_32CHAR_HEX__"

    posted_body: bytes = b""

    class MockResponse:
        def getcode(self) -> int:
            return 200

        def read(self) -> bytes:
            return b'{"count": 1}'

        def __enter__(self) -> MockResponse:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

    def mock_opener(req: Any, timeout: int = 30) -> Any:
        nonlocal posted_body
        posted_body = req.data
        return MockResponse()

    _, log_entry = submit_record(
        "https://mock.redcap.org/api/",
        secret_token,
        payload,
        case_id="case_idemp",
        run_id="run_01",
        transport_opener=mock_opener,
    )

    # Verify overwriteBehavior is in POST parameters
    body_str = posted_body.decode("utf-8")
    assert "overwriteBehavior=overwrite" in body_str

    # Verify token is redacted in log_entry
    log_str = json.dumps(
        {
            "payload": log_entry.payload,
            "response": log_entry.response_body,
            "status": log_entry.response_status,
        }
    )
    assert (
        secret_token not in log_str
    ), "Token leaked into REDCapSubmissionLog!"
    assert (
        secret_token not in str(log_entry)
    ), "Token leaked in dataclass string rep!"
