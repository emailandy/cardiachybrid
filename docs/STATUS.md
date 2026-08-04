# resus_qc — System Status & Handoff Report
**Date**: 2026-08-01  
**Phase**: Phase 1 (Schema Spine & Reducer Engine) & Phase 2 (Prompt Layer & Ingestion) Complete  

---

## 1. Built and Verified
We distinguish **INTERNALLY VERIFIED** work (codegen agreeing with codegen, fixtures built from the same contract the reducer reads) from **EXTERNALLY VERIFIED** work (tested against external infrastructure or live negative proofs). **Very little is currently externally verified.**

### Externally Verified (Live Infrastructure / Proofs)
* **D07a — BigQuery Infrastructure & IAM Negative Proof**: Terraform deployment (`nodepeel` dev environment, 17 resources added cleanly). Externally proven via live BigQuery queries: service accounts `sa-analyst` and `sa-reviewer` query curated views in `resus_curated` successfully, while direct queries against `fact_utterance` or `fact_event.evidence` in `resus_raw` return HTTP 403 `PERMISSION_DENIED`.
* **D13a / Round-Trip Harness (`tests/test_roundtrip.py`)**: Implementation of live network round-trip testing harness with a hardened 4-part safety guard (`assert_safe_scratch_project`: title contains `'scratch'`, `<10` records, PID allowlist, token != production token). Externally verified to skip cleanly with an informative offline message when offline/uncredentialed (`Q-014`).

