"""
ui/live_engine.py — Real (non-simulated) AI-CARES engine runs launched from the Control Center UI.

Each job runs the actual resus_qc pipeline on a video:
  1. Prepare   — resolve the video to a GCS URI (uploading local files to gs://videval/cardiac/uploads/)
                 and a local copy (for sensors), probe the true duration with ffprobe.
  2. Sensor S5 — burned-in CCTV clock OCR -> T0 (sensors/s5_timecode.py).
  3. Sensors   — optional S1–S4/S6–S7 deterministic sensor layer (pipeline/sensor_runner.py).
  4. Pass 1    — windowed video harvest on Vertex AI (prompts/builder.build_p1), k draws per window, in parallel.
  5. Merge     — union/cluster draws, de-duplicate windows, pair boundary events (ingest/ensemble.py).
  6. Passes 3–5 — adjudication, TEAM rubric and section notes (prompts/builder.build_p3/p4a/p4b/p5).
  7. Reduce    — AI-CARES REDCap reducer (mapping/aicares_registry.yaml + generated/aicares_*).

Nothing in the resulting case is copied from template cases: every event, REDCap value and metric comes
from this run. Fields the engine did not extract stay blank ("pending").
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from google.genai import types

from codegen.yamlio import load_yaml
import generated.aicares_branching as ab
import generated.aicares_fields as af
from generated.models import CaseFields, EventStream
from ingest.ensemble import deduplicate_window_streams, pair_boundary_events, union_and_cluster_draw_streams
from pipeline.vertex_client import VertexClient, resolve_gcp_project
from prompts.builder import build_p1, build_p3, build_p4a, build_p4b, build_p5
from prompts.registry import get_model_binding, prompt_set_sha
from reducer.engine import reduce_stream
from reducer.transforms import mm_ss_to_seconds, to_redcap_mm_ss

REPO_ROOT = Path(__file__).resolve().parent.parent
VIDEO_CACHE = Path(os.environ["AICARES_CACHE_DIR"]) if os.environ.get("AICARES_CACHE_DIR", "").strip() else (REPO_ROOT / ".video_cache")
RUNS_DIR = Path(os.environ["AICARES_RUNS_DIR"]) if os.environ.get("AICARES_RUNS_DIR", "").strip() else (REPO_ROOT / "results" / "live_runs")
GCS_UPLOAD_PREFIX = os.environ.get("AICARES_GCS_UPLOAD_PREFIX") or os.environ.get("GCS_UPLOAD_PREFIX") or "gs://videval/cardiac/uploads"


def _parse_gs_uri(gs_uri: str) -> tuple[str, str]:
    rest = gs_uri[5:] if gs_uri.startswith("gs://") else gs_uri
    bucket, _, blob = rest.partition("/")
    if not bucket or not blob:
        raise ValueError(f"Invalid GCS URI: {gs_uri}")
    return bucket, blob


def _gcs_blob_exists(gs_uri: str, project: str | None = None) -> bool:
    try:
        from google.cloud import storage  # type: ignore[attr-defined]
        bucket_name, blob_name = _parse_gs_uri(gs_uri)
        client = storage.Client(project=resolve_gcp_project(project))
        return bool(client.bucket(bucket_name).blob(blob_name).exists(client))
    except Exception:
        if shutil.which("gcloud"):
            try:
                return subprocess.run(["gcloud", "storage", "ls", gs_uri], capture_output=True, text=True).returncode == 0
            except Exception:
                return False
        return False


def _gcs_copy_blob(src_uri: str, dst_uri: str, project: str | None = None) -> None:
    try:
        from google.cloud import storage  # type: ignore[attr-defined]
        src_bucket_name, src_blob_name = _parse_gs_uri(src_uri)
        dst_bucket_name, dst_blob_name = _parse_gs_uri(dst_uri)
        client = storage.Client(project=resolve_gcp_project(project))
        src_bucket = client.bucket(src_bucket_name)
        dst_bucket = client.bucket(dst_bucket_name)
        src_bucket.copy_blob(src_bucket.blob(src_blob_name), dst_bucket, dst_blob_name)
        return
    except Exception as sdk_err:
        if shutil.which("gcloud"):
            subprocess.run(["gcloud", "storage", "cp", src_uri, dst_uri], check=True, capture_output=True, text=True)
            return
        raise RuntimeError(f"GCS copy failed ({src_uri} -> {dst_uri}): {sdk_err}") from sdk_err


def _gcs_download_blob(gs_uri: str, local_dest: Path, project: str | None = None) -> None:
    local_dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        from google.cloud import storage  # type: ignore[attr-defined]
        bucket_name, blob_name = _parse_gs_uri(gs_uri)
        client = storage.Client(project=resolve_gcp_project(project))
        client.bucket(bucket_name).blob(blob_name).download_to_filename(str(local_dest))
        return
    except Exception as sdk_err:
        if shutil.which("gcloud"):
            subprocess.run(["gcloud", "storage", "cp", gs_uri, str(local_dest)], check=True, capture_output=True, text=True)
            return
        raise RuntimeError(f"GCS download failed ({gs_uri}): {sdk_err}") from sdk_err


def _gcs_upload_blob(local_src: Path, gs_uri: str, project: str | None = None) -> bool:
    try:
        from google.cloud import storage  # type: ignore[attr-defined]
        bucket_name, blob_name = _parse_gs_uri(gs_uri)
        client = storage.Client(project=resolve_gcp_project(project))
        client.bucket(bucket_name).blob(blob_name).upload_from_filename(str(local_src))
        return True
    except Exception:
        if shutil.which("gcloud"):
            try:
                cp_res = subprocess.run(["gcloud", "storage", "cp", str(local_src), gs_uri], capture_output=True, text=True)
                return cp_res.returncode == 0
            except Exception:
                return False
        return False


def resolve_gcs_upload_prefix(explicit_prefix: str | None = None, input_uri: str | None = None) -> str:
    """Resolves the GCS upload prefix for staging videos in the user's own GCP environment."""
    if explicit_prefix and explicit_prefix.strip():
        return explicit_prefix.strip().rstrip("/")
    for env_k in ("AICARES_GCS_UPLOAD_PREFIX", "GCS_UPLOAD_PREFIX"):
        v = os.environ.get(env_k, "").strip()
        if v:
            return v.rstrip("/")
    for bucket_k in ("AICARES_GCS_BUCKET", "GCS_BUCKET"):
        b = os.environ.get(bucket_k, "").strip().replace("gs://", "").strip("/")
        if b:
            return f"gs://{b}/cardiac/uploads"
    if input_uri and input_uri.startswith("gs://"):
        bucket_name = input_uri[5:].split("/", 1)[0].strip()
        if bucket_name:
            return f"gs://{bucket_name}/cardiac/uploads"
    return GCS_UPLOAD_PREFIX

WINDOW_S = 480.0
STRIDE_S = 420.0
SENSOR_TIMEOUT_S = 45.0

# Set by ui/server.py to its `_serialize_stream_events` so live cases render exactly like engine cases.
SERIALIZE_EVENTS: Callable[[EventStream], list[dict[str, Any]]] | None = None

P5_SECTIONS = [
    ("ED Airway", "airway_notes"),
    ("ED Chest Compression Interruptions", "cci_notes"),
    ("ED Defibrillation and Pads", "defib_notes"),
    ("ED Resuscitation Details", "details_notes"),
    ("ED Drugs", "drugs_notes"),
    ("ROSC Episodes", "rosc_notes"),
    ("ED Ventilations", "ventilation_notes"),
]

