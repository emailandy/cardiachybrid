# docs/HANDOFF_READINESS_ASSESSMENT.md — Air-Gapped Clinician Handoff Readiness Assessment

> **EXECUTIVE CONCLUSION**: The `resus_qc` sensor pipeline is **NOT HANDOFF-READY** for unmonitored execution by clinicians on 25 real resuscitation cases. 
> 
> **CRITICAL DEPENDENCIES ON CLINICAL INQUIRIES & DEPLOYMENT POLICY (T1)**:
> 1. **Gating Timecode Query Q1 (`Q-020`)**: The assessment's conclusion that the repository has even one working sensor is **strictly conditional on Q1** (*Do bay cameras burn timestamps into video frames?*). If **NO**, Sensor S5 cannot run, leaving **ZERO working sensors validated against an independent source on real footage**.
> 2. **Delivery Blocked on Dependency Procurement (Q-007 / T1)**: The development environment runs Python 3.14.2, OpenCV 5.0, NumPy 2.5.1, SciPy 1.18.0. Delivering an air-gapped container image or offline wheelhouse to standard hospital Linux workstations (RHEL/Ubuntu with Python 3.9–3.11 and zero internet access) is **blocked on resolving Q-007 (pip index override and target wheel procurement)**. This is a procurement/policy blocker, not an engineering issue.
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

### Summary Counts (Q2 Corrected):
- **Total Parameter Sets Evaluated**: 12
- **Self-Detecting / Fail-Loud / Abstaining (Type a)**: **5 (41.7%)** (4 S1 Stage-1 parameter sets + S3 uncalibrated profile gate)
- **Silent Wrong Answers (Type b)**: **7 (58.3% of threshold sets)**:
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
| **Dependency / Environment Drift (Q1)** | Repository is running on Python 3.14.2 (`numpy==2.5.1`, `scipy==1.18.0`, `opencv-python-headless==5.0.0.93`). Version skew across Python 3.11–3.14 or BLAS/LAPACK builds will drift boundary centiseconds silently without crashing. | **Fail-Loud on crash; Silent Drift on version skew**. | Add strict pip pin file (`requirements-frozen.txt`) with exact Python version assertion inside `python -m resus_qc.self_test`. |
| **Unsupported Video Codec (HEVC/H.265, ProRes, VFR)** | `cv2.VideoCapture.isOpened()` returns `False` $\to$ raises `RuntimeError("Failed to open video file")`. If container opens but frames decode black $\to$ raises `NoPeriodicMotion`. | **Fail-Loud**. | Add explicit pre-flight codec inspection via `ffprobe` verifying container compatibility and constant frame rate (CFR). |
| **Timecode Overlay Absent or Shifted (Q1 / Q-020)** | S5 OCR template matching returns `None` on all frames $\to$ `t0_iso` set to `None` $\to$ report prints `T0 Clock Anchor: None (source: unavailable)`. | **Silent Degradation**: Absolute clock synchronization collapses; relative offsets continue without clock validation. | Require explicit operator confirmation of $T_0$ if S5 returns `None`. |
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

## N6. Bleeding-Edge Stack & Hospital Delivery Feasibility Assessment (R1)

### 1. The Installation Risk
The development environment is running on a bleeding-edge toolchain:
- **Python**: `3.14.2`
- **OpenCV**: `opencv-python-headless 5.0.0.93`
- **NumPy**: `2.5.1`
- **SciPy**: `1.18.0`

Hospital IT environments typically deploy Enterprise Linux (RHEL 8/9) or Ubuntu LTS (20.04/22.04) workstations locked to system Python versions (**3.9 – 3.11**), with zero root permissions and **strictly zero outbound Internet access** to PyPI. 

This presents a critical handoff barrier: **the current development environment cannot be directly `pip install`ed on clinical machines**.

