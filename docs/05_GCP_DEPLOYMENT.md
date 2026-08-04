# Resuscitation Quality Improvement Pipeline — GCP Deployment & BigQuery Warehouse (`D07`, `D07a`)

This specification documents the Google Cloud Platform (`GCP`) service architecture, Terraform infrastructure-as-code ([D07a](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D07a.md)), the five irreversible database decisions, IAM security architecture with empirical negative proof, VPC Service Controls (`VPC-SC`) regional endpoint configuration, and the production cost model.

---

## 1. GCP Services & Architectural Rationale

All cloud resources reside in GCP project `nodepeel`. The architecture leverages serverless managed services to ensure HIPAA compliance, elastic scaling, and strict separation of Protected Health Information (`PHI`):

```
+---------------------------------------------------------------------------------+
|                         GCP PROJECT: nodepeel (VPC-SC Perimeter)                |
|                                                                                 |
|   +--------------------------+               +------------------------------+   |
|   |        Vertex AI         |               |     Google Cloud Storage     |   |
|   |  (us-central1 endpoint)  |               |    (Video / Audio Archive)   |   |
|   +------------+-------------+               +--------------+---------------+   |
|                |                                            |                   |
|                v                                            v                   |
|   +-------------------------------------------------------------------------+   |
|   |                       BigQuery Warehouse (D07)                          |   |
|   |   +-------------------------------+   +-----------------------------+   |   |
|   |   | resus_raw (13 tables)         |   | resus_curated (7 views)     |   |   |
|   |   | (PHI: evidence & utterances)  |   | (Anonymized wide analytics) |   |   |
|   |   +-------------------------------+   +-----------------------------+   |   |
|   +-------------------------------------------------------------------------+   |
+---------------------------------------------------------------------------------+
```

| GCP Service | Primary Usage & Scope | Architectural Rationale |
| :--- | :--- | :--- |
| **BigQuery** | Managed clinical data warehouse (`resus_raw`, `resus_curated`) | Provides ANSI SQL analytical querying, column-level IAM security, and zero-maintenance storage scaling (`D07`). |
| **Vertex AI** | Multimodal LLM inference (`gemini-3.6-flash`, `gemini-3.1-pro-preview`) | Enables generation-time JSON Schema structured output enforcement (`F-002`) and enterprise BAA compliance. |
| **Cloud Storage (`GCS`)** | Archive for raw resuscitation video, audio, and sensor telemetry | Low-cost immutable storage for multi-gigabyte clinical video streams. |
| **Cloud IAM** | Role-based access control and dataset boundary isolation | Strictly separates raw PHI data access from analytical review (`D07a`). |

---

## 2. Terraform Infrastructure Architecture ([D07a](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D07a.md))

All BigQuery datasets, tables, views, and IAM service accounts are provisioned declaratively via Terraform (`infra/`). 

* **State Integrity**: In our baseline deployment (`D07a`), `terraform plan` on `nodepeel` added exactly 17 resources (`13 raw tables`, `2 datasets`, `2 service accounts`) with **zero changes or drift** after `terraform apply`.
* **Automated DDL Deployment (`bq/deploy.py`)**: Executes schema upgrades and seeds `nodepeel:resus_raw.dim_redcap_field` (`909 dictionary fields + 2 system fields = 911 rows`). It verifies dictionary SHA-256 header checksums (`dict_version e7c08437adcef4a5`) before executing DDL.

---

## 3. The Five Irreversible Schema & Deployment Decisions

The following five architectural decisions are structural invariants. Once deployed to production, modifying them would break HIPAA audit boundaries, deduplication guarantees, or API compatibility:

1. **Dataset Separation (`resus_raw` vs. `resus_curated`, [D07](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D07.md))**: Raw PHI tables (`fact_event`, `fact_utterance`) are strictly isolated in `resus_raw`. Curated analytical views (`v_redcap_wide`, `v_exemplar_store`, 6 audit views) reside in `resus_curated`. This boundary cannot be collapsed without violating PHI access controls.
2. **Deterministic SHA Primary Keys**: Every event and interval is keyed by a deterministic hash (`sha1(case_id|type|ordinal)[:12]`, `ingest/loader.py`). This guarantees idempotent ingestion under timestamp drift and cannot be altered without causing duplicate database insertions.
3. **Structural Refusal of Scratch Datasets (`*_scratch`)**: Production deployment scripts (`bq/deploy.py`, `infra/verify_iam.sh`) raise a fatal error if instructed to deploy schema or seed data to any dataset ending in `*_scratch` (`D07`).
4. **Exclusion of Server-Computed Calc Fields from Submission ([D11](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D11.md))**: The REDCap payload assembly engine (`redcap/assemble.py`) permanently excludes the two server-computed calculation fields (`dur_mccd_app_ed_secs_v2`, `duration_ventilator_place_v2`) from API payloads (`IMPORTABLE_COLUMNS` = `1,889`). Submitting calc fields causes REDCap API rejection.
5. **Constitutional Precision Floor (`F-004`)**: The Constitution permanently enforces the `t_precision_s >= 2.0s` timestamp floor in degraded mode, overriding calibration tables. This prevents artificial precision claims when clock sync (`S5`) is unavailable.

