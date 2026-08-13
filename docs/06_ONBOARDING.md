# Resuscitation Quality Improvement Pipeline — Developer Onboarding & The Four Tripwires

This onboarding guide provides structured Day 1 and Week 1 curricula, a step-by-step walkthrough for your first development task, and the four non-negotiable REDCap data dictionary tripwires.

---

## 1. Day 1 Curricula: Environment Setup & Core Verification

Your Day 1 goal is to set up a reproducible local environment and verify that all 150 unit tests and 6 invariants pass cleanly.

```bash
# 1. Clone repository and enter workspace
cd resus_qc

# 2. Activate Python virtual environment (Python 3.14+)
source .venv/bin/activate

# 3. Verify data dictionary hash and system invariants (I1-I6)
bash scripts/check_invariants.sh

# 4. Execute the complete offline unit test suite (150 tests)
pytest -q -m "not integration"
```

### Day 1 Required Reading
1. `docs/00_START_HERE.md`: Overview and document map.
2. `docs/01_ARCHITECTURE.md`: The three-layer architecture and "sensors first" rationale (`F-008`).
3. `prompts/system/constitution.v2.0.md`: The invariant clinical rules governing LLM extraction (`F-004`).

---

## 2. Week 1 Curricula: Deep-Dive Architecture & Reference Case

During your first week, you will explore the 909 dictionary fields (`FIELDS`), the 5-pass prompt sequence, and the 22-minute clinical reference case (`golden_case_01.py`, [D12](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D12.md)).

1. **Inspect `generated.redcap_fields.FIELDS`**: Examine the 909 dictionary fields, note their `source_class` (`AI_DIRECT`, `AI_DERIVED`, etc.), and see how repeating groups are defined (`defib`: 30, `cci`: 30, `airway`: 8, `rosc`: 20, `vent_delay`: 5).
2. **Execute `golden_case_01.py`**: Run the clinical reference case and inspect the 7-column routing table across the 1,879 reducer-emitted fields:
   * 1,462 `branching_not_satisfied`
   * 371 `auto_accepted`
   * 28 `low confidence`
   * 12 `TEAM` subjective ratings (`Q-006`)
   * 5 `empty_narrative_no_anomalies`
   * 1 `truncated group`
3. **Understand Empirical Findings (`docs/DEMO_FINDINGS.md`)**: Read findings `F-001` through `F-012`, focusing on why same-model consistency probes are not ground truth (`F-006`), why Pro models did not outperform Flash on stochastic shock counting (`F-010`), and why channel coverage abstention yields 47 `"no evidence observed"` fallbacks (`F-012`).

---

## 3. Your First Task: Adding or Editing an Anchor Card ([A03](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/A03.md))

When modifying an event extraction rule or adding positive/negative boundary examples to an anchor card in `prompts/anchors/`:

```
[Edit prompts/anchors/<card>.yaml] ---> [bash scripts/check_invariants.sh]
                                                |
              +---------------------------------+---------------------------------+
              |                                                                   |
              v                                                                   v
     [I6: 39 Anchor Cards Validated]                       [prompt_set_sha(strict=True) Verifies]
```

1. **Edit the Target Anchor Card**: Open `prompts/anchors/<event_type>.yaml` and update `positive_examples` or `negative_examples` using clear, clinical ED resuscitation scenarios.
2. **Verify Anchor Library Parity (`I6`)**: Run `python scripts/check_anchors.py --strict` to assert that all 39 required anchor cards are valid and contain no syntax errors.
3. **Verify Prompt Checksum Integrity**: Ensure `prompt_set_sha(strict=True)` (`12280b94c0c134e8`) remains reproducible and raises no missing-file exceptions ([A01](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/A01.md)).
4. **Execute Regression Suite**: Run `pytest -q` to verify that your changes do not break downstream prompt assembly (`build_p1`, `build_p3` in `prompts/builder.py`).

---

## 4. The Four Non-Negotiable REDCap Tripwires

Violating any of these four tripwires causes silent schema corruption, API import failures, or invalid clinical data extractions:

```
+---------------------------------------------------------------------------------+
|                        THE 4 NON-NEGOTIABLE TRIPWIRES                           |
+---------------------------------------------------------------------------------+
|  1. yesno is 1/0 not 1/2      -> Never assign code "2" to a yesno field (F-001) |
|  2. 7 CCI sub-fields lack _v2 -> pulse_check_cci_{i} has NO _v2 suffix          |
|  3. Never hand-type names     -> Always reference generated.redcap_fields       |
|  4. The LLM never counts      -> Use Union-of-k & physical sensors (F-008)      |
+---------------------------------------------------------------------------------+
```

### Tripwire 1: `yesno` is `1/0`, NOT `1/2` (`F-001`)
In REDCap, boolean `yesno` field types (`1="Yes"`, `0="No"`) use **`"1"` and `"0"`**. Standard REDCap radio button fields use `"1"`, `"2"`, `"3"`, etc. Never assign code `"2"` to a boolean `yesno` field (`F-001`). The Reducer Engine's vocabulary mapper (`_map_vocab()`) enforces this distinction automatically.

### Tripwire 2: Exactly Seven CCI Sub-Fields Lack `_v2` Suffix
In `dictionary/instrument.csv`, while the vast majority of Version 2 fields end in `_v2`, **exactly seven Chest Compression Interruption (`CCI`) sub-fields lack the `_v2` suffix**:
1. `pulse_check_cci_{i}`
2. `rhythm_check_cci_{i}`
3. `airway_placement_cci_{i}`
4. `aline_sbp_cci_{i}`
5. `aline_dbp_cci_{i}`
6. `compress_depth_cci_{i}`
7. `compress_rate_cci_{i}`

**Never guess or append `_v2` to these field names!** Always inspect `generated.redcap_fields.FIELDS`.

### Tripwire 3: Never Hand-Type a Field Name (`I5`, `assert_no_field_names`)
Never hand-type a REDCap column literal (`num_cci_v2`, `defib_shock_time_1`, etc.) into prompt templates, Python business logic, or SQL strings. Always reference field symbols from `generated.redcap_fields.FIELDS` or use dynamic schema generators (`codegen/emit_sql.py`, [D07](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D07.md)). Hand-typing literals causes silent typo defects and fails invariant `I5`.

### Tripwire 4: The LLM Never Counts (`F-008`, `F-010`)
Never prompt an LLM to count how many defibrillation shocks, airway attempts, or CPR interruptions occurred in a case (`F-008`). Our 5-call replication probe showed a **20% replication rate** for shock counting (`F-008`), and Pro models performed worse than Flash (`F-010`). The LLM extracts candidate event intervals; deterministic physical sensors (`S1–S7`) and the Reducer Engine (`D05`) count occurrences and unroll repeating instruments.

---
Last verified: 2026-08-13 against dict_version e7c08437adcef4a5, prompt_set_sha 2b6988545630a115
