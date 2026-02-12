from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.enums import FunnelDomainStatusEnum
from app.db.models import Funnel, FunnelDomain
from app.services import deploy as deploy_service


def _create_publish_ready_funnel(api_client: TestClient, *, funnel_name: str) -> tuple[str, str]:
    client_resp = api_client.post("/clients", json={"name": f"{funnel_name} Client", "industry": "SaaS"})
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]
    product_resp = api_client.post("/products", json={"clientId": client_id, "name": f"{funnel_name} Product"})
    assert product_resp.status_code == 201
    product_id = product_resp.json()["id"]

    funnel_resp = api_client.post(
        "/funnels",
        json={"clientId": client_id, "productId": product_id, "name": funnel_name, "description": "Demo"},
    )
    assert funnel_resp.status_code == 201
    funnel = funnel_resp.json()
    funnel_id = funnel["id"]
    public_id = funnel["public_id"]

    page_resp = api_client.post(f"/funnels/{funnel_id}/pages", json={"name": "Landing"})
    assert page_resp.status_code == 201
    page = page_resp.json()["page"]
    page_id = page["id"]

    set_entry = api_client.patch(f"/funnels/{funnel_id}", json={"entryPageId": page_id})
    assert set_entry.status_code == 200

    save_draft = api_client.put(
        f"/funnels/{funnel_id}/pages/{page_id}",
        json={
            "puckData": {
                "root": {"props": {}},
                "content": [{"type": "Text", "props": {"text": "Published"}}],
                "zones": {},
            }
        },
    )
    assert save_draft.status_code == 200

    return funnel_id, public_id

from app.db.models import AgentRun, AgentToolCall


def test_funnel_authoring_publish_and_public_runtime(api_client: TestClient, db_session):
    client_resp = api_client.post("/clients", json={"name": "Funnels Client", "industry": "SaaS"})
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]
    product_resp = api_client.post("/products", json={"clientId": client_id, "name": "Funnels Product"})
    assert product_resp.status_code == 201
    product_id = product_resp.json()["id"]

    funnel_resp = api_client.post(
        "/funnels",
        json={"clientId": client_id, "productId": product_id, "name": "Test Funnel", "description": "Demo"},
    )
    assert funnel_resp.status_code == 201
    funnel = funnel_resp.json()
    funnel_id = funnel["id"]
    public_id = funnel["public_id"]

    page1_resp = api_client.post(f"/funnels/{funnel_id}/pages", json={"name": "Landing"})
    assert page1_resp.status_code == 201
    page1 = page1_resp.json()["page"]
    page1_id = page1["id"]

    page2_resp = api_client.post(f"/funnels/{funnel_id}/pages", json={"name": "Thank you"})
    assert page2_resp.status_code == 201
    page2 = page2_resp.json()["page"]
    page2_id = page2["id"]

    set_entry = api_client.patch(f"/funnels/{funnel_id}", json={"entryPageId": page1_id})
    assert set_entry.status_code == 200

    # Set known content for publication, approve, then publish.
    save_draft = api_client.put(
        f"/funnels/{funnel_id}/pages/{page1_id}",
        json={
            "puckData": {
                "root": {"props": {}},
                "content": [{"type": "Text", "props": {"text": "Published"}}],
                "zones": {},
            }
        },
    )
    assert save_draft.status_code == 200

    publish = api_client.post(f"/funnels/{funnel_id}/publish")
    assert publish.status_code == 201
    publication_id = publish.json()["publicationId"]
    run_id = publish.json().get("runId")
    assert isinstance(run_id, str) and run_id

    agent_run = db_session.scalars(select(AgentRun).where(AgentRun.id == run_id)).first()
    assert agent_run is not None
    assert agent_run.objective_type == "objective.publish_funnel"
    assert agent_run.status.value == "completed"

    tool_calls = list(db_session.scalars(select(AgentToolCall).where(AgentToolCall.run_id == run_id)).all())
    tool_names = sorted({c.tool_name for c in tool_calls})
    assert tool_names == ["publish.execute", "publish.validate_ready"]

    meta = api_client.get(f"/public/funnels/{public_id}/meta")
    assert meta.status_code == 200
    assert meta.json()["publicationId"] == publication_id
    assert meta.json()["entrySlug"] == page1["slug"]

    public_page = api_client.get(f"/public/funnels/{public_id}/pages/{page1['slug']}")
    assert public_page.status_code == 200
    assert public_page.json()["slug"] == page1["slug"]
    assert public_page.json()["puckData"]["content"][0]["props"]["text"] == "Published"

    # Draft leakage guard: save a new draft but do not approve; public stays the same.
    save_new_draft = api_client.put(
        f"/funnels/{funnel_id}/pages/{page1_id}",
        json={
            "puckData": {
                "root": {"props": {}},
                "content": [{"type": "Text", "props": {"text": "Draft"}}],
                "zones": {},
            }
        },
    )
    assert save_new_draft.status_code == 200
    public_page_after = api_client.get(f"/public/funnels/{public_id}/pages/{page1['slug']}")
    assert public_page_after.status_code == 200
    assert public_page_after.json()["puckData"]["content"][0]["props"]["text"] == "Published"

    # Slug redirect: change slug, publish again, old slug resolves to redirect response.
    new_slug = "landing-updated"
    update_slug = api_client.patch(
        f"/funnels/{funnel_id}/pages/{page1_id}",
        json={"slug": new_slug},
    )
    assert update_slug.status_code == 200

    publish2 = api_client.post(f"/funnels/{funnel_id}/publish")
    assert publish2.status_code == 201
    publication_id_2 = publish2.json()["publicationId"]
    assert publication_id_2 != publication_id

    redirect = api_client.get(f"/public/funnels/{public_id}/pages/{page1['slug']}")
    assert redirect.status_code == 200
    assert redirect.json()["redirectToSlug"] == new_slug

    meta2 = api_client.get(f"/public/funnels/{public_id}/meta").json()
    assert meta2["publicationId"] == publication_id_2
    assert meta2["entrySlug"] == new_slug

    disable = api_client.post(f"/funnels/{funnel_id}/disable")
    assert disable.status_code == 200
    disabled_meta = api_client.get(f"/public/funnels/{public_id}/meta")
    assert disabled_meta.status_code == 410


