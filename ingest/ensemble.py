"""
ingest/ensemble.py — Multi-run ensemble merger and vote threshold adjudicator.

Enforces:
  1. Global nearest-neighbour matching across runs sorted by |Δt| ascending.
  2. Vote thresholds:
     - 3/3 accept (high confidence)
     - 2/3 accept and flag (ensemble_flag="2/3_majority")
     - 1/3 drop to fact_near_miss in resus_raw with full PHI evidence[]
  3. Median timestamps; ensemble_spread_s = max - min; spread > 3.0s routes to human.
  4. Categoricals take majority vote; 1/1/1 three-way tie abstains and routes to human.
"""

from __future__ import annotations

import json
import statistics
from typing import Any
from fixtures.synthetic_streams import get_maximal_stream


def get_ts(item: dict[str, Any]) -> float:
    return float(item.get("t_start_s", item.get("timestamp_s", 0.0)))


def can_merge_monotonically(
    c1: list[tuple[int, int]],
    c2: list[tuple[int, int]],
    clusters: list[list[tuple[int, int]]],
) -> bool:
    """Ensure merging c1 and c2 does not cross any existing matched pair across runs."""
    for r1, idx1 in c1:
        for r2, idx2 in c2:
            for c_exist in clusters:
                if len(c_exist) < 2 or c_exist is c1 or c_exist is c2:
                    continue
                x1 = None
                x2 = None
                for r, idx in c_exist:
                    if r == r1:
                        x1 = idx
                    elif r == r2:
                        x2 = idx
                if x1 is not None and x2 is not None:
                    if (idx1 < x1 and idx2 > x2) or (idx1 > x1 and idx2 < x2):
                        return False
    return True


def match_item_clusters(
    items_by_run: list[list[dict[str, Any]]], k: int, is_interval: bool = False
) -> list[list[dict[str, Any]]]:
    """
    Global nearest-neighbour matching across member runs.
    Sorts candidate pairs (run_i != run_j) by |Δt| ascending where |Δt| <= tol.
    Enforces monotonic matching (no crossing edges) to prevent matching cascade.
    For intervals, checks both start and end boundary tolerances.
    Returns a list of clusters (each cluster is a list of matched items across runs).
    """
    all_items: list[tuple[int, int, dict[str, Any]]] = []
    for r_idx, run_items in enumerate(items_by_run):
        for i_idx, item in enumerate(run_items):
            all_items.append((r_idx, i_idx, item))

    # Candidate pairs within tolerance
    candidate_pairs: list[tuple[float, tuple[int, int], tuple[int, int]]] = []
    n = len(all_items)
    for i in range(n):
        r1, i1, item1 = all_items[i]
        t1 = get_ts(item1)
        end1 = float(item1.get("t_end_s") if item1.get("t_end_s") is not None else t1)
        p1 = float(item1.get("t_precision_s") if item1.get("t_precision_s") is not None else 1.0)
        for j in range(i + 1, n):
            r2, i2, item2 = all_items[j]
            if r1 == r2:
                continue
            t2 = get_ts(item2)
            end2 = float(item2.get("t_end_s") if item2.get("t_end_s") is not None else t2)
            p2 = float(item2.get("t_precision_s") if item2.get("t_precision_s") is not None else 1.0)
            dt = abs(t1 - t2)
            if is_interval:
                dt_end = abs(end1 - end2)
                if dt <= (p1 + p2) and dt_end <= (p1 + p2):
                    candidate_pairs.append((dt + dt_end, (r1, i1), (r2, i2)))
            else:
                if dt <= (p1 + p2):
                    candidate_pairs.append((dt, (r1, i1), (r2, i2)))

    # Sort ascending by time difference
    candidate_pairs.sort(key=lambda x: x[0])

    event_to_cluster: dict[tuple[int, int], int] = {}
    clusters: list[list[tuple[int, int]]] = []
    for r_idx, i_idx, _ in all_items:
        c = [(r_idx, i_idx)]
        clusters.append(c)
        event_to_cluster[(r_idx, i_idx)] = len(clusters) - 1

    for _, k1, k2 in candidate_pairs:
        c1_idx = event_to_cluster[k1]
        c2_idx = event_to_cluster[k2]
        if c1_idx == c2_idx:
            continue
        c1 = clusters[c1_idx]
        c2 = clusters[c2_idx]
        runs_in_c1 = {r for r, _ in c1}
        runs_in_c2 = {r for r, _ in c2}
        if runs_in_c1.isdisjoint(runs_in_c2) and can_merge_monotonically(
            c1, c2, clusters
        ):
            c1.extend(c2)
            for item_key in c2:
                event_to_cluster[item_key] = c1_idx
            c2.clear()

    # Convert back to list of dicts and log unmatched nearest candidates
    result_clusters: list[list[dict[str, Any]]] = []
    for c in clusters:
        if not c:
            continue
        cluster_items = []
        for r_idx, i_idx in c:
            item = items_by_run[r_idx][i_idx]
            if len(c) == 1 and len(items_by_run) > 1:
                t1 = get_ts(item)
                best_dt = float("inf")
                best_r = -1
                best_t = 0.0
                for r2_idx, run_items2 in enumerate(items_by_run):
                    if r2_idx == r_idx:
                        continue
                    for item2 in run_items2:
                        t2 = get_ts(item2)
                        dt = abs(t1 - t2)
                        if dt < best_dt:
                            best_dt = dt
                            best_r = r2_idx
                            best_t = t2
                if best_r != -1:
                    attrs = dict(item.get("attributes", {}))
                    attrs["unmatched_log"] = (
                        f"Unmatched event at t={t1} (run {r_idx}): "
                        f"nearest candidate in run {best_r} at t={best_t} (Δt={round(best_dt, 2)}s)"
                    )
                    item = dict(item, attributes=attrs)
            cluster_items.append(item)
        result_clusters.append(cluster_items)

    # Sort clusters by median t_start_s
    result_clusters.sort(
        key=lambda cl: statistics.median([get_ts(x) for x in cl])
    )
    return result_clusters


