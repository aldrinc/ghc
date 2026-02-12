import io
import json
import os
import time
import shlex
from pathlib import Path
import paramiko
from typing import Dict, List, Optional  # noqa: F401

from ..models import (
    ApplicationSourceType,
    ApplicationSpec,
    FunnelArtifactSourceSpec,
    FunnelPublicationSourceSpec,
    RuntimeType,
)


_NGINX_PROXY_CONNECT_TIMEOUT = "60s"
_NGINX_PROXY_SEND_TIMEOUT = "3600s"
_NGINX_PROXY_READ_TIMEOUT = "3600s"


class ServerDeployer:
    """SSH-based deployer that configures apps without replacing servers."""

    def __init__(
        self,
        ip: str,
        private_key_str: str,
        user: str = "root",
        local_root: Optional[Path] = None,
    ):
        self.ip = ip
        self.user = user
        self.key = paramiko.RSAKey.from_private_key(io.StringIO(private_key_str))
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.local_root = Path(local_root).expanduser().resolve() if local_root else None

    def connect(self):
        for _ in range(10):
            try:
                self.client.connect(self.ip, username=self.user, pkey=self.key, timeout=10)
                return
            except Exception:
                time.sleep(5)
        raise ConnectionError(f"Could not connect to {self.ip}")

    def run(self, cmd: str, cwd: str = None, mask: Optional[List[str]] = None) -> str:
        if self.client.get_transport() is None or not self.client.get_transport().is_active():
            self.connect()

        final_cmd = f"cd {cwd} && {cmd}" if cwd else cmd
        display_cmd = final_cmd
        for m in mask or []:
            if m:
                display_cmd = display_cmd.replace(m, "***")
        print(f"[{self.ip}] Running: {display_cmd}")
        stdin, stdout, stderr = self.client.exec_command(final_cmd)

        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()

        if exit_code != 0:
            raise Exception(f"Command failed: {final_cmd}\nError: {err}")
        return out

    def upload_file(self, content: str, remote_path: str):
        if self.client.get_transport() is None or not self.client.get_transport().is_active():
            self.connect()
        sftp = self.client.open_sftp()
        with sftp.file(remote_path, "w") as f:
            f.write(content)
        sftp.close()

    def _normalize_server_names(self, server_names: Optional[List[str]]) -> List[str]:
        names: List[str] = []
        for name in server_names or []:
            cleaned = (name or "").strip()
            if cleaned and cleaned not in names:
                names.append(cleaned)
        return names

    def _server_name_directive(self, server_names: List[str]) -> str:
        return " ".join(server_names) if server_names else "_"

    def _resolve_local_path(self, raw_path: str) -> Path:
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            base = self.local_root or Path.cwd()
            path = base / path
        return path.resolve()

    def _env_lines_from_map(self, env_map: Dict[str, str]) -> List[str]:
        lines: List[str] = []
        for key, value in env_map.items():
            if value is None:
                continue
            lines.append(f"{key}={str(value).strip()}")
        return lines

    def _upload_env_content(self, content: str, remote_path: str) -> None:
        remote_dir = os.path.dirname(remote_path)
        if remote_dir:
            self.run(f"mkdir -p {remote_dir}")
        self.upload_file(content, remote_path)
        self.run(f"chmod 600 {remote_path}")

    def _write_env_file(self, app: ApplicationSpec, path: Optional[str] = None) -> Optional[str]:
        lines = self._env_lines_from_map(app.service_config.environment)
        if not lines:
            return None

        target = path or f"/etc/cloudhand/env/{app.name}.env"
        self._upload_env_content("\n".join(lines) + "\n", target)
        return target

    def _parse_env_file_path(self, raw_path: str, app_dir: str) -> Optional[tuple[str, bool]]:
        cleaned = (raw_path or "").strip()
        if not cleaned:
            return None
        optional = cleaned.startswith("-")
        if optional:
            cleaned = cleaned[1:]
        if cleaned.startswith("/"):
            resolved = cleaned
        else:
            resolved = f"{app_dir}/{cleaned}"
        return resolved, optional

    def _resolve_env_file(self, raw_path: str, app_dir: str) -> Optional[str]:
        parsed = self._parse_env_file_path(raw_path, app_dir)
        if not parsed:
            return None
        resolved, optional = parsed
        return f"-{resolved}" if optional else resolved

    def _env_file_directives(self, app: ApplicationSpec, app_dir: str) -> str:
        env_files: List[str] = []
        env_map_consumed = False

        if app.service_config.environment_file_upload:
            local_path = self._resolve_local_path(app.service_config.environment_file_upload)
            if not local_path.exists():
                raise FileNotFoundError(f"Environment file not found at {local_path}")
            content = local_path.read_text(encoding="utf-8")
            if not content.endswith("\n"):
                content += "\n"

            extra_lines = self._env_lines_from_map(app.service_config.environment)
            if extra_lines:
                content += "\n".join(extra_lines) + "\n"
                env_map_consumed = True

            target_raw = app.service_config.environment_file or f"/etc/cloudhand/env/{app.name}.env"
            parsed = self._parse_env_file_path(target_raw, app_dir)
            if not parsed:
                raise ValueError("environment_file_upload set but no target path resolved")
            target_path, optional = parsed
            self._upload_env_content(content, target_path)
            env_files.append(f"-{target_path}" if optional else target_path)
        elif app.service_config.environment_file:
            resolved = self._resolve_env_file(app.service_config.environment_file, app_dir)
            if resolved:
                env_files.append(resolved)

        if app.service_config.environment and not env_map_consumed:
            generated = self._write_env_file(app)
            if generated:
                env_files.append(generated)

        if not env_files:
            return ""

        return "\n".join(f"EnvironmentFile={path}" for path in env_files)

    def _configure_systemd(self, app: ApplicationSpec, app_dir: str):
        env_str = self._env_file_directives(app, app_dir)
        unit = f"""[Unit]
Description={app.name}
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={app_dir}
ExecStart={app.service_config.command}
Restart=always
{env_str}

[Install]
WantedBy=multi-user.target
"""
        self.upload_file(unit, f"/etc/systemd/system/{app.name}.service")
        self.run("systemctl daemon-reload")
        self.run(f"systemctl enable {app.name}")
        self.run(f"systemctl restart {app.name}")

    def _service_unit_exists(self, service_name: str) -> bool:
        safe_name = service_name.replace("'", "'\"'\"'")
        out = self.run(f"bash -lc \"systemctl cat '{safe_name}.service' >/dev/null 2>&1 && echo yes || true\"")
        return out.strip() == "yes"

    def _path_exists(self, path: str) -> bool:
        safe_path = shlex.quote(path)
        out = self.run(f"bash -lc \"test -e {safe_path} && echo yes || true\"")
        return out.strip() == "yes"

    def _remove_path_if_exists(self, path: str, *, recursive: bool = False) -> bool:
        if not self._path_exists(path):
            return False
        safe_path = shlex.quote(path)
        if recursive:
            self.run(f"rm -rf {safe_path}")
        else:
            self.run(f"rm -f {safe_path}")
        return True

    def _port_is_listening(self, port: int) -> bool:
        out = self.run(f"bash -lc \"ss -ltnH '( sport = :{port} )' | head -n 1 || true\"")
        return bool(out.strip())

    def _assert_ports_available(self, app: ApplicationSpec):
        for port in sorted(set(app.service_config.ports)):
            if not self._port_is_listening(port):
                continue
            if self._service_unit_exists(app.name):
                # Allow rolling restarts for an existing managed workload on the same port.
                continue
            raise ValueError(
                f"Port {port} is already in use on server {self.ip}; cannot deploy workload '{app.name}'."
            )

    def _enable_https(self, server_names: List[str]):
        names = self._normalize_server_names(server_names)
        if not names:
            print(f"[{self.ip}] HTTPS requested but no server_names configured; skipping certificate setup.")
            return

        domain_args = " ".join(f"-d {name}" for name in names)
        cert_cmd = self.run("command -v certbox || command -v certbot || true").strip()
        if not cert_cmd:
            self.run(
                "DEBIAN_FRONTEND=noninteractive apt-get update && "
                "DEBIAN_FRONTEND=noninteractive apt-get install -y certbot python3-certbot-nginx"
            )
            cert_cmd = "certbot"

        cmd_name = os.path.basename(cert_cmd)
        if cmd_name == "certbot":
            email = os.getenv("CERTBOT_EMAIL") or os.getenv("LETSENCRYPT_EMAIL") or ""
            email_flag = f"--email {email}" if email else "--register-unsafely-without-email"
            self.run(
                f"{cert_cmd} --nginx {domain_args} --non-interactive --agree-tos {email_flag} --redirect"
            )
        else:
            # Assume certbox is certbot-compatible.
            self.run(
                f"{cert_cmd} --nginx {domain_args} --non-interactive --agree-tos --redirect "
                "--register-unsafely-without-email"
            )

    def _ensure_nginx(self):
        # Ensure nginx exists (Hetzner cloud-init installs it in our Terraform, but be defensive)
        nginx_bin = self.run("command -v nginx || true").strip()
        if not nginx_bin:
            self.run(
                "DEBIAN_FRONTEND=noninteractive apt-get update && "
                "DEBIAN_FRONTEND=noninteractive apt-get install -y nginx"
            )

        self.run("mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled")
        self.run("systemctl enable nginx || true")
        self.run("systemctl start nginx || true")

    def _configure_funnel_publication_proxy(self, app: ApplicationSpec):
        source = app.source_ref
        if source is None:
            raise ValueError("source_ref is required when source_type='funnel_publication'.")
        if not isinstance(source, FunnelPublicationSourceSpec):
            raise ValueError("source_ref must be FunnelPublicationSourceSpec when source_type='funnel_publication'.")

        server_names = self._normalize_server_names(app.service_config.server_names)
        server_name_line = self._server_name_directive(server_names)
        if server_names:
            listen_port = 80
        else:
            ports = list(app.service_config.ports or [])
            if not ports:
                raise ValueError(
                    "service_config.ports must include one port for source_type='funnel_publication' "
                    "when server_names is empty."
                )
            listen_port = int(ports[0])

        public_id = source.public_id
        upstream_base_url = source.upstream_base_url.rstrip("/")
        upstream_api_base_url = source.upstream_api_base_url.rstrip("/")

        conf = f"""server {{
    listen {listen_port};
    server_name {server_name_line};
    client_max_body_size 25m;
    proxy_connect_timeout {_NGINX_PROXY_CONNECT_TIMEOUT};
    proxy_send_timeout {_NGINX_PROXY_SEND_TIMEOUT};
    proxy_read_timeout {_NGINX_PROXY_READ_TIMEOUT};

    location = / {{
        return 302 /f/{public_id}$is_args$args;
    }}

    location = /f/{public_id} {{
        proxy_pass {upstream_base_url}/f/{public_id};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Accept-Encoding "";
        sub_filter_once off;
        sub_filter_types text/html text/css application/javascript text/javascript application/json;
        sub_filter '{upstream_api_base_url}' '/api';
    }}

    location ^~ /f/{public_id}/ {{
        proxy_pass {upstream_base_url};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Accept-Encoding "";
        sub_filter_once off;
        sub_filter_types text/html text/css application/javascript text/javascript application/json;
        sub_filter '{upstream_api_base_url}' '/api';
    }}

    location ^~ /api/ {{
        proxy_pass {upstream_api_base_url}/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}

    location ^~ /assets/ {{
        proxy_pass {upstream_base_url}/assets/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Accept-Encoding "";
        sub_filter_once off;
        sub_filter_types text/css application/javascript text/javascript application/json;
        sub_filter '{upstream_api_base_url}' '/api';
    }}

    location = /favicon.ico {{
        proxy_pass {upstream_base_url}/favicon.ico;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}

    location / {{
        return 302 /f/{public_id}$request_uri;
    }}
}}"""
        self.upload_file(conf, f"/etc/nginx/sites-available/{app.name}")
        self.run(f"ln -sf /etc/nginx/sites-available/{app.name} /etc/nginx/sites-enabled/{app.name}")
        self.run("rm -f /etc/nginx/sites-enabled/default")
        self.run("systemctl reload nginx")
        if app.service_config.https:
            self._enable_https(server_names)

    def _replace_api_base_tokens(self, *, site_dir: str, upstream_api_base_root: str) -> None:
        if not upstream_api_base_root:
            return
        if not upstream_api_base_root.startswith(("http://", "https://")):
            raise ValueError("upstream_api_base_root must start with http:// or https://.")

        script = (
            "import pathlib\n"
            f"SITE = pathlib.Path({site_dir!r})\n"
            f"FROM = {upstream_api_base_root!r}\n"
            "TO = '/api'\n"
            "if not SITE.exists():\n"
            "    raise SystemExit(0)\n"
            "for path in SITE.rglob('*'):\n"
            "    if not path.is_file():\n"
            "        continue\n"
            "    if path.suffix.lower() not in {'.js', '.css', '.html', '.json'}:\n"
            "        continue\n"
            "    try:\n"
            "        raw = path.read_text(encoding='utf-8')\n"
            "    except Exception:\n"
            "        continue\n"
            "    replaced = raw.replace(FROM, TO)\n"
            "    if replaced != raw:\n"
            "        path.write_text(replaced, encoding='utf-8')\n"
        )
        self.run(f"python3 -c {shlex.quote(script)}")

    def _write_funnel_artifact_payload(self, *, site_dir: str, source: FunnelArtifactSourceSpec) -> None:
        artifact = source.artifact or {}
        meta = artifact.get("meta")
        pages = artifact.get("pages")
        commerce = artifact.get("commerce")
        if not isinstance(meta, dict):
            raise ValueError("source_ref.artifact.meta must be an object.")
        if not isinstance(pages, dict):
            raise ValueError("source_ref.artifact.pages must be an object.")

        public_id = source.public_id.strip()
        if not public_id:
            raise ValueError("source_ref.public_id must be non-empty.")

        base_dir = f"{site_dir}/api/public/funnels/{public_id}"
        pages_dir = f"{base_dir}/pages"
        self.run(f"mkdir -p {shlex.quote(pages_dir)}")
        self.upload_file(json.dumps(meta, ensure_ascii=False), f"{base_dir}/meta.json")

        if isinstance(commerce, dict):
            self.upload_file(json.dumps(commerce, ensure_ascii=False), f"{base_dir}/commerce.json")

        for raw_slug, page_payload in pages.items():
            slug = str(raw_slug or "").strip()
            if not slug:
                continue
            if "/" in slug or "\\" in slug:
                raise ValueError(f"Invalid artifact page slug '{slug}'.")
            if not isinstance(page_payload, dict):
                raise ValueError(f"Artifact page payload for slug '{slug}' must be an object.")
            self.upload_file(
                json.dumps(page_payload, ensure_ascii=False),
                f"{pages_dir}/{slug}.json",
            )

    def _configure_funnel_artifact_site(self, app: ApplicationSpec):
        source = app.source_ref
        if source is None:
            raise ValueError("source_ref is required when source_type='funnel_artifact'.")
        if not isinstance(source, FunnelArtifactSourceSpec):
            raise ValueError("source_ref must be FunnelArtifactSourceSpec when source_type='funnel_artifact'.")

        runtime_dist_path = (source.runtime_dist_path or "").strip()
        if not runtime_dist_path:
            raise ValueError("source_ref.runtime_dist_path must be non-empty for source_type='funnel_artifact'.")

        app_dir = f"{app.destination_path}/{app.name}"
        site_dir = f"{app_dir}/site"
        dist_q = shlex.quote(runtime_dist_path)
        app_dir_q = shlex.quote(app_dir)
        site_dir_q = shlex.quote(site_dir)

        if not self._path_exists(runtime_dist_path):
            raise ValueError(
                "source_ref.runtime_dist_path does not exist on target server: "
                f"{runtime_dist_path}. Build/copy the runtime bundle there or set "
                "DEPLOY_ARTIFACT_RUNTIME_DIST_PATH to the correct directory."
            )
        self.run(f"mkdir -p {app_dir_q}")
        self.run(f"rm -rf {site_dir_q}")
        self.run(f"mkdir -p {site_dir_q}")
        self.run(f"cp -R {dist_q}/. {site_dir_q}/")
        self._replace_api_base_tokens(site_dir=site_dir, upstream_api_base_root=source.upstream_api_base_root)
        self._write_funnel_artifact_payload(site_dir=site_dir, source=source)

        server_names = self._normalize_server_names(app.service_config.server_names)
        server_name_line = self._server_name_directive(server_names)
        if server_names:
            listen_port = 80
        else:
            ports = list(app.service_config.ports or [])
            if not ports:
                raise ValueError(
                    "service_config.ports must include one port for source_type='funnel_artifact' "
                    "when server_names is empty."
                )
            listen_port = int(ports[0])

        public_id = source.public_id
        conf = f"""server {{
    listen {listen_port};
    server_name {server_name_line};
    root {site_dir};
    index index.html;
    client_max_body_size 25m;
    proxy_connect_timeout {_NGINX_PROXY_CONNECT_TIMEOUT};
    proxy_send_timeout {_NGINX_PROXY_SEND_TIMEOUT};
    proxy_read_timeout {_NGINX_PROXY_READ_TIMEOUT};

    location = / {{
        return 302 /f/{public_id}$is_args$args;
    }}

    location = /api/public/checkout {{
        default_type application/json;
        return 501 '{{"detail":"Checkout is unavailable in standalone artifact mode."}}';
    }}

    location ^~ /api/public/events {{
        return 204;
    }}

    location ^~ /api/public/funnels/{public_id}/ {{
        default_type application/json;
        try_files $uri.json =404;
    }}

    location / {{
        try_files $uri /index.html;
    }}
}}"""
        self.upload_file(conf, f"/etc/nginx/sites-available/{app.name}")
        self.run(f"ln -sf /etc/nginx/sites-available/{app.name} /etc/nginx/sites-enabled/{app.name}")
        self.run("rm -f /etc/nginx/sites-enabled/default")
        self.run("nginx -t")
        self.run("systemctl reload nginx")
        if app.service_config.https:
            self._enable_https(server_names)

    def _configure_nginx(self, app: ApplicationSpec):
        if app.source_type == ApplicationSourceType.FUNNEL_PUBLICATION:
            self._ensure_nginx()
            self._configure_funnel_publication_proxy(app)
            return
        if app.source_type == ApplicationSourceType.FUNNEL_ARTIFACT:
            self._ensure_nginx()
            self._configure_funnel_artifact_site(app)
            return

        if not app.service_config.ports:
            return

        self._ensure_nginx()

        port = app.service_config.ports[0]
        server_names = self._normalize_server_names(app.service_config.server_names)
        server_name_line = self._server_name_directive(server_names)
        conf = f"""server {{
    listen 80;
    server_name {server_name_line};
    proxy_connect_timeout {_NGINX_PROXY_CONNECT_TIMEOUT};
    proxy_send_timeout {_NGINX_PROXY_SEND_TIMEOUT};
    proxy_read_timeout {_NGINX_PROXY_READ_TIMEOUT};
    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
    }}
}}"""
        self.upload_file(conf, f"/etc/nginx/sites-available/{app.name}")
        self.run(f"ln -sf /etc/nginx/sites-available/{app.name} /etc/nginx/sites-enabled/{app.name}")
        self.run("rm -f /etc/nginx/sites-enabled/default")
        self.run("systemctl reload nginx")
        if app.service_config.https:
            self._enable_https(server_names)

    def configure_combined_nginx(self, apps: List[ApplicationSpec]):
        """Create a single site config that proxies UI root and API paths on one host."""
        candidates = [a for a in apps if a.service_config.ports]
        if not candidates:
            return

        # Prefer an app named *ui* as the root site; otherwise first app.
        root_app = next((a for a in candidates if "ui" in a.name.lower()), candidates[0])
        root_port = root_app.service_config.ports[0]

        locations = []
        for app in candidates:
            port = app.service_config.ports[0]
            if app is root_app:
                continue
            name = app.name.lower()
            prefix = "/api/" if "api" in name else f"/{app.name}/"
            if not prefix.startswith("/"):
                prefix = f"/{prefix}"
            if not prefix.endswith("/"):
                prefix = f"{prefix}/"
            locations.append(
                f"""    location {prefix} {{
        proxy_pass http://127.0.0.1:{port}/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }}"""
            )

        server_names: List[str] = []
        https_enabled = False
        for app in candidates:
            server_names.extend(app.service_config.server_names)
            https_enabled = https_enabled or app.service_config.https

        server_names = self._normalize_server_names(server_names)
        server_name_line = self._server_name_directive(server_names)

        config = [
            "server {",
            "    listen 80;",
            f"    server_name {server_name_line};",
            "    client_max_body_size 25m;",
            f"    proxy_connect_timeout {_NGINX_PROXY_CONNECT_TIMEOUT};",
            f"    proxy_send_timeout {_NGINX_PROXY_SEND_TIMEOUT};",
            f"    proxy_read_timeout {_NGINX_PROXY_READ_TIMEOUT};",
            "    location / {",
            f"        proxy_pass http://127.0.0.1:{root_port}/;",
            "        proxy_http_version 1.1;",
            "        proxy_set_header Upgrade $http_upgrade;",
            "        proxy_set_header Connection 'upgrade';",
            "        proxy_set_header Host $host;",
            "        proxy_set_header X-Real-IP $remote_addr;",
            "    }",
        ]
        config.extend(locations)
        config.append("}")
        conf = "\n".join(config)
        self.upload_file(conf, "/etc/nginx/sites-available/cloudhand")
        self.run("ln -sf /etc/nginx/sites-available/cloudhand /etc/nginx/sites-enabled/cloudhand")
        self.run("rm -f /etc/nginx/sites-enabled/default || true")
        self.run("systemctl reload nginx")
        if https_enabled:
            self._enable_https(server_names)

    def remove_workload(self, app: ApplicationSpec):
        app_name = (app.name or "").strip()
        if not app_name:
            raise ValueError("Workload name is required for removal.")

        service_unit = f"{app_name}.service"
        safe_service_unit = shlex.quote(service_unit)
        service_exists = self._service_unit_exists(app_name)
        if service_exists:
            self.run(f"systemctl stop {safe_service_unit}")
            self.run(f"systemctl disable {safe_service_unit}")

        unit_removed = self._remove_path_if_exists(f"/etc/systemd/system/{service_unit}")
        if service_exists or unit_removed:
            self.run("systemctl daemon-reload")

        nginx_removed = False
        if self._remove_path_if_exists(f"/etc/nginx/sites-enabled/{app_name}"):
            nginx_removed = True
        if self._remove_path_if_exists(f"/etc/nginx/sites-available/{app_name}"):
            nginx_removed = True
        if nginx_removed:
            self.run("nginx -t")
            self.run("systemctl reload nginx")

        destination = (app.destination_path or "").rstrip("/")
        if destination:
            app_dir = f"{destination}/{app_name}"
            self._remove_path_if_exists(app_dir, recursive=True)

    def deploy(self, app: ApplicationSpec, configure_nginx: bool = True):
        app_dir = f"{app.destination_path}/{app.name}"

        # 1. System Deps
        if app.build_config.system_packages:
            self.run(
                f"DEBIAN_FRONTEND=noninteractive apt-get update && "
                f"DEBIAN_FRONTEND=noninteractive apt-get install -y {' '.join(app.build_config.system_packages)}"
            )
        if app.source_type in {ApplicationSourceType.FUNNEL_PUBLICATION, ApplicationSourceType.FUNNEL_ARTIFACT}:
            # Funnel publication workloads are nginx proxies only. Remove same-name
            # legacy service/site artifacts before configuring the proxy.
            self.remove_workload(app)
            if configure_nginx:
                self._configure_nginx(app)
            return

        if app.runtime == RuntimeType.NODEJS:
            # Ensure a modern Node runtime regardless of base image defaults.
            self.run(
                "DEBIAN_FRONTEND=noninteractive apt-get purge -y nodejs npm libnode-dev libnode72 || true"
            )
            self.run("DEBIAN_FRONTEND=noninteractive apt-get autoremove -y || true")
            self.run('bash -lc "curl -fsSL https://deb.nodesource.com/setup_20.x | bash -"')
            self.run("DEBIAN_FRONTEND=noninteractive apt-get install -y nodejs")

        self._assert_ports_available(app)

        # 2. Git Sync
        repo_url = (app.repo_url or "").strip()
        if not repo_url:
            raise ValueError(f"Workload '{app.name}' requires repo_url for source_type='git'.")

        gh_token = (
            os.getenv("GITHUB_TOKEN")
            or os.getenv("GH_TOKEN")
            or os.getenv("GITHUB_PAT")
            or ""
        )
        try:
            self.run(f"test -d {app_dir}")
            fetch_cmd = f"git fetch origin && git reset --hard origin/{app.branch}"
            if gh_token:
                fetch_cmd = (
                    f'git -c http.extraheader="Authorization: Bearer {gh_token}" '
                    f'fetch origin && git -c http.extraheader="Authorization: Bearer {gh_token}" '
                    f"reset --hard origin/{app.branch}"
                )
            self.run(fetch_cmd, cwd=app_dir, mask=[gh_token] if gh_token else None)
        except Exception:
            # Clean any partial checkout and reclone.
            self.run(f"rm -rf {app_dir}")
            self.run(f"mkdir -p {app.destination_path}")
            clone_url = repo_url
            if gh_token:
                clone_url = repo_url.replace("https://", f"https://{gh_token}@")
            self.run(
                f"git clone --branch {app.branch} {clone_url} {app_dir}",
                mask=[gh_token] if gh_token else None,
            )

        # 3. Build
        if app.build_config.install_command:
            self.run(app.build_config.install_command, cwd=app_dir)
        if app.build_config.build_command:
            self.run(app.build_config.build_command, cwd=app_dir)

        # 4. Services
        self._configure_systemd(app, app_dir)
        if configure_nginx:
            self._configure_nginx(app)
