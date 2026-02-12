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
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_BOOTSTRAP_PROVIDER", "hetzner")
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_BOOTSTRAP_REGION", "ash")
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_BOOTSTRAP_NETWORK_NAME", "default")
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_BOOTSTRAP_NETWORK_CIDR", "10.0.0.0/16")
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_BOOTSTRAP_INSTANCE_NAME", "mos-landing-1")
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_BOOTSTRAP_INSTANCE_SIZE", "cpx21")
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_BOOTSTRAP_INSTANCE_REGION", "ash")
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_BOOTSTRAP_INSTANCE_LABELS", {"project": "mos"})

    workload_patch = deploy_service.build_funnel_publication_workload_patch(
        workload_name="landing-page",
        funnel_public_id="f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
        upstream_base_url="https://moshq.app",
        upstream_api_base_url="https://moshq.app/api/public/funnels/f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
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
    assert payload["new_spec"]["instances"][0]["name"] == "mos-landing-1"
    assert payload["new_spec"]["instances"][0]["workloads"][0]["name"] == "landing-page"


def test_ensure_plan_for_funnel_publish_workload_errors_when_bootstrap_config_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_BOOTSTRAP_PROVIDER", None)
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_BOOTSTRAP_REGION", None)
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_BOOTSTRAP_NETWORK_NAME", None)
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_BOOTSTRAP_NETWORK_CIDR", None)
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_BOOTSTRAP_INSTANCE_NAME", None)
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_BOOTSTRAP_INSTANCE_SIZE", None)
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_BOOTSTRAP_INSTANCE_REGION", None)
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_BOOTSTRAP_INSTANCE_LABELS", None)

    workload_patch = deploy_service.build_funnel_publication_workload_patch(
        workload_name="landing-page",
        funnel_public_id="f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
        upstream_base_url="https://moshq.app",
        upstream_api_base_url="https://moshq.app/api/public/funnels/f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
        server_names=[],
        https=False,
        destination_path="/opt/apps",
    )

    with pytest.raises(deploy_service.DeployError, match="Auto-bootstrap requires"):
        deploy_service.ensure_plan_for_funnel_publish_workload(
            workload_patch=workload_patch,
            plan_path=None,
            instance_name=None,
        )
