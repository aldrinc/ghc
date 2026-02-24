from app.routers import clients as clients_router
from app.services.shopify_connection import ShopifyInstallation


def _create_client(api_client, *, name: str = "Shopify Workspace") -> str:
    response = api_client.post("/clients", json={"name": name, "industry": "Retail"})
    assert response.status_code == 201
    return response.json()["id"]


def test_get_shopify_status_returns_service_payload(api_client, monkeypatch):
    client_id = _create_client(api_client)

    observed: dict[str, str] = {}

    def fake_status(*, client_id: str, selected_shop_domain: str | None = None):
        observed["client_id"] = client_id
        return {
            "state": "ready",
            "message": "Shopify connection is ready.",
            "shopDomain": "example.myshopify.com",
            "shopDomains": [],
            "selectedShopDomain": selected_shop_domain,
            "hasStorefrontAccessToken": True,
            "missingScopes": [],
        }

    monkeypatch.setattr(clients_router, "get_client_shopify_connection_status", fake_status)

    response = api_client.get(f"/clients/{client_id}/shopify/status")

    assert response.status_code == 200
    assert observed["client_id"] == client_id
    assert response.json()["state"] == "ready"


def test_create_shopify_install_url_returns_url(api_client, monkeypatch):
    client_id = _create_client(api_client)

    observed: dict[str, str] = {}

    def fake_build(*, client_id: str, shop_domain: str) -> str:
        observed["client_id"] = client_id
        observed["shop_domain"] = shop_domain
        return "https://shopify-bridge.local/auth/install?shop=example.myshopify.com&client_id=test"

    monkeypatch.setattr(clients_router, "build_client_shopify_install_url", fake_build)

    response = api_client.post(
        f"/clients/{client_id}/shopify/install-url",
        json={"shopDomain": "example.myshopify.com"},
    )

    assert response.status_code == 200
    assert observed == {"client_id": client_id, "shop_domain": "example.myshopify.com"}
    assert response.json()["installUrl"].startswith("https://shopify-bridge.local/auth/install")


def test_update_shopify_installation_sets_token_and_returns_status(api_client, monkeypatch):
    client_id = _create_client(api_client)

    observed: dict[str, str] = {}

    def fake_set_token(*, client_id: str, shop_domain: str, storefront_access_token: str) -> None:
        observed["client_id"] = client_id
        observed["shop_domain"] = shop_domain
        observed["storefront_access_token"] = storefront_access_token

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

    monkeypatch.setattr(clients_router, "set_client_shopify_storefront_token", fake_set_token)
    monkeypatch.setattr(clients_router, "get_client_shopify_connection_status", fake_status)

    response = api_client.patch(
        f"/clients/{client_id}/shopify/installation",
        json={"shopDomain": "example.myshopify.com", "storefrontAccessToken": "shptka_123"},
    )

    assert response.status_code == 200
    assert observed == {
        "client_id": client_id,
        "shop_domain": "example.myshopify.com",
        "storefront_access_token": "shptka_123",
    }
    assert response.json()["state"] == "installed_missing_storefront_token"


def test_disconnect_shopify_installation_unlinks_workspace_and_returns_status(api_client, monkeypatch):
    client_id = _create_client(api_client)

    observed: dict[str, str] = {}

    def fake_disconnect(*, client_id: str, shop_domain: str) -> None:
        observed["client_id"] = client_id
        observed["shop_domain"] = shop_domain

    def fake_status(*, client_id: str, selected_shop_domain: str | None = None):
        return {
            "state": "not_connected",
            "message": "Shopify is not connected for this workspace.",
            "shopDomain": None,
            "shopDomains": [],
            "selectedShopDomain": selected_shop_domain,
            "hasStorefrontAccessToken": False,
            "missingScopes": [],
        }

    monkeypatch.setattr(clients_router, "disconnect_client_shopify_store", fake_disconnect)
    monkeypatch.setattr(clients_router, "get_client_shopify_connection_status", fake_status)

    response = api_client.request(
        method="DELETE",
        url=f"/clients/{client_id}/shopify/installation",
        json={"shopDomain": "example.myshopify.com"},
    )

    assert response.status_code == 200
    assert observed == {
        "client_id": client_id,
        "shop_domain": "example.myshopify.com",
    }
    assert response.json()["state"] == "not_connected"


