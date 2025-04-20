/**
 * Main Terraform configuration for LifeGoal project
 * Sets up Google Cloud provider and backend configuration
 */

terraform {
  required_version = ">= 1.0.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.80.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 4.80.0"
    }
  }
  
  # Uncomment to use a GCS bucket as the backend
  # backend "gcs" {
  #   bucket = "lifegoal-terraform-state"
  #   prefix = "terraform/state"
  # }
}

# Google Cloud provider configuration
provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# Random string for unique resource naming
resource "random_id" "default" {
  byte_length = 2
}

# Local variables for resource naming
locals {
  app_name       = "lifegoal"
  resource_suffix = "${local.app_name}-${random_id.default.hex}"
  tags = {
    application = local.app_name
    terraform   = "true"
    environment = var.environment
  }
}