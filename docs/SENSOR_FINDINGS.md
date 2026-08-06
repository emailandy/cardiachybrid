# docs/SENSOR_FINDINGS.md — Comprehensive Sensor Layer Findings (F-013 through F-029)

This standalone technical synthesis consolidates empirical findings, architectural limitations, and negative results established across Phase 3 of the Google Antigravity Resuscitation Quality Case (`resus_qc`) engineering build. All results are measured against human-adjudicated gold standard observations on reference simulation case `simvideo2.mp4` ($n=1$).

---

## 1. What Works

* **Sensor S5 (Timecode OCR Clock Anchor)**:
  * **Status**: Functional, deterministic, and externally validated.
  * **Performance**: Successfully decodes burned-in video timecode overlays via template matching OCR (`sensors/s5_timecode.py`), deriving case zero-anchor $T_0 = \text{2023-11-07T07:55:57}$ with sub-second precision and negligible drift ($\le 0.45\text{s}$ across $10\text{s}$, $300\text{s}$, and $600\text{s}$ samples).
  * **Validation**: It represents the **only sensor confirmed against an independent external source**—the human reviewer's resuscitation clock logs exactly match S5's automated OCR reads at $t=300\text{s}$ ($08:00:57.072 = T_0 + 300\text{s}$).

* **Sensor S1 (Chest-ROI Optical Flow Motion + Three-Tier Consumer Duration Rules)**:
  * **Status**: Functional and deterministic ($100\%$ repeatable across independent runs on current build).
  * **Performance (Current Build under $\pm 3.0\text{s}$ Monotonic Tolerance Matching)**: Captures clinical interruptions with **Interval Recall ($\pm 3.0\text{s}$) = `0.71`** ($5/7$) on un-floored CCF consumer detections ($\ge 1.0\text{s}$) and **`0.57`** ($4/7$) under the calibrated reporting floor ($\ge 5.0\text{s}$). Achieves boundary precision of **$\text{MAE} = 1.02\text{s}$** and active CPR fraction estimation on the active clinical window. (Note: all historical evaluation figures predating F-021 envelope smoothing and three-tier consumer gating are formally superseded by commits `769269f`, `5017dbc`, and `9da9e74`).
  * **The Three-Tier Consumer Architecture & Measurement Decoupling**:
    1. **CCF Computation**: Retains all unoccluded physical pauses $\ge 1.0\text{s}$ (`min_pause_duration_s`), emitting $40$ pause intervals in the clinical window (after filtering out 4 sub-$1.0\text{s}$ de-identification mask splittings from the 44 raw emitted detections).
    2. **REDCap Payload / Repeating Group**: Enforces the dictionary $\ge 3.0\text{s}$ rule required by data specifications (`num_cci_v2`).
    3. **Reporting & UI Summary**: Applies the calibrated reporting floor (`cci_reporting_floor_s: 5.0` in `roi_config.yaml`), eliminating $80\%$ of visual occlusion false positives ($35 \to 7$ under $\pm 3.0\text{s}$ tolerance matching) to insulate human review from transient motion dropouts.
    4. **Architectural Correction on Two Measurements**: Three consumers, three rules, **two measurements** (the interval stream and an independently-derived CPR duration). In `compute_ccf()`, active CPR time is derived independently by summing active compression motion events (`cpr_duration_s = sum(motion_events)`), rather than as `denominator - sum(pause_intervals)`. Across the CCF evaluation window ($70.75\text{–}922.0\text{s}$), total physical non-CPR time derived from `compute_ccf()` is $155.96\text{s}$, whereas emitted pause intervals total $140.00\text{s}$ across 44 raw intervals ($137.82\text{s}$ across 40 CCF intervals $\ge 1.0\text{s}$). The exact $15.96\text{s}$ difference ($155.96\text{s} - 140.00\text{s}$) is accounted for by precisely 18 inter-event gaps where physical non-CPR duration exceeded emitted raw CCIs due to sub-0.5s inter-event dropouts, gap merges (`gap_merge_duration_s = 0.5s`), and optical boundary splittings not emitted as formal pauses.

---

## 2. What Does Not Work, and Why

