# Identity used by agent-api pods to call Vertex AI
resource "google_service_account" "agent" {
  account_id   = "${var.prefix}-07-agent-sa"
  display_name = "agent-api pods: Vertex AI access"
}

resource "google_project_iam_member" "agent_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.agent.email}"
}

# Only the KSA wallettracker/agent-api may act as this GSA
resource "google_service_account_iam_member" "agent_wi" {
  service_account_id = google_service_account.agent.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[wallettracker/agent-api]"
}

output "agent_sa_email" {
  value = google_service_account.agent.email
}
