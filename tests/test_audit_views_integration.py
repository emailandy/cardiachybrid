"""
tests/test_audit_views_integration.py — Integration test suite for BigQuery audit views.
Seeds nodepeel:resus_scratch with a tiny hand-built case containing ONE deliberate instance
of each defect, asserting each view returns ONLY its own defect and that the AI_DERIVED
negative control is excluded from v_audit_hallucination.
"""
from __future__ import annotations

import json
import os
import subprocess
import pytest
import google.oauth2.credentials
from google.cloud import bigquery
from pathlib import Path

pytestmark = [
    pytest.mark.integration,
    pytest.mark.network,
]


def _get_bq_client(project: str = "nodepeel") -> bigquery.Client:
    try:
        out = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True,
            text=True,
            check=True,
        )
        token = out.stdout.strip()
        creds = google.oauth2.credentials.Credentials(token=token)
        return bigquery.Client(project=project, credentials=creds)
    except Exception:
        return bigquery.Client(project=project)


@pytest.fixture
def scratch_bq_client() -> bigquery.Client:
    client = _get_bq_client("nodepeel")
    dataset_id = "nodepeel.resus_scratch"
    client.create_dataset(dataset_id, exists_ok=True)

    def cleanup() -> None:
        for name in (
            "v_audit_hallucination",
            "v_audit_missing_fields",
            "v_audit_branching_violation",
            "v_audit_low_utd",
            "v_exemplar_store",
            "v_audit_domain_coverage",
            "v_audit_source_class_drift",
            "dim_redcap_field",
            "fact_redcap_field",
        ):
            client.delete_table(f"{dataset_id}.{name}", not_found_ok=True)

    cleanup()
    try:
        yield client
    finally:
        cleanup()


