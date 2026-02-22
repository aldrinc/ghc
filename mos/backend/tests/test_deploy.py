import json
import os
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.models import Org, OrgDeployDomain
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


def test_patch_workload_endpoint_persists_org_deploy_domains(api_client, db_session, monkeypatch):
    def fake_patch_workload_in_plan(
        *,
        org_id: str,
        workload_patch: dict,
        plan_path: str | None = None,
        instance_name: str | None = None,
        create_if_missing: bool = False,
        in_place: bool = False,
    ):
        _ = org_id
        _ = workload_patch
        _ = plan_path
        _ = instance_name
        _ = create_if_missing
        _ = in_place
        return {
            "status": "ok",
            "base_plan_path": "/tmp/plan.json",
            "updated_plan_path": "/tmp/plan.json",
            "workload_name": "brand-funnels-test",
            "updated_count": 1,
        }

    monkeypatch.setattr(deploy_service, "patch_workload_in_plan", fake_patch_workload_in_plan)

    resp = api_client.post(
        "/deploy/plans/workloads?plan_path=/tmp/plan.json",
        json={
            "name": "brand-funnels-test",
            "service_config": {
                "server_names": [
                    "Offers.Example.com",
                    "offers.example.com",
                    "  ",
                    "Landing.example.com",
                ],
                "https": True,
            },
        },
    )
    assert resp.status_code == 200

    hostnames = db_session.scalars(
        select(OrgDeployDomain.hostname).order_by(OrgDeployDomain.hostname.asc())
    ).all()
    assert hostnames == ["landing.example.com", "offers.example.com"]


def test_patch_workload_endpoint_clears_plan_domains_when_configuring_bunny(api_client, monkeypatch):
    captured: dict[str, object] = {}

    def fake_patch_workload_in_plan(
        *,
        org_id: str,
        workload_patch: dict,
        plan_path: str | None = None,
        instance_name: str | None = None,
        create_if_missing: bool = False,
        in_place: bool = False,
    ):
        captured["workload_patch"] = workload_patch
        return {
            "status": "ok",
            "base_plan_path": "/tmp/plan.json",
            "updated_plan_path": "/tmp/plan.json",
            "workload_name": "brand-funnels-test",
            "updated_count": 1,
        }

    def fake_configure_bunny_pull_zone_for_workload(
        *,
        org_id: str,
        workload_name: str,
        plan_path: str | None,
        instance_name: str | None,
        requested_origin_ip: str | None = None,
        server_names: list[str] | None = None,
    ):
        captured["cdn_server_names"] = server_names
        return {"provider": "bunny", "pull_zone": {"name": "workspace-123"}}

    monkeypatch.setattr(deploy_service, "patch_workload_in_plan", fake_patch_workload_in_plan)
    monkeypatch.setattr(
        deploy_service,
        "configure_bunny_pull_zone_for_workload",
        fake_configure_bunny_pull_zone_for_workload,
    )

    resp = api_client.post(
        "/deploy/plans/workloads?plan_path=/tmp/plan.json&configure_bunny_pull_zone=true",
        json={
            "name": "brand-funnels-test",
            "service_config": {
                "server_names": ["shop.example.com"],
                "https": True,
            },
            "org_server_names": ["shop.example.com"],
        },
    )
    assert resp.status_code == 200

    workload_patch = captured["workload_patch"]
    assert workload_patch["service_config"]["server_names"] == []
    assert workload_patch["service_config"]["https"] is False
    assert "org_server_names" not in workload_patch
    assert captured["cdn_server_names"] == ["shop.example.com"]