def test_funnel_public_preview_allows_approved_pages_before_publish(api_client: TestClient):
    client_resp = api_client.post("/clients", json={"name": "Preview Funnel Client", "industry": "SaaS"})
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]
    product_resp = api_client.post("/products", json={"clientId": client_id, "name": "Preview Product"})
    assert product_resp.status_code == 201
    product_id = product_resp.json()["id"]

    funnel_resp = api_client.post(
        "/funnels",
        json={"clientId": client_id, "productId": product_id, "name": "Preview Funnel", "description": "Demo"},
    )
    assert funnel_resp.status_code == 201
    funnel = funnel_resp.json()
    funnel_id = funnel["id"]
    public_id = funnel["public_id"]

    page1_resp = api_client.post(f"/funnels/{funnel_id}/pages", json={"name": "Landing"})
    assert page1_resp.status_code == 201
    page1 = page1_resp.json()["page"]
    page1_id = page1["id"]

    page2_resp = api_client.post(f"/funnels/{funnel_id}/pages", json={"name": "Thank you"})
    assert page2_resp.status_code == 201
    page2 = page2_resp.json()["page"]
    page2_id = page2["id"]

    set_entry = api_client.patch(f"/funnels/{funnel_id}", json={"entryPageId": page1_id})
    assert set_entry.status_code == 200

    # Save landing page content but do not publish the funnel yet.
    save_draft = api_client.put(
        f"/funnels/{funnel_id}/pages/{page1_id}",
        json={
            "puckData": {
                "root": {"props": {}},
                "content": [{"type": "Text", "props": {"text": "Preview"}}],
                "zones": {},
            }
        },
    )
    assert save_draft.status_code == 200

    meta = api_client.get(f"/public/funnels/{public_id}/meta")
    assert meta.status_code == 200
    assert meta.json()["publicationId"] == funnel_id
    assert meta.json()["entrySlug"] == page1["slug"]
    assert {"pageId": page1_id, "slug": page1["slug"]} in meta.json()["pages"]
    assert {"pageId": page2_id, "slug": page2["slug"]} in meta.json()["pages"]

    public_page = api_client.get(f"/public/funnels/{public_id}/pages/{page1['slug']}")
    assert public_page.status_code == 200
    assert public_page.json()["publicationId"] == funnel_id
    assert public_page.json()["slug"] == page1["slug"]
    assert public_page.json()["puckData"]["content"][0]["props"]["text"] == "Preview"

    # Preview mode: pages with drafts are available on the internal preview URL even before publish.
    page2_preview = api_client.get(f"/public/funnels/{public_id}/pages/{page2['slug']}")
    assert page2_preview.status_code == 200


