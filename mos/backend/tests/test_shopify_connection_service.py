from app.services import shopify_connection
from app.services.shopify_connection import ShopifyInstallation
from fastapi import HTTPException


def test_status_not_connected(monkeypatch):
    monkeypatch.setattr(shopify_connection, "list_shopify_installations", lambda: [])

    status = shopify_connection.get_client_shopify_connection_status(client_id="client_1")

    assert status["state"] == "not_connected"
    assert status["shopDomain"] is None


def test_status_missing_storefront_token(monkeypatch):
    monkeypatch.setattr(
        shopify_connection,
        "list_shopify_installations",
        lambda: [
            ShopifyInstallation(
                shop_domain="example.myshopify.com",
                client_id="client_1",
                has_storefront_access_token=False,
                scopes=sorted(
                    {
                        "read_orders",
                        "write_orders",
                        "unauthenticated_read_product_listings",
                        "read_products",
                        "write_products",
                        "read_discounts",
                        "write_discounts",
                    }
                ),
                uninstalled_at=None,
            )
        ],
    )

    status = shopify_connection.get_client_shopify_connection_status(client_id="client_1")

    assert status["state"] == "installed_missing_storefront_token"
    assert status["shopDomain"] == "example.myshopify.com"
    assert status["hasStorefrontAccessToken"] is False


def test_status_multiple_installations_conflict(monkeypatch):
    monkeypatch.setattr(
        shopify_connection,
        "list_shopify_installations",
        lambda: [
            ShopifyInstallation(
                shop_domain="one.myshopify.com",
                client_id="client_1",
                has_storefront_access_token=True,
                scopes=[],
                uninstalled_at=None,
            ),
            ShopifyInstallation(
                shop_domain="two.myshopify.com",
                client_id="client_1",
                has_storefront_access_token=True,
                scopes=[],
                uninstalled_at=None,
            ),
        ],
    )

    status = shopify_connection.get_client_shopify_connection_status(client_id="client_1")

    assert status["state"] == "multiple_installations_conflict"
    assert status["shopDomains"] == ["one.myshopify.com", "two.myshopify.com"]


def test_status_multiple_installations_uses_selected_shop(monkeypatch):
    monkeypatch.setattr(
        shopify_connection,
        "list_shopify_installations",
        lambda: [
            ShopifyInstallation(
                shop_domain="one.myshopify.com",
                client_id="client_1",
                has_storefront_access_token=True,
                scopes=sorted(
                    {
                        "read_orders",
                        "write_orders",
                        "unauthenticated_read_product_listings",
                        "read_products",
                        "write_products",
                        "read_discounts",
                        "write_discounts",
                    }
                ),
                uninstalled_at=None,
            ),
            ShopifyInstallation(
                shop_domain="two.myshopify.com",
                client_id="client_1",
                has_storefront_access_token=True,
                scopes=sorted(
                    {
                        "read_orders",
                        "write_orders",
                        "unauthenticated_read_product_listings",
                        "read_products",
                        "write_products",
                        "read_discounts",
                        "write_discounts",
                    }
                ),
                uninstalled_at=None,
            ),
        ],
    )

    status = shopify_connection.get_client_shopify_connection_status(
        client_id="client_1",
        selected_shop_domain="two.myshopify.com",
    )

    assert status["state"] == "ready"
    assert status["shopDomain"] == "two.myshopify.com"
    assert status["selectedShopDomain"] == "two.myshopify.com"


def test_status_missing_scopes_returns_error(monkeypatch):
    monkeypatch.setattr(
        shopify_connection,
        "list_shopify_installations",
        lambda: [
            ShopifyInstallation(
                shop_domain="example.myshopify.com",
                client_id="client_1",
                has_storefront_access_token=True,
                scopes=["read_products"],
                uninstalled_at=None,
            )
        ],
    )

    status = shopify_connection.get_client_shopify_connection_status(client_id="client_1")

    assert status["state"] == "error"
    assert "write_products" in status["missingScopes"]


def test_status_ready(monkeypatch):
    monkeypatch.setattr(
        shopify_connection,
        "list_shopify_installations",
        lambda: [
            ShopifyInstallation(
                shop_domain="example.myshopify.com",
                client_id="client_1",
                has_storefront_access_token=True,
                scopes=sorted(
                    {
                        "read_orders",
                        "write_orders",
                        "unauthenticated_read_product_listings",
                        "read_products",
                        "write_products",
                        "read_discounts",
                        "write_discounts",
                    }
                ),
                uninstalled_at=None,
            )
        ],
    )

    status = shopify_connection.get_client_shopify_connection_status(client_id="client_1")

    assert status["state"] == "ready"
    assert status["shopDomain"] == "example.myshopify.com"
    assert status["hasStorefrontAccessToken"] is True


