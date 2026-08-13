# Open Questions

## CLINICAL — awaiting clinical lead
Q-001 CCI truncation policy when >30 
  - options: TBD 
  - default: 30 longest by duration
  - owner: clinical lead
  - status: OPEN
  - blocks: TBD

Q-002 new_pad_position when repositioned twice 
  - options: TBD
  - default: last
  - owner: clinical lead
  - status: OPEN
  - blocks: TBD

Q-003 mccd_obstacles obesity/cachexia 
  - options: TBD
  - default: hard-suppressed, GOV-07
  - owner: clinical lead
  - status: OPEN
  - blocks: TBD

Q-004 MCCD adjustment window with multiple adjustments 
  - options: TBD
  - default: envelope
  - owner: clinical lead
  - status: OPEN
  - blocks: TBD

Q-005 intub_assist bougie + fiberoptic 
  - options: TBD
  - default: bougie precedence
  - owner: clinical lead
  - status: OPEN
  - blocks: TBD

Q-006 TEAM autonomy threshold 
  - options: TBD
  - default: always human until ICC ≥ 0.75
  - owner: clinical lead
  - status: OPEN
  - blocks: TBD

Q-009 — All 39 anchor cards require clinical review for accuracy before
production use. Structural validation (check_anchors) passes; clinical
validation has not occurred. Blocks: first production run, not development.
Owner: clinical lead.  Status: OPEN.

Q-012 CCF denominator definition
  - options: (a) first compression -> last compression, (b) patient arrival -> termination or ROSC, (c) first compression -> termination, excluding sustained-ROSC periods
  - default: candidate (c) first compression -> termination excluding sustained ROSC (configured in config/metrics.yaml)
  - note: Evaluated across simvideo2, Candidate (b) patient arrival window (36.0-922.0s, denom 886.0s) yields GT CCF 0.9074 vs S1 CCF 0.7919, whereas Candidate (c) first compression window (70.75-922.0s, denom 851.25s) yields GT CCF 0.9037 vs S1 CCF 0.8170. Candidate (c) is the comparable evaluation pair; comparing S1 under Candidate (c) against GT under Candidate (b) represents an invalid cross-window mismatch. Additionally, an early compression motion event occurs at 61.50-67.81s (dur=6.31s, cadence=114.1 cpm); because its duration is shorter than the rolling cadence variance requirement, its mode is classified as unable_to_determine. In code, t_first anchors exclusively to mechanical or manual mode events, bypassing this early 6.31s compression event and establishing t_first at 70.75s—a metrics-layer denominator defect under Q-012 candidate (c).
  - owner: clinical lead
  - status: OPEN
  - blocks: D10 clinical sign-off

Q-013 Case-level affirmative human sign-off for video_review_complete="2"
  - options: (a) infer from field-level human_verified state, (b) gate "2" on an explicit case-level sign-off table (case_signoff with signed_off_by/signed_off_at)
  - default: hard-code "1" (Unverified/Incomplete) in assemble_submission() until affirmative sign-off table is implemented
  - owner: clinical lead / engineering
  - status: OPEN
  - blocks: D11 production release (automated complete marking)

Q-017 — Gold set required for sensor accuracy validation. 25 cases, two independent abstractors, third-rater adjudication. Blocks the accuracy gates on S03 (motion), S08 (monitor OCR), and any published accuracy claim. Does NOT block sensor construction — determinism and plausibility are testable today.
  - owner: clinical lead
  - status: OPEN
  - blocks: S03 accuracy gate, S08 accuracy gate, published accuracy claims
  - timeline: 10-15 days

Q-018 — Calibrated ROI and optical-flow parameters for diverse clinical bay camera layouts. Sensor S1 and S6 thresholds in `roi_config.yaml` are provisional and fitted to simulation bay geometry (`simvideo2.mp4`). Blocks production deployment across heterogeneous emergency department camera installations.
  - owner: clinical lead / engineering
  - status: OPEN
  - blocks: S03 production deployment on uncalibrated bays

## OPERATIONAL — awaiting human
Q-007 — Is the artifact-foundry-prod pip index an institutional control?
Inherited pip config points at
us-python.pkg.dev/artifact-foundry-prod/ah-3p-staging-python, which lacks
setuptools and pytest.
(a) Deliberate supply-chain control → REVERT the venv override; request
    upstream PyPI passthrough or explicit mirroring from the platform team.
(b) Stale/unrelated config → the venv-scoped override is the permanent fix.
Interim: venv-scoped override to pypi.org, repo-local, no global change.
Owner: human / platform team.  Status: OPEN.  Blocks: nothing (workaround
in place), but must be resolved before any production deployment.

