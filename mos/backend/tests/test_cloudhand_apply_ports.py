from __future__ import annotations

import json
from pathlib import Path

import pytest

import cloudhand.core.apply as apply_module
from cloudhand.core.apply import (
    _assign_and_validate_instance_ports,
    _compute_stale_workloads,
    _validate_moshq_frontend_workloads,
    _validate_instance_server_name_conflicts,
)
from cloudhand.models import ApplicationSpec, DesiredStateSpec


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


def _artifact_app(
    *,
    name: str,
    ports: list[int] | None = None,
    env: dict[str, str] | None = None,
) -> ApplicationSpec:
    payload = {
        "name": name,
        "source_type": "funnel_artifact",
        "source_ref": {
            "client_id": "f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
            "upstream_api_base_root": "https://moshq.app/api",
            "runtime_dist_path": "mos/frontend/dist",
            "artifact": {
                "meta": {"clientId": "f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95"},
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
            "environment": env or {},
            "ports": ports or [],
            "server_names": [],
            "https": False,
        },
        "destination_path": "/opt/apps",
    }
    return ApplicationSpec.model_validate(payload)


def _instance_payload(name: str, app_payloads: list[dict]) -> dict:
    return {
        "name": name,
        "size": "cx23",
        "network": "default",
        "region": "nbg1",
        "labels": {},
        "workloads": app_payloads,
        "maintenance": None,
    }


def _desired_spec(instances: list[dict]) -> DesiredStateSpec:
    return DesiredStateSpec.model_validate(
        {
            "provider": "hetzner",
            "region": "fsn1",
            "networks": [{"name": "default", "cidr": "10.0.0.0/16"}],
            "instances": instances,
            "load_balancers": [],
            "firewalls": [],
            "dns_records": [],
            "containers": [],
        }
    )


def _moshq_git_app(*, name: str, command: str = "npm run start") -> dict:
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
            "environment": {},
            "ports": [3100],
            "server_names": ["moshq.app"],
            "https": True,
        },
        "destination_path": "/opt/apps",
    }
    return payload


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


def test_validate_moshq_frontend_workloads_scopes_to_selected_workloads():
    spec = _desired_spec(
        [
            _instance_payload(
                "mos-ghc-1",
                [
                    _moshq_git_app(name="mos-ui-good", command="npm run start"),
                    _moshq_git_app(name="mos-ui-bad", command="npm run start"),
                ],
            )
        ]
    )
    spec.instances[0].workloads[1].service_config.command = "python -m http.server 3000"

    _validate_moshq_frontend_workloads(spec, workload_names={"mos-ui-good"})

    with pytest.raises(ValueError, match="Python's built-in static file server"):
        _validate_moshq_frontend_workloads(spec, workload_names={"mos-ui-bad"})


def test_assign_ports_for_funnel_artifact_is_deterministic_and_no_port_env():
    app_a = _artifact_app(name="landing-artifact-a")
    app_b = _artifact_app(name="landing-artifact-b")
    _assign_and_validate_instance_ports(instance_name="mos-ghc-1", app_models=[app_a, app_b])

    a_port = app_a.service_config.ports[0]
    b_port = app_b.service_config.ports[0]
    assert a_port != b_port
    assert 20000 <= a_port <= 29999
    assert 20000 <= b_port <= 29999
    assert "PORT" not in app_a.service_config.environment
    assert "PORT" not in app_b.service_config.environment


def test_validate_instance_server_name_conflicts_allows_unique_domains_and_domainless():
    app_domain_a = _artifact_app(name="artifact-a")
    app_domain_a.service_config.server_names = ["funnel-a.example.com"]

    app_domain_b = _artifact_app(name="artifact-b")
    app_domain_b.service_config.server_names = ["funnel-b.example.com"]

    app_domainless = _artifact_app(name="artifact-c")
    app_domainless.service_config.server_names = []

    _validate_instance_server_name_conflicts(
        instance_name="mos-ghc-1",
        app_models=[app_domain_a, app_domain_b, app_domainless],
    )


