# app_run_job.tf
# This script deploys the resus_qc Python pipeline as a Google Cloud Run Job.

# Enable required APIs for deploying the app
resource "google_project_service" "cloudbuild" {
  project            = var.project_id
  service            = "cloudbuild.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "artifactregistry" {
  project            = var.project_id
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "run" {
  project            = var.project_id
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

# Create an Artifact Registry repository to hold the pipeline Docker images
resource "google_artifact_registry_repository" "pipeline_repo" {
  project       = var.project_id
  location      = var.region
  repository_id = "resus-qc-repo"
  description   = "Docker repository for Cardiac Memory resus_qc pipeline"
  format        = "DOCKER"

  depends_on = [google_project_service.artifactregistry]
}

# Define the Cloud Run Job for the pipeline
resource "google_cloud_run_v2_job" "pipeline_job" {
  project  = var.project_id
  name     = "resus-qc-pipeline-job"
  location = var.region

  template {
    template {
      containers {
        # Replace this with the actual pushed image path
        image = "${var.region}-docker.pkg.dev/${var.project_id}/resus-qc-repo/pipeline:latest"
        
        resources {
          limits = {
            cpu    = "2"
            memory = "4Gi"
          }
        }
        
        # Inject necessary environment variables for the pipeline
        env {
          name  = "PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "REGION"
          value = var.region
        }
        # Assuming we use the sa-ingest service account defined in iam.tf
        # to run the pipeline workload.
      }
      # The service account that the Cloud Run job will execute as
      service_account = google_service_account.ingest.email
      timeout = "3600s" # 1 hour max runtime
    }
  }

  depends_on = [
    google_project_service.run,
    google_artifact_registry_repository.pipeline_repo,
    google_service_account.ingest
  ]
}
