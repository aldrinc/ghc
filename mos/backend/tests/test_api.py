from fastapi.testclient import TestClient
from sqlalchemy import select
from uuid import UUID, uuid4

from app.auth import dependencies as auth_dependencies
from app.db.deps import get_session
from app.db.enums import (
    ArtifactTypeEnum,
    GeminiContextFileStatusEnum,
    WorkflowKindEnum,
    WorkflowStatusEnum,
)
from app.db.models import Artifact, Funnel, GeminiContextFile, Org, WorkflowRun
from app.main import app
from app.routers import gemini as gemini_router
from app.services.gemini_file_search import GeminiChatResult, GeminiCitation
from tests.helpers.launch_context import seed_ready_launch_context_for_campaign


def _create_campaign_with_product(api_client: TestClient, *, suffix: str) -> tuple[str, str, str]:
    client_resp = api_client.post("/clients", json={"name": f"Client {suffix}", "industry": "SaaS"})
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    product_resp = api_client.post(
        "/products",
        json={"clientId": client_id, "title": f"Product {suffix}"},
    )
    assert product_resp.status_code == 201
    product_id = product_resp.json()["id"]

    campaign_resp = api_client.post(
        "/campaigns",
        json={
            "client_id": client_id,
            "product_id": product_id,
            "name": f"Campaign {suffix}",
            "channels": ["meta"],
            "asset_brief_types": ["image"],
        },
    )
    assert campaign_resp.status_code == 201
    campaign_id = campaign_resp.json()["id"]
    return client_id, product_id, campaign_id


