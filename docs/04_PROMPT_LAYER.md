# Resuscitation Quality Improvement Pipeline — Prompt Layer & Extraction Contract (`P1–P5`)

This specification documents the prompt engineering architecture, version control governance, Constitution v2.0 rules, five-pass LLM prompt sequence, schema-bound extraction contracts, 39 structural anchor cards, and deterministic SHA-256 prompt set hashing.

---

## 1. Prompts as Source Code & `VERSIONS.yaml` Governance

In `resus_qc`, prompt templates are **executable source code**, not informal text strings. Every edit to a prompt template (`prompts/passes/*.v2.0.md`) alters the prompt set SHA-256 checksum (`12280b94c0c134e8`) and triggers automated CI validation.

### 1.1 `VERSIONS.yaml` Compatibility Matrix
The prompt library is bound to dictionary and contract versions via `prompts/VERSIONS.yaml` ([A01](tasks/A01.md)):

```yaml
schema_version: "2.0"
requires_contract_version: "1"
requires_dict_version: "e7c08437adcef4a5"
```

If the REDCap dictionary is modified and rehashed (`scripts/hash_dict.sh`) without updating `requires_dict_version` in `VERSIONS.yaml`, the prompt registry (`prompts/registry.py`) raises a fatal `ValueError` at import time (`I1`).

---

## 2. Constitution v2.0 (`prompts/system/constitution.v2.0.md`, [A02](tasks/A02.md))

The Constitution is an invariant system prompt prepended to every LLM extraction pass. It establishes universal clinical rules that cannot be overridden by individual pass instructions:

* **Temporal Floor in Degraded Mode (`F-004`)**: When visual or audio clock synchronization (`S5`) is degraded or unbuilt, timestamps default to `t_precision_s >= 2.0s` via constitutional floor instruction. This explicitly **OVERRIDES** any narrower interval in the calibration table (`F-004`).
* **Negative Controls & Aborted Charges (`F-009`)**: The Constitution establishes explicit negative controls for physical events. For example, a defibrillator charge tone (`400–1000 Hz`, slope `>= 40 Hz/s`) that is not followed by an acoustic discharge transient within 2.0 seconds is classified as `defib_charge_aborted`—preventing the model from assuming every charge results in a shock (`F-009`).
* **No Field-Name Literals**: Prompt templates are strictly forbidden from embedding REDCap database column names (`num_cci_v2`, etc.). All clinical concepts are expressed through semantic domain vocabulary (`assert_no_field_names`, [A01](tasks/A01.md)).

---

## 3. Five-Pass Architecture (`P1–P5`, [A04](tasks/A04.md), [A06](tasks/A06.md))

```
+---------------------------------------------------------------------------------+
|                        P1: EVENT HARVEST (gemini-3.6-flash)                     |
|            Extracts candidate clinical events across entire video timeline      |
+---------------------------------------------------------------------------------+
                                         |
                                         v
+---------------------------------------------------------------------------------+
|                     P2: TEMPORAL VERIFICATION (gemini-3.6-flash)                |
|            Verifies boundaries, applies t_precision_s >= 2.0s floor (F-004)     |
+---------------------------------------------------------------------------------+
                                         |
                                         v
+---------------------------------------------------------------------------------+
|                   P3: CLINICAL ADJUDICATION (gemini-3.1-pro-preview)            |
|            Deep clinical reasoning on complex attributes & rhythm strips        |
+---------------------------------------------------------------------------------+
                                         |
                    +--------------------+--------------------+
                    |                                         |
                    v                                         v
+---------------------------------------+  +--------------------------------------+
|       P4a/P4b: TEAM EVALUATION        |  |     P5: SECTION NARRATIVE NOTES      |
|       (gemini-3.1-pro-preview)        |  |         (gemini-3.6-flash)           |
|    12 subjective leadership ratings   |  |   Narratives & truncation reports    |
+---------------------------------------+  +--------------------------------------+
```

