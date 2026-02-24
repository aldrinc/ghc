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
    assert status["shopDomains"] == ["example.myshopify.com"]
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
    assert status["shopDomains"] == ["example.myshopify.com"]
    assert status["hasStorefrontAccessToken"] is True


def test_status_write_scopes_imply_read_scopes(monkeypatch):
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
                        "write_orders",
                        "write_products",
                        "write_discounts",
                        "unauthenticated_read_product_listings",
                    }
                ),
                uninstalled_at=None,
            )
        ],
    )

    status = shopify_connection.get_client_shopify_connection_status(client_id="client_1")

    assert status["state"] == "ready"
    assert status["missingScopes"] == []


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


def test_get_client_shopify_product_parses_response(monkeypatch):
    def fake_bridge_request(*, method: str, path: str, json_body=None):
        assert method == "POST"
        assert path == "/v1/catalog/products/get"
        assert json_body["clientId"] == "client_1"
        assert json_body["productGid"] == "gid://shopify/Product/123"
        return {
            "shopDomain": "example.myshopify.com",
            "productGid": "gid://shopify/Product/123",
            "title": "Sleep Drops",
            "handle": "sleep-drops",
            "status": "ACTIVE",
            "variants": [
                {
                    "variantGid": "gid://shopify/ProductVariant/1",
                    "title": "Default Title",
                    "priceCents": 4999,
                    "currency": "USD",
                    "compareAtPriceCents": 5999,
                    "sku": "SKU-001",
                    "barcode": "BAR-001",
                    "taxable": True,
                    "requiresShipping": True,
                    "inventoryPolicy": "continue",
                    "inventoryManagement": "shopify",
                    "inventoryQuantity": 5,
                    "optionValues": {"Size": "L"},
                }
            ],
        }

    monkeypatch.setattr(shopify_connection, "_bridge_request", fake_bridge_request)

    response = shopify_connection.get_client_shopify_product(
        client_id="client_1",
        product_gid="gid://shopify/Product/123",
    )

    assert response["shopDomain"] == "example.myshopify.com"
    assert response["productGid"] == "gid://shopify/Product/123"
    assert response["variants"][0]["variantGid"] == "gid://shopify/ProductVariant/1"
    assert response["variants"][0]["inventoryPolicy"] == "continue"
    assert response["variants"][0]["optionValues"] == {"Size": "L"}


def test_get_client_shopify_product_rejects_invalid_product_gid():
    try:
        shopify_connection.get_client_shopify_product(
            client_id="client_1",
            product_gid="gid://shopify/ProductVariant/123",
        )
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "productGid must be a Shopify product GID."
    else:
        raise AssertionError("Expected get_client_shopify_product to reject invalid product gid")


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


def test_update_client_shopify_variant_parses_response(monkeypatch):
    def fake_bridge_request(*, method: str, path: str, json_body=None):
        assert method == "PATCH"
        assert path == "/v1/catalog/variants"
        assert json_body["clientId"] == "client_1"
        assert json_body["variantGid"] == "gid://shopify/ProductVariant/222"
        assert json_body["priceCents"] == 5999
        return {
            "shopDomain": "example.myshopify.com",
            "productGid": "gid://shopify/Product/123",
            "variantGid": "gid://shopify/ProductVariant/222",
        }

    monkeypatch.setattr(shopify_connection, "_bridge_request", fake_bridge_request)

    response = shopify_connection.update_client_shopify_variant(
        client_id="client_1",
        variant_gid="gid://shopify/ProductVariant/222",
        fields={"priceCents": 5999},
    )

    assert response["shopDomain"] == "example.myshopify.com"
    assert response["productGid"] == "gid://shopify/Product/123"
    assert response["variantGid"] == "gid://shopify/ProductVariant/222"


def test_update_client_shopify_variant_sends_inventory_related_fields(monkeypatch):
    def fake_bridge_request(*, method: str, path: str, json_body=None):
        assert method == "PATCH"
        assert path == "/v1/catalog/variants"
        assert json_body["clientId"] == "client_1"
        assert json_body["variantGid"] == "gid://shopify/ProductVariant/222"
        assert json_body["sku"] == "SKU-001"
        assert json_body["barcode"] == "BAR-001"
        assert json_body["inventoryPolicy"] == "continue"
        assert json_body["inventoryManagement"] == "shopify"
        return {
            "shopDomain": "example.myshopify.com",
            "productGid": "gid://shopify/Product/123",
            "variantGid": "gid://shopify/ProductVariant/222",
        }

    monkeypatch.setattr(shopify_connection, "_bridge_request", fake_bridge_request)

    response = shopify_connection.update_client_shopify_variant(
        client_id="client_1",
        variant_gid="gid://shopify/ProductVariant/222",
        fields={
            "sku": "SKU-001",
            "barcode": "BAR-001",
            "inventoryPolicy": "continue",
            "inventoryManagement": "shopify",
        },
    )

    assert response["shopDomain"] == "example.myshopify.com"
    assert response["productGid"] == "gid://shopify/Product/123"
    assert response["variantGid"] == "gid://shopify/ProductVariant/222"