def test_audit_views_integration_defects_and_negative_control(scratch_bq_client: bigquery.Client) -> None:
    """Proves all 7 audit/curated views select exactly their intended defect rows and ignore non-defects."""
    client = scratch_bq_client

    # 1. Create dim_redcap_field
    client.query("""
        CREATE TABLE `nodepeel.resus_scratch.dim_redcap_field` (
          dict_version STRING NOT NULL,
          field_name STRING NOT NULL,
          form_name STRING,
          domain STRING NOT NULL,
          field_type STRING,
          field_label STRING,
          choices JSON,
          validation STRING,
          val_min STRING,
          val_max STRING,
          branching_logic STRING,
          is_required BOOL,
          export_columns JSON,
          source_class STRING,
          extraction_difficulty STRING,
          target_accuracy FLOAT64,
          owning_event_types JSON,
          expected_utd_floor FLOAT64,
          repeat_group STRING,
          repeat_index INT64,
          is_importable BOOL,
          is_calc_field BOOL
        );
    """).result()

    # 2. Create fact_redcap_field
    client.query("""
        CREATE TABLE `nodepeel.resus_scratch.fact_redcap_field` (
          case_id STRING NOT NULL,
          run_id STRING NOT NULL,
          field_name STRING NOT NULL,
          value STRING,
          dict_version STRING,
          source_class STRING,
          branching_satisfied BOOL,
          abstained BOOL,
          source_event_ids ARRAY<STRING>,
          human_verified BOOL,
          human_value STRING,
          event_date DATE
        );
    """).result()

    # 3. Seed dim_redcap_field with 8 fields (6 defects/controls + low_utd negative control + drift test)
    client.query("""
        INSERT INTO `nodepeel.resus_scratch.dim_redcap_field` (
          dict_version, field_name, form_name, domain, field_type, field_label, choices,
          validation, val_min, val_max, branching_logic, is_required, export_columns,
          source_class, extraction_difficulty, target_accuracy, owning_event_types,
          expected_utd_floor, repeat_group, repeat_index, is_importable, is_calc_field
        ) VALUES
        ('v1.0.0', 'field_ai_direct_halluc', 'video_review', 'airway', 'text', 'label', JSON '{}',
         '', '', '', '', FALSE, JSON '["field_ai_direct_halluc"]',
         'AI_DIRECT', 'LOW', 1.0, JSON '[]', 0.0, '', NULL, TRUE, FALSE),
        ('v1.0.0', 'field_missing', 'video_review', 'cci', 'text', 'label', JSON '{}',
         '', '', '', '', TRUE, JSON '["field_missing"]',
         'AI_DIRECT', 'LOW', 1.0, JSON '[]', 0.0, '', NULL, TRUE, FALSE),
        ('v1.0.0', 'field_branching_viol', 'video_review', 'drugs', 'text', 'label', JSON '{}',
         '', '', '', '[foo] = "1"', FALSE, JSON '["field_branching_viol"]',
         'AI_DIRECT', 'LOW', 1.0, JSON '[]', 0.0, '', NULL, TRUE, FALSE),
        ('v1.0.0', 'field_low_utd', 'video_review', 'ecmo', 'text', 'label', JSON '{}',
         '', '', '', '', FALSE, JSON '["field_low_utd"]',
         'AI_DIRECT', 'HIGH', 1.0, JSON '[]', 0.30, '', NULL, TRUE, FALSE),
        ('v1.0.0', 'field_low_utd_neg', 'video_review', 'ecmo', 'text', 'label', JSON '{}',
         '', '', '', '', FALSE, JSON '["field_low_utd_neg"]',
         'AI_DIRECT', 'HIGH', 1.0, JSON '[]', 0.30, '', NULL, TRUE, FALSE),
        ('v1.0.0', 'field_exemplar', 'video_review', 'rosc', 'text', 'label', JSON '{}',
         '', '', '', '', FALSE, JSON '["field_exemplar"]',
         'AI_DIRECT', 'LOW', 1.0, JSON '[]', 0.0, '', NULL, TRUE, FALSE),
        ('v1.0.0', 'field_ai_derived_neg', 'video_review', 'mccd', 'radio', 'label', JSON '{"0":"No","1":"Yes"}',
         '', '', '', '', FALSE, JSON '["field_ai_derived_neg"]',
         'AI_DERIVED', 'LOW', 1.0, JSON '[]', 0.0, '', NULL, TRUE, FALSE),
        ('v1.0.0', 'field_drift_test', 'video_review', 'redcap_internal', 'text', 'label', JSON '{}',
         '', '', '', '', FALSE, JSON '["field_drift_test"]',
         'AI_DERIVED', 'LOW', 1.0, JSON '[]', 0.0, '', NULL, TRUE, FALSE);
    """).result()

    # 4. Seed fact_redcap_field
    # - field_low_utd: abstained on 1 of 50 rows -> actual_utd_rate = 0.02 < 0.30 -> FIRES
    # - field_low_utd_neg: abstained on 20 of 50 rows -> actual_utd_rate = 0.40 >= 0.30 -> MUST NOT FIRE
    low_utd_rows = ",\n".join(
        f"('c{i}', 'r1', 'field_low_utd', 'val', 'v1.0.0', 'AI_DIRECT', TRUE, FALSE, ['e3'], FALSE, NULL, '2026-08-01')"
        for i in range(2, 51)
    )
    low_utd_neg_abstained = ",\n".join(
        f"('c{i}', 'r1', 'field_low_utd_neg', '', 'v1.0.0', 'AI_DIRECT', TRUE, TRUE, [], FALSE, NULL, '2026-08-01')"
        for i in range(1, 21)
    )
    low_utd_neg_populated = ",\n".join(
        f"('c{i}', 'r1', 'field_low_utd_neg', 'val', 'v1.0.0', 'AI_DIRECT', TRUE, FALSE, ['e5'], FALSE, NULL, '2026-08-01')"
        for i in range(21, 51)
    )

    client.query(f"""
        INSERT INTO `nodepeel.resus_scratch.fact_redcap_field` (
          case_id, run_id, field_name, value, dict_version, source_class,
          branching_satisfied, abstained, source_event_ids, human_verified, human_value, event_date
        ) VALUES
        ('c1', 'r1', 'field_ai_direct_halluc', 'halluc_val', 'v1.0.0', 'AI_DIRECT', TRUE, FALSE, [], FALSE, NULL, '2026-08-01'),
        ('c1', 'r1', 'field_missing', '', 'v1.0.0', 'AI_DIRECT', TRUE, FALSE, ['e1'], FALSE, NULL, '2026-08-01'),
        ('c1', 'r1', 'field_branching_viol', 'viol_val', 'v1.0.0', 'AI_DIRECT', FALSE, FALSE, ['e2'], FALSE, NULL, '2026-08-01'),
        ('c1', 'r1', 'field_low_utd', '', 'v1.0.0', 'AI_DIRECT', TRUE, TRUE, [], FALSE, NULL, '2026-08-01'),
        ('c1', 'r1', 'field_exemplar', 'ai_val', 'v1.0.0', 'AI_DIRECT', TRUE, FALSE, ['e4'], TRUE, 'human_val', '2026-08-01'),
        ('c1', 'r1', 'field_ai_derived_neg', '1', 'v1.0.0', 'AI_DERIVED', TRUE, FALSE, [], FALSE, NULL, '2026-08-01'),
        ('c1', 'r1', 'field_drift_test', 'val', 'v1.0.0', 'AI_DIRECT', TRUE, FALSE, ['e6'], FALSE, NULL, '2026-08-01'),
        {low_utd_rows},
        {low_utd_neg_abstained},
        {low_utd_neg_populated};
    """).result()

    # 5. Create all 7 views pointing to nodepeel.resus_scratch
    client.query("""
        CREATE OR REPLACE VIEW `nodepeel.resus_scratch.v_audit_hallucination` AS
        SELECT f.case_id, f.run_id, f.field_name, f.value
        FROM `nodepeel.resus_scratch.fact_redcap_field` f
        WHERE f.source_class = 'AI_DIRECT'
          AND f.value IS NOT NULL AND f.value != ''
          AND (f.source_event_ids IS NULL OR ARRAY_LENGTH(f.source_event_ids) = 0);
    """).result()

    client.query("""
        CREATE OR REPLACE VIEW `nodepeel.resus_scratch.v_audit_missing_fields` AS
        SELECT f.case_id, f.run_id, f.field_name
        FROM `nodepeel.resus_scratch.fact_redcap_field` f
        JOIN `nodepeel.resus_scratch.dim_redcap_field` df
          ON f.field_name = df.field_name
        WHERE df.is_importable = TRUE
          AND df.is_calc_field = FALSE
          AND df.source_class NOT IN ('HUMAN_ONLY', 'ROSTER_JOIN', 'REDCAP_CALC')
          AND f.branching_satisfied = TRUE
          AND f.abstained = FALSE
          AND (f.value IS NULL OR f.value = '');
    """).result()

    client.query("""
        CREATE OR REPLACE VIEW `nodepeel.resus_scratch.v_audit_branching_violation` AS
        SELECT f.case_id, f.run_id, f.field_name, f.value
        FROM `nodepeel.resus_scratch.fact_redcap_field` f
        JOIN `nodepeel.resus_scratch.dim_redcap_field` df
          ON f.field_name = df.field_name
        WHERE f.branching_satisfied = FALSE
          AND f.value IS NOT NULL
          AND f.value != '';
    """).result()

    client.query("""
        CREATE OR REPLACE VIEW `nodepeel.resus_scratch.v_audit_low_utd` AS
        SELECT
          df.field_name,
          df.domain,
          df.expected_utd_floor,
          COUNTIF(f.abstained = TRUE) AS abstained_count,
          COUNT(*) AS total_cases,
          ROUND(COUNTIF(f.abstained = TRUE) / NULLIF(COUNT(*), 0), 4) AS actual_utd_rate
        FROM `nodepeel.resus_scratch.fact_redcap_field` f
        JOIN `nodepeel.resus_scratch.dim_redcap_field` df
          ON f.field_name = df.field_name
        WHERE df.is_importable = TRUE
          AND df.is_calc_field = FALSE
          AND df.extraction_difficulty = 'HIGH'
          AND df.expected_utd_floor > 0.0
          AND f.branching_satisfied = TRUE
        GROUP BY df.field_name, df.domain, df.expected_utd_floor
        HAVING actual_utd_rate < df.expected_utd_floor;
    """).result()

    client.query("""
        CREATE OR REPLACE VIEW `nodepeel.resus_scratch.v_exemplar_store` AS
        SELECT
          f.case_id,
          f.run_id,
          f.field_name,
          f.value AS ai_value,
          f.human_value,
          f.event_date
        FROM `nodepeel.resus_scratch.fact_redcap_field` f
        WHERE f.human_verified = TRUE
          AND f.human_value IS NOT NULL
          AND f.human_value != f.value;
    """).result()

    client.query("""
        CREATE OR REPLACE VIEW `nodepeel.resus_scratch.v_audit_domain_coverage` AS
        SELECT
          f.run_id,
          df.domain,
          df.source_class,
          COUNTIF(f.value IS NOT NULL AND f.value != '' AND f.abstained = FALSE) AS populated_count,
          COUNTIF(f.abstained = TRUE) AS abstained_count,
          COUNT(*) AS total_fields,
          ROUND(COUNTIF(f.value IS NOT NULL AND f.value != '' AND f.abstained = FALSE) / NULLIF(COUNT(*), 0), 4) AS populated_pct
        FROM `nodepeel.resus_scratch.fact_redcap_field` f
        JOIN `nodepeel.resus_scratch.dim_redcap_field` df
          ON f.field_name = df.field_name
        WHERE df.is_importable = TRUE
          AND df.is_calc_field = FALSE
          AND f.branching_satisfied = TRUE
        GROUP BY f.run_id, df.domain, df.source_class;
    """).result()

    client.query("""
        CREATE OR REPLACE VIEW `nodepeel.resus_scratch.v_audit_source_class_drift` AS
        SELECT
          f.case_id,
          f.run_id,
          f.field_name,
          f.source_class AS run_value,
          df.source_class AS schema_value
        FROM `nodepeel.resus_scratch.fact_redcap_field` f
        JOIN `nodepeel.resus_scratch.dim_redcap_field` df
          USING (field_name)
        WHERE f.source_class != df.source_class;
    """).result()

    # 6. Verify assertions for each view and print per-view row counts
    # A. v_audit_hallucination
    rows_halluc = list(client.query("SELECT * FROM `nodepeel.resus_scratch.v_audit_hallucination`").result())
    print(f"\n[INTEGRATION] v_audit_hallucination -> {len(rows_halluc)} row(s): {[r['field_name'] for r in rows_halluc]}")
    assert len(rows_halluc) == 1, f"Expected 1 hallucination row, got {len(rows_halluc)}"
    assert rows_halluc[0]["field_name"] == "field_ai_direct_halluc"
    assert all(r["field_name"] != "field_ai_derived_neg" for r in rows_halluc), "AI_DERIVED negative control leaked!"
    print("[INTEGRATION] ✓ Verified AI_DERIVED negative control ('field_ai_derived_neg') is excluded from v_audit_hallucination.")

    # B. v_audit_missing_fields
    rows_missing = list(client.query("SELECT * FROM `nodepeel.resus_scratch.v_audit_missing_fields`").result())
    print(f"[INTEGRATION] v_audit_missing_fields -> {len(rows_missing)} row(s): {[r['field_name'] for r in rows_missing]}")
    assert len(rows_missing) == 1, f"Expected 1 missing field row, got {len(rows_missing)}"
    assert rows_missing[0]["field_name"] == "field_missing"

    # C. v_audit_branching_violation
    rows_branching = list(client.query("SELECT * FROM `nodepeel.resus_scratch.v_audit_branching_violation`").result())
    print(f"[INTEGRATION] v_audit_branching_violation -> {len(rows_branching)} row(s): {[r['field_name'] for r in rows_branching]}")
    assert len(rows_branching) == 1, f"Expected 1 branching violation row, got {len(rows_branching)}"
    assert rows_branching[0]["field_name"] == "field_branching_viol"

    # D. v_audit_low_utd
    rows_utd = list(client.query("SELECT * FROM `nodepeel.resus_scratch.v_audit_low_utd`").result())
    print(f"[INTEGRATION] v_audit_low_utd -> {len(rows_utd)} row(s): {[r['field_name'] for r in rows_utd]} (actual_utd_rate={rows_utd[0]['actual_utd_rate']})")
    assert len(rows_utd) == 1, f"Expected 1 low UTD row, got {len(rows_utd)}"
    assert rows_utd[0]["field_name"] == "field_low_utd"
    assert abs(rows_utd[0]["actual_utd_rate"] - 0.02) < 1e-4, f"Expected 0.02 actual_utd_rate, got {rows_utd[0]['actual_utd_rate']}"
    assert all(r["field_name"] != "field_low_utd_neg" for r in rows_utd), "field_low_utd_neg (rate=0.40 >= 0.30) leaked!"
    print("[INTEGRATION] ✓ Verified v_audit_low_utd negative control ('field_low_utd_neg', rate=0.40) is excluded.")

    # E. v_exemplar_store
    rows_exemplar = list(client.query("SELECT * FROM `nodepeel.resus_scratch.v_exemplar_store`").result())
    print(f"[INTEGRATION] v_exemplar_store -> {len(rows_exemplar)} row(s): {[r['field_name'] for r in rows_exemplar]}")
    assert len(rows_exemplar) == 1, f"Expected 1 exemplar row, got {len(rows_exemplar)}"
    assert rows_exemplar[0]["field_name"] == "field_exemplar"

    # F. v_audit_source_class_drift
    rows_drift = list(client.query("SELECT * FROM `nodepeel.resus_scratch.v_audit_source_class_drift`").result())
    print(f"[INTEGRATION] v_audit_source_class_drift -> {len(rows_drift)} row(s): {[r['field_name'] for r in rows_drift]} (run={rows_drift[0]['run_value']}, schema={rows_drift[0]['schema_value']})")
    assert len(rows_drift) == 1, f"Expected 1 source_class drift row, got {len(rows_drift)}"
    assert rows_drift[0]["field_name"] == "field_drift_test"
    assert rows_drift[0]["run_value"] == "AI_DIRECT"
    assert rows_drift[0]["schema_value"] == "AI_DERIVED"
    print("[INTEGRATION] ✓ Verified v_audit_source_class_drift fires on field_drift_test mismatch and ignores aligned fields.")

    # G. v_audit_domain_coverage
    rows_cov = list(client.query("SELECT * FROM `nodepeel.resus_scratch.v_audit_domain_coverage` ORDER BY domain").result())
    print(f"[INTEGRATION] v_audit_domain_coverage -> {len(rows_cov)} domain group row(s): {[(r['domain'], r['populated_count'], r['abstained_count']) for r in rows_cov]}")
    assert len(rows_cov) >= 5, f"Expected at least 5 domain coverage rows, got {len(rows_cov)}"
    cov_domains = {r["domain"] for r in rows_cov}
    for expected_dom in ("airway", "cci", "ecmo", "mccd", "rosc", "redcap_internal"):
        assert expected_dom in cov_domains, f"Missing domain {expected_dom} in coverage view"
