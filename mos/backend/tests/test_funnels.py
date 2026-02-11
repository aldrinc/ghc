from fastapi.testclient import TestClient

from sqlalchemy import select

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