def test_list_client_shopify_products_parses_response(monkeypatch):
    def fake_bridge_request(*, method: str, path: str, json_body=None):
        assert method == "POST"
        assert path == "/v1/catalog/products/list"
        assert json_body["clientId"] == "client_1"
        return {
            "shopDomain": "example.myshopify.com",
            "products": [
                {
                    "productGid": "gid://shopify/Product/1",
                    "title": "Alpha",
                    "handle": "alpha",
                    "status": "ACTIVE",
                }
            ],
        }

    monkeypatch.setattr(shopify_connection, "_bridge_request", fake_bridge_request)

    response = shopify_connection.list_client_shopify_products(client_id="client_1", query="alp", limit=20)

    assert response["shopDomain"] == "example.myshopify.com"
    assert response["products"][0]["productGid"] == "gid://shopify/Product/1"


def test_list_client_shopify_products_rejects_out_of_range_limit():
    try:
        shopify_connection.list_client_shopify_products(client_id="client_1", limit=0)
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "limit must be between 1 and 50."
    else:
        raise AssertionError("Expected list_client_shopify_products to reject invalid limit")


def test_create_client_shopify_product_parses_response(monkeypatch):
    def fake_bridge_request(*, method: str, path: str, json_body=None):
        assert method == "POST"
        assert path == "/v1/catalog/products/create"
        assert json_body["clientId"] == "client_1"
        assert json_body["title"] == "Sleep Drops"
        return {
            "shopDomain": "example.myshopify.com",
            "productGid": "gid://shopify/Product/123",
            "title": "Sleep Drops",
            "handle": "sleep-drops",
            "status": "DRAFT",
            "variants": [
                {
                    "variantGid": "gid://shopify/ProductVariant/111",
                    "title": "Starter",
                    "priceCents": 4999,
                    "currency": "USD",
                }
            ],
        }

    monkeypatch.setattr(shopify_connection, "_bridge_request", fake_bridge_request)

    response = shopify_connection.create_client_shopify_product(
        client_id="client_1",
        title="Sleep Drops",
        variants=[{"title": "Starter", "priceCents": 4999, "currency": "USD"}],
    )

    assert response["shopDomain"] == "example.myshopify.com"
    assert response["productGid"] == "gid://shopify/Product/123"
    assert response["variants"][0]["variantGid"] == "gid://shopify/ProductVariant/111"


def test_disconnect_client_shopify_store_unlinks_workspace(monkeypatch):
    monkeypatch.setattr(
        shopify_connection,
        "list_shopify_installations",
        lambda: [
            ShopifyInstallation(
                shop_domain="example.myshopify.com",
                client_id="client_1",
                has_storefront_access_token=True,
                scopes=[],
                uninstalled_at=None,
            )
        ],
    )

    observed: dict[str, object] = {}

    def fake_bridge_request(*, method: str, path: str, json_body=None):
        observed["method"] = method
        observed["path"] = path
        observed["json_body"] = json_body
        return {"ok": True}

    monkeypatch.setattr(shopify_connection, "_bridge_request", fake_bridge_request)

    shopify_connection.disconnect_client_shopify_store(
        client_id="client_1",
        shop_domain="example.myshopify.com",
    )

    assert observed == {
        "method": "PATCH",
        "path": "/admin/installations/example.myshopify.com",
        "json_body": {"clientId": None},
    }


def test_disconnect_client_shopify_store_requires_matching_workspace(monkeypatch):
    monkeypatch.setattr(
        shopify_connection,
        "list_shopify_installations",
        lambda: [
            ShopifyInstallation(
                shop_domain="example.myshopify.com",
                client_id="client_other",
                has_storefront_access_token=True,
                scopes=[],
                uninstalled_at=None,
            )
        ],
    )

    try:
        shopify_connection.disconnect_client_shopify_store(
            client_id="client_1",
            shop_domain="example.myshopify.com",
        )
    except HTTPException as exc:
        assert exc.status_code == 409
        assert exc.detail == "This Shopify store is not connected to this workspace. connectedWorkspaceId=client_other"
    else:
        raise AssertionError("Expected disconnect_client_shopify_store to reject mismatched workspace")