* **Reporting Floor Recall Loss on GT #1 (`F-027`, Retraction of `F-024`)**:
  * **Status**: Characterized optical flow boundary truncation defect.
  * **Retraction Note**: Earlier reports (`F-024`) incorrectly claimed GT #5 ($607\text{–}617\text{s}$) was lost to the floor. In fact, floored interval #7 ($608.9\text{–}617.2\text{s}$, $\text{dur}=8.4\text{s}$) cleanly matches GT #5 at both boundaries ($\Delta\text{start} = +1.9\text{s}$, $\Delta\text{end} = +0.2\text{s}$). `F-024` is retracted as factually false.
  * **The Finding (`F-027`)**: The true clinical pause lost when applying the $5.0\text{s}$ reporting floor is **GT #1 ($147.0\text{–}155.0\text{s}$, $\text{dur}=8.0\text{s}$)**. S1 optical flow started late at $150.00\text{s}$ and ended early at $154.62\text{s}$, producing a truncated detection of **$4.62\text{s}$** ($< 5.0\text{s}$) with confidence $0.88$. The $\ge 5.0\text{s}$ reporting floor discarded this $4.62\text{s}$ detection, dropping interval recall from $5/7$ (`0.71`) to $4/7$ (`0.57`). The phrase "zero recall cost" is false: the reporting floor costs exactly one true clinical interruption due to optical flow boundary truncation.

* **Total Fragmentation of Longest Clinical Pause GT #7 (`F-028`)**:
  * **Status**: Unexplained optical flow fragmentation defect.
  * **The Finding**: The longest clinical pause in the case—**GT #7 ($844.0\text{–}874.0\text{s}$, $\text{dur}=30.0\text{s}$)**, representing $36.6\%$ of all clinical no-flow time ($30.0\text{s} / 82.0\text{s}$)—was completely missed as a coherent interval. Sensor S1 optical flow fragmented the 30-second pause into four short slivers:
    * $845.66\text{–}846.85\text{s}$ ($\text{dur}=1.19\text{s}$)
    * $853.16\text{–}855.41\text{s}$ ($\text{dur}=2.25\text{s}$)
    * $862.48\text{–}863.73\text{s}$ ($\text{dur}=1.25\text{s}$)
    * $870.91\text{–}874.73\text{s}$ ($\text{dur}=3.82\text{s}$)
  * **Sensor S6 Coverage Verdict**: Sensor S6 was explicitly queried across $844.0\text{–}874.0\text{s}$ and returned **`False` (zero visual occlusion events)** across all four fragments and all gaps between them. The fragmentation mechanism is formally recorded as **unexplained optical flow motion detection failure without detected visual occlusion**. S1 detected only $8.51\text{s}$ of pause time, missing **$71.6\%$ ($21.49\text{s}$)** of the no-flow duration. Because every fragment is $< 5.0\text{s}$, the reporting floor discarded all four fragments, completely omitting GT #7 from reported intervals.

* **Structural Absence of Defibrillation Shock Containment (`F-029`)**:
  * **Status**: Validated mechanical CPR physiology.
  * **The Finding**: In contrast to manual CPR protocols, automated mechanical CPR devices (LUCAS) continue compressions uninterrupted through defibrillation shocks. Across all five confirmed shocks ($165.0\text{s}$, $388.0\text{s}$, $622.0\text{s}$, $742.0\text{s}$, $879.0\text{s}$), **zero shocks fall inside any clinical pause**. Each shock occurs $+10.0\text{s}$, $+17.0\text{s}$, $+5.0\text{s}$, $+6.0\text{s}$, and $+5.0\text{s}$ after the preceding pause ends. Earlier claims of "100% shock containment in CCIs" are structurally invalid for mechanical CPR.