### 2. Code Compatibility & OpenCV 4.x vs 5.x Assessment
- **Minimum Python Version**: The codebase requires **Python 3.10+** (due to union type syntax `X | Y` across dataclasses and standard library typing features). It cannot run on Python 3.9 without backwards-compatibility imports (`from __future__ import annotations` is present, but runtime type evaluations require $\ge 3.10$).
- **OpenCV API Usage**:
  * S1 optical flow relies on: `cv2.VideoCapture`, `cv2.CAP_PROP_FPS`, `cv2.CAP_PROP_FRAME_COUNT`, `cv2.cvtColor`, `cv2.COLOR_BGR2GRAY`, and `cv2.calcOpticalFlowFarneback`.
  * S5 OCR relies on: `cv2.imread`, `cv2.IMREAD_GRAYSCALE`, and `cv2.matchTemplate(..., cv2.TM_CCOEFF_NORMED)`.
  * **Result**: None of these calls are OpenCV 5-exclusive; all exist identically across OpenCV 3.x, 4.x, and 5.x.
- **Numerical Drift in Farnebäck Optical Flow**:
  * While the API is identical across OpenCV versions, C++ implementation details, SIMD vectorization (AVX2 vs AVX-512 vs Apple Silicon NEON), and underlying BLAS libraries differ across architectures and compiler flags.
  * Containers encapsulate userspace binaries, but OpenCV and BLAS dispatch dynamically to host CPU vector extensions at runtime. Consequently, **containers do NOT guarantee bit-identical floating-point results across different host CPU architectures** (e.g. development on `darwin-arm64` vs hospital deployment on `linux-x86_64`).
  * Farnebäck optical flow velocities ($v_y$) can drift by $10^{-4}$ to $10^{-3}\text{ px}$. 

### 3. Cross-Architecture Manifest Strategy & Derived Tolerance Specifications (T2)
If a raw byte-hash manifest is generated on a development machine (`darwin-arm64`) and checked strictly on a hospital workstation (`linux-x86_64`), bit-level floating-point checksums will fail 100% of the time, permanently halting the pipeline on arrival.

#### Manifest Options Evaluated:
1. **Option 1: In-Container Reference Generation on Target Hardware (First-Run Step)**: The delivered container generates the synthetic video and computes its baseline hashes locally on the target hardware during first-run initialization. *Drawback*: Verifies internal reproducibility, but cannot detect hardware-specific numerical drift against the development baseline.
2. **Option 2: Per-Architecture Manifests**: Ship separate signed manifests for `darwin-arm64`, `linux-x86_64-avx2`, and `linux-x86_64-avx512`. *Drawback*: Requires maintaining a matrix of hardware build targets.
3. **Option 3: Derived Analytical Tolerance Specifications on Clinical Metrics (Recommended)**: Replace raw floating-point array byte hashing with mathematically derived tolerance checks:
   * **Timecode OCR**: Exact string equality (`YYYY-MM-DDTHH:MM:SS`, zero tolerance).
   * **Synthetic Cadence / Dominant Peak Frequency**: Compared **exactly by discrete FFT bin index ($k_{\text{peak}} = \text{argmax}$)** with zero bin tolerance. (Derivation: For a $16.0\text{ fps}$ signal with $N=1024$ FFT window, discrete bin resolution is $\Delta f = \frac{f_s}{N} = \frac{16.0}{1024} = 0.015625\text{ Hz} \approx 0.9375\text{ CPM}$. Because the discrete peak quantizes strictly to integer bins, cross-platform error is either exactly 0 or $\ge 1$ full bin; continuous frequency bands narrower than $\Delta f$ are invalid).
   * **Synthetic Optical Flow Velocity $v_y$**: Marked **`UNDERIVED`** ($\pm 1.0 \times 10^{-3}\text{ px}$ provisional). *Required Experiment*: Run Farnebäck optical flow across 1,000 synthetic frame pairs rendered at $16.0\text{ fps}$ on both ARM64 NEON and x86_64 AVX2/AVX-512 architectures, and measure $\max |v_y^{\text{ARM}} - v_y^{\text{x86}}|$.
   * **Synthetic CCF**: $\pm 0.00104$ (Derivation: The synthetic reference video is specified at **$16.0\text{ fps}$** to match the validated video stream and exercise the identical 25-frame `rms_window_s` integer rounding path [preventing F-021 bypass]. Over a synthetic duration of $T_{\text{synth}} = 60.0\text{s}$ [$960\text{ frames}$], a 1-frame boundary shift $\Delta t = 1/16 = 0.0625\text{s}$ produces a CCF change of $\Delta \text{CCF} = \frac{0.0625\text{s}}{60.0\text{s}} \approx \mathbf{0.00104}$).

