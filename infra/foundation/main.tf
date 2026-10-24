# ---- Persistent foundation: survives the daily cluster destroy ----
terraform {
  required_providers {
    google = { source = "hashicorp/google", version = ">= 6.0" }
  }
  backend "gcs" {
    bucket = "nexusforge-ai-dev-wallettrackerai-00-tfstate"
    prefix = "foundation"
  }
}

variable "project_id"  { default = "nexusforge-ai-dev" }
variable "region"      { default = "us-east4" }
variable "github_repo" { default = "e00049/j4-learning-workspace" }

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_project_service" "apis" {
  for_each           = toset(["iam.googleapis.com", "iamcredentials.googleapis.com", "sts.googleapis.com"])
  service            = each.value
  disable_on_destroy = false
}

resource "google_iam_workload_identity_pool" "gh" {
  workload_identity_pool_id = "wallettrackerai-gh-pool"
  display_name              = "GitHub Actions"
  depends_on                = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "gh" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.gh.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub OIDC"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }
  # Only THIS repo, only the main branch. Forks and PRs get nothing.
  attribute_condition = "assertion.repository == '${var.github_repo}' && assertion.ref == 'refs/heads/main'"
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "deployer" {
  account_id   = "wallettrackerai-24-deployer-sa"
  display_name = "GitHub Actions deployer (images + helm)"
}

# GitHub (this repo) may act as the deployer SA
resource "google_service_account_iam_member" "wif" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.gh.name}/attribute.repository/${var.github_repo}"
}

# What the deployer may do: push images, deploy to GKE. Nothing else (no Terraform, no IAM).
resource "google_project_iam_member" "deployer" {
  for_each = toset(["roles/artifactregistry.writer", "roles/container.developer"])
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.deployer.email}"
}

output "wif_provider" { value = google_iam_workload_identity_pool_provider.gh.name }
output "deployer_sa"  { value = google_service_account.deployer.email }
