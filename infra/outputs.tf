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

output "clinical_video_bucket_name" {
  description = "The name of the GCS bucket storing raw clinical video."
  value       = google_storage_bucket.clinical_video.name
}

output "control_center_service_url" {
  description = "HTTPS endpoint URL of the deployed Cloud Run Control Center UI."
  value       = google_cloud_run_v2_service.control_center.uri
}

output "sa_ui_email" {
  description = "Email of the Cloud Run Control Center service account."
  value       = google_service_account.sa_ui.email
}
