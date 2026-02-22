import json
import os
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


def test_build_bunny_pull_zone_name_uses_workspace_and_brand_ids():
    name = deploy_service._build_bunny_pull_zone_name(
        workspace_id="Workspace_123",
        brand_id="Brand/ABC",
    )
    assert name == "workspace-123-brand-abc"


def test_resolve_bunny_pull_zone_origin_url_uses_requested_origin_ip(monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "BUNNY_PULLZONE_ORIGIN_IP", None)
    origin_url = deploy_service._resolve_bunny_pull_zone_origin_url(
        requested_origin_ip="46.225.124.104",
    )
    assert origin_url == "http://46.225.124.104"


def test_resolve_bunny_pull_zone_origin_url_errors_when_origin_missing(monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "BUNNY_PULLZONE_ORIGIN_IP", None)
    with pytest.raises(deploy_service.DeployError, match="required"):
        deploy_service._resolve_bunny_pull_zone_origin_url(
            requested_origin_ip=None,
        )


def test_ensure_bunny_pull_zone_creates_when_missing(monkeypatch):
    calls: list[tuple[str, str, dict | None]] = []

    def fake_bunny_api_request(*, method: str, path: str, payload: dict | None = None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/pullzone":
            return {"Items": []}
        if method == "POST" and path == "/pullzone":
            assert payload == {
                "Name": "workspace-123-brand-abc",
                "OriginUrl": "http://46.225.124.104",
            }
            return {
                "Id": 123,
                "Name": "workspace-123-brand-abc",
                "OriginUrl": "http://46.225.124.104",
                "Hostnames": [{"Value": "workspace-123-brand-abc.b-cdn.net"}],
            }
        raise AssertionError(f"Unexpected Bunny API call: method={method}, path={path}, payload={payload}")

    monkeypatch.setattr(deploy_service, "_bunny_api_request", fake_bunny_api_request)
    zone = deploy_service._ensure_bunny_pull_zone(
        workspace_id="workspace-123",
        brand_id="brand-abc",
        origin_url="http://46.225.124.104",
    )
    urls = deploy_service._extract_bunny_pull_zone_access_urls(zone)

    assert zone["Id"] == 123
    assert urls == ["https://workspace-123-brand-abc.b-cdn.net/"]
    assert calls[0] == ("GET", "/pullzone", None)
    assert calls[1][0] == "POST"
    assert calls[1][1] == "/pullzone"


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


def test_find_latest_plan_ignores_materialized_apply_plans(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))

    canonical_older = tmp_path / "plan-2026-02-19T12-00-00Z.json"
    canonical_newer = tmp_path / "plan-2026-02-19T12-05-00Z.json"
    materialized = tmp_path / "plan-apply-2026-02-19T12-06-00Z-abcd1234.json"

    canonical_older.write_text("{}", encoding="utf-8")
    canonical_newer.write_text("{}", encoding="utf-8")
    materialized.write_text("{}", encoding="utf-8")

    os.utime(canonical_older, (100.0, 100.0))
    os.utime(canonical_newer, (200.0, 200.0))
    os.utime(materialized, (300.0, 300.0))

    latest = deploy_service._find_latest_plan()
    assert latest == canonical_newer


def test_find_latest_plan_returns_none_when_only_materialized_apply_plan_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))

    materialized = tmp_path / "plan-apply-2026-02-19T12-06-00Z-abcd1234.json"
    materialized.write_text("{}", encoding="utf-8")

    assert deploy_service._find_latest_plan() is None


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


def test_materialize_funnel_artifacts_for_apply_normalizes_legacy_publication_source_ref(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_PUBLIC_BASE_URL", "https://moshq.app")
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_PUBLIC_API_BASE_URL", "https://moshq.app/api")

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
                                    "name": "legacy-publication-workload",
                                    "source_type": "funnel_publication",
                                    "source_ref": {
                                        "public_id": "dc6431ec-6f65-4fac-9492-6581a93690b0",
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
    assert source_ref["public_id"] == "dc6431ec-6f65-4fac-9492-6581a93690b0"
    assert source_ref["upstream_base_url"] == "https://moshq.app"
    assert source_ref["upstream_api_base_url"] == "https://moshq.app/api"


def test_materialize_funnel_artifacts_for_apply_normalizes_legacy_artifact_source_ref(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_PUBLIC_API_BASE_URL", "https://moshq.app/api")
    client_id = "f51f25df-e761-4ead-850b-a35a20b35fde"
    product_id = "638d19db-9480-4bbd-91c6-052b07b6537d"

    def _fake_product_context(*, product_id: str):
        assert product_id == "638d19db-9480-4bbd-91c6-052b07b6537d"
        return (
            "f51f25df-e761-4ead-850b-a35a20b35fde",
            "legacy-product",
        )

    monkeypatch.setattr(deploy_service, "_load_product_route_context_for_apply", _fake_product_context)

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
                                    "name": "legacy-artifact-workload",
                                    "source_type": "funnel_artifact",
                                    "source_ref": {
                                        "product_id": product_id,
                                        "upstream_api_base_url": "https://moshq.app/api",
                                        "artifact": {
                                            "meta": {"productId": product_id},
                                            "funnels": {},
                                        },
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
    workload = payload["new_spec"]["instances"][0]["workloads"][0]
    source_ref = workload["source_ref"]
    assert source_ref["client_id"] == client_id
    assert source_ref["upstream_api_base_root"] == "https://moshq.app/api"
    assert source_ref["runtime_dist_path"] == deploy_service.settings.DEPLOY_ARTIFACT_RUNTIME_DIST_PATH
    assert "legacy-product" in source_ref["artifact"]["products"]


def test_materialize_funnel_artifacts_for_apply_converts_legacy_artifact_public_id_to_publication(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_PUBLIC_BASE_URL", "https://moshq.app")
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_PUBLIC_API_BASE_URL", "https://moshq.app/api")

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
                                    "name": "legacy-artifact-public-id-workload",
                                    "source_type": "funnel_artifact",
                                    "source_ref": {
                                        "public_id": "dc6431ec-6f65-4fac-9492-6581a93690b0",
                                        "artifact": {"meta": {"offers": []}},
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
    workload = payload["new_spec"]["instances"][0]["workloads"][0]
    source_ref = workload["source_ref"]
    assert workload["source_type"] == "funnel_publication"
    assert source_ref["public_id"] == "dc6431ec-6f65-4fac-9492-6581a93690b0"
    assert source_ref["upstream_base_url"] == "https://moshq.app"
    assert source_ref["upstream_api_base_url"] == "https://moshq.app/api"
