# ---- Phase E: public edge (IP + Google-managed certificate) ----
resource "google_project_service" "certmgr" {
  service            = "certificatemanager.googleapis.com"
  disable_on_destroy = false
}

resource "google_compute_global_address" "gw_ip" {
  name = "wallettrackerai-08-ip"
}

resource "google_certificate_manager_dns_authorization" "auth" {
  name       = "wallettrackerai-09-dnsauth"
  domain     = var.app_domain
  depends_on = [google_project_service.certmgr]
}

resource "google_certificate_manager_certificate" "cert" {
  name = "wallettrackerai-10-cert"
  managed {
    domains            = [var.app_domain]
    dns_authorizations = [google_certificate_manager_dns_authorization.auth.id]
  }
}

resource "google_certificate_manager_certificate_map" "map" {
  name       = "wallettrackerai-11-certmap"
  depends_on = [google_project_service.certmgr]
}

resource "google_certificate_manager_certificate_map_entry" "entry" {
  name         = "wallettrackerai-12-certmap-entry"
  map          = google_certificate_manager_certificate_map.map.name
  certificates = [google_certificate_manager_certificate.cert.id]
  hostname     = var.app_domain
}

output "gateway_ip" {
  value = google_compute_global_address.gw_ip.address
}

output "dns_records_to_add" {
  value = {
    A_record = "${var.app_domain} -> ${google_compute_global_address.gw_ip.address}"
    CNAME    = "${google_certificate_manager_dns_authorization.auth.dns_resource_record[0].name} -> ${google_certificate_manager_dns_authorization.auth.dns_resource_record[0].data}"
  }
}
