variable "hcloud_token" {
  description = "Hetzner Cloud API token."
  type        = string
  sensitive   = true
}

variable "project_name" {
  description = "Short project label."
  type        = string
  default     = "home-site"
}

variable "domain_name" {
  description = "Final public domain for the site."
  type        = string
  default     = "home.moshq.app"
}

variable "server_name" {
  description = "Hetzner server name."
  type        = string
  default     = "home-moshq-policy"
}

variable "server_type" {
  description = "Hetzner server type."
  type        = string
  default     = "cx23"
}

variable "server_location" {
  description = "Hetzner location code."
  type        = string
  default     = "fsn1"
}

variable "server_image" {
  description = "Hetzner image slug."
  type        = string
  default     = "ubuntu-22.04"
}

variable "ssh_private_key_path" {
  description = "Absolute path to the SSH private key used for provisioning."
  type        = string
  default     = "/Users/aldrinclement/.ssh/hetzner_prod"
}

variable "ssh_public_key_path" {
  description = "Absolute path to the SSH public key uploaded to Hetzner."
  type        = string
  default     = "/Users/aldrinclement/.ssh/hetzner_prod.pub"
}

variable "support_email" {
  description = "Support mailbox published on the site."
  type        = string
  default     = "support@moshq.app"
}

variable "business_address_multiline" {
  description = "Published business address."
  type        = string
  default     = "8 The Green, STE A\nDover, DE 19901\nUnited States"
}
