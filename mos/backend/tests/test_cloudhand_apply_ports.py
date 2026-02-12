from __future__ import annotations

import pytest

from cloudhand.core.apply import _assign_and_validate_instance_ports
from cloudhand.models import ApplicationSpec


def _git_app(*, name: str, ports: list[int] | None = None, env: dict[str, str] | None = None) -> ApplicationSpec:
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
            "environment": env or {},
            "ports": ports or [],
            "server_names": ["example.com"],
            "https": True,
        },
        "destination_path": "/opt/apps",
    }
    return ApplicationSpec.model_validate(payload)


def _funnel_app(
    *,
    name: str,
    ports: list[int] | None = None,
    env: dict[str, str] | None = None,
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
            "environment": env or {},
            "ports": ports or [],
            "server_names": [],
            "https": False,
        },
        "destination_path": "/opt/apps",
    }
    return ApplicationSpec.model_validate(payload)


def test_assign_ports_deterministic_and_unique():
    app_a = _git_app(name="alpha")
    app_b = _git_app(name="beta")
    _assign_and_validate_instance_ports(instance_name="mos-ghc-1", app_models=[app_a, app_b])

    a_port = app_a.service_config.ports[0]
    b_port = app_b.service_config.ports[0]
    assert a_port != b_port
    assert 20000 <= a_port <= 29999
    assert 20000 <= b_port <= 29999
    assert app_a.service_config.environment["PORT"] == str(a_port)
    assert app_b.service_config.environment["PORT"] == str(b_port)

    app_a_2 = _git_app(name="alpha")
    app_b_2 = _git_app(name="beta")
    _assign_and_validate_instance_ports(instance_name="mos-ghc-1", app_models=[app_a_2, app_b_2])
    assert app_a_2.service_config.ports[0] == a_port
    assert app_b_2.service_config.ports[0] == b_port


def test_assign_ports_uses_env_port_when_present():
    app = _git_app(name="gamma", env={"PORT": "3100"})
    _assign_and_validate_instance_ports(instance_name="mos-ghc-1", app_models=[app])
    assert app.service_config.ports == [3100]
    assert app.service_config.environment["PORT"] == "3100"


def test_assign_ports_rejects_duplicate_explicit_ports():
    app_a = _git_app(name="alpha", ports=[3000])
    app_b = _git_app(name="beta", ports=[3000])
    with pytest.raises(ValueError, match="Port conflict"):
        _assign_and_validate_instance_ports(instance_name="mos-ghc-1", app_models=[app_a, app_b])


def test_assign_ports_rejects_reserved_system_port():
    app = _git_app(name="alpha", ports=[80])
    with pytest.raises(ValueError, match="already reserved"):
        _assign_and_validate_instance_ports(instance_name="mos-ghc-1", app_models=[app])


def test_assign_ports_for_funnel_publication_is_deterministic_and_no_port_env():
    app_a = _funnel_app(name="landing-alpha")
    app_b = _funnel_app(name="landing-beta")
    _assign_and_validate_instance_ports(instance_name="mos-ghc-1", app_models=[app_a, app_b])

    a_port = app_a.service_config.ports[0]
    b_port = app_b.service_config.ports[0]
    assert a_port != b_port
    assert 20000 <= a_port <= 29999
    assert 20000 <= b_port <= 29999
    assert "PORT" not in app_a.service_config.environment
    assert "PORT" not in app_b.service_config.environment

    app_a_2 = _funnel_app(name="landing-alpha")
    app_b_2 = _funnel_app(name="landing-beta")
    _assign_and_validate_instance_ports(instance_name="mos-ghc-1", app_models=[app_a_2, app_b_2])
    assert app_a_2.service_config.ports[0] == a_port
    assert app_b_2.service_config.ports[0] == b_port
