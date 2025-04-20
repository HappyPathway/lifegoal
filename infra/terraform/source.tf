/**
 * Source code packaging configuration for LifeGoal Cloud Functions
 * Handles zipping and uploading function source code to GCS
 */

# GCS bucket for storing function source code
resource "google_storage_bucket" "function_source" {
  name          = "${local.resource_suffix}-functions"
  location      = var.region
  force_destroy = true
  
  # No need for versioning as we only use this bucket for deployment
  versioning {
    enabled = false
  }
  
  uniform_bucket_level_access = true
  
  labels = local.tags
}

# Create an archive of the Slack webhook function source
data "archive_file" "slack_webhook_zip" {
  type        = "zip"
  output_path = "/tmp/slack_webhook_source.zip"
  source_dir  = "${path.root}/../../functions/slack_webhook"
  excludes    = ["__pycache__", "*.pyc", "*.pyo"]
}

# Upload the packaged Slack webhook function to GCS
resource "google_storage_bucket_object" "slack_webhook_source" {
  name   = "slack_webhook_source_${data.archive_file.slack_webhook_zip.output_md5}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.slack_webhook_zip.output_path
}

# Create an archive of the summary generator function source
data "archive_file" "summary_generator_zip" {
  type        = "zip"
  output_path = "/tmp/summary_generator_source.zip"
  source_dir  = "${path.root}/../../functions/summary_generator"
  excludes    = ["__pycache__", "*.pyc", "*.pyo"]
}

# Upload the packaged summary generator function to GCS
resource "google_storage_bucket_object" "summary_generator_source" {
  name   = "summary_generator_source_${data.archive_file.summary_generator_zip.output_md5}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.summary_generator_zip.output_path
}