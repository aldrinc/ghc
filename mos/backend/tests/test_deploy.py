import asyncio
import base64
import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.auth.dependencies import AuthContext, get_current_user
from app.main import app
from app.db.models import (
    Client,
    Funnel,
    FunnelPage,
    FunnelPageVersion,
    FunnelPublication,
    FunnelPublicationPage,
    OrgDeployDomain,
    Product,
)
from app.services import deploy as deploy_service
from tests.conftest import TEST_ORG_ID


def test_deploy_plan_route_rejects_non_operator(api_client, monkeypatch):
    called = False

    def fake_latest_plan():
        nonlocal called
        called = True
        return {"path": "/tmp/plan.json"}

    monkeypatch.setattr(deploy_service, "get_latest_plan", fake_latest_plan)
    app.dependency_overrides[get_current_user] = lambda: AuthContext(
        user_id="member-user",
        org_id=str(TEST_ORG_ID),
        org_role="org:member",
    )

    resp = api_client.get("/deploy/plans/latest")

    assert resp.status_code == 403
    assert "Deploy access requires" in resp.json()["detail"]
    assert called is False


def test_deploy_apply_route_rejects_ops_without_apply_permission(api_client, monkeypatch):
    called = False

    async def fake_apply_plan(*, plan_path=None, workload_names=None):
        nonlocal called
        called = True
        return {"returncode": 0}

    monkeypatch.setattr(deploy_service, "apply_plan", fake_apply_plan)
    app.dependency_overrides[get_current_user] = lambda: AuthContext(
        user_id="ops-user",
        org_id=str(TEST_ORG_ID),
        org_role="org:ops",
    )

    resp = api_client.post("/deploy/plans/apply", json={})

    assert resp.status_code == 403
    assert "Deploy apply requires" in resp.json()["detail"]
    assert called is False


def test_deploy_apply_proxies_to_service(api_client, monkeypatch):
    async def fake_apply_plan(*, plan_path=None, workload_names=None):
        assert plan_path is None
        assert workload_names is None
        return {"returncode": 0, "plan_path": "/tmp/plan.json", "server_ips": {}, "live_url": None, "logs": ""}

    monkeypatch.setattr(deploy_service, "apply_plan", fake_apply_plan)

    resp = api_client.post("/deploy/plans/apply", json={})
    assert resp.status_code == 200
    assert resp.json()["returncode"] == 0


def test_deploy_apply_alias_works(api_client, monkeypatch):
    async def fake_apply_plan(*, plan_path=None, workload_names=None):
        return {"returncode": 0, "plan_path": "/tmp/plan.json", "server_ips": {}, "live_url": None, "logs": ""}

    monkeypatch.setattr(deploy_service, "apply_plan", fake_apply_plan)

    resp = api_client.post("/deploy/apply", json={})
    assert resp.status_code == 200


def test_deploy_apply_async_starts_scoped_job(api_client, monkeypatch):
    captured: dict[str, object] = {}

    def fake_start_apply_plan_job(*, plan_path=None, workload_names=None, access_urls=None):
        captured["plan_path"] = plan_path
        captured["workload_names"] = workload_names
        captured["access_urls"] = access_urls
        return {
            "id": "job-123",
            "status": "queued",
            "plan_path": "/tmp/plan.json",
            "workload_names": ["brand-funnels-ember"],
        }

    monkeypatch.setattr(deploy_service, "start_apply_plan_job", fake_start_apply_plan_job)

    resp = api_client.post(
        "/deploy/plans/apply-async",
        json={"plan_path": "/tmp/plan.json", "workload_names": ["brand-funnels-ember"]},
    )
    assert resp.status_code == 200
    assert captured == {
        "plan_path": "/tmp/plan.json",
        "workload_names": ["brand-funnels-ember"],
        "access_urls": None,
    }
    assert resp.json() == {
        "jobId": "job-123",
        "status": "queued",
        "planPath": "/tmp/plan.json",
        "statusPath": "/deploy/plans/apply-jobs/job-123",
        "workloadNames": ["brand-funnels-ember"],
    }


def test_deploy_apply_async_alias_works(api_client, monkeypatch):
    monkeypatch.setattr(
        deploy_service,
        "start_apply_plan_job",
        lambda **_: {
            "id": "job-123",
            "status": "queued",
            "plan_path": "/tmp/plan.json",
            "workload_names": [],
        },
    )

    resp = api_client.post("/deploy/apply-async", json={})
    assert resp.status_code == 200
    assert resp.json()["jobId"] == "job-123"


def test_get_apply_plan_job_route_returns_status(api_client, monkeypatch):
    monkeypatch.setattr(
        deploy_service,
        "get_apply_plan_job",
        lambda *, job_id: {"id": job_id, "status": "running", "plan_path": "/tmp/plan.json"},
    )

    resp = api_client.get("/deploy/plans/apply-jobs/job-123")
    assert resp.status_code == 200
    assert resp.json() == {"id": "job-123", "status": "running", "plan_path": "/tmp/plan.json"}


def test_deploy_apply_forwards_workload_names(api_client, monkeypatch):
    async def fake_apply_plan(*, plan_path=None, workload_names=None):
        assert plan_path == "/tmp/plan.json"
        assert workload_names == ["brand-funnels-abc", "brand-funnels-def"]
        return {"returncode": 0, "plan_path": "/tmp/plan.json", "server_ips": {}, "live_url": None, "logs": ""}

    monkeypatch.setattr(deploy_service, "apply_plan", fake_apply_plan)

    resp = api_client.post(
        "/deploy/plans/apply",
        json={"plan_path": "/tmp/plan.json", "workload_names": ["brand-funnels-abc", "brand-funnels-def"]},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_apply_plan_scopes_materialization_and_cli_to_selected_workload(tmp_path, monkeypatch):
    cloudhand_dir = tmp_path / "cloudhand"
    terraform_dir = tmp_path / "terraform"
    cloudhand_dir.mkdir()
    plan_path = cloudhand_dir / "plan.json"
    plan_path.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("HCLOUD_TOKEN", "test-token")
    monkeypatch.setattr(deploy_service, "_cloudhand_dir", lambda: cloudhand_dir)
    monkeypatch.setattr(deploy_service, "_terraform_dir", lambda: terraform_dir)
    monkeypatch.setattr(deploy_service, "_resolve_terraform_bin", lambda: "terraform")

    captured: dict[str, object] = {}

    def fake_materialize(*, plan_file, workload_names=None):
        captured["materialize_plan_file"] = str(plan_file)
        captured["materialize_workload_names"] = workload_names
        return plan_file

    class FakeStdout:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class FakeProc:
        def __init__(self):
            self.stdout = FakeStdout()
            self.returncode = 0

        async def wait(self):
            return self.returncode

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["subprocess_args"] = list(args)
        captured["subprocess_kwargs"] = kwargs
        return FakeProc()

    monkeypatch.setattr(deploy_service, "_materialize_funnel_artifacts_for_apply", fake_materialize)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await deploy_service.apply_plan(
        plan_path=str(plan_path),
        workload_names=["brand-funnels-tenor", "brand-funnels-tenor"],
    )

    assert result["returncode"] == 0
    assert captured["materialize_workload_names"] == {"brand-funnels-tenor"}
    subprocess_args = captured["subprocess_args"]
    assert "--workload-name" in subprocess_args
    assert subprocess_args.count("--workload-name") == 1
    assert subprocess_args[-2:] == ["--workload-name", "brand-funnels-tenor"]


@pytest.mark.asyncio
async def test_run_apply_plan_job_forwards_scoped_workload_names(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))

    captured: dict[str, object] = {}

    async def fake_apply_plan(*, plan_path=None, workload_names=None):
        captured["plan_path"] = plan_path
        captured["workload_names"] = workload_names
        return {
            "returncode": 0,
            "plan_path": "/tmp/plan.json",
            "materialized_plan_path": "/tmp/plan.materialized.json",
            "server_ips": {"ubuntu-4gb-hel1-2": "135.181.93.244"},
            "live_url": "http://135.181.93.244",
            "logs": "",
        }

    monkeypatch.setattr(deploy_service, "apply_plan", fake_apply_plan)

    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    job_path = jobs_dir / "job-123.json"
    job_path.write_text(
        json.dumps(
            {
                "id": "job-123",
                "status": "queued",
                "created_at": "2026-04-22T00:00:00+00:00",
                "started_at": None,
                "finished_at": None,
                "plan_path": "/tmp/plan.json",
                "workload_names": ["brand-funnels-ember"],
                "access_urls": [],
                "result": None,
                "error": None,
            }
        ),
        encoding="utf-8",
    )

    await deploy_service._run_apply_plan_job("job-123")

    job = json.loads(job_path.read_text(encoding="utf-8"))
    assert captured == {
        "plan_path": "/tmp/plan.json",
        "workload_names": ["brand-funnels-ember"],
    }
    assert job["status"] == "succeeded"
    assert job["result"]["materialized_plan_path"] == "/tmp/plan.materialized.json"


def test_deploy_latest_plan_404_on_missing(api_client, monkeypatch):
    def fake_latest_plan():
        raise deploy_service.DeployError("No plan found.")

    monkeypatch.setattr(deploy_service, "get_latest_plan", fake_latest_plan)

    resp = api_client.get("/deploy/plans/latest")
    assert resp.status_code == 404


def test_patch_workload_endpoint_keeps_workload_scoped_deploy_domains(api_client, db_session, monkeypatch):
    db_session.add(
        Client(
            id=UUID("00000000-0000-0000-0000-000000000123"),
            org_id=UUID("00000000-0000-0000-0000-000000000001"),
            name="Workspace 123",
        )
    )
    db_session.commit()
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
        _ = org_id
        _ = workload_patch
        _ = plan_path
        _ = instance_name
        _ = create_if_missing
        _ = in_place
        captured["workload_patch"] = workload_patch
        return {
            "status": "ok",
            "base_plan_path": "/tmp/plan.json",
            "updated_plan_path": "/tmp/plan.json",
            "workload_name": "brand-funnels-test",
            "updated_count": 1,
        }

    monkeypatch.setattr(deploy_service, "patch_workload_in_plan", fake_patch_workload_in_plan)
    monkeypatch.setattr(
        deploy_service,
        "get_workload_workspace_id_from_plan",
        lambda *, workload_name, plan_path=None, instance_name=None: "00000000-0000-0000-0000-000000000123",
    )

    resp = api_client.post(
        "/deploy/plans/workloads?plan_path=/tmp/plan.json",
        json={
            "name": "brand-funnels-test",
            "workspace_server_names": [
                "Offers.Example.com",
                "offers.example.com",
                "  ",
                "Landing.example.com",
            ],
            "service_config": {
                "server_names": [],
                "https": True,
            },
            "source_ref": {"client_id": "00000000-0000-0000-0000-000000000123"},
        },
    )
    assert resp.status_code == 200

    workload_patch = captured["workload_patch"]
    assert workload_patch["workspace_server_names"] == [
        "offers.example.com",
        "landing.example.com",
    ]
    hostnames = db_session.scalars(
        select(OrgDeployDomain.hostname).order_by(OrgDeployDomain.hostname.asc())
    ).all()
    assert hostnames == []


def test_patch_workload_endpoint_clears_plan_domains_when_configuring_bunny(api_client, db_session, monkeypatch):
    workspace_id = UUID("00000000-0000-0000-0000-000000000124")
    db_session.add(
        Client(
            id=workspace_id,
            org_id=UUID("00000000-0000-0000-0000-000000000001"),
            name="Workspace 124",
        )
    )
    db_session.commit()

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
        client_id: str,
        workload_name: str,
        plan_path: str | None,
        instance_name: str | None,
        requested_origin_ip: str | None = None,
        server_names: list[str] | None = None,
    ):
        captured["cdn_server_names"] = server_names
        captured["client_id"] = client_id
        return {"provider": "bunny", "pull_zone": {"name": "workspace-123"}}

    monkeypatch.setattr(deploy_service, "patch_workload_in_plan", fake_patch_workload_in_plan)
    monkeypatch.setattr(
        deploy_service,
        "configure_bunny_pull_zone_for_workload",
        fake_configure_bunny_pull_zone_for_workload,
    )
    monkeypatch.setattr(
        deploy_service,
        "get_workload_workspace_id_from_plan",
        lambda *, workload_name, plan_path=None, instance_name=None: str(workspace_id),
    )

    resp = api_client.post(
        "/deploy/plans/workloads?plan_path=/tmp/plan.json&configure_bunny_pull_zone=true",
        json={
            "name": "brand-funnels-test",
            "service_config": {
                "server_names": ["shop.example.com"],
                "https": True,
            },
            "workspace_server_names": ["shop.example.com"],
            "source_ref": {"client_id": str(workspace_id)},
        },
    )
    assert resp.status_code == 200

    workload_patch = captured["workload_patch"]
    assert workload_patch["service_config"]["server_names"] == []
    assert workload_patch["service_config"]["https"] is False
    assert workload_patch["workspace_server_names"] == ["shop.example.com"]
    assert captured["cdn_server_names"] == ["shop.example.com"]
    assert captured["client_id"] == str(workspace_id)