* **Surviving and Unexplained False Positives under Reporting Floor**:
  * Exactly seven false positive interruptions survive the $\ge 5.0\text{s}$ reporting floor under consistent $\pm 3.0\text{s}$ monotonic tolerance matching (or six under any-overlap matching). Evaluated against Sensor S6 visual occlusion tracking, the seven false positives are:
    * **FP #1 ($249.5\text{–}256.4\text{s}$, $\text{dur}=6.9\text{s}$)**: `S6 True` (`provider_crowding` temporal diff spike detected). Physically overlaps true GT pause #2 ($245\text{–}256\text{s}$), but its start time deviates by $+4.5\text{s}$ from GT, failing $\pm 3.0\text{s}$ tolerance matching.
    * **FP #2 ($341.7\text{–}347.1\text{s}$, $\text{dur}=5.4\text{s}$)**: `S6 True` (`provider_crowding` temporal diff spike detected).
    * **FP #3 ($351.8\text{–}357.9\text{s}$, $\text{dur}=6.1\text{s}$)**: `S6 True` (`provider_crowding` temporal diff spike detected).
    * **FP #4 ($509.6\text{–}514.9\text{s}$, $\text{dur}=5.2\text{s}$)**: `S6 True` (`provider_crowding` temporal diff spike detected).
    * **FP #5 ($630.2\text{–}635.5\text{s}$, $\text{dur}=5.3\text{s}$)**: `S6 False` (**unexplained $\ge 5\text{s}$ false positive**; no cause supplied where sensor returned False).
    * **FP #6 ($639.4\text{–}644.7\text{s}$, $\text{dur}=5.2\text{s}$)**: `S6 False` (**unexplained $\ge 5\text{s}$ false positive**; no cause supplied where sensor returned False).
    * **FP #7 ($758.2\text{–}767.0\text{s}$, $\text{dur}=8.8\text{s}$)**: `S6 True` (`provider_crowding` temporal diff spike detected).

* **Sensor S2 (Compression Audio Cadence & Onset Detection) — `F-023`**:
  * **Status**: Architectural shell. Definitive negative methodological result on single-channel room audio.
  * **Envelope Periodicity Failure**: Hilbert amplitude-envelope STFT analysis ($1.3\text{–}3.0\text{ Hz}$) cannot separate metronomic mechanical CPR from ambient room conversation, equipment alarms, and ventilator cycling. Measured across the quietest tertile of S1-confirmed mechanical compressions ($n=755$ STFT frames), the acoustic peak frequency shows an interquartile range (IQR) of **$1.50\text{–}1.95\text{ Hz}$** ($90\text{–}117\text{ CPM}$). Because all seven true clinical pauses exhibit wandering acoustic peaks across **$1.50\text{–}2.40\text{ Hz}$**, the distributions overlap completely. A frequency lock tight enough to protect real pauses ($1.70 \pm 0.08\text{ Hz}$) bridges 0 of 18 visual occlusion windows; widening the tolerance erases real interruptions and collapses clinical recall.
  * **Transient Onset Failure (IOI)**: Evaluating spectral flux Inter-Onset Intervals (IOIs) to track broadband mechanical piston thumps revealed that during rock-steady mechanical compressions (where optical flow proved zero cadence drift over $820\text{s}$), onset intervals show wide, irregular dispersion ($\text{std} = \mathbf{0.137\text{s}}$ against a metronomic target of $< 0.03\text{s}$). This is statistically indistinguishable from ambient noise during true clinical pauses ($\text{std} = \mathbf{0.279\text{s}}$).
  * **Root Cause & Conclusion**: Single-channel acoustic features inevitably track whatever energy is loudest in the passband. During ongoing resuscitation, speech formants and alarms dominate mechanical piston strikes. **Sensor S2 cannot function on single-channel room footage without Sensor S7a speech rejection first.**

* **Sensor S3 (Defibrillator Acoustic Charge & Shock Detector) — `F-013`, `F-014`, `F-015`**:
  * **Status**: Architectural shell / windowed adjudicator only.
  * **Full-Track Failure**: Standalone scanning across full-length audio tracks generates $100\%$ false positive detections due to ambient room speech and equipment alarm harmonics within the $400\text{–}1000\text{ Hz}$ charge passband (`F-013`).
  * **Charge Tone Degradation**: Across the five confirmed defibrillation shocks, only 3 exhibit continuous rising charge tones ($165\text{s}$ at $183\text{ Hz/s}$, $742\text{s}$ at $81\text{–}191\text{ Hz/s}$, degraded at $879\text{s}$ at $29\text{ Hz/s}$); continuous tones are entirely absent preceding shocks at $388\text{s}$ and $622\text{s}$.
  * **Conclusion**: S3 functions reliably only as a targeted windowed adjudicator (`verdict = CONFIRMED_SHOCK`) around candidate timestamps or when coupled with LLM union-for-recall candidate adjudication.

