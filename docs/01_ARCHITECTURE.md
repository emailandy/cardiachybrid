# Resuscitation Quality Improvement Pipeline — Architecture & Data Flow

This specification details the three-layer architectural design, multimodal sensor integration, five-pass LLM prompt sequence, Reducer engine mechanics, and end-to-end clinical data flow of the `resus_qc` pipeline.

---

## 1. Three-Layer Architectural Design

The pipeline is structured into three strictly decoupled layers to ensure auditability, clinical reproducibility, and clean schema boundaries:

```
+-----------------------------------------------------------------------------------+
|                        1. EXTRACTION & SENSOR LAYER                               |
|   Multimodal Sensors (S1-S7)      +      LLM Prompt Sequence (P1-P5)              |
|   (Deterministic Audio/Visual)            (Semantic Reasoning & Narrative)        |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
|                         2. REDUCER ENGINE LAYER (D05)                             |
|   evaluates 909 dictionary fields against 100% of branching logic & constraints    |
|   emits immutable 1,879-column wide FieldValue payload (4 field states)           |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
|                  3. INTEGRATION, ROUTING & ANALYTICS LAYER                        |
|   Confidence Router (D09) -> HITL Queue | BigQuery Schema (D07)                   |
+-----------------------------------------------------------------------------------+
```

### Layer 1: Extraction & Sensor Layer
Combines deterministic physical signal processing with multimodal Large Language Model (LLM) reasoning. Physical sensors (`S1–S7`) measure continuous signals (optical flow, audio waveforms, monitor OCR), while prompt passes (`P1–P5`) extract discrete clinical events, verify temporal bounds, and adjudicate clinical context.

### Layer 2: Reducer Engine Layer (`reducer/engine.py`, [D05](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D05.md))
The deterministic bridge between extraction and database ingestion. The Reducer interprets the 909 dictionary fields (`generated.redcap_fields.FIELDS`), evaluates branching logic without Python `eval()`, unrolls repeating groups up to their declared capacity (`defib`: 30, `cci`: 30, `airway`: 8, `rosc`: 20, `vent_delay`: 5), and emits an immutable 1,879-column wide vector of `FieldValue` objects.

### Layer 3: Integration, Routing & Analytics Layer
Receives the reduced payload and performs three functions:
1. **Confidence Routing ([D09](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D09.md))**: Evaluates each field's extraction confidence against its declared difficulty threshold (`HIGH: 0.92`, `MEDIUM: 0.85`, `LOW: 0.80`). Low-confidence items, subjective TEAM ratings (`Q-006`), and UTD anomalies route immediately to the human-in-the-loop (`HITL`) review queue.
2. **BigQuery Analytical Warehouse ([D07](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D07.md))**: Persists raw provenance across 13 physical tables in `resus_raw` and exposes 7 curated audit views in `resus_curated`.

---

## 2. "Sensors First" Rationale & Model Tier Independence

A core finding of our clinical demonstration is that Large Language Models alone cannot reliably count instantaneous physical events or establish sub-second temporal boundaries across 30-minute ED resuscitation videos (`F-008`).

* **Failure of Pure LLM Event Counting (`F-008`)**: A 5-call replication test on a 20-second video window (`730–750s`, `gemini-3.6-flash`, `fps=5`, shock-only prompt) yielded only a 20% replication rate (1 of 5 calls detected the defibrillation shock at `741.2s`; 4 of 5 returned zero shocks). Furthermore, while forced-choice 5-second block questioning was 100% stable for multi-second compression interruptions (`CCIs`), it failed to stabilize instantaneous shock detection.
* **Model Tier Independence (`F-010`)**: Upgrading model tiers does not resolve instantaneous physical event detection. In a 4-draw comparison over identical clinical simulation footage (`Run 1–3` using `gemini-3.6-flash` vs. `Run 4` using `gemini-3.1-pro-preview` at $0.45 and +31% latency), the Pro model performed worse than Flash—recovering 3 of 4 shocks with one false positive (`3/4 recall`).
* **The Architectural Rule (`F-008`)**: The pipeline enforces **Union-of-k for Recall, Acoustic/Motion Sensors for Precision**. LLM draws generate candidate event windows across the timeline; deterministic sensors (`S1–S7`) confirm or reject each candidate using acoustic discharge spike analysis (`F-009`) and optical flow compression motion (`S1`).