def test_get_workload_domains_includes_workload_scoped_server_names_from_plan(
    api_client,
    db_session,
    auth_context,
    monkeypatch,
):
    org_id = UUID(auth_context.org_id)
    client_id = UUID("00000000-0000-0000-0000-000000000123")
    db_session.add(Client(id=client_id, org_id=org_id, name="Workspace"))
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
            "workspace_server_names": ["offers.example.com"],
            "https": False,
        }

    monkeypatch.setattr(
        deploy_service,
        "get_workload_domains_from_plan",
        fake_get_workload_domains_from_plan,
    )
    monkeypatch.setattr(
        deploy_service,
        "get_workload_workspace_id_from_plan",
        lambda *, workload_name, plan_path=None, instance_name=None: str(client_id),
    )

    resp = api_client.get(
        f"/deploy/plans/workloads/domains?workload_name=brand-funnels-test&workspace_id={client_id}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["workspace_server_names"] == ["offers.example.com"]
    assert body["workspace_id"] == str(client_id)
    assert body["server_names"] == []


def test_get_workload_domains_falls_back_to_workspace_repo_when_plan_has_no_scoped_domains(
    api_client,
    db_session,
    auth_context,
    monkeypatch,
):
    org_id = UUID(auth_context.org_id)
    client_id = UUID("00000000-0000-0000-0000-000000000126")
    db_session.add(Client(id=client_id, org_id=org_id, name="Workspace"))
    db_session.add(OrgDeployDomain(org_id=org_id, client_id=client_id, hostname="offers.example.com"))
    db_session.commit()

    monkeypatch.setattr(
        deploy_service,
        "get_workload_domains_from_plan",
        lambda *, workload_name, plan_path=None, instance_name=None: {
            "plan_path": "/tmp/plan.json",
            "workload_found": True,
            "server_names": [],
            "https": False,
        },
    )
    monkeypatch.setattr(
        deploy_service,
        "get_workload_workspace_id_from_plan",
        lambda *, workload_name, plan_path=None, instance_name=None: str(client_id),
    )

    resp = api_client.get(
        f"/deploy/plans/workloads/domains?workload_name=brand-funnels-test&workspace_id={client_id}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["workspace_server_names"] == ["offers.example.com"]
    assert body["workspace_scope_error"] is None


def test_get_workload_domains_does_not_fall_back_when_plan_clears_scoped_domains(
    api_client,
    db_session,
    auth_context,
    monkeypatch,
):
    org_id = UUID(auth_context.org_id)
    client_id = UUID("00000000-0000-0000-0000-000000000127")
    db_session.add(Client(id=client_id, org_id=org_id, name="Workspace"))
    db_session.add(OrgDeployDomain(org_id=org_id, client_id=client_id, hostname="offers.example.com"))
    db_session.commit()

    monkeypatch.setattr(
        deploy_service,
        "get_workload_domains_from_plan",
        lambda *, workload_name, plan_path=None, instance_name=None: {
            "plan_path": "/tmp/plan.json",
            "workload_found": True,
            "server_names": [],
            "workspace_server_names": [],
            "https": False,
        },
    )
    monkeypatch.setattr(
        deploy_service,
        "get_workload_workspace_id_from_plan",
        lambda *, workload_name, plan_path=None, instance_name=None: str(client_id),
    )

    resp = api_client.get(
        f"/deploy/plans/workloads/domains?workload_name=brand-funnels-test&workspace_id={client_id}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["workspace_server_names"] == []
    assert body["workspace_scope_error"] is None


def test_get_workload_domains_reports_legacy_org_scoped_domains(
    api_client,
    db_session,
    auth_context,
    monkeypatch,
):
    org_id = UUID(auth_context.org_id)
    client_id = UUID("00000000-0000-0000-0000-000000000125")
    db_session.add(Client(id=client_id, org_id=org_id, name="Workspace"))
    db_session.add(OrgDeployDomain(org_id=org_id, client_id=None, hostname="legacy.example.com"))
    db_session.commit()

    monkeypatch.setattr(
        deploy_service,
        "get_workload_domains_from_plan",
        lambda *, workload_name, plan_path=None, instance_name=None: {
            "plan_path": "/tmp/plan.json",
            "workload_found": True,
            "server_names": [],
            "https": False,
        },
    )
    monkeypatch.setattr(
        deploy_service,
        "get_workload_workspace_id_from_plan",
        lambda *, workload_name, plan_path=None, instance_name=None: str(client_id),
    )

    resp = api_client.get(
        f"/deploy/plans/workloads/domains?workload_name=brand-funnels-test&workspace_id={client_id}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["workspace_server_names"] == []
    assert body["workspace_scope_error"]


def test_get_workload_domains_does_not_inherit_workspace_domains_for_missing_workload(
    api_client,
    db_session,
    auth_context,
    monkeypatch,
):
    org_id = UUID(auth_context.org_id)
    client_id = UUID("00000000-0000-0000-0000-000000000128")
    db_session.add(Client(id=client_id, org_id=org_id, name="Workspace"))
    db_session.add(OrgDeployDomain(org_id=org_id, client_id=client_id, hostname="offers.example.com"))
    db_session.commit()

    monkeypatch.setattr(
        deploy_service,
        "get_workload_domains_from_plan",
        lambda *, workload_name, plan_path=None, instance_name=None: {
            "plan_path": "/tmp/plan.json",
            "workload_found": False,
            "server_names": [],
            "https": False,
        },
    )

    resp = api_client.get(
        f"/deploy/plans/workloads/domains?workload_name=brand-funnels-test&workspace_id={client_id}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["workspace_server_names"] == []
    assert body["workspace_scope_error"] is None


def test_get_workload_domains_from_plan_reads_workload_scoped_domains(tmp_path, monkeypatch):
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "new_spec": {
                    "instances": [
                        {
                            "name": "instance-1",
                            "workloads": [
                                {
                                    "name": "brand-funnels-test",
                                    "workspace_server_names": [
                                        "Offers.Example.com",
                                        "offers.example.com",
                                        "landing.example.com",
                                    ],
                                    "service_config": {
                                        "server_names": [],
                                        "https": False,
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

    monkeypatch.setattr(deploy_service, "_assert_under_cloudhand", lambda path: path)

    result = deploy_service.get_workload_domains_from_plan(
        workload_name="brand-funnels-test",
        plan_path=str(plan_path),
    )

    assert result["workspace_server_names"] == [
        "offers.example.com",
        "landing.example.com",
    ]


def _build_identity_audit_payload_fixture(db_session, *, org_id: UUID, monkeypatch):
    client_id = uuid4()
    product_id = uuid4()
    funnel_id = uuid4()
    page_id = uuid4()
    version_id = uuid4()
    publication_id = uuid4()
    route_slug = "identity-audit-funnel"
    product_slug = str(product_id).split("-")[0]

    db_session.add(Client(id=client_id, org_id=org_id, name="Identity Client"))
    db_session.add(
        Product(
            id=product_id,
            org_id=org_id,
            client_id=client_id,
            title="Identity Product",
        )
    )
    db_session.flush()
    funnel = Funnel(
        id=funnel_id,
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        name="Identity Funnel",
        route_slug=route_slug,
    )
    db_session.add(funnel)
    db_session.add(
        FunnelPage(
            id=page_id,
            funnel_id=funnel_id,
            name="Sales Page",
            slug="sales-page",
            template_id="sales-pdp",
        )
    )
    db_session.add(
        FunnelPageVersion(
            id=version_id,
            page_id=page_id,
            puck_data={"root": {"props": {"title": "Sales Page"}}, "content": []},
        )
    )
    db_session.add(
        FunnelPublication(
            id=publication_id,
            funnel_id=funnel_id,
            entry_page_id=page_id,
            created_by="codex",
        )
    )
    db_session.add(
        FunnelPublicationPage(
            publication_id=publication_id,
            page_id=page_id,
            page_version_id=version_id,
            slug_at_publish="sales-page",
            title_at_publish="Sales Page",
        )
    )
    db_session.flush()
    funnel.entry_page_id = page_id
    funnel.active_publication_id = publication_id
    db_session.commit()

    monkeypatch.setattr(deploy_service, "build_public_page_metadata_for_context", lambda **_: {"title": "Sales Page"})
    payload = deploy_service.build_client_funnel_runtime_artifact_payload(
        session=db_session,
        org_id=str(org_id),
        client_id=str(client_id),
        updated_from_funnel_id=str(funnel_id),
        updated_from_publication_id=str(publication_id),
    )
    page_payload = payload["products"][product_slug]["funnels"][route_slug]["pages"]["sales-page"]
    return payload, {
        "funnel_id": str(funnel_id),
        "publication_id": str(publication_id),
        "page_id": str(page_id),
        "product_slug": product_slug,
        "route_slug": route_slug,
        "page_payload": page_payload,
    }


def test_validate_funnel_artifact_identity_accepts_built_payload(db_session, auth_context, monkeypatch):
    org_id = UUID(auth_context.org_id)
    payload, fixture = _build_identity_audit_payload_fixture(
        db_session,
        org_id=org_id,
        monkeypatch=monkeypatch,
    )

    audit = deploy_service.validate_funnel_artifact_identity(
        session=db_session,
        org_id=str(org_id),
        artifact_payload=payload,
    )

    assert audit["status"] == "passed"
    assert audit["funnels"][0]["funnelId"] == fixture["funnel_id"]
    assert audit["funnels"][0]["publicationId"] == fixture["publication_id"]
    assert audit["funnels"][0]["pages"] == [
        {"pageId": fixture["page_id"], "slug": "sales-page", "stage": "sales"}
    ]


def test_validate_funnel_artifact_identity_rejects_page_map_drift(db_session, auth_context, monkeypatch):
    org_id = UUID(auth_context.org_id)
    payload, fixture = _build_identity_audit_payload_fixture(
        db_session,
        org_id=org_id,
        monkeypatch=monkeypatch,
    )
    fixture["page_payload"]["pageMap"][str(uuid4())] = "ghost-page"

    with pytest.raises(deploy_service.DeployError, match="pageMap does not match publication pages"):
        deploy_service.validate_funnel_artifact_identity(
            session=db_session,
            org_id=str(org_id),
            artifact_payload=payload,
        )


def test_validate_funnel_artifact_identity_rejects_stage_map_key_drift(
    db_session,
    auth_context,
    monkeypatch,
):
    org_id = UUID(auth_context.org_id)
    payload, fixture = _build_identity_audit_payload_fixture(
        db_session,
        org_id=org_id,
        monkeypatch=monkeypatch,
    )
    fixture["page_payload"]["pageStageMap"][str(uuid4())] = "sales"

    with pytest.raises(deploy_service.DeployError, match="pageStageMap keys differ from pageMap keys"):
        deploy_service.validate_funnel_artifact_identity(
            session=db_session,
            org_id=str(org_id),
            artifact_payload=payload,
        )


def test_runtime_artifact_payload_preserves_published_page_slug(db_session, auth_context, monkeypatch):
    org_id = UUID(auth_context.org_id)
    client_id = uuid4()
    product_id = uuid4()
    funnel_id = uuid4()
    page_id = uuid4()
    version_id = uuid4()
    publication_id = uuid4()
    product_slug = str(product_id).split("-")[0]

    db_session.add(Client(id=client_id, org_id=org_id, name="Test Client"))
    db_session.add(
        Product(
            id=product_id,
            org_id=org_id,
            client_id=client_id,
            title="Ember Gummies",
        )
    )
    db_session.flush()

    funnel = Funnel(
        id=funnel_id,
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        name="EMBER Funnel",
        route_slug="ember-brain-clarity-protocol-imported-template-3",
    )
    db_session.add(funnel)
    db_session.add(
        FunnelPage(
            id=page_id,
            funnel_id=funnel_id,
            name="Sales Page",
            slug="sales-page",
            template_id="sales-pdp",
        )
    )
    db_session.add(
        FunnelPageVersion(
            id=version_id,
            page_id=page_id,
            puck_data={"root": {"props": {"title": "Sales Page"}}, "content": []},
        )
    )
    db_session.add(
        FunnelPublication(
            id=publication_id,
            funnel_id=funnel_id,
            entry_page_id=page_id,
            created_by="codex",
        )
    )
    db_session.add(
        FunnelPublicationPage(
            publication_id=publication_id,
            page_id=page_id,
            page_version_id=version_id,
            slug_at_publish="sales-page",
            title_at_publish="Sales Page",
        )
    )
    db_session.flush()

    funnel.entry_page_id = page_id
    funnel.active_publication_id = publication_id
    db_session.commit()

    monkeypatch.setattr(deploy_service, "build_public_page_metadata_for_context", lambda **_: {"title": "Sales Page"})

    payload = deploy_service.build_client_funnel_runtime_artifact_payload(
        session=db_session,
        org_id=str(org_id),
        client_id=str(client_id),
        updated_from_funnel_id=str(funnel_id),
        updated_from_publication_id=str(publication_id),
    )

    funnel_payload = payload["products"][product_slug]["funnels"]["ember-brain-clarity-protocol-imported-template-3"]
    assert funnel_payload["meta"]["entrySlug"] == "sales-page"
    assert funnel_payload["meta"]["pages"] == [{"pageId": str(page_id), "slug": "sales-page"}]
    assert "sales-page" in funnel_payload["pages"]
    assert "sales" not in funnel_payload["pages"]


def test_runtime_artifact_payload_preserves_multiple_presales_page_slugs(
    db_session, auth_context, monkeypatch
):
    org_id = UUID(auth_context.org_id)
    client_id = uuid4()
    product_id = uuid4()
    funnel_id = uuid4()
    publication_id = uuid4()
    product_slug = str(product_id).split("-")[0]
    page_specs = [
        ("page-main", "presales"),
        ("page-angle-one", "01-personal-transformation"),
        ("page-angle-two", "02-agitation"),
    ]

    db_session.add(Client(id=client_id, org_id=org_id, name="Test Client"))
    db_session.add(
        Product(
            id=product_id,
            org_id=org_id,
            client_id=client_id,
            title="Ember Gummies",
        )
    )
    db_session.flush()
    funnel = Funnel(
        id=funnel_id,
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        name="EMBER Funnel",
        route_slug="ember-brain-clarity-protocol-imported-template-3",
    )
    db_session.add(funnel)
    db_session.flush()

    first_page_id: UUID | None = None
    for page_name, slug in page_specs:
        page_id = uuid4()
        version_id = uuid4()
        first_page_id = first_page_id or page_id
        db_session.add(
            FunnelPage(
                id=page_id,
                funnel_id=funnel_id,
                name=page_name,
                slug=slug,
                template_id="pre-sales-listicle",
            )
        )
        db_session.add(
            FunnelPageVersion(
                id=version_id,
                page_id=page_id,
                puck_data={"root": {"props": {"title": page_name}}, "content": []},
            )
        )
        db_session.add(
            FunnelPublicationPage(
                publication_id=publication_id,
                page_id=page_id,
                page_version_id=version_id,
                slug_at_publish=slug,
                title_at_publish=page_name,
            )
        )

    db_session.add(
        FunnelPublication(
            id=publication_id,
            funnel_id=funnel_id,
            entry_page_id=first_page_id,
            created_by="codex",
        )
    )
    db_session.flush()

    funnel.entry_page_id = first_page_id
    funnel.active_publication_id = publication_id
    db_session.commit()

    monkeypatch.setattr(deploy_service, "build_public_page_metadata_for_context", lambda **_: {"title": "Page"})

    payload = deploy_service.build_client_funnel_runtime_artifact_payload(
        session=db_session,
        org_id=str(org_id),
        client_id=str(client_id),
        updated_from_funnel_id=str(funnel_id),
        updated_from_publication_id=str(publication_id),
    )

    funnel_payload = payload["products"][product_slug]["funnels"]["ember-brain-clarity-protocol-imported-template-3"]
    assert set(funnel_payload["pages"]) == {
        "presales",
        "01-personal-transformation",
        "02-agitation",
    }
    assert funnel_payload["meta"]["entrySlug"] == "presales"
    assert {page["slug"] for page in funnel_payload["meta"]["pages"]} == {
        "presales",
        "01-personal-transformation",
        "02-agitation",
    }


def test_build_bunny_pull_zone_name_uses_workload_name():
    name = deploy_service._build_bunny_pull_zone_name(
        client_id="Workspace_123",
        workload_name="brand-funnels-workspace-123-funnel-456",
    )
    assert name == "brand-funnels-workspace-123-funnel-456"


def test_build_client_funnel_runtime_artifact_payload_prefers_explicit_publication_override(
    db_session, monkeypatch
):
    org_id = TEST_ORG_ID
    client_id = uuid4()
    product_id = uuid4()
    funnel_id = uuid4()
    page_id = uuid4()
    version_id = uuid4()
    old_publication_id = uuid4()
    new_publication_id = uuid4()
    product_slug = str(product_id).split("-")[0]

    db_session.add(Client(id=client_id, org_id=org_id, name="Test Client"))
    db_session.add(
        Product(
            id=product_id,
            org_id=org_id,
            client_id=client_id,
            title="Ember Gummies",
        )
    )
    db_session.flush()

    funnel = Funnel(
        id=funnel_id,
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        name="EMBER Funnel",
        route_slug="ember-brain-clarity-protocol-imported-template-3",
    )
    db_session.add(funnel)
    db_session.add(
        FunnelPage(
            id=page_id,
            funnel_id=funnel_id,
            name="Sales Page",
            slug="sales-page",
            template_id="sales-pdp",
        )
    )
    db_session.add(
        FunnelPageVersion(
            id=version_id,
            page_id=page_id,
            puck_data={"root": {"props": {"title": "Sales Page"}}, "content": []},
        )
    )
    db_session.add(
        FunnelPublication(
            id=old_publication_id,
            funnel_id=funnel_id,
            entry_page_id=page_id,
            created_by="codex",
        )
    )
    db_session.add(
        FunnelPublicationPage(
            publication_id=old_publication_id,
            page_id=page_id,
            page_version_id=version_id,
            slug_at_publish="old-sales-page",
            title_at_publish="Old Sales Page",
        )
    )
    db_session.add(
        FunnelPublication(
            id=new_publication_id,
            funnel_id=funnel_id,
            entry_page_id=page_id,
            created_by="codex",
        )
    )
    db_session.add(
        FunnelPublicationPage(
            publication_id=new_publication_id,
            page_id=page_id,
            page_version_id=version_id,
            slug_at_publish="sales-page",
            title_at_publish="Sales Page",
        )
    )
    db_session.flush()

    funnel.entry_page_id = page_id
    funnel.active_publication_id = old_publication_id
    db_session.commit()

    monkeypatch.setattr(
        deploy_service, "build_public_page_metadata_for_context", lambda **_: {"title": "Sales Page"}
    )

    payload = deploy_service.build_client_funnel_runtime_artifact_payload(
        session=db_session,
        org_id=str(org_id),
        client_id=str(client_id),
        updated_from_funnel_id=str(funnel_id),
        updated_from_publication_id=str(new_publication_id),
        publication_id_overrides={str(funnel_id): str(new_publication_id)},
    )

    funnel_payload = payload["products"][product_slug]["funnels"]["ember-brain-clarity-protocol-imported-template-3"]
    sales_page = funnel_payload["pages"]["sales-page"]

    assert funnel_payload["meta"]["publicationId"] == str(new_publication_id)
    assert funnel_payload["meta"]["entrySlug"] == "sales-page"
    assert sales_page["publicationId"] == str(new_publication_id)


def test_resolve_publish_job_workspace_server_names_prefers_workload_scoped_domains(
):
    result = deploy_service._resolve_publish_job_workspace_server_names(
        session=None,
        org_id=str(uuid4()),
        workload_client_id=str(uuid4()),
        workload_patch={
            "workspace_server_names": [
                "Shop.Example.com",
                "shop.example.com",
            ]
        },
    )

    assert result == ["shop.example.com"]


def test_resolve_publish_job_workspace_server_names_falls_back_to_saved_workspace_domains_when_empty(
    monkeypatch,
):
    class DummyRepo:
        def __init__(self, session):
            self.session = session

        def list_hostnames(self, *, org_id: str, client_id: str, strict: bool = True) -> list[str]:
            _ = self.session
            _ = strict
            assert org_id == "org-123"
            assert client_id == "client-123"
            return ["shop.shopemberco.com"]

    monkeypatch.setattr(
        "app.db.repositories.org_deploy_domains.OrgDeployDomainsRepository",
        DummyRepo,
    )

    result = deploy_service._resolve_publish_job_workspace_server_names(
        session=object(),
        org_id="org-123",
        workload_client_id="client-123",
        workload_patch={"workspace_server_names": []},
    )

    assert result == ["shop.shopemberco.com"]


@pytest.mark.asyncio
async def test_apply_plan_times_out_stuck_cloudhand_process(tmp_path, monkeypatch):
    cloudhand_dir = tmp_path / "cloudhand"
    terraform_dir = tmp_path / "terraform"
    cloudhand_dir.mkdir()
    terraform_dir.mkdir()
    plan_path = cloudhand_dir / "plan.json"
    plan_path.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("HCLOUD_TOKEN", "test-token")
    monkeypatch.setenv("DEPLOY_APPLY_TIMEOUT_SECONDS", "0.01")
    monkeypatch.setattr(deploy_service, "_cloudhand_dir", lambda: cloudhand_dir)
    monkeypatch.setattr(deploy_service, "_terraform_dir", lambda: terraform_dir)
    monkeypatch.setattr(
        deploy_service,
        "_materialize_funnel_artifacts_for_apply",
        lambda *, plan_file, workload_names=None: plan_file,
    )
    monkeypatch.setattr(deploy_service, "_resolve_terraform_bin", lambda: "terraform")

    class FakeStdout:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class FakeProc:
        def __init__(self):
            self.stdout = FakeStdout()
            self.returncode = None
            self.pid = 4242
            self._done = asyncio.Event()

        async def wait(self):
            await self._done.wait()
            return self.returncode

    fake_proc = FakeProc()

    async def fake_create_subprocess_exec(*args, **kwargs):
        _ = args
        _ = kwargs
        return fake_proc

    terminated: list[tuple[int, int]] = []

    def fake_killpg(pid: int, sig: int):
        terminated.append((pid, sig))
        fake_proc.returncode = -9
        fake_proc._done.set()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(deploy_service.os, "killpg", fake_killpg)

    with pytest.raises(deploy_service.DeployError, match="timed out"):
        await deploy_service.apply_plan(plan_path=str(plan_path))

    assert terminated


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


def test_request_bunny_pull_zone_certificate_uses_global_endpoint(monkeypatch):
    captured: dict[str, str] = {}

    def fake_bunny_api_request(*, method: str, path: str, payload: dict | None = None):
        captured["method"] = method
        captured["path"] = path
        _ = payload
        return {"Success": True}

    monkeypatch.setattr(deploy_service, "_bunny_api_request", fake_bunny_api_request)

    response = deploy_service._request_bunny_pull_zone_certificate(
        zone_id=5365591,
        hostname="shop.moshq.app",
    )

    assert response == {"Success": True}
    assert captured == {
        "method": "GET",
        "path": "/pullzone/loadFreeCertificate?hostname=shop.moshq.app",
    }


def test_ensure_bunny_pull_zone_creates_when_missing(monkeypatch):
    calls: list[tuple[str, str, dict | None]] = []

    def fake_bunny_api_request(*, method: str, path: str, payload: dict | None = None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/pullzone":
            return {"Items": []}
        if method == "POST" and path == "/pullzone":
            assert payload == {
                "Name": "brand-funnels-workspace-123-funnel-456",
                "OriginUrl": "http://46.225.124.104",
            }
            return {
                "Id": 123,
                "Name": "brand-funnels-workspace-123-funnel-456",
                "OriginUrl": "http://46.225.124.104",
                "Hostnames": [{"Value": "brand-funnels-workspace-123-funnel-456.b-cdn.net"}],
            }
        raise AssertionError(f"Unexpected Bunny API call: method={method}, path={path}, payload={payload}")

    monkeypatch.setattr(deploy_service, "_bunny_api_request", fake_bunny_api_request)
    zone = deploy_service._ensure_bunny_pull_zone(
        client_id="workspace-123",
        workload_name="brand-funnels-workspace-123-funnel-456",
        origin_url="http://46.225.124.104",
    )
    urls = deploy_service._extract_bunny_pull_zone_access_urls(zone)

    assert zone["Id"] == 123
    assert urls == ["https://brand-funnels-workspace-123-funnel-456.b-cdn.net/"]
    assert calls[0] == ("GET", "/pullzone", None)
    assert calls[1][0] == "POST"
    assert calls[1][1] == "/pullzone"


def test_ensure_bunny_pull_zone_adopts_existing_zone_from_custom_domain(monkeypatch):
    monkeypatch.setattr(deploy_service, "_find_bunny_pull_zone_by_name", lambda *, zone_name: None)
    monkeypatch.setattr(
        deploy_service,
        "_resolve_existing_bunny_pull_zone_for_hostnames",
        lambda *, server_names: {
            "Id": 5692458,
            "Name": "brand-funnels-486a8718-18ac0fe1",
            "OriginUrl": "http://46.225.124.104:22001",
            "Hostnames": [
                {"Value": "brand-funnels-486a8718-18ac0fe1.b-cdn.net"},
                {"Value": "shop.shopemberco.com"},
            ],
        },
    )

    captured: dict[str, object] = {}

    def fake_bunny_api_request(*, method: str, path: str, payload: dict | None = None):
        captured["method"] = method
        captured["path"] = path
        captured["payload"] = payload
        return {
            "Id": 5692458,
            "Name": "brand-funnels-486a8718-18ac0fe1",
            "OriginUrl": "http://46.225.124.104:22689",
            "Hostnames": [
                {"Value": "brand-funnels-486a8718-18ac0fe1.b-cdn.net"},
                {"Value": "shop.shopemberco.com"},
            ],
        }

    monkeypatch.setattr(deploy_service, "_bunny_api_request", fake_bunny_api_request)

    zone = deploy_service._ensure_bunny_pull_zone(
        client_id="486a8718-a2e8-4ff9-8c02-1f11ae33b8bc",
        workload_name="brand-funnels-070d6cf7-18ac0fe1",
        origin_url="http://46.225.124.104:22689",
        server_names=["shop.shopemberco.com"],
    )

    assert zone["Id"] == 5692458
    assert zone["Name"] == "brand-funnels-486a8718-18ac0fe1"
    assert captured == {
        "method": "POST",
        "path": "/pullzone/5692458",
        "payload": {"OriginUrl": "http://46.225.124.104:22689"},
    }


def test_resolve_existing_bunny_pull_zone_for_hostnames_errors_when_domains_span_multiple_zones(
    monkeypatch,
):
    zone_map = {
        "shop-one.example.com": {
            "Id": 100,
            "Name": "zone-one",
            "Hostnames": [{"Value": "shop-one.example.com"}],
        },
        "shop-two.example.com": {
            "Id": 200,
            "Name": "zone-two",
            "Hostnames": [{"Value": "shop-two.example.com"}],
        },
    }
    monkeypatch.setattr(
        deploy_service,
        "_find_bunny_pull_zone_by_hostname",
        lambda *, hostname: zone_map.get(hostname),
    )

    with pytest.raises(deploy_service.DeployError, match="multiple pull zones"):
        deploy_service._resolve_existing_bunny_pull_zone_for_hostnames(
            server_names=["shop-one.example.com", "shop-two.example.com"],
        )


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


def test_purge_bunny_pull_zone_cache_calls_expected_endpoint(monkeypatch):
    captured: dict[str, object] = {}

    def fake_bunny_api_request(*, method: str, path: str, payload: dict | None = None):
        captured["method"] = method
        captured["path"] = path
        captured["payload"] = payload
        return None

    monkeypatch.setattr(deploy_service, "_bunny_api_request", fake_bunny_api_request)

    output = deploy_service._purge_bunny_pull_zone_cache(zone_id=777)

    assert captured == {
        "method": "POST",
        "path": "/pullzone/777/purgeCache",
        "payload": None,
    }
    assert output == {"zoneId": 777, "status": "purged"}


def test_ensure_bunny_pull_zone_hostname_skips_create_when_hostname_already_on_same_zone(monkeypatch):
    monkeypatch.setattr(
        deploy_service,
        "_get_bunny_pull_zone",
        lambda *, zone_id: {"Id": zone_id, "Hostnames": []},
    )
    monkeypatch.setattr(
        deploy_service,
        "_find_bunny_pull_zone_by_hostname",
        lambda *, hostname: {"Id": 777, "Name": "workspace-123", "Hostnames": [{"Value": hostname}]},
    )

    def _unexpected_request(*, method: str, path: str, payload: dict | None = None):
        raise AssertionError(f"addHostname should not run when hostname already exists ({method} {path} {payload})")

    monkeypatch.setattr(deploy_service, "_bunny_api_request", _unexpected_request)

    output = deploy_service._ensure_bunny_pull_zone_hostname(
        zone_id=777,
        hostname="shop.example.com",
    )

    assert output == {"hostname": "shop.example.com", "status": "existing"}


def test_ensure_bunny_pull_zone_hostname_errors_when_hostname_is_on_other_zone(monkeypatch):
    monkeypatch.setattr(
        deploy_service,
        "_get_bunny_pull_zone",
        lambda *, zone_id: {"Id": zone_id, "Hostnames": []},
    )
    monkeypatch.setattr(
        deploy_service,
        "_find_bunny_pull_zone_by_hostname",
        lambda *, hostname: {"Id": 888, "Name": "workspace-other", "Hostnames": [{"Value": hostname}]},
    )

    with pytest.raises(
        deploy_service.DeployError,
        match="already registered to pull zone 'workspace-other' \\(id=888\\), not target zone id=777",
    ):
        deploy_service._ensure_bunny_pull_zone_hostname(
            zone_id=777,
            hostname="shop.example.com",
        )


def test_ensure_bunny_pull_zone_hostname_reconciles_already_registered_after_bunny_rejects_create(monkeypatch):
    zone_fetches = {"count": 0}

    def fake_get_bunny_pull_zone(*, zone_id: int):
        zone_fetches["count"] += 1
        if zone_fetches["count"] == 1:
            return {"Id": zone_id, "Hostnames": []}
        return {
            "Id": zone_id,
            "Hostnames": [
                {"Value": "workspace-123.b-cdn.net"},
                {"Value": "shop.example.com"},
            ],
        }

    monkeypatch.setattr(deploy_service, "_get_bunny_pull_zone", fake_get_bunny_pull_zone)
    monkeypatch.setattr(deploy_service, "_find_bunny_pull_zone_by_hostname", lambda *, hostname: None)

    def fake_bunny_api_request(*, method: str, path: str, payload: dict | None = None):
        assert method == "POST"
        assert path == "/pullzone/777/addHostname"
        assert payload == {"Hostname": "shop.example.com"}
        raise deploy_service.DeployError(
            "Bunny API request failed (POST /pullzone/777/addHostname) with status 400: The hostname is already registered."
        )

    monkeypatch.setattr(deploy_service, "_bunny_api_request", fake_bunny_api_request)

    output = deploy_service._ensure_bunny_pull_zone_hostname(
        zone_id=777,
        hostname="shop.example.com",
    )

    assert output == {"hostname": "shop.example.com", "status": "existing"}
    assert zone_fetches["count"] == 2


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
                                    "source_ref": {"client_id": "workspace-123"},
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

    def fake_ensure_bunny_pull_zone(
        *,
        client_id: str,
        workload_name: str,
        origin_url: str,
        server_names: list[str] | None = None,
    ):
        captured["client_id"] = client_id
        captured["workload_name"] = workload_name
        captured["origin_url"] = origin_url
        captured["server_names"] = server_names
        return {
            "Id": 999,
            "Name": workload_name,
            "OriginUrl": origin_url,
            "Hostnames": [{"Value": f"{workload_name}.b-cdn.net"}],
        }

    monkeypatch.setattr(deploy_service, "_ensure_bunny_pull_zone", fake_ensure_bunny_pull_zone)
    monkeypatch.setattr(
        deploy_service,
        "_provision_bunny_custom_domains",
        lambda *, bunny_zone, server_names, request_ssl: {
            "dnsTargetHostname": "brand-funnels-brand-abc.b-cdn.net",
            "domains": [
                {
                    "hostname": "offers.example.com",
                    "dns": {"provider": "namecheap"},
                    "bunnyHostname": {"status": "created"},
                    "ssl": {"status": "pending_publish" if not request_ssl else "requested"},
                }
            ],
            "pullZoneHostnames": ["brand-funnels-brand-abc.b-cdn.net", "offers.example.com"],
        },
    )

    output = deploy_service.configure_bunny_pull_zone_for_workload(
        client_id="workspace-123",
        workload_name="brand-funnels-brand-abc",
        plan_path=str(plan_path),
        instance_name="mos-ghc-1",
    )
    assert output["provider"] == "bunny"
    assert output["pull_zone"]["id"] == 999
    assert output["pull_zone"]["name"] == "brand-funnels-brand-abc"
    assert output["pull_zone"]["originUrl"] == "http://46.225.124.104"
    assert output["pull_zone"]["accessUrls"] == ["https://brand-funnels-brand-abc.b-cdn.net/", "https://offers.example.com/"]
    assert output["pull_zone"]["dnsTargetHostname"] == "brand-funnels-brand-abc.b-cdn.net"
    assert isinstance(output["pull_zone"]["domainProvisioning"], list)
    assert captured == {
        "client_id": "workspace-123",
        "workload_name": "brand-funnels-brand-abc",
        "origin_url": "http://46.225.124.104",
        "server_names": ["offers.example.com"],
    }


def test_configure_bunny_pull_zone_for_workload_uses_workspace_id_for_zone_scope(tmp_path, monkeypatch):
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
                                    "source_ref": {"client_id": "client-456"},
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

    def fake_ensure_bunny_pull_zone(
        *,
        client_id: str,
        workload_name: str,
        origin_url: str,
        server_names: list[str] | None = None,
    ):
        captured["client_id"] = client_id
        captured["workload_name"] = workload_name
        captured["origin_url"] = origin_url
        captured["server_names"] = server_names
        return {
            "Id": 999,
            "Name": workload_name,
            "OriginUrl": origin_url,
            "Hostnames": [{"Value": f"{workload_name}.b-cdn.net"}],
        }

    monkeypatch.setattr(deploy_service, "_ensure_bunny_pull_zone", fake_ensure_bunny_pull_zone)
    monkeypatch.setattr(
        deploy_service,
        "_provision_bunny_custom_domains",
        lambda *, bunny_zone, server_names, request_ssl: {
            "dnsTargetHostname": "brand-funnels-brand-abc.b-cdn.net",
            "domains": [],
            "pullZoneHostnames": ["brand-funnels-brand-abc.b-cdn.net", *server_names],
        },
    )

    output = deploy_service.configure_bunny_pull_zone_for_workload(
        client_id="client-456",
        workload_name="brand-funnels-brand-abc",
        plan_path=str(plan_path),
        instance_name="mos-ghc-1",
    )

    assert output["provider"] == "bunny"
    assert output["pull_zone"]["name"] == "brand-funnels-brand-abc"
    assert captured == {
        "client_id": "client-456",
        "workload_name": "brand-funnels-brand-abc",
        "origin_url": "http://46.225.124.104",
        "server_names": ["offers.example.com"],
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
                                    "source_ref": {"client_id": "workspace-123"},
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

    def fake_ensure_bunny_pull_zone(
        *,
        client_id: str,
        workload_name: str,
        origin_url: str,
        server_names: list[str] | None = None,
    ):
        captured["client_id"] = client_id
        captured["workload_name"] = workload_name
        captured["origin_url"] = origin_url
        captured["server_names"] = server_names
        return {
            "Id": 999,
            "Name": workload_name,
            "OriginUrl": origin_url,
            "Hostnames": [{"Value": f"{workload_name}.b-cdn.net"}],
        }

    monkeypatch.setattr(deploy_service, "_ensure_bunny_pull_zone", fake_ensure_bunny_pull_zone)

    output = deploy_service.configure_bunny_pull_zone_for_workload(
        client_id="workspace-123",
        workload_name="brand-funnels-brand-abc",
        plan_path=str(plan_path),
        instance_name="mos-ghc-1",
    )
    assert output["provider"] == "bunny"
    assert output["pull_zone"]["id"] == 999
    assert output["pull_zone"]["name"] == "brand-funnels-brand-abc"
    assert output["pull_zone"]["originUrl"] == "http://46.225.124.104:24123"
    assert output["pull_zone"]["accessUrls"] == ["https://brand-funnels-brand-abc.b-cdn.net/"]
    assert output["pull_zone"]["workloadPort"] == 24123
    assert captured == {
        "client_id": "workspace-123",
        "workload_name": "brand-funnels-brand-abc",
        "origin_url": "http://46.225.124.104:24123",
        "server_names": [],
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
                                    "source_ref": {"client_id": "workspace-123"},
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

    def fake_ensure_bunny_pull_zone(
        *,
        client_id: str,
        workload_name: str,
        origin_url: str,
        server_names: list[str] | None = None,
    ):
        captured["client_id"] = client_id
        captured["workload_name"] = workload_name
        captured["origin_url"] = origin_url
        captured["server_names"] = server_names
        return {
            "Id": 999,
            "Name": workload_name,
            "OriginUrl": origin_url,
            "Hostnames": [{"Value": f"{workload_name}.b-cdn.net"}],
        }

    monkeypatch.setattr(deploy_service, "_ensure_bunny_pull_zone", fake_ensure_bunny_pull_zone)

    output = deploy_service.configure_bunny_pull_zone_for_workload(
        client_id="workspace-123",
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
        "client_id": "workspace-123",
        "workload_name": "brand-funnels-brand-abc",
        "origin_url": "http://46.225.124.104",
        "server_names": [],
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
                                    "source_ref": {"client_id": "workspace-123"},
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

    def fake_ensure_bunny_pull_zone(
        *,
        client_id: str,
        workload_name: str,
        origin_url: str,
        server_names: list[str] | None = None,
    ):
        captured["client_id"] = client_id
        captured["workload_name"] = workload_name
        captured["origin_url"] = origin_url
        captured["zone_server_names"] = server_names
        return {
            "Id": 999,
            "Name": workload_name,
            "OriginUrl": origin_url,
            "Hostnames": [{"Value": f"{workload_name}.b-cdn.net"}],
        }

    def fake_provision(*, bunny_zone: dict, server_names: list[str], request_ssl: bool = True):
        captured["server_names"] = server_names
        captured["request_ssl"] = request_ssl
        return {
            "dnsTargetHostname": "brand-funnels-brand-abc.b-cdn.net",
            "domains": [],
            "pullZoneHostnames": ["brand-funnels-brand-abc.b-cdn.net"],
        }

    monkeypatch.setattr(deploy_service, "_ensure_bunny_pull_zone", fake_ensure_bunny_pull_zone)
    monkeypatch.setattr(deploy_service, "_provision_bunny_custom_domains", fake_provision)

    output = deploy_service.configure_bunny_pull_zone_for_workload(
        client_id="workspace-123",
        workload_name="brand-funnels-brand-abc",
        plan_path=str(plan_path),
        instance_name="mos-ghc-1",
        server_names=["shop.example.com"],
    )
    assert output["provider"] == "bunny"
    assert output["pull_zone"]["originUrl"] == "http://46.225.124.104"
    assert captured["client_id"] == "workspace-123"
    assert captured["workload_name"] == "brand-funnels-brand-abc"
    assert captured["origin_url"] == "http://46.225.124.104"
    assert captured["zone_server_names"] == ["shop.example.com"]
    assert captured["server_names"] == ["shop.example.com"]
    assert captured["request_ssl"] is False


def test_configure_bunny_pull_zone_for_workload_errors_when_workspace_scope_mismatches(tmp_path, monkeypatch):
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
                                    "source_ref": {"client_id": "workspace-123"},
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

    with pytest.raises(deploy_service.DeployError, match="belongs to workspace 'workspace-123'"):
        deploy_service.configure_bunny_pull_zone_for_workload(
            client_id="workspace-999",
            workload_name="brand-funnels-brand-abc",
            plan_path=str(plan_path),
            instance_name="mos-ghc-1",
        )


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
                                    "source_ref": {"client_id": "workspace-123"},
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

    def fake_ensure_bunny_pull_zone(
        *,
        client_id: str,
        workload_name: str,
        origin_url: str,
        server_names: list[str] | None = None,
    ):
        captured["client_id"] = client_id
        captured["workload_name"] = workload_name
        captured["origin_url"] = origin_url
        captured["server_names"] = server_names
        return {
            "Id": 999,
            "Name": workload_name,
            "OriginUrl": origin_url,
            "Hostnames": [{"Value": f"{workload_name}.b-cdn.net"}],
        }

    monkeypatch.setattr(deploy_service, "_ensure_bunny_pull_zone", fake_ensure_bunny_pull_zone)

    output = deploy_service._reconcile_bunny_pull_zone_for_published_workload(
        client_id="workspace-123",
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
        "client_id": "workspace-123",
        "workload_name": "brand-funnels-brand-abc",
        "origin_url": "http://46.225.124.104:24123",
        "server_names": [],
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
        upstream_api_base_url="https://api.moshq.app",
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


def test_build_funnel_publication_workload_patch_supports_html_deploy():
    patch = deploy_service.build_funnel_publication_workload_patch(
        workload_name="standalone-funnel",
        client_id="f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
        upstream_base_url="https://moshq.app",
        upstream_api_base_url="https://api.moshq.app",
        server_names=["shop.example.com"],
        https=True,
        destination_path="/opt/apps",
        artifact_render_mode="html_deploy",
    )

    source_ref = patch["source_ref"]
    assert source_ref["artifact_render_mode"] == "html_deploy"
    assert source_ref["default_route_policy"] == "entry_page"
    assert source_ref["default_page_slug"] is None
    assert source_ref["upstream_api_base_root"] == "https://api.moshq.app"
    assert "runtime_dist_path" not in source_ref


def test_build_funnel_publication_workload_patch_supports_explicit_default_route():
    patch = deploy_service.build_funnel_publication_workload_patch(
        workload_name="standalone-funnel",
        client_id="f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
        upstream_base_url="https://moshq.app",
        upstream_api_base_url="https://api.moshq.app",
        server_names=[],
        https=False,
        destination_path="/opt/apps",
        artifact_render_mode="html_deploy",
        default_route_policy="explicit_slug",
        default_page_slug="quiz-v6",
    )

    assert patch["source_ref"]["default_route_policy"] == "explicit_slug"
    assert patch["source_ref"]["default_page_slug"] == "quiz-v6"


def test_build_funnel_publication_workload_patch_rejects_pathful_api_base_for_standalone():
    with pytest.raises(deploy_service.DeployError, match="origin URL without a path"):
        deploy_service.build_funnel_publication_workload_patch(
            workload_name="standalone-funnel",
            client_id="f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
            upstream_base_url="https://moshq.app",
            upstream_api_base_url="https://moshq.app/api",
            server_names=["shop.example.com"],
            https=True,
            destination_path="/opt/apps",
            artifact_render_mode="html_deploy",
        )


def _tiny_png_bytes() -> bytes:
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
    )


def test_validate_standalone_html_image_references_accepts_src_and_srcset_assets():
    site_dir = "/tmp/mos-standalone-preflight"
    png = _tiny_png_bytes()
    served_assets = {
        "/shop/daily/presales/assets/hero.png": SimpleNamespace(
            content=png,
            content_type="image/png",
        ),
        "/shop/daily/presales/assets/hero-480.png": SimpleNamespace(
            content=png,
            content_type="image/png",
        ),
        "/shop/daily/presales/assets/hero-800.png": SimpleNamespace(
            content=png,
            content_type="image/png",
        ),
    }

    deploy_service._validate_standalone_html_image_references(
        site_dir=site_dir,
        uploaded_html_files={
            f"{site_dir}/shop/daily/presales/index.html": """
            <picture>
              <source srcset="./assets/hero-480.png 480w, ./assets/hero-800.png 800w">
              <img src="./assets/hero.png" srcset="./assets/hero-480.png 480w, ./assets/hero-800.png 800w">
            </picture>
            """,
        },
        uploaded_binary_files={},
        standalone_served_assets=served_assets,
        public_server_names=["shop.example.com"],
        upstream_api_base_root="https://api.example.com",
    )


def test_validate_standalone_html_image_references_rejects_missing_srcset_asset():
    site_dir = "/tmp/mos-standalone-preflight"
    png = _tiny_png_bytes()
    served_assets = {
        "/shop/daily/presales/assets/hero.png": SimpleNamespace(
            content=png,
            content_type="image/png",
        ),
        "/shop/daily/presales/assets/hero-480.png": SimpleNamespace(
            content=png,
            content_type="image/png",
        ),
    }

    with pytest.raises(deploy_service.DeployError, match="missing deployed image asset"):
        deploy_service._validate_standalone_html_image_references(
            site_dir=site_dir,
            uploaded_html_files={
                f"{site_dir}/shop/daily/presales/index.html": """
                <picture>
                  <source srcset="./assets/hero-480.png 480w, ./assets/missing-800.png 800w">
                  <img src="./assets/hero.png">
                </picture>
                """,
            },
            uploaded_binary_files={},
            standalone_served_assets=served_assets,
            public_server_names=["shop.example.com"],
            upstream_api_base_root="https://api.example.com",
        )


def test_validate_standalone_html_image_references_validates_uploaded_public_asset_bytes():
    site_dir = "/tmp/mos-standalone-preflight"
    public_id = "77777777-7777-4777-8777-777777777777"
    png = _tiny_png_bytes()

    deploy_service._validate_standalone_html_image_references(
        site_dir=site_dir,
        uploaded_html_files={
            f"{site_dir}/shop/daily/sales-page/index.html": (
                f'<img src="/public/assets/{public_id}" '
                f'srcset="/api/public/assets/{public_id}.png 480w">'
            ),
        },
        uploaded_binary_files={
            f"{site_dir}/api/public/assets/{public_id}.png": png,
        },
        standalone_served_assets={},
        public_server_names=["shop.example.com"],
        upstream_api_base_root="https://api.example.com",
    )


def test_apply_publish_job_artifact_render_mode_prefers_standalone_for_compatible_artifact(monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ARTIFACT_RUNTIME_DIST_PATH", "mos/frontend/dist")
    workload_patch = deploy_service.build_funnel_publication_workload_patch(
        workload_name="auto-standalone-funnel",
        client_id="f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
        upstream_base_url="https://moshq.app",
        upstream_api_base_url="https://api.moshq.app",
        server_names=[],
        https=False,
        destination_path="/opt/apps",
        artifact_render_mode="runtime_bundle",
    )

    artifact_payload = {
        "meta": {"clientId": "f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95"},
        "products": {
            "070d6cf7": {
                "meta": {"productId": "product-1"},
                "funnels": {
                    "sales-funnel": {
                        "meta": {
                            "productSlug": "070d6cf7",
                            "funnelSlug": "sales-funnel",
                            "funnelId": "18ac0fe1-1e27-4579-ad94-9a1e6c9530fe",
                            "publicationId": "pub-1",
                            "entrySlug": "sales-page",
                            "pages": [{"pageId": "page-1", "slug": "sales-page"}],
                        },
                        "pages": {
                            "sales-page": {
                                "puckData": {
                                    "root": {"props": {}},
                                    "content": [
                                        {
                                            "type": "ImportedHtmlDocument",
                                            "props": {
                                                "htmlDocument": "<html><body>ok</body></html>",
                                                    "instrumentationManifest": {
                                                    "schemaVersion": "html-deploy-v1",
                                                    "htmlArtifactKind": "sales",
                                                    "pageStage": "sales",
                                                    "bindings": [],
                                                },
                                            },
                                        }
                                    ],
                                    "zones": {},
                                }
                            },
                            "privacy-policy": {
                                "puckData": {
                                    "root": {"props": {}},
                                    "content": [
                                        {
                                            "type": "FunnelCompliancePage",
                                            "props": {
                                                "pageKey": "privacy_policy",
                                                "pageTitle": "Privacy Policy",
                                            },
                                        }
                                    ],
                                    "zones": {},
                                }
                            }
                        },
                    }
                },
            }
        },
    }

    patched = deploy_service._apply_publish_job_artifact_render_mode(
        workload_patch=workload_patch,
        artifact_payload=artifact_payload,
        requested_render_mode=None,
        render_mode_was_explicit=False,
    )

    source_ref = patched["source_ref"]
    assert source_ref["artifact_render_mode"] == "html_deploy"
    assert source_ref["upstream_api_base_root"] == "https://api.moshq.app"
    assert "runtime_dist_path" not in source_ref


def test_apply_publish_job_artifact_render_mode_keeps_runtime_bundle_for_incompatible_artifact(monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ARTIFACT_RUNTIME_DIST_PATH", "mos/frontend/dist")
    workload_patch = deploy_service.build_funnel_publication_workload_patch(
        workload_name="fallback-runtime-funnel",
        client_id="f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
        upstream_base_url="https://moshq.app",
        upstream_api_base_url="https://api.moshq.app",
        server_names=[],
        https=False,
        destination_path="/opt/apps",
        artifact_render_mode="runtime_bundle",
    )

    artifact_payload = {
        "meta": {"clientId": "f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95"},
        "products": {
            "070d6cf7": {
                "meta": {"productId": "product-1"},
                "funnels": {
                    "sales-funnel": {
                        "meta": {
                            "productSlug": "070d6cf7",
                            "funnelSlug": "sales-funnel",
                            "funnelId": "18ac0fe1-1e27-4579-ad94-9a1e6c9530fe",
                            "publicationId": "pub-1",
                            "entrySlug": "sales-page",
                            "pages": [{"pageId": "page-1", "slug": "sales-page"}],
                        },
                        "pages": {
                            "sales-page": {
                                "puckData": {
                                    "root": {"props": {}},
                                    "content": [
                                        {
                                            "type": "Text",
                                            "props": {"text": "Published"},
                                        }
                                    ],
                                    "zones": {},
                                }
                            }
                        },
                    }
                },
            }
        },
    }

    patched = deploy_service._apply_publish_job_artifact_render_mode(
        workload_patch=workload_patch,
        artifact_payload=artifact_payload,
        requested_render_mode=None,
        render_mode_was_explicit=False,
    )

    source_ref = patched["source_ref"]
    assert source_ref["artifact_render_mode"] == "runtime_bundle"
    assert source_ref["runtime_dist_path"] == "mos/frontend/dist"


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
        upstream_api_base_url="https://api.moshq.app",
        server_names=[],
        https=False,
        destination_path="/opt/apps",
    )
    patch_b = deploy_service.build_funnel_publication_workload_patch(
        workload_name="brand-funnels-b",
        client_id="3d8cf9b0-6e31-4f8f-9a56-9c94bbf2d68d",
        upstream_base_url="https://moshq.app",
        upstream_api_base_url="https://api.moshq.app",
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
        upstream_api_base_url="https://api.moshq.app",
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
    monkeypatch.setattr(
        deploy_service,
        "_artifact_payload_supports_html_deploy",
        lambda *, artifact_payload: True,
    )

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
                                        "upstream_api_base_root": "https://api.moshq.app",
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


def test_materialize_funnel_artifacts_for_apply_replaces_stale_inline_artifact_when_artifact_id_present(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))

    def _fake_load(*, artifact_id: str):
        assert artifact_id == "artifact-123"
        return {
            "meta": {"artifactId": artifact_id, "publicationId": "pub-new"},
            "products": {
                "sample-product": {
                    "meta": {"productSlug": "sample-product"},
                    "funnels": {
                        "new-funnel": {
                            "meta": {"publicationId": "pub-new"},
                        }
                    },
                }
            },
        }

    monkeypatch.setattr(deploy_service, "_load_funnel_runtime_artifact_payload_for_apply", _fake_load)
    monkeypatch.setattr(
        deploy_service,
        "_artifact_payload_supports_html_deploy",
        lambda *, artifact_payload: True,
    )

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
                                        "upstream_api_base_root": "https://api.moshq.app",
                                        "runtime_dist_path": "mos/frontend/dist",
                                        "artifact": {
                                            "meta": {"artifactId": "artifact-old", "publicationId": "pub-old"},
                                            "products": {
                                                "sample-product": {
                                                    "meta": {"productSlug": "sample-product"},
                                                    "funnels": {
                                                        "old-funnel": {
                                                            "meta": {"publicationId": "pub-old"},
                                                        }
                                                    },
                                                }
                                            },
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
    source_ref = payload["new_spec"]["instances"][0]["workloads"][0]["source_ref"]
    assert source_ref["artifact"]["meta"]["artifactId"] == "artifact-123"
    assert source_ref["artifact"]["meta"]["publicationId"] == "pub-new"
    assert "new-funnel" in source_ref["artifact"]["products"]["sample-product"]["funnels"]
    assert "old-funnel" not in source_ref["artifact"]["products"]["sample-product"]["funnels"]


def test_materialize_funnel_artifacts_for_apply_normalizes_legacy_publication_source_ref(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_PUBLIC_BASE_URL", "https://moshq.app")
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_PUBLIC_API_BASE_URL", "https://api.moshq.app")

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
    assert source_ref["upstream_api_base_url"] == "https://api.moshq.app"


def test_materialize_funnel_artifacts_for_apply_normalizes_legacy_artifact_source_ref(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_PUBLIC_API_BASE_URL", "https://api.moshq.app")
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
                                        "upstream_api_base_url": "https://api.moshq.app",
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
    assert source_ref["upstream_api_base_root"] == "https://api.moshq.app"
    assert source_ref["runtime_dist_path"] == deploy_service.settings.DEPLOY_ARTIFACT_RUNTIME_DIST_PATH
    assert "legacy-product" in source_ref["artifact"]["products"]


def test_materialize_funnel_artifacts_for_apply_converts_legacy_artifact_public_id_to_publication(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_PUBLIC_BASE_URL", "https://moshq.app")
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_PUBLIC_API_BASE_URL", "https://api.moshq.app")

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
    assert source_ref["upstream_api_base_url"] == "https://api.moshq.app"


def test_materialize_funnel_artifacts_for_apply_preserves_standalone_render_mode_without_runtime_path(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_PUBLIC_BASE_URL", "https://moshq.app")
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_PUBLIC_API_BASE_URL", "https://api.moshq.app")

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
                                    "name": "standalone-artifact-workload",
                                    "source_type": "funnel_artifact",
                                    "source_ref": {
                                        "client_id": "client-1",
                                        "artifact_render_mode": "html_deploy",
                                        "upstream_api_base_root": "https://api.moshq.app",
                                        "artifact": {
                                            "meta": {"clientId": "client-1"},
                                            "products": {},
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
    payload = json.loads(materialized.read_text(encoding="utf-8"))
    source_ref = payload["new_spec"]["instances"][0]["workloads"][0]["source_ref"]
    assert source_ref["artifact_render_mode"] == "html_deploy"
    assert "runtime_dist_path" not in source_ref


def test_materialize_funnel_artifacts_for_apply_infers_standalone_render_mode_from_artifact_payload(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_PUBLIC_BASE_URL", "https://moshq.app")
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_PUBLIC_API_BASE_URL", "https://api.moshq.app")

    def _fake_load(*, artifact_id: str):
        assert artifact_id == "artifact-123"
        return {
            "meta": {"artifactId": artifact_id},
            "products": {
                "sample-product": {
                    "meta": {"productSlug": "sample-product"},
                    "funnels": {
                        "sample-funnel": {
                            "meta": {
                                "routeSlug": "sample-funnel",
                                "entrySlug": "presales",
                                "publicationId": "publication-123",
                                "pages": [
                                    {"pageId": "page-1", "slug": "presales"},
                                ],
                            },
                            "pages": {
                                "presales": {
                                    "puckData": {
                                        "content": [
                                            {
                                                "type": "ImportedHtmlDocument",
                                                "props": {
                                                    "htmlDocument": "<html><body>Presales</body></html>",
                                                    "instrumentationManifest": {
                                                        "pageView": {
                                                            "eventName": "pre_sales_page_view",
                                                        },
                                                        "bindings": [],
                                                    },
                                                },
                                            }
                                        ]
                                    },
                                }
                            },
                        }
                    },
                }
            },
        }

    monkeypatch.setattr(deploy_service, "_load_funnel_runtime_artifact_payload_for_apply", _fake_load)
    monkeypatch.setattr(
        deploy_service,
        "_artifact_payload_supports_html_deploy",
        lambda *, artifact_payload: True,
    )

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
                                    "name": "standalone-artifact-workload",
                                    "source_type": "funnel_artifact",
                                    "source_ref": {
                                        "client_id": "client-1",
                                        "artifact_id": "artifact-123",
                                        "upstream_api_base_root": "https://api.moshq.app",
                                        "runtime_dist_path": "mos/frontend/dist",
                                        "artifact": {
                                            "meta": {"clientId": "client-1"},
                                            "products": {},
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
    payload = json.loads(materialized.read_text(encoding="utf-8"))
    source_ref = payload["new_spec"]["instances"][0]["workloads"][0]["source_ref"]
    assert source_ref["artifact_render_mode"] == "html_deploy"
    assert "runtime_dist_path" not in source_ref


def test_hydrate_funnel_artifact_workload_patch_embeds_full_persisted_artifact_payload(monkeypatch):
    artifact_payload = {
        "meta": {"clientId": "client-1", "artifactId": "artifact-123", "artifactVersion": 7},
        "products": {
            "sample-product": {
                "meta": {"productSlug": "sample-product"},
                "funnels": {
                    "sample-funnel": {
                        "meta": {"entrySlug": "sales-page"},
                        "pages": {
                            "sales-page": {
                                "slug": "sales-page",
                                "puckData": {
                                    "content": [
                                        {
                                            "type": "ImportedHtmlDocument",
                                            "props": {"htmlDocument": "<html><body>ok</body></html>"},
                                        }
                                    ]
                                },
                            }
                        },
                    }
                },
            }
        },
        "assets": {"items": {"asset-1": {"sizeBytes": 12, "bytesBase64": "YWJj"}}},
    }

    monkeypatch.setattr(
        deploy_service,
        "persist_client_funnel_runtime_artifact",
        lambda **_: {
            "artifact_id": "artifact-123",
            "artifact_version": 7,
            "client_id": "client-1",
        },
    )

    import app.db.repositories.artifacts as artifacts_module

    class _ArtifactsRepo:
        def __init__(self, session):
            self.session = session

        def get(self, org_id, artifact_id):
            assert org_id == "org-1"
            assert artifact_id == "artifact-123"
            return SimpleNamespace(data=artifact_payload)

    monkeypatch.setattr(artifacts_module, "ArtifactsRepository", _ArtifactsRepo)

    workload_patch = {
        "name": "brand-funnels-70124684-be65d76e",
        "source_type": "funnel_artifact",
        "source_ref": {
            "upstream_api_base_root": "https://api.moshq.app",
            "artifact": {"meta": {"clientId": "client-1"}, "products": {}},
        },
    }

    hydrated = deploy_service.hydrate_funnel_artifact_workload_patch(
        session=object(),
        org_id="org-1",
        funnel_id="funnel-1",
        publication_id="publication-1",
        workload_patch=workload_patch,
        created_by_user_id="user-1",
    )

    assert hydrated["source_ref"]["client_id"] == "client-1"
    assert hydrated["source_ref"]["artifact_id"] == "artifact-123"
    assert hydrated["source_ref"]["artifact_version"] == 7
    assert hydrated["source_ref"]["artifact"] == artifact_payload
    assert hydrated["source_ref"]["artifact"] is not artifact_payload
    assert hydrated["source_ref"]["artifact"]["meta"]["artifactId"] == "artifact-123"


def test_extract_embedded_asset_public_ids_collects_from_page_and_design_tokens():
    output = deploy_service._extract_embedded_asset_public_ids(
        puck_data={
            "root": {"props": {}},
            "content": [
                {
                    "type": "Image",
                    "props": {
                        "assetPublicId": "11111111-1111-1111-1111-111111111111",
                    },
                },
                {
                    "type": "SalesPdpHero",
                    "props": {
                        "config": {
                            "gallery": {
                                "slides": [
                                    {"thumbAssetPublicId": "22222222-2222-2222-2222-222222222222"},
                                    {"src": "/public/assets/44444444-4444-4444-4444-444444444444"},
                                    {"poster": "https://cdn.example.com/api/public/assets/55555555-5555-5555-5555-555555555555.png"},
                                ]
                            }
                        }
                    },
                },
            ],
            "zones": {},
        },
        design_system_tokens={
            "brand": {
                "logoAssetPublicId": "33333333-3333-3333-3333-333333333333",
                "logoOnDarkAssetPublicId": "66666666-6666-6666-6666-666666666666",
            }
        },
        context_label="test-page",
    )

    assert output == {
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
        "33333333-3333-3333-3333-333333333333",
        "44444444-4444-4444-4444-444444444444",
        "55555555-5555-5555-5555-555555555555",
        "66666666-6666-6666-6666-666666666666",
    }


def test_extract_embedded_asset_public_ids_collects_urls_inside_imported_html_document():
    output = deploy_service._extract_embedded_asset_public_ids(
        puck_data={
            "root": {"props": {}},
            "content": [
                {
                    "type": "ImportedHtmlDocument",
                    "props": {
                        "htmlDocument": """
<!DOCTYPE html>
<html>
  <body>
    <img src="https://api.moshq.app/public/assets/77777777-7777-7777-7777-777777777777" alt="Hero">
    <img src="/public/assets/88888888-8888-8888-8888-888888888888" alt="Chart">
    <img src="/api/public/assets/99999999-9999-9999-9999-999999999999.png" alt="Gallery">
  </body>
</html>
""",
                    },
                }
            ],
            "zones": {},
        },
        design_system_tokens=None,
        context_label="imported-html-page",
    )

    assert output == {
        "77777777-7777-7777-7777-777777777777",
        "88888888-8888-8888-8888-888888888888",
        "99999999-9999-9999-9999-999999999999",
    }


def test_extract_embedded_asset_public_ids_ignores_relative_standalone_asset_paths_in_imported_html():
    output = deploy_service._extract_embedded_asset_public_ids(
        puck_data={
            "root": {"props": {}},
            "content": [
                {
                    "type": "ImportedHtmlDocument",
                    "props": {
                        "htmlDocument": """
<!DOCTYPE html>
<html>
  <body>
    <img src="public/assets/generated/chart.jpg" alt="Generated chart">
    <img src="public/assets/hero/ember-pouch.webp" alt="Local hero image">
    <img src="https://api.moshq.app/public/assets/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa" alt="Remote hero">
  </body>
</html>
""",
                    },
                }
            ],
            "zones": {},
        },
        design_system_tokens=None,
        context_label="imported-html-page",
    )

    assert output == {
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    }


def test_extract_embedded_asset_public_ids_errors_on_invalid_uuid():
    with pytest.raises(deploy_service.DeployError, match="invalid assetPublicId"):
        deploy_service._extract_embedded_asset_public_ids(
            puck_data={
                "root": {"props": {}},
                "content": [
                    {
                        "type": "Image",
                        "props": {
                            "assetPublicId": "not-a-uuid",
                        },
                    }
                ],
                "zones": {},
            },
            design_system_tokens=None,
            context_label="test-page",
        )


def test_extract_embedded_asset_public_ids_errors_on_invalid_canonical_asset_url_in_imported_html():
    with pytest.raises(deploy_service.DeployError, match="invalid public asset URL"):
        deploy_service._extract_embedded_asset_public_ids(
            puck_data={
                "root": {"props": {}},
                "content": [
                    {
                        "type": "ImportedHtmlDocument",
                        "props": {
                            "htmlDocument": """
<!DOCTYPE html>
<html>
  <body>
    <img src="/public/assets/not-a-uuid" alt="Broken asset">
  </body>
</html>
""",
                        },
                    }
                ],
                "zones": {},
            },
            design_system_tokens=None,
            context_label="imported-html-page",
        )


def test_materialize_design_system_brand_logo_in_puck_data_rewrites_sales_and_presales_logo_slots():
    stale_logo_id = "11111111-1111-1111-1111-111111111111"
    current_logo_id = "22222222-2222-2222-2222-222222222222"
    gallery_asset_id = "33333333-3333-3333-3333-333333333333"
    brand_alt = "Current Honest Herbalist Logo"

    sales_template_config = {
        "hero": {"header": {"logo": {"assetPublicId": stale_logo_id, "alt": "Old Logo"}}},
        "footer": {"logo": {"assetPublicId": stale_logo_id, "alt": "Old Logo"}},
    }
    presales_template_config = {
        "footer": {"logo": {"assetPublicId": stale_logo_id, "alt": "Old Logo"}},
    }

    puck_data = {
        "root": {"props": {}},
        "content": [
            {
                "type": "SalesPdpPage",
                "props": {
                    "content": [
                        {
                            "type": "SalesPdpHeader",
                            "props": {
                                "config": {"logo": {"assetPublicId": stale_logo_id, "alt": "Old Logo", "href": "#top"}},
                                "configJson": json.dumps(
                                    {"logo": {"assetPublicId": stale_logo_id, "alt": "Old Logo", "href": "#top"}}
                                ),
                            },
                        },
                        {
                            "type": "SalesPdpHero",
                            "props": {
                                "config": {
                                    "header": {"logo": {"assetPublicId": stale_logo_id, "alt": "Old Logo", "href": "#top"}},
                                    "gallery": {"slides": [{"assetPublicId": gallery_asset_id}]},
                                },
                                "configJson": json.dumps(
                                    {
                                        "header": {
                                            "logo": {
                                                "assetPublicId": stale_logo_id,
                                                "alt": "Old Logo",
                                                "href": "#top",
                                            }
                                        },
                                        "gallery": {"slides": [{"assetPublicId": gallery_asset_id}]},
                                    }
                                ),
                            },
                        },
                        {
                            "type": "SalesPdpFooter",
                            "props": {
                                "config": {"logo": {"assetPublicId": stale_logo_id, "alt": "Old Logo"}},
                                "configJson": json.dumps({"logo": {"assetPublicId": stale_logo_id, "alt": "Old Logo"}}),
                            },
                        },
                    ]
                },
            },
            {
                "type": "SalesPdpTemplate",
                "props": {
                    "config": sales_template_config,
                    "configJson": json.dumps(sales_template_config),
                },
            },
            {
                "type": "PreSalesFooter",
                "props": {
                    "config": {"logo": {"assetPublicId": stale_logo_id, "alt": "Old Logo"}},
                    "configJson": json.dumps({"logo": {"assetPublicId": stale_logo_id, "alt": "Old Logo"}}),
                },
            },
            {
                "type": "PreSalesTemplate",
                "props": {
                    "config": presales_template_config,
                    "configJson": json.dumps(presales_template_config),
                },
            },
        ],
        "zones": {},
    }

    materialized = deploy_service._materialize_design_system_brand_logo_in_puck_data(
        puck_data=puck_data,
        design_system_tokens={"brand": {"logoAssetPublicId": current_logo_id, "logoAlt": brand_alt}},
    )

    sales_page_blocks = materialized["content"][0]["props"]["content"]
    sales_header = sales_page_blocks[0]["props"]["config"]["logo"]
    sales_hero_header = sales_page_blocks[1]["props"]["config"]["header"]["logo"]
    sales_footer = sales_page_blocks[2]["props"]["config"]["logo"]
    legacy_sales = materialized["content"][1]["props"]["config"]
    presales_footer = materialized["content"][2]["props"]["config"]["logo"]
    legacy_presales = materialized["content"][3]["props"]["config"]["footer"]["logo"]

    assert sales_header["assetPublicId"] == current_logo_id
    assert sales_hero_header["assetPublicId"] == current_logo_id
    assert sales_footer["assetPublicId"] == current_logo_id
    assert legacy_sales["hero"]["header"]["logo"]["assetPublicId"] == current_logo_id
    assert legacy_sales["footer"]["logo"]["assetPublicId"] == current_logo_id
    assert presales_footer["assetPublicId"] == current_logo_id
    assert legacy_presales["assetPublicId"] == current_logo_id

    assert sales_header["alt"] == brand_alt
    assert sales_hero_header["alt"] == brand_alt
    assert sales_footer["alt"] == brand_alt
    assert legacy_sales["hero"]["header"]["logo"]["alt"] == brand_alt
    assert legacy_sales["footer"]["logo"]["alt"] == brand_alt
    assert presales_footer["alt"] == brand_alt
    assert legacy_presales["alt"] == brand_alt

    sales_header_json = json.loads(sales_page_blocks[0]["props"]["configJson"])
    sales_hero_json = json.loads(sales_page_blocks[1]["props"]["configJson"])
    sales_footer_json = json.loads(sales_page_blocks[2]["props"]["configJson"])
    legacy_sales_json = json.loads(materialized["content"][1]["props"]["configJson"])
    presales_footer_json = json.loads(materialized["content"][2]["props"]["configJson"])
    legacy_presales_json = json.loads(materialized["content"][3]["props"]["configJson"])

    assert sales_header_json["logo"]["assetPublicId"] == current_logo_id
    assert sales_hero_json["header"]["logo"]["assetPublicId"] == current_logo_id
    assert sales_footer_json["logo"]["assetPublicId"] == current_logo_id
    assert legacy_sales_json["hero"]["header"]["logo"]["assetPublicId"] == current_logo_id
    assert legacy_sales_json["footer"]["logo"]["assetPublicId"] == current_logo_id
    assert presales_footer_json["logo"]["assetPublicId"] == current_logo_id
    assert legacy_presales_json["footer"]["logo"]["assetPublicId"] == current_logo_id

    extracted = deploy_service._extract_embedded_asset_public_ids(
        puck_data=materialized,
        design_system_tokens={"brand": {"logoAssetPublicId": current_logo_id, "logoAlt": brand_alt}},
        context_label="artifact-page",
    )

    assert extracted == {current_logo_id, gallery_asset_id}


def _write_publish_job_fixture(tmp_path: Path, *, job_id: str, deploy_request: dict) -> Path:
    job_path = tmp_path / "publish-jobs" / f"{job_id}.json"
    job_path.parent.mkdir(parents=True, exist_ok=True)
    job_path.write_text(
        json.dumps(
            {
                "id": job_id,
                "status": "queued",
                "created_at": "2026-04-22T00:00:00+00:00",
                "started_at": None,
                "finished_at": None,
                "org_id": str(TEST_ORG_ID),
                "user_id": "user-123",
                "funnel_id": "funnel-123",
                "deploy_request": deploy_request,
                "result": None,
                "access_urls": [],
                "error": None,
            }
        ),
        encoding="utf-8",
    )
    return job_path


def _build_tracking_validation_artifact_payload(
    *,
    include_presales: bool,
    presales_artifact_kind: str = "listicle",
) -> dict:
    tracking = {
        "metaPixelId": "pixel-123",
        "posthogProjectApiKey": "phc_test_123",
        "posthogApiHost": "https://emb.shopemberco.com",
        "posthogUiHost": "https://us.posthog.com",
        "posthogDefaults": "2026-01-30",
        "posthogPersonProfiles": "always",
    }
    sales_page = {
        "pageId": "sales-page-id",
        "stage": "sales",
        "tracking": tracking,
        "puckData": {
            "content": [
                {
                    "type": "ImportedHtml",
                    "props": {
                        "instrumentationManifest": {
                            "schemaVersion": "html-deploy-v1",
                            "htmlArtifactKind": "sales",
                            "pageStage": "sales",
                            "bindings": [
                                {
                                    "type": "checkout",
                                    "selector": "#checkout-btn",
                                    "trackEventType": "sales_to_checkout_click",
                                    "checkout": {
                                        "mode": "public_checkout",
                                        "externalUrlsByVariant": [],
                                    },
                                }
                            ],
                        }
                    },
                }
            ]
        },
    }
    pages = {"sales-page": sales_page}
    if include_presales:
        presales_manifest = {
            "schemaVersion": "html-deploy-v1",
            "htmlArtifactKind": presales_artifact_kind,
            "pageStage": "pre_sales",
            "sections": [
                {"id": "intro", "selector": "#intro", "sectionId": "intro"},
            ],
            "proofs": [
                {
                    "id": "proof-1",
                    "selector": "#proof-1",
                    "proofType": "testimonial",
                    "sectionId": "intro",
                },
            ],
            "ctas": [
                {"id": "to-sales-cta", "selector": "#to-sales", "ctaPosition": 1},
            ],
            "bindings": [
                {
                    "type": "internal_navigation",
                    "selector": "#to-sales",
                    "targetPageId": "sales-page-id",
                    "trackEventType": "pre_sales_to_sales_click",
                }
            ],
        }
        if presales_artifact_kind == "quiz":
            presales_manifest.update(
                {
                    "quizId": "daily-drive-quiz",
                    "quizVersion": "v1",
                    "quizVariant": "control",
                    "quizLeads": [
                        {"id": "lead", "selector": "#quiz-lead", "quizId": "daily-drive-quiz"},
                    ],
                    "quizQuestions": [
                        {
                            "id": "question-1",
                            "selector": "#question-1",
                            "questionId": "q1",
                            "questionIndex": 1,
                            "quizId": "daily-drive-quiz",
                            "quizVersion": "v1",
                        },
                    ],
                    "quizOptions": [
                        {
                            "id": "option-1",
                            "selector": "#option-1",
                            "questionId": "q1",
                            "questionIndex": 1,
                            "optionId": "a1",
                            "quizId": "daily-drive-quiz",
                            "quizVersion": "v1",
                        },
                    ],
                    "quizResults": [
                        {"id": "result-1", "selector": "#result-1", "resultId": "r1"},
                    ],
                    "quizMechanisms": [
                        {"id": "mechanism-1", "selector": "#mechanism-1", "mechanismName": "metabolic"},
                    ],
                    "quizRecommendations": [
                        {
                            "id": "recommendation-1",
                            "selector": "#recommendation-1",
                            "recommendationId": "daily-drive",
                        },
                    ],
                }
            )
        pages["presales"] = {
            "pageId": "presales-page-id",
            "stage": "pre_sales",
            "tracking": tracking,
            "puckData": {
                "content": [
                    {
                        "type": "ImportedHtml",
                        "props": {
                            "instrumentationManifest": presales_manifest
                        },
                    }
                ]
            },
        }
    pages["contact-us"] = {
        "pageId": "contact-page-id",
        "stage": "custom",
        "tracking": tracking,
        "puckData": {"content": []},
    }

    return {
        "products": {
            "ember": {
                "funnels": {
                    "daily": {
                        "meta": {
                            "funnelId": "funnel-123",
                            "publicationId": "00000000-0000-0000-0000-000000000999",
                        },
                        "pages": pages,
                    }
                }
            }
        }
    }


def _expected_sales_posthog_context(**overrides) -> dict:
    props = {
        "product_slug": "ember",
        "funnel_slug": "daily",
        "publication_id": "00000000-0000-0000-0000-000000000999",
        "page_id": "sales-page-id",
        "page_slug": "sales-page",
        "page_stage": "sales",
        "content_category": "sales_page",
        "session_id": "session-1",
        "visitor_id": "visitor-1",
    }
    props.update(overrides)
    return props


def _posthog_readback_raw_row(event_name: str, **overrides) -> list:
    validation_url = "https://shop.example.com/?mos_deploy_validation_id=deploy-validation-123"
    row = {
        "event": event_name,
        "timestamp": "2026-05-12T17:00:00Z",
        "current_url": validation_url,
        "event_source_url": validation_url,
        "destination_url": "",
        "url_params": {"mos_deploy_validation_id": "deploy-validation-123"},
        "path": "/?mos_deploy_validation_id=deploy-validation-123",
        "utm_source": "deploy-validation",
        "utm_medium": "deploy-validation",
        "utm_content": "deploy-validation-123",
        "utm_campaign": "deploy-validation-123",
        "content_category": "sales_page",
        "page_stage": "sales",
        "session_id": "session-1",
        "visitor_id": "visitor-1",
        "click_id": "click-1",
        "product_slug": "ember",
        "funnel_slug": "daily",
        "publication_id": "00000000-0000-0000-0000-000000000999",
        "page_id": "sales-page-id",
        "page_slug": "sales-page",
    }
    row.update(overrides)
    return [row.get(column) for column in deploy_service._POSTHOG_READBACK_COLUMNS]


def _install_publish_job_mocks(monkeypatch):
    import app.db.base as db_base
    import app.services.funnels as funnels_service

    class DummySession:
        def close(self):
            return None

    monkeypatch.setattr(db_base, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(
        funnels_service,
        "publish_funnel",
        lambda **kwargs: SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000999")),
    )
    monkeypatch.setattr(
        deploy_service,
        "hydrate_funnel_artifact_workload_patch",
        lambda **kwargs: {
            "name": "brand-funnels-70124684-be65d76e",
            "source_type": "funnel_artifact",
            "source_ref": {
                "client_id": "70124684-505f-48af-a25c-5f7a79601fa0",
                "artifact_id": "artifact-123",
                "artifact_version": 30,
                "artifact_render_mode": "html_deploy",
            },
        },
    )
    monkeypatch.setattr(
        deploy_service,
        "_load_funnel_runtime_artifact_payload_for_apply",
        lambda *, artifact_id: {"meta": {"artifactId": artifact_id}, "products": {}},
    )
    monkeypatch.setattr(
        deploy_service,
        "_apply_publish_job_artifact_render_mode",
        lambda **kwargs: kwargs["workload_patch"],
    )
    monkeypatch.setattr(
        deploy_service,
        "ensure_plan_for_funnel_publish_workload",
        lambda **kwargs: {"plan_path": "/tmp/plan.json", "bootstrapped": False},
    )
    monkeypatch.setattr(
        deploy_service,
        "patch_workload_in_plan",
        lambda **kwargs: {
            "status": "ok",
            "updated_plan_path": "/tmp/plan.json",
        },
    )
    monkeypatch.setattr(
        deploy_service,
        "_resolve_publish_job_workspace_server_names",
        lambda **kwargs: ["shoptenorco.com"],
    )
    monkeypatch.setattr(
        deploy_service,
        "_validate_standalone_funnel_artifact_preflight",
        lambda **kwargs: None,
    )

    async def _default_tracking_validation(**kwargs):
        return {"status": "validated", "startUrl": kwargs["access_urls"][0]}

    monkeypatch.setattr(
        deploy_service,
        "_run_funnel_tracking_post_deploy_validation",
        _default_tracking_validation,
    )


def test_build_funnel_tracking_validation_plan_for_presales_flow():
    plan = deploy_service._build_funnel_tracking_validation_plan(
        artifact_payload=_build_tracking_validation_artifact_payload(include_presales=True),
        funnel_id="funnel-123",
        publication_id="00000000-0000-0000-0000-000000000999",
        access_urls=["https://shop.shopemberco.com/"],
        render_mode="html_deploy",
    )

    assert plan["sales_page"]["slug"] == "sales-page"
    path_plan = plan["path_plans"][0]
    assert path_plan["start_page"]["slug"] == "presales"
    assert deploy_service._expected_presales_source_page_type(path_plan=path_plan) == "listical_presell"
    assert path_plan["pre_sales_click_selectors"] == ["#to-sales"]
    assert [target["selector"] for target in path_plan["checkout_targets"]] == ["#checkout-btn"]
    assert path_plan["expected_internal_events"] == [
        "pre_sales_page_view",
        "presell_page_view",
        "pre_sales_to_sales_click",
        "sales_page_view",
        "offer_page_view",
        "sales_to_checkout_click",
    ]
    assert path_plan["expected_meta_events"] == [
        "PageView",
        "EnteredPresales",
        "Entered Presales Page",
        "PreSalesToSalesClick",
        "PageView",
        "Entered Sales Page",
        "EnteredSales",
        "ViewContent",
        "AddToCart",
        "SalesToCheckoutClick",
        "SalesToCheckoutClicked",
    ]
    assert path_plan["expected_posthog_events"] == [
        "pre_sales_page_view",
        "PageView",
        "presell_page_view",
        "EnteredPresales",
        "Entered Presales Page",
        "pre_sales_to_sales_click",
        "cta_click",
        "PreSalesToSalesClick",
        "sales_page_view",
        "PageView",
        "Entered Sales Page",
        "EnteredSales",
        "ViewContent",
        "offer_page_view",
        "sales_to_checkout_click",
        "AddToCart",
        "SalesToCheckoutClick",
        "SalesToCheckoutClicked",
    ]
    assert path_plan["required_posthog_readback_events"] == [
        "presell_page_view",
        "EnteredPresales",
        "cta_click",
        "PreSalesToSalesClick",
        "scroll_depth",
        "qualified_session",
        "section_view",
        "proof_view",
        "cta_view",
        "sales_page_view",
        "EnteredSales",
        "AddToCart",
        "SalesToCheckoutClick",
        "SalesToCheckoutClicked",
    ]
    assert sorted(page["slug"] for page in plan["pages_to_validate"]) == [
        "presales",
        "sales-page",
    ]


def test_build_funnel_tracking_validation_plan_requires_quiz_posthog_readback_events():
    plan = deploy_service._build_funnel_tracking_validation_plan(
        artifact_payload=_build_tracking_validation_artifact_payload(
            include_presales=True,
            presales_artifact_kind="quiz",
        ),
        funnel_id="funnel-123",
        publication_id="00000000-0000-0000-0000-000000000999",
        access_urls=["https://shop.shopemberco.com/"],
        render_mode="html_deploy",
    )

    path_plan = plan["path_plans"][0]
    assert path_plan["start_page"]["html_artifact_kind"] == "quiz"
    assert deploy_service._expected_presales_source_page_type(path_plan=path_plan) == "quiz_presell"
    assert path_plan["required_posthog_readback_events"] == [
        "presell_page_view",
        "EnteredPresales",
        "cta_click",
        "PreSalesToSalesClick",
        "scroll_depth",
        "qualified_session",
        "section_view",
        "proof_view",
        "cta_view",
        "QuizLeadViewed",
        "QuizQuestionViewed",
        "QuizOptionPresented",
        "QuizResultViewed",
        "QuizMechanismViewed",
        "QuizProofViewed",
        "QuizRecommendationViewed",
        "QuizCtaViewed",
        "QuizOptionSelected",
        "QuizQuestionSubmitted",
        "QuizCompleted",
        "sales_page_view",
        "EnteredSales",
        "AddToCart",
        "SalesToCheckoutClick",
        "SalesToCheckoutClicked",
    ]


@pytest.mark.parametrize(
    (
        "include_presales",
        "presales_artifact_kind",
        "expected_profile",
        "required_readback_events",
    ),
    [
        (
            True,
            "listicle",
            "listical_presell",
            {
                "presell_page_view",
                "EnteredPresales",
                "cta_click",
                "PreSalesToSalesClick",
                "scroll_depth",
                "qualified_session",
                "section_view",
                "proof_view",
                "cta_view",
                "sales_page_view",
                "EnteredSales",
                "AddToCart",
                "SalesToCheckoutClick",
                "SalesToCheckoutClicked",
            },
        ),
        (
            True,
            "quiz",
            "quiz_presell",
            {
                "presell_page_view",
                "EnteredPresales",
                "cta_click",
                "PreSalesToSalesClick",
                "scroll_depth",
                "qualified_session",
                "section_view",
                "proof_view",
                "cta_view",
                "QuizLeadViewed",
                "QuizQuestionViewed",
                "QuizOptionPresented",
                "QuizResultViewed",
                "QuizMechanismViewed",
                "QuizProofViewed",
                "QuizRecommendationViewed",
                "QuizCtaViewed",
                "QuizOptionSelected",
                "QuizQuestionSubmitted",
                "QuizCompleted",
                "sales_page_view",
                "EnteredSales",
                "AddToCart",
                "SalesToCheckoutClick",
                "SalesToCheckoutClicked",
            },
        ),
        (
            False,
            "sales",
            "sales",
            {
                "sales_page_view",
                "EnteredSales",
                "AddToCart",
                "SalesToCheckoutClick",
                "SalesToCheckoutClicked",
            },
        ),
    ],
)
def test_html_deploy_production_ready_validation_contract_requires_live_posthog_readback(
    include_presales,
    presales_artifact_kind,
    expected_profile,
    required_readback_events,
):
    plan = deploy_service._build_funnel_tracking_validation_plan(
        artifact_payload=_build_tracking_validation_artifact_payload(
            include_presales=include_presales,
            presales_artifact_kind=presales_artifact_kind,
        ),
        funnel_id="funnel-123",
        publication_id="00000000-0000-0000-0000-000000000999",
        access_urls=["https://shop.shopemberco.com/"],
        render_mode="html_deploy",
    )

    path_plan = plan["path_plans"][0]
    observed_readback_events = set(path_plan["required_posthog_readback_events"])
    assert path_plan["tracking_validation_profile"] == expected_profile
    assert required_readback_events.issubset(observed_readback_events)
    assert deploy_service._tracking_path_requires_live_posthog_readback(path_plan=path_plan)
    assert "PageView" in path_plan["expected_meta_events"]
    assert "PageView" in path_plan["expected_posthog_events"]
    assert "PageView" not in observed_readback_events

    if include_presales:
        assert path_plan["pre_sales_click_selectors"] == ["#to-sales"]
        assert "EnteredPresales" in path_plan["expected_meta_events"]
        assert "PreSalesToSalesClick" in path_plan["expected_meta_events"]
        assert "EnteredSales" in path_plan["expected_meta_events"]
        assert deploy_service._expected_presales_source_page_type(path_plan=path_plan) == expected_profile
    else:
        assert path_plan["pre_sales_click_selectors"] == []
        assert "EnteredPresales" not in path_plan["expected_meta_events"]
        assert deploy_service._expected_presales_source_page_type(path_plan=path_plan) == ""


def test_build_funnel_tracking_validation_plan_marks_candidate_release():
    plan = deploy_service._build_funnel_tracking_validation_plan(
        artifact_payload=_build_tracking_validation_artifact_payload(include_presales=True),
        funnel_id="funnel-123",
        publication_id="00000000-0000-0000-0000-000000000999",
        access_urls=["https://shop.shopemberco.com/"],
        render_mode="html_deploy",
        candidate_release_id="candidate-123",
    )

    assert plan["candidate_release_id"] == "candidate-123"
    assert plan["path_plans"][0]["candidate_release_id"] == "candidate-123"


def test_run_html_deploy_lighthouse_validation_audits_candidate_pages(monkeypatch):
    calls: list[list[str]] = []

    def _fake_run(args, **kwargs):
        calls.append([str(arg) for arg in args])
        output_arg = next(str(arg) for arg in args if str(arg).startswith("--output-path="))
        output_path = Path(output_arg.split("=", 1)[1])
        profile = "desktop" if "--preset=desktop" in args else "mobile"
        output_path.write_text(
            json.dumps(
                {
                    "categories": {
                        "performance": {"score": 0.91 if profile == "mobile" else 0.93}
                    },
                    "audits": {
                        "largest-contentful-paint": {
                            "score": 0.9,
                            "numericValue": 1800,
                            "displayValue": "1.8 s",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        return deploy_service.subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(deploy_service.settings, "DEPLOY_HTML_DEPLOY_LIGHTHOUSE_ENABLED", True)
    monkeypatch.setattr(
        deploy_service.settings,
        "DEPLOY_HTML_DEPLOY_LIGHTHOUSE_COMMAND",
        "lighthouse",
    )
    monkeypatch.setattr(
        deploy_service.settings,
        "DEPLOY_HTML_DEPLOY_LIGHTHOUSE_MOBILE_MIN_SCORE",
        85.0,
    )
    monkeypatch.setattr(
        deploy_service.settings,
        "DEPLOY_HTML_DEPLOY_LIGHTHOUSE_DESKTOP_MIN_SCORE",
        85.0,
    )
    monkeypatch.setattr(deploy_service.subprocess, "run", _fake_run)

    result = deploy_service._run_html_deploy_lighthouse_validation_sync(
        validation_plan={
            "render_mode": "html_deploy",
            "candidate_release_id": "candidate-123",
            "pages_to_validate": [
                {"url": "https://shop.example.com/listicle/"},
                {"url": "https://shop.example.com/sales-page/"},
            ],
        }
    )

    assert result is not None
    assert result["status"] == "passed"
    assert result["thresholds"] == {"mobile": 85.0, "desktop": 85.0}
    assert [audit["profile"] for audit in result["audits"]] == [
        "mobile",
        "desktop",
        "mobile",
        "desktop",
    ]
    assert all(
        "mos_deploy_candidate_release=candidate-123" in audit["url"]
        for audit in result["audits"]
    )
    assert len(calls) == 4
    assert any("--preset=desktop" in call for call in calls)


def test_run_html_deploy_lighthouse_validation_fails_under_threshold(monkeypatch):
    def _fake_run(args, **kwargs):
        output_arg = next(str(arg) for arg in args if str(arg).startswith("--output-path="))
        output_path = Path(output_arg.split("=", 1)[1])
        profile = "desktop" if "--preset=desktop" in args else "mobile"
        output_path.write_text(
            json.dumps(
                {
                    "categories": {
                        "performance": {"score": 0.9 if profile == "desktop" else 0.84}
                    },
                    "audits": {},
                }
            ),
            encoding="utf-8",
        )
        return deploy_service.subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(deploy_service.settings, "DEPLOY_HTML_DEPLOY_LIGHTHOUSE_ENABLED", True)
    monkeypatch.setattr(
        deploy_service.settings,
        "DEPLOY_HTML_DEPLOY_LIGHTHOUSE_COMMAND",
        "lighthouse",
    )
    monkeypatch.setattr(
        deploy_service.settings,
        "DEPLOY_HTML_DEPLOY_LIGHTHOUSE_MOBILE_MIN_SCORE",
        85.0,
    )
    monkeypatch.setattr(
        deploy_service.settings,
        "DEPLOY_HTML_DEPLOY_LIGHTHOUSE_DESKTOP_MIN_SCORE",
        85.0,
    )
    monkeypatch.setattr(deploy_service.subprocess, "run", _fake_run)

    with pytest.raises(deploy_service.DeployError, match="below required 85.00"):
        deploy_service._run_html_deploy_lighthouse_validation_sync(
            validation_plan={
                "render_mode": "html_deploy",
                "candidate_release_id": "candidate-123",
                "pages_to_validate": [{"url": "https://shop.example.com/sales-page/"}],
            }
        )


class _HtmlDeployOptimizationFakeResponse:
    def __init__(
        self,
        *,
        text: str = "",
        status_code: int = 200,
        content_type: str = "text/html; charset=utf-8",
    ) -> None:
        self.text = text
        self.status_code = status_code
        self.headers = {"content-type": content_type}
        self.request = deploy_service.httpx.Request("GET", "https://shop.example.com/")
        self.response = deploy_service.httpx.Response(status_code, request=self.request)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise deploy_service.httpx.HTTPStatusError(
                "request failed",
                request=self.request,
                response=self.response,
            )


def _optimized_html_fixture() -> str:
    return """
<!doctype html>
<html>
  <head>
    <style data-mos-render-optimization="true">body{margin:0}</style>
    <link rel="preconnect" href="https://cdn.example.com">
    <link rel="preload" as="font" href="/assets/font.woff2" data-mos-font-preload="true">
    <link
      rel="preload"
      as="image"
      href="/assets/hero-1200w.webp"
      imagesrcset="/assets/hero-800w.webp 800w, /assets/hero-1200w.webp 1200w"
      fetchpriority="high"
    >
  </head>
  <body>
    <picture>
      <source
        srcset="/assets/hero-800w.webp 800w, /assets/hero-1200w.webp 1200w"
        type="image/webp"
      >
      <img
        src="/assets/hero-1200w.webp"
        srcset="/assets/hero-800w.webp 800w, /assets/hero-1200w.webp 1200w"
        loading="eager"
        decoding="async"
        fetchpriority="high"
      >
    </picture>
    <img
      src="/assets/section.webp"
      srcset="/assets/section-800w.webp 800w"
      loading="lazy"
      decoding="async"
      fetchpriority="low"
    >
  </body>
</html>
"""


def test_run_html_deploy_optimization_validation_checks_candidate_pages(monkeypatch):
    requested_urls: list[str] = []

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def get(self, url):
            requested_urls.append(str(url))
            if "/assets/" in str(url):
                return _HtmlDeployOptimizationFakeResponse(content_type="image/webp")
            return _HtmlDeployOptimizationFakeResponse(text=_optimized_html_fixture())

    monkeypatch.setattr(deploy_service.httpx, "Client", FakeClient)

    result = deploy_service._run_html_deploy_optimization_validation_sync(
        validation_plan={
            "render_mode": "html_deploy",
            "candidate_release_id": "candidate-123",
            "pages_to_validate": [
                {
                    "url": "https://shop.example.com/listicle/",
                    "stage": "pre_sales",
                    "html_artifact_kind": "listicle",
                },
                {
                    "url": "https://shop.example.com/sales-page/",
                    "stage": "sales",
                    "html_artifact_kind": "sales",
                },
            ],
        }
    )

    assert result is not None
    assert result["status"] == "passed"
    assert result["candidateReleaseId"] == "candidate-123"
    assert len(result["pages"]) == 2
    assert result["pages"][0]["renderOptimizationCss"] is True
    assert result["pages"][0]["tailwindRuntimeRemoved"] is True
    assert result["pages"][0]["legacyIm8ScriptsRemoved"] is True
    assert result["pages"][0]["rasterImageCount"] == 2
    assert result["pages"][0]["responsiveImageCount"] >= 2
    assert result["pages"][0]["lazyImageCount"] == 1
    assert result["pages"][0]["highPriorityImageCount"] == 1
    assert result["pages"][0]["imagePreloadCount"] == 1
    assert result["pages"][0]["fontPreloadCount"] == 1
    page_requests = [url for url in requested_urls if "/assets/" not in url]
    assert all("mos_deploy_candidate_release=candidate-123" in url for url in page_requests)


def test_run_html_deploy_optimization_validation_fails_without_render_marker(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def get(self, url):
            return _HtmlDeployOptimizationFakeResponse(
                text="<!doctype html><html><body>No optimization markers</body></html>"
            )

    monkeypatch.setattr(deploy_service.httpx, "Client", FakeClient)

    with pytest.raises(deploy_service.DeployError, match="missing data-mos-render-optimization"):
        deploy_service._run_html_deploy_optimization_validation_sync(
            validation_plan={
                "render_mode": "html_deploy",
                "candidate_release_id": "candidate-123",
                "pages_to_validate": [
                    {
                        "url": "https://shop.example.com/sales-page/",
                        "stage": "sales",
                        "html_artifact_kind": "sales",
                    }
                ],
            }
        )


def test_run_html_deploy_optimization_validation_fails_broken_image(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def get(self, url):
            if "/assets/" in str(url):
                return _HtmlDeployOptimizationFakeResponse(
                    status_code=404,
                    content_type="text/html",
                )
            return _HtmlDeployOptimizationFakeResponse(text=_optimized_html_fixture())

    monkeypatch.setattr(deploy_service.httpx, "Client", FakeClient)

    with pytest.raises(deploy_service.DeployError, match="image assets did not resolve"):
        deploy_service._run_html_deploy_optimization_validation_sync(
            validation_plan={
                "render_mode": "html_deploy",
                "candidate_release_id": "candidate-123",
                "pages_to_validate": [
                    {
                        "url": "https://shop.example.com/listicle/",
                        "stage": "pre_sales",
                        "html_artifact_kind": "listicle",
                    }
                ],
            }
        )


@pytest.mark.asyncio
async def test_run_funnel_tracking_post_deploy_validation_includes_lighthouse_report(monkeypatch):
    monkeypatch.setattr(
        deploy_service,
        "_run_funnel_tracking_post_deploy_validation_sync",
        lambda *, validation_plan: [{"validationId": "deploy-validation-123"}],
    )
    monkeypatch.setattr(
        deploy_service,
        "_run_html_deploy_optimization_validation_sync",
        lambda *, validation_plan: {
            "status": "passed",
            "candidateReleaseId": validation_plan.get("candidate_release_id"),
            "pages": [],
        },
    )
    monkeypatch.setattr(
        deploy_service,
        "_run_html_deploy_lighthouse_validation_sync",
        lambda *, validation_plan: {
            "status": "passed",
            "candidateReleaseId": validation_plan.get("candidate_release_id"),
            "audits": [],
        },
    )

    result = await deploy_service._run_funnel_tracking_post_deploy_validation(
        artifact_payload=_build_tracking_validation_artifact_payload(include_presales=True),
        funnel_id="funnel-123",
        publication_id="00000000-0000-0000-0000-000000000999",
        access_urls=["https://shop.shopemberco.com/"],
        render_mode="html_deploy",
        candidate_release_id="candidate-123",
    )

    assert result["candidateReleaseId"] == "candidate-123"
    assert result["optimizationValidation"] == {
        "status": "passed",
        "candidateReleaseId": "candidate-123",
        "pages": [],
    }
    assert result["lighthouseValidation"] == {
        "status": "passed",
        "candidateReleaseId": "candidate-123",
        "audits": [],
    }


def test_build_funnel_tracking_validation_plan_for_direct_sales_flow():
    plan = deploy_service._build_funnel_tracking_validation_plan(
        artifact_payload=_build_tracking_validation_artifact_payload(include_presales=False),
        funnel_id="funnel-123",
        publication_id="00000000-0000-0000-0000-000000000999",
        access_urls=["https://shop.shopemberco.com/"],
        render_mode="html_deploy",
    )

    path_plan = plan["path_plans"][0]
    assert path_plan["start_page"]["slug"] == "sales-page"
    assert path_plan["pre_sales_click_selectors"] == []
    assert path_plan["expected_internal_events"] == [
        "sales_page_view",
        "offer_page_view",
        "sales_to_checkout_click",
    ]
    assert path_plan["expected_meta_events"] == [
        "PageView",
        "Entered Sales Page",
        "EnteredSales",
        "ViewContent",
        "AddToCart",
        "SalesToCheckoutClick",
        "SalesToCheckoutClicked",
    ]
    assert path_plan["expected_posthog_events"] == [
        "sales_page_view",
        "PageView",
        "Entered Sales Page",
        "EnteredSales",
        "ViewContent",
        "offer_page_view",
        "sales_to_checkout_click",
        "AddToCart",
        "SalesToCheckoutClick",
        "SalesToCheckoutClicked",
    ]
    assert [page["slug"] for page in plan["pages_to_validate"]] == ["sales-page"]


def test_build_funnel_tracking_validation_plan_for_checkout_started_flow():
    artifact_payload = _build_tracking_validation_artifact_payload(include_presales=False)
    binding = (
        artifact_payload["products"]["ember"]["funnels"]["daily"]["pages"]["sales-page"]["puckData"]["content"][0]["props"][
            "instrumentationManifest"
        ]["bindings"][0]
    )
    binding["trackEventType"] = "checkout_started"

    plan = deploy_service._build_funnel_tracking_validation_plan(
        artifact_payload=artifact_payload,
        funnel_id="funnel-123",
        publication_id="00000000-0000-0000-0000-000000000999",
        access_urls=["https://shop.shopemberco.com/"],
        render_mode="html_deploy",
    )

    path_plan = plan["path_plans"][0]
    assert path_plan["checkout_targets"][0]["track_event_type"] == "checkout_started"
    assert path_plan["expected_internal_events"] == [
        "sales_page_view",
        "offer_page_view",
        "checkout_started",
    ]
    assert path_plan["expected_meta_events"] == [
        "PageView",
        "Entered Sales Page",
        "EnteredSales",
        "ViewContent",
        "InitiateCheckout",
    ]
    assert path_plan["expected_posthog_events"] == [
        "sales_page_view",
        "PageView",
        "Entered Sales Page",
        "EnteredSales",
        "ViewContent",
        "offer_page_view",
        "checkout_started",
        "InitiateCheckout",
    ]


def test_build_funnel_tracking_validation_plan_allows_null_external_checkout_urls():
    artifact_payload = _build_tracking_validation_artifact_payload(include_presales=True)
    checkout = (
        artifact_payload["products"]["ember"]["funnels"]["daily"]["pages"]["sales-page"]["puckData"]["content"][0]["props"][
            "instrumentationManifest"
        ]["bindings"][0]["checkout"]
    )
    checkout["externalUrlsByVariant"] = None

    plan = deploy_service._build_funnel_tracking_validation_plan(
        artifact_payload=artifact_payload,
        funnel_id="funnel-123",
        publication_id="00000000-0000-0000-0000-000000000999",
        access_urls=["https://shop.shopemberco.com/"],
        render_mode="html_deploy",
    )

    assert plan["path_plans"][0]["checkout_targets"][0]["external_urls"] == []


def test_validate_observed_tracking_events_accepts_expected_sequence():
    plan = deploy_service._build_funnel_tracking_validation_plan(
        artifact_payload=_build_tracking_validation_artifact_payload(include_presales=True),
        funnel_id="funnel-123",
        publication_id="00000000-0000-0000-0000-000000000999",
        access_urls=["https://shop.shopemberco.com/"],
        render_mode="html_deploy",
    )
    sales_url = (
        "https://shop.shopemberco.com/ember/daily/sales-page/"
        "?src=presale&from=listicle&source_page_type=listical_presell"
        "&from_stage=pre_sales&to_stage=sales"
        "&session_id=sess-1&visitor_id=anon-1&click_id=click-1"
    )
    handoff_props = {
        "session_id": "sess-1",
        "visitor_id": "anon-1",
        "click_id": "click-1",
        "source_page_type": "listical_presell",
        "from_stage": "pre_sales",
        "to_stage": "sales",
    }

    observed_state = {
        "internal": [
            {"eventType": "Entered Funnel"},
            {"eventType": "pre_sales_page_view"},
            {"eventType": "presell_page_view"},
            {"eventType": "pre_sales_to_sales_click", "props": {"destination_url": sales_url, **handoff_props}},
            {"eventType": "sales_page_view", "props": handoff_props},
            {"eventType": "offer_page_view"},
            {"eventType": "sales_to_checkout_click"},
        ],
        "meta": [
            ["init", "pixel-123"],
            ["track", "Entered Funnel", {}],
            ["track", "PageView", {}],
            ["track", "EnteredPresales", {}],
            ["track", "Entered Presales Page", {}],
            ["track", "PreSalesToSalesClick", handoff_props],
            ["track", "PageView", {}],
            ["track", "Entered Sales Page", {}],
            ["track", "EnteredSales", {"event_source_url": sales_url, **handoff_props}],
            ["track", "ViewContent", {}],
            ["track", "AddToCart", {}],
            ["track", "SalesToCheckoutClick", {}],
            ["track", "SalesToCheckoutClicked", {}],
        ],
        "posthog": {
            "inits": [
                [
                    "phc_test_123",
                    {
                        "api_host": "https://emb.shopemberco.com",
                        "ui_host": "https://us.posthog.com",
                    },
                ]
            ],
            "captures": [
                ["pre_sales_page_view", {}],
                ["PageView", {}],
                ["presell_page_view", {}],
                ["EnteredPresales", {}],
                ["Entered Presales Page", {}],
                ["pre_sales_to_sales_click", handoff_props],
                ["cta_click", handoff_props],
                ["PreSalesToSalesClick", handoff_props],
                ["sales_page_view", _expected_sales_posthog_context(**handoff_props)],
                ["PageView", {}],
                ["Entered Sales Page", {}],
                ["EnteredSales", _expected_sales_posthog_context(**handoff_props)],
                ["ViewContent", {}],
                ["offer_page_view", {}],
                ["sales_to_checkout_click", {}],
                ["AddToCart", {}],
                ["SalesToCheckoutClick", {}],
                ["SalesToCheckoutClicked", {}],
            ],
        },
    }

    deploy_service._validate_observed_tracking_events(
        path_plan=plan["path_plans"][0],
        observed_state=observed_state,
    )


def test_validate_observed_tracking_events_rejects_extra_sales_entry_meta_events():
    plan = deploy_service._build_funnel_tracking_validation_plan(
        artifact_payload=_build_tracking_validation_artifact_payload(include_presales=False),
        funnel_id="funnel-123",
        publication_id="00000000-0000-0000-0000-000000000999",
        access_urls=["https://shop.shopemberco.com/"],
        render_mode="html_deploy",
    )

    observed_state = {
        "internal": [
            {"eventType": "Entered Funnel"},
            {"eventType": "sales_page_view"},
            {"eventType": "offer_page_view"},
            {"eventType": "sales_to_checkout_click"},
        ],
        "meta": [
            ["init", "pixel-123"],
            ["track", "Entered Funnel", {}],
            ["track", "PageView", {}],
            ["track", "Entered Sales Page", {}],
            ["track", "EnteredSales", {}],
            ["track", "EnteredSales", {}],
            ["track", "ViewContent", {}],
            ["track", "AddToCart", {}],
            ["track", "SalesToCheckoutClick", {}],
            ["track", "SalesToCheckoutClicked", {}],
        ],
        "posthog": {
            "inits": [
                [
                    "phc_test_123",
                    {
                        "api_host": "https://emb.shopemberco.com",
                        "ui_host": "https://us.posthog.com",
                    },
                ]
            ],
            "captures": [
                ["sales_page_view", {}],
                ["PageView", {}],
                ["Entered Sales Page", {}],
                ["EnteredSales", {}],
                ["ViewContent", {}],
                ["offer_page_view", {}],
                ["sales_to_checkout_click", {}],
                ["AddToCart", {}],
                ["SalesToCheckoutClick", {}],
                ["SalesToCheckoutClicked", {}],
            ],
        },
    }

    with pytest.raises(deploy_service.DeployError, match="must fire only on sales_page_view loads"):
        deploy_service._validate_observed_tracking_events(
            path_plan=plan["path_plans"][0],
            observed_state=observed_state,
        )


def test_validate_observed_tracking_events_rejects_missing_sales_posthog_context():
    plan = deploy_service._build_funnel_tracking_validation_plan(
        artifact_payload=_build_tracking_validation_artifact_payload(include_presales=False),
        funnel_id="funnel-123",
        publication_id="00000000-0000-0000-0000-000000000999",
        access_urls=["https://shop.shopemberco.com/"],
        render_mode="html_deploy",
    )
    sales_url = "https://shop.shopemberco.com/ember/daily/sales-page/"

    observed_state = {
        "internal": [
            {"eventType": "Entered Funnel"},
            {"eventType": "sales_page_view"},
            {"eventType": "offer_page_view"},
            {"eventType": "sales_to_checkout_click"},
        ],
        "meta": [
            ["init", "pixel-123"],
            ["track", "Entered Funnel", {}],
            ["track", "PageView", {}],
            ["track", "Entered Sales Page", {}],
            ["track", "EnteredSales", {"event_source_url": sales_url}],
            ["track", "ViewContent", {}],
            ["track", "AddToCart", {}],
            ["track", "SalesToCheckoutClick", {}],
            ["track", "SalesToCheckoutClicked", {}],
        ],
        "posthog": {
            "inits": [
                [
                    "phc_test_123",
                    {
                        "api_host": "https://emb.shopemberco.com",
                        "ui_host": "https://us.posthog.com",
                    },
                ]
            ],
            "captures": [
                ["sales_page_view", {"session_id": "session-1", "visitor_id": "visitor-1"}],
                ["PageView", {}],
                ["Entered Sales Page", {}],
                ["EnteredSales", _expected_sales_posthog_context()],
                ["ViewContent", {}],
                ["offer_page_view", {}],
                ["sales_to_checkout_click", {}],
                ["AddToCart", {}],
                ["SalesToCheckoutClick", {}],
                ["SalesToCheckoutClicked", {}],
            ],
        },
    }

    with pytest.raises(deploy_service.DeployError, match="sales page PostHog funnel context"):
        deploy_service._validate_observed_tracking_events(
            path_plan=plan["path_plans"][0],
            observed_state=observed_state,
        )


def test_validate_observed_tracking_events_rejects_presales_sales_entry_meta_events():
    with pytest.raises(deploy_service.DeployError, match="must fire only on sales_page_view loads"):
        deploy_service._assert_sales_entry_meta_events_match_sales_loads(
            internal_events=["Entered Funnel", "pre_sales_page_view", "presell_page_view"],
            meta_event_names=["PageView", "EnteredPresales", "EnteredSales"],
            context_label="https://shoptenorco.com/quiz/",
        )


def test_validate_observed_tracking_events_requires_presales_sales_session_stitching():
    plan = deploy_service._build_funnel_tracking_validation_plan(
        artifact_payload=_build_tracking_validation_artifact_payload(include_presales=True),
        funnel_id="funnel-123",
        publication_id="00000000-0000-0000-0000-000000000999",
        access_urls=["https://shop.shopemberco.com/"],
        render_mode="html_deploy",
    )
    destination_url = (
        "https://shop.shopemberco.com/ember/daily/sales-page/"
        "?src=presale&from=listicle&source_page_type=listical_presell"
        "&from_stage=pre_sales&to_stage=sales"
        "&session_id=sess-1&visitor_id=anon-1&click_id=click-1"
    )
    handoff_props = {
        "session_id": "sess-1",
        "visitor_id": "anon-1",
        "click_id": "click-1",
        "source_page_type": "listical_presell",
        "from_stage": "pre_sales",
        "to_stage": "sales",
    }

    observed_state = {
        "internal": [
            {"eventType": "Entered Funnel"},
            {"eventType": "pre_sales_page_view"},
            {"eventType": "presell_page_view"},
            {
                "eventType": "pre_sales_to_sales_click",
                "props": {
                    "destination_url": destination_url,
                    **handoff_props,
                },
            },
            {
                "eventType": "sales_page_view",
                "props": handoff_props,
            },
            {"eventType": "offer_page_view"},
            {"eventType": "sales_to_checkout_click"},
        ],
        "meta": [
            ["init", "pixel-123"],
            ["track", "Entered Funnel", {}],
            ["track", "PageView", {}],
            ["track", "EnteredPresales", {}],
            ["track", "Entered Presales Page", {}],
            ["track", "PreSalesToSalesClick", handoff_props],
            ["track", "PageView", {}],
            ["track", "Entered Sales Page", {}],
            [
                "track",
                "EnteredSales",
                {
                    "event_source_url": destination_url,
                    **handoff_props,
                },
            ],
            ["track", "ViewContent", {}],
            ["track", "AddToCart", {}],
            ["track", "SalesToCheckoutClick", {}],
            ["track", "SalesToCheckoutClicked", {}],
        ],
        "posthog": {
            "inits": [["phc_test_123", {"api_host": "https://emb.shopemberco.com", "ui_host": "https://us.posthog.com"}]],
            "captures": [
                ["pre_sales_page_view", {}],
                ["PageView", {}],
                ["presell_page_view", {}],
                ["EnteredPresales", {}],
                ["Entered Presales Page", {}],
                ["pre_sales_to_sales_click", handoff_props],
                ["cta_click", handoff_props],
                ["PreSalesToSalesClick", handoff_props],
                [
                    "sales_page_view",
                    _expected_sales_posthog_context(
                        **handoff_props,
                    ),
                ],
                ["PageView", {}],
                ["Entered Sales Page", {}],
                [
                    "EnteredSales",
                    _expected_sales_posthog_context(
                        **handoff_props,
                    ),
                ],
                ["ViewContent", {}],
                ["offer_page_view", {}],
                ["sales_to_checkout_click", {}],
                ["AddToCart", {}],
                ["SalesToCheckoutClick", {}],
                ["SalesToCheckoutClicked", {}],
            ],
        },
    }

    deploy_service._validate_observed_tracking_events(
        path_plan=plan["path_plans"][0],
        observed_state=observed_state,
    )

    stale_listical_context_state = json.loads(json.dumps(observed_state))
    for internal_event in stale_listical_context_state["internal"]:
        props = internal_event.get("props") if isinstance(internal_event, dict) else None
        if isinstance(props, dict) and props.get("source_page_type"):
            props["source_page_type"] = "listicle"
    for capture in stale_listical_context_state["posthog"]["captures"]:
        if isinstance(capture[1], dict) and capture[1].get("source_page_type"):
            capture[1]["source_page_type"] = "listicle"
    for meta_call in stale_listical_context_state["meta"]:
        if len(meta_call) >= 3 and isinstance(meta_call[2], dict) and meta_call[2].get("source_page_type"):
            meta_call[2]["source_page_type"] = "listicle"
    with pytest.raises(deploy_service.DeployError, match="source_page_type"):
        deploy_service._validate_observed_tracking_events(
            path_plan=plan["path_plans"][0],
            observed_state=stale_listical_context_state,
        )

    quiz_plan = deploy_service._build_funnel_tracking_validation_plan(
        artifact_payload=_build_tracking_validation_artifact_payload(
            include_presales=True,
            presales_artifact_kind="quiz",
        ),
        funnel_id="funnel-123",
        publication_id="00000000-0000-0000-0000-000000000999",
        access_urls=["https://shop.shopemberco.com/"],
        render_mode="html_deploy",
    )
    quiz_state = json.loads(json.dumps(observed_state))
    quiz_destination_url = destination_url.replace("from=listicle", "from=quiz").replace(
        "source_page_type=listical_presell",
        "source_page_type=quiz_presell",
    )
    for internal_event in quiz_state["internal"]:
        props = internal_event.get("props") if isinstance(internal_event, dict) else None
        if isinstance(props, dict) and props.get("source_page_type"):
            props["source_page_type"] = "quiz_presell"
        if isinstance(props, dict) and props.get("destination_url"):
            props["destination_url"] = quiz_destination_url
    for capture in quiz_state["posthog"]["captures"]:
        if isinstance(capture[1], dict) and capture[1].get("source_page_type"):
            capture[1]["source_page_type"] = "quiz_presell"
        if isinstance(capture[1], dict) and capture[1].get("destination_url"):
            capture[1]["destination_url"] = quiz_destination_url
    for meta_call in quiz_state["meta"]:
        if len(meta_call) >= 3 and isinstance(meta_call[2], dict) and meta_call[2].get("source_page_type"):
            meta_call[2]["source_page_type"] = "quiz_presell"
        if len(meta_call) >= 3 and isinstance(meta_call[2], dict) and meta_call[2].get("event_source_url"):
            meta_call[2]["event_source_url"] = quiz_destination_url
    deploy_service._validate_observed_tracking_events(
        path_plan=quiz_plan["path_plans"][0],
        observed_state=quiz_state,
    )

    missing_quiz_context_state = json.loads(json.dumps(quiz_state))
    missing_quiz_context_state["posthog"]["captures"][8][1].pop("source_page_type")
    with pytest.raises(deploy_service.DeployError, match="source_page_type"):
        deploy_service._validate_observed_tracking_events(
            path_plan=quiz_plan["path_plans"][0],
            observed_state=missing_quiz_context_state,
        )

    missing_click_bridge_state = json.loads(json.dumps(observed_state))
    missing_click_props = missing_click_bridge_state["internal"][3]["props"]
    missing_click_props.pop("session_id")
    missing_click_props.pop("visitor_id")
    missing_click_props.pop("click_id")
    with pytest.raises(deploy_service.DeployError, match="missing canonical handoff values"):
        deploy_service._validate_observed_tracking_events(
            path_plan=plan["path_plans"][0],
            observed_state=missing_click_bridge_state,
        )

    url_params_only_state = json.loads(json.dumps(observed_state))
    for capture in url_params_only_state["posthog"]["captures"]:
        if capture[0] in {"sales_page_view", "EnteredSales"}:
            capture[1].pop("session_id", None)
            capture[1].pop("visitor_id", None)
            capture[1].pop("click_id", None)
            capture[1]["url_params"] = {
                "session_id": "sess-1",
                "visitor_id": "anon-1",
                "click_id": "click-1",
            }
    with pytest.raises(deploy_service.DeployError, match="one canonical"):
        deploy_service._validate_observed_tracking_events(
            path_plan=plan["path_plans"][0],
            observed_state=url_params_only_state,
        )

    anonymous_only_state = json.loads(json.dumps(observed_state))
    for internal_event in anonymous_only_state["internal"]:
        props = internal_event.get("props") if isinstance(internal_event, dict) else None
        if isinstance(props, dict) and props.get("visitor_id"):
            props["anonymous_id"] = props.pop("visitor_id")
            props.pop("visitorId", None)
    with pytest.raises(deploy_service.DeployError, match="visitor_id"):
        deploy_service._validate_observed_tracking_events(
            path_plan=plan["path_plans"][0],
            observed_state=anonymous_only_state,
        )

    url_missing_stage_context_state = json.loads(json.dumps(observed_state))
    stripped_destination_url = (
        "https://shop.shopemberco.com/ember/daily/sales-page/"
        "?src=presale&from=listicle&source_page_type=listical_presell"
        "&session_id=sess-1&visitor_id=anon-1&click_id=click-1"
    )
    url_missing_stage_context_state["internal"][3]["props"]["destination_url"] = stripped_destination_url
    with pytest.raises(deploy_service.DeployError, match="from_stage"):
        deploy_service._validate_observed_tracking_events(
            path_plan=plan["path_plans"][0],
            observed_state=url_missing_stage_context_state,
        )

    legacy_rmbc_only_state = json.loads(json.dumps(observed_state))
    for capture in legacy_rmbc_only_state["posthog"]["captures"]:
        if capture[0] in {"sales_page_view", "EnteredSales"}:
            capture[1].pop("visitor_id", None)
            capture[1].pop("visitorId", None)
            capture[1]["rmbc_anonymous_id"] = "anon-1"
    with pytest.raises(deploy_service.DeployError, match="one canonical"):
        deploy_service._validate_observed_tracking_events(
            path_plan=plan["path_plans"][0],
            observed_state=legacy_rmbc_only_state,
        )

    observed_state["posthog"]["captures"][8][1]["session_id"] = "other-session"
    with pytest.raises(deploy_service.DeployError, match="one canonical"):
        deploy_service._validate_observed_tracking_events(
            path_plan=plan["path_plans"][0],
            observed_state=observed_state,
        )


def test_validate_observed_tracking_events_rejects_public_events_400():
    with pytest.raises(deploy_service.DeployError, match="/public/events returned non-2xx"):
        deploy_service._assert_public_events_requests_succeeded(
            observed_state={
                "network": {
                    "publicEvents": [
                        {
                            "url": "https://shop.shopemberco.com/api/public/events",
                            "status": 400,
                            "ok": False,
                        }
                    ]
                }
            }
        )


def test_validate_observed_tracking_events_rejects_missing_checkout_event():
    plan = deploy_service._build_funnel_tracking_validation_plan(
        artifact_payload=_build_tracking_validation_artifact_payload(include_presales=False),
        funnel_id="funnel-123",
        publication_id="00000000-0000-0000-0000-000000000999",
        access_urls=["https://shop.shopemberco.com/"],
        render_mode="html_deploy",
    )

    observed_state = {
        "internal": [
            {"eventType": "Entered Funnel"},
            {"eventType": "sales_page_view"},
            {"eventType": "offer_page_view"},
            {"eventType": "sales_to_checkout_click"},
        ],
        "meta": [
            ["init", "pixel-123"],
            ["track", "Entered Funnel", {}],
            ["track", "PageView", {}],
            ["track", "Entered Sales Page", {}],
            ["track", "EnteredSales", {}],
            ["track", "ViewContent", {}],
        ],
        "posthog": {
            "inits": [
                [
                    "phc_test_123",
                    {
                        "api_host": "https://emb.shopemberco.com",
                        "ui_host": "https://us.posthog.com",
                    },
                ]
            ],
            "captures": [
                ["sales_page_view", {}],
                ["offer_page_view", {}],
                ["sales_to_checkout_click", {}],
            ],
        },
    }

    with pytest.raises(deploy_service.DeployError, match="Meta Pixel events"):
        deploy_service._validate_observed_tracking_events(
            path_plan=plan["path_plans"][0],
            observed_state=observed_state,
        )


def test_activate_tracking_validation_target_uses_dom_click():
    calls: list[object] = []

    class FakeLocator:
        @property
        def first(self):
            return self

        def wait_for(self, *, state=None, timeout=None):
            calls.append(("wait_for", state, timeout))

        def evaluate(self, script):
            calls.append(("evaluate", script))

    class FakePage:
        url = "https://shoptenorco.com/8b89a76d/be65d76e/sales-page/"

        def locator(self, selector):
            calls.append(("locator", selector))
            return FakeLocator()

    deploy_service._activate_tracking_validation_target(page=FakePage(), selector="#checkout-btn")

    assert calls[0] == ("locator", "#checkout-btn")
    assert calls[1] == ("wait_for", "attached", deploy_service._DEPLOY_TRACKING_VALIDATION_PAGE_TIMEOUT_MS)
    assert calls[2][0] == "evaluate"
    assert "element.click()" in calls[2][1]


def test_wait_for_tracking_validation_state_polls_until_events_settle(monkeypatch):
    states = [
        {
            "internal": [],
            "meta": [],
            "posthog": {"inits": [], "captures": []},
            "network": {"publicEvents": []},
        },
        {
            "internal": [{"eventType": "sales_page_view"}],
            "meta": [],
            "posthog": {"inits": [], "captures": []},
            "network": {"publicEvents": []},
        },
    ]
    waits: list[int] = []

    monkeypatch.setattr(deploy_service, "_DEPLOY_TRACKING_VALIDATION_ASSERTION_TIMEOUT_MS", 500)
    monkeypatch.setattr(deploy_service, "_DEPLOY_TRACKING_VALIDATION_ASSERTION_POLL_MS", 150)

    class FakePage:
        def evaluate(self, script):
            return states.pop(0) if states else {
                "internal": [{"eventType": "sales_page_view"}],
                "meta": [],
                "posthog": {"inits": [], "captures": []},
                "network": {"publicEvents": []},
            }

        def wait_for_timeout(self, ms):
            waits.append(ms)

    observed_state = deploy_service._wait_for_tracking_validation_state(
        page=FakePage(),
        path_plan={
            "expected_internal_events": ["sales_page_view"],
            "expected_meta_events": [],
            "expected_posthog_events": [],
            "tracking": {},
        },
    )

    assert observed_state["internal"] == [{"eventType": "sales_page_view"}]
    assert waits == [150]


def test_validate_posthog_live_readback_requires_api_key_for_required_events(monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_TRACKING_VALIDATION_POSTHOG_READBACK_API_KEY", None)

    with pytest.raises(deploy_service.DeployError, match="POSTHOG_READBACK_API_KEY"):
        deploy_service._validate_posthog_live_readback(
            path_plan={
                "required_posthog_readback_events": ["sales_page_view", "EnteredSales"],
                "tracking": {"posthogUiHost": "https://us.posthog.com"},
            },
            validation_id="deploy-validation-123",
        )


def test_validate_posthog_live_readback_polls_until_sales_aliases_land(monkeypatch):
    calls: list[object] = []
    payloads = [
        {
            "results": [
                _posthog_readback_raw_row("sales_page_view")
            ]
        },
        {
            "results": [
                _posthog_readback_raw_row("sales_page_view"),
                _posthog_readback_raw_row("EnteredSales"),
                _posthog_readback_raw_row("SalesToCheckoutClick"),
            ]
        },
    ]

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return payloads.pop(0)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, **kwargs):
            calls.append(("post", url, kwargs["headers"]["Authorization"], kwargs["json"]))
            return FakeResponse()

    monkeypatch.setattr(deploy_service.settings, "DEPLOY_TRACKING_VALIDATION_POSTHOG_READBACK_API_KEY", "phx_test")
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_TRACKING_VALIDATION_POSTHOG_READBACK_TIMEOUT_SECONDS", 2.0)
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_TRACKING_VALIDATION_POSTHOG_READBACK_POLL_SECONDS", 0.5)
    monkeypatch.setattr(deploy_service.httpx, "Client", FakeClient)
    monkeypatch.setattr(deploy_service.time, "sleep", lambda seconds: calls.append(("sleep", seconds)))

    result = deploy_service._validate_posthog_live_readback(
        path_plan={
            "required_posthog_readback_events": [
                "sales_page_view",
                "EnteredSales",
                "SalesToCheckoutClick",
            ],
            "tracking": {"posthogUiHost": "https://us.posthog.com"},
        },
        validation_id="deploy-validation-123",
    )

    assert result is not None
    assert result["observedEvents"] == [
        "EnteredSales",
        "SalesToCheckoutClick",
        "sales_page_view",
    ]
    assert calls[0][0] == "post"
    assert calls[0][1] == "https://us.posthog.com/api/projects/@current/query/"
    assert calls[0][2] == "Bearer phx_test"
    assert ("sleep", 0.5) in calls


def test_assert_posthog_readback_rows_validates_canonical_handoff_context():
    plan = deploy_service._build_funnel_tracking_validation_plan(
        artifact_payload=_build_tracking_validation_artifact_payload(include_presales=True),
        funnel_id="funnel-123",
        publication_id="00000000-0000-0000-0000-000000000999",
        access_urls=["https://shop.shopemberco.com/"],
        render_mode="html_deploy",
    )
    path_plan = plan["path_plans"][0]
    destination_url = (
        "https://shop.example.com/sales/?mos_deploy_validation_id=deploy-validation-123"
        "&session_id=session-1&visitor_id=visitor-1&click_id=click-1"
        "&source_page_type=listical_presell&from_stage=pre_sales&to_stage=sales"
    )
    handoff_props = {
        "source_page_type": "listical_presell",
        "from_stage": "pre_sales",
        "to_stage": "sales",
        "destination_url": destination_url,
    }
    rows = [
        dict(
            zip(
                deploy_service._POSTHOG_READBACK_COLUMNS,
                _posthog_readback_raw_row(
                    "PreSalesToSalesClick",
                    content_category="pre_sales_page",
                    page_stage="pre_sales",
                    **handoff_props,
                ),
            )
        ),
        dict(zip(deploy_service._POSTHOG_READBACK_COLUMNS, _posthog_readback_raw_row("sales_page_view", **handoff_props))),
        dict(zip(deploy_service._POSTHOG_READBACK_COLUMNS, _posthog_readback_raw_row("EnteredSales", **handoff_props))),
    ]

    deploy_service._assert_posthog_readback_rows(
        rows=rows,
        required_events=["PreSalesToSalesClick", "sales_page_view", "EnteredSales"],
        validation_id="deploy-validation-123",
        path_plan=path_plan,
    )

    rows[1]["source_page_type"] = ""
    with pytest.raises(deploy_service.DeployError, match="source_page_type"):
        deploy_service._assert_posthog_readback_rows(
            rows=rows,
            required_events=["PreSalesToSalesClick", "sales_page_view", "EnteredSales"],
            validation_id="deploy-validation-123",
            path_plan=path_plan,
        )

    anonymous_only_rows = [dict(row) for row in rows]
    anonymous_only_rows[1]["source_page_type"] = "listical_presell"
    for row in anonymous_only_rows:
        row["anonymous_id"] = row["visitor_id"]
        row["visitor_id"] = ""
        row["visitorId"] = ""
    with pytest.raises(deploy_service.DeployError, match="visitor_id"):
        deploy_service._assert_posthog_readback_rows(
            rows=anonymous_only_rows,
            required_events=["PreSalesToSalesClick", "sales_page_view", "EnteredSales"],
            validation_id="deploy-validation-123",
            path_plan=path_plan,
        )


def test_assert_posthog_readback_rows_rejects_duplicate_quiz_completed():
    rows = [
        dict(zip(deploy_service._POSTHOG_READBACK_COLUMNS, _posthog_readback_raw_row("QuizCompleted"))),
        dict(zip(deploy_service._POSTHOG_READBACK_COLUMNS, _posthog_readback_raw_row("QuizCompleted"))),
    ]

    with pytest.raises(deploy_service.DeployError, match="QuizCompleted must fire once"):
        deploy_service._assert_posthog_readback_rows(
            rows=rows,
            required_events=["QuizCompleted"],
            validation_id="deploy-validation-123",
        )


def test_validate_deployed_tracking_html_checks_direct_meta_pixel_bootstrap(monkeypatch):
    requested_urls: list[str] = []

    class FakeResponse:
        def __init__(self, url: str, *, status_code: int = 200, text: str = ""):
            self.url = url
            self.status_code = status_code
            self.text = text

        def raise_for_status(self):
            if self.status_code >= 400:
                request = deploy_service.httpx.Request("GET", self.url)
                response = deploy_service.httpx.Response(
                    self.status_code,
                    request=request,
                    text=self.text,
                )
                raise deploy_service.httpx.HTTPStatusError(
                    "error",
                    request=request,
                    response=response,
                )

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, **kwargs):
            requested_urls.append(str(url))
            if str(url).endswith("/sales-page/"):
                return FakeResponse(
                    str(url),
                    text=(
                        '<script>const pixelId = "pixel-123"; '
                        'window.fbq("init", pixelId);</script>'
                        '<script src="https://connect.facebook.net/en_US/fbevents.js"></script>'
                    ),
                )
            return FakeResponse(str(url))

    monkeypatch.setattr(deploy_service.httpx, "Client", FakeClient)

    deploy_service._validate_deployed_tracking_html(
        validation_plan={
            "render_mode": deploy_service._FUNNEL_ARTIFACT_RENDER_MODE_STANDALONE_IMPORTED_HTML,
            "origin": "https://shoptenorco.com",
            "pages_to_validate": [
                {
                    "url": "https://shoptenorco.com/8b89a76d/be65d76e/sales-page/",
                    "tracking": {"metaPixelId": "pixel-123"},
                }
            ],
        }
    )

    assert requested_urls == ["https://shoptenorco.com/8b89a76d/be65d76e/sales-page/"]


def test_validate_deployed_tracking_html_rejects_legacy_mars_references(monkeypatch):
    class FakeResponse:
        text = '<script src="https://ss.mengotomars.com/pixel.js"></script>'
        status_code = 200

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(deploy_service.httpx, "Client", FakeClient)

    with pytest.raises(deploy_service.DeployError, match="forbidden legacy references"):
        deploy_service._validate_deployed_tracking_html(
            validation_plan={
                "render_mode": deploy_service._FUNNEL_ARTIFACT_RENDER_MODE_STANDALONE_IMPORTED_HTML,
                "origin": "https://shoptenorco.com",
                "pages_to_validate": [
                    {
                        "url": "https://shoptenorco.com/8b89a76d/daily-drive-essentials/quiz/",
                        "tracking": {},
                    }
                ],
            }
        )


def test_find_html_deploy_forbidden_references_detects_split_legacy_tokens():
    matches = deploy_service._find_html_deploy_forbidden_references(
        text="""
        <script>
          const legacyHost = ["men", "go", "to", "mars"].join("");
          const oldStore = ["shop", "mars"].join("");
        </script>
        """
    )

    assert "MenGoToMars compact tracking host" in matches
    assert "legacy shopmars storefront token" in matches


def test_run_funnel_tracking_post_deploy_validation_sync_uses_checkout_request_for_public_checkout(monkeypatch):
    calls: list[object] = []
    validated: dict[str, object] = {}

    monkeypatch.setattr(
        deploy_service,
        "_validate_deployed_tracking_html",
        lambda **kwargs: calls.append(("validate_html", kwargs["validation_plan"]["checkout_validated"])),
    )
    monkeypatch.setattr(
        deploy_service,
        "_validate_observed_tracking_events",
        lambda **kwargs: validated.update(kwargs),
    )

    class FakeExpectRequest:
        def __enter__(self):
            calls.append(("expect_request_enter",))
            return self

        def __exit__(self, exc_type, exc, tb):
            calls.append(("expect_request_exit", exc_type.__name__ if exc_type else None))
            return False

        @property
        def value(self):
            calls.append(("expect_request_value",))
            return {"url": "/api/public/checkout"}

    class FakeLocator:
        @property
        def first(self):
            return self

        def wait_for(self, *, state=None, timeout=None):
            calls.append(("locator_wait_for", state, timeout))

        def evaluate(self, script):
            calls.append(("locator_evaluate", script))

    class FakePage:
        url = "https://shoptenorco.com/8b89a76d/be65d76e/sales-page/"

        def locator(self, selector):
            calls.append(("locator", selector))
            return FakeLocator()

        def goto(self, url, **kwargs):
            calls.append(("goto", url, kwargs.get("wait_until"), kwargs.get("timeout")))

        def wait_for_timeout(self, ms):
            calls.append(("wait_for_timeout", ms))

        def wait_for_url(self, pattern, **kwargs):
            calls.append(("wait_for_url", getattr(pattern, "pattern", str(pattern)), kwargs.get("timeout")))

        def expect_request(self, pattern):
            calls.append(("expect_request", getattr(pattern, "pattern", str(pattern))))
            return FakeExpectRequest()

        def evaluate(self, script):
            calls.append(("page_evaluate",))
            return {
                "internal": [],
                "meta": [],
                "posthog": {"inits": [], "captures": []},
            }

    fake_page = FakePage()

    class FakeContext:
        def route(self, pattern, handler):
            calls.append(("route", pattern))

        def add_init_script(self, script):
            calls.append(("add_init_script", bool(script)))

        def new_page(self):
            calls.append(("new_page",))
            return fake_page

        def close(self):
            calls.append(("context_close",))

    class FakeBrowser:
        def new_context(self, **kwargs):
            calls.append(("new_context", kwargs))
            return FakeContext()

        def close(self):
            calls.append(("browser_close",))

    class FakePlaywrightManager:
        def __enter__(self):
            calls.append(("playwright_enter",))
            return SimpleNamespace(chromium=SimpleNamespace(launch=lambda: FakeBrowser()))

        def __exit__(self, exc_type, exc, tb):
            calls.append(("playwright_exit", exc_type.__name__ if exc_type else None))
            return False

    import playwright.sync_api as sync_api

    monkeypatch.setattr(sync_api, "sync_playwright", lambda: FakePlaywrightManager())

    deploy_service._run_funnel_tracking_post_deploy_validation_sync(
        validation_plan={
            "render_mode": "html_deploy",
            "origin": "https://shoptenorco.com",
            "checkout_validated": True,
            "path_plans": [
                {
                    "start_page": {"url": "https://shoptenorco.com/8b89a76d/be65d76e/sales-page/"},
                    "sales_page": {"url": "https://shoptenorco.com/8b89a76d/be65d76e/sales-page/"},
                    "pre_sales_click_selectors": [],
                    "checkout_targets": [
                        {
                            "selector": "#main-cta",
                            "mode": "public_checkout",
                            "external_urls": [],
                        }
                    ],
                    "tracking": {},
                    "expected_internal_events": [],
                    "expected_meta_events": [],
                    "expected_posthog_events": [],
                }
            ],
        }
    )

    assert (
        "expect_request",
        r".*/(?:api/)?public/checkout(?:/prepare(?:/[^/?]+(?:/consume)?)?)?(?:\?.*)?$",
    ) in calls
    assert not any(call[0] == "wait_for_url" for call in calls if isinstance(call, tuple))
    assert validated["observed_state"]["posthog"]["captures"] == []


@pytest.mark.asyncio
async def test_run_funnel_publish_job_purges_bunny_cache_after_reconcile(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    _install_publish_job_mocks(monkeypatch)

    calls: list[object] = []

    monkeypatch.setattr(
        deploy_service,
        "_reconcile_bunny_pull_zone_for_published_workload",
        lambda **kwargs: calls.append(("reconcile", kwargs["workload_name"]))
        or {
            "provider": "bunny",
            "pull_zone": {
                "id": 777,
                "name": "brand-funnels-70124684-be65d76e",
                "accessUrls": ["https://shoptenorco.com/"],
            },
        },
    )
    monkeypatch.setattr(
        deploy_service,
        "_purge_bunny_pull_zone_cache",
        lambda *, zone_id, cache_tag=None: calls.append(("purge", zone_id, cache_tag))
        or {"zoneId": zone_id, "status": "purged"},
    )

    job_id = "publish-job-success"
    job_path = _write_publish_job_fixture(
        tmp_path,
        job_id=job_id,
        deploy_request={
            "workload_patch": {"name": "brand-funnels-70124684-be65d76e"},
            "apply_plan": False,
            "bunny_pull_zone": True,
        },
    )

    await deploy_service._run_funnel_publish_job(job_id)

    job = json.loads(job_path.read_text(encoding="utf-8"))
    assert job["status"] == "succeeded"
    assert job["phase"] == "completed"
    assert calls == [
        ("reconcile", "brand-funnels-70124684-be65d76e"),
        ("purge", 777, None),
    ]
    assert job["access_urls"] == ["https://shoptenorco.com/"]
    assert job["result"]["deploy"]["cdn"]["cachePurge"] == {"zoneId": 777, "status": "purged"}


@pytest.mark.asyncio
async def test_run_funnel_publish_job_fails_when_bunny_cache_purge_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    _install_publish_job_mocks(monkeypatch)

    monkeypatch.setattr(
        deploy_service,
        "_reconcile_bunny_pull_zone_for_published_workload",
        lambda **kwargs: {
            "provider": "bunny",
            "pull_zone": {
                "id": 777,
                "name": "brand-funnels-70124684-be65d76e",
                "accessUrls": ["https://shoptenorco.com/"],
            },
        },
    )

    def _raise_purge_error(*, zone_id, cache_tag=None):
        raise deploy_service.DeployError(
            f"Bunny API request failed (POST /pullzone/{zone_id}/purgeCache) with status 500: purge failed"
        )

    monkeypatch.setattr(deploy_service, "_purge_bunny_pull_zone_cache", _raise_purge_error)

    job_id = "publish-job-purge-failure"
    job_path = _write_publish_job_fixture(
        tmp_path,
        job_id=job_id,
        deploy_request={
            "workload_patch": {"name": "brand-funnels-70124684-be65d76e"},
            "apply_plan": False,
            "bunny_pull_zone": True,
        },
    )

    await deploy_service._run_funnel_publish_job(job_id)

    job = json.loads(job_path.read_text(encoding="utf-8"))
    assert job["status"] == "failed"
    assert job["phase"] == "purging_bunny_cache"
    assert "purgeCache" in job["error"]


@pytest.mark.asyncio
async def test_run_funnel_publish_job_records_tracking_validation_result(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    _install_publish_job_mocks(monkeypatch)
    monkeypatch.setattr(
        deploy_service,
        "_load_funnel_runtime_artifact_payload_for_apply",
        lambda *, artifact_id: _build_tracking_validation_artifact_payload(include_presales=True),
    )

    captured: dict[str, object] = {}

    async def _tracking_validation(**kwargs):
        captured.update(kwargs)
        return {
            "startUrl": "https://shop.shopemberco.com/ember/daily/presales/",
            "expectedInternalEvents": ["pre_sales_page_view"],
        }

    monkeypatch.setattr(
        deploy_service,
        "_run_funnel_tracking_post_deploy_validation",
        _tracking_validation,
    )

    job_id = "publish-job-tracking-validation-success"
    job_path = _write_publish_job_fixture(
        tmp_path,
        job_id=job_id,
        deploy_request={
            "workload_patch": {"name": "brand-funnels-70124684-be65d76e"},
            "apply_plan": False,
            "access_urls": ["https://shop.shopemberco.com/"],
        },
    )

    await deploy_service._run_funnel_publish_job(job_id)

    job = json.loads(job_path.read_text(encoding="utf-8"))
    assert job["status"] == "succeeded"
    assert job["phase"] == "completed"
    assert captured["publication_id"] == "00000000-0000-0000-0000-000000000999"
    assert captured["funnel_id"] == "funnel-123"
    assert captured["access_urls"] == ["https://shop.shopemberco.com/"]
    assert job["result"]["deploy"]["trackingValidation"] == {
        "startUrl": "https://shop.shopemberco.com/ember/daily/presales/",
        "expectedInternalEvents": ["pre_sales_page_view"],
    }


@pytest.mark.asyncio
async def test_run_funnel_publish_job_runs_standalone_preflight_before_apply(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    _install_publish_job_mocks(monkeypatch)

    calls: list[str] = []
    monkeypatch.setattr(
        deploy_service,
        "_validate_standalone_funnel_artifact_preflight",
        lambda *, workload_patch: calls.append(str(workload_patch["name"])),
    )

    async def _apply_plan(**kwargs):
        return {
            "returncode": 0,
            "plan_path": "/tmp/plan.json",
            "materialized_plan_path": "/tmp/plan.json",
            "server_ips": {"ubuntu-4gb-hel1-2": "135.181.93.244"},
            "live_url": "http://135.181.93.244",
            "logs": "",
        }

    monkeypatch.setattr(deploy_service, "apply_plan", _apply_plan)
    monkeypatch.setattr(
        deploy_service,
        "_infer_external_access_urls",
        lambda **kwargs: ["https://shop.shopemberco.com/"],
    )

    job_id = "publish-job-standalone-preflight-success"
    job_path = _write_publish_job_fixture(
        tmp_path,
        job_id=job_id,
        deploy_request={
            "workload_patch": {"name": "brand-funnels-70124684-be65d76e"},
            "apply_plan": True,
            "validate_tracking_post_deploy": False,
        },
    )

    await deploy_service._run_funnel_publish_job(job_id)

    job = json.loads(job_path.read_text(encoding="utf-8"))
    assert calls == ["brand-funnels-70124684-be65d76e"]
    assert job["status"] == "succeeded"
    assert job["phase"] == "completed"


@pytest.mark.asyncio
async def test_run_funnel_publish_job_validates_candidate_before_activation(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    _install_publish_job_mocks(monkeypatch)
    monkeypatch.setattr(
        deploy_service,
        "_load_funnel_runtime_artifact_payload_for_apply",
        lambda *, artifact_id: _build_tracking_validation_artifact_payload(include_presales=True),
    )
    monkeypatch.setattr(
        deploy_service,
        "_build_html_deploy_candidate_release_id",
        lambda *, job_id: "candidate-123",
    )

    calls: list[tuple[str, object]] = []
    patched_workload: dict[str, object] = {}

    def _patch_workload(**kwargs):
        patched_workload.update(kwargs["workload_patch"])
        calls.append(("patch", kwargs["workload_patch"]["source_ref"]["release_metadata"].copy()))
        return {
            "status": "ok",
            "updated_plan_path": "/tmp/plan.json",
        }

    async def _apply_plan(**kwargs):
        calls.append(("apply", kwargs["workload_names"]))
        return {
            "returncode": 0,
            "plan_path": "/tmp/plan.json",
            "materialized_plan_path": "/tmp/plan.json",
            "server_ips": {"ubuntu-4gb-hel1-2": "135.181.93.244"},
            "live_url": "http://135.181.93.244",
            "logs": "",
        }

    async def _tracking_validation(**kwargs):
        calls.append(("validate", kwargs.get("candidate_release_id")))
        return {"status": "validated", "candidateReleaseId": kwargs.get("candidate_release_id")}

    def _activate_candidate(**kwargs):
        calls.append(("activate", kwargs["release_id"]))
        return {"status": "activated", "releaseId": kwargs["release_id"]}

    monkeypatch.setattr(deploy_service, "patch_workload_in_plan", _patch_workload)
    monkeypatch.setattr(deploy_service, "apply_plan", _apply_plan)
    monkeypatch.setattr(
        deploy_service,
        "_run_funnel_tracking_post_deploy_validation",
        _tracking_validation,
    )
    monkeypatch.setattr(
        deploy_service,
        "_activate_html_deploy_candidate_release",
        _activate_candidate,
    )

    job_id = "publish-job-candidate-gate-success"
    job_path = _write_publish_job_fixture(
        tmp_path,
        job_id=job_id,
        deploy_request={
            "workload_patch": {"name": "brand-funnels-70124684-be65d76e"},
            "apply_plan": True,
            "access_urls": ["https://shop.shopemberco.com/"],
            "instance_name": "ubuntu-4gb-hel1-2",
        },
    )

    await deploy_service._run_funnel_publish_job(job_id)

    job = json.loads(job_path.read_text(encoding="utf-8"))
    release_metadata = patched_workload["source_ref"]["release_metadata"]
    assert release_metadata["htmlDeployActivationMode"] == "candidate_only"
    assert release_metadata["htmlDeployCandidateReleaseId"] == "candidate-123"
    assert calls == [
        ("patch", release_metadata),
        ("apply", ["brand-funnels-70124684-be65d76e"]),
        ("validate", "candidate-123"),
        ("activate", "candidate-123"),
    ]
    assert job["status"] == "succeeded"
    assert job["result"]["deploy"]["trackingValidation"]["candidateReleaseId"] == "candidate-123"
    assert job["result"]["deploy"]["candidatePromotion"] == {
        "status": "activated",
        "releaseId": "candidate-123",
    }


@pytest.mark.asyncio
async def test_run_funnel_publish_job_fails_when_standalone_preflight_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    _install_publish_job_mocks(monkeypatch)

    monkeypatch.setattr(
        deploy_service,
        "_validate_standalone_funnel_artifact_preflight",
        lambda *, workload_patch: (_ for _ in ()).throw(deploy_service.DeployError("parity mismatch")),
    )

    job_id = "publish-job-standalone-preflight-failure"
    job_path = _write_publish_job_fixture(
        tmp_path,
        job_id=job_id,
        deploy_request={
            "workload_patch": {"name": "brand-funnels-70124684-be65d76e"},
            "apply_plan": True,
        },
    )

    await deploy_service._run_funnel_publish_job(job_id)

    job = json.loads(job_path.read_text(encoding="utf-8"))
    assert job["status"] == "failed"
    assert job["phase"] == "preflighting_standalone"
    assert job["error"] == "parity mismatch"


@pytest.mark.asyncio
async def test_run_funnel_publish_job_fails_when_tracking_validation_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    _install_publish_job_mocks(monkeypatch)
    monkeypatch.setattr(
        deploy_service,
        "_load_funnel_runtime_artifact_payload_for_apply",
        lambda *, artifact_id: _build_tracking_validation_artifact_payload(include_presales=True),
    )

    async def _tracking_validation(**kwargs):
        raise deploy_service.DeployError("tracking mismatch")

    monkeypatch.setattr(
        deploy_service,
        "_run_funnel_tracking_post_deploy_validation",
        _tracking_validation,
    )

    job_id = "publish-job-tracking-validation-failure"
    job_path = _write_publish_job_fixture(
        tmp_path,
        job_id=job_id,
        deploy_request={
            "workload_patch": {"name": "brand-funnels-70124684-be65d76e"},
            "apply_plan": False,
            "access_urls": ["https://shop.shopemberco.com/"],
        },
    )

    await deploy_service._run_funnel_publish_job(job_id)

    job = json.loads(job_path.read_text(encoding="utf-8"))
    assert job["status"] == "failed"
    assert job["phase"] == "validating_tracking"
    assert job["error"] == "tracking mismatch"


@pytest.mark.asyncio
async def test_run_funnel_publish_job_fails_when_tracking_validation_has_no_public_access_url(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(deploy_service.settings, "DEPLOY_ROOT_DIR", str(tmp_path))
    _install_publish_job_mocks(monkeypatch)

    async def _apply_plan(**kwargs):
        return {
            "returncode": 0,
            "plan_path": "/tmp/plan.json",
            "server_ips": {},
            "live_url": None,
            "logs": "",
        }

    monkeypatch.setattr(deploy_service, "apply_plan", _apply_plan)
    monkeypatch.setattr(deploy_service, "_infer_external_access_urls", lambda **kwargs: [])

    job_id = "publish-job-tracking-validation-no-url"
    job_path = _write_publish_job_fixture(
        tmp_path,
        job_id=job_id,
        deploy_request={
            "workload_patch": {"name": "brand-funnels-70124684-be65d76e"},
            "apply_plan": True,
        },
    )

    await deploy_service._run_funnel_publish_job(job_id)

    job = json.loads(job_path.read_text(encoding="utf-8"))
    assert job["status"] == "failed"
    assert job["phase"] == "applying_plan"
    assert "public access URL" in job["error"]
