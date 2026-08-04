#!/usr/bin/env python3
"""
scripts/load_demo_bq.py — Load run_02 and run_03 from cached event streams into BigQuery nodepeel.resus_raw,
verify 1,879 rows per run, and run assert_gate_clean across all audit views.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest.ensemble import deduplicate_window_streams, pair_boundary_events
from generated.models import EventStream
from metrics.compute import compute_case_metrics
from pipeline.bq_writer import assert_gate_clean, write_run
from reducer.engine import reduce_stream

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')


def load_from_cache(cache_dir_name: str, case_id: str = 'DEMO-1') -> EventStream:
  w_streams = []
  for idx in range(4):
    p = Path(f'{cache_dir_name}/p1_win_{idx}.txt')
    if not p.exists():
      raise FileNotFoundError(f'Missing cached stream file: {p}')
    s = EventStream.model_validate_json(p.read_text(encoding='utf-8'))
    w_streams.append((s, 0.0 if idx == 0 else 420.0, 1363.78))
  merged = pair_boundary_events(deduplicate_window_streams(w_streams))
  merged.case_id = case_id
  return merged


def main():
  case_id = 'DEMO-1'
  runs = [
      ('run_02', 'generated/cache_run02'),
      ('run_03', 'generated/cache_run_03'),
  ]

  for run_id, cache_dir in runs:
    print(f'\nLoading {run_id} from {cache_dir}...')
    stream = load_from_cache(cache_dir, case_id=case_id)
    fvs, _, _ = reduce_stream(stream)
    assert len(fvs) == 1879, f'Expected 1879 fields for {run_id}, got {len(fvs)}'

    metrics = compute_case_metrics(stream)
    write_run(
        case_id=case_id,
        run_id=run_id,
        stream=stream,
        field_values=fvs,
        metrics=metrics,
        raw_dataset='resus_raw',
        project='nodepeel',
        is_synthetic=False,
    )

  print('\n=== Verifying Row Counts in BigQuery ===')
  from google.cloud import bigquery
  client = bigquery.Client(project='nodepeel')
  query = "SELECT run_id, COUNT(*) as cnt FROM nodepeel.resus_raw.fact_redcap_field WHERE case_id = 'DEMO-1' GROUP BY run_id ORDER BY run_id"
  results = list(client.query(query).result())
  for row in results:
    print(f'  {row.run_id}: {row.cnt:,d} rows in fact_redcap_field')
    assert row.cnt == 1879, (
        f'Run {row.run_id} row count mismatch: expected 1879, got {row.cnt}'
    )

  print(
      '\n=== Structural Audit Gate Verification (assert_gate_clean) across Audit'
      ' Views ==='
  )
  views_to_check = [
      'v_audit_hallucination',
      'v_audit_missing_fields',
      'v_audit_branching_violation',
      'v_audit_source_class_drift',
      'v_audit_low_utd',
  ]

  all_clean = True
  for v in views_to_check:
    try:
      assert_gate_clean(
          view=v,
          case_id=case_id,
          project='nodepeel',
          raw='resus_raw',
          curated='resus_curated',
      )
    except Exception as e:
      print(f'❌ GATE FAILURE / VIOLATION on {v}: {e}')
      all_clean = False
      view_where = "" if v == "v_audit_low_utd" else f"WHERE case_id = '{case_id}'"
      offenders = list(
          client.query(
              f"SELECT * FROM nodepeel.resus_curated.{v} {view_where} LIMIT 5"
          ).result()
      )
      print(f'   Sample offending rows ({len(offenders)} shown):')
      for off in offenders:
        print(f'     {dict(off)}')

  if not all_clean:
    print('\nWARNING: One or more audit gates reported violations!')
    sys.exit(1)
  else:
    print(
        '\n✓ All five audit views confirmed CLEAN against verified non-empty'
        ' physical tables!'
    )


if __name__ == '__main__':
  main()
