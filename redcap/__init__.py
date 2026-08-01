"""
REDCap integration package: client and payload assembly.
"""
from __future__ import annotations

from redcap.assemble import assemble_submission
from redcap.client import (
    submit_record,
    REDCapSubmissionError,
    REDCapSubmissionLog,
    redact_token,
)

__all__ = [
    "assemble_submission",
    "submit_record",
    "REDCapSubmissionError",
    "REDCapSubmissionLog",
    "redact_token",
]
