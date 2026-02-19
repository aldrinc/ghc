import json
from pathlib import Path

import pytest

from app.services import deploy as deploy_service


def test_deploy_apply_proxies_to_service(api_client, monkeypatch):
    async def fake_apply_plan(*, plan_path=None):
        assert plan_path is None
        return {"returncode": 0, "plan_path": "/tmp/plan.json", "server_ips": {}, "live_url": None, "logs": ""}

    monkeypatch.setattr(deploy_service, "apply_plan", fake_apply_plan)

    resp = api_client.post("/deploy/plans/apply", json={})
    assert resp.status_code == 200
    assert resp.json()["returncode"] == 0


def test_deploy_apply_alias_works(api_client, monkeypatch):
    async def fake_apply_plan(*, plan_path=None):
        return {"returncode": 0, "plan_path": "/tmp/plan.json", "server_ips": {}, "live_url": None, "logs": ""}

    monkeypatch.setattr(deploy_service, "apply_plan", fake_apply_plan)

    resp = api_client.post("/deploy/apply", json={})
    assert resp.status_code == 200


def test_deploy_latest_plan_404_on_missing(api_client, monkeypatch):
    def fake_latest_plan():
        raise deploy_service.DeployError("No plan found.")

    monkeypatch.setattr(deploy_service, "get_latest_plan", fake_latest_plan)

    resp = api_client.get("/deploy/plans/latest")
    assert resp.status_code == 404


def test_ensure_plan_for_funnel_publish_workload_bootstraps_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))

    workload_patch = deploy_service.build_funnel_publication_workload_patch(
        workload_name="landing-page",
        client_id="f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
        upstream_base_url="https://moshq.app",
        upstream_api_base_url="https://moshq.app/api",
        server_names=[],
        https=False,
        destination_path="/opt/apps",
    )

    resolved = deploy_service.ensure_plan_for_funnel_publish_workload(
        workload_patch=workload_patch,
        plan_path=None,
        instance_name=None,
    )

    assert resolved["bootstrapped"] is True
    plan_path = resolved["plan_path"]
    payload = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    assert payload["new_spec"]["provider"] == "hetzner"
    assert payload["new_spec"]["region"] == "fsn1"
    assert payload["new_spec"]["instances"][0]["name"] == "ubuntu-4gb-nbg1-2"
    assert payload["new_spec"]["instances"][0]["size"] == "cx23"
    assert payload["new_spec"]["instances"][0]["network"] == "default"
    assert payload["new_spec"]["instances"][0]["region"] == "nbg1"
    assert payload["new_spec"]["instances"][0]["workloads"][0]["name"] == "landing-page"


def test_ensure_plan_for_funnel_publish_workload_uses_instance_override(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))

    workload_patch = deploy_service.build_funnel_publication_workload_patch(
        workload_name="landing-page",
        client_id="f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
        upstream_base_url="https://moshq.app",
        upstream_api_base_url="https://moshq.app/api",
        server_names=[],
        https=False,
        destination_path="/opt/apps",
    )

    resolved = deploy_service.ensure_plan_for_funnel_publish_workload(
        workload_patch=workload_patch,
        plan_path=None,
        instance_name="custom-instance-1",
    )
    payload = json.loads(Path(resolved["plan_path"]).read_text(encoding="utf-8"))
    assert payload["new_spec"]["instances"][0]["name"] == "custom-instance-1"


def test_infer_external_access_urls_uses_assigned_workload_port(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    spec_payload = {
        "new_spec": {
            "instances": [
                {
                    "name": "ubuntu-4gb-nbg1-2",
                    "workloads": [
                        {
                            "name": "landing-page",
                            "service_config": {"ports": [24123]},
                        }
                    ],
                }
            ]
        }
    }
    (tmp_path / "spec.json").write_text(json.dumps(spec_payload), encoding="utf-8")

    urls = deploy_service._infer_external_access_urls(
        server_ips={"ubuntu-4gb-nbg1-2": "198.51.100.10"},
        workload_name="landing-page",
        instance_name="ubuntu-4gb-nbg1-2",
    )
    assert urls == ["http://198.51.100.10:24123/"]


def test_infer_external_access_urls_uses_plain_spec_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    spec_payload = {
        "provider": "hetzner",
        "instances": [
            {
                "name": "ubuntu-4gb-nbg1-2",
                "workloads": [
                    {
                        "name": "landing-page",
                        "service_config": {"ports": [24123]},
                    }
                ],
            }
        ],
    }
    (tmp_path / "spec.json").write_text(json.dumps(spec_payload), encoding="utf-8")

    urls = deploy_service._infer_external_access_urls(
        server_ips={"ubuntu-4gb-nbg1-2": "198.51.100.10"},
        workload_name="landing-page",
        instance_name="ubuntu-4gb-nbg1-2",
    )
    assert urls == ["http://198.51.100.10:24123/"]


def test_infer_external_access_urls_errors_when_server_ips_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    with pytest.raises(deploy_service.DeployError, match="did not include server IPs"):
        deploy_service._infer_external_access_urls(
            server_ips={},
            workload_name="landing-page",
            instance_name="ubuntu-4gb-nbg1-2",
        )


def test_materialize_funnel_artifacts_for_apply_skips_empty_inline_artifacts_without_artifact_id(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    plan_file = tmp_path / "plan-input.json"
    plan_file.write_text(
        json.dumps(
            {
                "new_spec": {
                    "instances": [
                        {
                            "name": "mos-ghc-1",
                            "workloads": [
                                {
                                    "name": "legacy-funnel-workload",
                                    "source_type": "funnel_artifact",
                                    "source_ref": {
                                        "client_id": "f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
                                        "upstream_api_base_root": "https://moshq.app/api",
                                        "runtime_dist_path": "mos/frontend/dist",
                                        "artifact": {"meta": {"clientId": "c1"}, "products": {}},
                                    },
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    materialized = deploy_service._materialize_funnel_artifacts_for_apply(plan_file=plan_file)
    assert materialized == plan_file


def test_materialize_funnel_artifacts_for_apply_hydrates_from_artifact_id(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))

    def _fake_load(*, artifact_id: str):
        assert artifact_id == "artifact-123"
        return {
            "meta": {"artifactId": artifact_id},
            "products": {
                "sample-product": {
                    "meta": {"productSlug": "sample-product"},
                    "funnels": {},
                }
            },
        }

    monkeypatch.setattr(deploy_service, "_load_funnel_runtime_artifact_payload_for_apply", _fake_load)

    plan_file = tmp_path / "plan-input.json"
    plan_file.write_text(
        json.dumps(
            {
                "new_spec": {
                    "instances": [
                        {
                            "name": "mos-ghc-1",
                            "workloads": [
                                {
                                    "name": "brand-funnels-workload",
                                    "source_type": "funnel_artifact",
                                    "source_ref": {
                                        "client_id": "f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
                                        "artifact_id": "artifact-123",
                                        "upstream_api_base_root": "https://moshq.app/api",
                                        "runtime_dist_path": "mos/frontend/dist",
                                        "artifact": {"meta": {"clientId": "c1"}, "products": {}},
                                    },
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    materialized = deploy_service._materialize_funnel_artifacts_for_apply(plan_file=plan_file)
    assert materialized != plan_file
    payload = json.loads(materialized.read_text(encoding="utf-8"))
    source_ref = payload["new_spec"]["instances"][0]["workloads"][0]["source_ref"]
    assert source_ref["artifact"]["meta"]["artifactId"] == "artifact-123"
    assert "sample-product" in source_ref["artifact"]["products"]
