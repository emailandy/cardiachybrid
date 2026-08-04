# Resuscitation Quality Improvement Pipeline — Data Model & BigQuery Schema

This specification documents the clinical data dictionary metrics, the six dictionary column counts, physical BigQuery database schema (`resus_raw` and `resus_curated`), the four extraction contract field states, the three legitimate null states, the seven source classes, and the multimodal event stream schema.

---

## 1. The Six Counts and Why They Differ

Every number in this table is derived directly from executable codebase artifacts (`generated/coverage_manifest.json`, `generated.redcap_fields`, and `tests/test_emit_python.py`). These counts differ because repeating clinical instruments are unrolled into flat columns, checkbox fields emit binary indicator columns, and REDCap distinguishes API importable columns from server-computed calculation fields.

| Count | Manifest Key / Symbol | Authority | Clinical & Technical Definition |
| :---: | :--- | :--- | :--- |
| **909** | `n_fields` | `len(FIELDS)` | **Defined Dictionary Instrument Fields**: The distinct conceptual clinical data variables defined in the research dictionary (`instrument.csv`), excluding REDCap system fields. |
| **911** | `n_variables` | `len(specs) + 2` | **Total REDCap Instrument Variables**: The 909 dictionary fields plus 2 REDCap system fields (`record_id` and `video_review_complete`). |
| **1,879** | `len(EXPORT_COLUMNS)` (Reducer) | `reduce_stream()` | **Reducer-Emitted Export Columns**: The exact number of field columns emitted by the Reducer Engine (`D05`) on a maximal case. This expands from 909 because repeating instruments (`defib`: 30, `cci`: 30, `airway`: 8, `rosc`: 20, `vent_delay`: 5) are unrolled across their maximum capacity, and checkbox fields emit individual `___code` binary columns. It excludes `record_id`, `video_review_complete`, and 10 present-and-blank `ROSTER_JOIN` / `HUMAN_ONLY` keys. |
| **1,889** | `DICT_IMPORTABLE_COLUMNS` | `IMPORTABLE_COLUMNS` | **API Importable Dictionary Columns**: All REDCap wide export table expressions that can be imported via API (`not server_computed`), excluding 2 server-computed calculation fields (`dur_mccd_app_ed_secs_v2` and `duration_ventilator_place_v2`). |
| **1,891** | `DICT_EXPORT_COLUMNS` | `EXPORT_COLUMNS` | **Total Wide Export Columns**: All 1,889 importable dictionary columns plus 2 server-computed calc fields (`1889 + 2 = 1891`). This is the exact column count of a REDCap wide export table (`v_redcap_wide`). |
| **1,891** | `SUBMISSION_COLUMNS` | `SUBMISSION_COLUMNS` | **Total API Submission Payload Keys**: All 1,889 importable dictionary columns plus 2 REDCap system columns (`record_id` and `video_review_complete`, `1889 + 2 = 1891`, `D11`). |

> [!IMPORTANT]
> **Why `EXPORT_COLUMNS != SUBMISSION_COLUMNS`**: Both collections contain exactly 1,891 elements (`len(EXPORT_COLUMNS) == 1891` and `len(SUBMISSION_COLUMNS) == 1891`). However, they are distinct sets: `EXPORT_COLUMNS` includes the 2 server-computed calculation fields while excluding the 2 system fields (`record_id`, `video_review_complete`), whereas `SUBMISSION_COLUMNS` excludes the 2 calculation fields (`IMPORTABLE_COLUMNS`) while including the 2 system fields (`tests/test_emit_python.py`).

---

## 2. BigQuery Physical Schema (`resus_raw` — 13 Tables, [D07](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D07.md))

All physical database tables are deployed into the `resus_raw` dataset. Raw PHI and verbatim evidence strings are strictly confined to this dataset.