def merge_cluster(
    cluster: list[dict[str, Any]], k: int, spread_threshold_s: float = 3.0
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any]]:
    """
    Evaluates an item cluster against vote thresholds.
    Returns (accepted_item, near_miss_item, stats_dict).
    """
    votes_accept = len(cluster)
    votes_reject = max(0, k - votes_accept)

    t_starts = [get_ts(x) for x in cluster]
    med_start = round(statistics.median(t_starts), 2)
    spread = round(max(t_starts) - min(t_starts), 3)

    # Combine evidence[]
    merged_evidence: list[Any] = []
    seen_ev: set[str] = set()
    for item in cluster:
        for ev in item.get("evidence", []):
            ev_str = json.dumps(ev, sort_keys=True)
            if ev_str not in seen_ev:
                seen_ev.add(ev_str)
                merged_evidence.append(ev)

    # Majority vote for categorical attributes
    all_attr_keys: set[str] = set()
    for item in cluster:
        attrs = item.get("attributes", {})
        if isinstance(attrs, dict):
            all_attr_keys.update(attrs.keys())

    merged_attrs: dict[str, Any] = {}
    tie_1_1_1 = False
    for a_key in sorted(all_attr_keys):
        vals = []
        for item in cluster:
            attrs = item.get("attributes", {})
            if isinstance(attrs, dict) and a_key in attrs:
                vals.append(attrs[a_key])
        if not vals:
            continue
        # Count frequencies
        freq: dict[Any, int] = {}
        for v in vals:
            v_key = json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else v
            freq[v_key] = freq.get(v_key, 0) + 1

        # Check for 1/1/1 three-way tie
        if len(vals) == 3 and len(freq) == 3:
            merged_attrs[a_key] = "abstained_1_1_1_tie"
            tie_1_1_1 = True
        else:
            # Majority value
            best_val_key = max(freq.keys(), key=lambda x: freq[x])
            merged_attrs[a_key] = best_val_key

    merged_attrs["ensemble_votes"] = votes_accept
    merged_attrs["ensemble_k"] = k
    merged_attrs["ensemble_spread_s"] = spread

    routed = False
    if spread > spread_threshold_s or tie_1_1_1:
        routed = True

    stats = {
        "votes_accept": votes_accept,
        "spread_gt_threshold": spread > spread_threshold_s,
        "tie_1_1_1": tie_1_1_1,
    }

    # Vote thresholds: accepted if votes_accept * 2 > k
    if votes_accept * 2 > k:
        if votes_accept < k:
            merged_attrs["ensemble_flag"] = "2/3_majority"

        conf_vals = [float(x.get("confidence") if x.get("confidence") is not None else 1.0) for x in cluster]
        med_conf = round(statistics.median(conf_vals), 4)

        base_item = cluster[0].copy()
        base_item["t_start_s"] = med_start
        if "timestamp_s" in base_item:
            base_item["timestamp_s"] = med_start
        base_item["confidence"] = med_conf
        base_item["routed_to_human"] = (
            base_item.get("routed_to_human", False) or routed
        )
        base_item["attributes"] = merged_attrs
        base_item["evidence"] = merged_evidence
        return base_item, None, stats
    else:
        # Near-miss (1/3 minority vote)
        nm_item = cluster[0].copy()
        nm_item["t_start_s"] = med_start
        if "timestamp_s" in nm_item:
            nm_item["timestamp_s"] = med_start
        nm_item["votes_accept"] = votes_accept
        nm_item["votes_reject"] = votes_reject
        nm_item["attributes"] = merged_attrs
        nm_item["evidence"] = merged_evidence
        return None, nm_item, stats