---

## 4. IAM Security Architecture & Empirical Negative Proof ([D07a](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D07a.md))

The project defines two dedicated service accounts:
* `sa-analyst@nodepeel.iam.gserviceaccount.com`: For clinical QI analysts and BI dashboard queries.
* `sa-reviewer@nodepeel.iam.gserviceaccount.com`: For human-in-the-loop (`HITL`) reviewers and queue managers.

### 4.1 Empirical Negative Proof Verification (`infra/verify_iam.sh`)
To prove that our IAM bindings prevent PHI leakage, `infra/verify_iam.sh` executes an automated **negative proof test suite** against real BigQuery tables:

```
+---------------------------------------------------------------------------------+
|                       IAM EMPIRICAL NEGATIVE PROOF SUITE                        |
+---------------------------------------------------------------------------------+
| sa-analyst / sa-reviewer ---> SELECT * FROM resus_curated.v_redcap_wide         |
|                               Result: SUCCESS (HTTP 200, 0 rows returned)       |
+---------------------------------------------------------------------------------+
| sa-analyst / sa-reviewer ---> SELECT evidence FROM resus_raw.fact_event         |
|                               Result: HTTP 403 PERMISSION_DENIED (PHI Denied)   |
+---------------------------------------------------------------------------------+
| sa-analyst / sa-reviewer ---> SELECT transcript FROM resus_raw.fact_utterance   |
|                               Result: HTTP 403 PERMISSION_DENIED (PHI Denied)   |
+---------------------------------------------------------------------------------+
```

* **Positive Proof (Curated Access)**: Verifies that `sa-analyst` and `sa-reviewer` query `resus_curated.v_redcap_wide` and `resus_curated.v_exemplar_store` successfully without error (`0` rows returned on empty tables).
* **Negative Proof (PHI Access Denial)**: Verifies that direct queries by `sa-analyst` or `sa-reviewer` against `resus_raw.fact_utterance` (diarized leader transcripts) or `resus_raw.fact_event.evidence` (verbatim audio quotes) are rejected by BigQuery with an explicit **`HTTP 403 PERMISSION_DENIED`** error ([D07a](file:///Users/emailandy/Documents/Code/Cardiac%20Memory/resus_qc/docs/tasks/D07a.md)).

---

## 5. VPC-SC and the Global-Endpoint Conflict

GCP project `nodepeel` is protected by a VPC Service Controls (`VPC-SC`) security perimeter that prohibits data egress across unmanaged network boundaries.

* **The Global-Endpoint Conflict**: By default, the Google Cloud Vertex AI SDK connects to the global API endpoint (`aiplatform.googleapis.com`). In a strict VPC-SC perimeter, requests to global endpoints are blocked as external network egress, causing connection failures.
* **The Regional Resolution**: Our execution client (`pipeline/vertex_client.py`) explicitly binds all Vertex AI API client sessions to the regional endpoint:
  ```python
  # Regional endpoint binding to satisfy VPC-SC perimeter rules
  client_options = {"api_endpoint": "us-central1-aiplatform.googleapis.com"}
  ```

---

## 6. Cloud Resource & Storage Cost Model

| GCP Service / Resource | Pricing Metric / Unit | Unit Rate ($ USD) | Est. Monthly Production Cost (100 Cases / Mo) |
| :--- | :--- | :--- | :--- |
| **Vertex AI (`gemini-3.6-flash`)** | 1M Input / Output Tokens | $0.075 / $0.30 | ~$40.00 |
| **Vertex AI (`gemini-3.1-pro-preview`)** | 1M Input / Output Tokens | $1.25 / $5.00 | ~$90.00 |
| **BigQuery Storage (`resus_raw` + `curated`)** | Active Storage / GB / Month | $0.020 / GB | < $1.00 (~50 GB) |
| **BigQuery Analysis Queries** | On-Demand Bytes Scanned / TB | $6.25 / TB | < $5.00 |
| **Cloud Storage (`GCS` Video Archive)** | Standard Storage / GB / Month | $0.020 / GB | ~$20.00 (~1,000 GB) |
| **Total Monthly GCP Infrastructure** | — | — | **~$156.00 / month** |

---
Last verified: 2026-08-03 against dict_version e7c08437adcef4a5, prompt_set_sha 12280b94c0c134e8
