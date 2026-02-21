from __future__ import annotations

import base64
from pathlib import Path
import pytest

from cloudhand.adapters.deployer import ServerDeployer
from cloudhand.models import ApplicationSpec


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


def _git_app(name: str = "legacy-app") -> ApplicationSpec:
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
            "command": "npm run start",
            "environment": {},
            "ports": [3000],
            "server_names": ["example.com"],
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
) -> ApplicationSpec:
    payload = {
        "name": name,
        "source_type": "funnel_artifact",
        "source_ref": {
            "client_id": "f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
            "upstream_api_base_root": "https://moshq.app/api",
            "runtime_dist_path": "mos/frontend/dist",
            "artifact": {
                "meta": {
                    "clientId": "f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
                },
                "assets": {
                    "totalBytes": 11,
                    "items": {
                        "11111111-1111-1111-1111-111111111111": {
                            "contentType": "image/png",
                            "sizeBytes": 11,
                            "bytesBase64": base64.b64encode(b"hello-asset").decode("ascii"),
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
                                    "presales": {
                                        "funnelId": "funnel-1",
                                        "publicationId": "pub-1",
                                        "pageId": "page-1",
                                        "slug": "presales",
                                        "puckData": {"root": {"props": {}}, "content": [], "zones": {}},
                                        "pageMap": {"page-1": "presales"},
                                    }
                                },
                            }
                        }
                    }
                },
            },
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
            "ports": ports or [24123],
            "server_names": server_names or [],
            "https": False,
        },
        "destination_path": "/opt/apps",
    }
    return ApplicationSpec.model_validate(payload)


def _stub_deployer():
    deployer = object.__new__(ServerDeployer)
    deployer.ip = "127.0.0.1"
    deployer.local_root = Path.cwd()
    uploaded: dict[str, str | bytes] = {}
    commands: list[str] = []

    def fake_upload(content: str, remote_path: str):
        uploaded[remote_path] = content

    def fake_upload_bytes(content: bytes, remote_path: str):
        uploaded[remote_path] = content

    def fake_run(cmd: str, cwd: str = None, mask=None) -> str:
        commands.append(cmd)
        return ""

    deployer.upload_file = fake_upload
    deployer.upload_bytes = fake_upload_bytes
    deployer.run = fake_run
    deployer._path_exists = lambda path: True
    deployer._enable_https = lambda server_names: None
    return deployer, uploaded, commands


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


def test_funnel_artifact_site_writes_local_api_payload_and_nginx_routes():
    app = _artifact_app()
    deployer, uploaded, commands = _stub_deployer()

    deployer._configure_funnel_artifact_site(app)

    conf = uploaded["/etc/nginx/sites-available/landing-artifact"]
    assert "listen 24123;" in conf
    assert "server_name _;" in conf
    assert "return 302 /f/" not in conf
    assert "location = /api/public/checkout" in conf
    assert "location ^~ /api/public/events" in conf
    assert "location ^~ /api/public/assets/ {" in conf
    assert "location ^~ /api/public/funnels/ {" in conf
    assert "try_files $uri.json =404;" in conf
    assert "try_files $uri /index.html;" in conf

    meta_path = "/opt/apps/landing-artifact/site/api/public/funnels/example-product/example-funnel/meta.json"
    page_path = "/opt/apps/landing-artifact/site/api/public/funnels/example-product/example-funnel/pages/presales.json"
    id_meta_path = "/opt/apps/landing-artifact/site/api/public/funnels/example-product/funnel-1/meta.json"
    id_page_path = "/opt/apps/landing-artifact/site/api/public/funnels/example-product/funnel-1/pages/presales.json"
    asset_path = "/opt/apps/landing-artifact/site/api/public/assets/11111111-1111-1111-1111-111111111111.png"
    assert meta_path in uploaded
    assert page_path in uploaded
    assert id_meta_path in uploaded
    assert id_page_path in uploaded
    assert asset_path in uploaded
    assert uploaded[asset_path] == b"hello-asset"

    assert "nginx -t" in commands
    assert "systemctl reload nginx" in commands


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


def test_funnel_artifact_site_injects_default_route_into_runtime_config():
    app = _artifact_app()
    uuid_funnel_id = "f85405a4-c7cd-4fdf-a953-6613d712392d"
    funnel_payload = app.source_ref.artifact["products"]["example-product"]["funnels"]["example-funnel"]
    funnel_payload["meta"]["funnelId"] = uuid_funnel_id
    funnel_payload["pages"]["presales"]["funnelId"] = uuid_funnel_id

    deployer, _uploaded, commands = _stub_deployer()

    deployer._configure_funnel_artifact_site(app)

    runtime_inject_cmd = next(
        (
            cmd
            for cmd in commands
            if cmd.startswith("python3 -c") and "__MOS_DEPLOY_RUNTIME__" in cmd
        ),
        "",
    )
    assert runtime_inject_cmd
    assert '"defaultProductSlug":"example-product"' in runtime_inject_cmd
    assert '"defaultFunnelSlug":"f85405a4"' in runtime_inject_cmd


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

    assert deployed["local_dir"] == str(local_dist)
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
