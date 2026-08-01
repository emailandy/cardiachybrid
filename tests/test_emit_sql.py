"""
tests/test_emit_sql.py — Unit tests for codegen/emit_sql.py and generated SQL artifacts.
"""

import json
import hashlib
import re
from pathlib import Path
import pytest
from generated.redcap_fields import FIELDS, IMPORTABLE_COLUMNS
from codegen.emit_sql import (
    generate_bq_ddl,
    generate_field_seed_jsonl,
    generate_v_redcap_wide,
    generate_audit_views,
)


def test_bq_ddl_table_count() -> None:
    """Assert exactly 13 physical tables are generated in {raw_dataset}."""
    ddl = generate_bq_ddl()
    create_statements = re.findall(r"CREATE TABLE IF NOT EXISTS `\{raw_dataset\}\.[a-z0-9_]+`", ddl)
    assert len(create_statements) == 13, f"Expected 13 tables, found: {len(create_statements)} ({create_statements})"
    assert "text_embedding" not in ddl, "fact_utterance must not contain text_embedding (Q-011 deferred)"
    assert "`{raw_dataset}.fact_near_miss`" in ddl, "fact_near_miss must be in raw_dataset per CORRECTION 1"


def test_count_fields_present_in_wide_view() -> None:
    """
    Count fields are text+number, reducer-populated. Only the two
    `calc` fields are server-computed and excluded.
    """
    sql = generate_v_redcap_wide()
    for f in (
        "num_cci_v2",
        "num_times_defib_ed_v2",
        "num_ed_adv_airway_att_v2",
        "num_rosc_episodes_ed_v2",
        "how_many_ventilation_delay_v2",
    ):
        assert f"'{f}'" in sql, f"{f} missing from wide view"
    assert "dur_mccd_app_ed_secs_v2" not in sql
    assert "duration_ventilator_place_v2" not in sql


def test_wide_view_column_count_matches_importable() -> None:
    """Assert exactly len(IMPORTABLE_COLUMNS) MAX(IF(...)) expressions plus case_id, run_id, event_date."""
    sql = generate_v_redcap_wide()
    max_if_matches = re.findall(r"MAX\(IF\(field_name = '[^']+', value, NULL\)\)", sql)
    assert len(max_if_matches) == len(
        IMPORTABLE_COLUMNS
    ), f"Expected {len(IMPORTABLE_COLUMNS)} MAX(IF) expressions, got {len(max_if_matches)}"
    for col in ("case_id,", "run_id,", "event_date,"):
        assert col in sql, f"Required column {col} missing from wide view SELECT"


def test_wide_view_checksum() -> None:
    """Assert that -- CHECKSUM in header matches SHA-256 of the body."""
    sql = generate_v_redcap_wide()
    lines = sql.splitlines(keepends=True)
    checksum = None
    body_lines = []
    for line in lines:
        if line.startswith("-- CHECKSUM:"):
            checksum = line.split("-- CHECKSUM:")[1].strip()
        elif line.startswith("-- Generated"):
            continue
        else:
            body_lines.append(line)
    assert checksum is not None, "CHECKSUM header missing from v_redcap_wide.sql"
    body_text = "".join(body_lines)
    actual = hashlib.sha256(body_text.encode("utf-8")).hexdigest()
    assert actual == checksum, f"Checksum mismatch: expected {checksum}, got {actual}"


def test_audit_views_count() -> None:
    """Assert exactly 6 CREATE VIEW statements in audit_views.sql."""
    sql = generate_audit_views()
    create_views = re.findall(r"CREATE OR REPLACE VIEW `\{curated_dataset\}\.[a-z0-9_]+`", sql)
    assert len(create_views) == 6, f"Expected 6 views in audit_views.sql, found: {len(create_views)} ({create_views})"


def test_field_seed_jsonl_count_and_content() -> None:
    """Assert seed file has exactly len(FIELDS) rows and required governance keys."""
    seed = generate_field_seed_jsonl()
    lines = [l for l in seed.splitlines() if l.strip()]
    assert len(lines) == len(FIELDS), f"Expected {len(FIELDS)} rows, got {len(lines)}"
    first_row = json.loads(lines[0])
    for key in (
        "field_name",
        "dict_version",
        "form_name",
        "field_type",
        "field_label",
        "choices",
        "is_importable",
        "expected_utd_floor",
        "is_calc_field",
        "is_phi",
    ):
        assert key in first_row, f"Required governance key {key} missing from seed JSONL"


def test_emit_sql_determinism() -> None:
    """Assert codegen functions produce identical output across repeated calls."""
    assert generate_bq_ddl() == generate_bq_ddl()
    assert generate_v_redcap_wide() == generate_v_redcap_wide()
    assert generate_audit_views() == generate_audit_views()
    assert generate_field_seed_jsonl() == generate_field_seed_jsonl()