#### The Vulnerability Tolerance Bands Cannot Protect:
Even with tolerance specifications on synthetic self-tests, **threshold-adjacent clinical outputs** on real footage remain vulnerable to $10^{-4}\text{ px}$ floating-point drift:
1. `min_modulation: 0.010 px` (S1 Stage 1 active motion gate).
2. `rms_threshold: 0.25` (S1 Stage 2 pause segmentation).
3. Mode classifier cadence standard deviation gates (`3.0 CPM` mechanical / `8.0 CPM` manual).
On borderline cases, a sub-millipixel shift flips frame classifications across thresholds, causing pause splits or boundary changes on real patients.

### 4. Air-Gapped Hospital Delivery Options & Dependency Resolution (T1)

| Delivery Mode | Mechanism | Air-Gap Viability | Feasibility Assessment |
| :--- | :--- | :--- | :--- |
| **Option A: Outbound `pip install`** | Clinician runs `pip install -r requirements.txt` on hospital network. | **ZERO (Infeasible)** | Blocked by hospital firewall and lack of outbound internet access. |
| **Option B: Standalone OCI Container Image** | Docker / Podman / Apptainer / Singularity tarball containing Linux userspace, Python $\ge 3.10$, pinned OpenCV, NumPy, and code. | **HIGH (Recommended)** | **Survives air-gapped networks**. Single signed image transferred via secure USB; eliminates host package skew. |
| **Option C: Pinned Offline Wheelhouse** | Pre-downloaded `.whl` bundle (`manylinux_2_28_x86_64`) installed via `pip install --no-index --find-links=wheels/`. | **MEDIUM (Fallback)** | Survives air-gap, but requires matching host Python minor version ($\ge 3.10$) and compatible host C-libraries (glibc). |

**Dependency Procurement Status (Q-007 / T1)**:
- Verified that `manylinux_2_28_x86_64` wheels for `opencv-python-headless 5.0.0.93` and `numpy 2.4.6` resolve and download directly on the current index.
- However, wheels for Python 3.11 with `<5.0` are absent, and building a fully pinned offline delivery image remains gated on formal resolution of `Q-007` (pip index policy and target wheel procurement).

---

## Synthesis & Actionable Roadmap

The pipeline cannot be handed off for unassisted clinical execution in its current state. Before any implementation begins, **Questions Q1 and Q2 must be answered by the clinical team**. If confirmed feasible, the following engineering gates must be executed:

1. **Gate 1: Synthetic Video Self-Test (`resus_qc.self_test`)**: Ship a self-test harness with a 16.0 fps synthetically rendered reference video ($60.0\text{s}$) and derived analytical tolerance checks (Timecode exact, FFT bin index exact, CCF $\pm 0.00104$) to verify end-to-end decoding, optical flow, OCR, and report determinism locally on the clinical machine without PHI.
2. **Gate 2: Containerized / Offline Delivery Package**: Build an air-gapped container image (or offline wheelhouse) pinning Python $\ge 3.10$, OpenCV, and SciPy to eliminate host dependency skew (blocked on Q-007).
3. **Gate 3: Camera ROI Calibration Tool**: Build an interactive or coordinate-validated ROI onboarding script to prevent running hardcoded manikin ROIs on real patient beds.
4. **Gate 4: Telemetry Export Package (`telemetry.json`)**: Implement automated serialization of PHI-free confidence distributions, mode classifier variance logs, duration histograms, and abstention tables for remote diagnosis.
5. **Gate 5: Timecode Ingestion Fallback**: Implement container-level presentation timestamp (PTS) decoding and manual $T_0$ operator entry to decouple the pipeline from burned-in CCTV text overlays.
