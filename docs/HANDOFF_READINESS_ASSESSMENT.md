# docs/HANDOFF_READINESS_ASSESSMENT.md — Air-Gapped Clinician Handoff Readiness Assessment

> **EXECUTIVE CONCLUSION**: The `resus_qc` sensor pipeline is **NOT HANDOFF-READY** for unmonitored execution by clinicians on 25 real resuscitation cases. 
> 
> **CRITICAL DEPENDENCY ON CLINICAL INQUIRY Q1**: The assessment's conclusion that the repository has even one working sensor is **strictly conditional on Q1** (`OPEN_QUESTIONS.md` `Q-020`): *Do the resuscitation bay cameras burn a timestamp into the video image?*
> - **If NO**: Sensor S5 cannot run at all. S5 is currently the repository's **only sensor validated against an independent ground truth source** ($100\%$ accuracy on `simvideo2`). If the bay cameras do not burn timestamps into video frames, the pipeline has **ZERO sensors validated against an independent source on real footage**.
> 
> Under the deployment constraint—where the pipeline executes locally in an air-gapped hospital environment on real Protected Health Information (PHI) without engineering access to video, audio, or transcripts—the existing debug loop disappears. Of 12 calibrated threshold sets across the sensor layer, **7 fail silently (Type b, 58.3%)** without self-detecting violation; uncalibrated camera ROIs will produce confident erroneous measurements rather than failing loudly; and the self-test requires a synthetic video harness to verify decoding and geometry without PHI.

---

## N0. Report Face Banner & Clinician Readership Scope Audit

In response to the N0 defect, the clinician-facing banner in `sensors/ccf_report.py` and all text outputs have been audited to ensure no simulation measurement is presented as a property of the case being evaluated:

```
================================================================================
NOT FOR CLINICAL OR PERFORMANCE ASSESSMENT.
In the single manikin validation case, interval precision was 0.36 and the longest
interruption was not detected. Accuracy on this case is unmeasured.
================================================================================
```

### Audit of Report Face Numbers & Gating Discipline (P1):
1. **Banner Scoping**: Explicitly attributes precision (`0.36`) and longest-interruption omission to the single manikin validation case (`simvideo2`).
2. **Elimination of `case_id` Comparison Gating (P1 / Invariant I3)**:
   - All `if self.case_id == "simvideo2"` string comparisons have been **permanently deleted from report generation logic**.
   - Ground truth error decompositions and validation statements are gated **strictly on whether ground truth was supplied** (`if ground_truth is not None and self.ccf_window_s is not None`).
   - Running a case named `"simvideo2"` without ground truth produces the unvalidated report and never leaks simulation decompositions (verified in `tests/test_ccf.py`).
3. **Unvalidated Mode**: When evaluating clinical cases without ground truth, the report emits:
   `Validation Status: Accuracy not validated for this case (no ground truth supplied).`

---

## N1. Remote Diagnostics: PHI-Free Telemetry vs. Remote Untriagable Blindspots

Because real resuscitation footage contains Protected Health Information (PHI)—including patient faces, identifiable staff voices, medical record numbers, and clinical dialogues—clinicians cannot return video files, frame crops, raw audio, or transcribed speech.

### 1. Enumerable Returnable Telemetry (100% PHI-Free)
The pipeline must serialize a structured JSON diagnostics bundle (`telemetry.json`) alongside the report. Each field below is aggregate numeric metadata containing zero identifiable information:

