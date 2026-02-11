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

    approve = api_client.post(f"/funnels/{funnel_id}/pages/{page_id}/approve")
    assert approve.status_code == 201

    return funnel_id, public_id


def test_funnel_authoring_publish_and_public_runtime(api_client: TestClient):
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

    approve1 = api_client.post(f"/funnels/{funnel_id}/pages/{page1_id}/approve")
    assert approve1.status_code == 201
    approve2 = api_client.post(f"/funnels/{funnel_id}/pages/{page2_id}/approve")
    assert approve2.status_code == 201

    publish = api_client.post(f"/funnels/{funnel_id}/publish")
    assert publish.status_code == 201
    publication_id = publish.json()["publicationId"]

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

    # Approve landing page content but do not publish the funnel (page2 stays unapproved).
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
    approve1 = api_client.post(f"/funnels/{funnel_id}/pages/{page1_id}/approve")
    assert approve1.status_code == 201

    meta = api_client.get(f"/public/funnels/{public_id}/meta")
    assert meta.status_code == 200
    assert meta.json()["publicationId"] == funnel_id
    assert meta.json()["entrySlug"] == page1["slug"]
    assert {"pageId": page1_id, "slug": page1["slug"]} in meta.json()["pages"]
    assert all(p["pageId"] != page2_id for p in meta.json()["pages"])

    public_page = api_client.get(f"/public/funnels/{public_id}/pages/{page1['slug']}")
    assert public_page.status_code == 200
    assert public_page.json()["publicationId"] == funnel_id
    assert public_page.json()["slug"] == page1["slug"]
    assert public_page.json()["puckData"]["content"][0]["props"]["text"] == "Preview"

    # Draft leakage guard: unapproved pages remain unavailable until approved or published.
    unapproved = api_client.get(f"/public/funnels/{public_id}/pages/{page2['slug']}")
    assert unapproved.status_code == 404


def test_publish_with_deploy_builds_funnel_publication_workload_from_db(api_client: TestClient, monkeypatch):
    funnel_id, public_id = _create_publish_ready_funnel(api_client, funnel_name="Deploy Funnel")

    captured: dict[str, object] = {}

    def fake_patch_workload_in_plan(
        *,
        workload_patch,
        plan_path=None,
        instance_name=None,
        create_if_missing=False,
        in_place=False,
    ):
        captured["workload_patch"] = workload_patch
        captured["plan_path"] = plan_path
        captured["instance_name"] = instance_name
        captured["create_if_missing"] = create_if_missing
        captured["in_place"] = in_place
        return {
            "status": "ok",
            "base_plan_path": "/tmp/plan-base.json",
            "updated_plan_path": "/tmp/plan-updated.json",
            "workload_name": workload_patch["name"],
            "updated_count": 1,
        }

    async def fake_apply_plan(*, plan_path=None):
        captured["apply_plan_path"] = plan_path
        return {
            "returncode": 0,
            "plan_path": plan_path,
            "server_ips": {},
            "live_url": None,
            "logs": "",
        }

    monkeypatch.setattr(deploy_service, "patch_workload_in_plan", fake_patch_workload_in_plan)
    monkeypatch.setattr(deploy_service, "apply_plan", fake_apply_plan)

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
    assert body["publicationId"]
    assert body["deploy"]["patch"]["updated_plan_path"] == "/tmp/plan-updated.json"
    assert body["deploy"]["apply"]["returncode"] == 0

    workload_patch = captured["workload_patch"]
    assert workload_patch["source_type"] == "funnel_publication"
    assert workload_patch["source_ref"]["public_id"] == public_id
    assert workload_patch["source_ref"]["upstream_base_url"] == "https://moshq.app"
    assert workload_patch["source_ref"]["upstream_api_base_url"] == f"https://moshq.app/api/public/funnels/{public_id}"
    assert workload_patch["service_config"]["server_names"] == ["landing.example.com"]
    assert captured["apply_plan_path"] == "/tmp/plan-updated.json"


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

    def fake_patch_workload_in_plan(
        *,
        workload_patch,
        plan_path=None,
        instance_name=None,
        create_if_missing=False,
        in_place=False,
    ):
        captured["workload_patch"] = workload_patch
        return {
            "status": "ok",
            "base_plan_path": "/tmp/plan-base.json",
            "updated_plan_path": "/tmp/plan-updated.json",
            "workload_name": workload_patch["name"],
            "updated_count": 1,
        }

    monkeypatch.setattr(deploy_service, "patch_workload_in_plan", fake_patch_workload_in_plan)

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

    workload_patch = captured["workload_patch"]
    assert workload_patch["source_ref"]["public_id"] == public_id
    assert workload_patch["service_config"]["server_names"] == ["offers.example.com"]


def test_publish_with_deploy_errors_when_server_names_unavailable(api_client: TestClient):
    funnel_id, _ = _create_publish_ready_funnel(api_client, funnel_name="Missing Domain Deploy Funnel")

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
    assert resp.status_code == 400
    assert "Deploy server names are required" in resp.json()["detail"]