### 3.1 Why P1/P2 Consistency Probes are Not Ground Truth (`F-006`, `F-010`)
Our demonstration established that same-model consistency probes are consistency checks, not ground truth (`F-006`). Pass P1 and a focused probe agreed on 3 shocks but disagreed on 2 of 3 compression interruptions—including a 54-second pause found by one and not the other. Neither model output is authoritative (`F-006`). 

Furthermore, upgrading model tiers does not resolve instantaneous-event detection (`F-010`). Run 4 used `gemini-3.1-pro-preview` at $0.45 and +31% latency, and performed worse than `gemini-3.6-flash`—recovering 3 of 4 shocks with one false positive (`3/4 recall`). This confirms why physical sensors (`S1–S7`) must adjudicate precision (`F-008`).

---

## 4. Extraction Contract & JSON Schema Binding (`F-002`, `F-011`, [D14](tasks/D14.md))

The prompt layer communicates with the Reducer Engine (`D05`) through strict JSON Schema structured output contracts:

```
[Prompt P1-P5] ---> (Vertex AI Generation-Time Schema Enforcement, F-002)
                          |
                          +--> Ungated required array -> Zero True Hallucinations
                          +--> Bound to Reducer Contract -> Yield Doubled (F-011)
```

1. **Generation-Time Schema Enforcement (`F-002`)**: Marking ungated contract attributes in the JSON Schema `required` array enables Vertex AI generation-time syntax enforcement without causing reflexive `True` hallucinations. In our demonstration, boolean optional attributes like `aline_present` appeared on 100% of CCIs as an honest `False` (`F-002`).
2. **Yield Doubling via Schema Binding (`F-011`)**: Binding the REDCap extraction contract to the response schema roughly doubled confident extraction yield: **`Run 1 (pre-schema-fix)` yielded 132 `auto_accepted` fields**, whereas schema-bound runs (**`Run 2`, `Run 3`, and `Run 4`**) yielded **243, 221, and 216 `auto_accepted` fields** respectively (`F-011`).

---

## 5. The 39 Structural Anchor Cards (`prompts/anchors/`, [A03](tasks/A03.md), [A03b](tasks/A03b.md))

The prompt builder injects event-specific YAML anchor cards (`prompts/anchors/*.yaml`) into P1 and P3 templates. There are exactly **39 required anchor cards** (`30 event rules`, `9 hints`, `7 both`, matching `generated/coverage_manifest.json`):

```yaml
# Example Anchor Card Structure (defibrillation_shock.yaml)
event_type: defibrillation_shock
definition: "An electrical shock delivered by a defibrillator to terminate VF/pVT."
positive_examples:
  - "Defibrillator audio 'Shock delivered', body jerk observed at 741.2s."
negative_examples:
  - "Defibrillator audio 'Charging...' followed by 'Disarm' button press."
```

> [!WARNING]
> **Clinical Review Pending (`Q-009`)**: All 39 anchor cards pass structural syntax, field-reference, and gap verification (`check_anchors(fail_on_gap=True)` in CI). However, human clinical review of their prompt prose against Emergency Department resuscitation reality is **NOT BUILT / PENDING** ([A03b](tasks/A03b.md), Q-009).

---

## 6. Deterministic Prompt Set Hashing (`prompt_set_sha(strict=True)`)

To guarantee reproducible prompt execution, `prompts/registry.py` exposes `prompt_set_sha(strict=True)`:

* **Computation**: Computes a 16-character hexadecimal SHA-256 hash (`12280b94c0c134e8`) over the concatenated, alphabetically sorted contents of all five prompt templates (`p1_harvest`, `p2_verify`, `p3_adjudicate`, `p4a_team_items`, `p4b_team_global`, `p5_notes`) and the Constitution.
* **No Missing-File Skipping (`I1`)**: In accordance with invariant `I1`, `prompt_set_sha(strict=True)` **never skips missing files**. A partial hash is a lie about reproducibility. If any required template file is missing, the function raises `FileNotFoundError` immediately ([A01](tasks/A01.md)).

---
Last verified: 2026-08-13 against dict_version e7c08437adcef4a5, prompt_set_sha 2b6988545630a115
