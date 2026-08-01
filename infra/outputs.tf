# infra/outputs.tf
# Core dataset IDs and service account email outputs for D07a.

output "resus_raw_dataset_id" {
  description = "Dataset ID for physical base tables (PHI restricted)."
  value       = google_bigquery_dataset.resus_raw.dataset_id
}

output "resus_curated_dataset_id" {
  description = "Dataset ID for authorized non-PHI views."
  value       = google_bigquery_dataset.resus_curated.dataset_id
}

output "resus_scratch_dataset_id" {
  description = "Dataset ID for ephemeral scratch and near-miss evaluation."
  value       = google_bigquery_dataset.resus_scratch.dataset_id
}

output "sa_ingest_email" {
  description = "Email of pipeline ingestion service account."
  value       = google_service_account.sa_ingest.email
}

output "sa_analyst_email" {
  description = "Email of analyst service account (curated view access only)."
  value       = google_service_account.sa_analyst.email
}

output "sa_reviewer_email" {
  description = "Email of clinical reviewer service account (curated view access only)."
  value       = google_service_account.sa_reviewer.email
}

output "sa_deploy_email" {
  description = "Email of schema DDL deployer service account."
  value       = google_service_account.sa_deploy.email
}