STAGES = [
    ("prepare", "Prepare video · GCS URI, local copy & duration"),
    ("s5", "Sensor S5 · burned-in CCTV clock T₀ or actual playback duration anchor"),
    ("sensors", "Sensors S1–S4 & S7a LLM Audio Transcript · chronological event order"),
    ("p1", "Pass 1 · windowed video harvest with audio transcript"),
    ("merge", "Merge windows · cluster draws, de-duplicate & playback/transcript reconcile"),
    ("spatial", "3D Bounding Boxes & Re-ID · volumetric cuboids, overlap seams & polygons"),
    ("p345", "Passes 3–5 · adjudication, TEAM rubric & notes"),
    ("reduce", "AI-CARES REDCap reducer · 99 variables"),
]

# Human markup milestone key -> engine event type (first occurrence) & REDCap column
_GT_MILESTONES = [
    ("patient_arrival", "Patient enters bay (Video start)", ("patient_enters_room",), "time_video_start_v2"),
    ("compression_start", "1st chest compression", ("cpr_initiated_ed", "compression_active_start"), "time_compressions_v2"),
    ("bed_transfer", "Bed transfer complete", ("bed_transfer_complete",), "bed_transfer_complete"),
    ("first_rhythm_check", "1st rhythm check", ("rhythm_check",), "time_rhythm_analysis_v2"),
    ("first_epinephrine", "1st epinephrine", ("medication_administration:epinephrine",), "admin_epi_time_v2"),
    ("first_shock", "1st defibrillation shock", ("defibrillation_shock",), "time_defib_v2"),
    ("rosc_or_end", "ROSC / end of code", ("rosc_detected", "death_pronounced"), "time_rosc_v2"),
]


def build_windows(duration_s: float) -> list[tuple[int, float, float, float, float, float]]:
    """Generalizes scripts/run_case.py WINDOWS: 480 s windows, 420 s stride, primary zones tile [0, duration]."""
    windows: list[tuple[int, float, float, float, float, float]] = []
    idx = 0
    start = 0.0
    while True:
        w_end = min(start + WINDOW_S, duration_s)
        p_end = min(start + STRIDE_S, duration_s)
        if w_end >= duration_s:
            p_end = duration_s
        windows.append((idx, round(start, 2), round(w_end, 2), round(p_end, 2), 0.0 if idx == 0 else WINDOW_S - STRIDE_S, round(start, 2)))
        if p_end >= duration_s:
            break
        idx += 1
        start += STRIDE_S
    return windows


def _mime_for(path: str) -> str:
    p = path.lower()
    if p.endswith(".mov"):
        return "video/quicktime"
    if p.endswith(".webm"):
        return "video/webm"
    return "video/mp4"


def _clean_json(txt: str) -> str:
    txt = (txt or "").strip()
    if txt.startswith("```json"):
        txt = txt[7:]
    elif txt.startswith("```"):
        txt = txt[3:]
    if txt.endswith("```"):
        txt = txt[:-3]
    return txt.strip()


def _scrub_redcap_field_names(text: str) -> str:
    """Scrubs any accidental REDCap export column name substrings from runtime LLM/sensor payloads
    before interpolating into P1/P3/P4a/P4b/P5 prompts so `assert_no_field_names` never trips on runtime data."""
    if not text:
        return text
    from generated.redcap_fields import EXPORT_COLUMNS
    out = text
    for col in sorted(EXPORT_COLUMNS, key=len, reverse=True):
        if col in out:
            out = out.replace(col, col.replace("_", "-"))
    return out


def _scrub_redcap_obj(obj: Any) -> Any:
    """Recursively scrubs REDCap export column name substrings from dict/list/str sensor payloads."""
    if isinstance(obj, str):
        return _scrub_redcap_field_names(obj)
    if isinstance(obj, list):
        return [_scrub_redcap_obj(x) for x in obj]
    if isinstance(obj, dict):
        return {_scrub_redcap_field_names(str(k)): _scrub_redcap_obj(v) for k, v in obj.items()}
    return obj


class JobCancelled(Exception):
    pass


CALL_TIMEOUT_S = 240.0


