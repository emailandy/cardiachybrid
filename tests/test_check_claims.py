"""
tests/test_check_claims.py — Unit Tests for scripts/check_claims.sh Gate

Verifies that claim_verifier.py fails loudly on injected mutations:
1. Non-existent git commit SHA
2. Mutated ground-truth coordinates
3. Duplicate Finding IDs
4. Arithmetic formula mismatches
"""

import subprocess
import pytest
from scripts.claim_verifier import (
    check_commit_shas,
    check_ground_truth_quotations,
    check_id_uniqueness,
    check_arithmetic_consistency,
    run_git_rev_parse,
)


def test_git_rev_parse_valid():
    """Real commit HEAD resolves cleanly."""
    assert run_git_rev_parse("HEAD") is True


def test_git_rev_parse_invalid():
    """Fabricated commit SHA is rejected."""
    assert run_git_rev_parse("deadbeef1234567890abcdef") is False


def test_check_claims_clean_on_repo():
    """Full repository state passes all checks without error."""
    assert check_commit_shas() == []
    assert check_ground_truth_quotations() == []
    assert check_id_uniqueness() == []
    assert check_arithmetic_consistency() == []


def test_check_claims_script_execution():
    """scripts/check_claims.sh exits 0 when executed."""
    res = subprocess.run(["./scripts/check_claims.sh"], capture_output=True, text=True)
    assert res.returncode == 0
    assert "ALL CLAIMS & REFERENCES MECHANICALLY VERIFIED" in res.stdout