def test_list_shopify_products_returns_products(api_client, monkeypatch):
    client_id = _create_client(api_client)

    observed: dict[str, object] = {}

    def fake_list(*, client_id: str, query: str | None, limit: int, shop_domain: str | None):
        observed["client_id"] = client_id
        observed["query"] = query
        observed["limit"] = limit
        observed["shop_domain"] = shop_domain
        return {
            "shopDomain": "example.myshopify.com",
            "products": [
                {
                    "productGid": "gid://shopify/Product/123",
                    "title": "Sleep Drops",
                    "handle": "sleep-drops",
                    "status": "ACTIVE",
                }
            ],
        }

    monkeypatch.setattr(clients_router, "list_client_shopify_products", fake_list)

    response = api_client.get(
        f"/clients/{client_id}/shopify/products",
        params={"query": "sleep", "limit": 10, "shopDomain": "example.myshopify.com"},
    )

    assert response.status_code == 200
    assert observed == {
        "client_id": client_id,
        "query": "sleep",
        "limit": 10,
        "shop_domain": "example.myshopify.com",
    }
    payload = response.json()
    assert payload["shopDomain"] == "example.myshopify.com"
    assert payload["products"][0]["productGid"] == "gid://shopify/Product/123"


def test_set_default_shop_updates_status(api_client, monkeypatch):
    client_id = _create_client(api_client)

    def fake_installations():
        return [
            ShopifyInstallation(
                shop_domain="one.myshopify.com",
                client_id=client_id,
                has_storefront_access_token=True,
                scopes=[],
                uninstalled_at=None,
            )
        ]

    def fake_status(*, client_id: str, selected_shop_domain: str | None = None):
        assert client_id
        return {
            "state": "ready",
            "message": "Shopify connection is ready.",
            "shopDomain": selected_shop_domain,
            "shopDomains": [],
            "selectedShopDomain": selected_shop_domain,
            "hasStorefrontAccessToken": True,
            "missingScopes": [],
        }

    monkeypatch.setattr(clients_router, "list_shopify_installations", fake_installations)
    monkeypatch.setattr(clients_router, "get_client_shopify_connection_status", fake_status)

    response = api_client.put(
        f"/clients/{client_id}/shopify/default-shop",
        json={"shopDomain": "one.myshopify.com"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "ready"
    assert body["selectedShopDomain"] == "one.myshopify.com"


def test_create_shopify_product_returns_created_payload(api_client, monkeypatch):
    client_id = _create_client(api_client)
    observed: dict[str, object] = {}

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

    def fake_create(
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
        observed["client_id"] = client_id
        observed["title"] = title
        observed["variants"] = variants
        observed["shop_domain"] = shop_domain
        return {
            "shopDomain": "example.myshopify.com",
            "productGid": "gid://shopify/Product/900",
            "title": "Sleep Drops",
            "handle": "sleep-drops",
            "status": "DRAFT",
            "variants": [
                {
                    "variantGid": "gid://shopify/ProductVariant/901",
                    "title": "Starter",
                    "priceCents": 4999,
                    "currency": "USD",
                }
            ],
        }

    monkeypatch.setattr(clients_router, "get_client_shopify_connection_status", fake_status)
    monkeypatch.setattr(clients_router, "create_client_shopify_product", fake_create)

    response = api_client.post(
        f"/clients/{client_id}/shopify/products",
        json={
            "title": "Sleep Drops",
            "status": "DRAFT",
            "variants": [{"title": "Starter", "priceCents": 4999, "currency": "USD"}],
        },
    )

    assert response.status_code == 200
    assert observed["client_id"] == client_id
    assert observed["title"] == "Sleep Drops"
    assert observed["shop_domain"] is None
    payload = response.json()
    assert payload["productGid"] == "gid://shopify/Product/900"
    assert payload["variants"][0]["variantGid"] == "gid://shopify/ProductVariant/901"


def test_create_shopify_product_requires_ready_connection(api_client, monkeypatch):
    client_id = _create_client(api_client)

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

    monkeypatch.setattr(clients_router, "get_client_shopify_connection_status", fake_status)

    response = api_client.post(
        f"/clients/{client_id}/shopify/products",
        json={
            "title": "Sleep Drops",
            "status": "DRAFT",
            "variants": [{"title": "Starter", "priceCents": 4999, "currency": "USD"}],
        },
    )

    assert response.status_code == 409
    assert "Shopify connection is not ready" in response.json()["detail"]


def test_sync_shopify_theme_brand_returns_sync_payload(api_client, monkeypatch):
    client_id = _create_client(api_client, name="Acme Workspace")
    observed: dict[str, object] = {}

    def fake_status(*, client_id: str, selected_shop_domain: str | None = None):
        observed["status_client_id"] = client_id
        observed["selected_shop_domain"] = selected_shop_domain
        return {
            "state": "ready",
            "message": "Shopify connection is ready.",
            "shopDomain": selected_shop_domain or "example.myshopify.com",
            "shopDomains": [],
            "selectedShopDomain": selected_shop_domain,
            "hasStorefrontAccessToken": True,
            "missingScopes": [],
        }

    def fake_design_system_get(self, *, org_id: str, design_system_id: str):
        observed["design_system_id"] = design_system_id
        return type(
            "FakeDesignSystem",
            (),
            {
                "id": design_system_id,
                "name": "Acme Design System",
                "client_id": client_id,
                "tokens": {"placeholder": True},
            },
        )()

    def fake_validate(tokens):
        assert tokens == {"placeholder": True}
        return {
            "dataTheme": "light",
            "fontUrls": ["https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap"],
            "cssVars": {"--color-brand": "#123456"},
            "brand": {"name": "Acme", "logoAssetPublicId": "logo-public-id"},
            "funnelDefaults": {"containerWidth": "lg"},
        }

    def fake_get_logo_asset(self, *, org_id: str, public_id: str, client_id: str | None = None):
        observed["logo_public_id"] = public_id
        observed["logo_client_id"] = client_id
        return object()

    def fake_sync_theme_brand(
        *,
        client_id: str,
        workspace_name: str,
        brand_name: str,
        logo_url: str,
        css_vars: dict[str, str],
        font_urls: list[str] | None,
        data_theme: str | None,
        theme_id: str | None,
        theme_name: str | None,
        shop_domain: str | None,
    ):
        observed["sync_client_id"] = client_id
        observed["workspace_name"] = workspace_name
        observed["brand_name"] = brand_name
        observed["logo_url"] = logo_url
        observed["css_vars"] = css_vars
        observed["font_urls"] = font_urls
        observed["data_theme"] = data_theme
        observed["theme_id"] = theme_id
        observed["theme_name"] = theme_name
        observed["shop_domain"] = shop_domain
        return {
            "shopDomain": "example.myshopify.com",
            "themeId": "gid://shopify/OnlineStoreTheme/1",
            "themeName": "Main Theme",
            "themeRole": "MAIN",
            "layoutFilename": "layout/theme.liquid",
            "cssFilename": "assets/acme-workspace-workspace-brand.css",
            "settingsFilename": "config/settings_data.json",
            "jobId": "gid://shopify/Job/1",
            "coverage": {
                "requiredSourceVars": [],
                "requiredThemeVars": [],
                "missingSourceVars": [],
                "missingThemeVars": [],
            },
            "settingsSync": {
                "settingsFilename": "config/settings_data.json",
                "expectedPaths": [],
                "updatedPaths": [],
                "missingPaths": [],
                "requiredMissingPaths": [],
            },
        }

    monkeypatch.setattr(clients_router, "get_client_shopify_connection_status", fake_status)
    monkeypatch.setattr(clients_router.DesignSystemsRepository, "get", fake_design_system_get)
    monkeypatch.setattr(clients_router, "validate_design_system_tokens", fake_validate)
    monkeypatch.setattr(clients_router.AssetsRepository, "get_by_public_id", fake_get_logo_asset)
    monkeypatch.setattr(clients_router, "sync_client_shopify_theme_brand", fake_sync_theme_brand)
    monkeypatch.setattr(clients_router.settings, "PUBLIC_ASSET_BASE_URL", "https://assets.example.com")

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/sync",
        json={
            "shopDomain": "example.myshopify.com",
            "designSystemId": "design-system-1",
            "themeName": "futrgroup2-0theme",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["shopDomain"] == "example.myshopify.com"
    assert payload["themeId"] == "gid://shopify/OnlineStoreTheme/1"
    assert payload["cssFilename"] == "assets/acme-workspace-workspace-brand.css"
    assert observed["workspace_name"] == "Acme Workspace"
    assert observed["brand_name"] == "Acme"
    assert observed["shop_domain"] == "example.myshopify.com"
    assert observed["theme_name"] == "futrgroup2-0theme"


def test_sync_shopify_theme_brand_uses_workspace_default_design_system_when_omitted(api_client, monkeypatch):
    client_id = _create_client(api_client, name="Acme Workspace")
    observed: dict[str, object] = {}

    def fake_get_client(self, *, org_id: str, client_id: str):
        assert client_id
        return type(
            "FakeClient",
            (),
            {
                "id": client_id,
                "name": "Acme Workspace",
                "design_system_id": "workspace-default-design-system",
            },
        )()

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

    def fake_design_system_get(self, *, org_id: str, design_system_id: str):
        observed["design_system_id"] = design_system_id
        return type(
            "FakeDesignSystem",
            (),
            {
                "id": design_system_id,
                "name": "Acme Default Design System",
                "client_id": client_id,
                "tokens": {"placeholder": True},
            },
        )()

    def fake_validate(tokens):
        assert tokens == {"placeholder": True}
        return {
            "dataTheme": "light",
            "fontUrls": ["https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap"],
            "cssVars": {"--color-brand": "#123456"},
            "brand": {"name": "Acme", "logoAssetPublicId": "logo-public-id"},
            "funnelDefaults": {"containerWidth": "lg"},
        }

    def fake_get_logo_asset(self, *, org_id: str, public_id: str, client_id: str | None = None):
        return object()

    def fake_sync_theme_brand(
        *,
        client_id: str,
        workspace_name: str,
        brand_name: str,
        logo_url: str,
        css_vars: dict[str, str],
        font_urls: list[str] | None,
        data_theme: str | None,
        theme_id: str | None,
        theme_name: str | None,
        shop_domain: str | None,
    ):
        observed["sync_theme_name"] = theme_name
        return {
            "shopDomain": "example.myshopify.com",
            "themeId": "gid://shopify/OnlineStoreTheme/1",
            "themeName": "futrgroup2-0theme",
            "themeRole": "MAIN",
            "layoutFilename": "layout/theme.liquid",
            "cssFilename": "assets/acme-workspace-workspace-brand.css",
            "settingsFilename": "config/settings_data.json",
            "jobId": "gid://shopify/Job/1",
            "coverage": {
                "requiredSourceVars": [],
                "requiredThemeVars": [],
                "missingSourceVars": [],
                "missingThemeVars": [],
            },
            "settingsSync": {
                "settingsFilename": "config/settings_data.json",
                "expectedPaths": [],
                "updatedPaths": [],
                "missingPaths": [],
                "requiredMissingPaths": [],
            },
        }

    monkeypatch.setattr(clients_router.ClientsRepository, "get", fake_get_client)
    monkeypatch.setattr(clients_router, "get_client_shopify_connection_status", fake_status)
    monkeypatch.setattr(clients_router.DesignSystemsRepository, "get", fake_design_system_get)
    monkeypatch.setattr(clients_router, "validate_design_system_tokens", fake_validate)
    monkeypatch.setattr(clients_router.AssetsRepository, "get_by_public_id", fake_get_logo_asset)
    monkeypatch.setattr(clients_router, "sync_client_shopify_theme_brand", fake_sync_theme_brand)
    monkeypatch.setattr(clients_router.settings, "PUBLIC_ASSET_BASE_URL", "https://assets.example.com")

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/sync",
        json={"shopDomain": "example.myshopify.com", "themeName": "futrgroup2-0theme"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["designSystemId"] == "workspace-default-design-system"
    assert observed["design_system_id"] == "workspace-default-design-system"
    assert observed["sync_theme_name"] == "futrgroup2-0theme"


def test_sync_shopify_theme_brand_requires_ready_connection(api_client, monkeypatch):
    client_id = _create_client(api_client)

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

    monkeypatch.setattr(clients_router, "get_client_shopify_connection_status", fake_status)

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/sync",
        json={"designSystemId": "design-system-1", "themeName": "futrgroup2-0theme"},
    )

    assert response.status_code == 409
    assert "Shopify connection is not ready" in response.json()["detail"]


def test_audit_shopify_theme_brand_returns_audit_payload(api_client, monkeypatch):
    client_id = _create_client(api_client, name="Acme Workspace")
    observed: dict[str, object] = {}

    def fake_status(*, client_id: str, selected_shop_domain: str | None = None):
        observed["status_client_id"] = client_id
        observed["selected_shop_domain"] = selected_shop_domain
        return {
            "state": "ready",
            "message": "Shopify connection is ready.",
            "shopDomain": selected_shop_domain or "example.myshopify.com",
            "shopDomains": [],
            "selectedShopDomain": selected_shop_domain,
            "hasStorefrontAccessToken": True,
            "missingScopes": [],
        }

    def fake_design_system_get(self, *, org_id: str, design_system_id: str):
        observed["design_system_id"] = design_system_id
        return type(
            "FakeDesignSystem",
            (),
            {
                "id": design_system_id,
                "name": "Acme Design System",
                "client_id": client_id,
                "tokens": {"placeholder": True},
            },
        )()

    def fake_validate(tokens):
        assert tokens == {"placeholder": True}
        return {
            "dataTheme": "light",
            "cssVars": {"--color-brand": "#123456"},
            "fontUrls": [],
            "brand": {"name": "Acme", "logoAssetPublicId": "logo-public-id"},
            "funnelDefaults": {"containerWidth": "lg"},
        }

    def fake_audit_theme_brand(
        *,
        client_id: str,
        workspace_name: str,
        css_vars: dict[str, str],
        data_theme: str | None,
        theme_id: str | None,
        theme_name: str | None,
        shop_domain: str | None,
    ):
        observed["audit_client_id"] = client_id
        observed["workspace_name"] = workspace_name
        observed["css_vars"] = css_vars
        observed["data_theme"] = data_theme
        observed["theme_id"] = theme_id
        observed["theme_name"] = theme_name
        observed["shop_domain"] = shop_domain
        return {
            "shopDomain": "example.myshopify.com",
            "themeId": "gid://shopify/OnlineStoreTheme/1",
            "themeName": "futrgroup2-0theme",
            "themeRole": "MAIN",
            "layoutFilename": "layout/theme.liquid",
            "cssFilename": "assets/acme-workspace-workspace-brand.css",
            "settingsFilename": "config/settings_data.json",
            "hasManagedMarkerBlock": True,
            "layoutIncludesManagedCssAsset": True,
            "managedCssAssetExists": True,
            "coverage": {
                "requiredSourceVars": [],
                "requiredThemeVars": [],
                "missingSourceVars": [],
                "missingThemeVars": [],
            },
            "settingsAudit": {
                "settingsFilename": "config/settings_data.json",
                "expectedPaths": [],
                "syncedPaths": [],
                "mismatchedPaths": [],
                "missingPaths": [],
                "requiredMissingPaths": [],
                "requiredMismatchedPaths": [],
            },
            "isReady": True,
        }

    monkeypatch.setattr(clients_router, "get_client_shopify_connection_status", fake_status)
    monkeypatch.setattr(clients_router.DesignSystemsRepository, "get", fake_design_system_get)
    monkeypatch.setattr(clients_router, "validate_design_system_tokens", fake_validate)
    monkeypatch.setattr(clients_router, "audit_client_shopify_theme_brand", fake_audit_theme_brand)

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/audit",
        json={
            "shopDomain": "example.myshopify.com",
            "designSystemId": "design-system-1",
            "themeName": "futrgroup2-0theme",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["shopDomain"] == "example.myshopify.com"
    assert payload["themeName"] == "futrgroup2-0theme"
    assert payload["isReady"] is True
    assert observed["workspace_name"] == "Acme Workspace"
    assert observed["data_theme"] == "light"
    assert observed["shop_domain"] == "example.myshopify.com"


def test_audit_shopify_theme_brand_requires_ready_connection(api_client, monkeypatch):
    client_id = _create_client(api_client)

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

    monkeypatch.setattr(clients_router, "get_client_shopify_connection_status", fake_status)

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/audit",
        json={"designSystemId": "design-system-1", "themeName": "futrgroup2-0theme"},
    )

    assert response.status_code == 409
    assert "Shopify connection is not ready" in response.json()["detail"]


def test_shopify_routes_require_existing_client(api_client):
    missing_client_id = "00000000-0000-0000-0000-00000000abcd"

    status_response = api_client.get(f"/clients/{missing_client_id}/shopify/status")
    install_response = api_client.post(
        f"/clients/{missing_client_id}/shopify/install-url",
        json={"shopDomain": "example.myshopify.com"},
    )
    patch_response = api_client.patch(
        f"/clients/{missing_client_id}/shopify/installation",
        json={"shopDomain": "example.myshopify.com", "storefrontAccessToken": "token"},
    )
    disconnect_response = api_client.request(
        method="DELETE",
        url=f"/clients/{missing_client_id}/shopify/installation",
        json={"shopDomain": "example.myshopify.com"},
    )
    default_shop_response = api_client.put(
        f"/clients/{missing_client_id}/shopify/default-shop",
        json={"shopDomain": "example.myshopify.com"},
    )
    create_product_response = api_client.post(
        f"/clients/{missing_client_id}/shopify/products",
        json={
            "title": "Sleep Drops",
            "status": "DRAFT",
            "variants": [{"title": "Starter", "priceCents": 4999, "currency": "USD"}],
        },
    )
    sync_theme_brand_response = api_client.post(
        f"/clients/{missing_client_id}/shopify/theme/brand/sync",
        json={"designSystemId": "design-system-1", "themeName": "futrgroup2-0theme"},
    )
    audit_theme_brand_response = api_client.post(
        f"/clients/{missing_client_id}/shopify/theme/brand/audit",
        json={"designSystemId": "design-system-1", "themeName": "futrgroup2-0theme"},
    )

    assert status_response.status_code == 404
    assert install_response.status_code == 404
    assert patch_response.status_code == 404
    assert disconnect_response.status_code == 404
    assert default_shop_response.status_code == 404
    assert create_product_response.status_code == 404
    assert sync_theme_brand_response.status_code == 404
    assert audit_theme_brand_response.status_code == 404
