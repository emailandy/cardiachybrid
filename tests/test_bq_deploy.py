"""
tests/test_bq_deploy.py — Unit tests for bq/deploy.py refusal controls and dry-run mode.
"""

import hashlib
import pytest
from pathlib import Path
from bq.deploy import (
    check_dictionary_drift,
    verify_wide_view_checksum,
    resolve_datasets,
    deploy_sql_artifact,
    parse_args,
)


def test_deploy_requires_dataset_arg() -> None:
    """Assert --dataset is a required argument with no default."""
    with pytest.raises(SystemExit):
        parse_args([])


def test_resolve_datasets_standard_and_explicit() -> None:
    """Assert prefix and explicit raw names resolve to (raw, curated)."""
    assert resolve_datasets("resus") == ("resus_raw", "resus_curated")
    assert resolve_datasets("resus_raw") == ("resus_raw", "resus_curated")
    assert resolve_datasets("ci_run_123") == ("ci_run_123_raw", "ci_run_123_curated")


def test_resolve_datasets_refuses_scratch() -> None:
    """Assert CORRECTION 2: refuse to deploy to any dataset ending in _scratch or containing scratch."""
    for bad_ds in ("resus_scratch", "ci_run_scratch", "scratch_db"):
        with pytest.raises(ValueError, match="NEVER receives a table from generated/bq_ddl.sql"):
            resolve_datasets(bad_ds)


def test_wide_view_checksum_refuses_hand_edit(tmp_path: Path) -> None:
    """Assert verify_wide_view_checksum raises ValueError if body was modified."""
    fake_sql = tmp_path / "fake_wide.sql"
    fake_sql.write_text(
        "-- CHECKSUM: 0000000000000000000000000000000000000000000000000000000000000000\n"
        "-- Generated SQL artifact. DO NOT EDIT BY HAND.\n"
        "SELECT * FROM modified_by_hand;\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="v_redcap_wide.sql checksum mismatch: file has been hand-edited"):
        verify_wide_view_checksum(fake_sql)


def test_check_dictionary_drift_refuses_drift(tmp_path: Path) -> None:
    """Assert check_dictionary_drift raises ValueError when sha256 != dict_version.txt."""
    inst = tmp_path / "instrument.csv"
    ver = tmp_path / "dict_version.txt"
    inst.write_text("field_name,form_name\nfoo,bar\n", encoding="utf-8")
    ver.write_text("deadbeef12345678", encoding="utf-8")
    with pytest.raises(ValueError, match="Dictionary drift detected"):
        check_dictionary_drift(inst, ver)


def test_deploy_sql_artifact_dry_run() -> None:
    """Assert dry-run formats placeholders and returns statements without calling BQ CLI."""
    sql = "CREATE TABLE `{raw_dataset}.test` (id INT64); CREATE VIEW `{curated_dataset}.v` AS SELECT 1;"
    stmts = deploy_sql_artifact(sql, "resus_raw", "resus_curated", dry_run=True)
    assert len(stmts) == 2
    assert stmts[0] == "CREATE TABLE `resus_raw.test` (id INT64)"
    assert stmts[1] == "CREATE VIEW `resus_curated.v` AS SELECT 1"