| Telemetry Item | Representation & Schema | Diagnostic Purpose | PHI Status |
| :--- | :--- | :--- | :--- |
| **Sensor Confidence Distributions** | Float summary: `min`, `p25`, `median`, `mean`, `p75`, `max`, `std`, and 5-bin histogram counts. | Identifies global signal degradation, low contrast, or poor SNR across a case. | **CLEAN** (pure statistics) |
| **Abstention Counts & Reasons** | String enum map with integer counts (e.g. `{'epoch_too_short': 4, 'cadence_out_of_bounds': 1}`). | Tracks where mode classifier or S3 refused to evaluate without crashing. | **CLEAN** (static enum strings) |
| **Interval Duration Histograms** | Bin counts across duration buckets: `<1.0s`, `1.0–3.0s`, `3.0–5.0s`, `5.0–10.0s`, `10.0–30.0s`, `>30.0s`. | Detects anomalous pause fragmentation (excessive short slivers) vs expected clinical pauses. | **CLEAN** (aggregate time bins) |
| **Calibration Surface Report** | Loaded profile name, full parameter dict, and SHA-256 hash of `roi_config.yaml` / `defib_profiles.yaml`. | Proves whether the correct camera/device profile was loaded. | **CLEAN** (static configuration) |
| **Mode Classifier Variance Log** | Array of numeric tuples per bout: `(t_start_rel_s, dur_s, median_cpm, min_sub_std_cpm, overall_std_cpm, mode)`. | Diagnoses why compressions were classified as manual vs mechanical. | **CLEAN** (relative seconds & CPM) |
| **Consumer Tier Counts & CCF Ratios** | Counts: `n_raw`, `n_ccf_tier` ($\ge 1\text{s}$), `n_redcap_tier` ($\ge 3\text{s}$), `n_reporting_tier` ($\ge 5\text{s}$), `cpr_active_s`, `ccf_denom_s`, `ccf_percent`. | Tracks interval filtering and active compression fraction. | **CLEAN** (aggregate counts/ratios) |
| **Video Stream Geometry** | Video duration (s), container frame count, detected FPS, frame dimensions ($W \times H$). | Identifies non-standard camera aspect ratios or frame rate mismatches. | **CLEAN** (technical metadata) |

*Note on Timestamps*: All timestamps in `telemetry.json` must be relative seconds from video start ($t=0.0\text{s}$). Burned-in clock ISO strings (e.g. `2023-11-07T07:55:57`) must NOT be exported in remote telemetry if the video timestamp reflects real patient clinical date/time.

---

### 2. What CANNOT Be Diagnosed From Numbers Alone (The Blindspots)
Even with a complete telemetry payload, the following failure mechanisms are **fundamentally invisible** from numeric telemetry without inspecting raw video/audio:

1. **Visual Occlusion vs. Real Clinical Rhythm Checks**:
   - Both events produce temporal difference bounding spikes (`roi_diff >= 20.0 px`) and internal stillness (`< 1.5 px`). In telemetry, a 10-second dropout looks identical whether clinicians were leaning over the patient to palpate a femoral pulse (true pause) or standing in front of the camera adjusting IV lines (occlusion).
