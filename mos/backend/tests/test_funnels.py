from fastapi.testclient import TestClient


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
