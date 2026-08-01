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
