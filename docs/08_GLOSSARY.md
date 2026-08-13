# Resuscitation Quality Improvement Pipeline — Clinical & Technical Glossary

This glossary provides authoritative clinical resuscitation definitions and system software architecture terminology used throughout the `resus_qc` documentation and codebase.

---

## 1. Clinical Resuscitation Terminology

* **A-Line (Arterial Line)**: An invasive hemodynamic catheter inserted into an artery to provide continuous beat-to-beat systolic (`SBP`) and diastolic (`DBP`) blood pressure monitoring (`aline_sbp_cci_*`).
* **CCF (Chest Compression Fraction)**: The proportion of resuscitation time during which active cardiopulmonary resuscitation (`CPR`) chest compressions are performed. Calculated from first compression to termination/sustained ROSC (`D10`, Q-012).
* **CCI (Chest Compression Interruption)**: Any pause or cessation of CPR chest compressions (`compression_interruption`). Classified by primary reason in `cci_reason` (`airway_placement`, `rhythm_determination`, `defibrillation`, `pulse_check`, `chest_us`, `us_pulse`, `stretcher_transfer`, etc.).
* **Defibrillation Shock**: An electrical discharge delivered by a defibrillator to terminate a shockable cardiac arrhythmia (`VF/pVT`, `num_times_defib_ed_v2`).
* **ETCO2 (End-Tidal Carbon Dioxide)**: The non-invasive partial pressure or concentration of carbon dioxide at the end of an exhaled breath, used to monitor CPR quality and detect ROSC.
* **IHCA (In-Hospital Cardiac Arrest)**: A cardiopulmonary arrest occurring inside the hospital facility.
* **MCCD (Mechanical Chest Compression Device)**: An automated mechanical device (e.g., LUCAS, AutoPulse) that delivers continuous, regulated chest compressions (`mccd_applied_ems_v2`).
* **OHCA (Out-of-Hospital Cardiac Arrest)**: A cardiopulmonary arrest occurring outside the hospital before ED arrival.
* **PEA / Asystole**: Non-shockable cardiac arrest rhythms: Pulseless Electrical Activity (`PEA`) and cardiac standstill (`Asystole`).
* **Peri-Shock Pause**: The CPR chest compression pause duration occurring immediately before (pre-shock) and immediately after (post-shock) a defibrillation discharge (`D10`).
* **ROSC (Return of Spontaneous Circulation)**: Resumption of sustained, independent cardiac circulatory function and palpable pulse (`any_episodes_rosc_ed_v2`).
* **SpO2 (Pulse Oximetry Saturation)**: Non-invasive estimation of arterial blood oxygen saturation.
* **VF / pVT (Ventricular Fibrillation / Pulseless VT)**: Shockable cardiac arrest rhythms characterized by disorganized, lethal ventricular electrical activity.

---

## 2. System Software & Architectural Terminology

* **Anchor Card**: A structured YAML document in `prompts/anchors/` (39 required cards) that defines a clinical event or hint, providing positive and negative boundary examples for LLM prompt injection ([A03](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/A03.md)).
* **Confidence Router (`D09`)**: The analytical policy engine (`router/policy.py`) that evaluates extracted field confidence against declared difficulty thresholds (`HIGH: 0.92`, `MEDIUM: 0.85`, `LOW: 0.80`), routing low-confidence or subjective fields to human review ([D09](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D09.md)).
* **Constitution (`prompts/system/constitution.v2.0.md`)**: The invariant system prompt prepended to every LLM extraction pass, enforcing universal rules like `t_precision_s >= 2.0s` in degraded mode (`F-004`) and negative controls (`defib_charge_aborted`, `F-009`).
* **`dict_version` (`e7c08437adcef4a5`)**: The 16-character hexadecimal SHA-256 checksum of the REDCap data dictionary (`dictionary/instrument.csv`), verified at runtime (`I1`).
* **`EXPORT_COLUMNS` (`1,891 columns`)**: The complete set of columns in a REDCap wide export table (`v_redcap_wide`), including 1,889 importable dictionary columns and 2 server-computed calculation fields (`dur_mccd_app_ed_secs_v2`, `duration_ventilator_place_v2`).
* **FieldState (`fact_redcap_field.state`)**: The four-state extraction contract enum: `AUTO_ACCEPTED`, `ROUTED` (HITL review), `UNABLE_TO_DETERMINE` (`utd`, clinical abstention), and `NOT_APPLICABLE` (inactive branch/repeat slot).
* **FieldValue**: The immutable data container emitted by the Reducer Engine (`reducer/engine.py`) for every field, encapsulating `field_name`, `value`, `confidence`, `state`, `abstained`, and `abstain_reason`.
* **HITL Review Queue**: The human-in-the-loop review queue where low-confidence extractions, subjective TEAM ratings (`Q-006`), and UTD anomalies are surfaced to clinical abstractors ([D09](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D09.md)).
* **`IMPORTABLE_COLUMNS` (`1,889 columns`)**: All REDCap dictionary columns that can be imported via API (`not server_computed`), excluding calculation fields.
* **`prompt_set_sha` (`12280b94c0c134e8`)**: The deterministic 16-character SHA-256 hash across all five prompt templates (`P1–P5`) and the Constitution, locking prompt reproducibility ([A01](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/A01.md)).
* **Reducer Engine (`D05`)**: The deterministic execution engine (`reducer/engine.py`) that evaluates branching logic without `eval()`, unrolls repeating groups, and emits 1,879 export columns per case ([D05](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D05.md)).
* **`resus_raw` / `resus_curated`**: The strict BigQuery dataset boundary isolating raw Protected Health Information (`PHI`: `fact_event`, `fact_utterance`) from anonymized analytical views (`v_redcap_wide`, [D07](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D07.md)).
* **`SUBMISSION_COLUMNS` (`1,891 keys`)**: The complete set of JSON keys submitted in a REDCap API import payload (`IMPORTABLE_COLUMNS` + `record_id` + `video_review_complete`, [D11](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D11.md)).
* **Union-of-k / Ensemble Voting (`D08`)**: The multi-draw event harvesting architecture where candidate event windows are merged across `k` independent LLM draws (`Union-of-k` for recall) and confirmed by deterministic acoustic/motion sensors for precision (`F-008`).

---
Last verified: 2026-08-13 against dict_version e7c08437adcef4a5, prompt_set_sha 2b6988545630a115
