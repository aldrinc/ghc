from uuid import UUID

from sqlalchemy import select

from app.db.models import ClientUserPreference


def test_active_product_defaults_when_only_one_product(api_client):
    client_resp = api_client.post("/clients", json={"name": "Single Product Client", "industry": "SaaS"})
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    prod = api_client.post("/products", json={"clientId": client_id, "title": "Only Product"})
    assert prod.status_code == 201
    prod_id = prod.json()["id"]

    resp = api_client.get(f"/clients/{client_id}/active-product")
    assert resp.status_code == 200
    assert resp.json()["active_product_id"] == prod_id


def test_active_product_defaults_to_latest_and_persists(api_client, db_session, auth_context):
    client_resp = api_client.post("/clients", json={"name": "Pref Client", "industry": "SaaS"})
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    first = api_client.post("/products", json={"clientId": client_id, "title": "First Product"})
    assert first.status_code == 201
    first_id = first.json()["id"]

    second = api_client.post("/products", json={"clientId": client_id, "title": "Second Product"})
    assert second.status_code == 201
    second_id = second.json()["id"]

    resp = api_client.get(f"/clients/{client_id}/active-product")
    assert resp.status_code == 200
    body = resp.json()
    assert body["active_product_id"] in {first_id, second_id}
    assert body["active_product"]["id"] == body["active_product_id"]

    org_uuid = UUID(auth_context.org_id)
    client_uuid = UUID(client_id)
    pref = db_session.scalar(
        select(ClientUserPreference).where(
            ClientUserPreference.org_id == org_uuid,
            ClientUserPreference.client_id == client_uuid,
            ClientUserPreference.user_external_id == auth_context.user_id,
        )
    )
    assert pref is not None
    assert str(pref.active_product_id) == body["active_product_id"]

    # Explicitly set the selection to the first product and confirm it sticks.
    set_resp = api_client.put(f"/clients/{client_id}/active-product", json={"product_id": first_id})
    assert set_resp.status_code == 200
    assert set_resp.json()["active_product_id"] == first_id

    resp2 = api_client.get(f"/clients/{client_id}/active-product")
    assert resp2.status_code == 200
    assert resp2.json()["active_product_id"] == first_id


def test_set_active_product_rejects_cross_client_product(api_client):
    client_a = api_client.post("/clients", json={"name": "Client A", "industry": "SaaS"})
    assert client_a.status_code == 201
    client_a_id = client_a.json()["id"]

    client_b = api_client.post("/clients", json={"name": "Client B", "industry": "SaaS"})
    assert client_b.status_code == 201
    client_b_id = client_b.json()["id"]

    prod_b = api_client.post("/products", json={"clientId": client_b_id, "title": "B Product"})
    assert prod_b.status_code == 201
    prod_b_id = prod_b.json()["id"]

    set_resp = api_client.put(f"/clients/{client_a_id}/active-product", json={"product_id": prod_b_id})
    assert set_resp.status_code == 409
    assert set_resp.json()["detail"] == "Product must belong to the selected client."


def test_active_product_recovers_from_stale_preference(api_client, db_session, auth_context):
    client_a = api_client.post("/clients", json={"name": "Pref Client A", "industry": "SaaS"})
    assert client_a.status_code == 201
    client_a_id = client_a.json()["id"]

    prod_a = api_client.post("/products", json={"clientId": client_a_id, "title": "A Product"})
    assert prod_a.status_code == 201
    prod_a_id = prod_a.json()["id"]

    client_b = api_client.post("/clients", json={"name": "Pref Client B", "industry": "SaaS"})
    assert client_b.status_code == 201
    client_b_id = client_b.json()["id"]

    prod_b = api_client.post("/products", json={"clientId": client_b_id, "title": "B Product"})
    assert prod_b.status_code == 201
    prod_b_id = prod_b.json()["id"]

    org_uuid = UUID(auth_context.org_id)
    client_a_uuid = UUID(client_a_id)
    db_session.add(
        ClientUserPreference(
            org_id=org_uuid,
            client_id=client_a_uuid,
            user_external_id=auth_context.user_id,
            active_product_id=UUID(prod_b_id),  # product exists but belongs to a different client
        )
    )
    db_session.commit()

    resp = api_client.get(f"/clients/{client_a_id}/active-product")
    assert resp.status_code == 200
    assert resp.json()["active_product_id"] == prod_a_id