* **Sensor S6 (Visual Occlusion & Provider Crowding Detection) — `F-020`**:
  * **Status**: Functional detector, non-functional arbitration gate.
  * **Temporal vs Spatial Signatures**: Spatial pixel intensity standard deviation ($< 15.0$) failed to detect provider crowding because scrubs and skin retain visual texture. Implementing temporal difference occlusion detection (`roi_diff` bounding spikes $\ge 20\text{ px/frame}$ bounding internal stillness $< 1.5\text{ px}$ while surrounding `room_diff` remains active $> 0.02\text{ px}$) successfully resolved visual occlusions ($251$ events detected).
  * **Arbitration Gate Failure**: However, temporal occlusion detection also triggers during genuine clinical rhythm checks ($6$ of $7$ true pauses overlapped, totaling $20.3\text{s}$ of interference). Why? Because immediately before compressions halt for a pulse check, clinicians lean across the patient to palpate carotid/femoral arteries or inspect pads—producing identical visual bounding spikes and chest stillness as provider crowding. **A gate that fires on both occlusions and genuine pauses cannot serve as an arbitration switch for acoustic fusion without risking pause erasure.**

---

## 3. What We Learned About the Footage

* **`F-017` (Screen Recording & Re-Encoding Artifacts)**:
  * `simvideo2.mp4` is a **screen recording of a computer UI playing CCTV video**, not a direct video capture (`nb_read_frames=21821` vs container rate $16\text{ fps}$).
  * UI presentation freezes and frame duplication induce synthetic vertical velocity variance ($\text{std} \approx 0.252\text{ px/frame}$), while the active chest occupies only a fraction of the frame ($140\times140$ within $1920\times1080$).
  * Additional compression re-encoding steps passed to the audio track plausibly destroyed continuous rising charge tones and acoustic piston strike transients.
  * **Critical Caveat**: Every parameter in this build is calibrated against this screen-recorded stack ($n=1$ case). Direct resuscitation bay cameras are untested and may behave completely differently—particularly regarding acoustic clarity and optical continuity.

* **`F-020` & `F-021` (De-Identification Masks vs RMS Smoothing)**:
  * De-identification blackout masks cover $15.6\text{s}$ ($1.1\%$) of the video and were previously erroneously assumed to cause optical flow fragmentation.
  * **`F-021`**: The true cause of optical flow fragmentation was an instantaneous rolling RMS window computed as `int(fps * 0.1) = 1` frame at $16\text{ fps}$ (no smoothing). Because piston velocity crosses zero twice per cycle at mechanical direction reversal, instantaneous power collapsed $\sim 3.4$ times per second during continuous CPR, splitting an $820\text{s}$ epoch into 40 pieces and starving the mode classifier. Fixed in commit `9da9e74` by requiring windows to span at least two full stroke cycles (`rms_window_s = 1.6`).

---

## 4. The Methodological Result & Silent-Pass Defects

Across this phase of engineering, we discovered **fifteen silent-pass and reporting defects** where code executed without errors, passed automated test suites while failing catastrophically on real clinical data, executed against incorrect analytical boundaries, or masked underlying verification errors:

1. **`F-013` / `F-014`**: Standalone audio scanning claiming functionality on synthetic tests while generating $100\%$ false positive rates on room speech.
2. **`F-015` / `F-016`**: Vacuous self-comparison evaluation fixtures where test predictions and ground truth originated from identical mock objects (`F-016`), artificially inflating reported F1 and WER metrics to `1.0` and `0.0`.
3. **`F-018`**: Zeroing optical flow outlier frames (`vy[abs(vy) > 30] = 0`), which converted impulse noise into step discontinuities that rang through Butterworth filters and flooded frequency spectral power.
4. **`F-019`**: Sliding-window union smearing active compression interval boundaries across real pauses and wiping out short pre-shock interruptions.
5. **`F-021`**: Zero-crossing power collapses caused by integer truncation of rolling RMS windows (`int(fps * 0.1) = 1` frame).
6. **`F-022`**: Uncritically assuming automated CPR requires clinical pauses during defibrillation; mechanically automated compressions (LUCAS) continue uninterrupted through shocks.
7. **Single-Sample Variance Artifacts**: Standard deviation computations over single windows or single STFT frames yielding degenerate `0.000` variance and passing stability floors trivially.
8. **Spatial Intensity Thresholding**: Attempting to detect provider crowding via pixel texture standard deviation ($< 15.0$) rather than temporal difference motion kinetics.
9. **`F-025` / OR-Fusion Over-Detection**: Relying on simple boolean union (`S1 OR S2`) or un-gated envelope energy, where continuous background room noise created an illusion of continuous CPR while erasing $57\%$ of real clinical interruptions.
10. **`F-027` / GT #1 Reporting Floor Recall Cost**: S1 optical flow truncated the true 8.0s pause at $147\text{–}155\text{s}$ into a $4.62\text{s}$ detection, which was discarded by the $\ge 5.0\text{s}$ floor (dropping recall $5/7 \to 4/7$).
11. **`F-028` / GT #7 Pause Fragmentation**: S1 optical flow fragmented the longest 30.0s clinical pause ($844\text{–}874\text{s}$) into 4 sub-$5\text{s}$ slivers ($1.19\text{s}$, $2.25\text{s}$, $1.25\text{s}$, $3.82\text{s}$) without detected S6 visual occlusion, missing $71.6\%$ ($21.49\text{s}$) of no-flow duration.
12. **`F-029` / Shock Containment Inversion**: Assuming defibrillation shocks fall inside pauses during mechanical CPR; in reality, 0 of 5 shocks fall inside pauses (landing 5–17s after pauses end).
13. **`F-026` / Ungated CCF Report Disagreement & Evaluation Window Mismatches**: `test_ccf.py::test_generate_ccf_report_vidsim2` passes cleanly while `ccf_report.py` runs over the full un-truncated video duration ($1,363.78\text{s}$), ungated on `death_pronounced_s` ($922.0\text{s}$) and without consumer floor filtering (`filter_ccis_by_consumer`), directly contradicting Decision 027 / Q-012. A green test running against the wrong window produces **$\text{CCF} = 0.8766$**. Furthermore, when F-026 was originally documented, the evaluation path itself ($0.8170$, computed over $70.75\text{–}922.0\text{s}$) was comparing against GT across mismatched windows ($0.9074$, computed over $36.0\text{–}922.0\text{s}$). Reconciled evaluation to compare S1 ($0.8170$) against the true comparable GT CCF of $0.9037$ over the identical $70.75\text{–}922.0\text{s}$ window. Existing assertions in `test_generate_ccf_report_vidsim2` (`assert report.total_case_duration_s == pytest.approx(1363.78, abs=0.5)` and `assert len(report.cci_intervals) >= 40`) actively encode this ungated behavior and must be updated alongside the fix so a correct failure is not mistaken for a regression.
14. **Silent Error Suppression & Untracked File Persistence**: Suppressing command exit codes with `2>/dev/null || true` led to asserting that `.DS_Store` was untracked when it remained tracked in the index until explicitly removed in D4.
15. **Fabricated Commit Identifiers & Stale Verification Reports**: Reporting a fabricated commit hash (`a858a7732...333`) and re-reporting stale, byte-identical wall-clock test execution results in a closeout verification report rather than inspecting actual git logs and executing genuine verification runs.

**The Transferable Core**: Automated test passage is not scientific validation. The permanent value of this architecture lies in its **fail-loudly discipline**: zero hardcoded literals, strict byte-identical determinism, explicit abstention on degraded channels, data-derived calibration profiles from config files, and the absolute requirement to score against real human ground truth and real terminal output before asserting functional validity.

---

## 5. Summary Scorecard (S1 Standalone on Current Build, `simvideo2.mp4`)

Evaluated against human-adjudicated gold standard observations ($T_0 = \text{2023-11-07T07:55:57}$, $n=1$ case, $7$ true interruptions summing to $82.0\text{s}$, $\text{GT CCF} = 0.9037$ over active CPR window $70.75\text{–}922.0\text{s}$) through reproducible command `python -m sensors.eval.report --sensor s1 --ground-truth fixtures/ground_truth_simvideo2.json --consumer compare`:

| Metric | S1 (>=1.0s CCF consumer) | S1 (>=5.0s Reporting consumer) | Clinical Interpretation & Status |
| :--- | :--- | :--- | :--- |
| **CCI F1 ($\pm 3.0\text{s}$)** | `0.21` | **`0.44`** | Doubled performance by filtering sub-$5\text{s}$ visual provider dropouts. |
| **Interval Precision ($\pm 3.0\text{s}$)** | `0.12` | **`0.36`** | False positives dropped from $35$ to $7$ under monotonic tolerance matching. |
| **Interval Recall ($\pm 3.0\text{s}$)** | `0.71` ($5/7$) | **`0.57`** ($4/7$) | Recall drop ($5 \to 4$) caused by optical flow truncation of GT #1 ($8.0\text{s} \to 4.62\text{s}$) discarded by floor (`F-027`). |
| **False Positives ($\pm 3.0\text{s}$)** | `35` | **`7`** | Consistently defined under $\pm 3.0\text{s}$ tolerance matching ($6$ under any-overlap matching). |
| **CCI F1 ($\pm 2.0\text{s}$)** | `0.13` | **`0.33`** | $\pm 2.0\text{s}$ tolerance is stricter than human clock precision ($\approx \pm 3\text{s}$). |
| **Boundary MAE ($\pm 2.0\text{s}$)** | `1.02s` | **`1.02s`** | Sub-second boundary precision on matched interruptions. |
| **CCF Error (70.75-922s)** | `0.09` | **`0.09`** | Evaluated via `compute_ccf()` as $\text{CPR Duration} / (\text{death\_pronounced\_s} - \text{t\_first}) = 695.29\text{s} / 851.25\text{s} = \mathbf{0.8170}$ (error $\mathbf{0.09}$ vs comparable GT CCF $0.9037$ over identical window $70.75\text{–}922.0\text{s}$). Note: ungated report path produces $\mathbf{0.8766}$ (`F-026`). |
| **Reported Intervals** | $40 \text{ total}$ | **$11 \text{ total}$** | Raw emitted set in interval reporting window ($36\text{–}922\text{s}$) is 44 intervals; CCF tier excludes 4 sub-1.0s mask splittings. |

#### Detailed CCF Window Reconciliation & Decomposition (Four Numbers)
Because `compute_ccf()` bounds calculations per Q-012 default candidate (c) from the first compression event to termination ($70.75\text{–}922.0\text{s}$), whereas the clinical room entry timestamp occurs at $36.0\text{s}$, CCF evaluated across both windows yields four distinct numbers:
1. **Window 1 ($36.0\text{–}922.0\text{s}$, Denominator $886.0\text{s}$ — Patient Enters Room)**:
   - **$\text{GT CCF} = \mathbf{0.9074}$** ($82.0\text{s}$ pause duration).
   - **$\text{S1 CCF} = \mathbf{0.7919}$** ($184.40\text{s}$ total non-CPR time).
2. **Window 2 ($70.75\text{–}922.0\text{s}$, Denominator $851.25\text{s}$ — Active CPR Window per Q-012)**:
   - **$\text{GT CCF} = \mathbf{0.9037}$** ($82.0\text{s}$ pause duration).
   - **$\text{S1 CCF} = \mathbf{0.8170}$** ($155.96\text{s}$ total non-CPR time, derived as $695.29\text{s}$ active CPR motion).
   - **Comparable Pair**: Window 2 ($70.75\text{–}922.0\text{s}$, $\text{GT} = 0.9037$ vs $\text{S1} = 0.8170$) is the accurate, comparable evaluation pair per Q-012 default candidate (c). The resulting CCF error of $0.09$ is produced by **cancelling errors**: S1 accumulates $+55.8\text{s}$ of false positive provider dropouts while simultaneously missing $21.49\text{s}$ of true no-flow duration during GT #7 (`F-028`).

*(Note: All earlier baselines from prior builds are officially superseded by commits `769269f`, `5017dbc`, and `9da9e74` and replaced by this reproducible measurement on current code).*
