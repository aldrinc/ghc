from __future__ import annotations

from fastapi import HTTPException

from app.routers import products as products_router


def _create_client(api_client, *, name: str) -> str:
    response = api_client.post("/clients", json={"name": name, "industry": "Retail"})
    assert response.status_code == 201
    return response.json()["id"]


def _create_product(
    api_client,
    *,
    client_id: str,
    title: str,
    shopify_product_gid: str | None = None,
) -> str:
    payload: dict[str, object] = {
        "clientId": client_id,
        "title": title,
    }
    if shopify_product_gid is not None:
        payload["shopifyProductGid"] = shopify_product_gid
    response = api_client.post("/products", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def _create_offer(api_client, *, product_id: str) -> str:
    response = api_client.post(
        f"/products/{product_id}/offers",
        json={
            "productId": product_id,
            "name": "Starter Pack",
            "businessModel": "one_time",
            "description": "Primary offer",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_add_offer_bonus_verifies_shopify_product(api_client, monkeypatch):
    client_id = _create_client(api_client, name="Offer Bonus Client")
    primary_product_id = _create_product(
        api_client,
        client_id=client_id,
        title="Primary Product",
        shopify_product_gid="gid://shopify/Product/111",
    )
    offer_id = _create_offer(api_client, product_id=primary_product_id)
    bonus_product_id = _create_product(
        api_client,
        client_id=client_id,
        title="Bonus Product",
        shopify_product_gid="gid://shopify/Product/222",
    )

    observed: dict[str, str] = {}

    def fake_verify(*, client_id: str, product_gid: str) -> None:
        observed["client_id"] = client_id
        observed["product_gid"] = product_gid

    monkeypatch.setattr(products_router, "verify_shopify_product_exists", fake_verify)

    response = api_client.post(
        f"/products/offers/{offer_id}/bonuses",
        json={"bonusProductId": bonus_product_id},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["bonus_product"]["id"] == bonus_product_id
    assert observed["product_gid"] == "gid://shopify/Product/222"

    detail = api_client.get(f"/products/{primary_product_id}")
    assert detail.status_code == 200
    offers = detail.json().get("offers") or []
    assert len(offers) == 1
    assert len(offers[0].get("bonuses") or []) == 1
    assert offers[0]["bonuses"][0]["bonus_product"]["id"] == bonus_product_id


def test_add_offer_bonus_requires_shopify_product_gid(api_client, monkeypatch):
    client_id = _create_client(api_client, name="Offer Bonus Missing GID")
    primary_product_id = _create_product(
        api_client,
        client_id=client_id,
        title="Primary Product",
        shopify_product_gid="gid://shopify/Product/333",
    )
    offer_id = _create_offer(api_client, product_id=primary_product_id)
    bonus_product_id = _create_product(
        api_client,
        client_id=client_id,
        title="Bonus Without Shopify GID",
    )

    called = {"value": False}

    def fake_verify(*, client_id: str, product_gid: str) -> None:
        called["value"] = True

    monkeypatch.setattr(products_router, "verify_shopify_product_exists", fake_verify)

    response = api_client.post(
        f"/products/offers/{offer_id}/bonuses",
        json={"bonusProductId": bonus_product_id},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Bonus product must include a Shopify product GID."
    assert called["value"] is False


def test_add_offer_bonus_bubbles_shopify_verification_error(api_client, monkeypatch):
    client_id = _create_client(api_client, name="Offer Bonus Verification Failure")
    primary_product_id = _create_product(
        api_client,
        client_id=client_id,
        title="Primary Product",
        shopify_product_gid="gid://shopify/Product/444",
    )
    offer_id = _create_offer(api_client, product_id=primary_product_id)
    bonus_product_id = _create_product(
        api_client,
        client_id=client_id,
        title="Bonus Product",
        shopify_product_gid="gid://shopify/Product/555",
    )

    def fake_verify(*, client_id: str, product_gid: str) -> None:
        raise HTTPException(status_code=404, detail="Shopify checkout app error: Product not found")

    monkeypatch.setattr(products_router, "verify_shopify_product_exists", fake_verify)

    response = api_client.post(
        f"/products/offers/{offer_id}/bonuses",
        json={"bonusProductId": bonus_product_id},
    )
    assert response.status_code == 404
    assert "Product not found" in response.json()["detail"]

    bonuses = api_client.get(f"/products/offers/{offer_id}/bonuses")
    assert bonuses.status_code == 200
    assert bonuses.json() == []


def test_create_variant_with_offer_id(api_client):
    client_id = _create_client(api_client, name="Offer Variant Link")
    product_id = _create_product(
        api_client,
        client_id=client_id,
        title="Primary Product",
        shopify_product_gid="gid://shopify/Product/701",
    )
    offer_id = _create_offer(api_client, product_id=product_id)

    response = api_client.post(
        f"/products/{product_id}/variants",
        json={
            "title": "Primary Variant",
            "price": 9900,
            "currency": "usd",
            "offerId": offer_id,
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["offer_id"] == offer_id


def test_create_variant_rejects_offer_from_other_product(api_client):
    client_id = _create_client(api_client, name="Offer Variant Scope")
    primary_product_id = _create_product(api_client, client_id=client_id, title="Primary Product")
    secondary_product_id = _create_product(api_client, client_id=client_id, title="Secondary Product")
    secondary_offer_id = _create_offer(api_client, product_id=secondary_product_id)

    response = api_client.post(
        f"/products/{primary_product_id}/variants",
        json={
            "title": "Primary Variant",
            "price": 10900,
            "currency": "usd",
            "offerId": secondary_offer_id,
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "offerId must belong to the selected product."