def test_validate_instance_server_name_conflicts_rejects_duplicate_domain():
    app_a = _artifact_app(name="artifact-a")
    app_a.service_config.server_names = ["landing.example.com"]

    app_b = _artifact_app(name="artifact-b")
    app_b.service_config.server_names = ["landing.example.com"]

    with pytest.raises(ValueError, match="Server name conflict"):
        _validate_instance_server_name_conflicts(
            instance_name="mos-ghc-1",
            app_models=[app_a, app_b],
        )


def test_apply_plan_deploys_only_selected_workload(tmp_path, monkeypatch):
    app_a = _artifact_app(name="artifact-a")
    app_b = _artifact_app(name="artifact-b")
    spec = _desired_spec([_instance_payload("mos-ghc-1", [app_a.model_dump(mode="json"), app_b.model_dump(mode="json")])])
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps({"new_spec": spec.model_dump(mode="json")}), encoding="utf-8")

    generated: dict[str, object] = {}
    deployed: list[str] = []

    class FakeGenerator:
        def generate(self, spec_obj, tf_dir, project_id, workspace_id):
            generated["instances"] = [inst.name for inst in spec_obj.instances]
            Path(tf_dir).mkdir(parents=True, exist_ok=True)

    class FakeCompleted:
        def __init__(self, returncode: int = 0):
            self.returncode = returncode

    class FakeDeployer:
        def __init__(self, ip, priv_key, local_root=None):
            self.ip = ip
            self.priv_key = priv_key
            self.local_root = local_root

        def deploy(self, app, configure_nginx=True):
            deployed.append(app.name)

        def remove_workload(self, app):
            deployed.append(f"remove:{app.name}")

    def fake_run(cmd, cwd=None, check=False, env=None):
        _ = cwd, check, env
        if len(cmd) >= 2 and cmd[1] == "apply":
            return FakeCompleted(returncode=0)
        return FakeCompleted(returncode=0)

    monkeypatch.setattr(apply_module, "get_generator", lambda provider: FakeGenerator())
    monkeypatch.setattr(apply_module, "get_or_create_project_ssh_key", lambda project_id: ("priv", "pub"))
    monkeypatch.setattr(apply_module.shutil, "which", lambda binary: f"/usr/bin/{binary}")
    monkeypatch.setattr(apply_module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        apply_module.subprocess,
        "check_output",
        lambda cmd, cwd=None, env=None: json.dumps(
            {"server_ips": {"value": {"mos-ghc-1": "127.0.0.1"}}}
        ).encode("utf-8"),
    )
    monkeypatch.setattr(apply_module, "ServerDeployer", FakeDeployer)
    monkeypatch.setenv("HCLOUD_TOKEN", "token")

    rc = apply_module.apply_plan(
        root=tmp_path,
        plan_path=plan_path,
        auto_approve=True,
        workload_names=["artifact-b"],
    )

    assert rc == 0
    assert generated["instances"] == ["mos-ghc-1"]
    assert deployed == ["artifact-b"]


def test_compute_stale_workloads_identifies_removed_workloads_and_instances():
    previous = _desired_spec(
        [
            _instance_payload(
                "mos-ghc-1",
                [
                    _git_app(name="honest-herbalist").model_dump(),
                    _funnel_app(name="funnel-old").model_dump(),
                ],
            ),
            _instance_payload(
                "mos-ghc-2",
                [
                    _git_app(name="legacy-site").model_dump(),
                ],
            ),
        ]
    )

    desired = _desired_spec(
        [
            _instance_payload(
                "mos-ghc-1",
                [
                    _funnel_app(name="funnel-new").model_dump(),
                ],
            ),
        ]
    )

    stale = _compute_stale_workloads(previous_spec=previous, desired_spec=desired)
    assert set(stale.keys()) == {"mos-ghc-1", "mos-ghc-2"}
    assert {app.name for app in stale["mos-ghc-1"]} == {"honest-herbalist", "funnel-old"}
    assert {app.name for app in stale["mos-ghc-2"]} == {"legacy-site"}
