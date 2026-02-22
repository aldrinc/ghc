import base64
import binascii
import io
import json
import os
import subprocess
import tarfile
import time
import shlex
import hashlib
import re
from uuid import UUID
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
_RUNTIME_CACHE_DIR = "/opt/apps/.cloudhand-runtime-cache"
_SHORT_UUID_TOKEN_PATTERN = re.compile(r"^[0-9a-f]{8}$")


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

    def upload_bytes(self, content: bytes, remote_path: str):
        if self.client.get_transport() is None or not self.client.get_transport().is_active():
            self.connect()
        sftp = self.client.open_sftp()
        with sftp.file(remote_path, "wb") as f:
            f.write(content)
        sftp.close()

    def _upload_local_directory(self, *, local_dir: Path, remote_dir: str) -> None:
        if not local_dir.is_dir():
            raise ValueError(f"Local runtime directory does not exist: {local_dir}")

        if self.client.get_transport() is None or not self.client.get_transport().is_active():
            self.connect()

        archive_stream = io.BytesIO()
        with tarfile.open(fileobj=archive_stream, mode="w:gz") as tar:
            for child in sorted(local_dir.rglob("*")):
                if child.is_dir():
                    continue
                if child.name.startswith("."):
                    continue
                if child.suffix == ".map":
                    continue
                tar.add(str(child), arcname=child.relative_to(local_dir).as_posix())
        archive_stream.seek(0)

        remote_archive = f"/tmp/cloudhand-runtime-{int(time.time() * 1000)}.tar.gz"
        sftp = self.client.open_sftp()
        try:
            with sftp.file(remote_archive, "wb") as remote_file:
                remote_file.write(archive_stream.read())
        finally:
            sftp.close()

        remote_dir_q = shlex.quote(remote_dir)
        remote_archive_q = shlex.quote(remote_archive)
        self.run(f"tar -xzf {remote_archive_q} -C {remote_dir_q}")
        self.run(f"rm -f {remote_archive_q}")

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

    def _run_local_command(self, args: List[str], *, cwd: Path) -> None:
        try:
            proc = subprocess.run(
                args,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ValueError(
                f"Required local command is unavailable: '{args[0]}'. Install it on the MOS API host."
            ) from exc

        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            stdout = (proc.stdout or "").strip()
            detail = stderr or stdout or "no output"
            raise ValueError(
                f"Local command failed: {' '.join(args)} (cwd={cwd})\n{detail}"
            )

    def _hash_local_directory(self, local_dir: Path) -> str:
        hasher = hashlib.sha256()
        for path in sorted(local_dir.rglob("*")):
            if path.is_dir():
                continue
            if path.name.startswith("."):
                continue
            if path.suffix == ".map":
                continue
            rel = path.relative_to(local_dir).as_posix()
            hasher.update(rel.encode("utf-8"))
            with path.open("rb") as file:
                while True:
                    chunk = file.read(1024 * 1024)
                    if not chunk:
                        break
                    hasher.update(chunk)
        return hasher.hexdigest()[:16]

    def _find_local_repo_root(self) -> Optional[Path]:
        candidates: List[Path] = []
        if self.local_root:
            candidates.append(self.local_root.resolve())
        candidates.append(Path.cwd().resolve())
        candidates.append(Path(__file__).resolve())

        seen: set[Path] = set()
        for start in candidates:
            for candidate in [start, *start.parents]:
                if candidate in seen:
                    continue
                seen.add(candidate)
                if (candidate / "mos" / "frontend" / "package.json").is_file():
                    return candidate
        return None

    def _ensure_local_runtime_dist(self, runtime_dist_path: str) -> Path | None:
        raw_path = Path(runtime_dist_path)
        dist_candidates: List[Path] = []
        if raw_path.is_absolute():
            dist_candidates.append(raw_path)
        else:
            dist_candidates.append(self._resolve_local_path(runtime_dist_path))
            repo_root = self._find_local_repo_root()
            if repo_root is not None:
                dist_candidates.append((repo_root / runtime_dist_path).resolve())

        unique_dist_candidates: List[Path] = []
        seen: set[Path] = set()
        for candidate in dist_candidates:
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            unique_dist_candidates.append(resolved)

        for candidate in unique_dist_candidates:
            if candidate.is_dir():
                return candidate

        frontend_candidates: List[Path] = []
        for candidate in unique_dist_candidates:
            if candidate.name == "dist" and (candidate.parent / "package.json").is_file():
                if candidate.parent not in frontend_candidates:
                    frontend_candidates.append(candidate.parent)

        repo_root = self._find_local_repo_root()
        if repo_root:
            repo_frontend = (repo_root / "mos" / "frontend").resolve()
            if (repo_frontend / "package.json").is_file() and repo_frontend not in frontend_candidates:
                frontend_candidates.append(repo_frontend)

        if not frontend_candidates:
            return None

        frontend_dir = frontend_candidates[0]
        print(f"[{self.ip}] Local runtime dist missing; building frontend in {frontend_dir}")
        self._run_local_command(["npm", "ci"], cwd=frontend_dir)
        self._run_local_command(["npm", "run", "build"], cwd=frontend_dir)

        for candidate in unique_dist_candidates:
            if candidate.is_dir():
                return candidate

        fallback_dist = frontend_dir / "dist"
        if fallback_dist.is_dir():
            return fallback_dist

        raise ValueError(
            "Frontend build completed but no dist directory was produced for "
            f"runtime_dist_path={runtime_dist_path!r}."
        )

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

    def _resolve_funnel_artifact_default_route(
        self, *, source: FunnelArtifactSourceSpec
    ) -> Optional[tuple[str, str]]:
        artifact = source.artifact or {}
        products = artifact.get("products")
        if not isinstance(products, dict):
            return None

        for raw_product_slug, product_payload in products.items():
            product_slug = str(raw_product_slug or "").strip()
            if not product_slug:
                continue
            if not isinstance(product_payload, dict):
                continue
            funnels = product_payload.get("funnels")
            if not isinstance(funnels, dict):
                continue

            for raw_funnel_slug, funnel_payload in funnels.items():
                funnel_slug = str(raw_funnel_slug or "").strip()
                if not funnel_slug:
                    continue
                if not isinstance(funnel_payload, dict):
                    continue

                resolved_funnel_token = funnel_slug
                funnel_meta = funnel_payload.get("meta")
                if isinstance(funnel_meta, dict):
                    funnel_id_token = str(funnel_meta.get("funnelId") or "").strip().lower()
                    if funnel_id_token:
                        try:
                            short_funnel_id_token = str(UUID(funnel_id_token)).split("-", 1)[0]
                        except ValueError:
                            short_funnel_id_token = ""
                        if short_funnel_id_token and _SHORT_UUID_TOKEN_PATTERN.fullmatch(short_funnel_id_token):
                            resolved_funnel_token = short_funnel_id_token
                        else:
                            resolved_funnel_token = funnel_id_token

                return product_slug, resolved_funnel_token

        return None

    def _inject_funnel_runtime_config(self, *, site_dir: str, source: FunnelArtifactSourceSpec) -> None:
        runtime_config: Dict[str, object] = {"bundleMode": True}
        default_route = self._resolve_funnel_artifact_default_route(source=source)
        if default_route:
            product_slug, funnel_slug = default_route
            runtime_config["defaultProductSlug"] = product_slug
            runtime_config["defaultFunnelSlug"] = funnel_slug

        config_json = json.dumps(runtime_config, separators=(",", ":"))
        block = (
            "<!-- MOS_DEPLOY_RUNTIME_START -->"
            f"<script>window.__MOS_DEPLOY_RUNTIME__={config_json};</script>"
            "<!-- MOS_DEPLOY_RUNTIME_END -->"
        )
        script = (
            "import pathlib\n"
            f"index_path = pathlib.Path({(site_dir + '/index.html')!r})\n"
            "if not index_path.exists():\n"
            "    raise SystemExit(0)\n"
            f"block = {block!r}\n"
            "start_marker = '<!-- MOS_DEPLOY_RUNTIME_START -->'\n"
            "end_marker = '<!-- MOS_DEPLOY_RUNTIME_END -->'\n"
            "raw = index_path.read_text(encoding='utf-8')\n"
            "if start_marker in raw and end_marker in raw:\n"
            "    start_idx = raw.index(start_marker)\n"
            "    end_idx = raw.index(end_marker) + len(end_marker)\n"
            "    raw = raw[:start_idx] + block + raw[end_idx:]\n"
            "elif '</head>' in raw:\n"
            "    raw = raw.replace('</head>', block + '</head>', 1)\n"
            "else:\n"
            "    raw = block + raw\n"
            "index_path.write_text(raw, encoding='utf-8')\n"
        )
        self.run(f"python3 -c {shlex.quote(script)}")

    def _write_funnel_artifact_payload(self, *, site_dir: str, source: FunnelArtifactSourceSpec) -> None:
        artifact = source.artifact or {}
        meta = artifact.get("meta")
        products = artifact.get("products")
        assets = artifact.get("assets")
        if not isinstance(meta, dict):
            raise ValueError("source_ref.artifact.meta must be an object.")
        if not isinstance(products, dict):
            raise ValueError("source_ref.artifact.products must be an object.")

        if assets is not None and not isinstance(assets, dict):
            raise ValueError("source_ref.artifact.assets must be an object when provided.")

        asset_items: dict[str, object] = {}
        if isinstance(assets, dict):
            raw_items = assets.get("items")
            if raw_items is None:
                asset_items = {}
            elif isinstance(raw_items, dict):
                asset_items = raw_items
            else:
                raise ValueError("source_ref.artifact.assets.items must be an object when provided.")

        assets_root = f"{site_dir}/api/public/assets"
        self.run(f"mkdir -p {shlex.quote(assets_root)}")
        for raw_public_id, raw_asset_payload in asset_items.items():
            public_id = str(raw_public_id or "").strip().lower()
            if not public_id:
                raise ValueError("Artifact assets.items keys must be non-empty UUID strings.")
            try:
                normalized_public_id = str(UUID(public_id))
            except ValueError as exc:
                raise ValueError(f"Invalid artifact asset public id '{public_id}'.") from exc
            if not isinstance(raw_asset_payload, dict):
                raise ValueError(f"Artifact asset payload for '{normalized_public_id}' must be an object.")
            raw_content_type = raw_asset_payload.get("contentType")
            if not isinstance(raw_content_type, str) or not raw_content_type.strip():
                raise ValueError(f"Artifact asset '{normalized_public_id}' must include non-empty contentType.")
            content_type = raw_content_type.strip().lower()
            if not content_type.startswith("image/"):
                raise ValueError(
                    f"Artifact asset '{normalized_public_id}' has unsupported contentType '{raw_content_type}'."
                )
            raw_bytes_base64 = raw_asset_payload.get("bytesBase64")
            if not isinstance(raw_bytes_base64, str) or not raw_bytes_base64.strip():
                raise ValueError(f"Artifact asset '{normalized_public_id}' must include non-empty bytesBase64.")
            try:
                decoded_bytes = base64.b64decode(raw_bytes_base64, validate=True)
            except binascii.Error as exc:
                raise ValueError(f"Artifact asset '{normalized_public_id}' has invalid bytesBase64.") from exc
            if not decoded_bytes:
                raise ValueError(f"Artifact asset '{normalized_public_id}' decoded to empty bytes.")
            declared_size = raw_asset_payload.get("sizeBytes")
            if declared_size is not None:
                if not isinstance(declared_size, int) or declared_size < 0:
                    raise ValueError(
                        f"Artifact asset '{normalized_public_id}' sizeBytes must be a non-negative integer."
                    )
                if declared_size != len(decoded_bytes):
                    raise ValueError(
                        f"Artifact asset '{normalized_public_id}' sizeBytes ({declared_size}) does not match decoded byte length ({len(decoded_bytes)})."
                    )
            extension = ""
            if content_type == "image/webp":
                extension = ".webp"
            elif content_type in {"image/jpeg", "image/jpg"}:
                extension = ".jpg"
            elif content_type == "image/png":
                extension = ".png"
            target_path = f"{assets_root}/{normalized_public_id}{extension}"
            self.upload_bytes(decoded_bytes, target_path)

        base_root = f"{site_dir}/api/public/funnels"
        self.run(f"mkdir -p {shlex.quote(base_root)}")

        for raw_product_slug, product_payload in products.items():
            product_slug = str(raw_product_slug or "").strip()
            if not product_slug:
                continue
            if "/" in product_slug or "\\" in product_slug:
                raise ValueError(f"Invalid artifact product slug '{product_slug}'.")
            if not isinstance(product_payload, dict):
                raise ValueError(f"Artifact product payload for '{product_slug}' must be an object.")

            product_meta = product_payload.get("meta")
            funnels = product_payload.get("funnels")
            if not isinstance(product_meta, dict):
                raise ValueError(f"Artifact product '{product_slug}' is missing a meta object.")
            if not isinstance(funnels, dict):
                raise ValueError(f"Artifact product '{product_slug}' is missing a funnels object.")

            product_dir = f"{base_root}/{product_slug}"
            self.run(f"mkdir -p {shlex.quote(product_dir)}")
            self.upload_file(json.dumps(product_meta, ensure_ascii=False), f"{product_dir}/meta.json")
            seen_funnel_path_tokens: set[str] = set()

            for raw_funnel_slug, funnel_payload in funnels.items():
                funnel_slug = str(raw_funnel_slug or "").strip()
                if not funnel_slug:
                    continue
                if "/" in funnel_slug or "\\" in funnel_slug:
                    raise ValueError(
                        f"Invalid artifact funnel slug '{funnel_slug}' for product '{product_slug}'."
                    )
                if not isinstance(funnel_payload, dict):
                    raise ValueError(
                        f"Artifact funnel payload for '{product_slug}/{funnel_slug}' must be an object."
                    )

                funnel_meta = funnel_payload.get("meta")
                pages = funnel_payload.get("pages")
                commerce = funnel_payload.get("commerce")
                if not isinstance(funnel_meta, dict):
                    raise ValueError(
                        f"Artifact funnel '{product_slug}/{funnel_slug}' is missing a meta object."
                    )
                if not isinstance(pages, dict):
                    raise ValueError(
                        f"Artifact funnel '{product_slug}/{funnel_slug}' is missing a pages object."
                    )

                funnel_path_tokens = [funnel_slug]
                funnel_id_token = str(funnel_meta.get("funnelId") or "").strip()
                if funnel_id_token:
                    if "/" in funnel_id_token or "\\" in funnel_id_token:
                        raise ValueError(
                            f"Invalid artifact funnelId '{funnel_id_token}' for '{product_slug}/{funnel_slug}'."
                        )
                    if funnel_id_token != funnel_slug:
                        funnel_path_tokens.append(funnel_id_token)
                    try:
                        short_funnel_id_token = str(UUID(funnel_id_token)).split("-", 1)[0]
                    except ValueError:
                        short_funnel_id_token = ""
                    if short_funnel_id_token and short_funnel_id_token not in funnel_path_tokens:
                        funnel_path_tokens.append(short_funnel_id_token)

                for funnel_path_token in funnel_path_tokens:
                    if funnel_path_token in seen_funnel_path_tokens:
                        raise ValueError(
                            f"Artifact product '{product_slug}' duplicates funnel path token '{funnel_path_token}'."
                        )
                    seen_funnel_path_tokens.add(funnel_path_token)

                    funnel_dir = f"{product_dir}/{funnel_path_token}"
                    pages_dir = f"{funnel_dir}/pages"
                    self.run(f"mkdir -p {shlex.quote(pages_dir)}")
                    self.upload_file(json.dumps(funnel_meta, ensure_ascii=False), f"{funnel_dir}/meta.json")

                    if isinstance(commerce, dict):
                        self.upload_file(json.dumps(commerce, ensure_ascii=False), f"{funnel_dir}/commerce.json")

                    for raw_page_slug, page_payload in pages.items():
                        page_slug = str(raw_page_slug or "").strip()
                        if not page_slug:
                            continue
                        if "/" in page_slug or "\\" in page_slug:
                            raise ValueError(
                                f"Invalid artifact page slug '{page_slug}' for funnel '{product_slug}/{funnel_slug}'."
                            )
                        if not isinstance(page_payload, dict):
                            raise ValueError(
                                f"Artifact page payload for '{product_slug}/{funnel_slug}/{page_slug}' must be an object."
                            )
                        self.upload_file(
                            json.dumps(page_payload, ensure_ascii=False),
                            f"{pages_dir}/{page_slug}.json",
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
        app_dir_q = shlex.quote(app_dir)
        site_dir_q = shlex.quote(site_dir)

        self.run(f"mkdir -p {app_dir_q}")
        self.run(f"rm -rf {site_dir_q}")
        self.run(f"mkdir -p {site_dir_q}")
        if self._path_exists(runtime_dist_path):
            dist_q = shlex.quote(runtime_dist_path)
            self.run(f"cp -R {dist_q}/. {site_dir_q}/")
        else:
            local_dist = self._ensure_local_runtime_dist(runtime_dist_path)
            if local_dist is None:
                raise ValueError(
                    "source_ref.runtime_dist_path was not found on target server or local control-plane host: "
                    f"{runtime_dist_path}. Build/copy the runtime bundle there or set "
                    "DEPLOY_ARTIFACT_RUNTIME_DIST_PATH to a valid path."
                )
            runtime_hash = self._hash_local_directory(local_dist)
            cached_runtime_dir = f"{_RUNTIME_CACHE_DIR}/{runtime_hash}"
            if not self._path_exists(cached_runtime_dir):
                self.run(f"mkdir -p {shlex.quote(_RUNTIME_CACHE_DIR)}")
                self.run(f"mkdir -p {shlex.quote(cached_runtime_dir)}")
                self._upload_local_directory(local_dir=local_dist, remote_dir=cached_runtime_dir)
            cached_runtime_q = shlex.quote(cached_runtime_dir)
            self.run(f"cp -R {cached_runtime_q}/. {site_dir_q}/")
        self._inject_funnel_runtime_config(site_dir=site_dir, source=source)
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

        conf = f"""server {{
    listen {listen_port};
    server_name {server_name_line};
    root {site_dir};
    index index.html;
    client_max_body_size 25m;
    proxy_connect_timeout {_NGINX_PROXY_CONNECT_TIMEOUT};
    proxy_send_timeout {_NGINX_PROXY_SEND_TIMEOUT};
    proxy_read_timeout {_NGINX_PROXY_READ_TIMEOUT};

    location = /api/public/checkout {{
        default_type application/json;
        return 501 '{{"detail":"Checkout is unavailable in standalone artifact mode."}}';
    }}

    location ^~ /api/public/events {{
        return 204;
    }}

    location ^~ /api/public/assets/ {{
        try_files $uri $uri.webp $uri.jpg $uri.jpeg $uri.png =404;
    }}

    location ^~ /public/assets/ {{
        try_files /api$uri /api$uri.webp /api$uri.jpg /api$uri.jpeg /api$uri.png =404;
    }}

    location ^~ /api/public/funnels/ {{
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
