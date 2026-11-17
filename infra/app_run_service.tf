# infra/app_run_service.tf
# Deploys the Interactive Control Center UI & Live Extraction Engine (`ui/server.py`)
# as a stateful single-instance Google Cloud Run v2 Service (Gen2).

resource "google_service_account" "sa_ui" {
  project      = var.project_id
  account_id   = "sa-ui-control-center"
  display_name = "CardiacHybrid AI-CARES Control Center Service Account"
  description  = "Runtime identity for the Cloud Run Control Center UI and Live Extraction Engine."
}

# Grant Vertex AI inference access for live Gemini-4-Argon / Flash runs
resource "google_project_iam_member" "ui_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.sa_ui.email}"
}

# Grant read/write access on the clinical video bucket for staging & Gen2 FUSE streaming
resource "google_storage_bucket_iam_member" "ui_video_object_user" {
  bucket = google_storage_bucket.clinical_video.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.sa_ui.email}"
}

# Grant read access strictly to curated BigQuery views (consistent with resus_raw PHI boundary)
resource "google_bigquery_dataset_iam_member" "ui_curated_viewer" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.resus_curated.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.sa_ui.email}"
}

resource "google_project_iam_member" "ui_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.sa_ui.email}"
}

resource "google_cloud_run_v2_service" "control_center" {
  project  = var.project_id
  name     = var.ui_service_name
  location = var.region
  ingress  = var.ui_ingress

  template {
    execution_environment = "EXECUTION_ENVIRONMENT_GEN2"
    service_account       = google_service_account.sa_ui.email
    timeout               = "3600s"
    session_affinity      = true

    # Single stateful instance ensures in-memory WORKSPACE & LIVE_JOBS polling stay consistent
    scaling {
      min_instance_count = var.ui_min_instances
      max_instance_count = 1
    }

    volumes {
      name = "clinical-video-vol"
      gcs {
        bucket    = google_storage_bucket.clinical_video.name
        read_only = false
      }
    }

    containers {
      image = var.ui_container_image != "" ? var.ui_container_image : "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.pipeline_repo.repository_id}/control-center:latest"

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "4"
          memory = "8Gi"
        }
        # CRITICAL: Keep CPU allocated between HTTP requests so background LiveEngineJob
        # threads (ffmpeg, S1-S7 sensors, Vertex AI passes) are never throttled after POST /api/jobs/live returns.
        cpu_idle          = false
        startup_cpu_boost = true
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "AICARES_GCS_BUCKET"
        value = google_storage_bucket.clinical_video.name
      }
      env {
        name  = "AICARES_VIDEO_DIR"
        value = "/mnt/videos"
      }
      env {
        name  = "GOOGLE_API_USE_CLIENT_CERTIFICATE"
        value = "false"
      }

      volume_mounts {
        name       = "clinical-video-vol"
        mount_path = "/mnt/videos"
      }

      startup_probe {
        http_get {
          path = "/healthz"
          port = 8080
        }
        initial_delay_seconds = 3
        period_seconds        = 5
        timeout_seconds       = 3
        failure_threshold     = 12
      }

      liveness_probe {
        http_get {
          path = "/healthz"
          port = 8080
        }
        period_seconds    = 30
        timeout_seconds   = 5
        failure_threshold = 3
      }
    }
  }

  depends_on = [
    google_project_service.run,
    google_artifact_registry_repository.pipeline_repo,
    google_service_account.sa_ui,
    google_storage_bucket_iam_member.ui_video_object_user,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  count    = var.allow_unauthenticated_ui ? 1 : 0
  project  = google_cloud_run_v2_service.control_center.project
  location = google_cloud_run_v2_service.control_center.location
  name     = google_cloud_run_v2_service.control_center.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
