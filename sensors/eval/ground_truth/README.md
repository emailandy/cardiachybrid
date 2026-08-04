# Ground-Truth Fixtures & Evaluation Standards

This directory documents the schemas, provenance tags, and evaluation rules for sensor ground-truth fixtures (e.g., `fixtures/ground_truth_simvideo2.json`).

## 1. Provenance Classifications (Mandated per Entry)

Every ground-truth item (event, interval, OCR reading, transcription token) **MUST** declare its provenance via the `"provenance"` key:

* **`"acoustic_confirmed"`**: Genuinely external, model-independent physical measurements (e.g., acoustically confirmed defibrillator shocks in audio tracks). Valid for accuracy calibration today (`S02`).
* **`"block_probe_unverified"`**: Probe-derived reference data generated from the same LLM/VLM model and footage (`simvideo2.mp4`). Not human ground truth. Useful for measuring run-to-run drift, determinism, and plausibility, but **unreliable for accuracy calibration** (`Q-017`).
* **`"human"`**: Human-verified ground truth from two independent abstractors with third-rater adjudication (`Q-017`). Required for formal accuracy calibration of motion (`S03`), monitor OCR (`S08`), and any published accuracy claim.

---

## 2. Strict Calibration & Evaluation Rules

1. **Unverified Provenance Refusal**: By default (`allow_unverified=False`), formal evaluation metrics in `sensors/eval/metrics.py` refuse to score against any ground-truth item tagged `"block_probe_unverified"`, `"unverified"`, or `"probe_verified"`. When `allow_unverified=True` is explicitly passed for determinism/plausibility checks, `report.py` prominently labels the scorecard line:
   ```text
   CCI F1: 0.83 (n=1 case, 3 intervals, ALL block_probe_unverified)
   ```
2. **Minimum Case Count (`n >= 5`)**: `sensors/eval/calibrate.py` refuses to execute grid search or threshold tuning against fewer than 5 cases (`len(cases_ground_truth) < 5`), raising a loud exception naming `Q-017`. Grid-searching thresholds against a single case is overfitting with extra steps.
3. **No Hardcoded Thresholds**: All sensor thresholds must live in `sensors/calibration/*.yaml`, keyed by bay or device model.
