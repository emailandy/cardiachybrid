# Clinical Video Storage Archive
resource "google_storage_bucket" "clinical_video" {
  name     = "${var.project_id}-clinical-video-${var.environment}"
  project  = var.project_id
  location = var.region

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  # TODO(Q-020): Video retention policy is currently blocked pending IRB / clinical lead review.
  # Do we delete raw video after 30 days, or retain indefinitely as the source of truth?
  # lifecycle_rule {
  #   action {
  #     type = "Delete"
  #   }
  #   condition {
  #     age = ???
  #   }
  # }

  dynamic "encryption" {
    for_each = var.cmek_kms_key_name != "" ? [var.cmek_kms_key_name] : []
    content {
      default_kms_key_name = encryption.value
    }
  }
}

# Grant sa_ingest object read access (pipeline consumption)
resource "google_storage_bucket_iam_member" "ingest_video_reader" {
  bucket = google_storage_bucket.clinical_video.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.sa_ingest.email}"
}

# Note: sa_analyst and sa_reviewer are deliberately NOT granted access to this bucket.
# Consistent with resus_raw denial boundary, raw video PHI is inaccessible to downstream analysts.