Q-008 Pin exact Gemini model version strings before the first production run.
-latest and -preview aliases make historical runs unreproducible.
  - options: specific immutable model snapshots (e.g. pinned snapshot revisions once frozen by GCP)
  - default: None (must be explicitly pinned by human)
  - owner: human
  - status: OPEN (Reopened: Task 4 demonstrated that `gemini-3.1-pro-preview` is an unpinned moving alias and `seed` is inert for multimodal video input on Vertex AI. Without bit-exact reproducibility, every historical scorecard in this repo describes a model state that cannot be re-obtained).
  - blocks: production deployment & reproducible benchmarking

Q-010 BigQuery Terraform Region Selection.
Multi-region US vs single region (e.g. us-east4 for data-residency compliance).
  - options: (a) Multi-region US (cheaper/simpler), (b) Single region e.g. us-east4
  - default: None (must be explicitly chosen by human; no silent default)
  - owner: human
  - status: RESOLVED (SINGLE REGION, us-east4)
  - blocks: nothing

Q-011 text_embedding storage in fact_utterance.
  - status: DEFERRED (not OPEN)
  - note: "Embedding storage deferred to the retrieval layer. When added, requires separate governance review — derived embeddings of clinical audio are PHI and voice embeddings may be biometric identifiers."

Q-014 Scratch REDCap project with video_review instrument and API token required for D13b round-trip verification.
  - status: OPEN
  - note: "Scratch REDCap project with video_review instrument and API token required for D13b round-trip verification. Blocks the definitive coverage proof — all column-count agreement to date is internal to codegen."

Q-015 Three TEAM calibration anchor cases at consensus global 2, 6, 9 require human-rated cases from the gold set.
  - status: OPEN
  - note: "Until then P4 runs uncalibrated. Does not block development — Q-006 routes all TEAM fields to human review regardless — but blocks any claim about TEAM score validity."



## RESOLVED
**T-001 (A01)**: What is the correct value for 'Scope: MODIFY'? (specs.yaml does not determine this).
**T-002 (A01)**: What is the correct value for 'Scope: READ'? (specs.yaml does not determine this).
**T-003 (A01)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-004 (A01)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-005 (A05)**: What is the correct value for 'Scope: MODIFY'? (specs.yaml does not determine this).
**T-006 (A05)**: What is the correct value for 'Scope: READ'? (specs.yaml does not determine this).
**T-007 (A05)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-008 (A05)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-009 (A04)**: What is the correct value for 'Scope: MODIFY'? (specs.yaml does not determine this).
**T-010 (A04)**: What is the correct value for 'Scope: READ'? (specs.yaml does not determine this).
**T-011 (A04)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-012 (A04)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-013 (A03)**: What is the correct value for 'Scope: MODIFY'? (specs.yaml does not determine this).
**T-014 (A03)**: What is the correct value for 'Scope: READ'? (specs.yaml does not determine this).
**T-015 (A03)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-016 (A03)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-017 (A02)**: What is the correct value for 'Scope: MODIFY'? (specs.yaml does not determine this).
**T-018 (A02)**: What is the correct value for 'Scope: READ'? (specs.yaml does not determine this).
**T-019 (A02)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-020 (A02)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-021 (A03b)**: What is the correct value for 'Scope: MODIFY'? (specs.yaml does not determine this).
**T-022 (A03b)**: What is the correct value for 'Scope: READ'? (specs.yaml does not determine this).
**T-023 (A03b)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-024 (A03b)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-025 (A06)**: What is the correct value for 'Scope: MODIFY'? (specs.yaml does not determine this).
**T-026 (A06)**: What is the correct value for 'Scope: READ'? (specs.yaml does not determine this).
**T-027 (A06)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-028 (A06)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-029 (D07a)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-030 (D07a)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-031 (D02)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-032 (D02)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-033 (D12)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-034 (D12)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-035 (D06)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-036 (D06)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-037 (D07)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-038 (D07)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-039 (D03)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-040 (D03)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-041 (D13)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-042 (D13)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-043 (D08)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-044 (D08)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-045 (D09)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-046 (D09)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-047 (D04)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-048 (D04)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-049 (D14)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-050 (D14)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-051 (D10)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-052 (D10)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-053 (D01)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-054 (D01)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-055 (D11)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-056 (D11)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).
**T-057 (D05)**: What is the correct value for 'Self-review Q2'? (specs.yaml does not determine this).
**T-058 (D05)**: What is the correct value for 'Self-review Q3'? (specs.yaml does not determine this).

