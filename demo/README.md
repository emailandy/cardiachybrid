# resus_qc DEMO-3 Part 1: Offline Viewer Shell & Data Contract

This folder contains the self-contained, offline-compatible HTML/CSS/JS viewer shell and assembly script for **DEMO-3**.

---

## 1. Files
* `viewer.html`: Single, self-contained HTML/CSS/JS file with zero framework dependencies, zero build step, and zero CDN links. Can be opened from a USB stick in a conference room without wifi.
* `prepare_demo.py`: Python script that assembles `case.json` by merging `run_01` and `run_02` artifacts, replication experiment data, and acoustic probe findings into the strict JSON data contract.
* `README.md`: This document.

---

## 2. Generating `case.json`
Run the assembly script from the repository root:
```bash
source .venv/bin/activate
PYTHONPATH=. python3 demo/prepare_demo.py
```
This produces `demo/case.json` (~1.99 MB) containing both pipeline runs, their 1,879 REDCap fields, acoustic transient telemetry, and the 5-call replication experiment.

---

## 3. Opening Offline (Chrome & Safari)
1. Open `demo/viewer.html` directly in **Google Chrome** or **Apple Safari** using File -> Open File (or dragging `viewer.html` into the browser window).
2. If your browser permits local same-directory `file://` fetch, `case.json` loads automatically.
3. If browser security restrictions block `file://` fetch, use the **Select case.json** button in the center banner to pick `demo/case.json` from disk. It will load and render instantly offline.

---

## 4. Invariant Compliance (I2)
`viewer.html` strictly complies with **I2** (Zero REDCap field name literals in code). Every field's label, section, export column, and state is read dynamically from `case.json`. To verify that zero REDCap export column strings exist in the HTML/JS:
```bash
python3 -c "
from generated.redcap_fields import EXPORT_COLUMNS
html = open('demo/viewer.html', 'r', encoding='utf-8').read()
hits = [col for col in EXPORT_COLUMNS if col in html]
```
This confirms strict I2 compliance.

---

## 5. Scripted Traceability Walkthrough: Epinephrine IV Push ("Epi in.")
For a clinician-facing demonstration of end-to-end data provenance from REDCap form fields back to raw video audio/speech evidence, use the following scripted moment:
1. **Target Field**: `time_epi_ed_v2` (Time of first epinephrine administration in the ED).
2. **Extracted Value**: `187.0` seconds (`03:07` video offset).
3. **Source Event ID**: `medication_administration@187.0`.
4. **Verbatim Evidence Quote**: `"Epi in."` (spoken by **Nurse**, timestamp `187.0s`, modality: `speech`, description: `"Epinephrine IV push confirmed."`).
5. **Deep-Link Video Offset**: `#t=177.0` (`max(0, 187.0 - 10)` — opening 10 seconds before the injection utterance so the reviewing clinician observes the medication preparation and hears the confirmation).

---

## 6. Handout Notes & Key Arguments for Clinicians (DEMO-3 Part 4 & F-012)

### A. Stochastic LLM vs. Deterministic Acoustic Signal Processing (Sensor S3)
In the 5-call replication experiment over the exact same 20-second window (`730–750s`) around a confirmed defibrillation shock (`742.21s`):
* **Language Model (`gemini-3.6-flash`, 5 attempts)**: 1 hit (20% replication rate).
* **Acoustic Detector (Sensor S3, 5 runs)**: 5 hits (100% precision, 100% recall).

> **Core Handout Takeaway**: The detector is 60 lines of signal processing. It found the charge tone rising 515→796 Hz over three seconds, then a transient at 5.7× background. It costs nothing per case and returns the same answer every time.

### B. The Act-2 Moment: White UTD Rows & Cause-Based Abstention (F-012)
When inspecting unpopulated clinical fields ("White UTD Rows"), notice that under our rigorous cause-based abstention rules, fields that abstain without explicit model error strings or existing channel coverage degradation resolve to `"no evidence observed"`. Because Sensor S6 (the dedicated camera and monitor occlusion/coverage sensor) is unbuilt at this stage of the system, the demo makes this architectural transparency explicit:

> **Scripted Clinician Explanation**: *"Sixty-three fields say 'unable to determine.' Forty-seven of them say only that — no evidence observed. The system knows it didn't see something; it doesn't yet know why, because the coverage sensor isn't built. When it is, each of those rows will name a channel and a timestamp range you can check against the video yourself."*