def test_get_workload_domains_includes_org_server_names(api_client, db_session, monkeypatch):
    org_id = db_session.scalars(select(Org.id)).first()
    assert org_id is not None
    db_session.add_all(
        [
            OrgDeployDomain(org_id=org_id, hostname="offers.example.com"),
        ]
    )
    db_session.commit()

    def fake_get_workload_domains_from_plan(
        *,
        workload_name: str,
        plan_path: str | None = None,
        instance_name: str | None = None,
    ):
        _ = workload_name
        _ = plan_path
        _ = instance_name
        return {
            "plan_path": "/tmp/plan.json",
            "workload_found": True,
            "server_names": [],
            "https": False,
        }

    monkeypatch.setattr(
        deploy_service,
        "get_workload_domains_from_plan",
        fake_get_workload_domains_from_plan,
    )

    resp = api_client.get("/deploy/plans/workloads/domains?workload_name=brand-funnels-test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["org_server_names"] == ["offers.example.com"]
    assert body["server_names"] == []


def test_build_bunny_pull_zone_name_uses_org_id():
    name = deploy_service._build_bunny_pull_zone_name(
        org_id="Workspace_123",
    )
    assert name == "workspace-123"


def test_resolve_bunny_pull_zone_origin_url_uses_requested_origin_ip(monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "BUNNY_PULLZONE_ORIGIN_IP", None)
    origin_url = deploy_service._resolve_bunny_pull_zone_origin_url(
        requested_origin_ip="46.225.124.104",
    )
    assert origin_url == "http://46.225.124.104"


def test_resolve_bunny_pull_zone_origin_url_appends_workload_port(monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "BUNNY_PULLZONE_ORIGIN_IP", None)
    origin_url = deploy_service._resolve_bunny_pull_zone_origin_url(
        requested_origin_ip="46.225.124.104",
        workload_port=24123,
    )
    assert origin_url == "http://46.225.124.104:24123"


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
                "Name": "workspace-123",
                "OriginUrl": "http://46.225.124.104",
            }
            return {
                "Id": 123,
                "Name": "workspace-123",
                "OriginUrl": "http://46.225.124.104",
                "Hostnames": [{"Value": "workspace-123.b-cdn.net"}],
            }
        raise AssertionError(f"Unexpected Bunny API call: method={method}, path={path}, payload={payload}")

    monkeypatch.setattr(deploy_service, "_bunny_api_request", fake_bunny_api_request)
    zone = deploy_service._ensure_bunny_pull_zone(
        org_id="workspace-123",
        origin_url="http://46.225.124.104",
    )
    urls = deploy_service._extract_bunny_pull_zone_access_urls(zone)

    assert zone["Id"] == 123
    assert urls == ["https://workspace-123.b-cdn.net/"]
    assert calls[0] == ("GET", "/pullzone", None)
    assert calls[1][0] == "POST"
    assert calls[1][1] == "/pullzone"


def test_list_bunny_pull_zones_accepts_array_response(monkeypatch):
    monkeypatch.setattr(
        deploy_service,
        "_bunny_api_request",
        lambda *, method, path, payload=None: [
            {"Id": 123, "Name": "workspace-123"},
            {"Id": 456, "Name": "workspace-456"},
        ],
    )
    zones = deploy_service._list_bunny_pull_zones()
    assert len(zones) == 2
    assert zones[0]["Id"] == 123
    assert zones[1]["Id"] == 456


def test_provision_bunny_custom_domains_upserts_namecheap_and_requests_ssl(monkeypatch):
    bunny_zone = {
        "Id": 777,
        "Name": "workspace-123",
        "Hostnames": [{"Value": "workspace-123.b-cdn.net"}],
    }

    captured: dict[str, object] = {}

    def fake_upsert_cname_record(*, hostname: str, target_hostname: str):
        captured["hostname"] = hostname
        captured["target_hostname"] = target_hostname
        return {"provider": "namecheap", "fqdn": hostname, "target": target_hostname}

    monkeypatch.setattr(
        deploy_service.namecheap_dns_service,
        "upsert_cname_record",
        fake_upsert_cname_record,
    )
    monkeypatch.setattr(
        deploy_service,
        "_ensure_bunny_pull_zone_auto_ssl_enabled",
        lambda *, zone_id: captured.setdefault("auto_ssl_zone_id", zone_id),
    )
    monkeypatch.setattr(
        deploy_service,
        "_ensure_bunny_pull_zone_hostname",
        lambda *, zone_id, hostname: {"zone_id": zone_id, "hostname": hostname, "status": "created"},
    )
    monkeypatch.setattr(
        deploy_service,
        "_request_bunny_pull_zone_certificate",
        lambda *, zone_id, hostname: {"zone_id": zone_id, "hostname": hostname, "status": "queued"},
    )
    monkeypatch.setattr(
        deploy_service,
        "_get_bunny_pull_zone",
        lambda *, zone_id: {
            "Id": zone_id,
            "Hostnames": [
                {"Value": "workspace-123.b-cdn.net"},
                {"Value": "shop.example.com"},
            ],
        },
    )

    output = deploy_service._provision_bunny_custom_domains(
        bunny_zone=bunny_zone,
        server_names=["shop.example.com"],
    )

    assert output["dnsTargetHostname"] == "workspace-123.b-cdn.net"
    assert output["pullZoneHostnames"] == ["workspace-123.b-cdn.net", "shop.example.com"]
    assert len(output["domains"]) == 1
    assert output["domains"][0]["hostname"] == "shop.example.com"
    assert output["domains"][0]["dns"]["provider"] == "namecheap"
    assert output["domains"][0]["ssl"]["status"] == "requested"
    assert captured == {
        "hostname": "shop.example.com",
        "target_hostname": "workspace-123.b-cdn.net",
        "auto_ssl_zone_id": 777,
    }


