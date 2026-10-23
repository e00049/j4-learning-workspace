# ---- Phase F: alerts for blind monitoring + upstream throttling ----
locals {
  alerts_extra = {
    "wallettrackerai-22-alert-scrape-down" = {
      query = "(min(up{namespace=\"wallettracker\"}) == 0) or absent(up{namespace=\"wallettracker\"})"
      doc   = "Monitoring is BLIND: agent-api metrics are not being scraped. Check pods, the allow-gmp-scrape NetworkPolicy, and the gmp-system collector."
    }
    "wallettrackerai-23-alert-gemini-429" = {
      query = "sum(rate(agent_upstream_errors_total{code=\"429\"}[5m])) * 60 > 12"
      doc   = "Gemini is throttling (>12 x 429/min). Scaling pods will NOT help. Options: global endpoint, Provisioned Throughput, response cache, fallback model."
    }
  }
}
