# ---- Phase F: alerting on agent-api (Managed Prometheus metrics) ----
variable "alert_email" {
  type = string
}

variable "latency_p95_threshold_s" {
  type    = number
  default = 8
}

variable "cost_inr_per_hour_threshold" {
  type    = number
  default = 50
}

resource "google_monitoring_notification_channel" "email" {
  display_name = "wallettrackerai-18-email"
  type         = "email"
  labels       = { email_address = var.alert_email }
}

locals {
  alerts = {
    "wallettrackerai-19-alert-latency" = {
      query = "histogram_quantile(0.95, sum by (le) (rate(agent_request_seconds_bucket[5m]))) > ${var.latency_p95_threshold_s}"
      doc   = "agent-api p95 latency above ${var.latency_p95_threshold_s}s. Check Gemini latency panel and rounds per question."
    }
    "wallettrackerai-20-alert-errors" = {
      query = "(sum(rate(agent_requests_total{status=~\"5..\"}[5m])) / sum(rate(agent_requests_total[5m]))) > 0.05"
      doc   = "agent-api 5xx ratio above 5%. 508 = tool loop exhausted; check logs and MCP health."
    }
    "wallettrackerai-21-alert-cost" = {
      query = "((sum(rate(agent_llm_tokens_total{type=\"input\"}[5m])) * 0.30 + sum(rate(agent_llm_tokens_total{type=~\"output|thinking\"}[5m])) * 2.50) / 1e6 * 3600 * 88) > ${var.cost_inr_per_hour_threshold}"
      doc   = "Estimated Gemini spend above INR ${var.cost_inr_per_hour_threshold}/hour. Check request rate by status and Cloud Armor logs for abuse."
    }
  }
}

resource "google_monitoring_alert_policy" "agent" {
  for_each     = merge(local.alerts, local.alerts_extra)
  display_name = each.key
  combiner     = "OR"

  conditions {
    display_name = each.key
    condition_prometheus_query_language {
      query               = each.value.query
      duration            = "300s"
      evaluation_interval = "60s"
    }
  }

  documentation {
    content   = each.value.doc
    mime_type = "text/markdown"
  }

  notification_channels = [google_monitoring_notification_channel.email.id]
}