def _insert_gemini_context_file(
    db_session,
    *,
    org_id: UUID,
    workspace_id: str,
    client_id: str,
    product_id: str,
    doc_key: str,
    document_name: str,
    store_name: str,
) -> GeminiContextFile:
    record = GeminiContextFile(
        org_id=org_id,
        idea_workspace_id=workspace_id,
        client_id=UUID(client_id),
        product_id=UUID(product_id),
        campaign_id=None,
        doc_key=doc_key,
        doc_title=f"{doc_key} title",
        source_kind="research_step",
        step_key="step-01",
        sha256=f"sha-{doc_key}",
        gemini_store_name=store_name,
        gemini_file_name=None,
        gemini_document_name=document_name,
        filename=f"{doc_key}.txt",
        mime_type="text/plain",
        size_bytes=128,
        drive_doc_id=None,
        drive_url=None,
        status=GeminiContextFileStatusEnum.ready,
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


_FOUNDATION_REQUIRED_STEP_KEYS = [
    "v2-02.foundation.01",
    "v2-02.foundation.03",
    "v2-02.foundation.04",
]


def _insert_workflow_run(
    db_session,
    *,
    org_id: UUID,
    client_id: str,
    product_id: str,
    kind: WorkflowKindEnum,
    status: WorkflowStatusEnum,
) -> WorkflowRun:
    run = WorkflowRun(
        org_id=org_id,
        client_id=UUID(client_id),
        product_id=UUID(product_id),
        campaign_id=None,
        temporal_workflow_id=f"{kind.value}-{uuid4().hex[:12]}",
        temporal_run_id=uuid4().hex,
        kind=kind,
        status=status,
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


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


def test_health_options_allows_loopback_dev_origins():
    with TestClient(app) as client:
        resp = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5276",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5276"


def test_health_options_allows_netbird_dev_origins():
    with TestClient(app) as client:
        resp = client.options(
            "/health",
            headers={
                "Origin": "http://100.79.158.197:5275",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://100.79.158.197:5275"


def test_create_campaign_rejects_unsupported_asset_brief_types(api_client: TestClient):
    client_resp = api_client.post("/clients", json={"name": "Invalid Asset Brief Client", "industry": "SaaS"})
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    product_resp = api_client.post("/products", json={"clientId": client_id, "title": "Invalid Asset Brief Product"})
    assert product_resp.status_code == 201
    product_id = product_resp.json()["id"]

    campaign_resp = api_client.post(
        "/campaigns",
        json={
            "client_id": client_id,
            "product_id": product_id,
            "name": "Invalid Asset Brief Campaign",
            "channels": ["meta"],
            "asset_brief_types": ["static-image"],
        },
    )

    assert campaign_resp.status_code == 422
    assert "Supported values: image, animated_image, video." in campaign_resp.text


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


def test_onboarding_requires_strategy_v2_enabled(api_client):
    client_resp = api_client.post("/clients", json={"name": "Client API", "industry": "SaaS"})
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    onboarding_resp = api_client.post(
        f"/clients/{client_id}/onboarding",
        json={
            "business_type": "new",
            "brand_story": "Brand story for testing",
            "product_name": "Test Product",
            "price": "$49",
            "product_type": "book",
            "product_customizable": True,
            "business_model": "one_time",
            "funnel_position": "top_of_funnel",
            "target_platforms": ["meta"],
            "target_regions": ["US"],
            "existing_proof_assets": ["customer testimonials"],
            "brand_voice_notes": "Clear and practical voice.",
            "product_description": "A simple test product for onboarding.",
            "goals": ["grow"],
        },
    )
    assert onboarding_resp.status_code == 409
    assert "Strategy V2 is disabled" in onboarding_resp.json()["detail"]


def test_clients_campaigns_and_workflows(api_client, fake_temporal, db_session, auth_context):
    client_resp = api_client.post(
        "/clients",
        json={"name": "Client API", "industry": "SaaS", "strategyV2Enabled": True},
    )
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
            "price": "$49",
            "product_type": "book",
            "product_customizable": True,
            "business_model": "one_time",
            "funnel_position": "top_of_funnel",
            "target_platforms": ["meta"],
            "target_regions": ["US"],
            "existing_proof_assets": ["customer testimonials"],
            "brand_voice_notes": "Clear and practical voice.",
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
    product_payload = product_detail.json()
    assert product_payload["title"] == "Test Product"
    assert product_payload["product_type"] == "book"
    assert isinstance(product_payload.get("variants"), list)
    assert len(product_payload["variants"]) == 1
    assert product_payload["variants"][0]["offer_id"] == default_offer_id
    assert product_payload["variants"][0]["price"] == 4900
    assert product_payload["variants"][0]["currency"] == "USD"

    short_product_id = product_id.split("-", 1)[0]
    product_detail_short = api_client.get(f"/products/{short_product_id}")
    assert product_detail_short.status_code == 200
    assert product_detail_short.json()["id"] == product_id

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
    db_session.add(
        Artifact(
            org_id=org_id,
            client_id=client_uuid,
            product_id=product_uuid,
            type=ArtifactTypeEnum.strategy_v2_stage3,
            data={"core_promise": "Test core promise", "variant_selected": "variant-a"},
        )
    )
    db_session.add(
        Artifact(
            org_id=org_id,
            client_id=client_uuid,
            product_id=product_uuid,
            type=ArtifactTypeEnum.strategy_v2_offer,
            data={"variant_selected": "variant-a"},
        )
    )
    db_session.add(
        Artifact(
            org_id=org_id,
            client_id=client_uuid,
            product_id=product_uuid,
            type=ArtifactTypeEnum.strategy_v2_copy,
            data={"headline": "Test headline", "presell_markdown": "presell", "sales_page_markdown": "sales"},
        )
    )
    db_session.add(
        Artifact(
            org_id=org_id,
            client_id=client_uuid,
            product_id=product_uuid,
            type=ArtifactTypeEnum.strategy_v2_copy_context,
            data={"angle_name": "Test angle"},
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


def test_marketing_agent_setup_allows_service_price_later(api_client, fake_temporal):
    client_resp = api_client.post(
        "/clients",
        json={"name": "Service Workspace", "industry": "Services", "strategyV2Enabled": True},
    )
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    setup_resp = api_client.post(
        f"/clients/{client_id}/marketing-agent/setup",
        json={
            "business_type": "new",
            "business_name": "Service Workspace",
            "business_model": "service_business",
            "offering_kind": "service",
            "offering_type": "implementation service",
            "offering_name": "Growth Sprint",
            "offering_description": "A done-for-you service that improves customer acquisition.",
            "competitor_urls": ["https://competitor.example"],
        },
    )
    assert setup_resp.status_code == 200
    payload = setup_resp.json()
    assert payload["pricing_status"] == "later"
    product_id = payload["product_id"]
    assert fake_temporal.started

    product_detail = api_client.get(f"/products/{product_id}")
    assert product_detail.status_code == 200
    product_payload = product_detail.json()
    assert product_payload["title"] == "Growth Sprint"
    assert product_payload["product_type"] == "implementation service"
    assert product_payload["variants"] == []


def test_marketing_agent_setup_supports_existing_business(api_client, fake_temporal):
    client_resp = api_client.post(
        "/clients",
        json={"name": "Existing Workspace", "industry": "SaaS", "strategyV2Enabled": True},
    )
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    setup_resp = api_client.post(
        f"/clients/{client_id}/marketing-agent/setup",
        json={
            "business_type": "existing",
            "input_mode": "source_extract",
            "business_url": "https://existing.example",
            "business_name": "Existing Workspace",
            "business_model": "saas_subscription",
            "offering_kind": "software",
            "offering_type": "analytics software",
            "offering_name": "Revenue Dashboard",
            "offering_description": "Software that helps operators monitor revenue signals.",
            "pricing_model": "subscription",
            "context_dev_summary": {
                "provider": "context_dev",
                "fields": {
                    "offering_name": {
                        "value": "Revenue Dashboard",
                        "provenance": "concrete",
                        "provider": "context_dev",
                    }
                },
            },
        },
    )
    assert setup_resp.status_code == 200
    assert setup_resp.json()["product_name"] == "Revenue Dashboard"
    assert fake_temporal.started


def test_marketing_agent_extract_uses_context_dev_review_service(api_client, monkeypatch):
    client_resp = api_client.post(
        "/clients",
        json={"name": "Extract Workspace", "industry": "SaaS", "strategyV2Enabled": True},
    )
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    from app.routers import clients as clients_router

    def _fake_build_existing_business_review(*, business_url: str, competitor_urls: list[str] | None = None):
        return {
            "provider": "context_dev",
            "domain": "example.com",
            "business_url": business_url,
            "competitor_urls": competitor_urls or [],
            "fields": {
                "offering_name": {
                    "value": "Revenue Dashboard",
                    "provenance": "concrete",
                    "provider": "context_dev",
                    "endpoint": "/brand/ai/products",
                    "raw_path": "products[0].name",
                    "confidence": "provider_returned",
                }
            },
            "raw": {},
            "requests": {},
        }

    monkeypatch.setattr(clients_router, "build_existing_business_review", _fake_build_existing_business_review)

    extract_resp = api_client.post(
        f"/clients/{client_id}/marketing-agent/extract",
        json={"business_url": "example.com", "competitor_urls": ["competitor.example"]},
    )
    assert extract_resp.status_code == 200
    payload = extract_resp.json()
    assert payload["provider"] == "context_dev"
    assert payload["business_url"] == "https://example.com"
    assert payload["competitor_urls"] == ["https://competitor.example"]
    assert payload["fields"]["offering_name"]["value"] == "Revenue Dashboard"
    assert "raw" not in payload
    assert isinstance(payload["raw_artifact_id"], str)


def test_foundation_readiness_pending_before_bundle(api_client, db_session, auth_context):
    client_resp = api_client.post(
        "/clients",
        json={"name": "Foundation Pending", "industry": "SaaS"},
    )
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    product_resp = api_client.post(
        "/products",
        json={"clientId": client_id, "title": "Pending Product"},
    )
    assert product_resp.status_code == 201
    product_id = product_resp.json()["id"]

    onboarding_run = _insert_workflow_run(
        db_session,
        org_id=UUID(auth_context.org_id),
        client_id=client_id,
        product_id=product_id,
        kind=WorkflowKindEnum.client_onboarding,
        status=WorkflowStatusEnum.running,
    )

    response = api_client.get(
        f"/clients/{client_id}/foundation-readiness",
        params={"productId": product_id},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "foundation_pending"
    assert payload["should_gate_overview"] is True
    assert payload["reason"] == "client_onboarding_running"
    assert payload["onboarding_workflow_run_id"] == str(onboarding_run.id)
    assert payload["required_step_keys"] == _FOUNDATION_REQUIRED_STEP_KEYS
    assert payload["present_step_keys"] == []
    assert payload["missing_step_keys"] == _FOUNDATION_REQUIRED_STEP_KEYS


def test_foundation_readiness_failed_when_strategy_failed(api_client, db_session, auth_context):
    client_resp = api_client.post(
        "/clients",
        json={"name": "Foundation Failed", "industry": "SaaS"},
    )
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    product_resp = api_client.post(
        "/products",
        json={"clientId": client_id, "title": "Failed Product"},
    )
    assert product_resp.status_code == 201
    product_id = product_resp.json()["id"]

    strategy_run = _insert_workflow_run(
        db_session,
        org_id=UUID(auth_context.org_id),
        client_id=client_id,
        product_id=product_id,
        kind=WorkflowKindEnum.strategy_v2,
        status=WorkflowStatusEnum.failed,
    )

    response = api_client.get(
        f"/clients/{client_id}/foundation-readiness",
        params={"productId": product_id},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "foundation_failed"
    assert payload["should_gate_overview"] is True
    assert payload["reason"] == "strategy_v2_foundation_run_failed"
    assert payload["strategy_workflow_run_id"] == str(strategy_run.id)
    assert payload["strategy_workflow_status"] == WorkflowStatusEnum.failed.value
    assert payload["required_step_keys"] == _FOUNDATION_REQUIRED_STEP_KEYS
    assert payload["present_step_keys"] == []
    assert payload["missing_step_keys"] == _FOUNDATION_REQUIRED_STEP_KEYS


def test_foundation_readiness_ready_when_bundle_complete(api_client, db_session, auth_context):
    client_resp = api_client.post(
        "/clients",
        json={"name": "Foundation Ready", "industry": "SaaS"},
    )
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    product_resp = api_client.post(
        "/products",
        json={"clientId": client_id, "title": "Ready Product"},
    )
    assert product_resp.status_code == 201
    product_id = product_resp.json()["id"]

    strategy_run = _insert_workflow_run(
        db_session,
        org_id=UUID(auth_context.org_id),
        client_id=client_id,
        product_id=product_id,
        kind=WorkflowKindEnum.strategy_v2,
        status=WorkflowStatusEnum.completed,
    )
    db_session.add(
        Artifact(
            org_id=UUID(auth_context.org_id),
            client_id=UUID(client_id),
            product_id=UUID(product_id),
            type=ArtifactTypeEnum.foundation_research_bundle,
            data={
                "workflow_run_id": str(strategy_run.id),
                "step_payload_artifact_ids": {
                    "v2-02.foundation.01": "artifact-step-01",
                    "v2-02.foundation.03": "artifact-step-03",
                    "v2-02.foundation.04": "artifact-step-04",
                },
            },
        )
    )
    db_session.commit()

    response = api_client.get(
        f"/clients/{client_id}/foundation-readiness",
        params={"productId": product_id},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "foundation_ready"
    assert payload["should_gate_overview"] is False
    assert payload["reason"] == "foundation_bundle_complete"
    assert payload["strategy_workflow_run_id"] == str(strategy_run.id)
    assert payload["strategy_workflow_status"] == WorkflowStatusEnum.completed.value
    assert payload["required_step_keys"] == _FOUNDATION_REQUIRED_STEP_KEYS
    assert payload["present_step_keys"] == _FOUNDATION_REQUIRED_STEP_KEYS
    assert payload["missing_step_keys"] == []


def test_generate_campaign_funnels_rejects_existing_angle(api_client, fake_temporal, db_session, auth_context):
    client_id, product_id, campaign_id = _create_campaign_with_product(api_client, suffix="Duplicate Angle")

    db_session.add(
        Funnel(
            org_id=UUID(auth_context.org_id),
            client_id=UUID(client_id),
            product_id=UUID(product_id),
            campaign_id=UUID(campaign_id),
            experiment_spec_id="angle-1",
            name="Existing Angle Funnel",
            route_slug=f"existing-angle-{uuid4().hex[:8]}",
        )
    )
    db_session.commit()

    generate_resp = api_client.post(
        f"/campaigns/{campaign_id}/funnels/generate",
        json={"experimentIds": ["angle-1"], "generateTestimonials": True},
    )
    assert generate_resp.status_code == 409
    assert generate_resp.json()["detail"] == "Funnels already exist for angle ids: angle-1."
    assert fake_temporal.started == []


def test_generate_campaign_funnels_rejects_when_run_in_progress(api_client, fake_temporal, db_session):
    client_id, product_id, campaign_id = _create_campaign_with_product(api_client, suffix="Running Workflow")
    seed_ready_launch_context_for_campaign(
        db_session,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
    )

    first_generate = api_client.post(
        f"/campaigns/{campaign_id}/funnels/generate",
        json={"experimentIds": ["angle-1"], "generateTestimonials": True},
    )
    assert first_generate.status_code == 200

    second_generate = api_client.post(
        f"/campaigns/{campaign_id}/funnels/generate",
        json={"experimentIds": ["angle-2"], "generateTestimonials": True},
    )
    assert second_generate.status_code == 409
    assert (
        second_generate.json()["detail"]
        == "A funnel generation workflow is already running for this campaign. Wait for it to finish."
    )
    assert len(fake_temporal.started) == 1


def test_gemini_context_requires_feature_flag(api_client, monkeypatch):
    monkeypatch.setenv("GEMINI_FILE_SEARCH_ENABLED", "false")

    response = api_client.get("/gemini/context", params={"ideaWorkspaceId": "ws-test"})
    assert response.status_code == 409
    assert response.json()["detail"] == "Gemini File Search is disabled."


def test_gemini_context_lists_scoped_files(api_client, db_session, auth_context, monkeypatch):
    monkeypatch.setenv("GEMINI_FILE_SEARCH_ENABLED", "true")
    client_id, product_id, _campaign_id = _create_campaign_with_product(
        api_client, suffix="Gemini Context"
    )
    workspace_id = client_id

    created = _insert_gemini_context_file(
        db_session,
        org_id=UUID(auth_context.org_id),
        workspace_id=workspace_id,
        client_id=client_id,
        product_id=product_id,
        doc_key="gemini-context-doc",
        document_name="fileSearchStores/test/documents/doc-123",
        store_name="fileSearchStores/test",
    )

    response = api_client.get(
        "/gemini/context",
        params={
            "ideaWorkspaceId": workspace_id,
            "clientId": client_id,
            "productId": product_id,
        },
    )
    assert response.status_code == 200
    files = response.json()["files"]
    assert len(files) == 1
    assert files[0]["id"] == str(created.id)
    assert files[0]["gemini_document_name"] == "fileSearchStores/test/documents/doc-123"


def test_gemini_chat_stream_returns_text_and_citations(
    api_client, db_session, auth_context, monkeypatch
):
    monkeypatch.setenv("GEMINI_FILE_SEARCH_ENABLED", "true")
    client_id, product_id, _campaign_id = _create_campaign_with_product(
        api_client, suffix="Gemini Stream"
    )
    workspace_id = client_id
    document_name = "fileSearchStores/test/documents/doc-abc"
    _insert_gemini_context_file(
        db_session,
        org_id=UUID(auth_context.org_id),
        workspace_id=workspace_id,
        client_id=client_id,
        product_id=product_id,
        doc_key="gemini-stream-doc",
        document_name=document_name,
        store_name="fileSearchStores/test",
    )

    def _fake_generate(**_kwargs):
        return GeminiChatResult(
            text="Grounded answer from Gemini.",
            stop_reason="STOP",
            output_tokens=42,
            citations=[
                GeminiCitation(
                    title="Doc Citation",
                    uri="https://example.com/doc",
                    source_kind="retrieved_context",
                    document_name=document_name,
                    start_index=0,
                    end_index=18,
                )
            ],
        )

    monkeypatch.setattr(gemini_router, "generate_with_gemini_file_search", _fake_generate)

    response = api_client.post(
        "/gemini/chat/stream",
        json={
            "prompt": "What does the context say?",
            "ideaWorkspaceId": workspace_id,
            "clientId": client_id,
            "productId": product_id,
            "fileIds": [document_name],
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"type":"text"' in response.text
    assert "Grounded answer from Gemini." in response.text
    assert '"type":"done"' in response.text
    assert '"citations"' in response.text


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