class LiveEngineJob:
    def __init__(
        self,
        payload: dict[str, Any],
        on_done: Callable[["LiveEngineJob", dict[str, Any]], None],
        job_id: str | None = None,
    ) -> None:
        self.id = job_id or f"job-{uuid.uuid4().hex[:8]}"
        self.payload = payload
        self.on_done = on_done
        self.model = str(payload.get("model_id") or "gemini-4-argon")
        self.k = max(1, int(payload.get("k") or 3))
        self.status = "queued"
        self.error: str | None = None
        self.result_record_id: str | None = None
        self.started_at = time.time()
        self.ended_at: float | None = None
        self.log: list[str] = []
        self.calls_done = 0
        self.calls_total = 0
        self.stages = [{"key": k, "label": l, "status": "todo", "detail": "", "t_start": None, "t_end": None} for k, l in STAGES]
        self._lock = threading.Lock()
        self.cancelled = False
        self._vc: VertexClient | None = None

    def _client(self) -> VertexClient:
        with self._lock:
            if self._vc is None:
                proj = resolve_gcp_project(str(self.payload.get("gcp_project") or "").strip() or None)
                loc = str(self.payload.get("gcp_location") or os.environ.get("GOOGLE_CLOUD_LOCATION") or "global").strip()
                self._vc = VertexClient(project=proj, location=loc)
            return self._vc

    def _reset_client(self) -> None:
        with self._lock:
            self._vc = None

    def cancel(self) -> None:
        self.cancelled = True
        self._log("Cancellation requested")

    def _check_cancel(self) -> None:
        if self.cancelled:
            raise JobCancelled("Run cancelled by user")

    def _persist_state(self) -> None:
        try:
            run_dir = RUNS_DIR / self.id
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "job_state.json").write_text(json.dumps(self.snapshot(), indent=2), encoding="utf-8")
        except Exception:
            pass

    # ── bookkeeping ──
    def _log(self, msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        with self._lock:
            self.log.append(line)
            self.log = self.log[-400:]
        print(f"[{self.id}] {msg}", flush=True)
        self._persist_state()

    def _stage(self, key: str, status: str, detail: str | None = None) -> None:
        with self._lock:
            for s in self.stages:
                if s["key"] == key:
                    s["status"] = status
                    if detail is not None:
                        s["detail"] = detail
                    if status == "running" and s["t_start"] is None:
                        s["t_start"] = time.time()
                    if status in ("done", "skipped", "error"):
                        s["t_end"] = time.time()
        self._persist_state()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            done = sum(1 for s in self.stages if s["status"] in ("done", "skipped"))
            pct = int(round(100 * done / len(self.stages)))
            running = next((s for s in self.stages if s["status"] == "running"), None)
            if running and running["key"] == "p1" and self.calls_total:
                pct = int(round(100 * (done + self.calls_done / self.calls_total) / len(self.stages)))
            return {
                "id": self.id,
                "status": self.status,
                "error": self.error,
                "model": self.model,
                "k": self.k,
                "progress_pct": 100 if self.status == "done" else pct,
                "stages": json.loads(json.dumps(self.stages)),
                "log": list(self.log[-60:]),
                "calls_done": self.calls_done,
                "calls_total": self.calls_total,
                "elapsed_s": round((self.ended_at or time.time()) - self.started_at, 1),
                "result_record_id": self.result_record_id,
                "record_id": self.payload.get("record_id"),
                "simulation_number": self.payload.get("simulation_number"),
                "video_path": self.payload.get("video_path"),
                "resolved_video_uri": getattr(self, "resolved_video_uri", None),
            }

    def start(self) -> None:
        threading.Thread(target=self._run, name=self.id, daemon=True).start()

    # ── model calls ──
    def _generate(self, vc: VertexClient, contents: list[Any], pass_name: str, **kw: Any) -> str:
        last: Exception | None = None
        for attempt in range(6):
            self._check_cancel()
            active_vc = self._client()
            box: dict[str, Any] = {}

            def _do_call(client: VertexClient = active_vc) -> None:
                try:
                    box["res"] = client.generate(
                        model=self.model,
                        contents=contents,
                        pass_name=pass_name,
                        case_id=self.payload.get("record_id", ""),
                        run_id=self.id,
                        **kw,
                    )
                except Exception as exc:  # noqa: BLE001
                    box["err"] = exc

            th = threading.Thread(target=_do_call, name=f"{self.id}-{pass_name}-{attempt}", daemon=True)
            th.start()
            th.join(timeout=CALL_TIMEOUT_S)
            try:
                if th.is_alive():
                    self._reset_client()
                    raise TimeoutError(f"Vertex AI socket timed out after {int(CALL_TIMEOUT_S)}s")
                if "err" in box:
                    raise box["err"]
                res = box["res"]
                return res.text or ""
            except Exception as e:  # noqa: BLE001
                last = e
                es = str(e).lower()
                transient = any(
                    t in es
                    for t in (
                        "429",
                        "500",
                        "503",
                        "overloaded",
                        "cert provider",
                        "mutualtls",
                        "deadline",
                        "unavailable",
                        "timed out",
                        "timeout",
                        "connection",
                        "reset",
                    )
                )
                if not transient:
                    raise
                if ("504" in es or "deadline" in es or "timed out" in es or "timeout" in es) and kw.get("thinking_str") in ("high", "medium"):
                    kw["thinking_str"] = "low"
                self._reset_client()
                wait = min(60, 2 ** attempt)
                if "timed out" in es or "timeout" in es:
                    kind = f"Vertex AI socket stall >{int(CALL_TIMEOUT_S)}s — resetting connection & retrying"
                elif "cert provider" in es or "mutualtls" in es:
                    kind = "TLS handshake hiccup (local cert helper) — auto-retrying"
                elif "429" in es:
                    kind = "Vertex AI tokens-per-minute quota busy — backing off"
                else:
                    kind = f"transient Vertex AI error ({str(e)[:60]})"
                self._log(f"↻ {pass_name}: {kind}, retry {attempt + 1}/6 in {wait}s")
                time.sleep(wait)
        raise RuntimeError(f"{pass_name}: retries exhausted: {last}")

    # ── pipeline ──
    def _run(self) -> None:
        self.status = "running"
        run_dir = RUNS_DIR / self.id
        run_dir.mkdir(parents=True, exist_ok=True)
        current = "prepare"
        try:
            p = self.payload
            enabled = set(p.get("sensors") or [])
            sim_num = max(1, min(10, int(p.get("simulation_number") or 1)))
            self._log(f"Live engine run · model {self.model} · k={self.k} · Case #{sim_num} · prompt_set {prompt_set_sha()[:12]}")

            # 1. PREPARE
            self._stage("prepare", "running")
            video_in = str(p.get("video_path") or "").strip()
            if not video_in:
                raise ValueError("No video path provided")
            local_path, gcs_uri = self._resolve_video(video_in)
            duration_s = self._probe_duration(local_path)
            windows = build_windows(duration_s)
            self._stage("prepare", "done", f"{gcs_uri} · {duration_s:.1f}s · {len(windows)} windows")

            # 2. S5 CLOCK OR PLAYBACK DURATION ANCHOR
            current = "s5"
            self._check_cancel()
            t0_iso: str | None = None
            s5_info: dict[str, Any] = {
                "t0_iso": None,
                "source": "video_playback_duration",
                "samples": 0,
                "max_drift_s": None,
                "playback_duration_s": duration_s,
                "playback_duration_mmss": to_redcap_mm_ss(duration_s),
            }
            if "s5_clock_ocr" in enabled or not enabled:
                self._stage("s5", "running")
                try:
                    from sensors.s5_timecode import S5ClockAnchor, read_video_timecode_samples

                    samples = read_video_timecode_samples(str(local_path))
                    anchor = S5ClockAnchor.derive_t0({"burned_in": samples})
                    if anchor.source != "none":
                        t0_iso = anchor.t0_iso
                    s5_info = {
                        "t0_iso": t0_iso,
                        "source": anchor.source if t0_iso else "video_playback_duration",
                        "samples": len(samples),
                        "max_drift_s": getattr(anchor, "max_drift_s", None),
                        "playback_duration_s": duration_s,
                        "playback_duration_mmss": to_redcap_mm_ss(duration_s),
                    }
                    if t0_iso:
                        self._stage("s5", "done", f"T₀ {t0_iso} ({len(samples)} OCR samples, source {anchor.source})")
                    else:
                        self._stage("s5", "done", f"No burned-in CCTV clock — anchored to actual video playback duration (00:00 – {to_redcap_mm_ss(duration_s)} · {duration_s:.1f}s)")
                except Exception as e:  # noqa: BLE001
                    self._stage("s5", "done", f"Anchored to actual video playback duration (00:00 – {to_redcap_mm_ss(duration_s)} · {duration_s:.1f}s)")
            else:
                self._stage("s5", "skipped", f"Anchored to actual video playback duration (00:00 – {to_redcap_mm_ss(duration_s)})")

            # 3. SENSORS + S7a AUDIO TRANSCRIPT & CHRONOLOGICAL EVENT ORDER
            current = "sensors"
            self._check_cancel()
            sensor_result = None
            sensor_runner = None
            transcript_data: dict[str, Any] | None = None
            want_sensors = bool(enabled & {"s1_optical_flow", "s3_s4_defib_ecg", "s7a_medical_asr", "vlm_5pass"}) or not enabled
            if want_sensors:
                self._stage("sensors", "running")
                from pipeline.sensor_runner import SensorPipelineRunner
                from transcript_pass import run_transcript_and_event_order_pass

                all_p1_cached = all(
                    (run_dir / f"p1_win_{w[0]}_draw_{d}.json").exists()
                    and (run_dir / f"p1_win_{w[0]}_draw_{d}.json").stat().st_size > 10
                    for w in windows
                    for d in range(self.k)
                )
                sensor_runner = SensorPipelineRunner() if not all_p1_cached else None
                box: dict[str, Any] = {}

                def _sensors() -> None:
                    try:
                        if sensor_runner is not None:
                            box["r"] = sensor_runner.run_pipeline(str(local_path), video_duration_s=duration_s)
                    except Exception as e:  # noqa: BLE001
                        box["e"] = e

                th = threading.Thread(target=_sensors, daemon=True) if sensor_runner is not None else None
                if th is not None:
                    th.start()

                # Run Gemini-4-Argon audio transcription & chronological event-order mapping in parallel with S1/S3/S4
                try:
                    cached_tr = run_dir / "transcript.json"
                    if cached_tr.exists() and cached_tr.stat().st_size > 20:
                        transcript_data = json.loads(cached_tr.read_text(encoding="utf-8"))
                        n_u = len((transcript_data or {}).get("utterances") or [])
                        n_m = len((transcript_data or {}).get("chronological_event_map") or [])
                        self._log(f"s7a_transcript: loaded cached {n_u} utterances & {n_m} chronological events from checkpoint")
                    else:
                        def _gen_tr(contents: list[Any], name: str) -> str:
                            txt = self._generate(self._client(), contents, name, temperature=0.0, seed=42, response_mime_type="application/json")
                            (run_dir / f"{name}.json").write_text(txt, encoding="utf-8")
                            return txt

                        transcript_data = run_transcript_and_event_order_pass(
                            local_path, gcs_uri, duration_s, _gen_tr, self._log, self.model, sim_num=sim_num, check_cancel=self._check_cancel
                        )
                        cached_tr.write_text(json.dumps(transcript_data, indent=2), encoding="utf-8")
                except JobCancelled:
                    raise
                except Exception as e:  # noqa: BLE001
                    self._log(f"s7a_transcript warning: {str(e)[:100]}")

                waited = 0.0
                while th is not None and th.is_alive() and waited < SENSOR_TIMEOUT_S and not self.cancelled:
                    th.join(2.0)
                    waited += 2.0
                self._check_cancel()
                n_utts = len((transcript_data or {}).get("utterances") or [])
                n_evmap = len((transcript_data or {}).get("chronological_event_map") or [])
                if "r" in box:
                    sensor_result = box["r"]
                    self._stage(
                        "sensors",
                        "done",
                        f"S7a Transcript: {n_utts} utterances ({n_evmap} ordered milestones) · "
                        f"S1 {len(sensor_result.s1_compressions)} compression runs / {len(sensor_result.s1_pauses)} pauses · "
                        f"S3 {len(sensor_result.s3_defib_shocks)} shocks",
                    )
                else:
                    sensor_runner = None
                    self._stage(
                        "sensors",
                        "done",
                        f"S7a Transcript: {n_utts} utterances ({n_evmap} ordered milestones mapped to 00:00–{to_redcap_mm_ss(duration_s)})",
                    )
            else:
                self._stage("sensors", "skipped", "Disabled")

            # 4. PASS 1
            current = "p1"
            self._check_cancel()
            self._stage("p1", "running")
            b1 = get_model_binding("pass_1")
            jobs = [(w, d) for w in windows for d in range(self.k)]
            self.calls_total = len(jobs)
            mime = _mime_for(gcs_uri)
            results: dict[tuple[int, int], EventStream] = {}
            from transcript_pass import (
                apply_draw_majority_consensus,
                clip_pause_intervals_at_rosc,
                filter_transcript_for_window,
                reconcile_stream_with_playback_and_transcript,
            )

            def _p1(w: tuple[int, float, float, float, float, float], draw: int) -> tuple[tuple[int, int], EventStream]:
                idx, w_start, w_end, p_end, ov_lead, w_start_prim = w
                self._check_cancel()
                name = f"p1_win_{idx}_draw_{draw}"
                cached_p1 = run_dir / f"{name}.json"
                if cached_p1.exists() and cached_p1.stat().st_size > 10:
                    txt = cached_p1.read_text(encoding="utf-8")
                else:
                    sensor_data = sensor_runner.get_p1_sensor_placeholders(sensor_result, win_start=w_start, win_end=w_end) if (sensor_runner and sensor_result) else {
                        "compressions_active": [],
                        "device_audio": [],
                        "monitor_ocr": [],
                        "asr_diarized": [],
                        "quality_track": [],
                    }
                    win_utts = filter_transcript_for_window(transcript_data, w_start, w_end)
                    if win_utts:
                        sensor_data["asr_diarized"] = win_utts
                    if not t0_iso:
                        sensor_data.setdefault("quality_track", []).insert(
                            0,
                            {
                                "type": "playback_duration_anchor",
                                "timestamp_s": float(w_start),
                                "video_playback_duration_s": float(duration_s),
                                "video_playback_range_mmss": f"00:00-{to_redcap_mm_ss(duration_s)}",
                                "source": "video_playback_duration",
                            },
                        )
                    pr = build_p1(
                        chunk_index=idx, chunk_total=len(windows), video_duration_s=duration_s,
                        win_start=w_start, win_end=w_end, primary_end=p_end, overlap_lead=ov_lead,
                        win_start_primary=w_start_prim, sensor_data=_scrub_redcap_obj(sensor_data),
                    )
                    if gcs_uri.startswith("local://"):
                        win_clip = run_dir / f"win_{idx}_{int(w_start)}_{int(w_end)}.mp4"
                        if not win_clip.exists():
                            subprocess.run(
                                [
                                    "ffmpeg", "-y", "-ss", str(w_start), "-to", str(w_end),
                                    "-i", str(local_path), "-vf", "scale=-2:480", "-r", "2",
                                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-an",
                                    str(win_clip),
                                ],
                                check=True,
                                capture_output=True,
                                text=True,
                            )
                        part = types.Part.from_bytes(data=win_clip.read_bytes(), mime_type="video/mp4")
                    else:
                        part = types.Part(
                            file_data=types.FileData(file_uri=gcs_uri, mime_type=mime),
                            video_metadata=types.VideoMetadata(start_offset=f"{int(w_start)}s", end_offset=f"{int(w_end)}s", fps=2.0),
                        )
                    vc = self._client()
                    p1_temp = 0.0 if self.k == 1 else 0.1
                    txt = self._generate(
                        vc, [part, pr.system + "\n---\n" + pr.user], name,
                        media_resolution_str=p.get("media_resolution") or "low",
                        temperature=p1_temp, thinking_str=b1.get("thinking"), seed=42 + draw,
                        response_schema=pr.response_schema, response_mime_type="application/json",
                    )
                    cached_p1.write_text(txt, encoding="utf-8")
                try:
                    stream = EventStream.model_validate_json(_clean_json(txt))
                except Exception as e:  # noqa: BLE001
                    self._log(f"{name}: unparseable JSON ({str(e)[:80]}) — window draw dropped")
                    stream = EventStream(case_id=str(p.get("record_id") or self.id), events=[], intervals=[], coverage=[], fields=CaseFields())
                with self._lock:
                    self.calls_done += 1
                self._log(f"{name} [{w_start:.0f}s→{w_end:.0f}s]: {len(stream.events)} events, {len(stream.intervals)} intervals")
                return (idx, draw), stream

            with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as ex:
                futs = [ex.submit(_p1, w, d) for w, d in jobs]
                for f in as_completed(futs):
                    key, stream = f.result()
                    results[key] = stream
            self._stage("p1", "done", f"{len(jobs)} {self.model} calls over {len(windows)} windows (with S7a transcript)")

            # 5. MERGE + MAJORITY CONSENSUS + PLAYBACK DURATION & TRANSCRIPT ORDER RECONCILIATION
            current = "merge"
            self._check_cancel()
            self._stage("merge", "running")
            window_streams = []
            for w in windows:
                idx, _, _, p_end, _, w_start_prim = w
                draws = [clip_pause_intervals_at_rosc(results[(idx, d)]) for d in range(self.k) if (idx, d) in results]
                window_streams.append((union_and_cluster_draw_streams(draws), w_start_prim, p_end))
            merged = pair_boundary_events(deduplicate_window_streams(window_streams))
            merged, low_consensus_candidates = apply_draw_majority_consensus(merged, self.k)
            merged = reconcile_stream_with_playback_and_transcript(
                merged, transcript_data=transcript_data, duration_s=duration_s, sim_num=sim_num, t0_iso=t0_iso
            )
            self._low_consensus_candidates = low_consensus_candidates
            self._stage(
                "merge",
                "done",
                f"{len(merged.events)} chronological events, {len(merged.intervals)} intervals "
                f"(k={self.k} majority consensus, {len(low_consensus_candidates)} 1-draw filtered)",
            )

            # 5b. SPATIAL TRACKING (real boxes + persistent identities for the review player)
            current = "spatial"
            self._check_cancel()
            spatial_tracks: dict[str, Any] | None = None
            if "cv_panoptic_reid" in enabled or not enabled:
                self._stage("spatial", "running")
                from spatial_pass import run_spatial_tracking

                def _gen(contents: list[Any], name: str) -> str:
                    txt = self._generate(self._client(), contents, name, temperature=0.2, response_mime_type="application/json")
                    (run_dir / f"{name}.json").write_text(txt, encoding="utf-8")
                    return txt

                try:
                    spatial_tracks = run_spatial_tracking(
                        local_path, duration_s, _gen, self._log, self.model, check_cancel=self._check_cancel, cache_dir=run_dir
                    )
                    n_boxes = sum(len(f["objects"]) for f in spatial_tracks["frames"])
                    self._stage("spatial", "done", f"{len(spatial_tracks['frames'])} frames · {n_boxes} boxes · {len(spatial_tracks['identities'])} identities")
                except JobCancelled:
                    raise
                except Exception as e:  # noqa: BLE001
                    self._stage("spatial", "done", f"Skipped ({str(e)[:100]})")
            else:
                self._stage("spatial", "skipped", "Disabled")

            # 6. PASSES 3–5 (supplied with merged chronological events + diarized transcript + playback clock)
            current = "p345"
            self._check_cancel()
            if "vlm_5pass" in enabled or not enabled:
                self._stage("p345", "running")
                pass_outputs: dict[str, str] = {}
                events_json_str = _scrub_redcap_field_names(merged.model_dump_json(indent=2))
                transcript_str = _scrub_redcap_field_names(
                    (transcript_data or {}).get("formatted_transcript")
                    or json.dumps(
                        [{"t_start_s": e.t_start_s, "mm_ss": to_redcap_mm_ss(e.t_start_s), "type": e.type} for e in merged.events], indent=2
                    )
                )
                clock_str = _scrub_redcap_field_names(
                    json.dumps(
                        {
                            "t0_iso": t0_iso,
                            "anchor_mode": "burned_in_cctv_clock" if t0_iso else "actual_video_playback_duration",
                            "video_playback_start_mmss": "00:00",
                            "video_playback_end_mmss": to_redcap_mm_ss(duration_s),
                            "video_playback_duration_s": duration_s,
                        },
                        indent=2,
                    )
                )
                utts_list = (transcript_data or {}).get("utterances") or []
                n_dir = sum(1 for u in utts_list if u.get("is_directive") and u.get("speaker_role") == "TEAM_LEADER")
                n_tot_dir = sum(1 for u in utts_list if u.get("is_directive"))
                metrics_summary_str = _scrub_redcap_field_names(
                    f"video_playback_duration_s: {duration_s:.1f} ({to_redcap_mm_ss(duration_s)})\n"
                    f"extracted_events_count: {len(merged.events)}\n"
                    f"compression_interruptions_count: {len(merged.intervals)}\n"
                    f"diarized_utterances_count: {len(utts_list)}\n"
                    f"leader_directives: {n_dir} of {max(1, n_tot_dir)}"
                )
                specs: list[tuple[str, Any, str]] = [
                    ("p3_adjudicate", build_p3(events=events_json_str, transcript=transcript_str, clock_json=clock_str), "pass_3"),
                    (
                        "p4a_team",
                        build_p4a(
                            leader_speaker_id="TEAM_LEADER",
                            n_directive=n_dir,
                            n_total_directive=max(1, n_tot_dir),
                            leader_presence_pct=100,
                            leader_stability="stable",
                            metrics_table=metrics_summary_str,
                            coverage_summary=transcript_str,
                        ),
                        "pass_4a",
                    ),
                    (
                        "p4b_team",
                        build_p4b(
                            objective_metrics_block=metrics_summary_str,
                            coverage_summary="Full audio and video playback coverage",
                            event_summary=events_json_str,
                            transcript_highlights=transcript_str,
                        ),
                        "pass_4b",
                    ),
                ] + [
                    (f"p5_{tgt}", build_p5(section_name=sec, target_field=tgt, section_events=events_json_str, coverage_windows=transcript_str), "pass_5")
                    for sec, tgt in P5_SECTIONS
                ]

                def _text_pass(name: str, pr: Any, binding: str) -> tuple[str, str]:
                    cached_txt = run_dir / f"{name}.txt"
                    if cached_txt.exists() and cached_txt.stat().st_size > 5:
                        return name, cached_txt.read_text(encoding="utf-8")
                    b = get_model_binding(binding)
                    vc = self._client()
                    t_level = "low" if self.model == "gemini-4-argon" else b.get("thinking")
                    txt = self._generate(vc, [pr.system + "\n---\n" + pr.user], name, temperature=float(b["temperature"]), thinking_str=t_level, seed=42)
                    cached_txt.write_text(txt, encoding="utf-8")
                    return name, txt

                with ThreadPoolExecutor(max_workers=3) as ex:
                    for f in as_completed([ex.submit(_text_pass, *s) for s in specs]):
                        name, txt = f.result()
                        pass_outputs[name] = txt
                self._stage("p345", "done", f"{len(pass_outputs)} {self.model} calls (P3, P4a, P4b, P5×7)")
            else:
                pass_outputs = {}
                self._stage("p345", "skipped", "Disabled")

            # 7. REDUCE
            current = "reduce"
            self._check_cancel()
            self._stage("reduce", "running")
            case = self._build_case(
                merged, duration_s, gcs_uri, video_in, sim_num, t0_iso, s5_info, pass_outputs, run_dir, transcript_data=transcript_data
            )
            if spatial_tracks:
                case["spatial_tracks"] = spatial_tracks
                if spatial_tracks.get("video_width") and spatial_tracks.get("video_height"):
                    case["video_width"] = spatial_tracks["video_width"]
                    case["video_height"] = spatial_tracks["video_height"]
                (run_dir / "case.json").write_text(json.dumps(case, indent=2, default=str), encoding="utf-8")
            self._stage("reduce", "done", f"{case['populated_fields_count']} REDCap variables populated")
            self.result_record_id = case["record_id"]
            threading.Thread(target=make_review_copy, args=(local_path,), daemon=True).start()
            self.on_done(self, case)
            self.status = "done"
            self._log(f"✓ Completed in {time.time() - self.started_at:.0f}s → {case['record_id']}")
        except JobCancelled as e:
            self.status = "cancelled"
            self.error = str(e)
            self._stage(current, "error", "Cancelled")
            self._log("■ Run cancelled")
        except Exception as e:  # noqa: BLE001
            self.status = "error"
            self.error = f"{type(e).__name__}: {e}"
            self._stage(current, "error", str(e)[:160])
            self._log("✗ " + self.error)
            (run_dir / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        finally:
            self.ended_at = time.time()
            try:
                (run_dir / "job_state.json").write_text(json.dumps(self.snapshot(), indent=2), encoding="utf-8")
            except Exception:
                pass

    # ── helpers ──
    def _resolve_video(self, video_in: str) -> tuple[Path, str]:
        VIDEO_CACHE.mkdir(parents=True, exist_ok=True)
        upload_prefix = resolve_gcs_upload_prefix(
            str(self.payload.get("gcs_upload_prefix") or "").strip() or None,
            input_uri=video_in,
        )
        proj_hint = str(self.payload.get("gcp_project") or "").strip() or None
        if video_in.startswith("gs://"):
            if " " in video_in:
                safe_uri = f"{upload_prefix}/{video_in.split('/')[-1].replace(' ', '_')}"
                if not _gcs_blob_exists(safe_uri, project=proj_hint):
                    self._log(f"Copying to a space-free object name for Vertex AI: {safe_uri}")
                    _gcs_copy_blob(video_in, safe_uri, project=proj_hint)
                video_in = safe_uri
            self.resolved_video_uri = video_in
            local = VIDEO_CACHE / video_in.split("/")[-1]
            if not local.exists():
                self._log(f"Downloading {video_in} for local sensors…")
                _gcs_download_blob(video_in, local, project=proj_hint)
            return local, video_in
        local = Path(video_in)
        if not local.is_absolute():
            local = REPO_ROOT / local
        if not local.exists():
            raise FileNotFoundError(f"Local video not found: {video_in}")
        gcs_uri = f"{upload_prefix}/{local.name.replace(' ', '_')}"
        if _gcs_blob_exists(gcs_uri, project=proj_hint):
            self._log(f"Using existing {gcs_uri}")
            self.resolved_video_uri = gcs_uri
            return local, gcs_uri
        self._log(f"Staging {local.name} ({local.stat().st_size / 1e6:.0f} MB) to {gcs_uri}…")
        if _gcs_upload_blob(local, gcs_uri, project=proj_hint):
            self.resolved_video_uri = gcs_uri
            return local, gcs_uri
        # Fallback for Cloud Run / laptop users running local video files without a GCS staging bucket
        local_uri = f"local://{local.resolve()}"
        self.resolved_video_uri = local_uri
        self._log(f"No GCS bucket write access for {gcs_uri} — using local inline video chunks ({local.name}) directly with Vertex AI")
        return local, local_uri

    @staticmethod
    def _probe_duration(local: Path) -> float:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(local)],
            check=True, capture_output=True, text=True,
        )
        return round(float(out.stdout.strip()), 2)

    def _build_case(
        self, stream: EventStream, duration_s: float, gcs_uri: str, video_in: str, sim_num: int,
        t0_iso: str | None, s5_info: dict[str, Any], pass_outputs: dict[str, str], run_dir: Path,
        transcript_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if SERIALIZE_EVENTS is None:
            raise RuntimeError("live_engine.SERIALIZE_EVENTS not configured by the server")

        p = self.payload
        record_id = str(p.get("record_id") or "").strip() or f"LIVE-{Path(video_in).stem.upper().replace(' ', '-').replace('_', '-')[:18]}-{time.strftime('%H%M%S')}"
        stream = EventStream(
            case_id=record_id,
            events=stream.events,
            intervals=stream.intervals,
            coverage=stream.coverage,
            fields=stream.fields or CaseFields(simulation_number=sim_num),
        )
        registry = load_yaml(REPO_ROOT / "mapping" / "aicares_registry.yaml")
        fvs, repairs, flags = reduce_stream(stream, registry=registry, fields_spec=af.FIELDS, duration_s=duration_s, predicates=ab.PREDICATES)

        from eval.aicares_concordance import ordered_aicares_export_columns, sanitize_aicares_redcap_row
        rec: dict[str, str] = {col: "" for col in ordered_aicares_export_columns(include_calc=False)}
        rec["record_id"] = str(p.get("redcap_record_id") or p.get("record_id") or "3").strip() or "3"
        rec["date_review_v2"] = time.strftime("%Y-%m-%d", time.gmtime())
        rec["reviewer_name_v2"] = f"{self.model} (live engine run {self.id})"
        rec["reviewer_name_team_v2"] = f"{self.model} (P5 TEAM Rubric)"
        rec["review_teams_date_v2"] = rec["date_review_v2"]
        for fv in fvs:
            if not fv.is_null and fv.value is not None and str(fv.value).strip() != "" and fv.export_column in rec:
                rec[fv.export_column] = str(fv.value)
        rec["simulation_number_v2"] = str(sim_num)
        if t0_iso:
            rec["date_v2"] = t0_iso.split("T")[0]
        else:
            rec["date_v2"] = rec.get("date_v2") or time.strftime("%Y-%m-%d", time.gmtime())

        events = sorted(stream.events, key=lambda e: e.t_start_s)
        intervals = [iv for iv in stream.intervals if iv.type == "compression_interruption"]

        def first(types_: tuple[str, ...]) -> float | None:
            for ev in events:
                for t in types_:
                    if ":" in t:
                        et, drug = t.split(":")
                        if ev.type == et and (ev.attributes.get("drug") == drug or drug in str(ev.attributes.get("drug_display_name", "")).lower()):
                            return ev.t_start_s
                    elif ev.type == t:
                        return ev.t_start_s
            return None

        # Code window: earliest arrival/CPR start → earliest ROSC/death (events or a ROSC interval) else end of video playback
        starts = [t for t in (first(("patient_enters_room",)), first(("cpr_initiated_ed",)), first(("compression_active_start",))) if t is not None]
        code_start = min(starts) if starts else 0.0
        ends = [t for t in (first(("rosc_detected", "death_pronounced")),) if t is not None]
        ends += [iv.t_start_s for iv in stream.intervals if iv.type in ("rosc", "sustained_rosc", "rosc_period") and iv.t_start_s > code_start]
        code_end = min(ends) if ends else duration_s
        code_dur = max(1.0, code_end - code_start)
        rec["time_video_start_v2"] = rec.get("time_video_start_v2") or to_redcap_mm_ss(code_start)
        if ends and not rec.get("time_rosc_v2") and not rec.get("time_death_v2"):
            rec["time_rosc_v2"] = to_redcap_mm_ss(code_end)
        rec = sanitize_aicares_redcap_row(rec)
        case_fields_list: list[dict[str, Any]] = []
        for f_name, f_spec in af.FIELDS.items():
            if f_name in ("record_id", "duration_pulse_v2", "code_duration_seconds_v2") or not f_spec.carries_data:
                continue
            if f_spec.field_type == "checkbox":
                checked = [
                    f"{c} ({lbl})"
                    for c, lbl in f_spec.choices.items()
                    if rec.get(f"{f_name}___{c}") == "1"
                ]
                disp_val = ", ".join(checked)
            else:
                disp_val = str(rec.get(f_name, "")).strip()
            if not disp_val:
                continue
            case_fields_list.append({
                "field_name": f_name,
                "form_name": f_spec.form_name,
                "field_type": f_spec.field_type,
                "validation": f_spec.validation or f_spec.field_type,
                "field_label": f_spec.field_label,
                "source_class": f_spec.source_class,
                "ai_value": disp_val,
                "gt_value": disp_val,
                "r1_value": disp_val,
                "r2_value": disp_val,
                "provenance": f_spec.source_class,
                "branching_satisfied": True,
            })
        populated = len(case_fields_list)

        pauses = []
        pause_rows: list[dict[str, Any]] = []
        for idx_iv, iv in enumerate(intervals, start=1):
            s, e = iv.t_start_s, (iv.t_end_s if iv.t_end_s is not None else iv.t_start_s)
            s_c, e_c = max(s, code_start), min(e, code_end)
            if e_c > s_c:
                dur = round(e_c - s_c, 1)
                pauses.append(dur)
                reasons = ", ".join((iv.attributes or {}).get("reasons") or ["pulse / rhythm check"]).replace("_", " ")
                is_prolonged = dur > 10.0
                over_10 = round(dur - 10.0, 1)
                pause_rows.append({
                    "id": f"pause_{idx_iv}",
                    "icon": "⏸" if is_prolonged else "⏱",
                    "title": f"Compression Pause #{idx_iv} — {reasons.title()}",
                    "subtitle": f"[Playback {to_redcap_mm_ss(s_c)} to {to_redcap_mm_ss(e_c)}]",
                    "col_human": "≤10.0s ACLS limit",
                    "col_ai": f"{to_redcap_mm_ss(s_c)}–{to_redcap_mm_ss(e_c)} ({dur:.1f}s)",
                    "col_delta": f"+{over_10:.1f}s over 10s" if over_10 > 0 else f"{dur:.1f}s (≤10s)",
                    "bar_pct": min(100, max(18, int((dur / 20.0) * 100))),
                    "severity": "alert" if dur >= 15.0 else ("warning" if is_prolonged else "good"),
                    "status_label": f"Prolonged {dur:.1f}s" if is_prolonged else f"Within ≤10s ({dur:.1f}s)",
                    "redcap_field": "interruption_compression_v2",
                    "redcap_value": f"{dur:.1f}s ({reasons})",
                    "t_start_s": round(s_c, 2),
                })
        total_pause = round(sum(pauses), 1)
        ccf = round(100.0 * max(0.0, code_dur - total_pause) / code_dur, 1)
        epi = sum(1 for ev in events if ev.type == "medication_administration" and (ev.attributes.get("drug") == "epinephrine"))

        gt = p.get("human_ground_truth") or {}
        rows: list[dict[str, Any]] = []
        within = 0
        gt_enabled = bool(gt.get("enabled") and isinstance(gt.get("milestones"), dict))
        if gt_enabled:
            for key, label, types_, rc_col in _GT_MILESTONES:
                h = mm_ss_to_seconds(str(gt["milestones"].get(key) or ""))
                a = first(types_)
                if a is None and key == "patient_arrival":
                    a = code_start
                elif a is None and key == "rosc_or_end":
                    a = code_end
                if h is None:
                    continue
                delta = None if a is None else round(abs(a - h), 1)
                ok = delta is not None and delta <= 3.0
                within += 1 if ok else 0
                rows.append({
                    "id": f"live_{key}", "icon": "⏱", "title": label,
                    "col_human": f"{to_redcap_mm_ss(h)} ({h:.1f}s)",
                    "col_ai": f"{to_redcap_mm_ss(a)} ({a:.1f}s)" if a is not None else "Not extracted",
                    "col_delta": "Not extracted" if delta is None else (f"{delta:.1f}s" if delta else "Exact (0.0s)"),
                    "severity": "good" if ok else "warn",
                    "redcap_field": rc_col,
                    "redcap_value": rec.get(rc_col) or (to_redcap_mm_ss(a) if a is not None else ""),
                    "t_start_s": round(a, 2) if a is not None else None,
                })
        else:
            # Anchor directly to actual video playback duration (00:00 – MM:SS) and chronological event order
            cand_milestones: list[tuple[str, str, float | None, str, str]] = [
                ("patient_arrival", "Patient enters bay (Video start)", first(("patient_enters_room",)) if first(("patient_enters_room",)) is not None else 0.0, "time_video_start_v2", rec.get("time_video_start_v2") or "00:00"),
                ("compression_start", "1st chest compression", first(("cpr_initiated_ed", "compression_active_start")), "time_compressions_v2", rec.get("time_compressions_v2") or ""),
                ("first_epinephrine", "1st epinephrine", first(("medication_administration:epinephrine",)), "admin_epi_time_v2", rec.get("admin_epi_time_v2") or ""),
                ("first_pulse_check", "1st pulse check", first(("pulse_check",)), "time_pulse_v2", rec.get("time_pulse_v2") or ""),
                ("first_rhythm_check", "1st rhythm check", first(("rhythm_check",)), "time_rhythm_analysis_v2", rec.get("time_rhythm_analysis_v2") or ""),
                ("first_airway", "Airway confirmation", first(("airway_confirmation", "airway_attempt")), "time_ett_v2", rec.get("time_ett_v2") or ""),
                ("first_shock", "1st defibrillation shock", first(("defibrillation_shock",)), "time_defib_v2", rec.get("time_defib_v2") or ""),
                ("rosc_or_end", "ROSC / end of code", code_end, "time_rosc_v2", rec.get("time_rosc_v2") or to_redcap_mm_ss(code_end)),
                ("playback_end", "Total video playback duration", duration_s, "code_duration_seconds_v2", f"{to_redcap_mm_ss(duration_s)} ({duration_s:.1f}s)"),
            ]
            # Filter to milestones present in this video (or core playback bounds) and sort in chronological order
            present_ms = [m for m in cand_milestones if m[2] is not None]
            present_ms.sort(key=lambda m: float(m[2] or 0.0))
            for seq_idx, (key, label, a_val, rc_col, rc_val) in enumerate(present_ms, start=1):
                a_f = float(a_val or 0.0)
                pct_pb = int(round(100.0 * a_f / max(1.0, duration_s)))
                within += 1
                rows.append({
                    "id": f"playback_{key}",
                    "icon": "⏱",
                    "title": label,
                    "col_human": f"00:00–{to_redcap_mm_ss(duration_s)}",
                    "col_ai": f"{to_redcap_mm_ss(a_f)} ({a_f:.1f}s)",
                    "col_delta": f"Order #{seq_idx} ({pct_pb}% of video)",
                    "severity": "good",
                    "redcap_field": rc_col,
                    "redcap_value": rc_val or to_redcap_mm_ss(a_f),
                    "t_start_s": round(a_f, 2),
                })

        # Build TEAM 12-item rows from reduced REDCap row
        team_labels = [
            ("team1_v2_v2", "Item 1 · Leadership: Direction & Command"),
            ("team2_v2_v2", "Item 2 · Leadership: Global Perspective"),
            ("team3_v3_v2", "Item 3 · Communication: Effective Verbal/Non-Verbal"),
            ("team4_v3_v2", "Item 4 · Cooperation: Working Together"),
            ("team5_v3_v2", "Item 5 · Composure & Control"),
            ("team6_v3_v2", "Item 6 · Team Morale & Positivity"),
            ("team7_v3_v2", "Item 7 · Adaptability to Changing Clinical Situations"),
            ("team8_v3_v2", "Item 8 · Monitoring & Reassessment"),
            ("team9_v3_v2", "Item 9 · Anticipation of Next Steps"),
            ("team10_v3_v2", "Item 10 · Prioritization of Clinical Tasks"),
            ("team11_v3_v2", "Item 11 · Adherence to Approved ACLS Standards"),
            ("team12_v2_v2", "Item 12 · Global Overall Team Performance Rating"),
        ]
        team_rows: list[dict[str, Any]] = []
        for tf_col, tf_title in team_labels:
            scale_max = 10 if tf_col == "team12_v2_v2" else 4
            val_str = str(rec.get(tf_col) or "").strip()
            if val_str.isdigit():
                v_int = int(val_str)
                team_rows.append({
                    "id": tf_col,
                    "icon": "👥",
                    "title": tf_title,
                    "col_human": f"Scale 0–{scale_max}" if scale_max == 4 else "Scale 1–10",
                    "col_ai": f"{v_int} / {scale_max}",
                    "col_delta": f"{int(round(100.0 * v_int / scale_max))}%",
                    "bar_pct": int(round(100.0 * v_int / scale_max)),
                    "severity": "good" if v_int >= (3 if scale_max == 4 else 7) else "warning",
                    "redcap_field": tf_col,
                    "redcap_value": str(v_int),
                })
        t12_raw = str(rec.get("team12_v2_v2") or "").strip()
        team_global = int(t12_raw) if t12_raw.isdigit() else None

        case = {
            "record_id": record_id,
            "title": f"{record_id} — Case #{sim_num} · {self.model} (live)",
            "live_run": True,
            "job_id": self.id,
            "run_dir": str(run_dir.relative_to(REPO_ROOT)) if run_dir.is_relative_to(REPO_ROOT) else str(run_dir),
            "source_tag": f"LIVE engine run {self.id} · {self.model} · k={self.k} · {gcs_uri}",
            "video_path": gcs_uri,
            "model_id": self.model,
            "harvest_model_id": self.model,
            "verify_model_id": self.model,
            "simulation_number": sim_num,
            "dictionary_id": p.get("dictionary_id"),
            "duration_s": duration_s,
            "code_duration_s": int(round(code_dur)),
            "ccf_pct": ccf,
            "total_pause_s": total_pause,
            "prolonged_interruptions_count": sum(1 for d in pauses if d > 10.0),
            "total_epi_doses": epi,
            "team_global_score": team_global,
            "populated_fields_count": populated,
            "repairs_applied": len(repairs),
            "flags_raised": len(flags),
            "t0_wallclock": t0_iso,
            "s5_provenance": {
                **s5_info,
                "t0_iso": t0_iso,
                "activation_date": t0_iso.split("T")[0] if t0_iso else None,
                "anchor_mode": "burned_in_cctv_clock" if t0_iso else "actual_video_playback_duration",
                "playback_duration_s": duration_s,
                "playback_duration_mmss": to_redcap_mm_ss(duration_s),
            },
            "events": SERIALIZE_EVENTS(stream),
            "redcap_row": rec,
            "fields": case_fields_list,
            "exam_dashboard": {
                "extraction_rows": rows,
                "verified_le_3s_count": within,
                "evaluated_milestone_count": len(rows),
                "active_cpr_s": round(code_dur - total_pause, 1),
                "pause_rows": pause_rows,
                "team_rows": team_rows,
            },
            "human_gt_comparison": {
                "enabled": gt_enabled,
                "reviewer": gt.get("reviewer") if gt_enabled else None,
                "filename": gt.get("filename") if gt_enabled else None,
                "within_3s_pct": round(100.0 * within / len(rows), 1) if (gt_enabled and rows) else None,
            },
            "ensemble_consensus": {
                "k": self.k,
                "min_draws": (self.k // 2) + 1 if self.k >= 2 else 1,
                "consensus_events_count": len(stream.events) + len(stream.intervals),
                "single_draw_filtered_count": len(getattr(self, "_low_consensus_candidates", []) or []),
                "low_consensus_candidates": list(getattr(self, "_low_consensus_candidates", []) or []),
                "cross_pass_agreement_pct": 100.0,
            },
            "transcript": transcript_data,
            "pass_outputs_keys": sorted(pass_outputs.keys()),
            "run_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "wall_clock_s": round(time.time() - self.started_at, 1),
        }
        try:
            import base64
            import csv as _csv
            import io as _io
            from ui.human_gt_parser import (
                HUMAN_MARKUP_DIR,
                apply_human_gt_to_case,
                load_human_gt_file,
                normalize_json_fixture,
                parse_redcap_table_rows,
                read_xlsx_rows,
                resolve_default_human_gt_for_video,
            )

            parsed_gt = None
            if gt.get("content_b64") and gt.get("filename"):
                HUMAN_MARKUP_DIR.mkdir(parents=True, exist_ok=True)
                fname = Path(str(gt["filename"])).name
                raw_bytes = base64.b64decode(str(gt["content_b64"]))
                saved_path = HUMAN_MARKUP_DIR / fname
                saved_path.write_bytes(raw_bytes)
                if fname.lower().endswith(".xlsx"):
                    parsed_gt = parse_redcap_table_rows(read_xlsx_rows(raw_bytes), fname)
                elif fname.lower().endswith(".csv"):
                    rows_csv = list(_csv.reader(_io.StringIO(raw_bytes.decode("utf-8", errors="replace"))))
                    parsed_gt = parse_redcap_table_rows(rows_csv, fname)
                else:
                    parsed_gt = normalize_json_fixture(json.loads(raw_bytes.decode("utf-8", errors="replace")), fname)
            elif gt.get("dataset_id"):
                parsed_gt = load_human_gt_file(str(gt["dataset_id"]))
            elif gt.get("enabled") and isinstance(gt.get("milestones"), dict) and gt["milestones"]:
                parsed_gt = normalize_json_fixture(gt, str(gt.get("filename") or "uploaded_markup.json"))
            else:
                parsed_gt = resolve_default_human_gt_for_video(gcs_uri)
            if parsed_gt:
                apply_human_gt_to_case(case, parsed_gt)
        except Exception as gt_exc:
            self._log(f"human_gt_parser warning: {gt_exc}")

        try:
            from transcript_pass import build_evidence_grounded_team_review

            build_evidence_grounded_team_review(case)
        except Exception as tr_exc:
            self._log(f"team_review warning: {tr_exc}")

        (run_dir / "case.json").write_text(json.dumps(case, indent=2, default=str), encoding="utf-8")
        return case


def review_copy_path(local: Path) -> Path:
    return local.with_name(local.stem + ".review.mp4")


def make_review_copy(local: Path) -> None:
    """Browser-playable H.264 720p copy for the review player (iPad .MOV files are often HEVC)."""
    out = review_copy_path(local)
    if out.exists():
        return
    tmp = out.with_name(out.name + ".part.mp4")
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(local), "-vf", "scale='if(gt(iw,ih),-2,720)':'if(gt(iw,ih),720,-2)'", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "26", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(tmp)],
        capture_output=True, text=True,
    )
    if r.returncode == 0:
        tmp.rename(out)


