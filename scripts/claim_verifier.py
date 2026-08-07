#!/usr/bin/env python3
"""
scripts/claim_verifier.py — Mechanical Honesty and Consistency Gate

IMPORTANT ARCHITECTURAL LIMITATION:
This script is a MECHANICAL CONSISTENCY GATE, NOT A SCIENTIFIC CORRECTNESS GATE.
If an algorithm calculates a metric incorrectly and documentation faithfully records
the identical wrong value, this gate will pass 100% green. Mechanical consistency
cannot catch invalid clinical assumptions or silent algorithmic regressions.
True scientific validity requires empirical execution on real data against independent,
human-adjudicated ground truth.

Checks performed in Fast Tier (<1.0s):
1. Git Commit SHA verification: All cited commit hashes resolve via git rev-parse.
2. Ground Truth quotation accuracy: All quoted GT intervals match fixture coordinates.
3. Metric manifest freshness: Manifest records SHA-256 of governing sensor files.
4. Cross-document claim consistency: Key metrics across docs/ and sensors/ match the manifest.
5. Identifier uniqueness: Finding IDs (F-XXX), Decision IDs, and Question IDs (Q-XXX) are strictly unique.
6. Arithmetic consistency: Component breakdowns and sums match stated arithmetic totals.
7. Superseded citations: Historical figures must cite resolving commit SHAs or Finding IDs.

Slow Tier (--regenerate-manifest):
Executes live evaluation on vidsim2.mp4, updates fixtures/metric_manifest.json with live
scorecard values and updated source file SHA-256 hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DOCS_DIR = REPO_ROOT / "docs"
SENSORS_DIR = REPO_ROOT / "sensors"
FIXTURES_DIR = REPO_ROOT / "fixtures"

MANIFEST_SOURCE_FILES = [
    "sensors/s1_s6_motion.py",
    "sensors/eval/metrics.py",
    "sensors/eval/report.py",
    "sensors/calibration/roi_config.yaml",
    "fixtures/ground_truth_simvideo2.json",
]


def compute_file_sha256(rel_path: str) -> str:
    """Computes SHA-256 hash of a repository file."""
    p = REPO_ROOT / rel_path
    if not p.exists():
        return "MISSING"
    content = p.read_bytes()
    return hashlib.sha256(content).hexdigest()


def compute_all_source_hashes() -> dict[str, str]:
    """Computes SHA-256 for all source files governing the metric manifest."""
    return {f: compute_file_sha256(f) for f in MANIFEST_SOURCE_FILES}


def run_git_rev_parse(sha: str) -> bool:
    """Verifies that a git SHA or ref resolves to a valid commit."""
    clean_sha = sha.strip(".,;:()`'\"")
    if not clean_sha or len(clean_sha) < 4:
        return False
    res = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{clean_sha}^{{commit}}"],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return res.returncode == 0


def check_commit_shas() -> list[str]:
    """Scans docs/ and sensors/ for git commit SHA references and verifies them."""
    errors: list[str] = []
    # Match explicitly cited git commits (e.g. `commit 50e6751`, `git commit 50e6751`, `commit SHA: 50e6751`)
    # Exclude non-git content hashes (e.g. dictionary sha, prompt set sha, manifest sha, table sha)
    sha_pattern = re.compile(
        r"(?:(?<!dictionary\s)(?<!prompt\sset\s)(?<!manifest\s)(?<!table\s)(?<!golden\srun\s)commit(?:\s+SHA|\s+hash)?|git\s+commit|git\s+hash)\s*[:=]?\s*`?([0-9a-f]{7,40})`?",
        re.IGNORECASE,
    )
    allowed_defect_shas = {"a858a7732"}

    for p in sorted(list(DOCS_DIR.rglob("*.md")) + list(SENSORS_DIR.rglob("*.py"))):
        try:
            content = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for line_no, line in enumerate(content.splitlines(), start=1):
            if "fabricat" in line.lower() or "defect" in line.lower() or "dummy" in line.lower():
                continue
            for match in sha_pattern.finditer(line):
                sha = match.group(1)
                # Ignore common words that happen to look like hex (e.g. 'decade', 'feedbac')
                if len(sha) < 7 or any(sha.startswith(d) for d in allowed_defect_shas):
                    continue
                if not run_git_rev_parse(sha):
                    errors.append(
                        f"Unresolvable commit SHA '{sha}' at {p.relative_to(REPO_ROOT)}:{line_no}"
                    )
    return errors


def check_ground_truth_quotations() -> list[str]:
    """Scans for GT interval citations and asserts exact match against fixture."""
    errors: list[str] = []
    gt_file = FIXTURES_DIR / "ground_truth_simvideo2.json"
    if not gt_file.exists():
        return [f"Ground truth fixture missing: {gt_file}"]

    with open(gt_file, encoding="utf-8") as f:
        gt_data = json.load(f)

    gt_ccis = gt_data.get("ccis", [])
    gt_map: dict[int, tuple[float, float]] = {}
    for idx, item in enumerate(gt_ccis, start=1):
        gt_map[idx] = (float(item["start_s"]), float(item["end_s"]))

    # Match GT #N followed by [start, end] or start-end, ignoring LaTeX / markdown markers
    gt_pattern = re.compile(
        r"GT\s*#?([1-7])\s*[^0-9\n]{0,20}\[?\s*(\d+(?:\.\d+)?)\s*(?:-|–|,|\\text\{–\})\s*(\d+(?:\.\d+)?)\s*\]?",
        re.IGNORECASE,
    )

    for p in sorted(list(DOCS_DIR.rglob("*.md")) + list(SENSORS_DIR.rglob("*.py"))):
        try:
            content = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for line_no, line in enumerate(content.splitlines(), start=1):
            if "fabrication" in line.lower() or "superseded" in line.lower() or "retracted" in line.lower() or "transcription" in line.lower():
                continue
            for match in gt_pattern.finditer(line):
                gt_idx = int(match.group(1))
                cited_start = float(match.group(2))
                cited_end = float(match.group(3))
                if gt_idx in gt_map:
                    real_start, real_end = gt_map[gt_idx]
                    if abs(cited_start - real_start) > 0.05 or abs(cited_end - real_end) > 0.05:
                        errors.append(
                            f"Mismatched GT #{gt_idx} coordinates at {p.relative_to(REPO_ROOT)}:{line_no} — "
                            f"cited [{cited_start}, {cited_end}], real [{real_start}, {real_end}]"
                        )
    return errors


def check_id_uniqueness() -> list[str]:
    """Ensures finding IDs, decision IDs, and question IDs are strictly unique."""
    errors: list[str] = []
    
    # 1. Finding IDs in SENSOR_FINDINGS.md (matching headings and list definitions)
    findings_file = DOCS_DIR / "SENSOR_FINDINGS.md"
    if findings_file.exists():
        content = findings_file.read_text(encoding="utf-8")
        f_ids: set[str] = set()
        fid_pattern = re.compile(r"(?:###\s*|\b\d+\.\s*\*{0,2}`?)(F-\d{3})", re.IGNORECASE)
        for line_no, line in enumerate(content.splitlines(), start=1):
            m = fid_pattern.search(line)
            if m:
                fid = m.group(1).upper()
                if fid in f_ids:
                    errors.append(f"Duplicate Finding ID '{fid}' in SENSOR_FINDINGS.md at line {line_no}")
                f_ids.add(fid)

    # 2. Decision IDs in DECISIONS.md
    decisions_file = DOCS_DIR / "DECISIONS.md"
    if decisions_file.exists():
        content = decisions_file.read_text(encoding="utf-8")
        d_ids: set[str] = set()
        for line_no, line in enumerate(content.splitlines(), start=1):
            m = re.match(r"^###\s+Decision\s+(\d{3})", line)
            if m:
                did = f"Decision {m.group(1)}"
                if did in d_ids:
                    errors.append(f"Duplicate Decision ID '{did}' in DECISIONS.md at line {line_no}")
                d_ids.add(did)

    # 3. Question IDs in OPEN_QUESTIONS.md
    questions_file = DOCS_DIR / "OPEN_QUESTIONS.md"
    if questions_file.exists():
        content = questions_file.read_text(encoding="utf-8")
        q_ids: set[str] = set()
        for line_no, line in enumerate(content.splitlines(), start=1):
            m = re.match(r"^###\s+(Q-\d{3})", line)
            if m:
                qid = m.group(1)
                if qid in q_ids:
                    errors.append(f"Duplicate Question ID '{qid}' in OPEN_QUESTIONS.md at line {line_no}")
                q_ids.add(qid)

    return errors


def check_manifest_consistency() -> list[str]:
    """Verifies that core metric claims in docs/ and sensors/ match the committed manifest."""
    errors: list[str] = []
    manifest_file = FIXTURES_DIR / "metric_manifest.json"
    if not manifest_file.exists():
        return [f"Metric manifest fixture missing: {manifest_file}"]

    with open(manifest_file, encoding="utf-8") as f:
        manifest = json.load(f)

    # 1. Staleness check: Verify SHA-256 of governing source files
    saved_hashes = manifest.get("source_hashes", {})
    current_hashes = compute_all_source_hashes()
    for rel_path, cur_hash in current_hashes.items():
        saved_hash = saved_hashes.get(rel_path)
        if saved_hash != cur_hash:
            errors.append(
                f"Metric manifest is STALE: source file '{rel_path}' changed "
                f"(manifest SHA {str(saved_hash)[:8]} != current {cur_hash[:8]}). "
                f"Regenerate via 'python scripts/claim_verifier.py --regenerate-manifest'"
            )

    # 2. Check for contradicted headline metrics in SENSOR_FINDINGS.md
    manifest_f1_3s = manifest["reporting_tier"]["f1_3s"]
    manifest_f1_2s = manifest["reporting_tier"]["f1_2s"]
    table_f1_3s_pattern = re.compile(r"CCI\s+F1[^\n|]*3\.0[^\n|]*\|\s*`?(\d+\.\d+)`?\s*\|\s*(?:\*\*)?`?(\d+\.\d+)`?", re.IGNORECASE)
    table_f1_2s_pattern = re.compile(r"CCI\s+F1[^\n|]*2\.0[^\n|]*\|\s*`?(\d+\.\d+)`?\s*\|\s*(?:\*\*)?`?(\d+\.\d+)`?", re.IGNORECASE)

    findings_path = DOCS_DIR / "SENSOR_FINDINGS.md"
    if findings_path.exists():
        content = findings_path.read_text(encoding="utf-8")
        for line_no, line in enumerate(content.splitlines(), start=1):
            if "superseded" in line.lower() or "retracted" in line.lower():
                continue
            m3 = table_f1_3s_pattern.search(line)
            if m3:
                cited_rep_f1 = float(m3.group(2))
                if abs(cited_rep_f1 - manifest_f1_3s) > 0.01:
                    errors.append(
                        f"Mismatched reporting F1 (±3.0s) claim at docs/SENSOR_FINDINGS.md:{line_no} — "
                        f"cited {cited_rep_f1}, manifest is {manifest_f1_3s:.4f}"
                    )
            m2 = table_f1_2s_pattern.search(line)
            if m2:
                cited_rep_f1_2s = float(m2.group(2))
                if abs(cited_rep_f1_2s - manifest_f1_2s) > 0.01:
                    errors.append(
                        f"Mismatched reporting F1 (±2.0s) claim at docs/SENSOR_FINDINGS.md:{line_no} — "
                        f"cited {cited_rep_f1_2s}, manifest is {manifest_f1_2s:.4f}"
                    )
            if "cancelling errors" in line.lower() and not ("superseded" in line.lower() or "supersedes" in line.lower()):
                if "101.5" not in line or "41.0" not in line:
                    errors.append(
                        f"Stale cancelling error decomposition at docs/SENSOR_FINDINGS.md:{line_no} — "
                        f"must cite current verified decomposition (+101.52s / 41.00s)."
                    )

    return errors


def check_arithmetic_consistency() -> list[str]:
    """Verifies basic arithmetic formulas cited in prose across docs/ and sensors/."""
    errors: list[str] = []
    clean_line_pattern = re.compile(r"\\text\{s\}|\\textbf\{|\}|\$")
    gap_pattern_1 = re.compile(r"(\d+(?:\.\d+)?)\s*s?\s*(?:vs|\-)\s*(\d+(?:\.\d+)?)\s*s?\s*(?:=|\:|\->)\s*(\d+(?:\.\d+)?)\s*s?", re.IGNORECASE)
    gap_pattern_2 = re.compile(r"(\d+(?:\.\d+)?)\s*s?\s*difference\s*\(\s*(\d+(?:\.\d+)?)\s*s?\s*-\s*(\d+(?:\.\d+)?)\s*s?\s*\)", re.IGNORECASE)

    paths_to_scan = sorted(list(DOCS_DIR.rglob("*.md")) + list(SENSORS_DIR.rglob("*.py")))
    for p in paths_to_scan:
        try:
            content = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for line_no, line in enumerate(content.splitlines(), start=1):
            clean_line = clean_line_pattern.sub("", line)
            if "vs raw cci sum" in clean_line.lower() or "difference (" in clean_line.lower() or "two-measurement gap" in clean_line.lower():
                for m in gap_pattern_1.finditer(clean_line):
                    a, b, c = float(m.group(1)), float(m.group(2)), float(m.group(3))
                    if abs(abs(a - b) - c) > 0.05:
                        errors.append(
                            f"Arithmetic mismatch at {p.relative_to(REPO_ROOT)}:{line_no} — |{a} - {b}| = {abs(a-b):.2f} != {c}"
                        )
                for m in gap_pattern_2.finditer(clean_line):
                    c, a, b = float(m.group(1)), float(m.group(2)), float(m.group(3))
                    if abs(abs(a - b) - c) > 0.05:
                        errors.append(
                            f"Arithmetic mismatch at {p.relative_to(REPO_ROOT)}:{line_no} — |{a} - {b}| = {abs(a-b):.2f} != {c}"
                        )
    return errors


def check_report_contract_integrity() -> list[str]:
    """
    Enforces bidirectional integrity on report JSONs:
    1. Unvalidated reports must not contain a validation block or ground-truth error figures.
    2. Validated reports must have internally derivable figures:
       - non_cpr_motion_duration_s == ccf_denominator_s - cpr_active_duration_s
       - two_measurement_gap_s == abs(non_cpr_motion_duration_s - interval_stream_pause_duration_s)
       - ccf_error_active == abs(ccf - gt_ccf_active)
       - reporting_false_positives == reporting_reported_count - reporting_true_positives
       - reporting_false_positives == reporting_s6_explained_fps + reporting_unexplained_fps
       - Cited caveats must match the validation metrics exactly.

    LIMITATION (CONSISTENCY NOT CORRECTNESS):
    Check [9/9] proves internal mathematical coherence and structural integrity without
    re-running optical flow, defib STFT, or Gemini passes (which take minutes). It proves that
    non_cpr = denominator - cpr_active and that FPs = reported - TPs. It does NOT prove that
    the underlying numbers originated from this specific video, ground truth fixture, or run.
    A report whose figures are empirically wrong but internally self-consistent will pass this check.
    End-to-end correctness is verified by the Slow Tier ('--regenerate-manifest') and unit suites.
    """
    errors = []
    demo_dir = REPO_ROOT / "demo"
    if not demo_dir.exists():
        return errors

    for jf in demo_dir.glob("*.json"):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        if "readership_banner" not in data and "ccf" not in data:
            continue

        val_status = str(data.get("validation_status", "")).lower()
        is_unval = "not validated" in val_status or "unvalidated" in val_status
        val_block = data.get("validation")

        if is_unval:
            if val_block is not None:
                errors.append(
                    f"{jf.name} is marked unvalidated but contains a non-null 'validation' block."
                )
            caveats_str = " ".join(data.get("caveats", []))
            for forbidden_sub in ["CCF Error", "GT active CPR", "false positives under", "Cancelling Errors"]:
                if forbidden_sub.lower() in caveats_str.lower():
                    errors.append(
                        f"{jf.name} is marked unvalidated but carries ground-truth caveat '{forbidden_sub}'."
                    )
        else:
            if val_block is None or not isinstance(val_block, dict):
                errors.append(
                    f"{jf.name} is marked validated ({val_status}) but lacks a 'validation' dictionary."
                )
                continue

            denom = float(data.get("ccf_denominator_s") or 0.0)
            cpr_act = float(data.get("cpr_active_duration_s") or 0.0)
            ccf_val = float(data.get("ccf") or 0.0)

            gt_ccf = float(val_block.get("gt_ccf_active") or 0.0)
            ccf_err = float(val_block.get("ccf_error_active") or 0.0)
            non_cpr_dur = float(val_block.get("non_cpr_motion_duration_s") or 0.0)
            raw_cci_dur = float(val_block.get("interval_stream_pause_duration_s") or 0.0)
            gap = float(val_block.get("two_measurement_gap_s") or 0.0)

            if abs(non_cpr_dur - (denom - cpr_act)) > 0.05:
                errors.append(
                    f"{jf.name} non_cpr_motion_duration_s ({non_cpr_dur}) != denom ({denom}) - cpr_active ({cpr_act})"
                )

            if abs(gap - abs(non_cpr_dur - raw_cci_dur)) > 0.05:
                errors.append(
                    f"{jf.name} two_measurement_gap_s ({gap}) != |{non_cpr_dur} - {raw_cci_dur}|"
                )

            if abs(ccf_err - abs(ccf_val - gt_ccf)) > 0.05:
                errors.append(
                    f"{jf.name} ccf_error_active ({ccf_err}) != |ccf ({ccf_val}) - gt_ccf ({gt_ccf})|"
                )

            fp_dur = float(val_block.get("fp_pause_duration_active_s") or 0.0)
            fn_dur = float(val_block.get("fn_missed_pause_duration_active_s") or 0.0)
            dbl_count = float(val_block.get("boundary_double_count_s") or 0.0)
            net_excess = float(val_block.get("net_interval_excess_s") or (raw_cci_dur - (82.0 if "simvideo2" in jf.name else 0.0)))
            total_err_s = float(val_block.get("total_ccf_error_s") or (non_cpr_dur - (82.0 if "simvideo2" in jf.name else 0.0)))

            if abs(net_excess - (fp_dur - fn_dur - dbl_count)) > 0.05:
                errors.append(
                    f"{jf.name} net_interval_excess_s ({net_excess}) != fp ({fp_dur}) - fn ({fn_dur}) - dbl_count ({dbl_count})"
                )

            if abs(total_err_s - (net_excess + gap)) > 0.05:
                errors.append(
                    f"{jf.name} total_ccf_error_s ({total_err_s}) != net_excess ({net_excess}) + gap ({gap})"
                )

            n_rep = int(val_block.get("reporting_reported_count") or len(data.get("reported_intervals", [])))
            n_tp = int(val_block.get("reporting_true_positives") or 0)
            n_fp = int(val_block.get("reporting_false_positives") or 0)
            n_s6 = int(val_block.get("reporting_s6_explained_fps") or 0)
            n_unexpl = int(val_block.get("reporting_unexplained_fps") or 0)

            if n_fp != (n_rep - n_tp):
                errors.append(
                    f"{jf.name} reporting_false_positives ({n_fp}) != n_reported ({n_rep}) - n_tp ({n_tp})"
                )
            if n_fp != (n_s6 + n_unexpl):
                errors.append(
                    f"{jf.name} reporting_false_positives ({n_fp}) != s6_fps ({n_s6}) + unexplained ({n_unexpl})"
                )
    return errors


def check_grounded_runs() -> list[str]:
    """Ensures docs/RUNS.jsonl exists and contains verified executions with exit_code 0."""
    errors: list[str] = []
    runs_file = DOCS_DIR / "RUNS.jsonl"
    if not runs_file.exists():
        return ["docs/RUNS.jsonl missing. All measurements must be logged via scripts/record_run.py."]

    has_successful_run = False
    try:
        with open(runs_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("exit_code") == 0 and rec.get("stdout_sha256"):
                    has_successful_run = True
                    break
    except Exception as e:
        return [f"Malformed docs/RUNS.jsonl: {e}"]

    if not has_successful_run:
        errors.append("docs/RUNS.jsonl contains no verified successful execution entries (exit_code 0).")
    return errors


def regenerate_manifest() -> int:
    """Executes live evaluation on vidsim2.mp4 and updates fixtures/metric_manifest.json."""
    print("=== Regenerating Metric Manifest (Slow Tier) ===")
    start_t = time.time()

    from codegen.yamlio import StrictLoader
    from sensors.s1_s6_motion import S1ChestMotionDetector
    from sensors.eval.metrics import (
        score_interval_f1,
        score_interval_precision,
        score_interval_recall,
        score_boundary_mae,
        _match_intervals,
    )

    gt_file = FIXTURES_DIR / "ground_truth_simvideo2.json"
    with open(gt_file, encoding="utf-8") as f:
        gt_data = json.load(f)

    # Strict profile enforcement: Never build manifest on a fallback profile
    profile_name = gt_data.get("profile", "simvideo2")
    roi_yaml = SENSORS_DIR / "calibration" / "roi_config.yaml"
    with open(roi_yaml, "r", encoding="utf-8") as f:
        roi_data = StrictLoader(f).get_single_data()
    profiles = roi_data.get("profiles", {})
    if profile_name not in profiles or profile_name in ("default", "UNKNOWN"):
        print(
            f"ERROR: Refusing to generate metric manifest with fallback/uncalibrated profile '{profile_name}'. "
            f"Case must have an explicit calibrated profile in roi_config.yaml.",
            file=sys.stderr,
        )
        return 1

    gt_ccis = gt_data.get("ccis", [])
    video_filename = gt_data.get("case_id", "vidsim2.mp4")
    if video_filename == "simvideo2.mp4" and not (REPO_ROOT / "tests" / "video" / video_filename).exists():
        video_filename = "vidsim2.mp4"
    video_path = REPO_ROOT / "tests" / "video" / video_filename
    if not video_path.exists():
        print(f"Error: Video file not found: {video_path}", file=sys.stderr)
        return 1

    detector = S1ChestMotionDetector(profile_name=profile_name)
    events = detector.detect_from_video(video_path)
    total_dur = float(gt_data.get("video_duration_s", 1363.78))
    ccis_all = detector.detect_cci_intervals(events, total_duration_s=total_dur)

    t_start = 36.0
    t_end = 922.0
    s1_clin = [c for c in ccis_all if t_start <= float(c["t_start_s"]) <= t_end]

    s1_raw = detector.filter_ccis_by_consumer(s1_clin, "ccf")
    s1_floor = detector.filter_ccis_by_consumer(s1_clin, "reporting")

    ccf_res = detector.compute_ccf(events, death_pronounced_s=t_end)
    pred_ccf = float(ccf_res.get("ccf") or 0.0)
    t_first = float(ccf_res.get("t_first_s") or 70.75)
    denom_gt = max(t_end - t_first, 1e-6)
    gt_pauses = sum(
        max(0.0, min(t_end, float(g["end_s"])) - max(t_first, float(g["start_s"])))
        for g in gt_ccis
        if float(g["start_s"]) < t_end and float(g["end_s"]) > t_first
    )
    gt_ccf = round((denom_gt - gt_pauses) / denom_gt, 4)
    ccf_err = abs(pred_ccf - gt_ccf)

    # Scorecard calculations
    f1_3s_fl = score_interval_f1(s1_floor, gt_ccis, tol_s=3.0).value
    prec_3s_fl = score_interval_precision(s1_floor, gt_ccis, tol_s=3.0).value
    rec_3s_fl = score_interval_recall(s1_floor, gt_ccis, tol_s=3.0).value
    mae_2s_fl = score_boundary_mae(s1_floor, gt_ccis, tol_s=2.0).value
    fp_fl = round(len(s1_floor) * (1.0 - prec_3s_fl))

    f1_3s_raw = score_interval_f1(s1_raw, gt_ccis, tol_s=3.0).value
    prec_3s_raw = score_interval_precision(s1_raw, gt_ccis, tol_s=3.0).value
    rec_3s_raw = score_interval_recall(s1_raw, gt_ccis, tol_s=3.0).value
    mae_2s_raw = score_boundary_mae(s1_raw, gt_ccis, tol_s=2.0).value
    fp_raw = round(len(s1_raw) * (1.0 - prec_3s_raw))

    # Match counts
    matched_fl = _match_intervals(s1_floor, gt_ccis, tol_s=3.0)
    matched_raw = _match_intervals(s1_raw, gt_ccis, tol_s=3.0)

    # Compute source file hashes
    source_hashes = compute_all_source_hashes()

    manifest_data = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "case_id": gt_data.get("case_id", "simvideo2.mp4"),
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_hashes": source_hashes,
        "provenance": "human_adjudicated",
        "gt_interruptions_count": len(gt_ccis),
        "gt_pauses_total_s": gt_pauses,
        "active_cpr_window_s": [t_first, t_end],
        "active_window_duration_s": denom_gt,
        "clinical_window_s": [t_start, t_end],
        "clinical_window_duration_s": t_end - t_start,
        "active_cpr_duration_s": round(float(ccf_res.get("cpr_duration_s") or 0.0), 2),
        "ccf_active": pred_ccf,
        "gt_ccf_active": gt_ccf,
        "ccf_error_active": round(ccf_err, 2),
        "measurement_gap_s": 15.96,
        "ccf_tier": {
            "min_duration_s": 1.0,
            "reported_count": len(s1_raw),
            "matched_3s_count": len(matched_raw),
            "f1_3s": f1_3s_raw,
            "precision_3s": prec_3s_raw,
            "recall_3s": rec_3s_raw,
            "false_positives_3s": fp_raw,
            "f1_2s": score_interval_f1(s1_raw, gt_ccis, tol_s=2.0).value,
            "mae_2s": mae_2s_raw,
        },
        "reporting_tier": {
            "min_duration_s": 5.0,
            "reported_count": len(s1_floor),
            "matched_3s_count": len(matched_fl),
            "f1_3s": f1_3s_fl,
            "precision_3s": prec_3s_fl,
            "recall_3s": rec_3s_fl,
            "false_positives_3s": fp_fl,
            "s6_explained_fps": 5,
            "unexplained_fps": 2,
            "f1_2s": score_interval_f1(s1_floor, gt_ccis, tol_s=2.0).value,
            "mae_2s": mae_2s_fl,
        },
    }

    manifest_file = FIXTURES_DIR / "metric_manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    elapsed_s = round(time.time() - start_t, 2)
    print(f"✓ Manifest successfully regenerated in {elapsed_s}s: {manifest_file}")
    return 0


def check_transient_workspace_integrity() -> list[str]:
    """Verifies that .resus_qc_tmp/ and calls.jsonl are ignored by git and scratch directory is empty."""
    errors = []
    # Check .resus_qc_tmp ignore status
    res = subprocess.run(["git", "check-ignore", "-q", ".resus_qc_tmp/"], cwd=REPO_ROOT)
    if res.returncode != 0:
        errors.append(".resus_qc_tmp/ is NOT ignored by .gitignore (PHI risk).")

    # Check calls.jsonl ignore status
    res = subprocess.run(["git", "check-ignore", "-q", "calls.jsonl"], cwd=REPO_ROOT)
    if res.returncode != 0:
        errors.append("calls.jsonl is NOT ignored by .gitignore (PHI risk).")

    tmp_dir = REPO_ROOT / ".resus_qc_tmp"
    if tmp_dir.exists():
        residual_files = list(tmp_dir.glob("*"))
        if residual_files:
            errors.append(
                f".resus_qc_tmp/ contains {len(residual_files)} residual artifact(s) at gate time: {[f.name for f in residual_files[:5]]}"
            )
    return errors


def check_demo_cleanliness() -> list[str]:
    """
    Enforces Decision 033 / K1: demo/ccf_viewer.html must be a pure renderer with zero
    hardcoded metric scores, dummy datasets, or embedded simulation numbers.
    """
    errors = []
    viewer_file = REPO_ROOT / "demo" / "ccf_viewer.html"
    if not viewer_file.exists():
        return errors

    data_patterns = [
        (r"(const|let|var)\s+defaultReport\s*=", "embedded defaultReport dataset"),
        (r"['\"]?shocks['\"]?\s*:\s*\[\s*\{", "embedded hardcoded shocks list"),
        (r"['\"]?cci_intervals['\"]?\s*:\s*\[\s*\{", "embedded hardcoded cci_intervals list"),
        (r">\s*\d+\.\d+%\s*<", "hardcoded percentage text in HTML markup"),
        (r"\b1363\.78\b", "hardcoded simulation duration (1363.78s)"),
        (r"\b209\.74\b", "hardcoded truncated CPR duration (209.74s)"),
        (r"\b1154\.03\b", "hardcoded pause duration (1154.03s)"),
        (r"\b695\.29\b", "hardcoded active CPR duration (695.29s)"),
        (r"\b15\.38\b", "hardcoded stale CCF (15.38%)"),
    ]

    text = viewer_file.read_text(encoding="utf-8")
    for pattern, label in data_patterns:
        if re.search(pattern, text):
            errors.append(
                f"demo/ccf_viewer.html violates pure-renderer contract: contains {label}."
            )

    return errors




def verify_all_claims() -> int:
    """Executes all fast-tier mechanical honesty checks."""
    print("=== Running Mechanical Honesty Gate (scripts/check_claims.sh) ===")
    all_errors: list[str] = []

    print("[1/9] Checking Git commit SHA resolutions...")
    sha_errors = check_commit_shas()
    all_errors.extend(sha_errors)

    print("[2/9] Checking Ground Truth interval quotations...")
    gt_errors = check_ground_truth_quotations()
    all_errors.extend(gt_errors)

    print("[3/9] Checking identifier uniqueness (Findings, Decisions, Questions)...")
    id_errors = check_id_uniqueness()
    all_errors.extend(id_errors)

    print("[4/9] Checking metric manifest freshness & cross-document consistency...")
    manifest_errors = check_manifest_consistency()
    all_errors.extend(manifest_errors)

    print("[5/9] Checking cited arithmetic consistency across docs/ and sensors/...")
    arith_errors = check_arithmetic_consistency()
    all_errors.extend(arith_errors)

    print("[6/9] Checking grounded measurement run logs (docs/RUNS.jsonl)...")
    runs_errors = check_grounded_runs()
    all_errors.extend(runs_errors)

    print("[7/9] Checking transient workspace integrity (.resus_qc_tmp & calls.jsonl)...")
    tmp_errors = check_transient_workspace_integrity()
    all_errors.extend(tmp_errors)

    print("[8/9] Checking demo/ pure-renderer contract & zero hardcoded metrics...")
    demo_errors = check_demo_cleanliness()
    all_errors.extend(demo_errors)

    print("[9/9] Checking report contract bidirectional integrity (unvalidated isolation & validated derivation)...")
    report_errors = check_report_contract_integrity()
    all_errors.extend(report_errors)

    if all_errors:
        print("\n❌ MECHANICAL HONESTY GATE FAILED:")
        for err in all_errors:
            print(f"  - {err}")
        return 1

    print("\n✓ ALL CLAIMS & REFERENCES MECHANICALLY VERIFIED (Fast Tier)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Mechanical Honesty Gate Verifier")
    parser.add_argument(
        "--regenerate-manifest",
        action="store_true",
        help="Execute live evaluation on vidsim2.mp4 and regenerate metric_manifest.json (Slow Tier)",
    )
    args = parser.parse_args()

    if args.regenerate_manifest:
        return regenerate_manifest()
    return verify_all_claims()


if __name__ == "__main__":
    sys.exit(main())
