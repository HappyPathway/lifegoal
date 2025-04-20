/**
 * Terraform outputs for LifeGoal project
 * Provides important deployment information
 */

output "slack_webhook_url" {
  description = "URL of the deployed Slack webhook function"
  value       = google_cloudfunctions_function.slack_webhook.https_trigger_url
}

output "db_storage_bucket" {
  description = "GCS bucket name for SQLite database storage"
  value       = google_storage_bucket.db_storage.name
}

output "service_account" {
  description = "Service account used by Cloud Functions"
  value       = local.service_account
}

output "summary_generator_trigger_topic" {
  description = "Pub/Sub topic name for triggering summary generation"
  value       = google_pubsub_topic.summary_trigger.name
}

output "weekly_summary_schedule" {
  description = "Scheduled time for weekly summary generation"
  value       = google_cloud_scheduler_job.weekly_summary_trigger.schedule
}