def test_update_client_shopify_variant_rejects_invalid_fields():
    try:
        shopify_connection.update_client_shopify_variant(
            client_id="client_1",
            variant_gid="gid://shopify/ProductVariant/222",
            fields={"currency": "USD"},
        )
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "Unsupported Shopify variant update fields" in exc.detail
    else:
        raise AssertionError("Expected update_client_shopify_variant to reject unsupported fields")


def test_update_client_shopify_variant_rejects_invalid_inventory_management():
    try:
        shopify_connection.update_client_shopify_variant(
            client_id="client_1",
            variant_gid="gid://shopify/ProductVariant/222",
            fields={"inventoryManagement": "manual"},
        )
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "inventoryManagement must be null or 'shopify'" in exc.detail
    else:
        raise AssertionError("Expected update_client_shopify_variant to reject invalid inventoryManagement")


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


def test_upsert_client_shopify_policy_pages_parses_response(monkeypatch):
    def fake_bridge_request(*, method: str, path: str, json_body=None):
        assert method == "POST"
        assert path == "/v1/policies/pages/upsert"
        assert json_body["clientId"] == "client_1"
        assert json_body["pages"][0]["pageKey"] == "privacy_policy"
        return {
            "shopDomain": "example.myshopify.com",
            "pages": [
                {
                    "pageKey": "privacy_policy",
                    "pageId": "gid://shopify/Page/101",
                    "title": "Privacy Policy",
                    "handle": "privacy-policy",
                    "url": "https://example.myshopify.com/pages/privacy-policy",
                    "operation": "created",
                }
            ],
        }

    monkeypatch.setattr(shopify_connection, "_bridge_request", fake_bridge_request)

    response = shopify_connection.upsert_client_shopify_policy_pages(
        client_id="client_1",
        pages=[
            {
                "pageKey": "privacy_policy",
                "title": "Privacy Policy",
                "handle": "privacy-policy",
                "bodyHtml": "<h1>Privacy Policy</h1>",
            }
        ],
    )

    assert response["shopDomain"] == "example.myshopify.com"
    assert response["pages"][0]["pageId"] == "gid://shopify/Page/101"
    assert response["pages"][0]["operation"] == "created"


def test_upsert_client_shopify_policy_pages_rejects_empty_pages():
    try:
        shopify_connection.upsert_client_shopify_policy_pages(client_id="client_1", pages=[])
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "pages must contain at least one policy page."
    else:
        raise AssertionError("Expected upsert_client_shopify_policy_pages to reject empty pages")


def test_sync_client_shopify_theme_brand_parses_response(monkeypatch):
    def fake_bridge_request(*, method: str, path: str, json_body=None):
        assert method == "POST"
        assert path == "/v1/themes/brand/sync"
        assert json_body["clientId"] == "client_1"
        assert json_body["workspaceName"] == "Acme Workspace"
        assert json_body["brandName"] == "Acme"
        assert json_body["themeName"] == "futrgroup2-0theme"
        assert json_body["logoUrl"] == "https://assets.example.com/public/assets/logo-1"
        assert json_body["cssVars"]["--color-brand"] == "#123456"
        return {
            "shopDomain": "example.myshopify.com",
            "themeId": "gid://shopify/OnlineStoreTheme/1",
            "themeName": "Main Theme",
            "themeRole": "MAIN",
            "layoutFilename": "layout/theme.liquid",
            "cssFilename": "assets/acme-workspace-workspace-brand.css",
            "jobId": "gid://shopify/Job/1",
        }

    monkeypatch.setattr(shopify_connection, "_bridge_request", fake_bridge_request)

    response = shopify_connection.sync_client_shopify_theme_brand(
        client_id="client_1",
        workspace_name="Acme Workspace",
        brand_name="Acme",
        logo_url="https://assets.example.com/public/assets/logo-1",
        css_vars={"--color-brand": "#123456"},
        font_urls=["https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap"],
        data_theme="light",
        theme_name="futrgroup2-0theme",
    )

    assert response == {
        "shopDomain": "example.myshopify.com",
        "themeId": "gid://shopify/OnlineStoreTheme/1",
        "themeName": "Main Theme",
        "themeRole": "MAIN",
        "layoutFilename": "layout/theme.liquid",
        "cssFilename": "assets/acme-workspace-workspace-brand.css",
        "jobId": "gid://shopify/Job/1",
    }


def test_sync_client_shopify_theme_brand_rejects_invalid_css_key():
    try:
        shopify_connection.sync_client_shopify_theme_brand(
            client_id="client_1",
            workspace_name="Acme Workspace",
            brand_name="Acme",
            logo_url="https://assets.example.com/public/assets/logo-1",
            css_vars={"color-brand": "#123456"},
            theme_name="futrgroup2-0theme",
        )
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "cssVars keys must be valid CSS custom properties" in exc.detail
    else:
        raise AssertionError("Expected sync_client_shopify_theme_brand to reject invalid cssVars keys")