2. **Optical Flow Boundary Truncation**:
   - When S1 starts late or ends early (e.g. GT #1 truncated $8.0\text{s} \to 4.62\text{s}$), telemetry records a single valid pause of $4.62\text{s}$. Without video frames or ground truth, an engineer cannot determine whether the true pause was 4.6s or 8.0s.
3. **Unexplained Optical Flow Pause Fragmentation**:
   - Long pauses splitting into slivers (e.g. GT #7 30s pause splitting into four 1–3s fragments with zero S6 visual occlusion). Telemetry shows four short pauses; nobody can determine remotely why optical flow detected motion during true stillness.
4. **Camera Jitter, Bed Nudges, and Room Vibration**:
   - Physical movement of the camera mount or patient bed creates vertical optical velocity $v_y$. The pipeline interprets this as active chest compressions, falsely inflating CCF.
5. **Acoustic Masking of Defibrillator Tones**:
   - If an uncalibrated defibrillator emits a charge tone that is drowned out by suction machines or room shouting, acoustic energy features will report no tone. Telemetry cannot distinguish "device did not charge" from "device charged but acoustic SNR was -12 dB".
6. **Novel Camera Angles & Resuscitation Bay Geometry**:
   - If a bay camera is mounted at a shallow $30^\circ$ angle or $5\text{ meters}$ away, pixel stroke displacements drop by $70\%$. Optical flow modulation collapses below `min_modulation` ($0.010$), causing the detector to abort or under-segment without any indication that camera distance was the cause.

---

## N2. Known-Answer Self-Test & Verifiable Artifact Distribution

### 1. The Requirement for a Known-Answer Self-Test (P2)
On an air-gapped clinical machine, environmental discrepancies (OS differences, OpenCV backend builds, NumPy BLAS/LAPACK floating-point rounding, corrupted configuration files) can silently alter detection boundaries.

Furthermore, **bypassing video decoding with pre-extracted numpy arrays alone does not test the failure modes most likely to occur in the field** (unsupported codecs, variable frame rate decoding, presentation timestamp drift, or incorrect pixel color conversions).

### 2. Two-Layer Self-Test Architecture (P2 Proposal)
To exercise the full execution stack without transmitting PHI:

1. **Layer 1: Deterministic Synthetically Generated Reference Video (`generate_synthetic_selftest_video.py`)**:
   - A committed, deterministic Python script generates a purely synthetic video fixture (`synthetic_reference.mp4`):
     * A rendered geometric rectangle oscillating vertically at an exact 102 CPM cadence ($1.7\text{ Hz}$) with calibrated pixel displacement.
     * Controlled pauses of known durations (e.g. exactly 8.0s, 15.0s, 30.0s).
     * A synthetic burned-in clock overlay in the upper-left S5 ROI (`2026-01-01 12:00:00.000`).
   - **Zero PHI**: Contains no patient, staff, hospital, or bay images.
   - **Full-Stack Execution**: Exercises `cv2.VideoCapture decode → container FPS read → ROI cropping → optical flow → S1 segmentation → S5 OCR → CCF computation → report generation` to a known, exact mathematical answer.
2. **Layer 2: Intermediate Numeric Arrays (`.npy` / `.npz`)**:
   - Pre-extracted numeric arrays (`synthetic_vy.npy`, `synthetic_stft.npy`) isolate floating-point numerical drift from video decoding drift.

### 3. PHI Assessment of Timecode Crops
- **Risk**: Any `timecode_crops.npz` extracted from real patient video or simulation video contains actual date/time stamps and camera DVR branding that is potentially identifying.
- **Rule**: Any artifact extracted from clinical video must undergo institutional PHI review and de-identification approval. A purely synthetically rendered video and OCR crop set avoids this legal barrier entirely.

---

## N3. Threshold Autonomy & Silent Failure Inventory

Every calibrated parameter in `roi_config.yaml` was evaluated against its failure behavior. Thresholds are categorized into:
- **(a) Self-Detecting / Fail-Loud / Abstaining**: Sensor detects that signal parameters violate calibration assumptions and raises an exception or explicitly abstains.
- **(b) Silent Wrong Answer**: Sensor executes without error, produces high-confidence output, and emits an incorrect clinical measurement.

### Comprehensive Threshold Taxonomy:

| Sensor / Module | Parameter Name | Calibrated Value | Failure Category | Mechanism & Clinical Impact |
| :--- | :--- | :--- | :--- | :--- |
| **S1 Stage 1** | `vy_bandpass_min_hz` / `max_hz` | 1.3 – 3.0 Hz (78–180 CPM) | **(a) Fail-Loud** | If compression rate is outside band, in-band FFT power collapses $\to$ raises `NoPeriodicMotion`. |
| **S1 Stage 1** | `min_band_power_ratio` / `min_peak_snr` | 0.15 / 10.0 | **(a) Fail-Loud** | If motion is broadband noise rather than rhythmic CPR, peak SNR drops $\to$ raises `NoPeriodicMotion`. |
| **S1 Stage 1** | `min_modulation` | 0.010 px | **(a) Fail-Loud** | If ROI is placed on empty bed or static tissue, $(p_{90} - p_{10}) < 0.010 \to$ raises `NoPeriodicMotion`. |
| **S1 Stage 1** | Active Track Fraction Gate | 0.05 – 0.98 | **(a) Fail-Loud** | If active CPR fraction over $\ge 60\text{s}$ is $< 5\%$ or $> 98\%$, raises `SensorFailure`. |
| **S1 Mode** | `mechanical_cadence_max_std_cpm` | 3.0 CPM | **(b) SILENT WRONG** | Steady manual CPR on real patients ($\text{std} = 2.8\text{ CPM}$) is silently classified as `mechanical` with 0.88 confidence. |
| **S1 Mode** | `manual_cadence_min_std_cpm` | 8.0 CPM | **(b) SILENT WRONG** | Mechanical CPR with slight strap slippage ($\text{std} = 4.5\text{ CPM}$) or manual CPR with moderate rhythm ($\text{std} = 5.5\text{ CPM}$) silently abstains as `unable_to_determine`. |
| **S1 Stage 2** | `rms_window_s` | 1.6 s | **(b) SILENT WRONG** | On slow manual CPR (< 70 CPM), 1.6s spans < 2 strokes, causing zero-crossing power drops that fragment continuous CPR into false pauses. |
| **S1 Stage 2** | `gap_merge_duration_s` | 0.5 s | **(b) SILENT WRONG** | Any true clinical pause $< 0.5\text{s}$ is merged into adjacent compressions and erased silently; dropouts of 0.52s create artificial splits. |
| **S1 Tier 1** | `min_pause_duration_s` (CCF tier) | 1.0 s | **(b) SILENT WRONG** | True pauses between 0.5s and 1.0s are silently excluded from the CCF pause sum without warning. |
| **S1 Tier 3** | `cci_reporting_floor_s` (Reporting tier) | 5.0 s | **(b) SILENT WRONG** | True pauses $< 5.0\text{s}$ (or pauses truncated to $< 5.0\text{s}$ by boundary lag, like GT #1) are silently deleted from reported intervals. |
| **S6 Occlusion** | `occlusion_entry_spike_px` / `still_px` | 20.0 px / 1.5 px | **(b) SILENT WRONG** | Clinician leaning over chest for carotid pulse check generates identical signature, causing S6 to falsely label real pauses as visual occlusions. |
| **S3 Defib** | `profile: "default"` / `UNKNOWN` | Uncalibrated | **(a) Fail-Loud / Abstain** | Explicitly emits `adjudication_status="UNAVAILABLE"` and notes "no calibrated profile for this device (Q-019)" (Invariant I5). |

### Summary Counts (P3 Corrected):
- **Total Parameter Sets Evaluated**: 12
- **Self-Detecting / Fail-Loud (Type a)**: 5
- **Self-Detecting Abstention Gate (Type a)**: 1 (S3 device profile)
- **Silent Wrong Answer (Type b)**: **7 (58.3% of threshold sets)**:
  1. Mode classifier mechanical std threshold (`3.0 CPM`)
  2. Mode classifier manual std threshold (`8.0 CPM`)
  3. Rolling RMS envelope window (`1.6s`)
  4. Compression gap merge duration (`0.5s`)
  5. CCF consumer floor (`1.0s`)
  6. Reporting consumer floor (`5.0s`)
  7. S6 temporal occlusion bounding diff spike/stillness pair (`20.0 px / 1.5 px`)

**Critical Defect**: 7 out of 12 parameter sets will execute cleanly and produce plausible-looking but incorrect clinical numbers on real resuscitation footage without raising warnings.

---

## N4. Failure Modes of the Handoff Execution Itself

| Scenario | Behavior on Clinician Workstation | Defect Classification | Recommended Hardening |
| :--- | :--- | :--- | :--- |
| **Dependency / Environment Drift** | If OpenCV, SciPy, or PyTorch versions differ, optical flow or filter rounding drifts by centiseconds; if libraries fail to import, execution aborts. | **Fail-Loud on crash; Silent Drift on version skew**. | Add strict pip pin file (`requirements-frozen.txt`) and mandatory `self_test` pre-run. |
| **Unsupported Video Codec (HEVC/H.265, ProRes, VFR)** | `cv2.VideoCapture.isOpened()` returns `False` $\to$ raises `RuntimeError("Failed to open video file")`. If container opens but frames decode black $\to$ raises `NoPeriodicMotion`. | **Fail-Loud**. | Add explicit pre-flight codec inspection via `ffprobe` verifying container compatibility and constant frame rate (CFR). |
| **Timecode Overlay Absent or Shifted (Q1)** | S5 OCR template matching returns `None` on all frames $\to$ `t0_iso` set to `None` $\to$ report prints `T0 Clock Anchor: None (source: unavailable)`. | **Silent Degradation**: Absolute clock synchronization collapses; relative offsets continue without clock validation. | Require explicit operator confirmation of $T_0$ if S5 returns `None`. |
| **ROI Configuration Mismatch (New Camera / Bay Angle)** | Hardcoded `chest_roi` points to wrong pixel coordinates. If region is static wall $\to$ raises `NoPeriodicMotion`. If region contains moving staff $\to$ **detects false CPR over empty bed**. | **Catastrophic Silent Wrong Answer** if non-patient motion occurs in ROI. | Require interactive or configuration-validated ROI bounding box per camera bay. |
| **Missing Operator Milestones (P4)** | If `death_pronounced_s` is omitted $\to$ CCF is ABSTAINED (`ccf_abstained=True`, Invariant I6). If `patient_enters_room_s` is omitted $\to$ interval reporting is ABSTAINED (`intervals_abstained=True`, P4). | **Fail-Loud / Abstain for both CCF and Interval Reporting** (Defaulting prohibited). | Require explicit operator milestones or abstain from all windowed calculations. |

---

## N5. Input Contract & Sensor S5 Timecode Vulnerability

### 1. Minimum Operator Input Contract
To execute on 25 real clinical cases, the pipeline requires the following explicit input contract per case:

```yaml
case_id: "BAY01_CASE2026_08"
video_path: "/secure/phi/bay01_case08.mp4"
camera_id: "bay01_overhead_dome"
clinical_milestones:
  patient_enters_room_s: 42.50       # MANDATORY for interval reporting (omission forces interval abstention, P4)
  death_pronounced_s: 1145.00        # MANDATORY for CCF calculation (omission forces CCF abstention, I6)
candidate_shocks_s:                  # Optional (omission sets shock status to NO_CANDIDATES)
  - 182.40
  - 410.15
  - 789.00
camera_roi:
  chest_roi: {x: 720, y: 380, width: 220, height: 220}  # MANDATORY per camera/bed position
```

### 2. Absence Paths and Abstention Rules (P4)
- **Missing `death_pronounced_s`**: The pipeline MUST ABSTAIN from computing CCF (`ccf = None`, `ccf_abstained = True`, reason: `"death_pronounced_s milestone not supplied by operator"`, Invariant I6 / `F-026`).
- **Missing `patient_enters_room_s` (P4)**: The pipeline MUST ABSTAIN from interval reporting (`interval_window_s = None`, `intervals_abstained = True`, reason: `"patient_enters_room_s milestone not supplied by operator"`, defaulting to 0.0s prohibited).
- **Missing `candidate_shocks_s`**: The pipeline MUST emit `(No candidate shock timestamps supplied by operator)` and evaluate 0 shocks without attempting full-track audio scanning (Invariant I4 / `F-013`).
- **Missing or Uncalibrated `chest_roi`**: The pipeline MUST NOT fall back to `default` ($600, 400, 720, 480$) or `simvideo2` coordinates. It must raise `ConfigurationError("No camera ROI calibration defined for camera_id")` and halt.

### 3. The Sensor S5 Vulnerability (The Single-Working-Sensor Trap & Q1)
- **The Finding**: Sensor S5 is currently the **only sensor in the repository that achieved $100\%$ validation against external ground truth**.
- **The Trap**: S5 functions strictly by template-matching OCR against burned-in digital clock overlays (`'MM/D/YYYY HH:MM:SS.mmm AM/PM'`) embedded by a specific CCTV DVR in the upper-left corner of `simvideo2.mp4`.
- **The Clinical Reality**: Real hospital resuscitation bay cameras (e.g. Axis, Panasonic, Hanwha IP cameras, or overhead surgical domes) frequently:
  1. Do not burn digital timecode overlays into video pixels at all (relying on RTSP/MP4 container timestamps).
  2. Use different font geometries, anti-aliasing, font sizes, or background contrasts.
  3. Place timestamps in different screen locations (bottom-right, header band, or metadata tracks).
- **Consequence**: When handed to real resuscitation bays, **S5 will immediately fail on cases lacking this exact burned-in overlay**. Without S5, the pipeline has **zero working sensors confirmed against external ground truth**, and all interval measurements degrade to unanchored relative seconds. This makes **Inquiry Q1** the single gating question for the entire sensor deployment strategy.

---

## Synthesis & Actionable Roadmap

The pipeline cannot be handed off for unassisted clinical execution in its current state. Before any implementation begins, **Questions Q1 and Q2 must be answered by the clinical team**. If confirmed feasible, the following engineering gates must be executed:

1. **Gate 1: Synthetic Video Self-Test (`resus_qc.self_test`)**: Ship a self-test harness with a synthetically rendered reference video and intermediate arrays to verify end-to-end decoding, optical flow, OCR, and report determinism locally on the clinical machine without PHI.
2. **Gate 2: Camera ROI Calibration Tool**: Build an interactive or coordinate-validated ROI onboarding script to prevent running hardcoded manikin ROIs on real patient beds.
3. **Gate 3: Telemetry Export Package (`telemetry.json`)**: Implement automated serialization of PHI-free confidence distributions, mode classifier variance logs, duration histograms, and abstention tables for remote diagnosis.
4. **Gate 4: Timecode Ingestion Fallback**: Implement container-level presentation timestamp (PTS) decoding and manual $T_0$ operator entry to decouple the pipeline from burned-in CCTV text overlays.
