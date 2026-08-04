# Resuscitation Quality Improvement Pipeline — Verification Architecture & Fail-Loudly Testing (`I1–I6`, `D12`)

This specification documents the "fail-loudly" verification philosophy, the seven silent-degradation traps prevented by code assertions, the six system invariants (`I1–I6`), the synthetic maximal fixture (`D12`), the 22-minute clinical reference case (`golden_case_01`), and the integration test suite.

---

## 1. The Fail-Loudly Principle

In clinical quality improvement, an unflagged silent error is more dangerous than an outright crash. A missing data column or corrupted choice code can skew hospital-wide resuscitation metrics. 

The `resus_qc` codebase enforces the **Fail-Loudly Principle**:
* **No Swallowing Exceptions**: Code paths never catch generic exceptions to return default strings (`""` or `"unknown"`).
* **No Fallback Coercion**: Validators return immutable `Result` objects without mutating or coercing invalid input records (`test_validators.py`).
* **Immediate Halts on Schema Drift**: Any mismatch between REDCap dictionary hashes (`e7c08437adcef4a5`), prompt checksums (`12280b94c0c134e8`), or generated Python artifacts halts execution at import time.

---

## 2. All Seven Silent-Degradation Instances Prevented by Assertions

Our verification suite explicitly prevents seven historical silent-degradation traps identified during pipeline development:

| # | Silent-Degradation Trap | Prevention Mechanism & Test Assertion | Authoritative Finding / Task |
| :---: | :--- | :--- | :--- |
| **1** | Stale REDCap dictionary without rehash | `scripts/check_invariants.sh` checks `I1`: asserts `dict_version.txt == sha256sum(instrument.csv)[:16]`. Halts if dictionary changed without rehash. | `I1` ([D03](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D03.md)) |
| **2** | Missing prompt templates or anchor cards | `prompt_set_sha(strict=True)` raises `FileNotFoundError` immediately if any of the 5 pass templates or 39 anchor cards are missing. Never skips missing files. | [A01](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/A01.md) |
| **3** | Undeclared placeholder variables in prompts | `validate_template_placeholders()` parses every `{var}` token in templates against `_PLACEHOLDERS.yaml`, failing on undeclared variables (`I4`). | `I4` ([A01](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/A01.md)) |
| **4** | Literal REDCap field names in prompt text | `assert_no_field_names()` regex-scans prompt templates to ensure zero database column names (`num_cci_v2`, etc.) leak into LLM prompts (`I5`). | `I5` ([A01](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/A01.md)) |
| **5** | Silent boolean mapping to radio code `'2'` | `_map_vocab()` (`reducer/engine.py`) restricts boolean `'yes'`/`'no'` mappings strictly to yesno fields, preventing booleans from corrupting non-yesno radios (`F-001`). | `F-001` ([D05](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D05.md)) |
| **6** | Omission of ungated attributes in JSON Schema | Marking ungated attributes in the JSON Schema `required` array prevents silent field omission and doubles `auto_accepted` yield (**`132` vs. `243`/`221`/`216`**, `F-002`, `F-011`). | `F-002`, `F-011` ([D14](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D14.md)) |
| **7** | Silent API 400 errors during REDCap submission | `redcap/client.py` captures HTTP 400 validation failures, parses error body, attaches to `quarantine_reasons`, and fails loudly without retry ([D11](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D11.md)). | [D11](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D11.md) |

---

## 3. The Six System Invariants (`I1–I6`, `scripts/check_invariants.sh`)

Every PR and CI run executes `bash scripts/check_invariants.sh` to enforce six non-negotiable structural invariants:

```
+---------------------------------------------------------------------------------+
|                       AUTOMATED INVARIANT SUITE (I1-I6)                         |
+---------------------------------------------------------------------------------+
|  I1: Dictionary Hash Parity -> dict_version.txt == e7c08437adcef4a5             |
|  I2: Field Coverage Completeness -> 100% of FIELDS in redcap_fields.py          |
|  I3: Submission Payload Completeness -> len(SUBMISSION_COLUMNS) == 1,891        |
|  I4: Prompt Placeholder Integrity -> validate_template_placeholders() passes    |
|  I5: Zero Field-Name Literals in Prompts -> assert_no_field_names() passes      |
|  I6: Anchor Card Library Parity -> 39 cards present in prompts/anchors/         |
+---------------------------------------------------------------------------------+
```