def test_public_funnel_commerce_requires_offers(api_client: TestClient):
    client_resp = api_client.post("/clients", json={"name": "Commerce Client", "industry": "SaaS"})
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    product_resp = api_client.post("/products", json={"clientId": client_id, "name": "Commerce Product"})
    assert product_resp.status_code == 201
    product_id = product_resp.json()["id"]

    funnel_resp = api_client.post(
        "/funnels",
        json={"clientId": client_id, "productId": product_id, "name": "Commerce Funnel"},
    )
    assert funnel_resp.status_code == 201
    public_id = funnel_resp.json()["public_id"]

    commerce_resp = api_client.get(f"/public/funnels/{public_id}/commerce")
    assert commerce_resp.status_code == 409
    assert commerce_resp.json()["detail"] == "Product offers are not configured for this funnel product."


def test_public_funnel_commerce_requires_price_points(api_client: TestClient):
    client_resp = api_client.post("/clients", json={"name": "Commerce Client", "industry": "SaaS"})
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    product_resp = api_client.post("/products", json={"clientId": client_id, "name": "Commerce Product"})
    assert product_resp.status_code == 201
    product_id = product_resp.json()["id"]

    offer_resp = api_client.post(
        f"/products/{product_id}/offers",
        json={
            "productId": product_id,
            "name": "Starter Offer",
            "businessModel": "one-time",
        },
    )
    assert offer_resp.status_code == 201

    funnel_resp = api_client.post(
        "/funnels",
        json={"clientId": client_id, "productId": product_id, "name": "Commerce Funnel"},
    )
    assert funnel_resp.status_code == 201
    public_id = funnel_resp.json()["public_id"]

    commerce_resp = api_client.get(f"/public/funnels/{public_id}/commerce")
    assert commerce_resp.status_code == 409
    assert commerce_resp.json()["detail"] == "Product offer price points are not configured for this funnel product."


def test_public_funnel_commerce_returns_offers_and_price_points(api_client: TestClient):
    client_resp = api_client.post("/clients", json={"name": "Commerce Client", "industry": "SaaS"})
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    product_resp = api_client.post("/products", json={"clientId": client_id, "name": "Commerce Product"})
    assert product_resp.status_code == 201
    product_id = product_resp.json()["id"]

    offer_resp = api_client.post(
        f"/products/{product_id}/offers",
        json={
            "productId": product_id,
            "name": "Starter Offer",
            "businessModel": "one-time",
        },
    )
    assert offer_resp.status_code == 201
    offer_id = offer_resp.json()["id"]

    price_point_resp = api_client.post(
        f"/products/offers/{offer_id}/price-points",
        json={
            "offerId": offer_id,
            "label": "Default",
            "amountCents": 9900,
            "currency": "usd",
            "optionValues": {"size": "standard"},
        },
    )
    assert price_point_resp.status_code == 201

    funnel_resp = api_client.post(
        "/funnels",
        json={"clientId": client_id, "productId": product_id, "name": "Commerce Funnel"},
    )
    assert funnel_resp.status_code == 201
    public_id = funnel_resp.json()["public_id"]

    commerce_resp = api_client.get(f"/public/funnels/{public_id}/commerce")
    assert commerce_resp.status_code == 200
    payload = commerce_resp.json()
    assert len(payload["offers"]) == 1
    assert payload["offers"][0]["id"] == offer_id
    assert len(payload["offers"][0]["pricePoints"]) == 1
    assert "external_price_id" not in payload["offers"][0]["pricePoints"][0]


