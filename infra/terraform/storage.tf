/**
 * Storage configuration for LifeGoal project
 * Sets up GCS bucket with versioning for SQLite database storage
 */

# GCS bucket for storing SQLite database
resource "google_storage_bucket" "db_storage" {
  name          = var.gcs_bucket_name != null ? var.gcs_bucket_name : "${local.resource_suffix}-db"
  location      = var.region
  force_destroy = var.environment != "prod"
  
  # Enable versioning to track database changes
  versioning {
    enabled = true
  }
  
  # Lifecycle rule to delete old versions after 30 days in non-prod environments
  dynamic "lifecycle_rule" {
    for_each = var.environment != "prod" ? [1] : []
    content {
      condition {
        num_newer_versions = 10
        age = 30  # days
      }
      action {
        type = "Delete"
      }
    }
  }
  
  uniform_bucket_level_access = true
  
  labels = local.tags
}