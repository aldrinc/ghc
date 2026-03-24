terraform {
  required_version = ">= 1.9.0"

  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.50"
    }
  }
}

provider "hcloud" {
  token = var.hcloud_token
}

locals {
  app_root           = "${path.module}/../app"
  app_files          = fileset(local.app_root, "**")
  app_hash           = sha256(join("", [for file_name in local.app_files : filesha256("${local.app_root}/${file_name}")]))
  nginx_http_config  = replace(file("${local.app_root}/nginx-http.conf"), "__DOMAIN_NAME__", var.domain_name)
  nginx_https_config = replace(file("${local.app_root}/nginx.conf"), "__DOMAIN_NAME__", var.domain_name)
  renew_hook_script  = file("${local.app_root}/certbot-renew-hook.sh")
}

resource "hcloud_ssh_key" "home_site" {
  name       = "${var.project_name}-ssh"
  public_key = trimspace(file(var.ssh_public_key_path))
}

resource "hcloud_firewall" "home_site" {
  name = "${var.project_name}-firewall"

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "80"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "443"
    source_ips = ["0.0.0.0/0", "::/0"]
  }
}

resource "hcloud_server" "home_site" {
  name        = var.server_name
  image       = var.server_image
  server_type = var.server_type
  location    = var.server_location

  labels = {
    project = var.project_name
    service = "policy-site"
  }

  ssh_keys     = [hcloud_ssh_key.home_site.id]
  firewall_ids = [hcloud_firewall.home_site.id]

  public_net {
    ipv4_enabled = true
    ipv6_enabled = true
  }

  user_data = <<-EOF
    #cloud-config
    package_update: true
    package_upgrade: false
    ssh_pwauth: false
  EOF
}

resource "terraform_data" "provision" {
  depends_on = [hcloud_server.home_site]

  triggers_replace = [
    hcloud_server.home_site.id,
    local.app_hash,
    var.domain_name,
    var.support_email,
    var.business_address_multiline,
  ]

  connection {
    type        = "ssh"
    user        = "root"
    host        = hcloud_server.home_site.ipv4_address
    private_key = file(var.ssh_private_key_path)
    timeout     = "6m"
  }

  provisioner "remote-exec" {
    inline = [
      "cloud-init status --wait >/dev/null 2>&1 || true",
      "export DEBIAN_FRONTEND=noninteractive",
      "apt-get update",
      "apt-get install -y certbot nginx python3 sqlite3",
      "mkdir -p /tmp/home-site /opt/home-site/data /var/www/certbot /etc/letsencrypt/renewal-hooks/deploy",
      "rm -rf /tmp/home-site/*",
    ]
  }

  provisioner "file" {
    source      = "${local.app_root}/"
    destination = "/tmp/home-site/"
  }

  provisioner "file" {
    content     = local.nginx_http_config
    destination = "/tmp/home-site/nginx-http.conf"
  }

  provisioner "file" {
    content     = local.nginx_https_config
    destination = "/tmp/home-site/nginx-https.conf"
  }

  provisioner "file" {
    content     = local.renew_hook_script
    destination = "/tmp/home-site/certbot-renew-hook.sh"
  }

  provisioner "remote-exec" {
    inline = [
      "install -d -m 0755 /opt/home-site",
      "install -m 0644 /tmp/home-site/site.css /opt/home-site/site.css",
      "install -m 0755 /tmp/home-site/server.py /opt/home-site/server.py",
      "install -m 0644 /tmp/home-site/home-site.service /etc/systemd/system/home-site.service",
      "install -m 0644 /tmp/home-site/nginx-http.conf /etc/nginx/sites-available/home-site",
      "rm -f /etc/nginx/sites-enabled/default",
      "ln -sf /etc/nginx/sites-available/home-site /etc/nginx/sites-enabled/home-site",
      "chown -R www-data:www-data /opt/home-site",
      "systemctl daemon-reload",
      "systemctl enable home-site",
      "systemctl restart home-site",
      "systemctl enable --now certbot.timer",
      "nginx -t",
      "systemctl reload nginx || systemctl restart nginx",
      "certbot certonly --webroot -w /var/www/certbot -d ${var.domain_name} --non-interactive --agree-tos -m ${var.support_email} --keep-until-expiring",
      "install -m 0755 /tmp/home-site/certbot-renew-hook.sh /etc/letsencrypt/renewal-hooks/deploy/home-site-reload-nginx.sh",
      "install -m 0644 /tmp/home-site/nginx-https.conf /etc/nginx/sites-available/home-site",
      "nginx -t",
      "systemctl reload nginx",
      "systemctl is-active --quiet home-site",
      "systemctl is-active --quiet nginx",
    ]
  }
}
