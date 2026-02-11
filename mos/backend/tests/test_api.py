from fastapi.testclient import TestClient
from sqlalchemy import select
from uuid import UUID

from app.auth import dependencies as auth_dependencies
from app.db.deps import get_session
from app.db.enums import ArtifactTypeEnum
from app.db.models import Artifact
from app.db.models import Org
from app.main import app


def test_protected_routes_require_auth():
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        resp = client.get("/clients")
    assert resp.status_code == 401


def test_health_endpoints():
    with TestClient(app) as client:
        health = client.get("/health")
        db_health = client.get("/health/db")

    assert health.status_code == 200
    assert health.json() == {"ok": True}
    assert db_health.status_code == 200
    assert "db" in db_health.json()


def test_auth_creates_org_and_allows_client_create(db_session, monkeypatch):
    app.dependency_overrides.clear()

    def get_session_override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_session] = get_session_override
    monkeypatch.setattr(
        auth_dependencies,
        "verify_clerk_token",
        lambda _token: {"sub": "test-user", "org_id": "org_test_123"},
    )

    try:
        with TestClient(app) as client:
            resp = client.post(
                "/clients",
                headers={"Authorization": "Bearer test-token"},
                json={"name": "Auth Client", "industry": "SaaS"},
            )
        assert resp.status_code == 201

        created_org = db_session.scalars(select(Org).where(Org.external_id == "org_test_123")).first()
        assert created_org is not None
    finally:
        app.dependency_overrides.clear()


def test_clients_campaigns_and_workflows(api_client, fake_temporal, db_session, auth_context):
    client_resp = api_client.post("/clients", json={"name": "Client API", "industry": "SaaS"})
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    list_resp = api_client.get("/clients")
    assert any(item["id"] == client_id for item in list_resp.json())

    onboarding_resp = api_client.post(
        f"/clients/{client_id}/onboarding",
        json={
            "business_type": "new",
            "brand_story": "Brand story for testing",
            "product_name": "Test Product",
            "product_description": "A simple test product for onboarding.",
            "goals": ["grow"],
        },
    )
    assert onboarding_resp.status_code == 200
    onboarding_run = onboarding_resp.json()["workflow_run_id"]
    product_id = onboarding_resp.json().get("product_id")
    default_offer_id = onboarding_resp.json().get("default_offer_id")
    assert product_id
    assert default_offer_id
    assert fake_temporal.started  # workflow kicked off

    product_detail = api_client.get(f"/products/{product_id}")
    assert product_detail.status_code == 200
    offers = product_detail.json().get("offers") or []
    assert len(offers) == 1
    assert offers[0]["id"] == default_offer_id
    assert offers[0]["name"] == "Test Product"
    assert offers[0]["business_model"] == "unspecified"
    assert offers[0]["description"] == "A simple test product for onboarding."

    # Planning prereqs: campaign planning requires canon + metric schema artifacts to exist.
    # Use the test auth org (the DB may contain non-test orgs as well).
    org_id = UUID(auth_context.org_id)
    client_uuid = UUID(client_id)
    product_uuid = UUID(product_id)
    db_session.add(
        Artifact(
            org_id=org_id,
            client_id=client_uuid,
            product_id=product_uuid,
            type=ArtifactTypeEnum.client_canon,
            data={"brand": {"story": "Test canon story"}},
        )
    )
    db_session.add(
        Artifact(
            org_id=org_id,
            client_id=client_uuid,
            product_id=product_uuid,
            type=ArtifactTypeEnum.metric_schema,
            data={"kpis": [{"id": "kpi-1", "name": "CTR"}]},
        )
    )
    db_session.commit()

    # Sanity check: artifacts should be visible to the API session before planning starts.
    canon_list = api_client.get(
        f"/artifacts?clientId={client_id}&productId={product_id}&type=client_canon"
    )
    assert canon_list.status_code == 200
    assert len(canon_list.json()) >= 1
    metric_list = api_client.get(
        f"/artifacts?clientId={client_id}&productId={product_id}&type=metric_schema"
    )
    assert metric_list.status_code == 200
    assert len(metric_list.json()) >= 1

    campaign_resp = api_client.post(
        "/campaigns",
        json={
            "client_id": client_id,
            "product_id": product_id,
            "name": "Launch",
            "channels": ["meta"],
            "asset_brief_types": ["image"],
        },
    )
    assert campaign_resp.status_code == 201
    campaign_id = campaign_resp.json()["id"]

    plan_resp = api_client.post(f"/campaigns/{campaign_id}/plan", json={"goal": "grow"})
    assert plan_resp.status_code == 200
    planning_run = plan_resp.json()["workflow_run_id"]
    planning_temporal_id = plan_resp.json()["temporal_workflow_id"]
    assert planning_temporal_id

    workflows = api_client.get("/workflows").json()
    workflow_ids = {wf["id"] for wf in workflows}
    assert onboarding_run in workflow_ids
    assert planning_run in workflow_ids

    # Strategy approval was removed; experiment approvals are now the gate.
    removed_strategy_resp = api_client.post(
        f"/workflows/{planning_run}/signals/approve-strategy",
        json={"approved": True},
    )
    assert removed_strategy_resp.status_code == 410

    approve_experiments_resp = api_client.post(
        f"/workflows/{planning_run}/signals/approve-experiments",
        json={"approved_ids": ["exp-1"], "rejected_ids": []},
    )
    assert approve_experiments_resp.status_code == 200
    assert (
        "approve_experiments",
        ({"approved_ids": ["exp-1"], "rejected_ids": [], "edited_specs": None},),
    ) in fake_temporal.signals

    # The API should also accept Temporal workflow IDs so operators can unblock runs from the Temporal UI.
    approve_by_temporal_id = api_client.post(
        f"/workflows/{planning_temporal_id}/signals/approve-experiments",
        json={"approved_ids": ["exp-2"], "rejected_ids": ["exp-3"]},
    )
    assert approve_by_temporal_id.status_code == 200
    assert (
        "approve_experiments",
        ({"approved_ids": ["exp-2"], "rejected_ids": ["exp-3"], "edited_specs": None},),
    ) in fake_temporal.signals

    logs_resp = api_client.get(f"/workflows/{onboarding_run}/logs")
    assert logs_resp.status_code == 200
    logs = logs_resp.json()
    assert isinstance(logs, list)
    assert any(log["step"] == "client_onboarding" for log in logs)

    planning_logs = api_client.get(f"/workflows/{planning_run}/logs").json()
    assert any(log["step"] == "campaign_planning" for log in planning_logs)


def test_artifacts_assets_experiments_and_swipes(api_client, seed_data):
    artifacts = api_client.get("/artifacts").json()
    assert any(item["id"] == str(seed_data["artifact"].id) for item in artifacts)

    assets = api_client.get("/assets").json()
    assert any(item["id"] == str(seed_data["asset"].id) for item in assets)

    experiments = api_client.get("/experiments").json()
    assert any(item["id"] == str(seed_data["experiment"].id) for item in experiments)

    company_swipes = api_client.get("/swipes/company").json()
    assert any(item["id"] == str(seed_data["company_swipe"].id) for item in company_swipes)

    client_swipes = api_client.get(f"/swipes/client/{seed_data['client'].id}").json()
    assert any(item["id"] == str(seed_data["client_swipe"].id) for item in client_swipes)

    workflows = api_client.get("/workflows").json()
    assert any(item["id"] == str(seed_data["workflow_run"].id) for item in workflows)

    logs = api_client.get(f"/workflows/{seed_data['workflow_run'].id}/logs").json()
    assert any(log["status"] == seed_data["log"].status for log in logs)