| Table Name | Primary Key | Description & Lineage |
| :--- | :--- | :--- |
| `dim_case` | `case_id` | Demographic, clinical arrival, and administrative metadata for resuscitation cases. |
| `dim_run` | `run_id` | Execution run provenance, LLM model tiers, and SHA-256 prompt version hashes. |
| `dim_redcap_field` | `dict_version`, `field_name` | The 911 dictionary and system field metadata definitions (seeded from `generated/dim_redcap_field_seed.jsonl`). |
| `fact_event` | `event_id` | Extracted discrete clinical events with temporal bounds (`t_start_s`, `t_end_s`) and verbatim evidence quotes. |
| `fact_interval` | `interval_id` | Extracted continuous state intervals (CPR interruptions, ultrasound windows). |
| `fact_utterance` | `utterance_id` | Diarized transcription utterances from resuscitation team leaders (`S7`). |
| `fact_sensor_interval` | `sensor_interval_id` | Continuous physical sensor measurement intervals (`S1–S7`). |
| `fact_redcap_field` | `case_id`, `run_id`, `export_column` | Reducer-emitted field values (1,879 rows per case-run) with confidence, state, and routing provenance. |
| `redcap_submission` | `submission_id` | Immutable log of JSON payloads submitted to REDCap API (`D11`). |
| `fact_metric` | `case_id`, `run_id`, `metric_name` | Derived clinical quality improvement metrics (`CCF`, `peri-shock pause`, etc., `D10`). |
| `fact_coverage_note` | `note_id` | Diarized channel coverage and occlusion annotations (`S6`). |
| `fact_near_miss` | `near_miss_id` | Extracted candidate events rejected by ensemble voting (`1/3` minority vote, `D08`). |
| `fact_team_score` | `case_id`, `run_id`, `field_name` | Extracted subjective resuscitation team performance ratings (`P4a/P4b`, Q-006). |

---

## 3. Four Field States (`fact_redcap_field.state` / `FieldState`)

Every reducer-emitted field value (`FieldValue`) carries an explicit `state` enum tag that dictates its downstream handling in the Confidence Router ([D09](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D09.md)):

```
                       +-----------------------------------+
                       |    Extracted FieldValue (D05)     |
                       +-----------------+-----------------+
                                         |
               +-------------------------+-------------------------+
               |                         |                         |
               v                         v                         v
     [Branching Satisfied?] ---> NO -> [not_applicable]   [Coverage Degraded?]
               |                                                   |
              YES                                                 YES
               |                                                   |
               v                                                   v
   [conf >= difficulty_floor?] ---> NO -> [routed (HITL)]        [utd]
               |                                                   |
              YES                                                  +---> [routed (HITL)]
               |
               v
        [auto_accepted]
```

1. **`AUTO_ACCEPTED` (`auto_accepted`)**: Confident extraction (`confidence >= difficulty_floor`) or confirmed true absence on an active branching path. Automatically accepted into the curated clinical dataset.
2. **`ROUTED` (`routed`)**: Low-confidence extraction (`confidence < difficulty_floor`), subjective TEAM rating (`Q-006`), or unmapped value routed to the human-in-the-loop (`HITL`) review queue.
3. **`UNABLE_TO_DETERMINE` (`utd`)**: Legitimate clinical abstention due to coverage degradation, sensor occlusion, or physical ambiguity (`F-012`). Routed to human review.
4. **`NOT_APPLICABLE` (`not_applicable`)**: Branching logic predicate unsatisfied or inactive repeating slot. Excluded from human review.

---

## 4. Three Legitimate Null States in the Pipeline

A field value of `None` (`is_null=True`) occurs in exactly three legitimate clinical scenarios, distinguished by confidence, abstention flags, and routing behavior:

| Null State Scenario | `value` | `confidence` | `abstained` | `routed` | Clinical / Technical Meaning |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Unobserved Optional Attribute on an Observed Event** | `None` | `0.75` | `False` | `True` | The parent event occurred, but an optional attribute was unreadable (e.g., A-line SBP during intubation occlusion). Routes to HITL review. |
| **2. Confirmed True Absence** | `None` | `1.0` | `False` | `False` | An event or condition did not occur, and signal coverage was complete (e.g., no vascular access attempted: `access_confirmed_time = None`). Clean absence; does not route. |
| **3. Channel Coverage Degraded / Visual Occlusion** | `None` | `0.0` | `True` | `True` | Signal channel was occluded or degraded (`F-012`, `F-004`). Carries explicit `abstain_reason="Channel coverage degraded"` and routes to HITL review. |

