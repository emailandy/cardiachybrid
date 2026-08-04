#!/usr/bin/env python3
"""
demo/query_agent.py — Conversational agent execution wrapper with architectural and privacy guardrails.

Implements two pre-query and post-query safety guardrails:
1. Provider-scope refusal (`check_provider_scope`): Refuses queries attempting to group, order, or partition by provider identity or role columns (`role`, `operator_position`, `provider`, etc.) before any SQL reaches BigQuery.
2. Minimum cell-size guardrail (`check_privacy_cell_size`): Refuses/suppresses aggregated results where any group cell size is n < 10 cases to prevent re-identification.
"""

import re
import sys
from typing import Any
from google.cloud import bigquery

PROVIDER_IDENTIFIABLE = {
    'speaker_id',
    'role',
    'operator_position',
    'operator_ed',
    'reviewer_id',
    'human_verified_by',
    'attending',
    'provider',
}


class Refused(Exception):
  """Raised when a conversational agent query violates architectural or privacy guardrails."""

  pass


def check_provider_scope(sql: str) -> None:
  """Inspects SQL before execution; raises Refused if query groups or ranks by provider/role identity."""
  low = sql.lower()
  for col in PROVIDER_IDENTIFIABLE:
    if re.search(rf'\b{col}\b', low) and re.search(
        r'\b(group\s+by|order\s+by|partition\s+by)\b', low
    ):
      raise Refused(
          "This system is scoped to department-level quality improvement."
          " Grouping or ranking by an individual or role requires separate"
          " institutional approval and is not available here."
      )


def check_privacy_cell_size(
    rows: list[dict[str, Any]], min_cell: int = 10
) -> None:
  """Inspects query result rows; raises Refused if any group cell size is 0 < n < min_cell."""
  count_keys = {
      'total_cases',
      'n',
      'case_count',
      'cases',
      'cases_assisted',
      'n_cases',
  }
  for row in rows:
    for k, val in row.items():
      if k.lower() in count_keys and val is not None:
        try:
          n_val = int(val)
          if 0 < n_val < min_cell:
            raise Refused(
                f"Privacy aggregation guardrail triggered: group cell size"
                f" n={n_val} (< {min_cell} cases required). Small-cell outputs"
                f" are suppressed to protect patient and clinical team"
                f" confidentiality."
            )
        except (ValueError, TypeError):
          continue


def run_agent_query(
    sql: str, project: str = "nodepeel"
) -> list[dict[str, Any]]:
  """Executes SQL query against BigQuery after checking provider scope and verifying cell sizes."""
  check_provider_scope(sql)
  client = bigquery.Client(project=project)
  query_job = client.query(sql)
  rows = [dict(r) for r in query_job.result()]
  check_privacy_cell_size(rows)
  return rows


def demonstrate_guardrails():
  print("=== CONVERSATIONAL AGENT GUARDRAILS DEMONSTRATION ===")

  print("\n[Demonstration 1a: Provider Scope Refusal (Team Leader CCF)]")
  prompt_1a = "Which team leader has the lowest compression fraction?"
  sql_1a = """
    SELECT role, AVG(value) AS ccf
    FROM nodepeel.resus_demo.v_case_metrics
    WHERE metric_name = 'chest_compression_fraction'
    GROUP BY role
    ORDER BY ccf ASC;
    """
  print(f'  User Request: "{prompt_1a}"')
  print(f"  Proposed SQL:\n{sql_1a.strip()}")
  try:
    run_agent_query(sql_1a)
    print("❌ ERROR: Query 1a unexpectedly succeeded without refusal!")
    sys.exit(1)
  except Refused as e:
    print(f"  ✓ AGENT REFUSAL:\n    -> {e}")

  print(
      "\n[Demonstration 1b: Provider Scope Refusal (Intubation Success by"
      " Operator Position)]"
  )
  prompt_1b = "Compare first-pass intubation success by operator position."
  sql_1b = """
    SELECT operator_position, COUNT(*) AS n, AVG(value) AS first_pass_success
    FROM nodepeel.resus_demo.v_case_metrics
    WHERE metric_name = 'first_pass_success'
    GROUP BY operator_position
    ORDER BY first_pass_success DESC;
    """
  print(f'  User Request: "{prompt_1b}"')
  print(f"  Proposed SQL:\n{sql_1b.strip()}")
  try:
    run_agent_query(sql_1b)
    print("❌ ERROR: Query 1b unexpectedly succeeded without refusal!")
    sys.exit(1)
  except Refused as e:
    print(f"  ✓ AGENT REFUSAL:\n    -> {e}")

  print("\n[Demonstration 2: Minimum Cell-Size Privacy Guardrail (n < 10)]")
  prompt_2 = (
      "Show me CCF for cases where ROSC was achieved, broken down by month"
  )
  sql_2 = """
    SELECT
      SUBSTR(CAST(m.event_date AS STRING), 1, 7) AS month,
      COUNT(DISTINCT m.case_id) AS total_cases,
      ROUND(AVG(m.value), 3) AS avg_ccf
    FROM nodepeel.resus_demo.v_case_metrics m
    JOIN nodepeel.resus_demo.fact_event e
      ON m.case_id = e.case_id
    WHERE m.metric_name = 'chest_compression_fraction'
      AND e.event_type = 'rosc_detected'
    GROUP BY month
    ORDER BY month;
    """
  print(f'  User Request: "{prompt_2}"')
  print(f"  Executed SQL:\n{sql_2.strip()}")
  try:
    run_agent_query(sql_2)
    print("❌ ERROR: Query 2 unexpectedly succeeded without refusal!")
    sys.exit(1)
  except Refused as e:
    print(f"  ✓ AGENT REFUSAL:\n    -> {e}")

  print(
      "\n✓ All three guardrail demonstrations executed and verified"
      " successfully!"
  )


if __name__ == "__main__":
  demonstrate_guardrails()
