# ---- Phase F: Custom Metrics Adapter reads Cloud Monitoring (keyless, direct WI principal) ----
data "google_project" "this" {}

resource "google_project_iam_member" "metrics_adapter" {
  project = data.google_project.this.project_id
  role    = "roles/monitoring.viewer"
  member  = "principal://iam.googleapis.com/projects/${data.google_project.this.number}/locations/global/workloadIdentityPools/${data.google_project.this.project_id}.svc.id.goog/subject/ns/custom-metrics/sa/custom-metrics-stackdriver-adapter"
}
