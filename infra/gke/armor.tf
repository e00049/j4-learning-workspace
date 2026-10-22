# ---- Phase E: Cloud Armor rate limit for agent-api ----
resource "google_compute_security_policy" "armor" {
  name        = "wallettrackerai-14-armor"
  description = "Rate limit for public agent-api"

  rule {
    action      = "throttle"
    priority    = 1000
    description = "10 requests per minute per IP, then 429"
    match {
      versioned_expr = "SRC_IPS_V1"
      config { src_ip_ranges = ["*"] }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = 10
        interval_sec = 60
      }
    }
  }

  rule {
    action      = "allow"
    priority    = 2147483647
    description = "default allow"
    match {
      versioned_expr = "SRC_IPS_V1"
      config { src_ip_ranges = ["*"] }
    }
  }
}
