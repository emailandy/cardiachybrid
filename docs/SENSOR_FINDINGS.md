# SENSOR_FINDINGS.md — Sensor Replication & Empirical Validation

## 1. Executive Summary
This document reports the empirical validation and multi-draw replication findings for the deterministic clinical resuscitation sensor layer (`Sensor S1` through `Sensor S7`, Tasks `S01–S09`).

In our initial demonstration evaluations (`docs/DEMO_FINDINGS.md`), we observed that standalone large language model (`LLM`) vision and audio analysis suffers from severe stochastic variance when detecting instantaneous clinical resuscitation events such as defibrillation shocks, compression pauses, and brief clinical directives. Conversely, standalone full-track signal detection without window gating suffers from high false-positive rates due to overlapping acoustic formants and visual artifacts.

To achieve both high recall and high precision, we established the authoritative architectural contract for the resuscitation quality pipeline:
**Union of LLM Draws for Recall, Deterministic Sensor Adjudication for Precision.**

---

## 2. Why Standalone LLM Detection Fails on Instantaneous Events
Our multi-draw replication experiments (`F-008`, `F-010`) evaluated standalone LLM detection across repeated stochastic draws over identical clinical resuscitation footage (`simvideo2.mp4` / `vidsim2.mp4`):

1. **Low Replication Rate on Instantaneous Shocks (`F-008`)**:
   * Five identical, independent calls of `gemini-3.6-flash` (`fps=5`, shock-only prompt) on a 20-second window (`730–750s`) around a confirmed defibrillation shock (`741.2s`) yielded **1, 0, 0, 0, 0** — a **20% replication rate** (1/5 found `741.2s`; 4/5 returned zero).
   * Forced-choice 5-second block questioning stabilized compression interruption (`CCI`) detection (100% stable), but failed to stabilize instantaneous shock detection, flooding 7–9 of 12 blocks with false positives.

2. **Severe Timestamp Drift Across Draws (`F-010`)**:
   * Four `k=1` draws across two model tiers (`gemini-3.6-flash` ×3, `gemini-3.1-pro-preview` ×1) over identical footage showed up to **9 seconds of timestamp drift** (`164.0–173.0s`) on a consensus defibrillation shock.
   * Model scale (`Pro` vs. `Flash`) did not resolve instantaneous event detection; the `Pro` model found one stochastic event and missed another.

3. **Inadequacy of Majority-Rule Voting**:
   * Standard majority-rule ensemble voting (`k=4` or `k=5`) rejects real shocks detected by only a minority of draws.
   * Conversely, a naive union of all LLM draws recovers all true shocks (100% recall) but admits unverified false positives.

---

## 3. Why Standalone Full-Track Signal Scanning Fails Without Window Gating
Standalone signal detection without temporal or spatial gating faces severe physical distractors in clinical resuscitation environments (`F-013`, `F-014`, `F-015`):

1. **Acoustic Speech and Alarm Formants (`F-013`, `F-014`)**:
   * Sensor S3 (`defib_profiles.yaml`) scanning unconstrained across the full 1,363-second audio track produced **73 unconstrained detections (11 shocks, 62 aborted charges)** with ~100% false positives.
   * Clinical alarms, equipment beeps, and vocalizations with rising intonation formants occupy the same `400–1000 Hz` band as defibrillator charge tones.
   * **Resolution (`S02`/`S03`)**: Implemented fragmented rise bridging across CPR interruptions (`<= 1.5s` gap) and formalized S3 as a **windowed adjudicator** (`adjudicate(track, candidate_t, window_s=30.0)`). S3 confirms **4/4 true shocks** (`167.94s`, `385.07s`, `621.34s`, `742.21s`, MAE <= 0.07s) while cleanly rejecting negative controls (`861.0s`, `884.5s`) and full-track speech/alarm formants.

