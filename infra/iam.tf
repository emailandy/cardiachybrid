# infra/iam.tf
# Four core service accounts and their least-privilege IAM bindings:
#   1. sa-ingest: Pipeline loader writing to resus_raw and resus_scratch.
#   2. sa-analyst: Reads ONLY curated views in resus_curated (no access to resus_raw).
#   3. sa-reviewer: Reads ONLY curated views (e.g. v_exemplar_store) in resus_curated.
#   4. sa-deploy: DDL and schema deployment SA (no human-assumable roles in prod).

resource "google_service_account" "sa_ingest" {
  project      = var.project_id
  account_id   = "sa-ingest"
  display_name = "Resuscitation QC Ingestion Service Account"
  description  = "Writes normalized clinical events, intervals, and utterances into resus_raw."
}

resource "google_service_account" "sa_analyst" {
  project      = var.project_id
  account_id   = "sa-analyst"
  display_name = "Resuscitation QC Analyst Service Account"
  description  = "Query access to authorized views in resus_curated only. ZERO access to resus_raw PHI."
}

resource "google_service_account" "sa_reviewer" {
  project      = var.project_id
  account_id   = "sa-reviewer"
  display_name = "Resuscitation QC Clinical Reviewer Service Account"
  description  = "Read access to authorized review views (e.g. v_exemplar_store) in resus_curated only."
}

resource "google_service_account" "sa_deploy" {
  project      = var.project_id
  account_id   = "sa-deploy"
  display_name = "Resuscitation QC Deployer Service Account"
  description  = "Manages BigQuery table DDL, schema updates, and authorized views."
}

# -----------------------------------------------------------------------------
# 1. Ingest SA Bindings (Write access to resus_raw and resus_scratch)
# -----------------------------------------------------------------------------
resource "google_bigquery_dataset_iam_member" "ingest_raw_editor" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.resus_raw.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.sa_ingest.email}"
}

resource "google_bigquery_dataset_iam_member" "ingest_scratch_editor" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.resus_scratch.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.sa_ingest.email}"
}

resource "google_project_iam_member" "ingest_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.sa_ingest.email}"
}

# -----------------------------------------------------------------------------
# 2. Analyst SA Bindings (Read access strictly to resus_curated)
#    CRITICAL: No bindings on resus_raw. SELECT from fact_utterance or
#              fact_event.evidence returns PERMISSION_DENIED.
# -----------------------------------------------------------------------------
resource "google_bigquery_dataset_iam_member" "analyst_curated_viewer" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.resus_curated.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.sa_analyst.email}"
}

resource "google_project_iam_member" "analyst_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.sa_analyst.email}"
}

# -----------------------------------------------------------------------------
# 3. Reviewer SA Bindings (Read access strictly to resus_curated)
#    CRITICAL: No bindings on resus_raw. Can query v_exemplar_store in
#              resus_curated without direct base table access.
# -----------------------------------------------------------------------------
resource "google_bigquery_dataset_iam_member" "reviewer_curated_viewer" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.resus_curated.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.sa_reviewer.email}"
}

resource "google_project_iam_member" "reviewer_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.sa_reviewer.email}"
}

# -----------------------------------------------------------------------------
# 4. Deployer SA Bindings (DDL admin across datasets)
# -----------------------------------------------------------------------------
resource "google_project_iam_member" "deploy_bq_admin" {
  project = var.project_id
  role    = "roles/bigquery.admin"
  member  = "serviceAccount:${google_service_account.sa_deploy.email}"
}

# TODO(CI-FEDERATION): On production (var.environment == "prod"), sa-deploy MUST NOT be
# human-assumable. Do not grant roles/iam.serviceAccountUser or roles/iam.serviceAccountTokenCreator
# to human users or developers. Bind this service account strictly to CI/CD Workload Identity
# Federation (OIDC) via google_service_account_iam_binding with PrincipalSet for the gated CI repo.
# Example:
# resource "google_service_account_iam_member" "ci_oidc_binding" {
#   count              = var.environment == "prod" ? 1 : 0
#   service_account_id = google_service_account.sa_deploy.name
#   role               = "roles/iam.workloadIdentityUser"
#   member             = "principalSet://iam.googleapis.com/projects/YOUR_PROJECT_NUM/locations/global/workloadIdentityPools/YOUR_POOL/attribute.repository/YOUR_ORG/resus_qc"
# }

# Pipeline Vertex AI inference access
resource "google_project_iam_member" "ingest_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.sa_ingest.email}"
}
