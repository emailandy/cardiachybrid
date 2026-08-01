"""
REDCap API client for submitting assembled payloads.
Implements retry with exponential backoff and jitter for 5xx and connection errors,
loud fail without retry on 400 Bad Request, token redaction in audit logs,
and idempotent updates keyed on (case_id, run_id).
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from typing import Any, Callable
import urllib.error
import urllib.parse
import urllib.request


class REDCapSubmissionError(Exception):
    """Raised when REDCap submission fails (e.g. HTTP 400 validation error or unrecoverable error)."""
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: str | None = None,
        quarantine_reasons: list[str] | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
        self.quarantine_reasons = quarantine_reasons or []


@dataclass
class REDCapSubmissionLog:
    """Record of a submission attempt for redcap_submission logging."""
    submission_id: str
    case_id: str
    run_id: str
    dict_version: str
    payload: dict[str, Any]  # API token MUST be redacted
    submitted_at: str
    response_status: int
    response_body: Any
    event_date: str


def redact_token(data: Any, token: str | None = None) -> Any:
    """Redacts API token from dictionaries, strings, or lists."""
    if isinstance(data, dict):
        res = {}
        for k, v in data.items():
            if k.lower() == "token":
                res[k] = "[REDACTED]"
            else:
                res[k] = redact_token(v, token)
        return res
    elif isinstance(data, list):
        return [redact_token(item, token) for item in data]
    elif isinstance(data, str) and token and len(token) > 4:
        return data.replace(token, "[REDACTED]")
    return data


def submit_record(
    url: str,
    token: str,
    payload: dict[str, str],
    case_id: str = "",
    run_id: str = "",
    dict_version: str = "",
    max_retries: int = 3,
    backoff_base_s: float = 1.0,
    transport_opener: Callable[..., Any] | None = None,
) -> tuple[dict[str, Any], REDCapSubmissionLog]:
    """
    Submits an assembled record payload to the REDCap API.

    Args:
        url: REDCap API endpoint URL.
        token: API authentication token (from env/secret manager).
        payload: Assembled record payload dictionary (1,891 SUBMISSION_COLUMNS).
        case_id: Case ID for logging.
        run_id: Run ID for logging.
        dict_version: Data dictionary version hash.
        max_retries: Max retry attempts for 5xx/connection errors.
        backoff_base_s: Base delay in seconds for exponential backoff.
        transport_opener: Custom URL opener for testing/mocking.

    Returns:
        (response_data, submission_log):
          - response_data: Parsed JSON response from REDCap (e.g. {"count": 1}).
          - submission_log: REDCapSubmissionLog with redacted token.
    """
    if not token:
        raise ValueError("REDCap API token must not be empty.")
    if not url:
        raise ValueError("REDCap API URL must not be empty.")

    # Prepare form data per REDCap API flat JSON specification
    form_params = {
        "token": token,
        "content": "record",
        "format": "json",
        "type": "flat",
        "overwriteBehavior": "overwrite",
        "returnContent": "count",
        "returnFormat": "json",
        "data": json.dumps([payload]),
    }
    encoded_data = urllib.parse.urlencode(form_params).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=encoded_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    opener = transport_opener or urllib.request.urlopen
    attempt = 0
    last_error: Exception | None = None

    while attempt <= max_retries:
        try:
            with opener(req, timeout=30) as resp:
                status_code = resp.getcode()
                body_str = resp.read().decode("utf-8")
                try:
                    resp_json = json.loads(body_str)
                except Exception:
                    resp_json = {"raw": body_str}

                log_entry = REDCapSubmissionLog(
                    submission_id=f"{case_id}_{run_id}_{int(time.time())}",
                    case_id=case_id,
                    run_id=run_id,
                    dict_version=dict_version,
                    payload=redact_token(payload, token),
                    submitted_at=time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                    response_status=status_code,
                    response_body=resp_json,
                    event_date=time.strftime("%Y-%m-%d", time.gmtime()),
                )
                return resp_json, log_entry

        except urllib.error.HTTPError as e:
            status_code = e.code
            body_str = e.read().decode("utf-8", errors="replace")
            # NEVER RETRY 400 — parse REDCap field-level validation errors and fail loudly
            if status_code == 400:
                quarantine_reasons = []
                try:
                    err_json = json.loads(body_str)
                    if isinstance(err_json, dict) and "error" in err_json:
                        quarantine_reasons.append(str(err_json["error"]))
                    elif isinstance(err_json, list):
                        for item in err_json:
                            quarantine_reasons.append(str(item))
                    else:
                        quarantine_reasons.append(body_str)
                except Exception:
                    quarantine_reasons.append(body_str)

                raise REDCapSubmissionError(
                    f"REDCap HTTP 400 Bad Request: {body_str}",
                    status_code=400,
                    response_body=body_str,
                    quarantine_reasons=quarantine_reasons,
                ) from e
            elif 500 <= status_code < 600:
                last_error = e
                attempt += 1
                if attempt > max_retries:
                    break
                sleep_s = (backoff_base_s * (2 ** (attempt - 1))) + random.uniform(0.0, 0.5)
                time.sleep(sleep_s)
            else:
                raise REDCapSubmissionError(
                    f"REDCap HTTP {status_code}: {body_str}",
                    status_code=status_code,
                    response_body=body_str,
                ) from e

        except (urllib.error.URLError, OSError) as e:
            last_error = e
            attempt += 1
            if attempt > max_retries:
                break
            sleep_s = (backoff_base_s * (2 ** (attempt - 1))) + random.uniform(0.0, 0.5)
            time.sleep(sleep_s)

    raise REDCapSubmissionError(
        f"REDCap submission failed after {max_retries} retries: {last_error}"
    )