| Invariant | Title | Command / Code Assertion | Failure Condition |
| :---: | :--- | :--- | :--- |
| **I1** | **Dictionary Hash Parity** | `cat dictionary/dict_version.txt == sha256sum dictionary/instrument.csv` | `dict_version.txt` is stale or missing after modifying `instrument.csv`. |
| **I2** | **Field Coverage Completeness** | `all(f.export_column in EXPORT_COLUMNS for f in FIELDS.values())` | Any dictionary field in `FIELDS` is missing from `generated.redcap_fields`. |
| **I3** | **Submission Payload Completeness** | `len(SUBMISSION_COLUMNS) == 1891` (`IMPORTABLE_COLUMNS \| {"record_id", "video_review_complete"}`) | API payload assembly omits importable dictionary columns or system keys. |
| **I4** | **Prompt Placeholder Integrity** | `validate_template_placeholders(template)` | Any `{variable}` token in a prompt template is missing from `_PLACEHOLDERS.yaml`. |
| **I5** | **Zero Field-Name Literals** | `assert_no_field_names(template)` | Any database field literal (`num_cci_v2`, `defib_shock_time_1`) appears in prompt text. |
| **I6** | **Anchor Library Parity** | `len(list_anchor_cards()) == 39` | Any of the 39 required anchor cards is missing from `prompts/anchors/`. |

---

## 4. Synthetic Maximal Fixture (`fixtures/synthetic_maximal.py`, [D12](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D12.md))

To verify Reducer Engine behavior under maximum clinical load, `fixtures/synthetic_maximal.py` dynamically constructs a maximal event stream (`build_event_stream()`):
* **Dynamic Generation**: Derived directly from `FIELDS` without hand-coded literals or hard-coded counts.
* **Repeating Group Saturation**: Exercises all repeating instruments at declared cap: **30 defibrillations (`defib`)**, **30 CPR interruptions (`cci`)**, **8 airway attempts (`airway`)**, **20 ROSC episodes (`rosc`)**, and **5 ventilation delays (`vent_delay`)**.
* **Reason Vocabulary Cycling**: Cycles all 21 declared `cci_reason` codes across the 30 CCIs without invalid literals.
* **Coverage Verification**: Asserts that `reduce_stream()` emits exactly **1,879 export columns** without raising exceptions or throwing choice validation errors (`test_coverage.py`).

---

## 5. Clinical Reference Case (`fixtures/golden_case_01.py`, [D12](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D12.md))

`golden_case_01.py` implements a clinically realistic 22-minute Out-of-Hospital Cardiac Arrest (`OHCA`) resuscitation narrative in the ED:
* **Clinical Scenario**: 58yo male OHCA, 12 CPR interruptions, 3 defibrillation shocks, 2 advanced airway attempts, 1 ROSC episode, a visual crowding occlusion (`11:00–11:30`), and a low-confidence arterial line reading (`14:22`).
* **Seven-Column Routing Distribution Table**: Running `golden_case_01.py` through the Reducer and Confidence Router distributes all **1,879 reducer-emitted fields** across exactly seven routing classes:

```
===================================================================================
                  golden_case_01 SEVEN-COLUMN ROUTING TABLE (D12)                  
===================================================================================
  1. branching_not_satisfied     : 1,462 (inactive repeating slots & predicates)   
  2. auto_accepted               :   371 (populated confident fields & clean nulls)
  3. low confidence              :    28 (unobserved optional attributes on events)
  4. TEAM (Q-006)                :    12 (subjective ratings -> HITL review queue) 
  5. empty_narrative_no_anomalies:     5 (clean section narrative notes)           
  6. truncated group             :     1 (mccd_applied_ems_v2, visual occlusion)   
-----------------------------------------------------------------------------------
  TOTAL REDUCER-EMITTED FIELDS   : 1,879 (1462 + 371 + 28 + 12 + 5 + 1 = 1879)     
===================================================================================
```

---

## 6. Integration Test Suite & Verification Boundaries

The integration test suite (`tests/`) isolates unit verification from live infrastructure requirements:

1. **BigQuery DDL & View Integration (`tests/test_audit_views_integration.py`, [D07](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D07.md))**: Verifies local SQL generation (`emit_bq_ddl()`, `emit_audit_views_sql()`) and asserts schema parity against `nodepeel` datasets (`resus_raw`, `resus_curated`).
2. **REDCap Round-Trip Integration (`tests/test_roundtrip.py`, [D13](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D13.md))**: Offline unit tests verify payload JSON dictionary set-equality (`1,891 keys`, `test_assemble.py`). Live round-trip tests against physical REDCap API servers are **NOT BUILT / SKIPPED OFFLINE** ([D13](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D13.md), Q-014).
3. **Execution Summary**: All **150 unit tests across 17 test suites** pass 100% cleanly in offline CI (`150 passed, 8 deselected`).

---
Last verified: 2026-08-03 against dict_version e7c08437adcef4a5, prompt_set_sha 12280b94c0c134e8