def test_publish_with_deploy_builds_funnel_artifact_workload_from_db(api_client: TestClient, monkeypatch):
    funnel_id, public_id = _create_publish_ready_funnel(api_client, funnel_name="Deploy Funnel")

    captured: dict[str, object] = {}

    def fake_start_funnel_publish_job(
        *,
        org_id=None,
        user_id=None,
        funnel_id=None,
        deploy_request=None,
        access_urls=None,
    ):
        captured["org_id"] = org_id
        captured["user_id"] = user_id
        captured["funnel_id"] = funnel_id
        captured["deploy_request"] = deploy_request
        captured["access_urls"] = access_urls
        return {
            "id": "publish-job-123",
            "status": "queued",
            "created_at": "2026-01-01T00:00:00+00:00",
            "access_urls": access_urls or [],
            "result": None,
            "error": None,
        }

    monkeypatch.setattr(deploy_service, "start_funnel_publish_job", fake_start_funnel_publish_job)

    resp = api_client.post(
        f"/funnels/{funnel_id}/publish",
        json={
            "deploy": {
                "workloadName": "landing-page",
                "instanceName": "mos-ghc-1",
                "serverNames": ["landing.example.com"],
                "upstreamBaseUrl": "https://moshq.app",
                "upstreamApiBaseUrl": "https://moshq.app/api",
                "createIfMissing": True,
                "inPlace": False,
            }
        },
    )
    assert resp.status_code == 201

    body = resp.json()
    assert body["publicationId"] is None
    assert body["deploy"]["apply"]["mode"] == "async"
    assert body["deploy"]["apply"]["jobId"] == "publish-job-123"
    assert body["deploy"]["apply"]["statusPath"] == f"/funnels/{funnel_id}/publish-jobs/publish-job-123"
    assert body["deploy"]["apply"]["accessUrls"] == ["https://landing.example.com/"]

    deploy_request = captured["deploy_request"]
    workload_patch = deploy_request["workload_patch"]
    assert workload_patch["source_type"] == "funnel_artifact"
    assert workload_patch["source_ref"]["public_id"] == public_id
    assert workload_patch["source_ref"]["upstream_api_base_root"] == "https://moshq.app/api"
    assert workload_patch["source_ref"]["runtime_dist_path"] == "mos/frontend/dist"
    assert workload_patch["source_ref"]["artifact"]["meta"]["publicId"] == public_id
    assert workload_patch["source_ref"]["artifact"]["pages"] == {}
    assert workload_patch["service_config"]["server_names"] == ["landing.example.com"]
    assert deploy_request["plan_path"] is None
    assert deploy_request["instance_name"] == "mos-ghc-1"
    assert deploy_request["create_if_missing"] is True
    assert deploy_request["in_place"] is False
    assert deploy_request["apply_plan"] is True
    assert captured["access_urls"] == ["https://landing.example.com/"]


def test_publish_with_deploy_uses_funnel_domain_from_db_when_server_names_omitted(
    api_client: TestClient,
    db_session,
    monkeypatch,
):
    funnel_id, public_id = _create_publish_ready_funnel(api_client, funnel_name="Domain Deploy Funnel")

    funnel = db_session.scalars(select(Funnel).where(Funnel.id == funnel_id)).first()
    assert funnel is not None
    db_session.add(
        FunnelDomain(
            org_id=funnel.org_id,
            client_id=funnel.client_id,
            funnel_id=funnel.id,
            hostname="offers.example.com",
            status=FunnelDomainStatusEnum.active,
        )
    )
    db_session.commit()

    captured: dict[str, object] = {}

    def fake_start_funnel_publish_job(
        *,
        org_id=None,
        user_id=None,
        funnel_id=None,
        deploy_request=None,
        access_urls=None,
    ):
        captured["deploy_request"] = deploy_request
        captured["access_urls"] = access_urls
        return {
            "id": "publish-job-234",
            "status": "queued",
            "created_at": "2026-01-01T00:00:00+00:00",
            "access_urls": access_urls or [],
            "result": None,
            "error": None,
        }

    monkeypatch.setattr(deploy_service, "start_funnel_publish_job", fake_start_funnel_publish_job)

    resp = api_client.post(
        f"/funnels/{funnel_id}/publish",
        json={
            "deploy": {
                "workloadName": "landing-page",
                "upstreamBaseUrl": "https://moshq.app",
                "upstreamApiBaseUrl": "https://moshq.app/api",
                "applyPlan": False,
            }
        },
    )
    assert resp.status_code == 201

    deploy_request = captured["deploy_request"]
    workload_patch = deploy_request["workload_patch"]
    assert workload_patch["source_ref"]["public_id"] == public_id
    assert workload_patch["service_config"]["server_names"] == ["offers.example.com"]
    assert deploy_request["apply_plan"] is False
    assert captured["access_urls"] == ["https://offers.example.com/"]


