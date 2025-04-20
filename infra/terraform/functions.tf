/**
 * Cloud Functions configuration for LifeGoal project
 * Deploys the Slack webhook and Summary generator functions
 */

# Slack webhook function
resource "google_cloudfunctions_function" "slack_webhook" {
  name                  = "${local.app_name}-slack-webhook"
  description           = "Handles Slack interactions for LifeGoal assistant"
  runtime               = "python310"
  region                = var.region
  available_memory_mb   = var.slack_webhook_memory
  source_archive_bucket = google_storage_bucket.function_source.name
  source_archive_object = google_storage_bucket_object.slack_webhook_source.name
  timeout               = var.slack_webhook_timeout
  entry_point           = "slack_webhook"
  service_account_email = local.service_account
  
  # Set as HTTP trigger
  trigger_http          = true
  
  # Environment variables
  environment_variables = {
    GCS_BUCKET_NAME = google_storage_bucket.db_storage.name
    DB_NAME         = var.db_name
    ENVIRONMENT     = var.environment
  }

  # Secret environment variables (to be retrieved from Secret Manager)
  secret_environment_variables {
    key        = "SLACK_SIGNING_SECRET"
    project_id = var.project_id
    secret     = "slack_signing_secret"
    version    = "latest"
  }
  
  labels = local.tags
}

# Allow public access to the function
resource "google_cloudfunctions_function_iam_member" "slack_webhook_invoker" {
  project        = google_cloudfunctions_function.slack_webhook.project
  region         = google_cloudfunctions_function.slack_webhook.region
  cloud_function = google_cloudfunctions_function.slack_webhook.name
  role           = "roles/cloudfunctions.invoker"
  member         = "allUsers"
}

# Summary generator function
resource "google_cloudfunctions_function" "summary_generator" {
  name                  = "${local.app_name}-summary-generator"
  description           = "Generates daily and weekly wellness summaries"
  runtime               = "python310"
  region                = var.region
  available_memory_mb   = var.summary_generator_memory
  source_archive_bucket = google_storage_bucket.function_source.name
  source_archive_object = google_storage_bucket_object.summary_generator_source.name
  timeout               = var.summary_generator_timeout
  entry_point           = "weekly_summary"  # The function name in main.py
  service_account_email = local.service_account
  
  # Set up Pub/Sub trigger
  event_trigger {
    event_type = "google.pubsub.topic.publish"
    resource   = google_pubsub_topic.summary_trigger.name
  }
  
  # Environment variables
  environment_variables = {
    GCS_BUCKET_NAME = google_storage_bucket.db_storage.name
    DB_NAME         = var.db_name
    ENVIRONMENT     = var.environment
  }
  
  labels = local.tags
}

# Create Pub/Sub topic for triggering summary generation
resource "google_pubsub_topic" "summary_trigger" {
  name   = "${local.app_name}-summary-trigger"
  labels = local.tags
}

# Create Cloud Scheduler job to trigger weekly summaries
resource "google_cloud_scheduler_job" "weekly_summary_trigger" {
  name             = "${local.app_name}-weekly-summary-job"
  description      = "Triggers generation of weekly wellness summaries"
  schedule         = "0 9 * * SUN"  # 9 AM every Sunday
  time_zone        = "America/Los_Angeles"
  attempt_deadline = "320s"

  pubsub_target {
    topic_name = google_pubsub_topic.summary_trigger.id
    data       = base64encode("{\"type\": \"weekly\"}")
  }
}