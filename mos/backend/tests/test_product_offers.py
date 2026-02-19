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


def test_create_variant_requires_external_price_id_for_shopify_provider(api_client):
    client_id = _create_client(api_client, name="Shopify Variant Missing External")
    product_id = _create_product(api_client, client_id=client_id, title="Primary Product")

    response = api_client.post(
        f"/products/{product_id}/variants",
        json={
            "title": "Primary Variant",
            "price": 9900,
            "currency": "usd",
            "provider": "shopify",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == 'Shopify provider requires externalPriceId (gid://shopify/ProductVariant/...).'


def test_create_variant_rejects_non_gid_external_price_id_for_shopify_provider(api_client):
    client_id = _create_client(api_client, name="Shopify Variant Invalid External")
    product_id = _create_product(api_client, client_id=client_id, title="Primary Product")

    response = api_client.post(
        f"/products/{product_id}/variants",
        json={
            "title": "Primary Variant",
            "price": 9900,
            "currency": "usd",
            "provider": "shopify",
            "externalPriceId": "price_test_123",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Shopify externalPriceId must be a Shopify variant GID."


def test_update_variant_rejects_shopify_gid_with_non_shopify_provider(api_client):
    client_id = _create_client(api_client, name="Shopify Variant Update Validation")
    product_id = _create_product(api_client, client_id=client_id, title="Primary Product")

    create_resp = api_client.post(
        f"/products/{product_id}/variants",
        json={
            "title": "Primary Variant",
            "price": 9900,
            "currency": "usd",
            "provider": "stripe",
            "externalPriceId": "price_test_123",
        },
    )
    assert create_resp.status_code == 201
    variant_id = create_resp.json()["id"]

    update_resp = api_client.patch(
        f"/products/variants/{variant_id}",
        json={"externalPriceId": "gid://shopify/ProductVariant/123456789"},
    )
    assert update_resp.status_code == 400
    assert update_resp.json()["detail"] == 'Shopify variant GIDs require provider="shopify".'


def test_update_shopify_managed_variant_propagates_to_shopify(api_client, monkeypatch):
    client_id = _create_client(api_client, name="Shopify Variant Propagation")
    product_id = _create_product(api_client, client_id=client_id, title="Primary Product")

    create_resp = api_client.post(
        f"/products/{product_id}/variants",
        json={
            "title": "Primary Variant",
            "price": 9900,
            "currency": "usd",
            "provider": "shopify",
            "externalPriceId": "gid://shopify/ProductVariant/123456789",
        },
    )
    assert create_resp.status_code == 201
    variant_id = create_resp.json()["id"]

    observed: dict[str, object] = {}

    def fake_status(*, client_id: str, selected_shop_domain: str | None = None):
        observed["status_client_id"] = client_id
        observed["selected_shop_domain"] = selected_shop_domain
        return {
            "state": "ready",
            "message": "Shopify connection is ready.",
            "shopDomain": "example.myshopify.com",
            "shopDomains": [],
            "selectedShopDomain": selected_shop_domain,
            "hasStorefrontAccessToken": True,
            "missingScopes": [],
        }

    def fake_update_variant(*, client_id: str, variant_gid: str, fields: dict, shop_domain: str | None = None):
        observed["update_client_id"] = client_id
        observed["variant_gid"] = variant_gid
        observed["fields"] = fields
        observed["shop_domain"] = shop_domain
        return {
            "shopDomain": shop_domain or "example.myshopify.com",
            "productGid": "gid://shopify/Product/101",
            "variantGid": variant_gid,
        }

    monkeypatch.setattr(products_router, "get_client_shopify_connection_status", fake_status)
    monkeypatch.setattr(products_router, "update_client_shopify_variant", fake_update_variant)

    update_resp = api_client.patch(
        f"/products/variants/{variant_id}",
        json={
            "title": "Updated Variant",
            "price": 10900,
            "compareAtPrice": 12900,
        },
    )
    assert update_resp.status_code == 200
    body = update_resp.json()
    assert body["title"] == "Updated Variant"
    assert body["price"] == 10900
    assert body["compare_at_price"] == 12900

    assert observed["status_client_id"] == client_id
    assert observed["variant_gid"] == "gid://shopify/ProductVariant/123456789"
    assert observed["fields"] == {
        "title": "Updated Variant",
        "priceCents": 10900,
        "compareAtPriceCents": 12900,
    }
    assert observed["shop_domain"] == "example.myshopify.com"
    assert body["shopify_last_synced_at"] is not None
    assert body["shopify_last_sync_error"] is None


def test_update_shopify_managed_variant_propagates_inventory_related_fields(api_client, monkeypatch):
    client_id = _create_client(api_client, name="Shopify Variant Inventory Propagation")
    product_id = _create_product(api_client, client_id=client_id, title="Primary Product")

    create_resp = api_client.post(
        f"/products/{product_id}/variants",
        json={
            "title": "Primary Variant",
            "price": 9900,
            "currency": "usd",
            "provider": "shopify",
            "externalPriceId": "gid://shopify/ProductVariant/123456789",
        },
    )
    assert create_resp.status_code == 201
    variant_id = create_resp.json()["id"]

    observed: dict[str, object] = {}

    def fake_status(*, client_id: str, selected_shop_domain: str | None = None):
        return {
            "state": "ready",
            "message": "Shopify connection is ready.",
            "shopDomain": "example.myshopify.com",
            "shopDomains": [],
            "selectedShopDomain": selected_shop_domain,
            "hasStorefrontAccessToken": True,
            "missingScopes": [],
        }

    def fake_update_variant(*, client_id: str, variant_gid: str, fields: dict, shop_domain: str | None = None):
        observed["variant_gid"] = variant_gid
        observed["fields"] = fields
        observed["shop_domain"] = shop_domain
        return {
            "shopDomain": shop_domain or "example.myshopify.com",
            "productGid": "gid://shopify/Product/101",
            "variantGid": variant_gid,
        }

    monkeypatch.setattr(products_router, "get_client_shopify_connection_status", fake_status)
    monkeypatch.setattr(products_router, "update_client_shopify_variant", fake_update_variant)

    update_resp = api_client.patch(
        f"/products/variants/{variant_id}",
        json={
            "sku": "SKU-001",
            "barcode": "BAR-001",
            "inventoryPolicy": "continue",
            "inventoryManagement": "shopify",
        },
    )
    assert update_resp.status_code == 200
    body = update_resp.json()
    assert body["sku"] == "SKU-001"
    assert body["barcode"] == "BAR-001"
    assert body["inventory_policy"] == "continue"
    assert body["inventory_management"] == "shopify"
    assert body["shopify_last_synced_at"] is not None
    assert body["shopify_last_sync_error"] is None

    assert observed["variant_gid"] == "gid://shopify/ProductVariant/123456789"
    assert observed["fields"] == {
        "sku": "SKU-001",
        "barcode": "BAR-001",
        "inventoryPolicy": "continue",
        "inventoryManagement": "shopify",
    }
    assert observed["shop_domain"] == "example.myshopify.com"


def test_update_shopify_managed_variant_records_sync_error(api_client, monkeypatch):
    client_id = _create_client(api_client, name="Shopify Variant Sync Error")
    product_id = _create_product(api_client, client_id=client_id, title="Primary Product")

    create_resp = api_client.post(
        f"/products/{product_id}/variants",
        json={
            "title": "Primary Variant",
            "price": 9900,
            "currency": "usd",
            "provider": "shopify",
            "externalPriceId": "gid://shopify/ProductVariant/123456789",
        },
    )
    assert create_resp.status_code == 201
    variant_id = create_resp.json()["id"]

    def fake_status(*, client_id: str, selected_shop_domain: str | None = None):
        return {
            "state": "ready",
            "message": "Shopify connection is ready.",
            "shopDomain": "example.myshopify.com",
            "shopDomains": [],
            "selectedShopDomain": selected_shop_domain,
            "hasStorefrontAccessToken": True,
            "missingScopes": [],
        }

    def fake_update_variant(*, client_id: str, variant_gid: str, fields: dict, shop_domain: str | None = None):
        raise HTTPException(status_code=502, detail="Shopify checkout app error: upstream timeout")

    monkeypatch.setattr(products_router, "get_client_shopify_connection_status", fake_status)
    monkeypatch.setattr(products_router, "update_client_shopify_variant", fake_update_variant)

    update_resp = api_client.patch(
        f"/products/variants/{variant_id}",
        json={"price": 10900},
    )
    assert update_resp.status_code == 502
    assert "upstream timeout" in update_resp.json()["detail"]

    detail_resp = api_client.get(f"/products/{product_id}")
    assert detail_resp.status_code == 200
    variants = detail_resp.json().get("variants") or []
    updated_variant = next(item for item in variants if item["id"] == variant_id)
    assert updated_variant["shopify_last_synced_at"] is None
    assert updated_variant["shopify_last_sync_error"] == "Shopify checkout app error: upstream timeout"


def test_update_shopify_managed_variant_requires_ready_shopify_connection(api_client, monkeypatch):
    client_id = _create_client(api_client, name="Shopify Variant Not Ready")
    product_id = _create_product(api_client, client_id=client_id, title="Primary Product")

    create_resp = api_client.post(
        f"/products/{product_id}/variants",
        json={
            "title": "Primary Variant",
            "price": 9900,
            "currency": "usd",
            "provider": "shopify",
            "externalPriceId": "gid://shopify/ProductVariant/123456789",
        },
    )
    assert create_resp.status_code == 201
    variant_id = create_resp.json()["id"]

    called = {"value": False}

    def fake_status(*, client_id: str, selected_shop_domain: str | None = None):
        return {
            "state": "installed_missing_storefront_token",
            "message": "Shopify is installed but missing storefront access token.",
            "shopDomain": "example.myshopify.com",
            "shopDomains": [],
            "selectedShopDomain": selected_shop_domain,
            "hasStorefrontAccessToken": False,
            "missingScopes": [],
        }

    def fake_update_variant(*, client_id: str, variant_gid: str, fields: dict, shop_domain: str | None = None):
        called["value"] = True
        return {}

    monkeypatch.setattr(products_router, "get_client_shopify_connection_status", fake_status)
    monkeypatch.setattr(products_router, "update_client_shopify_variant", fake_update_variant)

    update_resp = api_client.patch(
        f"/products/variants/{variant_id}",
        json={"price": 10100},
    )
    assert update_resp.status_code == 409
    assert "Shopify connection is not ready" in update_resp.json()["detail"]
    assert called["value"] is False


def test_update_shopify_managed_variant_rejects_currency_change(api_client, monkeypatch):
    client_id = _create_client(api_client, name="Shopify Variant Currency Change")
    product_id = _create_product(api_client, client_id=client_id, title="Primary Product")

    create_resp = api_client.post(
        f"/products/{product_id}/variants",
        json={
            "title": "Primary Variant",
            "price": 9900,
            "currency": "usd",
            "provider": "shopify",
            "externalPriceId": "gid://shopify/ProductVariant/123456789",
        },
    )
    assert create_resp.status_code == 201
    variant_id = create_resp.json()["id"]

    update_resp = api_client.patch(
        f"/products/variants/{variant_id}",
        json={"currency": "eur"},
    )
    assert update_resp.status_code == 409
    assert "currency cannot be changed" in update_resp.json()["detail"]


def test_create_shopify_product_for_product_imports_shopify_variants(api_client, monkeypatch):
    client_id = _create_client(api_client, name="Shopify Product Import")
    product_id = _create_product(api_client, client_id=client_id, title="Primary Product")

    def fake_status(*, client_id: str, selected_shop_domain: str | None = None):
        return {
            "state": "ready",
            "message": "Shopify connection is ready.",
            "shopDomain": selected_shop_domain or "example.myshopify.com",
            "shopDomains": [],
            "selectedShopDomain": selected_shop_domain,
            "hasStorefrontAccessToken": True,
            "missingScopes": [],
        }

    def fake_create_client_shopify_product(
        *,
        client_id: str,
        title: str,
        variants: list[dict],
        description: str | None,
        handle: str | None,
        vendor: str | None,
        product_type: str | None,
        tags: list[str] | None,
        status_text: str,
        shop_domain: str | None,
    ):
        assert client_id
        assert title == "Sleep Drops"
        assert variants
        return {
            "shopDomain": "example.myshopify.com",
            "productGid": "gid://shopify/Product/800",
            "title": "Sleep Drops",
            "handle": "sleep-drops",
            "status": "DRAFT",
            "variants": [
                {
                    "variantGid": "gid://shopify/ProductVariant/801",
                    "title": "Starter",
                    "priceCents": 4999,
                    "currency": "USD",
                },
                {
                    "variantGid": "gid://shopify/ProductVariant/802",
                    "title": "Bundle",
                    "priceCents": 7900,
                    "currency": "USD",
                },
            ],
        }

    monkeypatch.setattr(products_router, "get_client_shopify_connection_status", fake_status)
    monkeypatch.setattr(products_router, "create_client_shopify_product", fake_create_client_shopify_product)

    response = api_client.post(
        f"/products/{product_id}/shopify/create",
        json={
            "title": "Sleep Drops",
            "status": "DRAFT",
            "variants": [
                {"title": "Starter", "priceCents": 4999, "currency": "USD"},
                {"title": "Bundle", "priceCents": 7900, "currency": "USD"},
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["productGid"] == "gid://shopify/Product/800"

    product_detail = api_client.get(f"/products/{product_id}")
    assert product_detail.status_code == 200
    body = product_detail.json()
    assert body["shopify_product_gid"] == "gid://shopify/Product/800"
    variants = body.get("variants") or []
    assert len(variants) == 2
    assert {variant["external_price_id"] for variant in variants} == {
        "gid://shopify/ProductVariant/801",
        "gid://shopify/ProductVariant/802",
    }
    assert all(variant["provider"] == "shopify" for variant in variants)


def test_create_shopify_product_for_product_rejects_existing_mapping(api_client):
    client_id = _create_client(api_client, name="Shopify Product Already Mapped")
    product_id = _create_product(
        api_client,
        client_id=client_id,
        title="Primary Product",
        shopify_product_gid="gid://shopify/Product/123",
    )

    response = api_client.post(
        f"/products/{product_id}/shopify/create",
        json={
            "title": "Sleep Drops",
            "status": "DRAFT",
            "variants": [{"title": "Starter", "priceCents": 4999, "currency": "USD"}],
        },
    )
    assert response.status_code == 409
    assert "already mapped to Shopify" in response.json()["detail"]


def test_create_shopify_product_for_product_requires_ready_connection(api_client, monkeypatch):
    client_id = _create_client(api_client, name="Shopify Product Not Ready")
    product_id = _create_product(api_client, client_id=client_id, title="Primary Product")

    def fake_status(*, client_id: str, selected_shop_domain: str | None = None):
        return {
            "state": "installed_missing_storefront_token",
            "message": "Shopify is installed but missing storefront access token.",
            "shopDomain": "example.myshopify.com",
            "shopDomains": [],
            "selectedShopDomain": selected_shop_domain,
            "hasStorefrontAccessToken": False,
            "missingScopes": [],
        }

    monkeypatch.setattr(products_router, "get_client_shopify_connection_status", fake_status)

    response = api_client.post(
        f"/products/{product_id}/shopify/create",
        json={
            "title": "Sleep Drops",
            "status": "DRAFT",
            "variants": [{"title": "Starter", "priceCents": 4999, "currency": "USD"}],
        },
    )
    assert response.status_code == 409
    assert "Shopify connection is not ready" in response.json()["detail"]


def test_create_shopify_product_for_product_rejects_duplicate_shopify_variant_title(api_client, monkeypatch):
    client_id = _create_client(api_client, name="Shopify Product Duplicate Title")
    product_id = _create_product(api_client, client_id=client_id, title="Primary Product")

    existing_variant_resp = api_client.post(
        f"/products/{product_id}/variants",
        json={
            "title": "Starter",
            "price": 4900,
            "currency": "usd",
            "provider": "shopify",
            "externalPriceId": "gid://shopify/ProductVariant/777",
        },
    )
    assert existing_variant_resp.status_code == 201

    def fake_status(*, client_id: str, selected_shop_domain: str | None = None):
        return {
            "state": "ready",
            "message": "Shopify connection is ready.",
            "shopDomain": selected_shop_domain or "example.myshopify.com",
            "shopDomains": [],
            "selectedShopDomain": selected_shop_domain,
            "hasStorefrontAccessToken": True,
            "missingScopes": [],
        }

    observed = {"called": False}

    def fake_create_client_shopify_product(
        *,
        client_id: str,
        title: str,
        variants: list[dict],
        description: str | None,
        handle: str | None,
        vendor: str | None,
        product_type: str | None,
        tags: list[str] | None,
        status_text: str,
        shop_domain: str | None,
    ):
        observed["called"] = True
        return {
            "shopDomain": "example.myshopify.com",
            "productGid": "gid://shopify/Product/888",
            "title": "Sleep Drops",
            "handle": "sleep-drops",
            "status": "DRAFT",
            "variants": [
                {
                    "variantGid": "gid://shopify/ProductVariant/889",
                    "title": "Starter",
                    "priceCents": 4999,
                    "currency": "USD",
                }
            ],
        }

    monkeypatch.setattr(products_router, "get_client_shopify_connection_status", fake_status)
    monkeypatch.setattr(products_router, "create_client_shopify_product", fake_create_client_shopify_product)

    response = api_client.post(
        f"/products/{product_id}/shopify/create",
        json={
            "title": "Sleep Drops",
            "status": "DRAFT",
            "variants": [{"title": "Starter", "priceCents": 4999, "currency": "USD"}],
        },
    )
    assert observed["called"] is True
    assert response.status_code == 409
    assert response.json()["detail"] == 'Shopify variant title "Starter" already exists for this product.'
