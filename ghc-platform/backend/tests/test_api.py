from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import dependencies as auth_dependencies
from app.db.deps import get_session
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


def test_clients_campaigns_and_workflows(api_client, fake_temporal):
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
            "offers": ["A"],
            "goals": ["grow"],
        },
    )
    assert onboarding_resp.status_code == 200
    onboarding_run = onboarding_resp.json()["workflow_run_id"]
    assert fake_temporal.started  # workflow kicked off

    campaign_resp = api_client.post("/campaigns", json={"client_id": client_id, "name": "Launch"})
    assert campaign_resp.status_code == 201
    campaign_id = campaign_resp.json()["id"]

    # approvals to satisfy gating and simulate onboarding completion
    api_client.post(f"/workflows/{onboarding_run}/signals/approve-canon", json={"approved": True})
    api_client.post(f"/workflows/{onboarding_run}/signals/approve-metric-schema", json={"approved": True})

    plan_resp = api_client.post(f"/campaigns/{campaign_id}/plan", json={"goal": "grow"})
    assert plan_resp.status_code == 200
    planning_run = plan_resp.json()["workflow_run_id"]

    workflows = api_client.get("/workflows").json()
    workflow_ids = {wf["id"] for wf in workflows}
    assert onboarding_run in workflow_ids
    assert planning_run in workflow_ids

    approve_resp = api_client.post(
        f"/workflows/{planning_run}/signals/approve-strategy",
        json={"approved": True},
    )
    assert approve_resp.status_code == 200
    assert (
        "approve_strategy_sheet",
        ({"approved": True, "updated_strategy_sheet": None},),
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