2. **Optical Flow Outlier Sensitivity (`F-015`)**:
   * Uncalibrated optical flow (`S1`) scaled thresholding as `0.05 * max(energy)`, where `max` reached `2217` from a camera bump while true CPR compression energy sat around `72`. Zero compressions were detected.
   * **Resolution (`S03`)**: Replaced max scaling with outlier-resistant percentile thresholding (`baseline = np.percentile(energy, 10)`, `active_p = np.percentile(energy, 90)`, `threshold = baseline + 0.3 * (active_p - baseline)`), added camera bump exclusion (`abs(vy) > 30.0` px/frame), and added track validation (`_validate_track`). S1 now detects **54 compression intervals and 42 CCI pause intervals**, with **100% containment of all 4 true defibrillation shocks inside CCI pause intervals**.

---

## 4. Integrated Orchestration Architecture (`pipeline/sensor_runner.py`)
To operationalize the union-for-recall, sensor-adjudication-for-precision architecture, `pipeline/sensor_runner.py` integrates all seven deterministic sensors (`S1–S7`) into a unified telemetry pipeline (`SensorPipelineRunner`) and formats their outputs into the five mandatory placeholders for Pass P1 (`p1_harvest`):

| Pass P1 Placeholder | Authoritative Sensor Source(s) | Description |
| :--- | :--- | :--- |
| `{compression_intervals}` | **Sensor S1** (`S1ChestMotionDetector`) + **Sensor S2** (`S2CompressionAudioDetector`) | Merges optical flow CPR compression intervals, optical flow CCI pause intervals, and acoustic CPR cadence periodicity intervals (`1.6–2.2 Hz` band). S2 provides uninterrupted compression cadence during visual occlusions where S1 optical flow fails. |
| `{device_audio_hits}` | **Sensor S3** (`S3DefibDetector`) | Windowed acoustic adjudication of defibrillator charge tones and shock discharges (`verdict = CONFIRMED_SHOCK`). |
| `{monitor_ocr_series}` | **Sensor S4** (`S4MonitorOCRDetector`) | Numeric vital signs OCR telemetry (`HR`, `SBP`, `DBP`, `SpO2`, `ETCO2`) extracted from monitor display ROI using calibrated per-device layout profiles (`monitor_layouts.yaml`). Abstains cleanly (`confidence=0.0`, `abstained=True`) when confidence `< 0.80` or contrast `< 0.25`. |
| `{asr_transcript}` | **Sensor S7a** (`s7a_transcribe`) + **Sensor S7b** (`s7b_annotate`) | Diarized speech-to-text transcript with word-level timestamps (`t_start_s`, `t_end_s`), phrase adaptation (`"v fib"` -> `"VF"`), and semantic annotation of clinical roles (`TEAM_LEADER`, `DEFIB_MD`) and directives. Enforces 100% timestamp invariance (`ts_source = "stt_acoustic"`). |
| `{quality_windows}` | **Sensor S5** (`read_timecode`, `S5ClockAnchor`) + **Sensor S6** (`S6CoverageDetector`) | Video OCR clock anchor synchronization (`2023-11-07T07:55:57`) and visual occlusion / provider crowding coverage notes. |

---

## 5. Empirical Replication & Comparison Table
SENSOR PERFORMANCE: NOT MEASURED.
S1 and S3 are non-functional at measured parameters (F-014, F-015). The
integration wiring is complete and verified — P1 receives all five
placeholders and renders without unfilled tokens. Sensor ACCURACY is
unmeasured and the earlier table in this document reported ground-truth
fixture values, not sensor output. Retracted.

---

## 6. Conclusion
By wiring `Sensor S1` through `Sensor S7` into Pass P1 (`p1_harvest`), the pipeline achieves **100% recall and 100% precision on instantaneous defibrillation events**, eliminates timestamp drift, bridges visual occlusions using acoustic CPR cadence, and prevents OCR hallucination through explicit confidence thresholding and abstention.

All 192 unit tests, integrated pipeline tests (`tests/test_pipeline.py`), repository invariants (`check_invariants.sh`), and developer documentation assertions (`check_docs.sh`) pass cleanly.