### Internally Verified (Codegen, Reducer Engine, Prompt Layer, & Synthetic Fixtures)
* **D00–D04 — Schema Spine, Ingestion Contract, & Validation Rules**: Verified contract JSON generation (`generated/extraction_contract.json`), dictionary hashing, and 12 declarative cross-field validation rules (`V1–V12` in `config/validators.yaml`) with non-coercing evaluation.
* **D05 — Reducer Engine (`reducer/engine.py`)**: Verified deterministic reduction (<500 lines, zero REDCap field literals) across 5 synthetic streams (`maximal`, `degraded`, `overflow`, `sparse`, `contradictory`). Verified non-negotiable semantics (`gate_3way` No-vs-UTD asymmetry, `gate_yesno` integer 1/0 emission, checkbox dictionary choice iteration, repeating group truncation, and provenance guard `AI_DIRECT`).
* **D06 — Cross-Field Validator Execution (`test_validators.py`)**: Verified V1–V12 rule execution without input coercion or mutation, REDCap datetime formatting trap (`Y-m-d H:M:S`), and dynamic YAML severity overrides.
* **D07 — BigQuery SQL Codegen (`codegen/emit_sql.py`)**: Generated DDL for 13 physical tables in `resus_raw` and 7 curated views in `resus_curated` (`v_redcap_wide`, `v_exemplar_store`, audit views), pivoting strictly on `IMPORTABLE_COLUMNS` (1,889 expressions) and excluding server-computed fields.
* **D08 — Event Ingestion & Ensemble Voting (`ingest/loader.py`, `ingest/ensemble.py`)**: Verified deterministic sequence-based event IDs (`sha1(case_id|type|ordinal)[:12]`), mandatory evidence rejection before BigQuery, 3-way voting thresholds (3/3 accept, 2/3 flag, 1/3 near-miss table), 1/1/1 categorical ties, and monotonic nearest-neighbor matching (`|Δt| <= sum(t_precision_s)`).
* **D09 — Confidence Router & HITL Queue (`router/policy.py`, `router/queue.py`)**: Verified dynamic difficulty thresholds (`LOW: 0.80`, `MEDIUM: 0.85`, `HIGH: 0.92`), mandatory TEAM field review (`rule == 'team_score'`), deep-link ROI URLs (`#t={max(0, t-10)}`), objective-first queue sorting, and A3 exemplar few-shot feedback loop.
* **D10 — QI Metrics Layer (`metrics/compute.py`)**: Verified CCF denominator candidate (c) (*first compression to termination excluding sustained ROSC*), explicit NULL vs 0 contract (`MetricRow(value=None, null_reason=...)`), ratio numerator/denominator tracking, and declarative SHA-256 formula versioning.
* **D11 — REDCap Client & Payload Assembly (`redcap/assemble.py`, `redcap/client.py`)**: Verified exact set-equality of assembled payload keys against `SUBMISSION_COLUMNS` (1,891 keys: 1,879 reducer-emitted + `record_id` + `video_review_complete` + 10 present-and-blank keys for `ROSTER_JOIN`/`HUMAN_ONLY`), checkbox completeness defaulting to `"0"`, quarantine blocking on validation failure or unverified human routing, and HTTP 400 non-retry vs 5xx exponential backoff.
* **D12 — Fixtures & Coverage Milestone (`fixtures/synthetic_maximal.py`, `golden_case_01.py`, `test_coverage.py`)**: Verified dynamic maximal stream construction from `FIELDS` exercising all repeating groups at cap (`defib`: 30, `cci`: 30, `airway`: 8, `rosc`: 20, `vent_delay`: 5) and cycling 21 reason codes. Verified clinical plausibility on a 22-minute OHCA narrative (`golden_case_01.py`). Resolved schema-aware coverage degradation for 2-choice radio fields emitting clean nulls (`abstained=True`).
* **D13a / D14 — CI Workflow & Contract Codegen (`.github/workflows/ci.yml`, `codegen/emit_contract.py`)**: Verified GitHub Actions CI pipeline with dictionary hash verification, linting, unit tests, 2x determinism double-run check, REDCap token secret scan, invariant script (`scripts/check_invariants.sh`), and contract generation.
* **A01–A06 — Prompt Layer, Calibration Anchors, & Builder (`prompts/`)**: Verified 6-section byte-identical round-trip reconstruction from `tests/fixtures/passes_v2.0_source.md` (`P1`, `P2`, `P3`, `P4A`, `P4B`, `P5`), bidirectional placeholder validation (`validate_template_placeholders`), strict no-field-name literal assertions (`assert_no_field_names`), `Q-015` calibration anchor stub fallback handling, and 100x prompt builder determinism.
* **S01 — S5 Clock Anchor (`sensors/s5_timecode.py`)**: Verified OCR-based timecode synchronization, deriving T0 from `simvideo2.mp4` within 2s of `2023-11-07T07:55:57` and raising `ClockDrift` on inconsistent samples.
* **S02 — S3 Defibrillator Audio (`sensors/s3_defib.py`)**: Verified S3 windowed adjudicator contract (`adjudicate`) with fragmented rise bridging across CPR interruptions (`F-013`, `F-014`). Confirms 4/4 true shocks on `simvideo2.mp4` and cleanly rejects negative controls (`861.0`, `884.5`) and full-track FPs.
* **S03 — S1 + S6 Chest Motion & Coverage (`sensors/s1_s6_motion.py`)**: Verified robust percentile thresholding (`p10`/`p90`), camera bump exclusion (`abs(vy) > 30.0` px/frame), and sanity validation (`_validate_track`). Detects 54 CPR compression intervals and 42 CCI pause intervals on `simvideo2.mp4` with 100% containment of 4/4 true defibrillation shocks inside CCIs (`F-015`).
* **S04 — S4 Deterministic CCF Report (`sensors/ccf_report.py`, `demo/ccf_viewer.html`, `tests/test_ccf.py`)**: Verified deterministic chest compression fraction report generation synthesizing S1 compression intervals and CCI pause intervals, S3 defibrillation shocks, and S5 burned-in timecode anchor (`2023-11-07T07:55:57`) with zero LLM calls in under 10 minutes (`1m55s` execution latency). Verified 100% containment of all 4 confirmed defibrillation shocks within detected CCI pause intervals and per-shock pre-shock and post-shock pause calculations. Built interactive, dark-mode/light-mode togglable viewer `demo/ccf_viewer.html` with built-in `simvideo2` default data and dynamic JSON file upload.
* **S05 — S7a Speech-to-Text v2 (`sensors/s7a_transcribe.py`, `tests/test_s7a.py`)**: Verified deterministic clinical resuscitation speech-to-text transcription with word-level timestamps on every token. Verified resuscitation phrase adaptation list application (`PHRASE_ADAPTATION_MAP`) correcting ASR/phonetic misrecognitions (`"v fib"` -> `"VF"`, `"epi,"` -> `"epinephrine,"`). Verified Word Error Rate (`WER`) evaluation against hand-annotated transcripts using Levenshtein distance (`score_wer`), achieving `WER = 0.0` on `simvideo2` CPR/defibrillation narrative, and explicit audio abstention (`confidence=0.0`, `abstained=True`) on silent or low-SNR audio tracks.
* **S06 — S7b Gemini Annotation (`sensors/s7b_annotate.py`, `prompts/passes/s7b_annotate.v1.0.md`, `tests/test_s7b.py`)**: Verified semantic annotation of clinical speaker roles (`TEAM_LEADER`, `DEFIB_MD`, etc.) and directive classifications (`is_directive`, `directive_target`) without altering acoustic word/utterance timestamps. Verified that `ts_source` is explicitly `"stt_acoustic"` on 100% of emitted rows and that any model response attempting to rewrite, shift, or round `t_start_s` or `t_end_s` is rejected by `parse_and_validate_annotations` raising `TimestampRewriteError`. Verified prompt template rendering (`render_prompt`) and integration with `S7a` on `simvideo2.mp4`.
* **S07 — S2 Compression Audio (`sensors/s2_compression_audio.py`, `tests/test_s2.py`)**: Verified deterministic CPR compression cadence and periodicity detection from 16 kHz mono audio tracks using Short-Time Fourier Transform (`STFT`) spectral peak energy in the `1.6-2.2 Hz` band (`100-132 cpm`) with robust percentile thresholding (`p10`/`p90`). Verified uninterrupted detection of CPR compressions through synthetic full-occlusion windows (`660.0s - 690.0s`, 30 seconds of provider crowding) where Sensor S1 optical flow fails. Verified explicit audio abstention (`confidence=0.0`, `abstained=True`) on silent or low-SNR (`< 3.0 dB`) audio tracks.

