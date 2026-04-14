output "server_ipv4" {
  value       = hcloud_server.home_site.ipv4_address
  description = "Primary public IPv4 address."
}

output "server_ipv6" {
  value       = hcloud_server.home_site.ipv6_address
  description = "Primary public IPv6 network."
}

output "dns_a_record" {
  value       = hcloud_server.home_site.ipv4_address
  description = "A record target for home.moshq.app."
}

output "dns_aaaa_record" {
  value       = split("/", hcloud_server.home_site.ipv6_address)[0]
  description = "AAAA record target for home.moshq.app."
}
