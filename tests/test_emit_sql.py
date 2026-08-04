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
    """Assert exactly 9 CREATE VIEW statements in audit_views.sql."""
    sql = generate_audit_views()
    create_views = re.findall(r"CREATE OR REPLACE VIEW `\{curated_dataset\}\.[a-z0-9_]+`", sql)
    assert len(create_views) == 9, f"Expected 9 views in audit_views.sql, found: {len(create_views)} ({create_views})"


def test_field_seed_jsonl_count_and_content() -> None:
    """Assert seed file has exactly len(FIELDS)+2 rows and required governance keys."""
    seed = generate_field_seed_jsonl()
    lines = [l for l in seed.splitlines() if l.strip()]
    expected_count = len(FIELDS) + 2
    assert len(lines) == expected_count, f"Expected {expected_count} rows, got {len(lines)}"
    first_row = json.loads(lines[0])
    for key in (
        "dict_version",
        "field_name",
        "form_name",
        "domain",
        "field_type",
        "field_label",
        "choices",
        "validation",
        "val_min",
        "val_max",
        "branching_logic",
        "is_required",
        "export_columns",
        "source_class",
        "extraction_difficulty",
        "target_accuracy",
        "owning_event_types",
        "expected_utd_floor",
        "repeat_group",
        "repeat_index",
        "is_importable",
        "is_calc_field",
    ):
        assert key in first_row, f"Required governance key {key} missing from seed JSONL"


def parse_ddl_columns(table_name: str, ddl_path: Path) -> set[str]:
    content = ddl_path.read_text()
    pattern = rf"CREATE TABLE IF NOT EXISTS `\{{raw_dataset\}}\.{re.escape(table_name)}` \((.*?)\) (?:PARTITION|CLUSTER)"
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        raise ValueError(f"Table {table_name} not found in {ddl_path}")
    block = match.group(1)
    cols = set()
    for line in block.splitlines():
        line = line.strip().rstrip(",")
        if line and not line.startswith("--"):
            parts = line.split()
            if parts:
                cols.add(parts[0])
    return cols


def first_line_of_seed() -> str:
    seed_path = Path("generated/dim_redcap_field_seed.jsonl")
    with seed_path.open() as f:
        return f.readline().strip()


def parse_view_column_refs(views_path: Path) -> dict[str, dict[str, set[str]]]:
    content = views_path.read_text()
    view_blocks = re.findall(
        r"CREATE OR REPLACE VIEW `[^`]+\.([^`]+)` AS(.*?)(?=(?:CREATE OR REPLACE VIEW|\Z))",
        content,
        re.DOTALL,
    )
    result = {}
    for view_name, block_text in view_blocks:
        refs = {"dim_redcap_field": set()}
        if "dim_redcap_field" in block_text:
            for match in re.finditer(r"\bdf\.([a-zA-Z0-9_]+)", block_text):
                refs["dim_redcap_field"].add(match.group(1))
        result[view_name] = refs
    return result


def test_seed_columns_match_ddl_spec() -> None:
    """dim_redcap_field's seed must match its DDL, and every column referenced by an audit view must exist in the DDL."""
    ddl_cols = parse_ddl_columns("dim_redcap_field", Path("generated/bq_ddl.sql"))
    seed_cols = set(json.loads(first_line_of_seed()))
    assert seed_cols == ddl_cols, f"seed/DDL mismatch: {seed_cols ^ ddl_cols}"

    for view, refs in parse_view_column_refs(Path("generated/audit_views.sql")).items():
        unknown = refs["dim_redcap_field"] - ddl_cols
        assert not unknown, f"{view} references undeclared columns: {unknown}"


def extract_view(view_name: str, sql: str) -> str:
    match = re.search(
        rf"CREATE OR REPLACE VIEW `.*?\.{re.escape(view_name)}` AS(.*?)(?=(?:CREATE OR REPLACE VIEW|\Z))",
        sql,
        re.DOTALL,
    )
    if not match:
        raise ValueError(f"View {view_name} not found")
    return match.group(1)


def test_hallucination_view_filters_on_ai_direct() -> None:
    """AI_DERIVED fields legitimately have empty source_event_ids — their
    value derives from event ABSENCE. Filtering on importability instead of
    source_class makes this view meaningless."""
    sql = Path("generated/audit_views.sql").read_text()
    block = extract_view("v_audit_hallucination", sql)
    assert "source_class = 'AI_DIRECT'" in block
    assert "is_importable" not in block
    assert "JOIN" not in block.upper(), "v_audit_hallucination must be a single table scan"


def seed_rows() -> list[dict]:
    seed = generate_field_seed_jsonl()
    rows = []
    for line in seed.splitlines():
        if line.strip():
            data = json.loads(line)
            if data["field_name"] in FIELDS:
                rows.append(data)
    return rows


def test_boolean_flags_derive_from_source_class() -> None:
    for row in seed_rows():
        spec = FIELDS[row["field_name"]]
        assert row["is_calc_field"] == spec.server_computed
        assert row["is_importable"] == (spec.carries_data and not spec.server_computed)


def test_dim_redcap_field_has_13_domains() -> None:
    """Assert all 911 seed rows have non-null domain and exactly 13 distinct registry domains."""
    domains = set()
    for line in generate_field_seed_jsonl().splitlines():
        if line.strip():
            row = json.loads(line)
            domain = row.get("domain")
            assert domain is not None and domain != "", f"Field {row.get('field_name')} has null/empty domain"
            domains.add(domain)
    assert len(domains) == 13, f"Expected 13 domains, got {len(domains)}: {sorted(domains)}"


def test_emit_sql_determinism() -> None:
    """Assert codegen functions produce identical output across repeated calls."""
    assert generate_bq_ddl() == generate_bq_ddl()
    assert generate_v_redcap_wide() == generate_v_redcap_wide()
    assert generate_audit_views() == generate_audit_views()
    assert generate_field_seed_jsonl() == generate_field_seed_jsonl()


def test_audit_views_branching_discipline() -> None:
    """Assert audit views filter on branching_satisfied and abstained so Q1 returns zero on healthy cases."""
    sql = generate_audit_views()
    assert "f.branching_satisfied = TRUE" in sql, "Audit views must filter on branching_satisfied = TRUE"
    assert "f.abstained = FALSE" in sql, "v_audit_missing_fields must filter out abstained fields"
    assert "f.branching_satisfied = FALSE" in sql, "v_audit_branching_violation must check branching_satisfied = FALSE"