---

## 3. Five-Pass LLM Prompt Sequence (`P1–P5`)

The prompt layer decomposes clinical abstraction into five sequential, schema-bound passes ([A04](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/A04.md), [A06](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/A06.md)):

```
[P1: Event Harvest] ---> [P2: Verification] ---> [P3: Clinical Adjudication]
  (gemini-3.6-flash)      (gemini-3.6-flash)       (gemini-3.1-pro-preview)
                                                            |
                                        +-------------------+-------------------+
                                        |                                       |
                                        v                                       v
                             [P4a / P4b: TEAM Scores]                   [P5: Narrative Notes]
                             (gemini-3.1-pro-preview)                    (gemini-3.6-flash)
```

| Pass | Template File | Model Binding | Primary Scope & Responsibilities |
| :--- | :--- | :--- | :--- |
| **P1** | `p1_harvest.v2.0.md` | `gemini-3.6-flash` | High-recall harvesting of candidate resuscitation events (CPR interruptions, shocks, airway attempts, vascular access, medications, ROSC). |
| **P2** | `p2_verify.v2.0.md` | `gemini-3.6-flash` | Temporal verification and boundary refinement. Enforces constitutional floor instruction `t_precision_s >= 2.0s` in degraded mode (`F-004`). |
| **P3** | `p3_adjudicate.v2.0.md` | `gemini-3.1-pro-preview` | Deep clinical reasoning on complex case attributes (rhythm classification, intubation difficulty, ROSC duration, peri-shock pauses). |
| **P4a** | `p4a_team_items.v2.0.md` | `gemini-3.1-pro-preview` | Subjective evaluation of 11 resuscitation team communication and leadership items (`team1_v2` through `team11_v2`, Q-006). |
| **P4b** | `p4b_team_global.v2.0.md` | `gemini-3.1-pro-preview` | Subjective evaluation of overall resuscitation team performance score (`team12_v2`, Q-006). |
| **P5** | `p5_notes.v2.0.md` | `gemini-3.6-flash` | Section narrative synthesis (`*_narrative`) and mandatory truncation reporting (`format_truncation_report`) for repeating group overflow. |

All prompt templates are version-locked by a SHA-256 checksum (`prompt_set_sha(strict=True)` = `12280b94c0c134e8`), preventing silent template drift ([A01](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/A01.md)).

---

## 4. Reducer Engine Role & Mechanics

The Reducer Engine (`reducer/engine.py`, [D05](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D05.md)) receives extracted events and intervals from P1–P5 and executes four deterministic transformation stages:

1. **Branching Predicate Evaluation**: Evaluates all REDCap branching logic strings (`branching_raw`) using an AST-based parser (`_evaluate_branching`) without executing Python `eval()`. Inactive conditional fields are marked `NOT_APPLICABLE` (`not_applicable`).
2. **Repeating Group Unrolling**: Unrolls repeating instruments up to their declared capacity (`defib`: 30, `cci`: 30, `airway`: 8, `rosc`: 20, `vent_delay`: 5). Excess events beyond capacity trigger a truncation repair record and write to `overflow_note_field`.
3. **Checkbox & Radio Choice Mapping**: Maps extracted labels to dictionary choice codes (`_map_vocab`, `F-001`). Suppresses undeclared choice codes (`mccd_obstacles___1`, `mccd_obstacles___2`).
4. **Coverage & Abstention Fallback**: For fields lacking observed evidence, applies cause-based abstention logic (`F-012`). If visual channel coverage is degraded, emits an explicit abstention (`state="utd"`, `confidence=0.0`, `routed_to_human=True`, `abstain_reason="Channel coverage degraded"`, `F-004`).

---

## 5. End-to-End Pipeline Data Flow