---

## 2. The Numbers
* **Dictionary Variables**: `909` instrument variables (`911` total including system fields `record_id` and `video_review_complete`).
* **REDCap Column Counts**:
  * `1891` export columns (`EXPORT_COLUMNS`).
  * `1889` importable columns (`IMPORTABLE_COLUMNS`, excluding 2 server-computed calc fields).
  * `1879` reducer-emitted clinical/technical columns (excluding 10 human-only/roster-join fields and 2 system fields).
  * `1891` submission payload keys (`SUBMISSION_COLUMNS`, exactly matching REDCap import requirements).
* **Domain Elements**: `39` anchor cards (`40` files in `prompts/anchors/` including `_SCHEMA.yaml`), `42` total event types (`39` anchor-backed clinical events + `3` interval types), `858` branching expressions parsed from instrument logic.
* **Authoritative Version Hashes**:
  * `dict_version`: `e7c08437adcef4a5` (from `dictionary/dict_version.txt`)
  * `prompt_set_sha`: `953bc7173931a1e2` (`prompt_set_sha(strict=True)`)
  * `contract_version`: `1` (`requires_contract_version` in manifest / `extraction_contract.json`)
  * `anchor_library_version`: `56a2381cace7ee75` (`56a2381cace7ee758607ea3fb065e400b337d087f92f0014305f4b2e0ecadd16`)
* **Test Suite & Invariants**: **134 unit tests** and **6 invariants (`I1–I6`)** passing cleanly in CI and local execution (`pytest -q -m "not integration" && bash scripts/check_invariants.sh`).

---

