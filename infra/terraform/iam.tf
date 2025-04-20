/**
 * IAM configuration for LifeGoal project
 * Sets up service accounts and permissions for Cloud Functions
 */

# Service account for Cloud Functions if not provided
resource "google_service_account" "functions_service_account" {
  count        = var.service_account_email == null ? 1 : 0
  account_id   = "${local.app_name}-functions-sa"
  display_name = "Service Account for LifeGoal Cloud Functions"
  description  = "Used by Cloud Functions to access GCS and Secret Manager"
}

locals {
  service_account = var.service_account_email != null ? var.service_account_email : google_service_account.functions_service_account[0].email
}

# Grant the service account access to the GCS bucket
resource "google_storage_bucket_iam_member" "function_gcs_access" {
  bucket = google_storage_bucket.db_storage.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${local.service_account}"
}

# Grant the service account access to Secret Manager
resource "google_project_iam_member" "secret_manager_access" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${local.service_account}"
}