def ensemble_streams(
    runs: list[Any], k: int = 3, spread_threshold_s: float = 3.0
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Ensemble k member runs into a merged stream and a near-miss list.
    """
    norm_runs: list[dict[str, Any]] = []
    for r in runs:
        if hasattr(r, "model_dump"):
            norm_runs.append(r.model_dump())
        elif hasattr(r, "dict"):
            norm_runs.append(r.dict())
        else:
            norm_runs.append(r)
    runs = norm_runs

    merged_stream: dict[str, Any] = {
        "events": [],
        "intervals": [],
        "utterances": [],
        "sensors": [],
    }
    near_miss_list: list[dict[str, Any]] = []

    # 1. Events
    ev_by_type: dict[str, list[list[dict[str, Any]]]] = {}
    for r_idx, run in enumerate(runs):
        for ev in run.get("events", []):
            etype = ev.get("type", "")
            if etype not in ev_by_type:
                ev_by_type[etype] = [[] for _ in range(k)]
            if r_idx < k:
                ev_by_type[etype][r_idx].append(ev)

    for etype, runs_evs in ev_by_type.items():
        clusters = match_item_clusters(runs_evs, k)
        for cl in clusters:
            acc, nm, _ = merge_cluster(cl, k, spread_threshold_s)
            if acc:
                merged_stream["events"].append(acc)
            if nm:
                near_miss_list.append(nm)

    merged_stream["events"].sort(key=lambda x: float(x.get("t_start_s", 0.0)))
    near_miss_list.sort(key=lambda x: float(x.get("t_start_s", 0.0)))

    # 2. Intervals
    iv_by_type: dict[str, list[list[dict[str, Any]]]] = {}
    for r_idx, run in enumerate(runs):
        for iv in run.get("intervals", []):
            itype = iv.get("type", "")
            if itype not in iv_by_type:
                iv_by_type[itype] = [[] for _ in range(k)]
            if r_idx < k:
                iv_by_type[itype][r_idx].append(iv)

    for itype, runs_ivs in iv_by_type.items():
        clusters = match_item_clusters(runs_ivs, k, is_interval=True)
        for cl in clusters:
            acc, nm, _ = merge_cluster(cl, k, spread_threshold_s)
            if acc:
                merged_stream["intervals"].append(acc)
            if nm:
                near_miss_list.append(nm)

    merged_stream["intervals"].sort(key=lambda x: float(x.get("t_start_s", 0.0)))

    # 3. Utterances (pass through from first run or merge by timestamp)
    if runs:
        merged_stream["utterances"] = list(runs[0].get("utterances", []))
        merged_stream["sensors"] = list(runs[0].get("sensors", []))

    return merged_stream, near_miss_list


def build_path_coverage_triple() -> list[dict[str, Any]]:
    """
    Deterministic path-coverage run-triple where each ensemble branch fires exactly once.
    Purpose: every branch executes. Not a baseline distribution.
    """
    base_obj = get_maximal_stream()
    base_dict = base_obj.model_dump() if hasattr(base_obj, "model_dump") else base_obj.dict()
    run0 = json.loads(json.dumps(base_dict))
    run1 = json.loads(json.dumps(base_dict))
    run2 = json.loads(json.dumps(base_dict))

    # Run 1 perturbations: shift timestamps by +0.2s, change one categorical
    changed_rhythm_1 = False
    for ev in run1.get("events", []):
        ts = ev.get("t_start_s", ev.get("timestamp_s", 0.0))
        ev["t_start_s"] = ts + 0.2
        ev["timestamp_s"] = ts + 0.2
        if not changed_rhythm_1 and ev.get("type") == "rhythm_check" and "rhythm" in ev.get("attributes", {}):
            ev["attributes"]["rhythm"] = "vtach"
            changed_rhythm_1 = True

    # Run 2 perturbations: shift timestamps by -0.1s, trigger exactly one 1/1/1 tie, drop exactly one shock
    changed_rhythm_2 = False
    dropped_first = False
    for ev in list(run2.get("events", [])):
        ts = ev.get("t_start_s", ev.get("timestamp_s", 0.0))
        ev["t_start_s"] = ts - 0.1
        ev["timestamp_s"] = ts - 0.1
        if not changed_rhythm_2 and ev.get("type") == "rhythm_check" and "rhythm" in ev.get("attributes", {}):
            ev["attributes"]["rhythm"] = "asystole"
            changed_rhythm_2 = True
        if ev.get("type") == "defibrillation_shock" and not dropped_first:
            run2["events"].remove(ev)
            dropped_first = True

    spread_ev_0 = {
        "type": "compression_mode_change",
        "t_start_s": 50.0,
        "timestamp_s": 50.0,
        "t_precision_s": 2.0,
        "confidence": 0.95,
        "evidence": [{"text": "mode change 0"}],
        "attributes": {},
    }
    spread_ev_1 = dict(spread_ev_0, t_start_s=50.5, timestamp_s=50.5, evidence=[{"text": "mode change 1"}])
    spread_ev_2 = dict(spread_ev_0, t_start_s=53.2, timestamp_s=53.2, evidence=[{"text": "mode change 2"}])
    run0.setdefault("events", []).append(spread_ev_0)
    run1.setdefault("events", []).append(spread_ev_1)
    run2.setdefault("events", []).append(spread_ev_2)

    nm_ev_1 = {
        "type": "pocus_cardiac",
        "t_start_s": 88.0,
        "timestamp_s": 88.0,
        "t_precision_s": 1.0,
        "confidence": 0.6,
        "evidence": [{"text": "possible pocus"}],
        "attributes": {},
    }
    run1.setdefault("events", []).append(nm_ev_1)

    return [run0, run1, run2]


def run_path_coverage_experiment() -> dict[str, Any]:
    """
    Executes the deterministic path coverage triple and returns branch counts.
    Not a baseline distribution.
    """
    runs = build_path_coverage_triple()
    merged, near_misses = ensemble_streams(runs, k=3)

    count_3_3 = 0
    count_2_3 = 0
    count_spread_gt_3 = 0
    count_1_1_1_ties = 0

    for ev in merged.get("events", []):
        attrs = ev.get("attributes", {})
        votes = attrs.get("ensemble_votes", 0)
        if votes == 3:
            count_3_3 += 1
        elif votes == 2:
            count_2_3 += 1
        if attrs.get("ensemble_spread_s", 0.0) > 3.0:
            count_spread_gt_3 += 1
        if any(v == "abstained_1_1_1_tie" for v in attrs.values()):
            count_1_1_1_ties += 1

    return {
        "total_clusters_evaluated": len(merged.get("events", [])) + len(near_misses),
        "accepted_3_3": count_3_3,
        "accepted_2_3": count_2_3,
        "dropped_1_3_near_miss": len(near_misses),
        "spread_exceeded_3s": count_spread_gt_3,
        "categorical_1_1_1_ties": count_1_1_1_ties,
    }


run_synthetic_ensemble_experiment = run_path_coverage_experiment


def build_stochastic_triple(
    seed: int,
    jitter_sd: float = 0.4,
    drop_p: float = 0.05,
    spurious_p: float = 0.03,
    attr_flip_p: float = 0.08,
) -> list[dict[str, Any]]:
    """
    Stochastic generator for realistic ensemble disagreement distribution.
    Parameters are guesses; replace with measured values after first real P1/P2 triple.
    """
    import random

    rng = random.Random(seed)
    base_obj = get_maximal_stream()
    base_dict = (
        base_obj.model_dump()
        if hasattr(base_obj, "model_dump")
        else base_obj.dict()
    )

    runs: list[dict[str, Any]] = []
    for run_idx in range(3):
        r = json.loads(json.dumps(base_dict))
        new_events: list[dict[str, Any]] = []
        for ev in r.get("events", []):
            if rng.random() < drop_p:
                continue

            ts = get_ts(ev)
            jitter = rng.gauss(0, jitter_sd)
            ev["t_start_s"] = round(ts + jitter, 2)
            if "timestamp_s" in ev:
                ev["timestamp_s"] = round(ts + jitter, 2)

            if rng.random() < attr_flip_p:
                attrs = ev.get("attributes", {})
                if isinstance(attrs, dict):
                    if "rhythm" in attrs:
                        rhythms = ["vfib", "vtach", "asystole", "pea"]
                        cur = attrs["rhythm"]
                        alt = [x for x in rhythms if x != cur]
                        if alt:
                            attrs["rhythm"] = rng.choice(alt)
                    elif "access_type" in attrs:
                        types = ["iv", "io", "central"]
                        cur = attrs["access_type"]
                        alt = [x for x in types if x != cur]
                        if alt:
                            attrs["access_type"] = rng.choice(alt)
            new_events.append(ev)

        if rng.random() < spurious_p:
            spurious = {
                "type": "pocus_cardiac",
                "t_start_s": round(rng.uniform(10.0, 300.0), 2),
                "timestamp_s": round(rng.uniform(10.0, 300.0), 2),
                "t_precision_s": 1.0,
                "confidence": 0.5,
                "evidence": [{"text": f"spurious pocus run {run_idx}"}],
                "attributes": {},
            }
            new_events.append(spurious)

        r["events"] = new_events
        runs.append(r)
    return runs


def run_stochastic_ensemble_experiment(n_seeds: int = 20) -> dict[str, Any]:
    """
    Run build_stochastic_triple across n_seeds and compute mean and range
    for 3/3, 2/3, 1/3 percentages, spread>3s counts, and 1/1/1 tie counts.
    """
    pct_3_3_list = []
    pct_2_3_list = []
    pct_1_3_list = []
    spread_gt_3_list = []
    ties_list = []

    for s in range(n_seeds):
        runs = build_stochastic_triple(seed=s)
        merged, near_misses = ensemble_streams(runs, k=3)
        total = len(merged.get("events", [])) + len(near_misses)
        if total == 0:
            continue
        c_3_3 = 0
        c_2_3 = 0
        c_spread = 0
        c_ties = 0
        for ev in merged.get("events", []):
            attrs = ev.get("attributes", {})
            v = attrs.get("ensemble_votes", 0)
            if v == 3:
                c_3_3 += 1
            elif v == 2:
                c_2_3 += 1
            if attrs.get("ensemble_spread_s", 0.0) > 3.0:
                c_spread += 1
            if any(val == "abstained_1_1_1_tie" for val in attrs.values()):
                c_ties += 1

        pct_3_3_list.append(round(c_3_3 / total * 100.0, 1))
        pct_2_3_list.append(round(c_2_3 / total * 100.0, 1))
        pct_1_3_list.append(round(len(near_misses) / total * 100.0, 1))
        spread_gt_3_list.append(c_spread)
        ties_list.append(c_ties)

    return {
        "seeds": n_seeds,
        "3_3_pct_mean": round(statistics.mean(pct_3_3_list), 1),
        "3_3_pct_range": f"{min(pct_3_3_list)}–{max(pct_3_3_list)}",
        "2_3_pct_mean": round(statistics.mean(pct_2_3_list), 1),
        "2_3_pct_range": f"{min(pct_2_3_list)}–{max(pct_2_3_list)}",
        "1_3_pct_mean": round(statistics.mean(pct_1_3_list), 1),
        "1_3_pct_range": f"{min(pct_1_3_list)}–{max(pct_1_3_list)}",
        "spread_gt_3s_mean": round(statistics.mean(spread_gt_3_list), 1),
        "spread_gt_3s_range": f"{min(spread_gt_3_list)}–{max(spread_gt_3_list)}",
        "ties_1_1_1_mean": round(statistics.mean(ties_list), 1),
        "ties_1_1_1_range": f"{min(ties_list)}–{max(ties_list)}",
    }


def deduplicate_window_streams(
    windows: list[tuple[Any, float, float]],
    overlap_tol_s: float = 5.0,
) -> Any:
    """
    Deduplicates a sequence of overlapping window EventStream objects across a case.
    Rule: Dedup should remove duplicates, never orphans (F-005).
    Each entry in `windows` is a tuple of (stream, win_start_primary, primary_end).
    - Items in [win_start_primary, primary_end) are kept.
    - Items in the overlap tail (>= primary_end) are kept IF AND ONLY IF no
      subsequent window contains a matching item of the same type within overlap_tol_s.
    """
    if not windows:
        raise ValueError("windows list must not be empty")

    from generated.models import EventStream

    kept_events = []
    kept_intervals = []
    kept_coverage = []
    final_fields = windows[-1][0].fields
    case_id = windows[0][0].case_id

    n = len(windows)
    for i, (stream, start_prim, end_prim) in enumerate(windows):
        is_last = (i == n - 1)
        # Check events
        for ev in stream.events:
            ts = getattr(ev, "timestamp_s", getattr(ev, "t_start_s", 0.0))
            if ts < start_prim:
                continue
            if is_last or ts < end_prim:
                kept_events.append(ev)
            else:
                # Overlap tail: check if any subsequent window has a matching event
                has_match = False
                for j in range(i + 1, n):
                    next_stream, _, _ = windows[j]
                    for next_ev in next_stream.events:
                        next_ts = getattr(next_ev, "timestamp_s", getattr(next_ev, "t_start_s", 0.0))
                        if ev.type == next_ev.type and abs(ts - next_ts) <= overlap_tol_s:
                            has_match = True
                            break
                    if has_match:
                        break
                if not has_match:
                    kept_events.append(ev)

        # Check intervals
        for inv in stream.intervals:
            ts = getattr(inv, "t_start_s", 0.0)
            if ts < start_prim:
                continue
            if is_last or ts < end_prim:
                kept_intervals.append(inv)
            else:
                # Overlap tail: check if any subsequent window has a matching interval
                has_match = False
                for j in range(i + 1, n):
                    next_stream, _, _ = windows[j]
                    for next_inv in next_stream.intervals:
                        next_ts = getattr(next_inv, "t_start_s", 0.0)
                        if inv.type == next_inv.type and abs(ts - next_ts) <= overlap_tol_s:
                            has_match = True
                            break
                    if has_match:
                        break
                if not has_match:
                    kept_intervals.append(inv)

        kept_coverage.extend(stream.coverage)

    return EventStream(
        case_id=case_id,
        events=kept_events,
        intervals=kept_intervals,
        coverage=kept_coverage,
        fields=final_fields,
    )


def pair_boundary_events(stream: Any) -> Any:
    """
    Deterministically pairs start/end boundary events into Interval objects.
    Specifically pairs 'rosc_detected' and 'rosc_lost' point events into 'rosc' Interval objects.
    """
    from generated.models import EventStream, Interval
    rosc_starts = sorted([e for e in stream.events if e.type == "rosc_detected"], key=lambda x: getattr(x, "t_start_s", 0.0))
    rosc_ends = sorted([e for e in stream.events if e.type == "rosc_lost"], key=lambda x: getattr(x, "t_start_s", 0.0))

    new_intervals = list(stream.intervals)
    used_ends = set()

    for start_ev in rosc_starts:
        t0 = getattr(start_ev, "t_start_s", 0.0)
        # Find earliest rosc_lost after t0
        t1 = None
        for i, end_ev in enumerate(rosc_ends):
            if i in used_ends:
                continue
            te = getattr(end_ev, "t_start_s", 0.0)
            if te >= t0:
                t1 = te
                used_ends.add(i)
                break

        inv = Interval(
            type="rosc",
            t_start_s=t0,
            t_end_s=t1,
            t_precision_s=getattr(start_ev, "t_precision_s", None),
            attributes=getattr(start_ev, "attributes", {}),
            evidence=getattr(start_ev, "evidence", []),
        )
        new_intervals.append(inv)

    return EventStream(
        case_id=stream.case_id,
        events=stream.events,
        intervals=new_intervals,
        coverage=stream.coverage,
        fields=stream.fields,
    )


def main() -> None:
    pc = run_path_coverage_experiment()
    print("=== D08 Path Coverage Fixture (Deterministic, Pinned) ===")
    for k, v in pc.items():
        print(f"  {k}: {v}")

    stoch = run_stochastic_ensemble_experiment(n_seeds=20)
    print("\n=== D08 Stochastic Baseline (20 seeds, PROVISIONAL — parameters are guesses) ===")
    for k, v in stoch.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()

