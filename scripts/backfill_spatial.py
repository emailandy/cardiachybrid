"""Backfill: run the real gemini-4-argon spatial tracking pass on an already-finished live run and save it into case.json."""
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "ui"), str(REPO)]

import live_engine as le  # noqa: E402
from spatial_pass import run_spatial_tracking  # noqa: E402

job_id = sys.argv[1]
run_dir = le.RUNS_DIR / job_id
case = json.loads((run_dir / "case.json").read_text())
video = le.local_video_for_case(case)
assert video is not None, "no local video for case"
job = le.LiveEngineJob({"record_id": case["record_id"], "model_id": "gemini-4-argon"}, lambda j, c: None)
job.id = job_id
t0 = time.time()


def gen(contents, name):
    vc = job._client()
    txt = job._generate(vc, contents, name, temperature=0.2, response_mime_type="application/json")
    (run_dir / f"{name}.json").write_text(txt, encoding="utf-8")
    return txt


tracks = run_spatial_tracking(video, float(case["duration_s"]), gen, job._log, "gemini-4-argon")
case["spatial_tracks"] = tracks
(run_dir / "case.json").write_text(json.dumps(case, indent=2, default=str))
print(f"DONE {len(tracks['frames'])} frames, {sum(len(f['objects']) for f in tracks['frames'])} boxes, identities={tracks['identities']} in {time.time()-t0:.0f}s")