Q-018 — The ground truth fixture `fixtures/ground_truth_simvideo2.json` contains a `"$schema"` key pointing to the JSON Schema Draft 2020-12 meta-schema (`"https://json-schema.org/draft/2020-12/schema"`). The file contains instance data rather than schema definitions; this key is instance metadata and must not be mistaken for a JSON schema validation contract. Status: DOCUMENTED.

Q-019 — Defibrillator Acoustic Calibration, Simulation Provenance, Ground Truth Announcement Semantics, & Verbal Candidate Source Design.
  - case nature (M0 / M4): `simvideo2.mp4` is CONFIRMED as a manikin simulation for an educational training program; the defibrillator was in a training configuration; the system's intended deployment is real human resuscitation.
  - s3 reclassification (M1): S3 acoustic charge-tone detection is UNTESTED on real charge tones, not failed. Four candidate hypotheses for missing charge tones in reference audio are ranked by empirical evidence:
    1. *Candidate 1 (Hardware / Simulation Mode - Strongest)*: Training-configuration defibrillator never charged high-voltage capacitors or emitted physical acoustic charge tones.
    2. *Candidate 2 (Acoustic Masking & Codec Loss)*: Ambient resuscitation noise ($>-40\text{ dBFS}$) and low-bitrate AAC compression masked weak tonal components below SNR detection thresholds.
    3. *Candidate 3 (DVR Hardware Noise Gating)*: Direct DVR audio analysis (`blankbayvideop1.mp4`) revealed digital noise gating active at $\le -89.8\text{ dBFS}$ with instantaneous attack ($<0.06\text{ ms}$), closing on quiet intervals but opening immediately on signal onset.
    4. *Candidate 4 (Sample-Rate Decimation - Weakest / Disproven)*: Disproven by direct capture analysis showing native DVR audio is identical 16 kHz mono.
  - inquiry to clinical lead (M1): Did the training-configuration defibrillator deliver energy into a test load or did it not charge at all? Status: UNCONFIRMED until answered.
  - shock times are announcement times (M0 / M2): Gold standard `timestamp_s` values are confirmed to be marked from the resuscitation team's verbal call-out, not physical energy delivery.
    * Any peri-shock pause computed against these measures pause-around-announcement, a distinct clinical quantity — flagged to the D10 metrics layer before those fields are populated.
    * The cross-modal spread up to 2.9s noted in the fixture reflects genuine temporal separation between verbal announcement and physical intervention.
    * The four `acoustic_measured` timestamps (167.94s, 385.07s, 621.34s, 742.21s) are manual spectrogram readings of unattributed acoustic transients given no confirmed electrical discharge.
  - inquiry to clinical lead (M2): Should future ground truth fixtures carry distinct fields separating announcement time from physical energy delivery time? Status: UNCONFIRMED until answered.
  - negative control validity (L1 / F-030): S3's negative control at 861.0s and 884.5s returning `(0.0, 0.0)` is a vacuous pass: a detector confirming zero true positives cannot distinguish "correctly rejects negatives" from "rejects everything." A valid negative control requires the detector to first confirm a true positive. Discrimination evidence for the default defib profile is void until direct bay calibration is available.
  - verbal candidate source design (M0 / L5): Verbal announcement is a candidate SOURCE for S3's windowed adjudicator, not a fallback detector.
    * Announcement is intent rather than delivery; shocks are sometimes aborted.
    * Verbal and acoustic timestamps are not interchangeable.
    * A verbally derived shock must occupy a different field from an acoustically confirmed one and must NEVER populate peri-shock pause.
    * Absence of verbal announcement is UNAVAILABLE, not zero shocks (Invariant I5).
    * Blocked on S7a (speech-to-text), currently a shell.
    * Because gold standard shock times were annotated from team verbal call-outs, scoring a speech detector against them constitutes same-modality comparison (F-016 family defect) and must be explicitly declared before reporting accuracy numbers.
    * Trigger phrase vocabulary is a clinical question and must not be engineered without clinical input.
    * Roadmap note: S7a is the precondition for both the shock-candidate channel and the S2 retest (F-023), making it the highest-leverage remaining sensor.
  - adjudicator scalar window asymmetry constraint: `S3DefibDetector.adjudicate(audio_or_video_path, candidate_t, window_s)` accepts only a scalar `window_s`, forcing symmetric half-widths ([t_cand - W/2, t_cand + W/2]), whereas physical charge tone precursors require asymmetric reach (tau_lead >= 6.5s before discharge, tau_trail <= 2.0s post-discharge). S3 fusion gating uses derived scalar window_s = 13.0s (tau_lead = 6.5s) to encompass precursor charging sequences under existing frozen sensor contract.
  - mode classifier calibration-transfer risk (M3): `mechanical_cadence_max_std_cpm` (3.0) and `manual_cadence_min_std_cpm` (8.0) are fitted to a manikin with spring-loaded uniform recoil, short scenario, no provider fatigue, and no chest deformation feedback. The cadence variability gap may narrow or invert on real human compressions. (Cross-reference Q-012 / G3 abstention).
  - roadmap dependency (M5): Gold set expansion (n=25) must include real resuscitation bay footage. A simulation gold set generalises only to simulation. Thresholds validated on simulation must be re-derived against real clinical cases before clinical use. Real bay footage validation is the gating dependency for the entire system.
  - owner: clinical lead / engineering
  - status: BLOCKED on direct bay audio, real footage gold set, & S7a
  - blocks: S02 / S10 per-device acoustic calibration & clinical deployment

