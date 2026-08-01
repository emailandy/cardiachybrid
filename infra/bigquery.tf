# infra/bigquery.tf
# Three core datasets for resuscitation quality control data warehouse:
#   1. resus_raw: Physical base tables (PHI restricted, CMEK encrypted).
#   2. resus_curated: Authorized views projecting non-PHI / redacted schema.
#   3. resus_scratch: Ephemeral scratch/eval dataset for test runs and near-miss eval.
#
# -----------------------------------------------------------------------------
# AUDIT LOGGING & DELETION PROTECTION POLICY
# 1. Audit Logging: Full Data Access READ and WRITE audit logs (DATA_READ, DATA_WRITE, ADMIN_READ)
#    are enabled across all BigQuery datasets (resus_raw, resus_curated, resus_scratch) via bq_audit.
# 2. Deletion Protection: For production (var.environment == "prod"), dataset deletion protection
#    is enforced by delete_contents_on_destroy = false. Furthermore, all physical tables deployed
#    into resus_raw MUST enforce deletion_protection = true in prod to prevent accidental PHI loss.
# 3. CMEK Encryption: var.cmek_kms_key_name is a variable awaiting a Cloud KMS CryptoKey resource ID.
#    If left unset (""), encryption falls back to Google-managed keys (permitted only in dev/test).
#    In production, an explicit KMS key with automatic rotation MUST be supplied.
# -----------------------------------------------------------------------------


resource "google_bigquery_dataset" "resus_raw" {
  project                    = var.project_id
  dataset_id                 = "resus_raw"
  friendly_name              = "Resuscitation QC Raw PHI Tables"
  description                = "Physical fact and dim base tables containing clinical PHI (e.g. fact_utterance, fact_event.evidence)."
  location                   = var.region
  delete_contents_on_destroy = var.environment != "prod"

  dynamic "default_encryption_configuration" {
    for_each = var.cmek_kms_key_name != "" ? [var.cmek_kms_key_name] : []
    content {
      kms_key_name = default_encryption_configuration.value
    }
  }
}

resource "google_bigquery_dataset" "resus_curated" {
  project                    = var.project_id
  dataset_id                 = "resus_curated"
  friendly_name              = "Resuscitation QC Curated Views"
  description                = "Authorized views over resus_raw (v_redcap_wide, v_exemplar_store, v_fact_event without evidence JSON)."
  location                   = var.region
  delete_contents_on_destroy = var.environment != "prod"

  dynamic "default_encryption_configuration" {
    for_each = var.cmek_kms_key_name != "" ? [var.cmek_kms_key_name] : []
    content {
      kms_key_name = default_encryption_configuration.value
    }
  }
}

resource "google_bigquery_dataset" "resus_scratch" {
  project                    = var.project_id
  dataset_id                 = "resus_scratch"
  friendly_name              = "Resuscitation QC Scratch and Eval Dataset"
  description                = "Scratch dataset for deployment testing, near_miss eval tables, and temporary CI runs."
  location                   = var.region
  delete_contents_on_destroy = var.environment != "prod"

  default_table_expiration_ms = var.environment == "prod" ? 604800000 : 86400000 # 7 days prod, 1 day dev

  dynamic "default_encryption_configuration" {
    for_each = var.cmek_kms_key_name != "" ? [var.cmek_kms_key_name] : []
    content {
      kms_key_name = default_encryption_configuration.value
    }
  }
}

# Authorize all views in resus_curated to read physical tables in resus_raw
# without granting callers direct IAM read access to resus_raw.
resource "google_bigquery_dataset_access" "curated_views_access" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.resus_raw.dataset_id

  dataset {
    dataset {
      project_id = var.project_id
      dataset_id = google_bigquery_dataset.resus_curated.dataset_id
    }
    target_types = ["VIEWS"]
  }
}

# Full BigQuery Audit Logging (ADMIN_READ, DATA_WRITE, DATA_READ) per IRB & PHI governance.
resource "google_project_iam_audit_config" "bq_audit" {
  project = var.project_id
  service = "bigquery.googleapis.com"

  audit_log_config {
    log_type = "ADMIN_READ"
  }
  audit_log_config {
    log_type = "DATA_WRITE"
  }
  audit_log_config {
    log_type = "DATA_READ"
  }
}