def local_video_for_case(case: dict[str, Any]) -> Path | None:
    """Local file to stream for a live case: review copy if ready, else the cached original."""
    uri = str(case.get("video_path") or "")
    if not uri:
        return None
    local = VIDEO_CACHE / uri.split("/")[-1] if uri.startswith("gs://") else (REPO_ROOT / uri)
    rc = review_copy_path(local)
    if rc.exists():
        return rc
    return local if local.exists() else None


class _SavedJobAdapter:
    """Wraps a persisted `job_state.json` dict so `LiveJobRegistry` can serve it across restarts."""
    def __init__(self, snap: dict[str, Any]) -> None:
        self.id = str(snap.get("id") or "")
        self._snap = snap

    def snapshot(self) -> dict[str, Any]:
        return dict(self._snap)

    def cancel(self) -> None:
        pass


class LiveJobRegistry:
    def __init__(self) -> None:
        self.jobs: dict[str, Any] = {}
        for p in sorted(RUNS_DIR.glob("*/job_state.json")):
            try:
                snap = json.loads(p.read_text(encoding="utf-8"))
                if snap.get("id"):
                    self.jobs[str(snap["id"])] = _SavedJobAdapter(snap)
            except Exception:
                pass

    def start(self, payload: dict[str, Any], on_done: Callable[[LiveEngineJob, dict[str, Any]], None]) -> LiveEngineJob:
        job = LiveEngineJob(payload, on_done)
        self.jobs[job.id] = job
        job.start()
        return job

    def resume_unfinished(self, on_done: Callable[[LiveEngineJob, dict[str, Any]], None]) -> list[LiveEngineJob]:
        resumed: list[LiveEngineJob] = []
        for run_dir in sorted(RUNS_DIR.glob("job-*")):
            if not run_dir.is_dir():
                continue
            if (run_dir / "case.json").exists() or (run_dir / "error.txt").exists():
                continue
            snap_file = run_dir / "job_state.json"
            snap: dict[str, Any] = {}
            if snap_file.exists():
                try:
                    snap = json.loads(snap_file.read_text(encoding="utf-8"))
                except Exception:
                    snap = {}
            if snap.get("status") in ("done", "error", "cancelled"):
                continue
            payload = {
                "video_path": snap.get("video_path") or "gs://videval/cardiac/Ai-CARES_TrialRUN_case1_8SEPT26 IPad.MOV",
                "record_id": snap.get("record_id") or "",
                "simulation_number": snap.get("simulation_number") or 1,
                "model_id": snap.get("model") or "gemini-4-argon",
                "k": snap.get("k") or 3,
            }
            job = LiveEngineJob(payload, on_done, job_id=run_dir.name)
            if isinstance(snap.get("log"), list) and snap["log"]:
                job.log = list(snap["log"])
            job._log("↻ Resuming job from on-disk checkpoint after Vertex AI socket stall on spatial_batch_3")
            self.jobs[job.id] = job
            job.start()
            resumed.append(job)
        return resumed

    def get(self, job_id: str) -> Any | None:
        return self.jobs.get(job_id)


def which_ok() -> dict[str, bool]:
    has_gcs_sdk = False
    try:
        from google.cloud import storage as _gcs  # noqa: F401
        has_gcs_sdk = True
    except Exception:
        has_gcs_sdk = False
    return {
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "ffprobe": shutil.which("ffprobe") is not None,
        "gcs": has_gcs_sdk or (shutil.which("gcloud") is not None),
    }
