#!/usr/bin/env python3
"""
demo/generate_synthetic_cohort.py — Synthetic cohort generator for the conversational agent demo in resus_demo.

NOTICE OF SYNTHETIC DATA:
Nothing in this dataset is real. All parameters, patient demographics, clinical events, interval durations, and timing distributions are completely invented and are not literature-derived or reflective of real patient outcomes. The chest compression fraction (CCF) positive trend (drifting from 0.74 to 0.84 over 4 months) and the airway placement no-flow duration skew are deliberately injected so that the run-chart and Pareto SQL queries return legible, recognizable shapes during demonstration presentations.
"""

from datetime import datetime, timedelta
import json
import logging
import random
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.cloud import bigquery
from generated.models import CaseFields, CoverageNote, Event, EventStream, Evidence, Interval
from metrics.compute import compute_case_metrics
from pipeline.bq_writer import assert_gate_clean, write_run
from reducer.engine import reduce_stream

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)


def _make_evidence(ts: float, text: str) -> list[Evidence]:
  return [Evidence(timestamp_s=ts, duration_s=1.0, text=text, attributes={})]


def build_synthetic_case(idx: int) -> tuple[EventStream, str, float]:
  # 40 cases across 4 months (10 per month -> satisfies n >= 10 privacy guard for every month shown)
  month_idx = idx // 10  # 0: Nov 2025, 1: Dec 2025, 2: Jan 2026, 3: Feb 2026
  day = (idx % 10) * 2 + 1
  month_strs = ["2025-11", "2025-12", "2026-01", "2026-02"]
  date_str = f"{month_strs[month_idx]}-{day:02d}"

  # Duration 8 to 45 min (480s to 2700s)
  duration_s = float(random.randint(480, 2700))

  # FIX 3: Realistic CCF trend (0.74 -> 0.71 -> 0.79 -> 0.81), constant variance sigma ~0.07, and outlier cases
  month_bases = [0.74, 0.71, 0.79, 0.81]
  if (idx % 10) in [0, 5]:
    target_ccf = random.uniform(
        0.55, 0.62
    )  # Refractory arrest with long airway pause
  else:
    noise = random.gauss(0.0, 0.07)
    target_ccf = max(0.50, min(0.95, month_bases[month_idx] + noise))

  total_pause_time = duration_s * (1.0 - target_ccf)
  n_ccis = random.randint(6, 22)

  events: list[Event] = []
  intervals: list[Interval] = []

  # Always include arrival events
  events.append(
      Event(
          type="patient_enters_room",
          timestamp_s=0.0,
          attributes={"arrival": True},
          evidence=_make_evidence(0.0, "Patient arrival observed"),
      )
  )
  events.append(
      Event(
          type="first_team_member_enters",
          timestamp_s=6.0,
          attributes={"team_present": True},
      )
  )
  events.append(
      Event(
          type="cpr_initiated_ed",
          timestamp_s=10.0,
          attributes={"in_progress": True},
      )
  )

  # Airway attempts: 0-3 airway attempts, mode 1
  # Out of every 10 cases: 2 get 0, 5 get 1, 2 get 2, 1 gets 3
  att_map = [0, 0, 1, 1, 1, 1, 1, 2, 2, 3]
  n_airway = att_map[idx % 10]

  # Distribute pause time across interruptions
  # To ensure airway placement is the largest no-flow contributor in Pareto query:
  # If case has airway attempt, make 1 pause "airway" (~34s).
  # In 50% of cases, make 1 pause "stretcher_transfer" (~42s).
  # Remaining pauses are typical short checks (~9s).
  pause_allocations: list[tuple[str, float]] = []
  if n_airway > 0:
    for _ in range(min(3, n_ccis - 1)):
      pause_allocations.append(
          ("airway_placement", random.uniform(32.0, 36.0))
      )
  if idx % 5 < 3 and len(pause_allocations) < n_ccis:
    pause_allocations.append(("stretcher_transfer", random.uniform(38.0, 44.0)))

  remaining_ccis = max(1, n_ccis - len(pause_allocations))
  for _ in range(remaining_ccis):
    r_type = random.choice(
        ["rhythm_determination", "pulse_check", "defibrillation"]
    )
    pause_allocations.append((r_type, random.uniform(4.0, 6.0)))

  # Scale durations to exactly match our desired target CCF pause time
  actual_sum = sum(x[1] for x in pause_allocations)
  scale = total_pause_time / actual_sum if actual_sum > 0 else 1.0

  curr_t = 20.0
  step = (duration_s - 40.0) / len(pause_allocations)
  for i_cci, (p_reason, p_raw_dur) in enumerate(pause_allocations):
    p_dur = p_raw_dur * scale
    mod_20 = (idx + i_cci) % 20
    reasons = [p_reason]
    if mod_20 == 0:
      reasons.extend(["chest_us", "us_pulse"])
      p_dur = max(p_dur, random.uniform(12.0, 16.0))
    elif mod_20 in [1, 2, 3, 4]:
      reasons.append("chest_us")
      p_dur = max(p_dur, random.uniform(12.0, 16.0))
    elif mod_20 in [5, 6]:
      reasons.append("us_pulse")
      p_dur = max(p_dur, random.uniform(7.0, 9.0))

    if p_dur < 3.0:
      p_dur = 3.0
    t0 = curr_t
    t1 = min(duration_s - 5.0, t0 + p_dur)
    attrs = {
        "pulse_check": p_reason == "pulse_check",
        "rhythm_check": p_reason in ["rhythm_determination", "defibrillation"],
        "rhythm_code": "vf",
        "aline_present": True,
    }
    if "chest_us" in reasons:
      attrs.update({"echo_success": True, "sono_window": "subxiphoid"})
    if "us_pulse" in reasons:
      attrs.update({"us_pulse_present": True, "us_pulse_site": "femoral"})
    if (idx + i_cci) % 3 != 0:
      attrs.update({"aline_sbp": 120.0, "aline_dbp": 80.0})
    else:
      attrs.update({"aline_sbp": None, "aline_dbp": None})
    attrs["reasons"] = reasons
    intervals.append(
        Interval(
            type="compression_interruption",
            t_start_s=t0,
            t_end_s=t1,
            attributes=attrs,
        )
    )
    curr_t += step

  # Add airway attempt events
  for k in range(n_airway):
    ts = min(duration_s - 10.0, 50.0 + k * 120.0)
    attrs = {"successful": (k == n_airway - 1)}
    if not (idx in [0, 20] and k == 0):
      attrs["device"] = "ett"
    events.append(
        Event(
            type="airway_attempt",
            timestamp_s=ts,
            attributes=attrs,
            evidence=_make_evidence(ts, f"Airway attempt #{k+1}"),
        )
    )

  # Shocks: 0 shocks in 65% of cases (26 cases), else 1-7 shocks
  if idx >= 26:
    n_shocks = random.randint(1, 7)
    for k in range(n_shocks):
      ts = min(duration_s - 15.0, 40.0 + k * 90.0)
      events.append(
          Event(
              type="defibrillation_shock",
              timestamp_s=ts,
              attributes={"shock_delivered": True, "energy_j": 200},
              evidence=_make_evidence(ts, f"Shock #{k+1}"),
          )
      )

  # ROSC: 33% of cases (13 out of 40 cases)
  if idx % 3 == 0:
    ts_r = duration_s * 0.7
    events.append(
        Event(
            type="rosc_detected",
            timestamp_s=ts_r,
            attributes={"pulse_palpable": True},
            evidence=_make_evidence(ts_r, "ROSC detected"),
        )
    )
    intervals.append(
        Interval(
            type="rosc",
            t_start_s=ts_r,
            t_end_s=min(duration_s, ts_r + 180.0),
            attributes={"rosc_duration_s": 180.0},
        )
    )

  # Add a rhythm check event so rhythm fields evaluate cleanly without bare empties
  rhythm_attrs = {"rhythm_shockable": True, "t_start_s": 30.0}
  if idx % 10 != 0:
    rhythm_attrs["rhythm"] = "VF"
  events.append(
      Event(
          type="rhythm_check",
          timestamp_s=30.0,
          attributes=rhythm_attrs,
      )
  )
  events.append(
      Event(
          type="ems_handoff_end",
          timestamp_s=duration_s,
      )
  )

  coverage = []
  if idx % 10 == 0:
    coverage.append(
        CoverageNote(
            type="provider_crowding",
            text="Provider crowding blocking visual field",
        )
    )
  if idx % 3 == 0:
    coverage.append(
        CoverageNote(
            type="monitor_not_visible",
            text="Monitor screen occluded by equipment or personnel",
        )
    )

  case_id = f"syn_case_{idx+1:03d}"
  stream = EventStream(
      case_id=case_id,
      events=events,
      intervals=intervals,
      coverage=coverage,
      fields=CaseFields(recording_started_late=False, arrest_location="ohca"),
  )
  return stream, date_str, duration_s


