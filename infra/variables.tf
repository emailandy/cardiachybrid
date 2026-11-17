# infra/variables.tf
# NOTE: No remote state backend or provider credential block is configured here.
# State storage and auth are environment decisions the human makes.
# Uncomment and configure backend in your wrapper/environment as needed:
# terraform {
#   backend "gcs" {
#     bucket = "YOUR-TERRAFORM-STATE-BUCKET"
#     prefix = "resus-qc/prod"
#   }
# }

variable "project_id" {
  description = "The Google Cloud project ID where BigQuery resources will be deployed."
  type        = string
}

variable "region" {
  description = "Single region for all datasets, CMEK, and resources (fixed at creation per IRB compliance)."
  type        = string
  default     = "us-east4"
}

variable "environment" {
  description = "Deployment environment (e.g. dev, staging, prod)."
  type        = string
  default     = "dev"
}

variable "cmek_kms_key_name" {
  description = "Optional Cloud KMS CryptoKey resource ID for CMEK dataset encryption."
  type        = string
  default     = ""
}

variable "vpc_sc_perimeter_name" {
  description = "Optional Access Context Manager Service Perimeter name for VPC-SC restriction."
  type        = string
  default     = ""
}

variable "ui_service_name" {
  description = "Cloud Run service name for the Interactive Control Center UI."
  type        = string
  default     = "cardiachybrid-control-center"
}

variable "ui_container_image" {
  description = "Optional explicit Artifact Registry image URI for the Control Center service."
  type        = string
  default     = ""
}

variable "ui_ingress" {
  description = "Cloud Run ingress traffic policy (INGRESS_TRAFFIC_ALL, INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER, INGRESS_TRAFFIC_INTERNAL_ONLY)."
  type        = string
  default     = "INGRESS_TRAFFIC_ALL"
}

variable "ui_min_instances" {
  description = "Minimum warm instances for the Control Center UI (set to 1 during live executive demos to eliminate cold starts)."
  type        = number
  default     = 0
}

variable "allow_unauthenticated_ui" {
  description = "Whether to grant roles/run.invoker to allUsers. Keep false for clinical/PHI environments (use IAM or IAP)."
  type        = bool
  default     = false
}