def test_provision_bunny_custom_domains_skips_dns_when_no_domains(monkeypatch):
    bunny_zone = {
        "Id": 777,
        "Name": "workspace-123",
        "Hostnames": [{"Value": "workspace-123.b-cdn.net"}],
    }

    def _unexpected_upsert(*, hostname: str, target_hostname: str):
        raise AssertionError(f"Namecheap should not be called, got {hostname} -> {target_hostname}")

    monkeypatch.setattr(
        deploy_service.namecheap_dns_service,
        "upsert_cname_record",
        _unexpected_upsert,
    )

    output = deploy_service._provision_bunny_custom_domains(
        bunny_zone=bunny_zone,
        server_names=[],
    )

    assert output == {
        "dnsTargetHostname": None,
        "domains": [],
        "pullZoneHostnames": ["workspace-123.b-cdn.net"],
    }


def test_provision_bunny_custom_domains_skips_ssl_request_when_disabled(monkeypatch):
    bunny_zone = {
        "Id": 777,
        "Name": "workspace-123",
        "Hostnames": [{"Value": "workspace-123.b-cdn.net"}],
    }

    monkeypatch.setattr(
        deploy_service.namecheap_dns_service,
        "upsert_cname_record",
        lambda *, hostname, target_hostname: {
            "provider": "namecheap",
            "fqdn": hostname,
            "target": target_hostname,
        },
    )

    def _unexpected_auto_ssl(*, zone_id: int):
        raise AssertionError(f"Auto SSL should not run on deploy-domain save path for zone {zone_id}")

    def _unexpected_certificate(*, zone_id: int, hostname: str):
        raise AssertionError(
            f"Free certificate should not be requested on deploy-domain save path ({zone_id}, {hostname})"
        )

    monkeypatch.setattr(deploy_service, "_ensure_bunny_pull_zone_auto_ssl_enabled", _unexpected_auto_ssl)
    monkeypatch.setattr(deploy_service, "_request_bunny_pull_zone_certificate", _unexpected_certificate)
    monkeypatch.setattr(
        deploy_service,
        "_ensure_bunny_pull_zone_hostname",
        lambda *, zone_id, hostname: {"zone_id": zone_id, "hostname": hostname, "status": "created"},
    )
    monkeypatch.setattr(
        deploy_service,
        "_get_bunny_pull_zone",
        lambda *, zone_id: {
            "Id": zone_id,
            "Hostnames": [
                {"Value": "workspace-123.b-cdn.net"},
                {"Value": "shop.example.com"},
            ],
        },
    )

    output = deploy_service._provision_bunny_custom_domains(
        bunny_zone=bunny_zone,
        server_names=["shop.example.com"],
        request_ssl=False,
    )

    assert output["domains"][0]["ssl"]["status"] == "pending_publish"
    assert output["domains"][0]["ssl"]["certificateRequest"] is None


