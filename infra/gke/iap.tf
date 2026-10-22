# ---- Phase E: IAP access for humans + one machine client ----
variable "iap_users" {
  description = "Principals allowed through IAP, e.g. user:me@gmail.com"
  type        = list(string)
}

resource "google_project_service" "iap" {
  service            = "iap.googleapis.com"
  disable_on_destroy = false
}

resource "google_service_account" "caller" {
  account_id   = "wallettrackerai-16-caller-sa"
  display_name = "Machine client for agent-api via IAP"
}

# Humans: allowed through IAP
resource "google_project_iam_member" "iap_users" {
  for_each = toset(var.iap_users)
  project  = google_service_account.caller.project
  role     = "roles/iap.httpsResourceAccessor"
  member   = each.value
}

# Machine client: allowed through IAP
resource "google_project_iam_member" "iap_caller" {
  project = google_service_account.caller.project
  role    = "roles/iap.httpsResourceAccessor"
  member  = "serviceAccount:${google_service_account.caller.email}"
}

# You may mint ID tokens as the caller SA (for curl tests)
resource "google_service_account_iam_member" "impersonate" {
  for_each           = toset(var.iap_users)
  service_account_id = google_service_account.caller.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = each.value
}