Q-020 — Resuscitation Bay Camera Burned-In Timestamp Geometry & Font Format.
  - answer from clinical lead (V1): Real bay footage carries burned-in timestamp in upper-left corner with format `"11/7/2023 08:04:59.748 AM"` (matching S5 template format).
  - technical caveats & vulnerabilities recorded (V1):
    * `P.png` (`P`) is missing from `sensors/calibration/timecode/`; afternoon cases (`PM`) will abstain or mis-match against `A.png`.
    * Hardcoded column offsets in `_TIMECODE_COLS` break on varying digit counts (e.g. 2-digit vs 1-digit month/day) and shifting window layouts.
    * Date order ambiguity: Pixels cannot distinguish `M/D/YYYY` from `D/M/YYYY` for day $\le 12$, risking 12-hour or multi-month chart anchoring errors.
  - owner: clinical lead / engineering
  - status: ANSWERED (with V1 hardening caveats recorded)
  - blocks: S5 template expansion & OCR layout robustness

Q-021 — Real Bay Video Ingestion Verification Clip (Inquiry to Clinician / Codec & Geometry Verification).
  - answer from clinical lead (V5): No dedicated bay clip available; opening 30 seconds of simulation video `simvideo4` contains an empty bay.
  - assessment: `simvideo4` is simulation footage (720p @ 25 fps), not real clinical bay camera footage. It does not establish real bay camera codec, frame rate (CFR vs VFR), resolution, camera angle, or chest ROI geometry. Real bay camera ingestion remains unverified.
  - owner: clinical lead / engineering
  - status: OPEN (Awaiting real hospital bay clip / configuration profile)
  - blocks: Real camera ROI onboarding & container verification

Q-022 — Bay Camera DVR Date Format Standardization & Date Resolution (Patient 2).
  - resolution: RESOLVED. High-resolution glyph audit confirmed that `simvid3.mp4` physically displays `12/8/2023` (day digit `'8'` matches at score $0.8844$ vs `'6'` score $0.6508$). The earlier `12/6` report was an S5 column-misalignment measurement artifact, not a DVR clock fault and not a transcription error. The clinical review sheet (`12/8/2023`) was the correct ground truth source.
  - gold-standard provenance finding: The clinical review sheet dates have proven 100% accurate in both cases where independently checkable (`11/7/2023` on Patient 1; `12/8/2023` on Patient 2).
  - status: RESOLVED
  - date: 2026-08-06

## Clinical Video Retention & Migration (`Q-020`)
* **Retention Policy**: What is the IRB/clinical lead approved retention period for raw clinical video? Currently, the lifecycle block is commented out awaiting confirmation (e.g., delete after 30 days vs retain indefinitely).
* **Legacy Bucket Migration**: Should the existing unmanaged `gs://videval/` bucket be imported into Terraform state, or should its contents be migrated to the new managed `clinical-video` bucket? Who owns this migration?

## Infrastructure Remote State
* **State Management**: Should we enable a remote GCS backend for `terraform.tfstate`? The local-only state introduces a single-machine risk, but a dedicated remote state bucket requires setup.

## REDCap Submission (`Q-014`)
* **Retirement vs Deferral**: Is the `D11` / REDCap payload submission being permanently retired from the architecture, or just deferred? This affects whether `Q-014` stays open, and whether Secret Manager/API connectivity to REDCap will ever need to be provisioned.