def test_configure_bunny_pull_zone_for_workload_uses_updated_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    monkeypatch.setattr(deploy_service.settings, "BUNNY_PULLZONE_ORIGIN_IP", "46.225.124.104")

    plan_path = tmp_path / "plan-test.json"
    plan_path.write_text(
        json.dumps(
            {
                "new_spec": {
                    "instances": [
                        {
                            "name": "mos-ghc-1",
                            "workloads": [
                                {
                                    "name": "brand-funnels-brand-abc",
                                    "source_type": "funnel_artifact",
                                    "service_config": {"server_names": ["offers.example.com"], "https": True},
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    captured: dict[str, str] = {}

    def fake_ensure_bunny_pull_zone(*, org_id: str, origin_url: str):
        captured["org_id"] = org_id
        captured["origin_url"] = origin_url
        return {
            "Id": 999,
            "Name": "workspace-123",
            "OriginUrl": origin_url,
            "Hostnames": [{"Value": "workspace-123.b-cdn.net"}],
        }

    monkeypatch.setattr(deploy_service, "_ensure_bunny_pull_zone", fake_ensure_bunny_pull_zone)
    monkeypatch.setattr(
        deploy_service,
        "_provision_bunny_custom_domains",
        lambda *, bunny_zone, server_names, request_ssl: {
            "dnsTargetHostname": "workspace-123.b-cdn.net",
            "domains": [
                {
                    "hostname": "offers.example.com",
                    "dns": {"provider": "namecheap"},
                    "bunnyHostname": {"status": "created"},
                    "ssl": {"status": "pending_publish" if not request_ssl else "requested"},
                }
            ],
            "pullZoneHostnames": ["workspace-123.b-cdn.net", "offers.example.com"],
        },
    )

    output = deploy_service.configure_bunny_pull_zone_for_workload(
        org_id="workspace-123",
        workload_name="brand-funnels-brand-abc",
        plan_path=str(plan_path),
        instance_name="mos-ghc-1",
    )
    assert output["provider"] == "bunny"
    assert output["pull_zone"]["id"] == 999
    assert output["pull_zone"]["name"] == "workspace-123"
    assert output["pull_zone"]["originUrl"] == "http://46.225.124.104"
    assert output["pull_zone"]["accessUrls"] == ["https://workspace-123.b-cdn.net/", "https://offers.example.com/"]
    assert output["pull_zone"]["dnsTargetHostname"] == "workspace-123.b-cdn.net"
    assert isinstance(output["pull_zone"]["domainProvisioning"], list)
    assert captured == {
        "org_id": "workspace-123",
        "origin_url": "http://46.225.124.104",
    }


def test_configure_bunny_pull_zone_for_workload_uses_workload_port_when_no_domains(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    monkeypatch.setattr(deploy_service.settings, "BUNNY_PULLZONE_ORIGIN_IP", "46.225.124.104")

    plan_path = tmp_path / "plan-test.json"
    plan_path.write_text(
        json.dumps(
            {
                "new_spec": {
                    "instances": [
                        {
                            "name": "mos-ghc-1",
                            "workloads": [
                                {
                                    "name": "brand-funnels-brand-abc",
                                    "source_type": "funnel_artifact",
                                    "service_config": {"server_names": [], "https": False, "ports": [24123]},
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    captured: dict[str, str] = {}

    def fake_ensure_bunny_pull_zone(*, org_id: str, origin_url: str):
        captured["org_id"] = org_id
        captured["origin_url"] = origin_url
        return {
            "Id": 999,
            "Name": "workspace-123",
            "OriginUrl": origin_url,
            "Hostnames": [{"Value": "workspace-123.b-cdn.net"}],
        }

    monkeypatch.setattr(deploy_service, "_ensure_bunny_pull_zone", fake_ensure_bunny_pull_zone)

    output = deploy_service.configure_bunny_pull_zone_for_workload(
        org_id="workspace-123",
        workload_name="brand-funnels-brand-abc",
        plan_path=str(plan_path),
        instance_name="mos-ghc-1",
    )
    assert output["provider"] == "bunny"
    assert output["pull_zone"]["id"] == 999
    assert output["pull_zone"]["name"] == "workspace-123"
    assert output["pull_zone"]["originUrl"] == "http://46.225.124.104:24123"
    assert output["pull_zone"]["accessUrls"] == ["https://workspace-123.b-cdn.net/"]
    assert output["pull_zone"]["workloadPort"] == 24123
    assert captured == {
        "org_id": "workspace-123",
        "origin_url": "http://46.225.124.104:24123",
    }


def test_configure_bunny_pull_zone_for_workload_allows_missing_port(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    monkeypatch.setattr(deploy_service.settings, "BUNNY_PULLZONE_ORIGIN_IP", "46.225.124.104")

    plan_path = tmp_path / "plan-test.json"
    plan_path.write_text(
        json.dumps(
            {
                "new_spec": {
                    "instances": [
                        {
                            "name": "mos-ghc-1",
                            "workloads": [
                                {
                                    "name": "brand-funnels-brand-abc",
                                    "source_type": "funnel_artifact",
                                    "service_config": {"server_names": [], "https": False, "ports": []},
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    captured: dict[str, str] = {}

    def fake_ensure_bunny_pull_zone(*, org_id: str, origin_url: str):
        captured["org_id"] = org_id
        captured["origin_url"] = origin_url
        return {
            "Id": 999,
            "Name": "workspace-123",
            "OriginUrl": origin_url,
            "Hostnames": [{"Value": "workspace-123.b-cdn.net"}],
        }

    monkeypatch.setattr(deploy_service, "_ensure_bunny_pull_zone", fake_ensure_bunny_pull_zone)

    output = deploy_service.configure_bunny_pull_zone_for_workload(
        org_id="workspace-123",
        workload_name="brand-funnels-brand-abc",
        plan_path=str(plan_path),
        instance_name="mos-ghc-1",
    )
    assert output["provider"] == "bunny"
    assert output["pull_zone"]["originUrl"] == "http://46.225.124.104"
    assert output["pull_zone"]["workloadPort"] is None
    assert output["pull_zone"]["workloadPortPending"] is True
    assert output["pull_zone"]["workloadPortSource"] == "pending"
    assert captured == {
        "org_id": "workspace-123",
        "origin_url": "http://46.225.124.104",
    }


def test_configure_bunny_pull_zone_for_workload_uses_explicit_server_name_override(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    monkeypatch.setattr(deploy_service.settings, "BUNNY_PULLZONE_ORIGIN_IP", "46.225.124.104")

    plan_path = tmp_path / "plan-test.json"
    plan_path.write_text(
        json.dumps(
            {
                "new_spec": {
                    "instances": [
                        {
                            "name": "mos-ghc-1",
                            "workloads": [
                                {
                                    "name": "brand-funnels-brand-abc",
                                    "source_type": "funnel_artifact",
                                    "service_config": {"server_names": [], "https": False, "ports": []},
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def fake_ensure_bunny_pull_zone(*, org_id: str, origin_url: str):
        captured["origin_url"] = origin_url
        return {
            "Id": 999,
            "Name": "workspace-123",
            "OriginUrl": origin_url,
            "Hostnames": [{"Value": "workspace-123.b-cdn.net"}],
        }

    def fake_provision(*, bunny_zone: dict, server_names: list[str], request_ssl: bool = True):
        captured["server_names"] = server_names
        captured["request_ssl"] = request_ssl
        return {
            "dnsTargetHostname": "workspace-123.b-cdn.net",
            "domains": [],
            "pullZoneHostnames": ["workspace-123.b-cdn.net"],
        }

    monkeypatch.setattr(deploy_service, "_ensure_bunny_pull_zone", fake_ensure_bunny_pull_zone)
    monkeypatch.setattr(deploy_service, "_provision_bunny_custom_domains", fake_provision)

    output = deploy_service.configure_bunny_pull_zone_for_workload(
        org_id="workspace-123",
        workload_name="brand-funnels-brand-abc",
        plan_path=str(plan_path),
        instance_name="mos-ghc-1",
        server_names=["shop.example.com"],
    )
    assert output["provider"] == "bunny"
    assert output["pull_zone"]["originUrl"] == "http://46.225.124.104"
    assert captured["origin_url"] == "http://46.225.124.104"
    assert captured["server_names"] == ["shop.example.com"]
    assert captured["request_ssl"] is False


def test_reconcile_bunny_pull_zone_for_published_workload_uses_spec_port(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    monkeypatch.setattr(deploy_service.settings, "BUNNY_PULLZONE_ORIGIN_IP", "46.225.124.104")

    plan_path = tmp_path / "plan-test.json"
    plan_path.write_text(
        json.dumps(
            {
                "new_spec": {
                    "instances": [
                        {
                            "name": "mos-ghc-1",
                            "workloads": [
                                {
                                    "name": "brand-funnels-brand-abc",
                                    "source_type": "funnel_artifact",
                                    "service_config": {"server_names": [], "https": False, "ports": []},
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    (tmp_path / "spec.json").write_text(
        json.dumps(
            {
                "new_spec": {
                    "instances": [
                        {
                            "name": "mos-ghc-1",
                            "workloads": [
                                {
                                    "name": "brand-funnels-brand-abc",
                                    "service_config": {"ports": [24123]},
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    captured: dict[str, str] = {}

    def fake_ensure_bunny_pull_zone(*, org_id: str, origin_url: str):
        captured["org_id"] = org_id
        captured["origin_url"] = origin_url
        return {
            "Id": 999,
            "Name": "workspace-123",
            "OriginUrl": origin_url,
            "Hostnames": [{"Value": "workspace-123.b-cdn.net"}],
        }

    monkeypatch.setattr(deploy_service, "_ensure_bunny_pull_zone", fake_ensure_bunny_pull_zone)

    output = deploy_service._reconcile_bunny_pull_zone_for_published_workload(
        org_id="workspace-123",
        workload_name="brand-funnels-brand-abc",
        plan_path=str(plan_path),
        instance_name="mos-ghc-1",
        requested_origin_ip=None,
        require_port_when_no_domains=True,
    )
    assert output["provider"] == "bunny"
    assert output["pull_zone"]["originUrl"] == "http://46.225.124.104:24123"
    assert output["pull_zone"]["workloadPort"] == 24123
    assert output["pull_zone"]["workloadPortSource"] == "spec"
    assert output["pull_zone"]["workloadPortPending"] is False
    assert captured == {
        "org_id": "workspace-123",
        "origin_url": "http://46.225.124.104:24123",
    }


def test_patch_workload_in_plan_assigns_and_preserves_org_scoped_port(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    plan_path = tmp_path / "plan-test.json"
    plan_path.write_text(
        json.dumps(
            {
                "new_spec": {
                    "instances": [
                        {
                            "name": "mos-ghc-1",
                            "workloads": [],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    create_patch = deploy_service.build_funnel_publication_workload_patch(
        workload_name="brand-funnels-1",
        client_id="f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
        upstream_base_url="https://moshq.app",
        upstream_api_base_url="https://moshq.app/api",
        server_names=[],
        https=False,
        destination_path="/opt/apps",
    )
    deploy_service.patch_workload_in_plan(
        org_id="workspace-123",
        workload_patch=create_patch,
        plan_path=str(plan_path),
        instance_name="mos-ghc-1",
        create_if_missing=True,
        in_place=True,
    )
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    first_workload = payload["new_spec"]["instances"][0]["workloads"][0]
    first_port = first_workload["service_config"]["ports"][0]
    assert 20000 <= first_port <= 29999

    update_patch = {
        "name": "brand-funnels-1",
        "service_config": {"server_names": [], "https": False, "ports": []},
    }
    deploy_service.patch_workload_in_plan(
        org_id="workspace-123",
        workload_patch=update_patch,
        plan_path=str(plan_path),
        instance_name="mos-ghc-1",
        create_if_missing=False,
        in_place=True,
    )
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    stable_port = payload["new_spec"]["instances"][0]["workloads"][0]["service_config"]["ports"][0]
    assert stable_port == first_port


def test_patch_workload_in_plan_assigns_different_ports_for_different_orgs(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    plan_path = tmp_path / "plan-test.json"
    plan_path.write_text(
        json.dumps(
            {
                "new_spec": {
                    "instances": [
                        {
                            "name": "mos-ghc-1",
                            "workloads": [],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    patch_a = deploy_service.build_funnel_publication_workload_patch(
        workload_name="brand-funnels-a",
        client_id="f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
        upstream_base_url="https://moshq.app",
        upstream_api_base_url="https://moshq.app/api",
        server_names=[],
        https=False,
        destination_path="/opt/apps",
    )
    patch_b = deploy_service.build_funnel_publication_workload_patch(
        workload_name="brand-funnels-b",
        client_id="3d8cf9b0-6e31-4f8f-9a56-9c94bbf2d68d",
        upstream_base_url="https://moshq.app",
        upstream_api_base_url="https://moshq.app/api",
        server_names=[],
        https=False,
        destination_path="/opt/apps",
    )

    deploy_service.patch_workload_in_plan(
        org_id="workspace-123",
        workload_patch=patch_a,
        plan_path=str(plan_path),
        instance_name="mos-ghc-1",
        create_if_missing=True,
        in_place=True,
    )
    deploy_service.patch_workload_in_plan(
        org_id="workspace-456",
        workload_patch=patch_b,
        plan_path=str(plan_path),
        instance_name="mos-ghc-1",
        create_if_missing=True,
        in_place=True,
    )

    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    workloads = payload["new_spec"]["instances"][0]["workloads"]
    ports_by_workload = {
        str(item["name"]): int(item["service_config"]["ports"][0])
        for item in workloads
    }
    assert ports_by_workload["brand-funnels-a"] != ports_by_workload["brand-funnels-b"]


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
