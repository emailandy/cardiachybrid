# Resuscitation QC (`resus_qc`) — BigQuery Infrastructure

This directory contains Terraform definitions for the BigQuery layer of the resuscitation quality control data warehouse.

## 1. Region Architecture & IRB Compliance (`us-east4`)

All BigQuery datasets and related resources in this directory use **single region `us-east4`** (`DECISION 014`).

**Rationale**:
Institutional PHI requires the narrowest defensible footprint. US multi-region replication spreads data across geographies you do not control and cannot name precisely to an Institutional Review Board (IRB). When asked "where does this data physically live," you need a one-sentence answer (`us-east4`). Cost difference is noise at this volume.
*Note: BigQuery dataset region is **FIXED AT DATASET CREATION** — changing it later requires recreating and reloading every table.*

## 2. State & Authentication

**No remote state backend or provider credential block is configured in code.**
State storage and authentication are environment decisions the human makes; a committed backend config pointed at the wrong bucket is worse than none. See `infra/variables.tf` for commented placeholder examples for configuring GCS state backends in your wrapper or environment.

## 3. Dataset Topology

Three core datasets are deployed:
1. `resus_raw`: Physical base tables (`fact_utterance`, `fact_event`, `fact_interval`, etc.). Contains clinical PHI and verbatim audio/evidence quotes. Encrypted with CMEK when KMS keys are provided.
2. `resus_curated`: Authorized views over `resus_raw` (`v_redcap_wide`, `v_exemplar_store`, `v_fact_event`). Views project non-PHI attributes and timestamps while omitting sensitive columns (such as `fact_event.evidence` and `fact_utterance.text`).
3. `resus_scratch`: Ephemeral scratch and evaluation dataset for testing deployments and storing `near_miss` evaluation records.

### Authorized View Authorization
`resus_curated` is granted `VIEWS` access to `resus_raw` (`google_bigquery_dataset_access.curated_views_access`). This allows views in `resus_curated` to query physical tables in `resus_raw` without callers having direct IAM read access to `resus_raw`.

## 4. Service Account Model & Least Privilege

Four service accounts are managed in `infra/iam.tf`:
- `sa-ingest`: Pipeline ingestion loader. Granted `roles/bigquery.dataEditor` on `resus_raw` and `resus_scratch` only.
- `sa-analyst`: Data analyst account. Granted `roles/bigquery.dataViewer` **strictly on `resus_curated`**. ZERO IAM bindings exist on `resus_raw`, ensuring queries against `fact_utterance` or `fact_event.evidence` return `PERMISSION_DENIED`.
- `sa-reviewer`: Clinical reviewer account. Granted `roles/bigquery.dataViewer` **strictly on `resus_curated`** to query `v_exemplar_store` (an authorized view joining `fact_event` and `fact_redcap_field`). ZERO direct base table access.
- `sa-deploy`: DDL deployment account. On production environments, this service account has no human-assumable roles and must be bound strictly to CI/CD Workload Identity Federation (`TODO(CI-FEDERATION)` in `infra/iam.tf`).

## 5. Embedding Storage Governance (`Q-011`)

`fact_utterance.text_embedding` (`ARRAY<FLOAT64>`) is explicitly **DROPPED** from table DDL and schema definitions (`Q-011`, deferred).
Voice and text embeddings derived from clinical audio are derived PHI, and voice embeddings may be biometric identifiers under institutional interpretations. Storage of embeddings is deferred until the retrieval layer is implemented under independent IRB and governance review.
