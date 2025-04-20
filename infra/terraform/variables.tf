/**
 * Variables for LifeGoal Terraform configuration
 */

variable "project_id" {
  description = "Google Cloud Project ID"
  type        = string
}

variable "region" {
  description = "Default region for resources"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "gcs_bucket_name" {
  description = "Name of the GCS bucket for storing SQLite database"
  type        = string
  default     = null
}

variable "db_name" {
  description = "Name of the SQLite database file"
  type        = string
  default     = "lifegoal.db"
}

variable "slack_webhook_memory" {
  description = "Memory allocation for slack webhook function (in MB)"
  type        = number
  default     = 256
}

variable "summary_generator_memory" {
  description = "Memory allocation for summary generator function (in MB)"
  type        = number
  default     = 512
}

variable "slack_webhook_timeout" {
  description = "Timeout for slack webhook function (in seconds)"
  type        = number
  default     = 60
}

variable "summary_generator_timeout" {
  description = "Timeout for summary generator function (in seconds)"
  type        = number
  default     = 300
}

variable "service_account_email" {
  description = "Service account email for Cloud Functions"
  type        = string
  default     = null
}