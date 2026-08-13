# Resuscitation Quality Improvement Pipeline (resus_qc) — Developer Start Here

Welcome to the **resus_qc** developer documentation package. This repository houses an autonomous, multimodal resuscitation quality improvement (QI) extraction engine designed to ingest raw video, audio, and physiological telemetry from Emergency Department (ED) and Critical Care resuscitation cases (`OHCA`, `IHCA`, trauma) and produce verified, audit-ready clinical dataset abstractions for REDCap and BigQuery.

---

## 1. Executive Summary & Purpose

Clinical resuscitation quality improvement relies on meticulous case abstraction—capturing chest compression fractions (CCF), defibrillation timing, advanced airway attempts, medication delivery, and closed-loop communication. Manual human abstraction is labor-intensive, retrospective, and prone to inter-rater variability. 

The `resus_qc` pipeline solves this by coupling **deterministic multimodal sensors (`S1–S7`)** for continuous physical signal measurement (motion optical flow, audio discharge transients, monitor OCR) with a **five-pass LLM prompt layer (`P1–P5`)** for semantic reasoning, narrative synthesis, and clinical adjudication. A formal **Reducer Engine (`D05`)** bridges these layers, evaluating 909 clinical data dictionary fields against strict branching rules and emitting an immutable 1,891-column wide payload for clinical review and archival.

---

## 2. Document Map

This documentation package consists of nine authoritative technical specifications. Every number, schema, and behavioral claim is derived directly from executable codebase artifacts (`generated/coverage_manifest.json`, `reducer/engine.py`, `mapping/registry.yaml`, and `docs/DEMO_FINDINGS.md`).

| Document | Title & Primary Scope | Core Technical References |
| :--- | :--- | :--- |
| `docs/00_START_HERE.md` | **System Overview & Onboarding Portal** | Core repository entrypoint and navigation map. |
| `docs/01_ARCHITECTURE.md` | **Three-Layer Architecture & Pipeline Data Flow** | Three-layer design, "sensors first" rationale (`F-008`), 5 LLM passes (`P1–P5`), Reducer role (`D05`), runtime cost/latency. |
| `docs/02_DATA_MODEL.md` | **Data Model, Field States & BigQuery Schema** | The 6 dictionary counts (`909`, `911`, `1879`, `1889`, `1891`, `1891`), 13 BigQuery tables, 4 field states, 3 legitimate null states, 7 source classes. |
| `docs/03_SENSOR_SPECS.md` | **Deterministic Multimodal Sensor Suite (`S1–S7`)** | Detailed algorithmic specs, schemas, calibration, and failure modes for S1–S7, including S3 acoustic parameters (`5.7` RMS, `F-009`) and `n=4` calibration caveat. |
| `docs/04_PROMPT_LAYER.md` | **Prompt Engineering & Extraction Contract Layer** | Prompts as source, `VERSIONS.yaml`, Constitution v2.0 (`F-004`), 5-pass architecture (`F-006`, `F-010`), 39 anchor cards, and 16-char `prompt_set_sha`. |
| `docs/05_GCP_DEPLOYMENT.md` | **GCP Cloud Infrastructure & BigQuery Deployer** | GCP services, Terraform architecture (`D07a`), 5 irreversible schema decisions, IAM negative proof, VPC-SC, and cost model. |
| `docs/06_ONBOARDING.md` | **Developer Onboarding, Workflow & Tripwires** | Day 1 / Week 1 onboarding, step-by-step first task guide, and the 4 non-negotiable REDCap tripwires (`1/0` yesno, `_v2` missing suffixes, literal bans). |
| `docs/07_TESTING.md` | **Verification Architecture & Fail-Loudly Principles** | The fail-loudly philosophy, 7 silent-degradation traps, 6 invariants (`I1–I6`), synthetic maximal fixture (`D12`), and integration test suite. |
| `docs/08_GLOSSARY.md` | **Clinical Resuscitation & System Technical Glossary** | Definitive reference of ED resuscitation clinical terminology and internal architecture concepts. |

---

## 3. Core Architectural & Operational Truths

1. **Why Sensors First (`F-008`, `F-010`)**: Large Language Models alone cannot reliably count instantaneous physical events or establish sub-second temporal boundaries across 30-minute videos (`F-008`). Our architecture enforces **Union-of-k for Recall, Deterministic Sensors for Precision**: LLM draws propose candidate event windows, while deterministic sensors (`S1–S7`) adjudicate timestamps and physical signal validity (`F-006`, `F-009`).
2. **Three-Layer Design**: The system separates **Extraction** (Sensors `S1–S7` + LLM Passes `P1–P5`), **Reduction** (`reducer/engine.py`, deterministic branching and schema evaluation), and **Storage/Integration** (13 physical BigQuery tables in `resus_raw`, 7 curated audit views in `resus_curated`, ).
3. **Fail-Loudly Verification**: No fallback heuristics or silent defaults are permitted. If a dictionary checksum drift is detected (`I1`), an anchor card is missing (`prompt_set_sha(strict=True)`), or a REDCap choice code is undeclared (`F-001`), the pipeline raises a fatal exception immediately.

---

## 4. Quickstart: First 10 Minutes

To verify local environment integrity and execute the core invariant test suite:

```bash
# 1. Activate Python 3.14 virtual environment
source .venv/bin/activate

# 2. Verify dictionary hash and generated coverage manifest
bash scripts/check_invariants.sh

# 3. Run entire unit test suite (150 tests across 17 files)
pytest -q -m "not integration"
```

Where a sensor or capability is not yet built in Phase 1, it is explicitly documented and linked to its tracking task file in `docs/tasks/` (e.g., [D00](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D00.md), [A03b](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/A03b.md)).

---
Last verified: 2026-08-03 against dict_version e7c08437adcef4a5, prompt_set_sha 12280b94c0c134e8