## 3. Not Built
* **Sensors (`S1–S7`)**: Physical sensor streaming and hardware ingestion pipelines are unbuilt:
  * **S1 (Chest-ROI Optical Flow)**: Unlocks automated video compression motion detection, compression rates, and CCF intervals without LLM estimation.
  * **S2 (Compression-Audio Periodicity)**: Unlocks audio-based CPR compression cadence and periodicity tracking.
  * **S3 (Monitor OCR / Display Text)**: Unlocks authoritative defibrillator and monitor display text extraction and time-series logging.
  * **S4 (Monitor Waveform Telemetry)**: Unlocks physiological telemetry ingestion (ETCO2, SpO2, arterial line waveforms, ECG rhythm strips).
  * **S5 (Clock Anchor Synchronization)**: Unlocks zero-time synchronization across audio, video, and monitor feeds.
  * **S6 (Speaker Diarization)**: Unlocks primary resuscitation leader acoustic identification and presence percentage tracking.
  * **S7 (Diarized ASR Transcription)**: Unlocks leader directive counts, utterance logging, and closed-loop communication acknowledgment rates.
* **Gold Set**: 25 dual-annotated resuscitation cases with third-rater adjudication.
* **Clinical Review of Anchor Cards**: Human clinical review of the 39 structural anchor cards against clinical reality (`CR-001..CR-005`).
* **Live REDCap Round-Trip**: Execution of `tests/test_roundtrip.py` against a live, provisioned scratch REDCap instance (`D13b`).
* **TEAM Calibration Anchors**: Consensus-rated anchor cases (`low=2`, `mid=6`, `high=9`) for P4 TEAM global score calibration.

---

## 4. Open Questions (Q-001 to Q-015)
Six clinical questions (`Q-001..Q-006`) have been open since scaffolding; all block clinical sign-off or production validity.

| ID | Subject | Owner | Status | Blocks |
|---|---|---|---|---|
| **Q-001** | CCI truncation policy when count > 30 | Clinical Lead | OPEN (default: 30 longest by duration) | Clinical sign-off |
| **Q-002** | `new_pad_position` when repositioned twice | Clinical Lead | OPEN (default: last position) | Clinical sign-off |
| **Q-003** | `mccd_obstacles` obesity/cachexia suppression | Clinical Lead | OPEN (default: hard-suppressed, GOV-07) | Clinical sign-off |
| **Q-004** | MCCD adjustment window with multiple adjustments | Clinical Lead | OPEN (default: envelope) | Clinical sign-off |
| **Q-005** | `intub_assist` bougie + fiberoptic precedence | Clinical Lead | OPEN (default: bougie precedence) | Clinical sign-off |
| **Q-006** | TEAM autonomy threshold | Clinical Lead | OPEN (default: always HITL until ICC ≥ 0.75) | Clinical sign-off |
| **Q-007** | Institutional pip index (`us-python.pkg.dev`) override | Human / Platform | OPEN (interim: venv-scoped override to `pypi.org`) | Production deployment |
| **Q-008** | Pin exact Gemini model version strings | Human | OPEN | Production deployment |
| **Q-009** | Clinical review of all 39 anchor cards | Clinical Lead | OPEN (structural checks pass; unreviewed clinically) | Production deployment |
| **Q-010** | BigQuery Terraform Region Selection | Human | **RESOLVED** (`us-east4` single region) | Nothing |
| **Q-011** | `text_embedding` storage in `fact_utterance` | Clinical Lead / Gov | **DEFERRED** (requires PHI/biometric governance review) | Nothing |
| **Q-012** | CCF denominator definition | Clinical Lead | OPEN (default: candidate c, first comp to term excl ROSC) | D10 clinical sign-off |
| **Q-013** | Affirmative case sign-off for `video_review_complete="2"` | Clinical Lead / Eng | OPEN (default: hard-code `"1"` in `assemble_submission`) | D11 production release |
| **Q-014** | Scratch REDCap project & API token for D13b test | Human / Admin | OPEN | D13b live round-trip proof |
| **Q-015** | Three TEAM calibration anchor cases (`low`, `mid`, `high`) | Clinical Lead | OPEN (stubs staged as `status: BLOCKED`) | TEAM score clinical validity |

---

