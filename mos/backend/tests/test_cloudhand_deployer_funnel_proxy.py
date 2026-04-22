from __future__ import annotations

import ast
import base64
import hashlib
import io
import json
import os
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace
import pytest
from PIL import Image

import cloudhand.adapters.deployer as deployer_module
from cloudhand.adapters.deployer import (
    ServerDeployer,
    _build_standalone_render_optimization_css,
    _html_tag_has_aspect_ratio_class,
    _html_tag_has_explicit_box_size_classes,
    _normalize_remote_standalone_fetch_url,
    _parse_fontawesome_icon_codepoints,
    _rewrite_standalone_compliance_navigation_links,
)
from cloudhand.models import ApplicationSpec
from cloudhand.models import FunnelArtifactRenderMode


def _make_png_bytes(*, width: int, height: int, color: tuple[int, int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _make_jpeg_bytes(*, width: int, height: int, color: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def _make_noisy_jpeg_bytes(*, width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    noise = Image.effect_noise((width, height), 96).convert("RGB")
    noise.save(buffer, format="JPEG", quality=100, subsampling=0)
    return buffer.getvalue()


_PRIMARY_ASSET_BYTES = _make_png_bytes(width=1600, height=1000, color=(201, 20, 35, 255))
_SECONDARY_ASSET_BYTES = _make_png_bytes(width=1200, height=800, color=(24, 24, 24, 255))
_TERTIARY_ASSET_BYTES = _make_png_bytes(width=900, height=600, color=(245, 241, 232, 255))


def _funnel_app(
    *,
    name: str = "landing-page",
    ports: list[int] | None = None,
    server_names: list[str] | None = None,
    https: bool = False,
) -> ApplicationSpec:
    payload = {
        "name": name,
        "source_type": "funnel_publication",
        "source_ref": {
            "public_id": "f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
            "upstream_base_url": "https://moshq.app",
            "upstream_api_base_url": "https://moshq.app/api/public/funnels/f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
        },
        "runtime": "static",
        "build_config": {
            "install_command": None,
            "build_command": None,
            "system_packages": [],
        },
        "service_config": {
            "command": None,
            "environment": {},
            "ports": ports or [],
            "server_names": server_names or [],
            "https": https,
        },
        "destination_path": "/opt/apps",
    }
    return ApplicationSpec.model_validate(payload)


def _git_app(
    name: str = "legacy-app",
    *,
    command: str | None = "npm run start",
    static_root: str | None = None,
    spa_fallback: bool = False,
    ports: list[int] | None = None,
    server_names: list[str] | None = None,
) -> ApplicationSpec:
    payload = {
        "name": name,
        "source_type": "git",
        "repo_url": "https://github.com/example/repo",
        "branch": "main",
        "runtime": "nodejs",
        "build_config": {
            "install_command": "npm ci",
            "build_command": "npm run build",
            "system_packages": [],
        },
        "service_config": {
            "command": command,
            "static_root": static_root,
            "spa_fallback": spa_fallback,
            "environment": {},
            "ports": ports or [3000],
            "server_names": server_names or ["example.com"],
            "https": False,
        },
        "destination_path": "/opt/apps",
    }
    return ApplicationSpec.model_validate(payload)


def _artifact_app(
    *,
    name: str = "landing-artifact",
    ports: list[int] | None = None,
    server_names: list[str] | None = None,
    workspace_server_names: list[str] | None = None,
    render_mode: str = "runtime_bundle",
    html_document: str | None = None,
) -> ApplicationSpec:
    commerce_payload = None
    page_payload = {
        "funnelId": "funnel-1",
        "publicationId": "pub-1",
        "pageId": "page-1",
        "slug": "presales",
        "puckData": {
            "root": {"props": {}},
            "content": [
                {
                    "type": "PreSalesPage",
                    "props": {
                        "id": "root-page",
                        "anchorId": "top",
                        "content": [
                            {
                                "type": "PreSalesHero",
                                "props": {
                                    "id": "hero-1",
                                    "config": {
                                        "hero": {
                                            "title": "Hero title",
                                            "subtitle": "Hero subtitle",
                                            "media": {
                                                "type": "image",
                                                "alt": "Hero image",
                                                "assetPublicId": "11111111-1111-1111-1111-111111111111",
                                            },
                                        },
                                        "badges": [],
                                    },
                                },
                            }
                        ],
                    },
                }
            ],
            "zones": {},
        },
        "pageMap": {"page-1": "presales"},
    }
    if html_document is not None:
        page_payload = {
            "funnelId": "funnel-1",
            "funnelSlug": "example-funnel",
            "productSlug": "example-product",
            "publicationId": "pub-1",
            "pageId": "page-1",
            "slug": "presales",
            "stage": "sales",
            "pageStageMap": {"page-1": "sales"},
            "tracking": {
                "provider": "meta",
                "mode": "public_funnel_runtime",
                "metaPixelId": "pixel-123",
                "posthogProjectApiKey": "gPFG-Lz2YfpQgyEjLvec7KsmvBEbyiQa8HkeY8lsmVk",
                "posthogApiHost": "https://us.i.posthog.com",
                "posthogDefaults": "2026-01-30",
                "posthogPersonProfiles": "identified_only",
            },
            "puckData": {
                "root": {"props": {"title": "Imported HTML"}},
                "content": [
                    {
                        "type": "ImportedHtmlDocument",
                        "props": {
                            "id": "imported-html-document",
                            "title": "Imported HTML",
                            "sourceLabel": "sales-page.html",
                            "htmlDocument": html_document,
                            "instrumentationManifest": {
                                "schemaVersion": "imported-html-instrumentation-v1",
                                "pageStage": "sales",
                                "bindings": [
                                    {
                                        "id": "primary-buy",
                                        "type": "checkout",
                                        "selector": "#main-cta",
                                        "event": "click",
                                        "trackEventType": "sales_to_checkout_click",
                                        "checkout": {
                                            "mode": "public_checkout",
                                            "variantResolver": {
                                                "type": "fixed",
                                                "variantId": "variant-1",
                                            },
                                        },
                                    }
                                ],
                            },
                        },
                    }
                ],
                "zones": {},
            },
            "pageMap": {"page-1": "presales"},
        }
        commerce_payload = {
            "productSlug": "example-product",
            "funnelSlug": "example-funnel",
            "funnelId": "funnel-1",
            "product": {
                "id": "product-1",
                "variants": [
                    {
                        "id": "variant-1",
                        "provider": "shopify",
                        "price": 4900,
                        "currency": "USD",
                        "option_values": {},
                    }
                ],
                "variants_count": 1,
            },
        }

    source_ref = {
        "client_id": "f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
        "upstream_api_base_root": (
            "https://api.moshq.app"
            if render_mode == "standalone_imported_html"
            else "https://moshq.app/api"
        ),
        "artifact_render_mode": render_mode,
        "artifact": {
            "meta": {
                "clientId": "f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
            },
            "assets": {
                "totalBytes": 11,
                "items": {
                    "11111111-1111-1111-1111-111111111111": {
                        "contentType": "image/png",
                        "sizeBytes": len(_PRIMARY_ASSET_BYTES),
                        "bytesBase64": base64.b64encode(_PRIMARY_ASSET_BYTES).decode("ascii"),
                    },
                    "22222222-2222-2222-2222-222222222222": {
                        "contentType": "image/png",
                        "sizeBytes": len(_SECONDARY_ASSET_BYTES),
                        "bytesBase64": base64.b64encode(_SECONDARY_ASSET_BYTES).decode("ascii"),
                    },
                    "33333333-3333-3333-3333-333333333333": {
                        "contentType": "image/png",
                        "sizeBytes": len(_TERTIARY_ASSET_BYTES),
                        "bytesBase64": base64.b64encode(_TERTIARY_ASSET_BYTES).decode("ascii"),
                    }
                },
            },
            "products": {
                "example-product": {
                    "meta": {
                        "productId": "product-1",
                        "productSlug": "example-product",
                    },
                    "funnels": {
                        "example-funnel": {
                            "meta": {
                                "funnelSlug": "example-funnel",
                                "funnelId": "funnel-1",
                                "publicationId": "pub-1",
                                "entrySlug": "presales",
                                "pages": [{"pageId": "page-1", "slug": "presales"}],
                            },
                            "pages": {
                                "presales": page_payload,
                            },
                            "commerce": commerce_payload,
                        }
                    }
                }
            },
        },
    }
    if render_mode == "runtime_bundle":
        source_ref["runtime_dist_path"] = "mos/frontend/dist"

    payload = {
        "name": name,
        "source_type": "funnel_artifact",
        "source_ref": source_ref,
        "runtime": "static",
        "build_config": {
            "install_command": None,
            "build_command": None,
            "system_packages": [],
        },
        "service_config": {
            "command": None,
            "environment": {},
            "ports": ports or [24123],
            "server_names": server_names or [],
            "https": False,
        },
        "workspace_server_names": workspace_server_names or [],
        "destination_path": "/opt/apps",
    }
    return ApplicationSpec.model_validate(payload)


def _stub_deployer():
    deployer = object.__new__(ServerDeployer)
    deployer.ip = "127.0.0.1"
    deployer.local_root = Path.cwd()
    uploaded: dict[str, str | bytes] = {}
    commands: list[str] = []

    def normalize_remote_path(remote_path: str) -> str:
        return re.sub(
            r"(/opt/apps/[^/]+)/(?:site-releases/[^/]+|site\.__staging__[^/]+)",
            r"\1/site",
            remote_path,
        )

    def fake_upload(content: str, remote_path: str):
        uploaded[normalize_remote_path(remote_path)] = content

    def fake_upload_bytes(content: bytes, remote_path: str):
        uploaded[normalize_remote_path(remote_path)] = content

    def fake_run(cmd: str, cwd: str = None, mask=None) -> str:
        commands.append(cmd)
        return ""

    deployer.upload_file = fake_upload
    deployer.upload_bytes = fake_upload_bytes
    deployer.run = fake_run
    deployer._path_exists = lambda path: True
    deployer._enable_https = lambda server_names: None
    deployer._measure_standalone_imported_html_image_layouts = lambda **_: {}
    deployer._validate_standalone_imported_html_visual_parity = lambda **_: None
    deployer._validate_funnel_artifact_site_output = lambda **_: None
    return deployer, uploaded, commands


def _extract_runtime_block(script_text: str) -> str:
    for line in script_text.splitlines():
        if not line.startswith("block = "):
            continue
        return ast.literal_eval(line[len("block = ") :])
    raise AssertionError("Runtime injection script did not contain a block assignment.")


class _FakeRemoteFile:
    def __init__(self, *, sftp, path: str) -> None:
        self._sftp = sftp
        self._path = path

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def write(self, content):
        self._sftp.files[self._path] = content


class _FakeSFTP:
    def __init__(self) -> None:
        self.directories = {"/", "/opt"}
        self.files: dict[str, str | bytes] = {}
        self.mkdir_calls: list[str] = []

    def stat(self, path: str):
        if path in self.directories or path in self.files:
            return SimpleNamespace()
        raise FileNotFoundError(path)

    def mkdir(self, path: str):
        self.directories.add(path)
        self.mkdir_calls.append(path)

    def file(self, path: str, mode: str):
        parent = Path(path).parent.as_posix()
        if parent not in self.directories:
            raise FileNotFoundError(path)
        return _FakeRemoteFile(sftp=self, path=path)

    def close(self):
        return None


class _FakeTransport:
    def is_active(self) -> bool:
        return True


class _FakeSSHClient:
    def __init__(self, sftp: _FakeSFTP) -> None:
        self._sftp = sftp

    def get_transport(self):
        return _FakeTransport()

    def open_sftp(self):
        return self._sftp


def test_env_file_upload_normalizes_shell_style_assignments_for_systemd(tmp_path):
    env_file = tmp_path / ".env.example"
    env_file.write_text(
        "\n".join(
            [
                "# API keys",
                'GOOGLE_API_KEY="AIzaSyAXBYbLxxHGZIpS4sR69VQ5AQY7qJcf8k8"             # Optional, for Google Gemini models.',
                "GEMINI_API_KEY=AIzaSyAXBYbLxxHGZIpS4sR69VQ5AQY7qJcf8k8",
                'OPENAI_API_KEY="sk-test" # Optional, for OpenAI models.',
                "EMPTY_VALUE=",
                "",
            ]
        ),
        encoding="utf-8",
    )

    app = _git_app(name="env-normalizer")
    app.service_config.environment_file_upload = str(env_file)
    app.service_config.environment_file = "/etc/cloudhand/env/env-normalizer.env"
    app.service_config.environment = {"LLM_DEFAULT_MODEL": "claude-opus-4-6"}

    deployer, uploaded, _commands = _stub_deployer()
    directives = deployer._env_file_directives(app, "/opt/apps/env-normalizer")

    assert directives == "EnvironmentFile=/etc/cloudhand/env/env-normalizer.env"
    assert uploaded["/etc/cloudhand/env/env-normalizer.env"] == (
        "GOOGLE_API_KEY=AIzaSyAXBYbLxxHGZIpS4sR69VQ5AQY7qJcf8k8\n"
        "GEMINI_API_KEY=AIzaSyAXBYbLxxHGZIpS4sR69VQ5AQY7qJcf8k8\n"
        "OPENAI_API_KEY=sk-test\n"
        "EMPTY_VALUE=\n"
        "LLM_DEFAULT_MODEL=claude-opus-4-6\n"
    )


def test_upload_file_creates_missing_remote_parent_directories():
    deployer = object.__new__(ServerDeployer)
    sftp = _FakeSFTP()
    deployer.client = _FakeSSHClient(sftp)
    deployer.connect = lambda: None

    deployer.upload_file("hello", "/opt/apps/example/site/contact-us/index.html")

    assert sftp.files["/opt/apps/example/site/contact-us/index.html"] == "hello"
    assert "/opt/apps" in sftp.mkdir_calls
    assert "/opt/apps/example" in sftp.mkdir_calls
    assert "/opt/apps/example/site" in sftp.mkdir_calls
    assert "/opt/apps/example/site/contact-us" in sftp.mkdir_calls


def test_upload_bytes_wraps_remote_parent_directory_creation_errors():
    deployer = object.__new__(ServerDeployer)

    class _BrokenSFTP(_FakeSFTP):
        def mkdir(self, path: str):
            if path == "/opt/apps":
                raise FileNotFoundError(path)
            super().mkdir(path)

    sftp = _BrokenSFTP()
    deployer.client = _FakeSSHClient(sftp)
    deployer.connect = lambda: None

    with pytest.raises(ValueError, match="Failed to create remote directory '/opt/apps'"):
        deployer.upload_bytes(b"abc", "/opt/apps/example/site/index.html")


def test_funnel_proxy_redirects_slug_paths_on_same_host_and_port():
    app = _funnel_app(ports=[24123], server_names=[], https=False)
    deployer, uploaded, commands = _stub_deployer()

    deployer._configure_funnel_publication_proxy(app)

    conf = uploaded["/etc/nginx/sites-available/landing-page"]
    assert "listen 24123;" in conf
    assert "server_name _;" in conf
    assert "location = / {" in conf
    assert "return 302 /f/f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95$is_args$args;" in conf
    assert "location ^~ /f/f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95/ {" in conf
    assert "location / {" in conf
    assert "return 302 /f/f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95$request_uri;" in conf
    assert "proxy_pass https://moshq.app/f/f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95$request_uri;" not in conf

    assert "ln -sf /etc/nginx/sites-available/landing-page /etc/nginx/sites-enabled/landing-page" in commands
    assert "systemctl reload nginx" in commands


def test_funnel_proxy_uses_standard_http_port_when_server_names_are_configured():
    app = _funnel_app(ports=[24123], server_names=["landing.example.com"], https=False)
    deployer, uploaded, _commands = _stub_deployer()

    deployer._configure_funnel_publication_proxy(app)

    conf = uploaded["/etc/nginx/sites-available/landing-page"]
    assert "listen 80;" in conf
    assert "listen 24123;" not in conf
    assert "server_name landing.example.com;" in conf


def test_funnel_proxy_requires_port_when_server_names_are_empty():
    app = _funnel_app(ports=[], server_names=[], https=False)
    deployer, _uploaded, _commands = _stub_deployer()

    with pytest.raises(ValueError, match="service_config.ports must include one port"):
        deployer._configure_funnel_publication_proxy(app)


def test_generic_nginx_config_allows_large_upload_bodies():
    app = _git_app(name="api-service")
    app.service_config.server_names = ["api.example.com"]
    app.service_config.ports = [8008]
    deployer, uploaded, commands = _stub_deployer()
    deployer._ensure_nginx = lambda: None

    deployer._configure_nginx(app)

    conf = uploaded["/etc/nginx/sites-available/api-service"]
    assert "listen 80;" in conf
    assert "server_name api.example.com;" in conf
    assert "client_max_body_size 250m;" in conf
    assert "proxy_pass http://127.0.0.1:8008;" in conf
    assert "systemctl reload nginx" in commands


def test_git_static_site_config_serves_built_spa_with_history_fallback():
    app = _git_app(
        name="mos-ui",
        command=None,
        static_root="mos/frontend/dist",
        spa_fallback=True,
        server_names=["moshq.app"],
    )
    deployer, uploaded, commands = _stub_deployer()

    deployer._configure_git_static_site(app, "/opt/apps/mos-ui")

    conf = uploaded["/etc/nginx/sites-available/mos-ui"]
    assert "listen 80;" in conf
    assert "server_name moshq.app;" in conf
    assert "root /opt/apps/mos-ui/mos/frontend/dist;" in conf
    assert "index index.html;" in conf
    assert "try_files $uri $uri/ /index.html;" in conf
    assert "proxy_pass" not in conf
    assert "nginx -t" in commands
    assert "systemctl reload nginx" in commands


def test_deploy_git_static_site_builds_then_replaces_old_service_with_nginx():
    app = _git_app(
        name="mos-ui",
        command=None,
        static_root="mos/frontend/dist",
        spa_fallback=True,
        server_names=["moshq.app"],
    )
    deployer, uploaded, commands = _stub_deployer()
    removed_paths: list[tuple[str, bool]] = []
    configure_systemd_calls: list[tuple[str, str]] = []

    deployer._service_unit_exists = lambda service_name: service_name == "mos-ui"
    deployer._remove_path_if_exists = lambda path, recursive=False: removed_paths.append((path, recursive)) or (
        path == "/etc/systemd/system/mos-ui.service"
    )
    deployer._port_is_listening = lambda port: False
    deployer._configure_systemd = lambda app_arg, app_dir_arg: configure_systemd_calls.append((app_arg.name, app_dir_arg))

    deployer.deploy(app)

    assert any(cmd == "npm ci" for cmd in commands)
    assert any(cmd == "npm run build" for cmd in commands)
    assert any(cmd.startswith("systemctl stop") and "mos-ui.service" in cmd for cmd in commands)
    assert any(cmd.startswith("systemctl disable") and "mos-ui.service" in cmd for cmd in commands)
    assert "/etc/nginx/sites-available/mos-ui" in uploaded
    assert ("/etc/systemd/system/mos-ui.service", False) in removed_paths
    assert configure_systemd_calls == []


def test_remove_workload_cleans_service_nginx_and_app_dir():
    app = _git_app(name="honest-herbalist")
    deployer, _uploaded, commands = _stub_deployer()

    removed: list[tuple[str, bool]] = []
    existing_paths = {
        "/etc/systemd/system/honest-herbalist.service": True,
        "/etc/nginx/sites-enabled/honest-herbalist": True,
        "/etc/nginx/sites-available/honest-herbalist": True,
        "/opt/apps/honest-herbalist": True,
    }

    deployer._service_unit_exists = lambda service_name: service_name == "honest-herbalist"

    def fake_remove(path: str, recursive: bool = False) -> bool:
        removed.append((path, recursive))
        return existing_paths.get(path, False)

    deployer._remove_path_if_exists = fake_remove

    deployer.remove_workload(app)

    assert any(cmd.startswith("systemctl stop") and "honest-herbalist.service" in cmd for cmd in commands)
    assert any(cmd.startswith("systemctl disable") and "honest-herbalist.service" in cmd for cmd in commands)
    assert "systemctl daemon-reload" in commands
    assert "nginx -t" in commands
    assert "systemctl reload nginx" in commands
    assert ("/etc/systemd/system/honest-herbalist.service", False) in removed
    assert ("/etc/nginx/sites-enabled/honest-herbalist", False) in removed
    assert ("/etc/nginx/sites-available/honest-herbalist", False) in removed
    assert ("/opt/apps/honest-herbalist", True) in removed


def test_deploy_funnel_artifact_updates_in_place_without_removing_existing_workload():
    app = _artifact_app()
    deployer, _uploaded, _commands = _stub_deployer()

    configure_calls: list[str] = []
    disable_calls: list[str] = []
    deployer.remove_workload = lambda _app: (_ for _ in ()).throw(AssertionError("remove_workload should not run"))
    deployer._disable_service_unit = lambda service_name: disable_calls.append(service_name)
    deployer._configure_nginx = lambda app_arg: configure_calls.append(app_arg.name)

    deployer.deploy(app)

    assert disable_calls == ["landing-artifact"]
    assert configure_calls == ["landing-artifact"]


def test_deploy_funnel_publication_updates_in_place_without_removing_existing_workload():
    app = _funnel_app()
    deployer, _uploaded, _commands = _stub_deployer()

    configure_calls: list[str] = []
    disable_calls: list[str] = []
    deployer.remove_workload = lambda _app: (_ for _ in ()).throw(AssertionError("remove_workload should not run"))
    deployer._disable_service_unit = lambda service_name: disable_calls.append(service_name)
    deployer._configure_nginx = lambda app_arg: configure_calls.append(app_arg.name)

    deployer.deploy(app)

    assert disable_calls == ["landing-page"]
    assert configure_calls == ["landing-page"]


def test_funnel_artifact_site_proxies_live_api_and_keeps_bundle_routes():
    app = _artifact_app()
    deployer, uploaded, commands = _stub_deployer()

    deployer._configure_funnel_artifact_site(app)

    conf = uploaded["/etc/nginx/sites-available/landing-artifact"]
    assert "listen 24123;" in conf
    assert "server_name _;" in conf
    assert "return 302 /f/" not in conf
    assert 'location ^~ /api/public/assets/ {' in conf
    assert 'try_files $uri $uri.webp $uri.jpg $uri.jpeg $uri.png =404;' in conf
    assert 'add_header Cache-Control "public, max-age=31536000, immutable";' in conf
    assert 'location ^~ /public/assets/ {' in conf
    assert 'try_files /api$uri /api$uri.webp /api$uri.jpg /api$uri.jpeg /api$uri.png =404;' in conf
    assert 'location ^~ /_standalone-assets/ {' in conf
    assert 'try_files $uri =404;' in conf
    assert "location ^~ /api/ {" in conf
    assert "proxy_pass https://moshq.app/api/;" in conf
    assert "proxy_pass https://moshq.app/api/public/assets/;" not in conf
    assert "Checkout is unavailable in standalone artifact mode." not in conf
    assert "try_files $uri.json =404;" not in conf
    assert "try_files $uri /index.html;" in conf

    meta_path = "/opt/apps/landing-artifact/site/api/public/funnels/example-product/example-funnel/meta.json"
    page_path = "/opt/apps/landing-artifact/site/api/public/funnels/example-product/example-funnel/pages/presales.json"
    id_meta_path = "/opt/apps/landing-artifact/site/api/public/funnels/example-product/funnel-1/meta.json"
    id_page_path = "/opt/apps/landing-artifact/site/api/public/funnels/example-product/funnel-1/pages/presales.json"
    asset_path = "/opt/apps/landing-artifact/site/api/public/assets/11111111-1111-1111-1111-111111111111.png"
    public_asset_path = "/opt/apps/landing-artifact/site/public/assets/11111111-1111-1111-1111-111111111111.png"
    assert meta_path in uploaded
    assert page_path in uploaded
    assert id_meta_path in uploaded
    assert id_page_path in uploaded
    assert asset_path in uploaded
    assert public_asset_path in uploaded
    assert uploaded[asset_path] == _PRIMARY_ASSET_BYTES
    assert uploaded[public_asset_path] == _PRIMARY_ASSET_BYTES

    assert "nginx -t" in commands
    assert "systemctl reload nginx" in commands


def test_funnel_artifact_site_exports_standalone_imported_html_without_runtime_bundle():
    html_document = """<!DOCTYPE html>
<html>
  <head>
    <title>Standalone Sales</title>
  </head>
  <body>
    <main id="app">
      <img src="/public/assets/11111111-1111-1111-1111-111111111111" alt="Hero">
      <img src="/public/assets/22222222-2222-2222-2222-222222222222" alt="Gallery 1">
      <img src="/public/assets/33333333-3333-3333-3333-333333333333" alt="Gallery 2" loading="lazy">
      <a id="main-cta" href="#shop">Start my protocol</a>
    </main>
  </body>
</html>
"""
    app = _artifact_app(render_mode="standalone_imported_html", html_document=html_document)
    deployer, uploaded, commands = _stub_deployer()

    deployer._configure_funnel_artifact_site(app)

    conf = uploaded["/etc/nginx/sites-available/landing-artifact"]
    assert "return 302 /example-product/example-funnel/presales$is_args$args;" in conf
    assert "try_files $uri $uri/index.html $uri/ =404;" in conf
    assert "try_files $uri /index.html;" not in conf
    assert "gzip on;" in conf
    assert "gzip_types text/plain text/css text/javascript application/javascript application/json application/xml image/svg+xml;" in conf
    assert not any(path.startswith("/tmp/cloudhand-runtime-config-") for path in uploaded)
    assert not any(cmd.startswith("cp -R ") for cmd in commands)
    assert not any(cmd.startswith("python3 -c ") for cmd in commands)

    entry_route_path = "/opt/apps/landing-artifact/site/example-product/example-funnel/index.html"
    page_route_path = "/opt/apps/landing-artifact/site/example-product/example-funnel/presales/index.html"
    alias_entry_route_path = "/opt/apps/landing-artifact/site/example-product/funnel-1/index.html"
    alias_page_route_path = "/opt/apps/landing-artifact/site/example-product/funnel-1/presales/index.html"
    asset_path = "/opt/apps/landing-artifact/site/api/public/assets/11111111-1111-1111-1111-111111111111.png"
    public_asset_path = "/opt/apps/landing-artifact/site/public/assets/11111111-1111-1111-1111-111111111111.png"
    runtime_page_path = "/opt/apps/landing-artifact/site/api/public/funnels/example-product/example-funnel/pages/presales.json"

    entry_html = uploaded[entry_route_path]
    page_html = uploaded[page_route_path]
    alias_entry_html = uploaded[alias_entry_route_path]
    alias_page_html = uploaded[alias_page_route_path]

    assert "<main id=\"app\">" in entry_html
    assert "MOS_STANDALONE_IMPORTED_HTML_BRIDGE_START" in entry_html
    assert "\"apiBasePath\":\"/api\"" in entry_html
    assert 'rel="preload" as="image" fetchpriority="high" href="/public/assets/11111111-1111-1111-1111-111111111111"' in entry_html
    assert 'src="/public/assets/11111111-1111-1111-1111-111111111111" alt="Hero" loading="eager" decoding="async" fetchpriority="high"' in entry_html
    assert 'src="/public/assets/22222222-2222-2222-2222-222222222222" alt="Gallery 1" loading="lazy" decoding="async" fetchpriority="low"' in entry_html
    assert 'src="/public/assets/33333333-3333-3333-3333-333333333333" alt="Gallery 2" loading="lazy" decoding="async" fetchpriority="low"' in entry_html
    assert "/public/events" in entry_html
    assert "navigator.sendBeacon" in entry_html
    assert 'new Blob([payload], { type: "application/json" })' in entry_html
    assert "pageLifecycleFinalizing = true;" in entry_html
    assert "/public/checkout" in entry_html
    assert "/public/checkout/prepare" not in entry_html
    assert "standalone_html" in entry_html
    assert "web_vital_recorded" in entry_html
    assert "metricName" in entry_html
    assert "document.write" not in entry_html
    assert "__MOS_DEPLOY_RUNTIME__" not in entry_html
    assert "funnel_visitor_id" in entry_html
    assert "pixel-123" in entry_html
    assert "gPFG-Lz2YfpQgyEjLvec7KsmvBEbyiQa8HkeY8lsmVk" in entry_html
    assert "https://us.i.posthog.com" in entry_html
    assert "window.posthog.init(" in entry_html
    assert "posthog.capture(eventType, eventProps);" in entry_html

    assert page_html == entry_html
    assert "/example-product/example-funnel/presales/" in entry_html
    assert alias_entry_html == alias_page_html
    assert "/example-product/funnel-1/presales/" in alias_entry_html
    assert uploaded[asset_path] == _PRIMARY_ASSET_BYTES
    assert uploaded[public_asset_path] == _PRIMARY_ASSET_BYTES
    assert runtime_page_path not in uploaded


def test_funnel_artifact_site_standalone_builds_release_before_live_activation():
    html_document = """<!DOCTYPE html>
<html>
  <head><title>Standalone Sales</title></head>
  <body><a id="main-cta" href="#shop">Start</a></body>
</html>
"""
    app = _artifact_app(render_mode="standalone_imported_html", html_document=html_document)
    deployer, uploaded, commands = _stub_deployer()

    deployer._configure_funnel_artifact_site(app)

    conf = uploaded["/etc/nginx/sites-available/landing-artifact"]
    assert "root /opt/apps/landing-artifact/site;" in conf
    assert any(cmd.startswith("mkdir -p /opt/apps/landing-artifact/site-releases") for cmd in commands)
    assert any(cmd.startswith("mkdir -p /opt/apps/landing-artifact/site-releases/") for cmd in commands)
    assert any("ln -sfn " in cmd and "/opt/apps/landing-artifact/site.__next__" in cmd for cmd in commands)
    assert any("mv -Tf \"$next_link\" \"$live_site\"" in cmd for cmd in commands)


def test_standalone_imported_html_rewrites_upstream_public_asset_urls_to_artifact_assets(monkeypatch):
    monkeypatch.setattr(deployer_module, "_STANDALONE_MAX_COMPRESSED_IMAGE_ROUTE_CANDIDATES", 0)
    monkeypatch.setattr(deployer_module, "_STANDALONE_MAX_TINY_IMAGE_ROUTE_CANDIDATES", 0)
    monkeypatch.setattr(deployer_module, "_STANDALONE_MAX_RESPONSIVE_IMAGE_CANDIDATES", 0)
    html_document = """<!DOCTYPE html>
<html>
  <head>
    <title>Standalone Sales</title>
  </head>
  <body>
    <main id="app">
      <img src="https://moshq.app/api/public/assets/11111111-1111-1111-1111-111111111111" alt="Hero">
      <a id="main-cta" href="#shop">Start my protocol</a>
    </main>
  </body>
</html>
"""
    app = _artifact_app(
        render_mode="standalone_imported_html",
        html_document=html_document,
        workspace_server_names=["shop.example.com"],
    )
    deployer, uploaded, _commands = _stub_deployer()
    observed_urls: list[str] = []

    def fetch_remote_image(**kwargs):
        observed_urls.append(kwargs["url"])
        return _PRIMARY_ASSET_BYTES, "image/png"

    deployer._fetch_remote_standalone_image_asset = fetch_remote_image
    deployer._configure_funnel_artifact_site(app)

    entry_route_path = "/opt/apps/landing-artifact/site/example-product/example-funnel/index.html"
    mirrored_digest = hashlib.sha256(_PRIMARY_ASSET_BYTES).hexdigest()[:32]
    mirrored_path = f"/opt/apps/landing-artifact/site/_standalone-assets/{mirrored_digest}.png"
    entry_html = uploaded[entry_route_path]
    assert observed_urls == ["https://moshq.app/api/public/assets/11111111-1111-1111-1111-111111111111"]
    assert "https://moshq.app/api/public/assets/" not in entry_html
    assert f'src="/_standalone-assets/{mirrored_digest}.png"' in entry_html
    assert f'href="/_standalone-assets/{mirrored_digest}.png"' in entry_html
    assert uploaded[mirrored_path] == _PRIMARY_ASSET_BYTES


def test_funnel_artifact_site_standalone_internal_navigation_preserves_query_params():
    html_document = """<!DOCTYPE html>
<html>
  <body>
    <a id="main-cta" href="#shop">Check availability</a>
  </body>
</html>
"""
    app = _artifact_app(render_mode="standalone_imported_html", html_document=html_document)
    page_payload = app.source_ref.artifact["products"]["example-product"]["funnels"]["example-funnel"]["pages"][
        "presales"
    ]
    page_payload["stage"] = "pre_sales"
    page_payload["pageMap"] = {"page-1": "presales", "page-2": "sales-page"}
    page_payload["pageStageMap"] = {"page-1": "pre_sales", "page-2": "sales"}
    page_payload["puckData"]["content"][0]["props"]["instrumentationManifest"] = {
        "schemaVersion": "imported-html-instrumentation-v1",
        "pageStage": "pre_sales",
        "bindings": [
            {
                "id": "presales-cta",
                "type": "internal_navigation",
                "selector": "#main-cta",
                "event": "click",
                "targetPageId": "page-2",
                "trackEventType": "pre_sales_to_sales_click",
            }
        ],
    }

    deployer, uploaded, _commands = _stub_deployer()

    deployer._configure_funnel_artifact_site(app)

    entry_route_path = "/opt/apps/landing-artifact/site/example-product/example-funnel/index.html"
    entry_html = uploaded[entry_route_path]

    assert "const buildInternalNavigationUrl = (targetPath, options) => {" in entry_html
    assert 'currentUrl.searchParams.delete("checkout");' in entry_html
    assert "nextUrl.search = currentUrl.search;" in entry_html
    assert 'nextUrl.searchParams.set(PRESALE_SOURCE_PARAM, PRESALE_SOURCE_VALUE);' in entry_html
    assert "element.href = buildInternalNavigationUrl(targetPath, {" in entry_html
    assert "window.location.href = buildInternalNavigationUrl(targetPath, {" in entry_html
    assert 'trackMetaPixel("trackCustom", "EnteredSales", pageViewParams);' in entry_html
    assert '"/example-product/example-funnel/sales-page/"' in entry_html


def test_rewrite_standalone_compliance_navigation_links_rewrites_relative_policy_links():
    rewritten = _rewrite_standalone_compliance_navigation_links(
        html_fragment=(
            '<footer>'
            '<a href="contact-us">Contact</a>'
            '<a href="terms-of-service">Terms</a>'
            '<a href="privacy-policy">Privacy</a>'
            '<a href="refund-policy">Refunds</a>'
            "</footer>"
        ),
        shop_path="/example-product/example-funnel/sales-page/",
        footer_terms="/example-product/example-funnel/terms-of-service/",
        footer_privacy="/example-product/example-funnel/privacy-policy/",
        footer_refund="/example-product/example-funnel/refund-policy/",
        footer_contact="/example-product/example-funnel/contact-us/",
    )

    assert 'href="/example-product/example-funnel/contact-us/"' in rewritten
    assert 'href="/example-product/example-funnel/terms-of-service/"' in rewritten
    assert 'href="/example-product/example-funnel/privacy-policy/"' in rewritten
    assert 'href="/example-product/example-funnel/refund-policy/"' in rewritten


def test_funnel_artifact_site_standalone_export_scopes_to_preferred_funnel():
    html_document = """<!DOCTYPE html>
<html>
  <body>
    <img src="/public/assets/11111111-1111-1111-1111-111111111111" alt="Hero">
    <a id="main-cta" href="#shop">Start my protocol</a>
  </body>
</html>
"""
    app = _artifact_app(render_mode="standalone_imported_html", html_document=html_document)
    artifact = app.source_ref.artifact
    artifact["meta"]["updatedFromFunnelId"] = "funnel-1"
    product_payload = artifact["products"]["example-product"]
    product_payload["funnels"]["other-funnel"] = {
        "meta": {
            "funnelSlug": "other-funnel",
            "funnelId": "funnel-2",
            "publicationId": "pub-2",
            "entrySlug": "presales",
            "pages": [{"pageId": "page-2", "slug": "presales"}],
        },
        "pages": {
            "presales": {
                "funnelId": "funnel-2",
                "funnelSlug": "other-funnel",
                "productSlug": "example-product",
                "publicationId": "pub-2",
                "pageId": "page-2",
                "slug": "presales",
                "stage": "sales",
                "pageStageMap": {"page-2": "sales"},
                "tracking": {
                    "provider": "meta",
                    "mode": "public_funnel_runtime",
                    "metaPixelId": "pixel-456",
                    "posthogProjectApiKey": "gPFG-Lz2YfpQgyEjLvec7KsmvBEbyiQa8HkeY8lsmVk",
                    "posthogApiHost": "https://us.i.posthog.com",
                    "posthogDefaults": "2026-01-30",
                    "posthogPersonProfiles": "identified_only",
                },
                "puckData": {
                    "root": {"props": {"title": "Other Funnel"}},
                    "content": [
                        {
                            "type": "ImportedHtmlDocument",
                            "props": {
                                "id": "other-imported-html-document",
                                "title": "Other Funnel",
                                "sourceLabel": "other.html",
                                "htmlDocument": html_document,
                            },
                        }
                    ],
                    "zones": {},
                },
                "pageMap": {"page-2": "presales"},
            }
        },
        "commerce": None,
    }

    deployer, uploaded, _commands = _stub_deployer()

    deployer._configure_funnel_artifact_site(app)

    assert "/opt/apps/landing-artifact/site/example-product/example-funnel/index.html" in uploaded
    assert "/opt/apps/landing-artifact/site/example-product/example-funnel/presales/index.html" in uploaded
    assert "/opt/apps/landing-artifact/site/example-product/other-funnel/index.html" not in uploaded
    assert "/opt/apps/landing-artifact/site/example-product/other-funnel/presales/index.html" not in uploaded


def test_standalone_imported_html_bridge_uses_funnel_meta_publication_id():
    html_document = """<!DOCTYPE html>
<html>
  <body>
    <a id="main-cta" href="#shop">Start my protocol</a>
  </body>
</html>
"""
    app = _artifact_app(render_mode="standalone_imported_html", html_document=html_document)
    funnel_payload = app.source_ref.artifact["products"]["example-product"]["funnels"]["example-funnel"]
    funnel_payload["meta"]["publicationId"] = "pub-2"
    funnel_payload["pages"]["presales"]["publicationId"] = "pub-1"

    deployer, uploaded, _commands = _stub_deployer()

    deployer._configure_funnel_artifact_site(app)

    entry_route_path = "/opt/apps/landing-artifact/site/example-product/example-funnel/presales/index.html"
    entry_html = uploaded[entry_route_path]

    assert '"publicationId":"pub-2"' in entry_html
    assert '"publicationId":"pub-1"' not in entry_html


def test_standalone_imported_html_bridge_augments_checkout_selection_with_purchase_mode():
    html_document = """<!DOCTYPE html>
<html>
  <body>
    <div id="quantity-selector" data-mode="subscribe"></div>
    <a id="main-cta" href="#shop">Start my protocol</a>
  </body>
</html>
"""
    app = _artifact_app(render_mode="standalone_imported_html", html_document=html_document)
    deployer, uploaded, _commands = _stub_deployer()

    deployer._configure_funnel_artifact_site(app)

    entry_route_path = "/opt/apps/landing-artifact/site/example-product/example-funnel/presales/index.html"
    entry_html = uploaded[entry_route_path]

    assert 'document.getElementById("mos-selected-purchase-mode")' in entry_html
    assert 'document.getElementById("quantity-selector")' in entry_html
    assert 'key.trim().toLowerCase() !== "purchasemode"' in entry_html


def test_standalone_imported_html_local_relative_image_assets_are_written(monkeypatch, tmp_path):
    html_document = """<!DOCTYPE html>
<html>
  <body>
    <img src="public/assets/generated/chart.jpg" alt="Chart">
    <a id="main-cta" href="#shop">Start my protocol</a>
  </body>
</html>
"""
    asset_root = tmp_path / "public" / "assets" / "generated"
    asset_root.mkdir(parents=True, exist_ok=True)
    asset_path = asset_root / "chart.jpg"
    asset_path.write_bytes(_make_jpeg_bytes(width=1200, height=800, color=(201, 20, 35)))

    monkeypatch.setattr(
        deployer_module,
        "_STANDALONE_LOCAL_IMAGE_ASSET_ROOTS",
        (tmp_path,),
    )

    app = _artifact_app(render_mode="standalone_imported_html", html_document=html_document)
    deployer, uploaded, _commands = _stub_deployer()

    deployer._configure_funnel_artifact_site(app)

    entry_route_path = "/opt/apps/landing-artifact/site/example-product/example-funnel/presales/index.html"
    entry_html = uploaded[entry_route_path]
    expected_digest = hashlib.sha256(asset_path.read_bytes()).hexdigest()[:32]
    expected_route = f"/_standalone-assets/{expected_digest}.jpg"
    assert f'src="{expected_route}"' in entry_html

    asset_route_path = f"/opt/apps/landing-artifact/site{expected_route}"
    assert asset_route_path in uploaded
    assert isinstance(uploaded[asset_route_path], bytes)


def test_funnel_artifact_site_prepares_imported_html_once_per_page_across_route_tokens(monkeypatch):
    html_document = """<!DOCTYPE html>
<html>
  <body>
    <a id="main-cta" href="#shop">Start my protocol</a>
  </body>
</html>
"""
    app = _artifact_app(render_mode="standalone_imported_html", html_document=html_document)
    funnel_payload = app.source_ref.artifact["products"]["example-product"]["funnels"]["example-funnel"]
    uuid_funnel_id = "18ac0fe1-1e27-4579-ad94-9a1e6c9530fe"
    funnel_payload["meta"]["funnelId"] = uuid_funnel_id
    funnel_payload["pages"]["presales"]["funnelId"] = uuid_funnel_id

    deployer, uploaded, _commands = _stub_deployer()
    prepare_calls: list[str] = []

    def fake_prepare(**kwargs):
        prepare_calls.append(str(kwargs["page_slug"]))
        return "<!DOCTYPE html><html><body><a id=\"main-cta\" href=\"#shop\">Prepared</a></body></html>"

    monkeypatch.setattr(
        deployer,
        "_prepare_standalone_imported_html_document",
        fake_prepare,
    )

    deployer._configure_funnel_artifact_site(app)

    assert prepare_calls == ["presales"]
    assert "/opt/apps/landing-artifact/site/example-product/example-funnel/index.html" in uploaded
    assert f"/opt/apps/landing-artifact/site/example-product/{uuid_funnel_id}/index.html" in uploaded
    assert "/opt/apps/landing-artifact/site/example-product/18ac0fe1/index.html" in uploaded


def test_funnel_artifact_site_compiles_tailwind_and_normalizes_public_asset_urls(monkeypatch):
    html_document = """<!DOCTYPE html>
<html>
  <head>
    <title>Standalone Sales</title>
    <link href="https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700,900&display=swap" rel="stylesheet">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
      tailwind.config = {
        theme: {
          extend: {
            colors: {
              brand: {
                primary: '#C41423'
              }
            }
          }
        }
      }
    </script>
  </head>
  <body>
    <main class="bg-brand-primary text-white">
      <i class="fa-solid fa-star"></i>
      <img src="https://shop.example.com/public/assets/11111111-1111-1111-1111-111111111111" alt="Hero">
      <a id="main-cta" href="#shop">Start my protocol</a>
    </main>
  </body>
</html>
"""
    app = _artifact_app(
        render_mode="standalone_imported_html",
        html_document=html_document,
        server_names=["shop.example.com"],
    )
    deployer, uploaded, _commands = _stub_deployer()
    monkeypatch.setattr(
        deployer,
        "_compile_standalone_imported_html_tailwind_css",
        lambda **_: ".bg-brand-primary{background-color:#C41423}.text-white{color:#fff}",
    )
    fontshare_400 = b"fontshare-400"
    fontshare_700 = b"fontshare-700"
    fontawesome_solid = b"fontawesome-solid"
    google_inter_400 = b"google-inter-400"
    google_inter_700 = b"google-inter-700"
    fontshare_css = (
        "@font-face{font-family:'Satoshi';font-style:normal;font-weight:400;font-display:swap;"
        "src:url('https://cdn.fontshare.com/fonts/satoshi-400.woff2') format('woff2');}"
        "@font-face{font-family:'Satoshi';font-style:normal;font-weight:700;font-display:swap;"
        "src:url('https://cdn.fontshare.com/fonts/satoshi-700.woff2') format('woff2');}"
    ).encode("utf-8")
    google_fonts_css = (
        "@font-face{font-family:'Inter';font-style:normal;font-weight:400;font-display:swap;"
        "src:url('https://fonts.gstatic.com/s/inter/v18/inter-400.woff2') format('woff2');}"
        "@font-face{font-family:'Inter';font-style:normal;font-weight:700;font-display:swap;"
        "src:url('https://fonts.gstatic.com/s/inter/v18/inter-700.woff2') format('woff2');}"
    ).encode("utf-8")
    fontawesome_css = (
        '@font-face{font-family:"Font Awesome 6 Free";font-style:normal;font-weight:900;font-display:block;'
        'src:url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-solid-900.woff2") format("woff2");}'
        '.fa-solid,.fas{font-family:"Font Awesome 6 Free";font-weight:900;}'
        '.fa-star:before{content:"\\\\f005";}'
    ).encode("utf-8")

    def fake_fetch_remote_binary_asset(*, url: str, user_agent: str | None = None, **_kwargs):
        if url == "https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700,900&display=swap":
            assert user_agent is None
            return fontshare_css, "text/css"
        if url == "https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap":
            assert user_agent == deployer_module._STANDALONE_MODERN_BROWSER_USER_AGENT
            return google_fonts_css, "text/css"
        if url == "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css":
            assert user_agent is None
            return fontawesome_css, "text/css"
        if url == "https://cdn.fontshare.com/fonts/satoshi-400.woff2":
            assert user_agent is None
            return fontshare_400, "font/woff2"
        if url == "https://cdn.fontshare.com/fonts/satoshi-700.woff2":
            assert user_agent is None
            return fontshare_700, "font/woff2"
        if url == "https://fonts.gstatic.com/s/inter/v18/inter-400.woff2":
            assert user_agent is None
            return google_inter_400, "font/woff2"
        if url == "https://fonts.gstatic.com/s/inter/v18/inter-700.woff2":
            assert user_agent is None
            return google_inter_700, "font/woff2"
        if url in {
            "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-solid-900.woff2",
            "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-solid-900.ttf",
        }:
            assert user_agent is None
            return fontawesome_solid, "font/woff2"
        raise AssertionError(f"Unexpected mirrored asset request: {url}")

    monkeypatch.setattr(deployer, "_fetch_remote_standalone_binary_asset", fake_fetch_remote_binary_asset)
    monkeypatch.setattr(
        deployer,
        "_subset_font_awesome_font_payload",
        lambda *, payload, **_kwargs: (payload, "font/woff2"),
    )
    monkeypatch.setattr(
        deployer,
        "_subset_text_font_payload",
        lambda *, payload, **_kwargs: (payload, "font/woff2"),
    )

    deployer._configure_funnel_artifact_site(app)

    entry_route_path = "/opt/apps/landing-artifact/site/example-product/example-funnel/index.html"
    entry_html = uploaded[entry_route_path]
    fontshare_400_route = (
        "/_standalone-assets/fonts/"
        f"{hashlib.sha256(b'fontshare-400:Satoshi:400:normal:').hexdigest()[:32]}.woff2"
    )
    fontshare_700_route = (
        "/_standalone-assets/fonts/"
        f"{hashlib.sha256(b'fontshare-700:Satoshi:700:normal:').hexdigest()[:32]}.woff2"
    )
    google_inter_400_route = (
        "/_standalone-assets/fonts/"
        f"{hashlib.sha256(b'google-inter-400:Inter:400:normal:').hexdigest()[:32]}.woff2"
    )
    google_inter_700_route = (
        "/_standalone-assets/fonts/"
        f"{hashlib.sha256(b'google-inter-700:Inter:700:normal:').hexdigest()[:32]}.woff2"
    )
    fontawesome_solid_route = (
        "/_standalone-assets/fonts/"
        f"{hashlib.sha256(fontawesome_solid + b':fa-solid').hexdigest()[:32]}.woff2"
    )
    assert "https://cdn.tailwindcss.com" not in entry_html
    assert "tailwind.config" not in entry_html
    assert 'data-mos-compiled-tailwind="true"' in entry_html
    assert ".bg-brand-primary{background-color:#C41423}" in entry_html
    assert 'src="/public/assets/11111111-1111-1111-1111-111111111111"' in entry_html
    assert "https://api.fontshare.com" not in entry_html
    assert "https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap" not in entry_html
    assert "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" not in entry_html
    assert 'data-mos-local-fontshare="true"' in entry_html
    assert 'data-mos-local-google-fonts="true"' in entry_html
    assert 'data-mos-local-font-awesome="true"' in entry_html
    assert 'const resolveSameDocumentHashTarget = (element) => {' in entry_html
    assert 'binding.type === "checkout" ? resolveSameDocumentHashTarget(element) : null' in entry_html
    assert fontshare_400_route in entry_html
    assert fontshare_700_route in entry_html
    assert google_inter_400_route in entry_html
    assert google_inter_700_route in entry_html
    assert fontawesome_solid_route in entry_html
    assert 'data-mos-style-preload="true"' not in entry_html
    assert (
        f'rel="preload" as="font" href="{fontawesome_solid_route}" type="font/woff2" '
        'crossorigin="anonymous" data-mos-font-preload="true"'
    ) in entry_html
    assert f"/opt/apps/landing-artifact/site{fontshare_400_route}" in uploaded
    assert f"/opt/apps/landing-artifact/site{fontshare_700_route}" in uploaded
    assert f"/opt/apps/landing-artifact/site{google_inter_400_route}" in uploaded
    assert f"/opt/apps/landing-artifact/site{google_inter_700_route}" in uploaded
    assert f"/opt/apps/landing-artifact/site{fontawesome_solid_route}" in uploaded


def test_configure_funnel_artifact_site_subsets_localized_text_fonts_to_used_unicode_ranges(
    monkeypatch,
):
    html_document = """<!DOCTYPE html>
<html>
  <head>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400&display=swap" rel="stylesheet">
  </head>
  <body>
    <main>
      <h1>Hero title</h1>
      <p>Women over 45 feel better.</p>
    </main>
  </body>
</html>
"""
    app = _artifact_app(
        render_mode="standalone_imported_html",
        html_document=html_document,
        server_names=["shop.example.com"],
    )
    deployer, uploaded, _commands = _stub_deployer()

    latin_font_bytes = b"latin-ttf"
    latin_ext_font_bytes = b"latin-ext-ttf"
    google_fonts_css = (
        "@font-face{font-family:'Inter';font-style:normal;font-weight:400;font-display:swap;"
        "src:url('https://fonts.gstatic.com/s/inter/v18/inter-latin-ext.ttf') format('truetype');"
        "unicode-range:U+0100-024F;}"
        "@font-face{font-family:'Inter';font-style:normal;font-weight:400;font-display:swap;"
        "src:url('https://fonts.gstatic.com/s/inter/v18/inter-latin.ttf') format('truetype');"
        "unicode-range:U+0000-00FF;}"
    ).encode("utf-8")
    subset_calls: list[tuple[str, tuple[int, ...]]] = []

    def fake_fetch_remote_binary_asset(*, url: str, user_agent: str | None = None, **_kwargs):
        if url == "https://fonts.googleapis.com/css2?family=Inter:wght@400&display=swap":
            assert user_agent == deployer_module._STANDALONE_MODERN_BROWSER_USER_AGENT
            return google_fonts_css, "text/css"
        if url == "https://fonts.gstatic.com/s/inter/v18/inter-latin.ttf":
            assert user_agent is None
            return latin_font_bytes, "font/ttf"
        if url == "https://fonts.gstatic.com/s/inter/v18/inter-latin-ext.ttf":
            assert user_agent is None
            return latin_ext_font_bytes, "font/ttf"
        raise AssertionError(f"Unexpected mirrored asset request: {url}")

    def fake_subset_text_font_payload(*, payload: bytes, source_url: str, used_codepoints: set[int], **_kwargs):
        subset_calls.append((source_url, tuple(sorted(used_codepoints))))
        if source_url.endswith("inter-latin.ttf"):
            return b"latin-subset-woff2", "font/woff2"
        if source_url.endswith("inter-latin-ext.ttf"):
            return b"latin-ext-subset-woff2", "font/woff2"
        raise AssertionError(f"Unexpected subset source: {source_url}")

    monkeypatch.setattr(deployer, "_fetch_remote_standalone_binary_asset", fake_fetch_remote_binary_asset)
    monkeypatch.setattr(deployer, "_subset_text_font_payload", fake_subset_text_font_payload)

    deployer._configure_funnel_artifact_site(app)

    entry_route_path = "/opt/apps/landing-artifact/site/example-product/example-funnel/index.html"
    entry_html = uploaded[entry_route_path]
    latin_subset_route = (
        "/_standalone-assets/fonts/"
        f"{hashlib.sha256(b'latin-subset-woff2:Inter:400:normal:U+0000-00FF').hexdigest()[:32]}.woff2"
    )
    latin_ext_subset_route = (
        "/_standalone-assets/fonts/"
        f"{hashlib.sha256(b'latin-ext-subset-woff2:Inter:400:normal:U+0100-024F').hexdigest()[:32]}.woff2"
    )

    assert 'data-mos-local-google-fonts="true"' in entry_html
    assert latin_subset_route in entry_html
    assert latin_ext_subset_route not in entry_html
    assert "inter-latin.ttf" not in entry_html
    assert "inter-latin-ext.ttf" not in entry_html
    assert subset_calls == [
        (
            "https://fonts.gstatic.com/s/inter/v18/inter-latin.ttf",
            tuple(sorted({ord(character) for character in " Hero title Women over 45 feel better."})),
        )
    ]
    assert f"/opt/apps/landing-artifact/site{latin_subset_route}" in uploaded
    assert uploaded[f"/opt/apps/landing-artifact/site{latin_subset_route}"] == b"latin-subset-woff2"


def test_replace_standalone_imported_html_tailwind_runtime_places_compiled_css_after_custom_styles(
    monkeypatch,
):
    deployer, _uploaded, _commands = _stub_deployer()
    monkeypatch.setattr(
        deployer,
        "_compile_standalone_imported_html_tailwind_css",
        lambda **_: ".text-\\[32px\\]{font-size:32px}",
    )
    html_document = """<!DOCTYPE html>
<html>
  <head>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
      tailwind.config = {
        theme: {
          extend: {}
        }
      }
    </script>
    <style>
      .strict-h1 { font-size: 13px; }
    </style>
  </head>
  <body>
    <h1 class="strict-h1 text-[32px]">Headline</h1>
  </body>
</html>
"""

    rewritten = deployer._replace_standalone_imported_html_tailwind_runtime(html_document=html_document)

    assert "https://cdn.tailwindcss.com" not in rewritten
    assert "tailwind.config" not in rewritten
    assert rewritten.index(".strict-h1 { font-size: 13px; }") < rewritten.index(
        'data-mos-compiled-tailwind="true"'
    )
    assert rewritten.index('data-mos-compiled-tailwind="true"') < rewritten.lower().rindex("</head>")


def test_compile_standalone_imported_html_tailwind_css_uses_external_frontend_root(
    monkeypatch,
    tmp_path,
):
    deployer, _uploaded, _commands = _stub_deployer()
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    external_frontend_root = tmp_path / "external" / "mos" / "frontend"
    (external_frontend_root / "node_modules" / "tailwindcss" / "lib").mkdir(parents=True)
    (external_frontend_root / "node_modules" / "postcss" / "lib").mkdir(parents=True)
    (external_frontend_root / "node_modules" / "tailwindcss" / "lib" / "index.js").write_text(
        "export default function tailwindcss() { return () => {}; }",
        encoding="utf-8",
    )
    (external_frontend_root / "node_modules" / "postcss" / "lib" / "postcss.js").write_text(
        "export default function postcss() { return { process: async () => ({ css: '' }) }; }",
        encoding="utf-8",
    )

    monkeypatch.setattr(deployer, "_resolve_local_workspace_root", lambda: workspace_root)
    monkeypatch.setenv(
        "MOS_STANDALONE_TAILWIND_FRONTEND_ROOTS",
        str(external_frontend_root),
    )

    observed: dict[str, str] = {}

    def fake_subprocess_run(
        args,
        *,
        cwd,
        capture_output,
        check,
        text,
        timeout,
    ):
        observed["cwd"] = cwd
        observed["postcss"] = args[4]
        observed["tailwind"] = args[5]
        output_path = Path(args[3])
        output_path.write_text(".compiled{display:block}", encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    compiled_css = deployer._compile_standalone_imported_html_tailwind_css(
        html_document='<!DOCTYPE html><html><head><script src="https://cdn.tailwindcss.com"></script></head></html>'
    )

    assert compiled_css == ".compiled{display:block}"
    assert observed["cwd"] == str(external_frontend_root)
    assert observed["postcss"].endswith("/node_modules/postcss/lib/postcss.js")
    assert observed["tailwind"].endswith("/node_modules/tailwindcss/lib/index.js")


def test_parse_fontawesome_icon_codepoints_handles_minified_content_rules():
    stylesheet = (
        '.fa-solid,.fas{font-family:"Font Awesome 6 Free";font-weight:900;}'
        '.fa-circle-xmark:before,.fa-times-circle:before,.fa-xmark-circle:before{content:"\\f057"}'
    )

    codepoints = _parse_fontawesome_icon_codepoints(stylesheet)

    assert codepoints["fa-circle-xmark"] == 0xF057
    assert codepoints["fa-times-circle"] == 0xF057
    assert codepoints["fa-xmark-circle"] == 0xF057


def test_html_tag_has_aspect_ratio_class_detects_tailwind_aspect_tokens():
    assert _html_tag_has_aspect_ratio_class('<img class="w-full aspect-[16/9] object-cover">') is True
    assert _html_tag_has_aspect_ratio_class('<img class="aspect-square rounded-full">') is True
    assert _html_tag_has_aspect_ratio_class('<img class="w-10 h-10 rounded-full">') is False


def test_html_tag_has_explicit_box_size_classes_detects_fixed_box_utilities():
    assert _html_tag_has_explicit_box_size_classes('<img class="w-10 h-10 rounded-full">') is True
    assert _html_tag_has_explicit_box_size_classes('<img class="w-[45px] h-[45px] rounded-full">') is True
    assert _html_tag_has_explicit_box_size_classes('<img class="w-full h-auto">') is False
    assert _html_tag_has_explicit_box_size_classes('<img class="w-[100px] aspect-square">') is False


def test_funnel_artifact_site_mirrors_non_canonical_public_asset_urls_locally(monkeypatch):
    html_document = """<!DOCTYPE html>
<html>
  <head>
    <title>Standalone Pre-Sales</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
      tailwind.config = {
        theme: {
          extend: {
            colors: {
              brand: {
                primary: '#C41423'
              }
            }
          }
        }
      }
    </script>
  </head>
  <body>
    <main class="bg-brand-primary text-white">
      <img src="https://api.moshq.app/public/assets/11111111-1111-1111-1111-111111111111" alt="Hero">
      <a id="main-cta" href="#shop">Start my protocol</a>
    </main>
  </body>
</html>
"""
    app = _artifact_app(
        render_mode="standalone_imported_html",
        html_document=html_document,
        server_names=["shop.shopemberco.com"],
    )
    deployer, uploaded, _commands = _stub_deployer()
    monkeypatch.setattr(
        deployer,
        "_compile_standalone_imported_html_tailwind_css",
        lambda **_: ".bg-brand-primary{background-color:#C41423}.text-white{color:#fff}",
    )
    monkeypatch.setattr(
        deployer,
        "_fetch_remote_standalone_image_asset",
        lambda **_: (_make_jpeg_bytes(width=1600, height=900, color=(201, 20, 35)), "image/jpeg"),
    )

    deployer._configure_funnel_artifact_site(app)

    entry_route_path = "/opt/apps/landing-artifact/site/example-product/example-funnel/index.html"
    entry_html = uploaded[entry_route_path]
    mirrored_payload = _make_jpeg_bytes(width=1600, height=900, color=(201, 20, 35))
    mirrored_digest = hashlib.sha256(mirrored_payload).hexdigest()[:32]
    mirrored_path = f"/opt/apps/landing-artifact/site/_standalone-assets/{mirrored_digest}.jpg"

    assert "https://cdn.tailwindcss.com" not in entry_html
    assert 'data-mos-compiled-tailwind="true"' in entry_html
    assert 'src="/public/assets/11111111-1111-1111-1111-111111111111"' in entry_html
    assert 'src="https://api.moshq.app/public/assets/11111111-1111-1111-1111-111111111111"' not in entry_html
    assert mirrored_path not in uploaded


def test_funnel_artifact_site_mirrors_extensionless_absolute_img_urls(monkeypatch):
    html_document = """<!DOCTYPE html>
<html>
  <body>
    <img src="https://assets.replocdn.com/projects/1d59688c-4fca-4894-8cd3-23dbe64f87b3/c20e5f0a-57f7-4265-be05-b5f356e9b0b7" alt="Hero">
    <a id="main-cta" href="#shop">Start my protocol</a>
  </body>
</html>
"""
    app = _artifact_app(
        render_mode="standalone_imported_html",
        html_document=html_document,
        server_names=["shop.shopemberco.com"],
    )
    deployer, uploaded, _commands = _stub_deployer()
    mirrored_payload = _make_png_bytes(width=1200, height=1200, color=(201, 20, 35, 255))
    monkeypatch.setattr(
        deployer,
        "_fetch_remote_standalone_image_asset",
        lambda **_: (mirrored_payload, "image/png"),
    )

    deployer._configure_funnel_artifact_site(app)

    entry_route_path = "/opt/apps/landing-artifact/site/example-product/example-funnel/index.html"
    entry_html = uploaded[entry_route_path]
    mirrored_digest = hashlib.sha256(mirrored_payload).hexdigest()[:32]
    mirrored_path = f"/opt/apps/landing-artifact/site/_standalone-assets/{mirrored_digest}.png"

    assert (
        'src="/_standalone-assets/'
        f'{mirrored_digest}.png" alt="Hero" loading="eager" decoding="async" fetchpriority="high"'
    ) in entry_html
    assert mirrored_path in uploaded
    assert uploaded[mirrored_path] == mirrored_payload


def test_funnel_artifact_site_prioritizes_large_hero_image_over_decorative_icons(monkeypatch):
    html_document = """<!DOCTYPE html>
<html>
  <head>
    <title>Standalone Pre-Sales</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
      tailwind.config = {
        theme: {
          extend: {
            colors: {
              brand: {
                primary: '#C41423'
              }
            }
          }
        }
      }
    </script>
  </head>
  <body>
    <main class="bg-brand-primary text-white">
      <img src="https://img.funnelish.com/badge.png" alt="Ratings" class="h-4 object-contain">
      <img src="https://api.moshq.app/public/assets/11111111-1111-1111-1111-111111111111" alt="Hero" class="w-full block aspect-[16/10] object-cover">
      <img src="https://api.moshq.app/public/assets/22222222-2222-2222-2222-222222222222" alt="Reviewer Avatar" class="w-10 h-10 rounded-full">
      <a id="main-cta" href="#shop">Start my protocol</a>
    </main>
  </body>
</html>
"""
    app = _artifact_app(
        render_mode="standalone_imported_html",
        html_document=html_document,
        server_names=["shop.shopemberco.com"],
    )
    deployer, uploaded, _commands = _stub_deployer()
    monkeypatch.setattr(
        deployer,
        "_compile_standalone_imported_html_tailwind_css",
        lambda **_: ".bg-brand-primary{background-color:#C41423}.text-white{color:#fff}",
    )
    mirrored_assets = {
        "https://img.funnelish.com/badge.png": (_make_png_bytes(width=100, height=100, color=(255, 255, 255, 255)), "image/png"),
        "https://api.moshq.app/public/assets/11111111-1111-1111-1111-111111111111": (_make_jpeg_bytes(width=1600, height=1000, color=(201, 20, 35)), "image/jpeg"),
        "https://api.moshq.app/public/assets/22222222-2222-2222-2222-222222222222": (_make_png_bytes(width=40, height=40, color=(245, 241, 232, 255)), "image/png"),
    }
    monkeypatch.setattr(
        deployer,
        "_fetch_remote_standalone_image_asset",
        lambda **kwargs: mirrored_assets[kwargs["url"]],
    )

    deployer._configure_funnel_artifact_site(app)

    entry_route_path = "/opt/apps/landing-artifact/site/example-product/example-funnel/index.html"
    entry_html = uploaded[entry_route_path]
    badge_digest = hashlib.sha256(mirrored_assets["https://img.funnelish.com/badge.png"][0]).hexdigest()[:32]

    assert f'src="/_standalone-assets/{badge_digest}.png" alt="Ratings" class="h-4 object-contain" loading="lazy" decoding="async" fetchpriority="low"' in entry_html
    assert 'src="/public/assets/11111111-1111-1111-1111-111111111111" alt="Hero" class="w-full block aspect-[16/10] object-cover" loading="eager" decoding="async" fetchpriority="high"' in entry_html
    assert 'rel="preload" as="image" fetchpriority="high" href="/public/assets/11111111-1111-1111-1111-111111111111"' in entry_html
    assert 'src="/public/assets/22222222-2222-2222-2222-222222222222" alt="Reviewer Avatar" class="w-10 h-10 rounded-full" loading="lazy" decoding="async" fetchpriority="low"' in entry_html


def test_funnel_artifact_site_errors_when_mirroring_required_image_asset_fails(monkeypatch):
    html_document = """<!DOCTYPE html>
<html>
  <body>
    <img src="https://img.funnelish.com/hero.png" alt="Hero">
    <a id="main-cta" href="#shop">Start my protocol</a>
  </body>
</html>
"""
    app = _artifact_app(
        render_mode="standalone_imported_html",
        html_document=html_document,
        server_names=["shop.shopemberco.com"],
    )
    deployer, _uploaded, _commands = _stub_deployer()
    monkeypatch.setattr(
        deployer,
        "_fetch_remote_standalone_image_asset",
        lambda **_: (_ for _ in ()).throw(ValueError("mirror failed")),
    )

    with pytest.raises(ValueError, match="mirror failed"):
        deployer._configure_funnel_artifact_site(app)


def test_standalone_image_source_uses_actual_image_format_for_mismatched_content_type():
    deployer, _uploaded, _commands = _stub_deployer()

    image_source = deployer._build_standalone_image_source(
        route_path="/_standalone-assets/example.png",
        payload=_make_jpeg_bytes(width=1600, height=900, color=(201, 20, 35)),
        content_type="image/png",
        context_label="test",
    )

    assert image_source is not None
    assert image_source.image_format == "JPEG"
    assert image_source.content_type == "image/jpeg"


def test_funnel_artifact_site_rewrites_tiny_reused_image_routes_when_safe(monkeypatch):
    html_document = """<!DOCTYPE html>
<html>
  <body>
    <img src="/public/assets/11111111-1111-1111-1111-111111111111" alt="Avatar" class="w-10 h-10 rounded-full">
    <img src="/public/assets/11111111-1111-1111-1111-111111111111" alt="Avatar duplicate" class="w-10 h-10 rounded-full hidden">
    <a id="main-cta" href="#shop">Start my protocol</a>
  </body>
</html>
"""
    app = _artifact_app(render_mode="standalone_imported_html", html_document=html_document)
    deployer, uploaded, _commands = _stub_deployer()
    monkeypatch.setattr(deployer_module, "_STANDALONE_MAX_TINY_IMAGE_ROUTE_CANDIDATES", 1)
    monkeypatch.setattr(deployer_module, "_STANDALONE_MAX_RESPONSIVE_IMAGE_CANDIDATES", 0)
    monkeypatch.setattr(deployer_module, "_STANDALONE_TINY_IMAGE_RESPONSIVE_MIN_BYTES", 1)
    monkeypatch.setattr(
        deployer,
        "_measure_standalone_imported_html_image_layouts",
        lambda **_: {0: {"desktop": 45, "mobile": 45}, 1: {"desktop": 0, "mobile": 0}},
    )
    monkeypatch.setattr(
        deployer,
        "_validate_standalone_imported_html_visual_parity",
        lambda **_: None,
    )

    deployer._configure_funnel_artifact_site(app)

    entry_route_path = "/opt/apps/landing-artifact/site/example-product/example-funnel/index.html"
    entry_html = uploaded[entry_route_path]

    assert "tiny-w96.png" in entry_html
    assert entry_html.count("tiny-w96.png") == 2
    assert 'src="/public/assets/11111111-1111-1111-1111-111111111111"' not in entry_html


def test_funnel_artifact_site_rewrites_large_images_to_compressed_routes_when_safe(monkeypatch):
    html_document = """<!DOCTYPE html>
<html>
  <body>
    <img src="/public/assets/11111111-1111-1111-1111-111111111111" alt="Hero">
    <a id="main-cta" href="#shop">Start my protocol</a>
  </body>
</html>
"""
    app = _artifact_app(render_mode="standalone_imported_html", html_document=html_document)
    noisy_jpeg = _make_noisy_jpeg_bytes(width=1600, height=900)
    app.source_ref.artifact["assets"]["items"]["11111111-1111-1111-1111-111111111111"] = {
        "contentType": "image/jpeg",
        "sizeBytes": len(noisy_jpeg),
        "bytesBase64": base64.b64encode(noisy_jpeg).decode("ascii"),
    }
    deployer, uploaded, _commands = _stub_deployer()
    monkeypatch.setattr(deployer_module, "_STANDALONE_MAX_COMPRESSED_IMAGE_ROUTE_CANDIDATES", 1)
    monkeypatch.setattr(deployer_module, "_STANDALONE_MAX_TINY_IMAGE_ROUTE_CANDIDATES", 0)
    monkeypatch.setattr(deployer_module, "_STANDALONE_MAX_RESPONSIVE_IMAGE_CANDIDATES", 0)
    monkeypatch.setattr(
        deployer,
        "_validate_standalone_imported_html_visual_parity",
        lambda **_: None,
    )

    deployer._configure_funnel_artifact_site(app)

    entry_route_path = "/opt/apps/landing-artifact/site/example-product/example-funnel/index.html"
    entry_html = uploaded[entry_route_path]
    assert "/_standalone-assets/compressed/" in entry_html
    assert 'src="/public/assets/11111111-1111-1111-1111-111111111111"' not in entry_html


def test_presales_compression_candidates_include_lossy_webp_for_large_images():
    deployer, _uploaded, _commands = _stub_deployer()
    noisy_jpeg = _make_noisy_jpeg_bytes(width=1376, height=768)
    image_source = deployer._build_standalone_image_source(
        route_path="/_standalone-assets/noisy.jpg",
        payload=noisy_jpeg,
        content_type="image/jpeg",
        context_label="test",
    )

    assert image_source is not None
    candidates = deployer._generate_standalone_image_compression_candidates(
        image_source=image_source,
        context_label="test",
        page_stage="pre_sales",
    )

    assert any(label.startswith("webp-q") for _payload, _content_type, label in candidates)


def test_normalize_remote_standalone_fetch_url_downgrades_legacy_public_asset_host():
    assert _normalize_remote_standalone_fetch_url(
        "https://api.moshq.app/public/assets/6c579e05-f25b-4003-9b33-d2c3ac70473b"
    ) == "http://api.moshq.app/public/assets/6c579e05-f25b-4003-9b33-d2c3ac70473b"
    assert _normalize_remote_standalone_fetch_url(
        "https://api.moshq.app/other/path"
    ) == "https://api.moshq.app/other/path"


def test_presales_responsive_rewrites_emit_webp_variants(monkeypatch):
    html_document = """<!DOCTYPE html>
<html>
  <body>
    <img src="/public/assets/11111111-1111-1111-1111-111111111111" alt="Hero">
    <a id="main-cta" href="#shop">Start my protocol</a>
  </body>
</html>
"""
    app = _artifact_app(render_mode="standalone_imported_html", html_document=html_document)
    page_payload = app.source_ref.artifact["products"]["example-product"]["funnels"]["example-funnel"]["pages"]["presales"]
    page_payload["stage"] = "pre_sales"
    page_payload["pageStageMap"] = {"page-1": "pre_sales"}
    imported_block = page_payload["puckData"]["content"][0]
    imported_block["props"]["instrumentationManifest"]["pageStage"] = "pre_sales"

    noisy_jpeg = _make_noisy_jpeg_bytes(width=1600, height=900)
    app.source_ref.artifact["assets"]["items"]["11111111-1111-1111-1111-111111111111"] = {
        "contentType": "image/jpeg",
        "sizeBytes": len(noisy_jpeg),
        "bytesBase64": base64.b64encode(noisy_jpeg).decode("ascii"),
    }

    deployer, uploaded, _commands = _stub_deployer()
    monkeypatch.setattr(deployer_module, "_STANDALONE_MAX_COMPRESSED_IMAGE_ROUTE_CANDIDATES", 0)
    monkeypatch.setattr(deployer_module, "_STANDALONE_MAX_TINY_IMAGE_ROUTE_CANDIDATES", 0)
    monkeypatch.setattr(deployer_module, "_STANDALONE_MAX_RESPONSIVE_IMAGE_CANDIDATES", 1)
    monkeypatch.setattr(
        deployer,
        "_measure_standalone_imported_html_image_layouts",
        lambda **_: {0: {"desktop": 400, "mobile": 200}},
    )
    monkeypatch.setattr(
        deployer,
        "_validate_standalone_imported_html_visual_parity",
        lambda **_: None,
    )

    deployer._configure_funnel_artifact_site(app)

    entry_route_path = "/opt/apps/landing-artifact/site/example-product/example-funnel/index.html"
    entry_html = uploaded[entry_route_path]
    assert ".webp" in entry_html
    assert "srcset=" in entry_html


def test_responsive_image_parity_checks_always_compare_against_original_html(monkeypatch):
    html_document = """<!DOCTYPE html>
<html>
  <body>
    <img src="/public/assets/11111111-1111-1111-1111-111111111111" alt="Hero">
    <a id="main-cta" href="#shop">Start my protocol</a>
  </body>
</html>
"""
    app = _artifact_app(render_mode="standalone_imported_html", html_document=html_document)
    deployer, uploaded, _commands = _stub_deployer()
    monkeypatch.setattr(deployer_module, "_STANDALONE_MAX_TINY_IMAGE_ROUTE_CANDIDATES", 0)
    monkeypatch.setattr(deployer_module, "_STANDALONE_MAX_RESPONSIVE_IMAGE_CANDIDATES", 1)
    monkeypatch.setattr(
        deployer,
        "_measure_standalone_imported_html_image_layouts",
        lambda **_: {0: {"desktop": 400, "mobile": 200}},
    )
    recorded_before_html: list[str] = []

    def record_validate(*, before_html: str, **_kwargs):
        recorded_before_html.append(before_html)

    monkeypatch.setattr(
        deployer,
        "_validate_standalone_imported_html_visual_parity",
        record_validate,
    )

    deployer._configure_funnel_artifact_site(app)

    assert recorded_before_html
    assert all(before_html == html_document for before_html in recorded_before_html)
    entry_route_path = "/opt/apps/landing-artifact/site/example-product/example-funnel/index.html"
    assert "srcset=" in uploaded[entry_route_path]


def test_funnel_artifact_site_keeps_exact_image_sources_when_responsive_rewrites_are_disabled(monkeypatch):
    html_document = """<!DOCTYPE html>
<html>
  <head>
    <title>Responsive</title>
  </head>
  <body>
    <main>
      <img src="/public/assets/11111111-1111-1111-1111-111111111111" alt="Hero">
      <a id="main-cta" href="#shop">Start my protocol</a>
    </main>
  </body>
</html>
"""
    app = _artifact_app(render_mode="standalone_imported_html", html_document=html_document)
    deployer, uploaded, _commands = _stub_deployer()
    monkeypatch.setattr(deployer_module, "_STANDALONE_MAX_TINY_IMAGE_ROUTE_CANDIDATES", 0)
    monkeypatch.setattr(deployer_module, "_STANDALONE_MAX_RESPONSIVE_IMAGE_CANDIDATES", 0)
    deployer._measure_standalone_imported_html_image_layouts = lambda **_: {
        0: {"desktop": 720, "mobile": 390}
    }

    deployer._configure_funnel_artifact_site(app)

    entry_route_path = "/opt/apps/landing-artifact/site/example-product/example-funnel/index.html"
    entry_html = uploaded[entry_route_path]
    assert 'src="/public/assets/11111111-1111-1111-1111-111111111111"' in entry_html
    assert "srcset=" not in entry_html
    assert "sizes=" not in entry_html


def test_funnel_artifact_site_minifies_final_html_and_loads_meta_pixel_soon_after_page_load(monkeypatch):
    html_document = """<!DOCTYPE html>
<html>
  <head>
    <!-- remove me -->
    <title>Standalone Sales</title>
  </head>
  <body>
    <main>
      <img src="/public/assets/11111111-1111-1111-1111-111111111111" alt="Hero">
      <a id="main-cta" href="#shop">Start my protocol</a>
    </main>
  </body>
</html>
"""
    app = _artifact_app(render_mode="standalone_imported_html", html_document=html_document)
    deployer, uploaded, _commands = _stub_deployer()
    monkeypatch.setattr(deployer_module, "_STANDALONE_MAX_COMPRESSED_IMAGE_ROUTE_CANDIDATES", 0)
    monkeypatch.setattr(deployer_module, "_STANDALONE_MAX_TINY_IMAGE_ROUTE_CANDIDATES", 0)
    monkeypatch.setattr(deployer_module, "_STANDALONE_MAX_RESPONSIVE_IMAGE_CANDIDATES", 0)

    deployer._configure_funnel_artifact_site(app)

    entry_route_path = "/opt/apps/landing-artifact/site/example-product/example-funnel/index.html"
    entry_html = uploaded[entry_route_path]
    assert "<!-- remove me -->" not in entry_html
    assert ">      <" not in entry_html
    assert "const META_PIXEL_DEFER_TIMEOUT_MS = 2500;" in entry_html
    assert 'window.addEventListener("load", flush, { once: true });' in entry_html
    assert "window.requestIdleCallback(flush, {" in entry_html
    assert "const resetBusyBoundElements = () => {" in entry_html
    assert 'window.addEventListener("pageshow", () => {' in entry_html


def test_build_standalone_render_optimization_css_targets_sales_and_presales():
    sales_css = _build_standalone_render_optimization_css(page_stage="sales")
    presales_css = _build_standalone_render_optimization_css(page_stage="pre_sales")

    assert "body>section:nth-of-type(n+3)" in sales_css
    assert "body>footer" in sales_css
    assert "content-visibility:auto" in sales_css

    assert "body>div:nth-of-type(n+3):not(.fixed)" in presales_css
    assert ".article-body>*:nth-child(n+13)" in presales_css
    assert ".article-body>figure:nth-child(n+13)" in presales_css
    assert "content-visibility:auto" in presales_css


def test_funnel_artifact_site_injects_render_optimization_styles(monkeypatch):
    html_document = """<!DOCTYPE html>
<html>
  <head>
    <title>Standalone Sales</title>
  </head>
  <body>
    <section>Hero</section>
    <section>Proof</section>
    <section>FAQ</section>
    <footer>Footer</footer>
  </body>
</html>
"""
    app = _artifact_app(render_mode="standalone_imported_html", html_document=html_document)
    deployer, uploaded, _commands = _stub_deployer()
    monkeypatch.setattr(deployer_module, "_STANDALONE_MAX_COMPRESSED_IMAGE_ROUTE_CANDIDATES", 0)
    monkeypatch.setattr(deployer_module, "_STANDALONE_MAX_TINY_IMAGE_ROUTE_CANDIDATES", 0)
    monkeypatch.setattr(deployer_module, "_STANDALONE_MAX_RESPONSIVE_IMAGE_CANDIDATES", 0)

    deployer._configure_funnel_artifact_site(app)

    entry_html = uploaded["/opt/apps/landing-artifact/site/example-product/example-funnel/index.html"]
    assert 'data-mos-render-optimization="true"' in entry_html
    assert "body>section:nth-of-type(n+3)" in entry_html


def test_funnel_artifact_site_uses_canonical_domain_for_default_route_when_workspace_server_names_present():
    html_document = """<!DOCTYPE html>
<html>
  <head>
    <title>Standalone Sales</title>
  </head>
  <body>
    <main id="app">
      <a id="main-cta" href="#shop">Start my protocol</a>
    </main>
  </body>
</html>
"""
    app = _artifact_app(
        render_mode="standalone_imported_html",
        html_document=html_document,
        workspace_server_names=["shop.example.com"],
    )
    deployer, uploaded, _commands = _stub_deployer()

    deployer._configure_funnel_artifact_site(app)

    conf = uploaded["/etc/nginx/sites-available/landing-artifact"]
    assert "location = / {" in conf
    assert (
        "return 302 https://shop.example.com/example-product/example-funnel/presales$is_args$args;"
        in conf
    )


def test_funnel_artifact_site_standalone_export_errors_on_unsupported_page_blocks():
    app = _artifact_app(render_mode="standalone_imported_html")
    deployer, _uploaded, _commands = _stub_deployer()

    with pytest.raises(ValueError, match="unsupported standalone page block type 'PreSalesPage'"):
        deployer._configure_funnel_artifact_site(app)


def test_funnel_artifact_site_standalone_export_errors_when_manifest_is_missing():
    html_document = """<!DOCTYPE html>
<html>
  <body>
    <a id="main-cta" href="#shop">Start my protocol</a>
  </body>
</html>
"""
    app = _artifact_app(render_mode="standalone_imported_html", html_document=html_document)
    props = app.source_ref.artifact["products"]["example-product"]["funnels"]["example-funnel"]["pages"]["presales"]["puckData"]["content"][0]["props"]
    props.pop("instrumentationManifest", None)
    deployer, _uploaded, _commands = _stub_deployer()

    with pytest.raises(ValueError, match="instrumentationManifest is required"):
        deployer._configure_funnel_artifact_site(app)


def test_funnel_artifact_site_standalone_export_renders_compliance_pages():
    html_document = """<!DOCTYPE html>
<html>
  <head>
    <title>Sales Page</title>
    <style>.brand-header{color:red;}</style>
  </head>
  <body class="brand-body">
    <header class="brand-header">
      <a id="header-shop-link" href="#shop" rel="nofollow">SHOP</a>
      <span>BRAND</span>
    </header>
    <main>
      <a id="main-cta" href="#shop">Start my protocol</a>
    </main>
    <footer class="brand-footer">
      <a href="#" rel="nofollow">Contact</a>
      <a id="footer-shop-link" href="#shop" rel="nofollow">Shop</a>
      <a href="#" rel="nofollow">Terms</a>
      <a href="#" rel="nofollow">Privacy</a>
      <a href="#" rel="nofollow">Refunds</a>
    </footer>
  </body>
</html>
"""
    app = _artifact_app(
        render_mode="standalone_imported_html",
        html_document=html_document,
        workspace_server_names=["shoptenorco.com"],
    )
    funnel_payload = app.source_ref.artifact["products"]["example-product"]["funnels"]["example-funnel"]
    imported_page = funnel_payload["pages"]["presales"]
    imported_page["pageMap"] = {
        "page-1": "presales",
        "page-2": "terms-of-service",
        "page-3": "privacy-policy",
        "page-4": "refund-policy",
        "page-5": "contact-us",
    }
    imported_page["pageStageMap"] = {
        "page-1": "pre_sales",
        "page-2": "custom",
        "page-3": "custom",
        "page-4": "custom",
        "page-5": "custom",
    }
    imported_page["designSystemTokens"] = {
        "brand": {
            "name": "Ember",
        }
    }
    funnel_payload["meta"]["pages"] = [
        {"pageId": "page-1", "slug": "presales"},
        {"pageId": "page-2", "slug": "terms-of-service"},
        {"pageId": "page-3", "slug": "privacy-policy"},
        {"pageId": "page-4", "slug": "refund-policy"},
        {"pageId": "page-5", "slug": "contact-us"},
    ]
    funnel_payload["pages"]["terms-of-service"] = {
        "productSlug": "example-product",
        "funnelId": "funnel-1",
        "publicationId": "pub-1",
        "pageId": "page-2",
        "slug": "terms-of-service",
        "stage": "custom",
        "puckData": {
            "root": {
                "props": {
                    "title": "Terms of Service",
                    "description": "Terms of service",
                }
            },
            "content": [
                {
                    "type": "FunnelCompliancePage",
                    "props": {
                        "pageKey": "terms_of_service",
                        "pageTitle": "Terms of Service",
                        "supportEmail": "support@shoptenorco.com",
                    },
                }
            ],
            "zones": {},
        },
        "pageMap": {
            "page-1": "presales",
            "page-2": "terms-of-service",
            "page-3": "privacy-policy",
            "page-4": "refund-policy",
            "page-5": "contact-us",
        },
        "pageStageMap": {
            "page-1": "pre_sales",
            "page-2": "custom",
            "page-3": "custom",
            "page-4": "custom",
            "page-5": "custom",
        },
        "designSystemTokens": {
            "brand": {
                "name": "Ember",
            }
        },
    }

    deployer, uploaded, _commands = _stub_deployer()

    deployer._configure_funnel_artifact_site(app)

    compliance_route_path = "/opt/apps/landing-artifact/site/example-product/example-funnel/terms-of-service/index.html"
    compliance_html = uploaded[compliance_route_path]
    assert "MOS_STANDALONE_IMPORTED_HTML_BRIDGE_START" not in compliance_html
    assert 'id="mos-standalone-policy-content"' in compliance_html
    assert 'Loading policy content...' in compliance_html
    assert "/api/public/funnels/example-product/example-funnel/policy-pages/terms_of_service" in compliance_html
    assert 'params.set("support_email", supportEmailOverride);' in compliance_html
    assert "payload.html" in compliance_html
    assert '<body class="brand-body">' in compliance_html
    assert 'id="header-shop-link" href="/example-product/example-funnel/presales/#shop"' in compliance_html
    assert 'href="/example-product/example-funnel/contact-us/" rel="nofollow">Contact</a>' in compliance_html
    assert 'id="footer-shop-link" href="/example-product/example-funnel/presales/#shop"' in compliance_html
    assert 'href="/example-product/example-funnel/terms-of-service/" rel="nofollow">Terms</a>' in compliance_html
    assert 'href="/example-product/example-funnel/privacy-policy/" rel="nofollow">Privacy</a>' in compliance_html
    assert 'href="/example-product/example-funnel/refund-policy/" rel="nofollow">Refunds</a>' in compliance_html


def test_funnel_artifact_site_standalone_export_uses_pathless_api_origin_for_proxy():
    html_document = """<!DOCTYPE html>
<html>
  <head><title>Standalone Sales</title></head>
  <body>
    <main id="app"><a id="main-cta" href="#shop">Start</a></main>
  </body>
</html>
"""
    app = _artifact_app(render_mode="standalone_imported_html", html_document=html_document)
    deployer, uploaded, _commands = _stub_deployer()

    deployer._configure_funnel_artifact_site(app)

    conf = uploaded["/etc/nginx/sites-available/landing-artifact"]
    assert "location ^~ /api/ {" in conf
    assert "proxy_pass https://api.moshq.app/;" in conf
    assert "proxy_set_header Host api.moshq.app;" in conf


def test_funnel_artifact_site_standalone_export_requires_origin_api_base_url():
    html_document = """<!DOCTYPE html>
<html>
  <head><title>Standalone Sales</title></head>
  <body>
    <main id="app"><a id="main-cta" href="#shop">Start</a></main>
  </body>
</html>
"""
    app = _artifact_app(render_mode="standalone_imported_html", html_document=html_document)
    app.source_ref.upstream_api_base_root = "https://moshq.app/api"
    deployer, _uploaded, _commands = _stub_deployer()

    with pytest.raises(ValueError, match="origin URL without a path"):
        deployer._configure_funnel_artifact_site(app)


def test_validate_funnel_artifact_site_output_requires_posthog_bootstrap_when_tracking_is_declared():
    app = _artifact_app(render_mode="standalone_imported_html", html_document="<!DOCTYPE html><html><body>Hi</body></html>")
    deployer = object.__new__(ServerDeployer)
    deployer._path_exists = lambda path: True
    deployer._funnel_artifact_declares_posthog_tracking = lambda *, source: True
    deployer._resolve_funnel_artifact_default_route = lambda *, source: ("example-product", "example-funnel", "presales")
    deployer._remote_tree_contains_text = lambda *, root_path, text: text == "MOS_STANDALONE_IMPORTED_HTML_BRIDGE_START"

    with pytest.raises(ValueError, match="PostHog bootstrap"):
        deployer._validate_funnel_artifact_site_output(
            site_dir="/opt/apps/landing-artifact/site-releases/20260422T000000Z",
            source=app.source_ref,
            render_mode=FunnelArtifactRenderMode.STANDALONE_IMPORTED_HTML,
        )


def test_funnel_artifact_site_errors_when_funnel_id_alias_collides_with_existing_slug():
    app = _artifact_app()
    product_payload = app.source_ref.artifact["products"]["example-product"]
    product_payload["funnels"]["funnel-1"] = {
        "meta": {
            "funnelSlug": "funnel-1",
            "funnelId": "funnel-2",
            "publicationId": "pub-2",
            "entrySlug": "presales",
            "pages": [{"pageId": "page-2", "slug": "presales"}],
        },
        "pages": {
            "presales": {
                "funnelId": "funnel-2",
                "publicationId": "pub-2",
                "pageId": "page-2",
                "slug": "presales",
                "puckData": {"root": {"props": {}}, "content": [], "zones": {}},
                "pageMap": {"page-2": "presales"},
            }
        },
    }

    deployer, _uploaded, _commands = _stub_deployer()

    with pytest.raises(ValueError, match="duplicates funnel path token"):
        deployer._configure_funnel_artifact_site(app)


def test_funnel_artifact_site_errors_when_embedded_asset_base64_is_invalid():
    app = _artifact_app()
    app.source_ref.artifact["assets"]["items"]["11111111-1111-1111-1111-111111111111"]["bytesBase64"] = "!!!"
    deployer, _uploaded, _commands = _stub_deployer()

    with pytest.raises(ValueError, match="invalid bytesBase64"):
        deployer._configure_funnel_artifact_site(app)


def test_funnel_artifact_site_writes_short_funnel_id_alias_for_uuid_funnel_id():
    app = _artifact_app()
    uuid_funnel_id = "f85405a4-c7cd-4fdf-a953-6613d712392d"
    funnel_payload = app.source_ref.artifact["products"]["example-product"]["funnels"]["example-funnel"]
    funnel_payload["meta"]["funnelId"] = uuid_funnel_id
    funnel_payload["pages"]["presales"]["funnelId"] = uuid_funnel_id

    deployer, uploaded, _commands = _stub_deployer()

    deployer._configure_funnel_artifact_site(app)

    short_meta_path = "/opt/apps/landing-artifact/site/api/public/funnels/example-product/f85405a4/meta.json"
    short_page_path = "/opt/apps/landing-artifact/site/api/public/funnels/example-product/f85405a4/pages/presales.json"
    assert short_meta_path in uploaded
    assert short_page_path in uploaded


def test_funnel_artifact_site_canonicalizes_presales_slug_without_legacy_alias():
    app = _artifact_app()
    funnel_payload = app.source_ref.artifact["products"]["example-product"]["funnels"]["example-funnel"]
    legacy_page = funnel_payload["pages"].pop("presales")
    legacy_page["slug"] = "pre-sales"
    legacy_page["pageMap"] = {"page-1": "pre-sales"}
    funnel_payload["meta"]["entrySlug"] = "pre-sales"
    funnel_payload["meta"]["pages"] = [{"pageId": "page-1", "slug": "pre-sales"}]
    funnel_payload["pages"]["pre-sales"] = legacy_page

    deployer, uploaded, _commands = _stub_deployer()

    deployer._configure_funnel_artifact_site(app)

    meta_path = "/opt/apps/landing-artifact/site/api/public/funnels/example-product/example-funnel/meta.json"
    canonical_page_path = "/opt/apps/landing-artifact/site/api/public/funnels/example-product/example-funnel/pages/presales.json"
    legacy_page_path = "/opt/apps/landing-artifact/site/api/public/funnels/example-product/example-funnel/pages/pre-sales.json"

    meta_payload = json.loads(uploaded[meta_path])
    canonical_page_payload = json.loads(uploaded[canonical_page_path])

    assert meta_payload["entrySlug"] == "presales"
    assert meta_payload["pages"] == [{"pageId": "page-1", "slug": "presales"}]
    assert canonical_page_payload["slug"] == "presales"
    assert canonical_page_payload["pageMap"] == {"page-1": "presales"}
    assert legacy_page_path not in uploaded


def test_funnel_artifact_site_injects_default_route_into_runtime_config():
    app = _artifact_app()
    uuid_funnel_id = "f85405a4-c7cd-4fdf-a953-6613d712392d"
    funnel_payload = app.source_ref.artifact["products"]["example-product"]["funnels"]["example-funnel"]
    funnel_payload["meta"]["funnelId"] = uuid_funnel_id
    funnel_payload["pages"]["presales"]["funnelId"] = uuid_funnel_id

    deployer, _uploaded, commands = _stub_deployer()

    deployer._configure_funnel_artifact_site(app)

    runtime_script_path = next((path for path in _uploaded if path.startswith("/tmp/cloudhand-runtime-config-")), "")
    assert runtime_script_path
    runtime_inject_script = _uploaded[runtime_script_path]
    assert isinstance(runtime_inject_script, str)
    runtime_block = _extract_runtime_block(runtime_inject_script)
    assert any(cmd.startswith("python3 /tmp/cloudhand-runtime-config-") for cmd in commands)
    assert any(cmd.startswith("rm -f /tmp/cloudhand-runtime-config-") for cmd in commands)
    assert '"defaultProductSlug":"example-product"' in runtime_block
    assert '"defaultFunnelSlug":"f85405a4"' in runtime_block
    assert '"defaultEntrySlug":"presales"' in runtime_block
    assert "raw = raw.replace" in runtime_inject_script
    assert '<script type="module"' in runtime_inject_script
    assert '"entryImagePreloadMap"' in runtime_block
    assert (
        '"example-product/example-funnel/presales":"11111111-1111-1111-1111-111111111111"'
        in runtime_block
    )
    assert (
        '"example-product/f85405a4/presales":"11111111-1111-1111-1111-111111111111"'
        in runtime_block
    )
    assert '"preloadedFunnel":{"productSlug":"example-product","funnelSlug":"f85405a4"' in runtime_block


def test_funnel_artifact_site_prefers_updated_from_funnel_for_runtime_config():
    app = _artifact_app()
    first_funnel_id = "f85405a4-c7cd-4fdf-a953-6613d712392d"
    preferred_funnel_id = "18ac0fe1-1e27-4579-ad94-9a1e6c9530fe"
    product_payload = app.source_ref.artifact["products"]["example-product"]
    funnels_payload = product_payload["funnels"]

    first_funnel_payload = funnels_payload["example-funnel"]
    first_funnel_payload["meta"]["funnelId"] = first_funnel_id
    first_funnel_payload["pages"]["presales"]["funnelId"] = first_funnel_id

    preferred_funnel_payload = json.loads(json.dumps(first_funnel_payload))
    preferred_funnel_payload["meta"]["funnelSlug"] = "imported-funnel"
    preferred_funnel_payload["meta"]["funnelId"] = preferred_funnel_id
    preferred_funnel_payload["meta"]["publicationId"] = "pub-2"
    preferred_funnel_payload["pages"]["presales"]["funnelId"] = preferred_funnel_id
    preferred_funnel_payload["pages"]["presales"]["publicationId"] = "pub-2"
    preferred_funnel_payload["pages"]["presales"]["pageId"] = "page-2"
    preferred_funnel_payload["pages"]["presales"]["pageMap"] = {"page-2": "presales"}
    preferred_funnel_payload["meta"]["pages"] = [{"pageId": "page-2", "slug": "presales"}]
    funnels_payload["imported-funnel"] = preferred_funnel_payload

    app.source_ref.artifact["meta"]["updatedFromFunnelId"] = preferred_funnel_id
    app.source_ref.artifact["meta"]["updatedFromPublicationId"] = "pub-2"

    deployer, uploaded, _commands = _stub_deployer()

    deployer._configure_funnel_artifact_site(app)

    runtime_script_path = next((path for path in uploaded if path.startswith("/tmp/cloudhand-runtime-config-")), "")
    assert runtime_script_path
    runtime_inject_script = uploaded[runtime_script_path]
    assert isinstance(runtime_inject_script, str)
    runtime_block = _extract_runtime_block(runtime_inject_script)
    assert '"defaultProductSlug":"example-product"' in runtime_block
    assert '"defaultFunnelSlug":"18ac0fe1"' in runtime_block
    assert '"defaultEntrySlug":"presales"' in runtime_block
    assert '"preloadedFunnel":{"productSlug":"example-product","funnelSlug":"18ac0fe1"' in runtime_block
    assert '"commerce":' not in runtime_block


def test_funnel_artifact_site_only_inlines_the_entry_page_in_runtime_config():
    app = _artifact_app()
    funnel_payload = app.source_ref.artifact["products"]["example-product"]["funnels"]["example-funnel"]
    funnel_payload["pages"]["sales-page"] = {
        "funnelId": "funnel-1",
        "publicationId": "pub-1",
        "pageId": "page-2",
        "slug": "sales-page",
        "puckData": {
            "root": {"props": {"title": "Sales"}},
            "content": [],
            "zones": {},
        },
        "pageMap": {"page-1": "presales", "page-2": "sales-page"},
    }
    funnel_payload["meta"]["pages"] = [
        {"pageId": "page-1", "slug": "presales"},
        {"pageId": "page-2", "slug": "sales-page"},
    ]

    deployer, uploaded, _commands = _stub_deployer()

    deployer._configure_funnel_artifact_site(app)

    runtime_script_path = next((path for path in uploaded if path.startswith("/tmp/cloudhand-runtime-config-")), "")
    assert runtime_script_path
    runtime_inject_script = uploaded[runtime_script_path]
    assert isinstance(runtime_inject_script, str)
    runtime_block = _extract_runtime_block(runtime_inject_script)

    assert '"pages":{"presales":' in runtime_block
    assert '"pageId":"page-2","slug":"sales-page","puckData"' not in runtime_block


def test_funnel_artifact_site_escapes_html_script_terminators_in_runtime_config():
    app = _artifact_app()
    funnel_payload = app.source_ref.artifact["products"]["example-product"]["funnels"]["example-funnel"]
    funnel_payload["pages"]["presales"] = {
        "funnelId": "funnel-1",
        "publicationId": "pub-1",
        "pageId": "page-1",
        "slug": "presales",
        "puckData": {
            "root": {"props": {"title": "Pre-Sales"}},
            "content": [
                {
                    "type": "ImportedHtmlDocument",
                    "props": {
                        "id": "imported-html-document",
                        "title": "Pre-Sales",
                        "sourceLabel": "pre-sales.html",
                        "htmlDocument": '<!DOCTYPE html><html><head><script src="https://cdn.tailwindcss.com"></script></head><body><h1>Advertorial</h1></body></html>',
                    },
                }
            ],
            "zones": {},
        },
        "pageMap": {"page-1": "presales"},
    }

    deployer, uploaded, _commands = _stub_deployer()

    deployer._configure_funnel_artifact_site(app)

    runtime_script_path = next((path for path in uploaded if path.startswith("/tmp/cloudhand-runtime-config-")), "")
    assert runtime_script_path
    runtime_inject_script = uploaded[runtime_script_path]
    assert isinstance(runtime_inject_script, str)
    runtime_block = _extract_runtime_block(runtime_inject_script)
    assert "\\u003c/script\\u003e" in runtime_block
    assert "</script></head><body><h1>Advertorial</h1>" not in runtime_block


def test_funnel_artifact_site_errors_when_preload_asset_public_id_is_invalid_uuid():
    app = _artifact_app()
    hero_config = (
        app.source_ref.artifact["products"]["example-product"]["funnels"]["example-funnel"]["pages"]["presales"]["puckData"][
            "content"
        ][0]["props"]["content"][0]["props"]["config"]
    )
    hero_config["hero"]["media"]["assetPublicId"] = "not-a-uuid"
    deployer, _uploaded, _commands = _stub_deployer()

    with pytest.raises(ValueError, match="hero.media.assetPublicId"):
        deployer._configure_funnel_artifact_site(app)


def test_funnel_artifact_site_errors_with_clear_message_when_runtime_dist_missing():
    app = _artifact_app()
    deployer, _uploaded, _commands = _stub_deployer()

    deployer._path_exists = lambda path: False
    deployer._ensure_local_runtime_dist = lambda runtime_dist_path: None

    with pytest.raises(ValueError, match="runtime_dist_path was not found on target server or local control-plane host"):
        deployer._configure_funnel_artifact_site(app)


def test_funnel_artifact_site_uploads_local_runtime_when_remote_missing(tmp_path):
    app = _artifact_app()
    app.source_ref.runtime_dist_path = "mos/frontend/dist"
    local_dist = tmp_path / "mos" / "frontend" / "dist"
    local_dist.mkdir(parents=True, exist_ok=True)
    (local_dist / "index.html").write_text("<html></html>", encoding="utf-8")

    deployer, _uploaded, commands = _stub_deployer()
    deployer.local_root = tmp_path
    deployer._path_exists = lambda path: False
    deployed: dict[str, str] = {}

    def fake_upload_local_directory(*, local_dir: Path, remote_dir: str):
        deployed["local_dir"] = str(local_dir)
        deployed["remote_dir"] = remote_dir

    deployer._upload_local_directory = fake_upload_local_directory
    deployer._replace_api_base_tokens = lambda **_: None

    deployer._configure_funnel_artifact_site(app)

    assert Path(deployed["local_dir"]).resolve() == local_dist.resolve()
    assert deployed["remote_dir"].startswith("/opt/apps/.cloudhand-runtime-cache/")
    assert any(
        cmd.startswith("cp -R /opt/apps/.cloudhand-runtime-cache/") and cmd.endswith("/. /opt/apps/landing-artifact/site/")
        for cmd in commands
    )
    assert "nginx -t" in commands
    assert "systemctl reload nginx" in commands


def test_funnel_artifact_site_reuses_cached_runtime_without_upload(tmp_path):
    app = _artifact_app()
    deployer, _uploaded, commands = _stub_deployer()
    deployer._path_exists = lambda path: path == "/opt/apps/.cloudhand-runtime-cache/runtimehash123"
    deployer._ensure_local_runtime_dist = lambda runtime_dist_path: tmp_path
    deployer._hash_local_directory = lambda local_dir: "runtimehash123"
    upload_calls: list[tuple[str, str]] = []

    def fake_upload_local_directory(*, local_dir: Path, remote_dir: str):
        upload_calls.append((str(local_dir), remote_dir))

    deployer._upload_local_directory = fake_upload_local_directory
    deployer._replace_api_base_tokens = lambda **_: None

    deployer._configure_funnel_artifact_site(app)

    assert upload_calls == []
    assert any(
        cmd.startswith("cp -R /opt/apps/.cloudhand-runtime-cache/runtimehash123/. /opt/apps/landing-artifact/site/")
        for cmd in commands
    )


def test_ensure_local_runtime_dist_rebuilds_when_frontend_source_is_newer(tmp_path):
    frontend_dir = tmp_path / "mos" / "frontend"
    dist_dir = frontend_dir / "dist"
    src_dir = frontend_dir / "src"
    frontend_dir.mkdir(parents=True, exist_ok=True)
    dist_dir.mkdir(parents=True, exist_ok=True)
    src_dir.mkdir(parents=True, exist_ok=True)

    package_json = frontend_dir / "package.json"
    package_json.write_text('{"name":"mos-frontend"}', encoding="utf-8")
    dist_file = dist_dir / "index.html"
    dist_file.write_text("<html></html>", encoding="utf-8")
    source_file = src_dir / "PublicFunnelPage.tsx"
    source_file.write_text("export const ready = true;\n", encoding="utf-8")

    os.utime(package_json, (100, 100))
    os.utime(dist_file, (100, 100))
    os.utime(source_file, (200, 200))

    deployer = object.__new__(ServerDeployer)
    deployer.ip = "127.0.0.1"
    deployer.local_root = tmp_path
    commands: list[tuple[str, Path]] = []
    deployer._run_local_command = lambda args, *, cwd: commands.append((" ".join(args), cwd))

    resolved = deployer._ensure_local_runtime_dist("mos/frontend/dist")

    assert resolved == dist_dir.resolve()
    assert commands == [
        ("npm ci", frontend_dir.resolve()),
        ("npm run build", frontend_dir.resolve()),
    ]
