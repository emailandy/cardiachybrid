# API Enablement for resus_qc runtime
# Evidence of usage:
# - aiplatform.googleapis.com: Called by pipeline/vertex_client.py for LLM inference (gemini-3.1-pro-preview).
# - storage.googleapis.com: Accessed in scripts/run_case.py (e.g. gs://videval/cardiac/simvideo2.mp4).
# - bigquery.googleapis.com: Used by pipeline/bq_writer.py and bq/deploy.py for writing event streams.
# - logging.googleapis.com: Expected for baseline audit/Vertex telemetry and pipeline structured logging.

resource "google_project_service" "aiplatform" {
  project            = var.project_id
  service            = "aiplatform.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "storage" {
  project            = var.project_id
  service            = "storage.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "bigquery" {
  project            = var.project_id
  service            = "bigquery.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "logging" {
  project            = var.project_id
  service            = "logging.googleapis.com"
  disable_on_destroy = false
}