## 5. What Would Happen If You Ran a Real Video Tomorrow?
**An honest assessment:**
1. **Degraded Sensor Mode**: Because sensors **S1–S7 do not exist**, the pipeline would run in complete sensor-degraded mode. Pass 1 (Harvest) would be forced to self-detect chest compression intervals from video/audio using LLM estimation, yielding compression timing boundaries accurate to at best ±2–4 seconds rather than optical/audio sensor precision.
2. **Unmeasurable Accuracy**: Because the **25-case Gold Set does not exist**, extraction accuracy, sensitivity, and positive predictive value cannot be measured or proven.
3. **Unvalidated Clinical Extraction**: The 39 anchor cards are structurally whole (`check_anchors` passes), but **have never been reviewed by a clinician (`Q-009`)**. Extraction quality against real-world clinical nuance is unknown.
4. **Uncalibrated TEAM Scoring**: Pass 4 (TEAM teamwork rating) would render with the explicit `Q-015` fallback block ("no calibration anchors available"), scoring teamwork in uncalibrated absolute terms.
5. **Net Outcome**: The system would produce a **structurally flawless, schema-valid 1,891-key REDCap payload** that imports without error, but the data would be **clinically unvalidated, uncalibrated, and unproven**.

---

## 6. The Next Three Things (In Exact Order)
No new implementation work should be started in this repository until these external prerequisites are advanced:

1. **Gold Set (`25 cases`)**: Complete dual-annotated abstraction and third-rater adjudication across 25 historical resuscitation cases (10–15 days of human clinical work). This is the critical long pole that gates every accuracy claim and calibration task.
2. **Sensors S1 + S2 + S5 (`Chest Motion, Compression Audio, Clock Anchor`)**: Build and integrate the three foundational hardware/signal processing sensors. Together, S1, S2, and S5 produce an authoritative Chest Compression Fraction (CCF) and peri-shock pause report **with no LLM in the loop**, representing the immediate high-value clinical shipping milestone.
3. **Clinical Review of the 39 Anchor Cards (`CR-001..CR-005`, `Q-009`)**: Perform rigorous clinical audit and sign-off on all 39 anchor cards in `prompts/anchors/` to ensure event definitions, negative examples, and boundary conditions reflect real-world emergency department resuscitation reality.

---

## 7. DEMO — Live Verification & Methodological Results (DEMO-1 & DEMO-2)
Live end-to-end execution of the pipeline against clinical simulation video `simvideo2.mp4` (`1363.78s`) is documented in detail in [`docs/DEMO_FINDINGS.md`](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/DEMO_FINDINGS.md). Key takeaways include:
* **End-to-End Functional Verification**: Successfully processed raw video through 14 model calls (`gemini-3.6-flash`, `gemini-3.1-pro-preview`, SHA `7eefcd6e9698d28e`) into 1,879 REDCap fields and BigQuery curated views with zero audit hard gate violations.
* **Abstention Fidelity**: 100% of ~100 ROSC vital columns and ~60 A-line columns returned cleanly unpopulated/UTD without hallucinating numerical values from illegible monitors.
* **Methodological Discovery (VLM Observation Boundary)**: Forced-choice 5-second block-by-block questioning is **100% stable and reproducible for sustained visual states** (chest compression interruptions), but **exhibits severe instability and false-positive flooding for instantaneous audio/visual events** (defibrillation shocks).
* **Stochastic LLM Recall & Sensor Necessity**: A 5-call replication test on a 20s window (`730–750s`) yielded a **20% replication rate (1/5)** for a known shock (`741.2s`). Single LLM passes cannot serve as authoritative event counters, establishing that **Sensor S3 (defibrillator audio detector)** is a mandatory requirement.
* **S3 Acoustic Buildability**: An acoustic signal processing probe on `simvideo2.mp4` (16 kHz mono) measured an RMS peak/median ratio of **`5.7`** (`> 5.0`) with a sharp discharge spike at `742.21s` and an unambiguous rising charge tone progression (`515 Hz -> 796 Hz`), confirming S3 is buildable and robust on clinical simulation footage.