```
[Raw ED Video / Audio / Monitor]
               |
               +---> [Deterministic Sensors S1-S7] --------+
               |     (Optical Flow, Acoustic RMS 5.7)      |
               |                                           v
               +---> [LLM Prompt Sequence P1-P5] ---> [Event / Interval Stream]
                     (gemini-3.6-flash / pro)              |
                                                           v
                                              [Reducer Engine (D05)]
                                              (909 dictionary fields)
                                                           |
                                                           v
                                              [1,879 Export Columns]
                                                           |
                          +--------------------------------+--------------------------------+
                          |                                                                 |
                          v                                                                 v
              [Confidence Router (D09)]                                      [BigQuery Warehouse (D07)]
              - auto_accepted (conf >= diff_floor)                           - resus_raw (13 physical tables)
              - routed -> HITL Clinical Review Queue                         - resus_curated (7 audit views)
                          |                                                                 |
                          +--------------------------------+--------------------------------+
                                                           |
                                                           v
```

---

## 6. Runtime Cost & Latency Profile

Execution cost and latency per case depend on the configured ensemble draw count (`k=1` vs. `k=3` voting):

| Pipeline Stage / Component | Model Tier | Avg. Latency (s) | Estimated Cost / Case ($ USD) |
| :--- | :--- | :--- | :--- |
| **Pass P1 (Event Harvest)** | `gemini-3.6-flash` | 18–22s | $0.15 |
| **Pass P2 (Verification)** | `gemini-3.6-flash` | 12–16s | $0.15 |
| **Pass P3 (Adjudication)** | `gemini-3.1-pro-preview` | 35–45s | $0.45 |
| **Pass P4a/P4b (TEAM Scores)** | `gemini-3.1-pro-preview` | 20–25s | $0.25 |
| **Pass P5 (Narrative Notes)** | `gemini-3.6-flash` | 10–15s | $0.10 |
| **Reducer Engine (`D05`)** | Deterministic Python | < 0.2s | $0.00 |
| **Total (`k=1` Single Draw)** | Hybrid Flash / Pro | **95–123s** | **$1.10** |
| **Total (`k=3` Ensemble, [D08](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D08.md))** | Hybrid Flash / Pro | **140–180s** (parallel) | **$3.30** |

---

## 7. Built vs. Not Built (Phase 1 Scope Boundary)

| Component / Subsystem | Current Implementation Status | Authoritative Reference / Task File |
| :--- | :--- | :--- |
| **Prompt Layer (`P1–P5`)** | **BUILT & VERIFIED** (100% template checksum locking) | [A04](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/A04.md), [A06](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/A06.md) |
| **Reducer Engine (`D05`)** | **BUILT & VERIFIED** (909 fields, all repeating groups) | [D05](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D05.md) |
| **BigQuery DDL & Audit Views (`D07`)** | **BUILT & VERIFIED** (13 physical tables, 7 audit views) | [D07](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D07.md), [D07a](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D07a.md) |
| **Sensors `S1–S7` Streaming Pipelines** | **NOT BUILT** (Hardware pipelines unbuilt in Phase 1; S3 acoustic probe validated offline in `F-009`) | [D00](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D00.md) |
| **Clinical Gold Set (25 Cases)** | **NOT BUILT** (25 dual-annotated cases unadjudicated) | [D00](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D00.md) |
| **Clinical Review of 39 Anchor Cards** | **NOT BUILT** (Cards pass structural linting; clinical review pending) | [A03b](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/A03b.md) (Q-009) |
| **Live REDCap Server Round-Trip** | **OBSOLETE** (REDCap network submission retired) | [D13](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D13.md) (Q-014) | **NOT BUILT** (Offline assembly tests pass; live API unverified) | [D13](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D13.md) (Q-014) |
| **TEAM Subjective Score Calibration** | **NOT BUILT** (Uncalibrated; all TEAM fields route to HITL review) | [A06](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/A06.md) (Q-006, Q-015) |

---
Last verified: 2026-08-13 against dict_version e7c08437adcef4a5, prompt_set_sha 2b6988545630a115
