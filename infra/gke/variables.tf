variable "project_id" {
  type = string
}
variable "region" {
  type = string
}
variable "zone" {
  type = string
}
variable "prefix" {
  type = string
}
variable "admin_cidr" {
  type        = string
  description = "Your public IP in /32 form; only this may reach the control plane"
}

variable "app_domain" {
  description = "Public hostname for agent-api (e.g. ai.example.com)"
  type        = string
}
