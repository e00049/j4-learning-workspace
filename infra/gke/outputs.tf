output "cluster_name" {
  value = google_container_cluster.gke.name
}
output "zone" {
  value = var.zone
}
output "registry_url" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.repo.repository_id}"
}