def test_publish_with_deploy_allows_no_server_names(api_client: TestClient, monkeypatch):
    funnel_id, _ = _create_publish_ready_funnel(api_client, funnel_name="Missing Domain Deploy Funnel")

    captured: dict[str, object] = {}

    def fake_start_funnel_publish_job(
        *,
        org_id=None,
        user_id=None,
        funnel_id=None,
        deploy_request=None,
        access_urls=None,
    ):
        captured["deploy_request"] = deploy_request
        captured["access_urls"] = access_urls
        return {
            "id": "publish-job-456",
            "status": "queued",
            "created_at": "2026-01-01T00:00:00+00:00",
            "access_urls": access_urls or [],
            "result": None,
            "error": None,
        }

    monkeypatch.setattr(deploy_service, "start_funnel_publish_job", fake_start_funnel_publish_job)

    resp = api_client.post(
        f"/funnels/{funnel_id}/publish",
        json={
            "deploy": {
                "workloadName": "landing-page",
                "upstreamBaseUrl": "https://moshq.app",
                "upstreamApiBaseUrl": "https://moshq.app/api",
                "applyPlan": True,
            }
        },
    )
    assert resp.status_code == 201

    deploy_request = captured["deploy_request"]
    workload_patch = deploy_request["workload_patch"]
    assert workload_patch["service_config"]["server_names"] == []
    assert workload_patch["service_config"]["https"] is False
    body = resp.json()
    assert body["deploy"]["apply"]["jobId"] == "publish-job-456"
    assert captured["access_urls"] == []


def test_get_funnel_publish_job_status(api_client: TestClient, monkeypatch):
    funnel_id, _ = _create_publish_ready_funnel(api_client, funnel_name="Publish Job Status Funnel")

    def fake_get_funnel_publish_job(*, job_id=None, org_id=None, funnel_id=None):
        assert job_id == "publish-job-789"
        return {
            "id": "publish-job-789",
            "status": "succeeded",
            "created_at": "2026-01-01T00:00:00+00:00",
            "started_at": "2026-01-01T00:00:01+00:00",
            "finished_at": "2026-01-01T00:01:00+00:00",
            "access_urls": ["https://landing.example.com/"],
            "result": {"publicationId": "pub-1"},
            "error": None,
        }

    monkeypatch.setattr(deploy_service, "get_funnel_publish_job", fake_get_funnel_publish_job)

    resp = api_client.get(f"/funnels/{funnel_id}/publish-jobs/publish-job-789")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "publish-job-789"
    assert body["status"] == "succeeded"
    assert body["access_urls"] == ["https://landing.example.com/"]


def test_get_funnel_deploy_job_status(api_client: TestClient, monkeypatch):
    funnel_id, _ = _create_publish_ready_funnel(api_client, funnel_name="Deploy Job Status Funnel")

    def fake_get_apply_plan_job(*, job_id=None):
        assert job_id == "job-789"
        return {
            "id": "job-789",
            "status": "succeeded",
            "created_at": "2026-01-01T00:00:00+00:00",
            "started_at": "2026-01-01T00:00:01+00:00",
            "finished_at": "2026-01-01T00:01:00+00:00",
            "plan_path": "/tmp/plan-updated.json",
            "access_urls": ["https://landing.example.com/"],
            "result": {"returncode": 0},
            "error": None,
        }

    monkeypatch.setattr(deploy_service, "get_apply_plan_job", fake_get_apply_plan_job)

    resp = api_client.get(f"/funnels/{funnel_id}/deploy-jobs/job-789")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "job-789"
    assert body["status"] == "succeeded"
    assert body["access_urls"] == ["https://landing.example.com/"]