---

## 5. Seven Source Classes across 909 Dictionary Fields

The 909 dictionary instrument fields are categorized into seven source classes (`by_source_class` in `generated/coverage_manifest.json`):

| Source Class | Count | Extraction Mechanism & Provenance |
| :--- | :---: | :--- |
| `AI_DIRECT` | **806** | Extracted directly from multimodal audio/video/sensor event streams (`P1–P3`). |
| `AI_DERIVED` | **49** | Derived algorithmically by the Reducer from other events/fields (e.g., `drug_class`, `rhythm_shockable`). |
| `CONDITIONAL` | **35** | Conditioned on specific clinical triggers or prior branching logic paths. |
| `ROSTER_JOIN` | **8** | Joined from hospital clinical operator roster (`operator_ed_*`). Emitted as present-and-blank `""` in REDCap payloads. |
| `AI_NARRATIVE` | **7** | Section summary narrative fields (`*_narrative`, `P5`). |
| `REDCAP_CALC` | **2** | Server-computed calculation fields (`dur_mccd_app_ed_secs_v2`, `duration_ventilator_place_v2`). Excluded from API import payloads (`IMPORTABLE_COLUMNS`). |
| `HUMAN_ONLY` | **2** | Exclusively populated by human clinical reviewers (`review_trigger`, etc.). Emitted as present-and-blank `""` in REDCap payloads. |

---

## 6. Multimodal Event Stream Schema

Extracted clinical events (`fact_event`) and continuous intervals (`fact_interval`) share a unified schema defined in `reducer/engine.py`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "id": { "type": "string", "description": "sha1(case_id|type|ordinal)[:12] deterministic identifier" },
    "case_id": { "type": "string", "description": "Foreign key to dim_case" },
    "run_id": { "type": "string", "description": "Foreign key to dim_run" },
    "type": { "type": "string", "description": "Declared event or interval type (e.g., defibrillation_shock, compression_interruption)" },
    "t_start_s": { "type": "number", "description": "Event/interval start timestamp in seconds from video start" },
    "t_end_s": { "type": "number", "description": "Event/interval end timestamp in seconds from video start" },
    "modality": { "type": "string", "enum": ["visual", "speech", "audio_device", "monitor_ocr", "inference"] },
    "confidence": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
    "evidence": { "type": "string", "description": "Verbatim audio quote or visual description supporting extraction" },
    "attributes": { "type": "object", "description": "Event-specific key-value attribute dictionary" }
  },
  "required": ["id", "case_id", "run_id", "type", "t_start_s", "t_end_s", "modality", "confidence", "evidence", "attributes"]
}
```

---

## 7. Extraction Difficulty Breakdown (`by_difficulty`)

The 909 dictionary fields are assigned to three confidence difficulty tiers (`by_difficulty` in `generated/coverage_manifest.json`), plus 10 non-extractable fields:

| Difficulty Tier | Count | Conf. Threshold (`diff_floor`) | Clinical Examples |
| :--- | :---: | :---: | :--- |
| `HIGH` | **345** | `0.92` | Subtle visual/audio features (e.g., arterial line SBP/DBP during CPR, airway anatomical difficulty). |
| `MEDIUM` | **418** | `0.85` | Standard clinical events and interventions (e.g., defibrillation shock timing, medication delivery). |
| `LOW` | **136** | `0.80` | Basic arrival, demographic, and macro-timestamp items. |
| `NOT_EXTRACTABLE` | **10** | N/A | Human-only and roster fields excluded from AI extraction. |
| **Total Fields** | **909** | | Sum of all difficulty tiers (`345 + 418 + 136 + 10 = 909`). |

---
Last verified: 2026-08-03 against dict_version e7c08437adcef4a5, prompt_set_sha 12280b94c0c134e8
