from __future__ import annotations

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


def _stub_deployer():
    deployer = object.__new__(ServerDeployer)
    deployer.ip = "127.0.0.1"
    uploaded: dict[str, str] = {}
    commands: list[str] = []

    def fake_upload(content: str, remote_path: str):
        uploaded[remote_path] = content

    def fake_run(cmd: str, cwd: str = None, mask=None) -> str:
        commands.append(cmd)
        return ""

    deployer.upload_file = fake_upload
    deployer.run = fake_run
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