def main():
  print("=== GENERATING 40 SYNTHETIC CASES FOR RESUS_DEMO COHORT ===")
  random.seed(2026)

  client = bigquery.Client(project="nodepeel")

  for i in range(40):
    stream, dt_str, dur = build_synthetic_case(i)
    fvs, _, _ = reduce_stream(stream, duration_s=dur)
    assert len(fvs) == 1879, (
        f"Case {stream.case_id} failed contract: {len(fvs)} fields emitted"
    )

    metrics = compute_case_metrics(stream)
    write_run(
        case_id=stream.case_id,
        run_id="demo_run_01",
        stream=stream,
        field_values=fvs,
        metrics=metrics,
        raw_dataset="resus_demo",
        project="nodepeel",
        is_synthetic=True,
        event_date_str=dt_str,
        site="Demo Medical Center",
    )
    if (i + 1) % 10 == 0 or i == 39:
      print(
          f"  Processed & loaded {i+1}/40 synthetic cases into"
          " nodepeel.resus_demo..."
      )

  print("\n=== VERIFYING ISOLATION & COHORT METRICS IN BIGQUERY ===")
  q_iso = "SELECT COUNT(*) FROM nodepeel.resus_raw.dim_case WHERE is_synthetic = TRUE"
  raw_syn_count = list(client.query(q_iso).result())[0][0]
  print(
      f"  Isolation check on nodepeel.resus_raw.dim_case (is_synthetic=True):"
      f" {raw_syn_count} rows (MUST be 0)"
  )
  assert raw_syn_count == 0, (
      "SAFETY FAILURE: Synthetic rows detected in physical clinical dataset!"
  )

  print("\n=== VERIFYING REASON VOCABULARY IN BIGQUERY ===")
  valid_reasons = {
      "airway_placement",
      "arterial_line",
      "central_line",
      "chest_us",
      "defibrillation",
      "dual_sequential_defib",
      "ecmo",
      "log_roll",
      "mccd_adjusted",
      "mccd_placement",
      "mccd_removed",
      "ng_og",
      "other",
      "pad_placement",
      "pulse_check",
      "rhythm_determination",
      "rosc",
      "stretcher_transfer",
      "tee",
      "unknown",
      "us_pulse",
  }
  q_reasons = "SELECT DISTINCT reason FROM nodepeel.resus_demo.v_cci_reasons"
  found_reasons = {
      r.reason for r in client.query(q_reasons).result() if r.reason
  }
  invalid = found_reasons - valid_reasons
  assert not invalid, (
      f"SAFETY FAILURE: Found invalid CCI reason codes in BigQuery: {invalid}"
  )
  print(
      f"  ✓ All {len(found_reasons)} distinct reasons in"
      f" nodepeel.resus_demo.v_cci_reasons are valid cci_reason members!"
  )

  q_coh = "SELECT COUNT(DISTINCT case_id) n, MIN(CAST(enrollment_date AS STRING)) min_d, MAX(CAST(enrollment_date AS STRING)) max_d FROM nodepeel.resus_demo.dim_case"
  coh_row = list(client.query(q_coh).result())[0]
  print(
      f"  Cohort summary in nodepeel.resus_demo.dim_case: n={coh_row.n} cases"
      f" spanning from {coh_row.min_d} to {coh_row.max_d}"
  )
  assert coh_row.n == 40, f"Expected 40 cases in resus_demo, found {coh_row.n}"

  print("\n=== RUNNING STRICT HARD GATES AGAINST RESUS_DEMO ===")
  views_to_check = [
      "v_audit_hallucination",
      "v_audit_missing_fields",
      "v_audit_branching_violation",
      "v_audit_source_class_drift",
  ]
  all_clean = True
  for v in views_to_check:
    try:
      assert_gate_clean(
          view=v,
          case_id="ALL",
          project="nodepeel",
          raw="resus_demo",
          curated="resus_demo",
      )
    except Exception as e:
      print(f"❌ AUDIT VIOLATION on {v}: {e}")
      all_clean = False
      offenders = list(
          client.query(
              f"SELECT * FROM nodepeel.resus_demo.{v} LIMIT 5"
          ).result()
      )
      print(f"   Sample offending rows ({len(offenders)} shown):")
      for off in offenders:
        print(f"     {dict(off)}")

  if not all_clean:
    print(
        "\nWARNING: Synthetic cohort generated violations! Must fix before"
        " demoing."
    )
    sys.exit(1)
  else:
    print(
        "\n✓ All four strict audit hard gates confirmed 100% CLEAN against the"
        " 40-case synthetic cohort!"
    )

  print("\n=== [INSIGHT CHECK: v_audit_low_utd (HIGH-difficulty fields below expected UTD floor)] ===")
  low_utd_rows = list(
      client.query("SELECT * FROM nodepeel.resus_demo.v_audit_low_utd").result()
  )
  print(
      f"  v_audit_low_utd flagged {len(low_utd_rows)} HIGH-difficulty fields"
      " below their expected UTD floor (demonstrating audit view sensitivity):"
  )
  for row in low_utd_rows:
    print(f"   -> {dict(row)}")

  print("\n=== RUNNING THE THREE DEMO QUERIES FOR CONVERSATIONAL AGENT ===")

  print("\n[Query 1: CCF Run-Chart by Month]")
  q1 = """
    SELECT
      SUBSTR(CAST(event_date AS STRING), 1, 7) AS month,
      COUNT(DISTINCT case_id) AS total_cases,
      ROUND(AVG(value), 3) AS avg_ccf,
      ROUND(STDDEV(value), 3) AS stddev_ccf
    FROM nodepeel.resus_demo.v_case_metrics
    WHERE metric_name = 'chest_compression_fraction'
    GROUP BY month
    ORDER BY month;
    """
  for r in client.query(q1).result():
    print(
        f"  Month: {r.month} | Cases: {r.total_cases:2d} | Avg CCF: {r.avg_ccf:.3f}"
        f" | StdDev: {r.stddev_ccf:.3f}"
    )
  print(
      '  "Forty invented cases. I built in a mild upward trend so the run'
      " chart shows something. That trend is not a finding — it's a fixture."
      " What I'm showing you is the shape of the question, not an answer about"
      ' your department."'
  )

  print("\n[Query 2: Pareto of No-Flow Duration by Reason]")
  q2 = """
    SELECT
      reason,
      COUNT(*) AS pause_count,
      ROUND(SUM(duration_s), 1) AS total_no_flow_seconds,
      ROUND(SUM(duration_s) / (SELECT SUM(duration_s) FROM nodepeel.resus_demo.v_cci_reasons) * 100, 1) AS pct_of_total_no_flow
    FROM nodepeel.resus_demo.v_cci_reasons
    GROUP BY reason
    ORDER BY total_no_flow_seconds DESC;
    """
  for r in client.query(q2).result():
    print(
        f"  Reason: {r.reason:<20} | Pauses: {r.pause_count:3d} | Total"
        f" No-Flow: {r.total_no_flow_seconds:7.1f}s"
        f" ({r.pct_of_total_no_flow:5.1f}%)"
    )

  print(
      "\n[Query 3: Provider-Level Evaluation Query (MUST REFUSE / FAIL BY"
      " ARCHITECTURE)]"
  )
  q3 = """
    SELECT
      provider_id,
      COUNT(DISTINCT case_id) AS cases_assisted,
      ROUND(AVG(value), 3) AS provider_avg_ccf
    FROM nodepeel.resus_demo.v_case_metrics
    WHERE metric_name = 'chest_compression_fraction'
    GROUP BY provider_id
    ORDER BY provider_avg_ccf DESC;
    """
  try:
    client.query(q3).result()
    print("❌ ERROR: Provider query unexpectedly succeeded!")
    sys.exit(1)
  except Exception as e:
    print(
        f"✓ Query correctly REFUSED by schema architecture (Zero Provider"
        f" Identity Expiration):\n   -> {e}"
    )


if __name__ == "__main__":
  main()
