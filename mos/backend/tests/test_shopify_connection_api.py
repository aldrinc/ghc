from uuid import UUID

from app.routers import clients as clients_router
from app.services.shopify_connection import ShopifyInstallation


def _create_client(api_client, *, name: str = "Shopify Workspace") -> str:
    response = api_client.post("/clients", json={"name": name, "industry": "Retail"})
    assert response.status_code == 201
    return response.json()["id"]


def test_sanitize_theme_component_text_value_removes_unsupported_characters():
    raw_value = '  "Sleep <better>\n tonight\'s pick"  '
    assert (
        clients_router._sanitize_theme_component_text_value(raw_value)
        == "Sleep better tonight’s pick"
    )


def test_sanitize_theme_component_text_value_strips_inline_markup_tags():
    raw_value = "Boost <strong>energy</strong> and <em>focus</em> daily"
    assert (
        clients_router._sanitize_theme_component_text_value(raw_value)
        == "Boost energy and focus daily"
    )


def test_build_theme_sync_image_slot_text_hints_uses_adjacent_feature_copy():
    feature_image_path = (
        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_47f4ep.settings.image"
    )
    hints = clients_router._build_theme_sync_image_slot_text_hints(
        image_slots=[
            {"path": feature_image_path},
            {"path": "templates/index.json.sections.hero.settings.image"},
        ],
        text_slots=[
            {
                "path": (
                    "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_47f4ep."
                    "settings.title"
                ),
                "currentValue": "We deliver worldwide",
            },
            {
                "path": (
                    "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_47f4ep."
                    "settings.text"
                ),
                "currentValue": "Fast <strong>shipping</strong> for all orders",
            },
            {
                "path": "templates/index.json.sections.hero.settings.heading",
                "currentValue": "Hero heading",
            },
        ],
    )

    assert hints == {
        feature_image_path: "We deliver worldwide Fast shipping for all orders"
    }


def test_normalize_asset_public_id_handles_uuid_and_string():
    uuid_value = UUID("11111111-1111-1111-1111-111111111111")
    assert clients_router._normalize_asset_public_id(uuid_value) == "11111111-1111-1111-1111-111111111111"
    assert clients_router._normalize_asset_public_id("  abc-123  ") == "abc-123"
    assert clients_router._normalize_asset_public_id("") is None
    assert clients_router._normalize_asset_public_id(None) is None


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
        json={
            "shopDomain": "example.myshopify.com",
            "storefrontAccessToken": "shptka_123",
        },
    )

    assert response.status_code == 200
    assert observed == {
        "client_id": client_id,
        "shop_domain": "example.myshopify.com",
        "storefront_access_token": "shptka_123",
    }
    assert response.json()["state"] == "installed_missing_storefront_token"


def test_disconnect_shopify_installation_unlinks_workspace_and_returns_status(
    api_client, monkeypatch
):
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


def test_enqueue_shopify_theme_brand_sync_job_returns_accepted(api_client, monkeypatch):
    client_id = _create_client(api_client, name="Acme Workspace")
    observed: dict[str, object] = {}

    def fake_run_sync_job(job_id: str):
        observed["job_id"] = job_id

    monkeypatch.setattr(
        clients_router,
        "_run_client_shopify_theme_brand_sync_job",
        fake_run_sync_job,
    )

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/sync-async",
        json={
            "shopDomain": "example.myshopify.com",
            "designSystemId": "design-system-1",
            "themeName": "futrgroup2-0theme",
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert isinstance(payload["jobId"], str) and payload["jobId"]
    assert payload["status"] in {"queued", "running", "succeeded", "failed"}
    assert payload["statusPath"] == (
        f"/clients/{client_id}/shopify/theme/brand/sync-jobs/{payload['jobId']}"
    )
    assert observed["job_id"] == payload["jobId"]

    status_response = api_client.get(
        f"/clients/{client_id}/shopify/theme/brand/sync-jobs/{payload['jobId']}"
    )
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["jobId"] == payload["jobId"]
    assert status_payload["status"] in {"queued", "running", "succeeded", "failed"}


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
            "fontUrls": [
                "https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap"
            ],
            "cssVars": {"--color-brand": "#123456"},
            "brand": {"name": "Acme", "logoAssetPublicId": "logo-public-id"},
            "funnelDefaults": {"containerWidth": "lg"},
        }

    def fake_get_logo_asset(self, *, org_id: str, public_id: str, client_id: str | None = None):
        observed["logo_public_id"] = public_id
        observed["logo_client_id"] = client_id
        return object()

    def fake_list_template_slots(
        *,
        client_id: str,
        theme_id: str | None,
        theme_name: str | None,
        shop_domain: str | None,
    ):
        return {"imageSlots": [], "textSlots": []}

    def fake_sync_theme_brand(
        *,
        client_id: str,
        workspace_name: str,
        brand_name: str,
        logo_url: str,
        css_vars: dict[str, str],
        font_urls: list[str] | None,
        data_theme: str | None,
        component_image_urls: dict[str, str] | None,
        component_text_values: dict[str, str] | None,
        auto_component_image_urls: list[str] | None,
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
        observed["component_image_urls"] = component_image_urls
        observed["component_text_values"] = component_text_values
        observed["auto_component_image_urls"] = auto_component_image_urls
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
    monkeypatch.setattr(
        clients_router,
        "list_client_shopify_theme_template_slots",
        fake_list_template_slots,
    )
    monkeypatch.setattr(clients_router, "sync_client_shopify_theme_brand", fake_sync_theme_brand)
    monkeypatch.setattr(
        clients_router.settings, "PUBLIC_ASSET_BASE_URL", "https://assets.example.com"
    )

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
    assert observed["component_image_urls"] == {}
    assert observed["component_text_values"] == {}
    assert observed["auto_component_image_urls"] == []


def test_sync_shopify_theme_brand_resolves_component_image_asset_map(api_client, monkeypatch):
    client_id = _create_client(api_client, name="Acme Workspace")
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

    def fake_design_system_get(self, *, org_id: str, design_system_id: str):
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
            "fontUrls": [
                "https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap"
            ],
            "cssVars": {"--color-brand": "#123456"},
            "brand": {"name": "Acme", "logoAssetPublicId": "logo-public-id"},
            "funnelDefaults": {"containerWidth": "lg"},
        }

    def fake_get_asset(self, *, org_id: str, public_id: str, client_id: str | None = None):
        observed.setdefault("asset_public_ids", []).append(public_id)
        if public_id in {
            "logo-public-id",
            "hero-image-public-id",
            "footer-image-public-id",
        }:
            return object()
        return None

    def fake_sync_theme_brand(
        *,
        client_id: str,
        workspace_name: str,
        brand_name: str,
        logo_url: str,
        css_vars: dict[str, str],
        font_urls: list[str] | None,
        data_theme: str | None,
        component_image_urls: dict[str, str] | None,
        component_text_values: dict[str, str] | None,
        auto_component_image_urls: list[str] | None,
        theme_id: str | None,
        theme_name: str | None,
        shop_domain: str | None,
    ):
        observed["component_image_urls"] = component_image_urls
        observed["component_text_values"] = component_text_values
        observed["auto_component_image_urls"] = auto_component_image_urls
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
    monkeypatch.setattr(clients_router.AssetsRepository, "get_by_public_id", fake_get_asset)
    monkeypatch.setattr(clients_router, "sync_client_shopify_theme_brand", fake_sync_theme_brand)
    monkeypatch.setattr(
        clients_router.settings, "PUBLIC_ASSET_BASE_URL", "https://assets.example.com"
    )

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/sync",
        json={
            "shopDomain": "example.myshopify.com",
            "designSystemId": "design-system-1",
            "themeName": "futrgroup2-0theme",
            "componentImageAssetMap": {
                "templates/index.json.sections.hero.settings.image": "hero-image-public-id",
                "sections/footer-group.json.sections.ss_footer_4_abc123.settings.image": "footer-image-public-id",
            },
        },
    )

    assert response.status_code == 200
    assert observed["asset_public_ids"] == [
        "logo-public-id",
        "hero-image-public-id",
        "footer-image-public-id",
    ]
    assert observed["component_image_urls"] == {
        "templates/index.json.sections.hero.settings.image": "https://assets.example.com/public/assets/hero-image-public-id",
        "sections/footer-group.json.sections.ss_footer_4_abc123.settings.image": (
            "https://assets.example.com/public/assets/footer-image-public-id"
        ),
    }
    assert observed["component_text_values"] == {}
    assert observed["auto_component_image_urls"] == []


def test_sync_shopify_theme_brand_generates_ai_images_without_product_id(
    api_client, monkeypatch
):
    client_id = _create_client(api_client, name="Acme Workspace")
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

    def fake_design_system_get(self, *, org_id: str, design_system_id: str):
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
            "fontUrls": [
                "https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap"
            ],
            "cssVars": {"--color-brand": "#123456"},
            "brand": {"name": "Acme", "logoAssetPublicId": "logo-public-id"},
            "funnelDefaults": {"containerWidth": "lg"},
        }

    def fake_get_asset(self, *, org_id: str, public_id: str, client_id: str | None = None):
        if public_id == "logo-public-id":
            return type("FakeAsset", (), {"public_id": "logo-public-id"})()
        return None

    def fake_create_funnel_image_asset(
        *,
        session,
        org_id: str,
        client_id: str,
        prompt: str,
        aspect_ratio: str | None = None,
        usage_context: dict[str, object] | None = None,
        reference_image_bytes=None,
        reference_image_mime_type=None,
        reference_asset_public_id: str | None = None,
        reference_asset_id: str | None = None,
        funnel_id: str | None = None,
        product_id: str | None = None,
        tags: list[str] | None = None,
    ):
        observed.setdefault("generated_product_ids", []).append(product_id)
        slot_path = usage_context.get("slotPath") if isinstance(usage_context, dict) else None
        if slot_path == "templates/index.json.sections.hero.settings.image":
            public_id = UUID("11111111-1111-1111-1111-111111111111")
        else:
            public_id = "generated-image-gallery"
        return type(
            "FakeGeneratedAsset",
            (),
            {
                "public_id": public_id,
                "width": 1600 if aspect_ratio == "16:9" else 1000,
                "height": 900 if aspect_ratio == "16:9" else 1000,
                "alt": None,
                "tags": ["shopify_theme_sync"],
                "ai_metadata": {"source": "ai"},
            },
        )()

    def fake_list_template_slots(
        *,
        client_id: str,
        theme_id: str | None,
        theme_name: str | None,
        shop_domain: str | None,
    ):
        return {
            "imageSlots": [
                {
                    "path": "templates/index.json.sections.hero.settings.image",
                    "role": "hero",
                    "recommendedAspect": "16:9",
                    "currentValue": None,
                },
                {
                    "path": "templates/product.json.sections.gallery.settings.image",
                    "role": "gallery",
                    "recommendedAspect": "1:1",
                    "currentValue": None,
                },
            ],
            "textSlots": [],
        }

    def fail_planner(**kwargs):
        raise AssertionError("Planner should not run when productId is omitted.")

    def fake_sync_theme_brand(
        *,
        client_id: str,
        workspace_name: str,
        brand_name: str,
        logo_url: str,
        css_vars: dict[str, str],
        font_urls: list[str] | None,
        data_theme: str | None,
        component_image_urls: dict[str, str] | None,
        component_text_values: dict[str, str] | None,
        auto_component_image_urls: list[str] | None,
        theme_id: str | None,
        theme_name: str | None,
        shop_domain: str | None,
    ):
        observed["component_image_urls"] = component_image_urls
        observed["component_text_values"] = component_text_values
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
    monkeypatch.setattr(clients_router.AssetsRepository, "get_by_public_id", fake_get_asset)
    monkeypatch.setattr(clients_router, "create_funnel_image_asset", fake_create_funnel_image_asset)
    monkeypatch.setattr(
        clients_router,
        "list_client_shopify_theme_template_slots",
        fake_list_template_slots,
    )
    monkeypatch.setattr(clients_router, "plan_shopify_theme_component_content", fail_planner)
    monkeypatch.setattr(clients_router, "sync_client_shopify_theme_brand", fake_sync_theme_brand)
    monkeypatch.setattr(
        clients_router.settings, "PUBLIC_ASSET_BASE_URL", "https://assets.example.com"
    )

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/sync",
        json={
            "shopDomain": "example.myshopify.com",
            "designSystemId": "design-system-1",
            "themeName": "futrgroup2-0theme",
        },
    )

    assert response.status_code == 200
    assert observed["generated_product_ids"] == [None, None]
    assert observed["component_image_urls"] == {
        "templates/index.json.sections.hero.settings.image": (
            "https://assets.example.com/public/assets/11111111-1111-1111-1111-111111111111"
        ),
        "templates/product.json.sections.gallery.settings.image": (
            "https://assets.example.com/public/assets/generated-image-gallery"
        ),
    }
    assert observed["component_text_values"] == {}


def test_sync_shopify_theme_brand_returns_429_when_ai_generation_is_rate_limited_without_product_id(
    api_client, monkeypatch
):
    client_id = _create_client(api_client, name="Acme Workspace")

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
            "fontUrls": [
                "https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap"
            ],
            "cssVars": {"--color-brand": "#123456"},
            "brand": {"name": "Acme", "logoAssetPublicId": "logo-public-id"},
            "funnelDefaults": {"containerWidth": "lg"},
        }

    def fake_get_asset(self, *, org_id: str, public_id: str, client_id: str | None = None):
        if public_id == "logo-public-id":
            return type("FakeAsset", (), {"public_id": "logo-public-id"})()
        return None

    def fake_create_funnel_image_asset(
        *,
        session,
        org_id: str,
        client_id: str,
        prompt: str,
        aspect_ratio: str | None = None,
        usage_context: dict[str, object] | None = None,
        reference_image_bytes=None,
        reference_image_mime_type=None,
        reference_asset_public_id: str | None = None,
        reference_asset_id: str | None = None,
        funnel_id: str | None = None,
        product_id: str | None = None,
        tags: list[str] | None = None,
    ):
        raise RuntimeError(
            "Gemini image request failed (status=429): "
            '{"error":{"status":"RESOURCE_EXHAUSTED","message":"You exceeded your current quota."}}'
        )

    def fake_create_funnel_unsplash_asset(
        *,
        session,
        org_id: str,
        client_id: str,
        query: str,
        usage_context: dict[str, object] | None = None,
        funnel_id: str | None = None,
        product_id: str | None = None,
        tags: list[str] | None = None,
    ):
        raise RuntimeError("UNSPLASH_ACCESS_KEY not configured")

    def fake_list_template_slots(
        *,
        client_id: str,
        theme_id: str | None,
        theme_name: str | None,
        shop_domain: str | None,
    ):
        return {
            "imageSlots": [
                {
                    "path": "templates/index.json.sections.hero.settings.image",
                    "role": "hero",
                    "recommendedAspect": "16:9",
                    "currentValue": None,
                },
            ],
            "textSlots": [],
        }

    monkeypatch.setattr(clients_router, "get_client_shopify_connection_status", fake_status)
    monkeypatch.setattr(clients_router.DesignSystemsRepository, "get", fake_design_system_get)
    monkeypatch.setattr(clients_router, "validate_design_system_tokens", fake_validate)
    monkeypatch.setattr(clients_router.AssetsRepository, "get_by_public_id", fake_get_asset)
    monkeypatch.setattr(clients_router, "create_funnel_image_asset", fake_create_funnel_image_asset)
    monkeypatch.setattr(clients_router, "create_funnel_unsplash_asset", fake_create_funnel_unsplash_asset)
    monkeypatch.setattr(
        clients_router,
        "list_client_shopify_theme_template_slots",
        fake_list_template_slots,
    )
    monkeypatch.setattr(
        clients_router.settings, "PUBLIC_ASSET_BASE_URL", "https://assets.example.com"
    )

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/sync",
        json={
            "shopDomain": "example.myshopify.com",
            "designSystemId": "design-system-1",
            "themeName": "futrgroup2-0theme",
        },
    )

    assert response.status_code == 429
    assert "productId was not provided for fallback product images" in response.json()["detail"]


def test_sync_shopify_theme_brand_resolves_product_images_for_auto_component_sync(
    api_client, monkeypatch
):
    client_id = _create_client(api_client, name="Acme Workspace")
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

    def fake_design_system_get(self, *, org_id: str, design_system_id: str):
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
            "fontUrls": [
                "https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap"
            ],
            "cssVars": {"--color-brand": "#123456"},
            "brand": {"name": "Acme", "logoAssetPublicId": "logo-public-id"},
            "funnelDefaults": {"containerWidth": "lg"},
        }

    def fake_get_asset(self, *, org_id: str, public_id: str, client_id: str | None = None):
        if public_id in {"logo-public-id"}:
            return type("FakeAsset", (), {"public_id": public_id})()
        return None

    def fake_get_product(self, *, org_id: str, product_id: str):
        observed["product_id"] = product_id
        return type(
            "FakeProduct",
            (),
            {
                "id": product_id,
                "client_id": client_id,
            },
        )()

    def fake_create_funnel_image_asset(
        *,
        session,
        org_id: str,
        client_id: str,
        prompt: str,
        aspect_ratio: str | None = None,
        usage_context: dict[str, object] | None = None,
        reference_image_bytes=None,
        reference_image_mime_type=None,
        reference_asset_public_id: str | None = None,
        reference_asset_id: str | None = None,
        funnel_id: str | None = None,
        product_id: str | None = None,
        tags: list[str] | None = None,
    ):
        observed.setdefault("generated_aspect_ratios", []).append(aspect_ratio)
        observed.setdefault("generated_prompts", []).append(prompt)
        if aspect_ratio == "16:9":
            generated_public_id = "generated-image-hero"
            width, height = 1600, 900
        elif aspect_ratio == "1:1":
            generated_public_id = "generated-image-gallery"
            width, height = 1000, 1000
        else:
            generated_public_id = "generated-image-generic"
            width, height = 1200, 900
        return type(
            "FakeGeneratedAsset",
            (),
            {
                "public_id": generated_public_id,
                "width": width,
                "height": height,
                "alt": None,
                "tags": ["shopify_theme_sync"],
                "ai_metadata": {"source": "ai"},
            },
        )()

    def fake_list_template_slots(
        *,
        client_id: str,
        theme_id: str | None,
        theme_name: str | None,
        shop_domain: str | None,
    ):
        observed["slot_theme_name"] = theme_name
        return {
            "imageSlots": [
                {
                    "path": "templates/index.json.sections.hero.settings.image",
                    "role": "hero",
                    "recommendedAspect": "16:9",
                    "currentValue": None,
                },
                {
                    "path": "templates/product.json.sections.gallery.settings.image",
                    "role": "gallery",
                    "recommendedAspect": "1:1",
                    "currentValue": None,
                },
            ],
            "textSlots": [
                {
                    "path": "templates/index.json.sections.hero.settings.heading",
                    "role": "headline",
                    "maxLength": 80,
                    "currentValue": "Old headline",
                }
            ],
        }

    def fake_list_offers(self, *, product_id: str):
        observed["offers_product_id"] = product_id
        return []

    def fake_plan_component_content(
        *,
        product,
        offers,
        product_image_assets,
        image_slots,
        text_slots,
    ):
        observed["planner_image_slot_paths"] = [slot["path"] for slot in image_slots]
        observed["planner_text_slot_paths"] = [slot["path"] for slot in text_slots]
        observed["planner_asset_public_ids"] = [
            getattr(asset, "public_id", None) for asset in product_image_assets
        ]
        return {
            "componentImageAssetMap": {
                "templates/index.json.sections.hero.settings.image": "generated-image-hero",
                "templates/product.json.sections.gallery.settings.image": "generated-image-gallery",
            },
            "componentTextValues": {
                "templates/index.json.sections.hero.settings.heading": (
                    '  "Sleep <better>\n tonight\'s pick"  '
                )
            },
        }

    def fake_sync_theme_brand(
        *,
        client_id: str,
        workspace_name: str,
        brand_name: str,
        logo_url: str,
        css_vars: dict[str, str],
        font_urls: list[str] | None,
        data_theme: str | None,
        component_image_urls: dict[str, str] | None,
        component_text_values: dict[str, str] | None,
        auto_component_image_urls: list[str] | None,
        theme_id: str | None,
        theme_name: str | None,
        shop_domain: str | None,
    ):
        observed["component_image_urls"] = component_image_urls
        observed["component_text_values"] = component_text_values
        observed["auto_component_image_urls"] = auto_component_image_urls
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
    monkeypatch.setattr(clients_router.AssetsRepository, "get_by_public_id", fake_get_asset)
    monkeypatch.setattr(clients_router.ProductsRepository, "get", fake_get_product)
    monkeypatch.setattr(clients_router, "create_funnel_image_asset", fake_create_funnel_image_asset)
    monkeypatch.setattr(
        clients_router,
        "list_client_shopify_theme_template_slots",
        fake_list_template_slots,
    )
    monkeypatch.setattr(clients_router.ProductOffersRepository, "list_by_product", fake_list_offers)
    monkeypatch.setattr(
        clients_router,
        "plan_shopify_theme_component_content",
        fake_plan_component_content,
    )
    monkeypatch.setattr(clients_router, "sync_client_shopify_theme_brand", fake_sync_theme_brand)
    monkeypatch.setattr(
        clients_router.settings, "PUBLIC_ASSET_BASE_URL", "https://assets.example.com"
    )

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/sync",
        json={
            "shopDomain": "example.myshopify.com",
            "designSystemId": "design-system-1",
            "productId": "product-123",
            "themeName": "futrgroup2-0theme",
        },
    )

    assert response.status_code == 200
    assert observed["product_id"] == "product-123"
    assert observed["slot_theme_name"] == "futrgroup2-0theme"
    assert observed["offers_product_id"] == "product-123"
    assert set(observed["planner_asset_public_ids"]) == {
        "generated-image-hero",
        "generated-image-gallery",
    }
    assert sorted(observed["generated_aspect_ratios"]) == ["1:1", "16:9"]
    assert observed["planner_image_slot_paths"] == [
        "templates/index.json.sections.hero.settings.image",
        "templates/product.json.sections.gallery.settings.image",
    ]
    assert observed["planner_text_slot_paths"] == [
        "templates/index.json.sections.hero.settings.heading"
    ]
    assert observed["component_image_urls"] == {
        "templates/index.json.sections.hero.settings.image": (
            "https://assets.example.com/public/assets/generated-image-hero"
        ),
        "templates/product.json.sections.gallery.settings.image": (
            "https://assets.example.com/public/assets/generated-image-gallery"
        ),
    }
    assert observed["component_text_values"] == {
        "templates/index.json.sections.hero.settings.heading": ("Sleep better tonight’s pick")
    }
    assert observed["auto_component_image_urls"] == []


def test_sync_shopify_theme_brand_uses_existing_product_images_when_ai_is_rate_limited(
    api_client, monkeypatch
):
    client_id = _create_client(api_client, name="Acme Workspace")
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

    def fake_design_system_get(self, *, org_id: str, design_system_id: str):
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
            "fontUrls": [
                "https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap"
            ],
            "cssVars": {"--color-brand": "#123456"},
            "brand": {"name": "Acme", "logoAssetPublicId": "logo-public-id"},
            "funnelDefaults": {"containerWidth": "lg"},
        }

    def fake_get_asset(self, *, org_id: str, public_id: str, client_id: str | None = None):
        if public_id in {"logo-public-id"}:
            return type("FakeAsset", (), {"public_id": public_id})()
        return None

    def fake_list_assets(
        self,
        org_id: str,
        client_id: str | None = None,
        campaign_id: str | None = None,
        experiment_id: str | None = None,
        product_id: str | None = None,
        funnel_id: str | None = None,
        asset_kind: str | None = None,
        tags: list[str] | None = None,
        statuses: list[object] | None = None,
    ):
        assert product_id == "product-123"
        assert asset_kind == "image"
        return [
            type(
                "FakeExistingAsset",
                (),
                {
                    "public_id": "existing-image-1",
                    "width": 1600,
                    "height": 900,
                    "alt": None,
                    "tags": ["product"],
                    "ai_metadata": {"source": "upload"},
                },
            )(),
            type(
                "FakeExistingAsset",
                (),
                {
                    "public_id": "existing-image-2",
                    "width": 1000,
                    "height": 1000,
                    "alt": None,
                    "tags": ["product"],
                    "ai_metadata": {"source": "upload"},
                },
            )(),
        ]

    def fake_get_product(self, *, org_id: str, product_id: str):
        return type(
            "FakeProduct",
            (),
            {
                "id": product_id,
                "client_id": client_id,
            },
        )()

    def fake_create_funnel_image_asset(
        *,
        session,
        org_id: str,
        client_id: str,
        prompt: str,
        aspect_ratio: str | None = None,
        usage_context: dict[str, object] | None = None,
        reference_image_bytes=None,
        reference_image_mime_type=None,
        reference_asset_public_id: str | None = None,
        reference_asset_id: str | None = None,
        funnel_id: str | None = None,
        product_id: str | None = None,
        tags: list[str] | None = None,
    ):
        observed.setdefault("attempted_aspects", []).append(aspect_ratio)
        raise RuntimeError(
            "Gemini image request failed (status=429): "
            '{"error":{"status":"RESOURCE_EXHAUSTED","message":"You exceeded your current quota."}}'
        )

    def fake_create_funnel_unsplash_asset(
        *,
        session,
        org_id: str,
        client_id: str,
        query: str,
        usage_context: dict[str, object] | None = None,
        funnel_id: str | None = None,
        product_id: str | None = None,
        tags: list[str] | None = None,
    ):
        raise RuntimeError("UNSPLASH_ACCESS_KEY not configured")

    def fake_list_template_slots(
        *,
        client_id: str,
        theme_id: str | None,
        theme_name: str | None,
        shop_domain: str | None,
    ):
        return {
            "imageSlots": [
                {
                    "path": "templates/index.json.sections.hero.settings.image",
                    "role": "hero",
                    "recommendedAspect": "16:9",
                    "currentValue": None,
                },
                {
                    "path": "templates/product.json.sections.gallery.settings.image",
                    "role": "gallery",
                    "recommendedAspect": "1:1",
                    "currentValue": None,
                },
            ],
            "textSlots": [],
        }

    def fake_list_offers(self, *, product_id: str):
        return []

    def fake_plan_component_content(
        *,
        product,
        offers,
        product_image_assets,
        image_slots,
        text_slots,
    ):
        observed["planner_asset_public_ids"] = [
            getattr(asset, "public_id", None) for asset in product_image_assets
        ]
        return {
            "componentImageAssetMap": {
                "templates/index.json.sections.hero.settings.image": "existing-image-1",
                "templates/product.json.sections.gallery.settings.image": "existing-image-2",
            },
            "componentTextValues": {},
        }

    def fake_sync_theme_brand(
        *,
        client_id: str,
        workspace_name: str,
        brand_name: str,
        logo_url: str,
        css_vars: dict[str, str],
        font_urls: list[str] | None,
        data_theme: str | None,
        component_image_urls: dict[str, str] | None,
        component_text_values: dict[str, str] | None,
        auto_component_image_urls: list[str] | None,
        theme_id: str | None,
        theme_name: str | None,
        shop_domain: str | None,
    ):
        observed["component_image_urls"] = component_image_urls
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
    monkeypatch.setattr(clients_router.AssetsRepository, "get_by_public_id", fake_get_asset)
    monkeypatch.setattr(clients_router.AssetsRepository, "list", fake_list_assets)
    monkeypatch.setattr(clients_router.ProductsRepository, "get", fake_get_product)
    monkeypatch.setattr(clients_router, "create_funnel_image_asset", fake_create_funnel_image_asset)
    monkeypatch.setattr(clients_router, "create_funnel_unsplash_asset", fake_create_funnel_unsplash_asset)
    monkeypatch.setattr(
        clients_router,
        "list_client_shopify_theme_template_slots",
        fake_list_template_slots,
    )
    monkeypatch.setattr(clients_router.ProductOffersRepository, "list_by_product", fake_list_offers)
    monkeypatch.setattr(
        clients_router,
        "plan_shopify_theme_component_content",
        fake_plan_component_content,
    )
    monkeypatch.setattr(clients_router, "sync_client_shopify_theme_brand", fake_sync_theme_brand)
    monkeypatch.setattr(
        clients_router.settings, "PUBLIC_ASSET_BASE_URL", "https://assets.example.com"
    )

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/sync",
        json={
            "shopDomain": "example.myshopify.com",
            "designSystemId": "design-system-1",
            "productId": "product-123",
            "themeName": "futrgroup2-0theme",
        },
    )

    assert response.status_code == 200
    assert observed["planner_asset_public_ids"] == ["existing-image-1", "existing-image-2"]
    assert observed["component_image_urls"] == {
        "templates/index.json.sections.hero.settings.image": (
            "https://assets.example.com/public/assets/existing-image-1"
        ),
        "templates/product.json.sections.gallery.settings.image": (
            "https://assets.example.com/public/assets/existing-image-2"
        ),
    }
    assert sorted(observed["attempted_aspects"]) == ["1:1", "16:9"]


def test_sync_shopify_theme_brand_feature_slots_keep_their_generated_assets(
    api_client, monkeypatch
):
    client_id = _create_client(api_client, name="Acme Workspace")
    observed: dict[str, object] = {}
    feature_slot_one = (
        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_47f4ep.settings.image"
    )
    feature_slot_two = (
        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_4LDkHp.settings.image"
    )
    feature_slot_three = (
        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_HnJEzN.settings.image"
    )
    feature_slot_four = (
        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_RCFhqV.settings.image"
    )
    feature_slots = [
        feature_slot_one,
        feature_slot_two,
        feature_slot_three,
        feature_slot_four,
    ]
    hero_slot = "templates/index.json.sections.hero.settings.image"
    generated_public_id_by_slot = {
        feature_slot_one: "generated-feature-1",
        feature_slot_two: "generated-feature-2",
        feature_slot_three: "generated-feature-3",
        feature_slot_four: "generated-feature-4",
        hero_slot: "generated-hero",
    }

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
            "fontUrls": [
                "https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap"
            ],
            "cssVars": {"--color-brand": "#123456"},
            "brand": {"name": "Acme", "logoAssetPublicId": "logo-public-id"},
            "funnelDefaults": {"containerWidth": "lg"},
        }

    def fake_get_asset(self, *, org_id: str, public_id: str, client_id: str | None = None):
        if public_id == "logo-public-id":
            return type("FakeAsset", (), {"public_id": public_id})()
        return None

    def fake_list_assets(
        self,
        org_id: str,
        client_id: str | None = None,
        campaign_id: str | None = None,
        experiment_id: str | None = None,
        product_id: str | None = None,
        funnel_id: str | None = None,
        asset_kind: str | None = None,
        tags: list[str] | None = None,
        statuses: list[object] | None = None,
    ):
        assert product_id == "product-123"
        assert asset_kind == "image"
        return []

    def fake_get_product(self, *, org_id: str, product_id: str):
        return type(
            "FakeProduct",
            (),
            {
                "id": product_id,
                "client_id": client_id,
            },
        )()

    def fake_create_funnel_image_asset(
        *,
        session,
        org_id: str,
        client_id: str,
        prompt: str,
        aspect_ratio: str | None = None,
        usage_context: dict[str, object] | None = None,
        reference_image_bytes=None,
        reference_image_mime_type=None,
        reference_asset_public_id: str | None = None,
        reference_asset_id: str | None = None,
        funnel_id: str | None = None,
        product_id: str | None = None,
        tags: list[str] | None = None,
    ):
        slot_path = usage_context.get("slotPath") if isinstance(usage_context, dict) else None
        assert isinstance(slot_path, str)
        observed.setdefault("prompts_by_slot", {})[slot_path] = prompt
        generated_public_id = generated_public_id_by_slot.get(slot_path)
        assert generated_public_id is not None
        return type(
            "FakeGeneratedAsset",
            (),
            {
                "public_id": generated_public_id,
                "width": 1600 if aspect_ratio == "16:9" else 1000,
                "height": 900 if aspect_ratio == "16:9" else 1000,
                "alt": None,
                "tags": ["shopify_theme_sync"],
                "ai_metadata": {"source": "ai"},
            },
        )()

    def fake_list_template_slots(
        *,
        client_id: str,
        theme_id: str | None,
        theme_name: str | None,
        shop_domain: str | None,
    ):
        return {
            "imageSlots": [
                {
                    "path": hero_slot,
                    "role": "hero",
                    "recommendedAspect": "16:9",
                    "currentValue": None,
                },
                {
                    "path": feature_slot_one,
                    "role": "supporting",
                    "recommendedAspect": "1:1",
                    "currentValue": None,
                },
                {
                    "path": feature_slot_two,
                    "role": "supporting",
                    "recommendedAspect": "1:1",
                    "currentValue": None,
                },
                {
                    "path": feature_slot_three,
                    "role": "supporting",
                    "recommendedAspect": "1:1",
                    "currentValue": None,
                },
                {
                    "path": feature_slot_four,
                    "role": "supporting",
                    "recommendedAspect": "1:1",
                    "currentValue": None,
                },
            ],
            "textSlots": [
                {
                    "path": (
                        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_47f4ep."
                        "settings.title"
                    ),
                    "role": "body",
                    "maxLength": 120,
                    "currentValue": "We deliver worldwide",
                },
                {
                    "path": (
                        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_47f4ep."
                        "settings.text"
                    ),
                    "role": "body",
                    "maxLength": 120,
                    "currentValue": "<strong>Fast</strong> shipping worldwide",
                },
                {
                    "path": (
                        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_4LDkHp."
                        "settings.title"
                    ),
                    "role": "body",
                    "maxLength": 120,
                    "currentValue": "Cruelty free care",
                },
                {
                    "path": (
                        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_4LDkHp."
                        "settings.text"
                    ),
                    "role": "body",
                    "maxLength": 120,
                    "currentValue": "Gentle on <em>all</em> skin types",
                },
                {
                    "path": (
                        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_HnJEzN."
                        "settings.title"
                    ),
                    "role": "body",
                    "maxLength": 120,
                    "currentValue": "Clinically tested",
                },
                {
                    "path": (
                        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_HnJEzN."
                        "settings.text"
                    ),
                    "role": "body",
                    "maxLength": 120,
                    "currentValue": "Backed by <strong>derm</strong> experts",
                },
                {
                    "path": (
                        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_RCFhqV."
                        "settings.title"
                    ),
                    "role": "body",
                    "maxLength": 120,
                    "currentValue": "Rechargeable at home",
                },
                {
                    "path": (
                        "templates/index.json.sections.ss_feature_1_pro_MNXtYb.blocks.slide_RCFhqV."
                        "settings.text"
                    ),
                    "role": "body",
                    "maxLength": 120,
                    "currentValue": "Simple routine in 10 minutes",
                },
            ],
        }

    def fake_list_offers(self, *, product_id: str):
        return []

    def fake_plan_component_content(
        *,
        product,
        offers,
        product_image_assets,
        image_slots,
        text_slots,
    ):
        observed["planner_asset_public_ids"] = {
            getattr(asset, "public_id", None) for asset in product_image_assets
        }
        component_image_asset_map = {hero_slot: "generated-hero"}
        for feature_slot in feature_slots:
            component_image_asset_map[feature_slot] = "generated-hero"
        return {"componentImageAssetMap": component_image_asset_map, "componentTextValues": {}}

    def fake_sync_theme_brand(
        *,
        client_id: str,
        workspace_name: str,
        brand_name: str,
        logo_url: str,
        css_vars: dict[str, str],
        font_urls: list[str] | None,
        data_theme: str | None,
        component_image_urls: dict[str, str] | None,
        component_text_values: dict[str, str] | None,
        auto_component_image_urls: list[str] | None,
        theme_id: str | None,
        theme_name: str | None,
        shop_domain: str | None,
    ):
        observed["component_image_urls"] = component_image_urls
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
    monkeypatch.setattr(clients_router.AssetsRepository, "get_by_public_id", fake_get_asset)
    monkeypatch.setattr(clients_router.AssetsRepository, "list", fake_list_assets)
    monkeypatch.setattr(clients_router.ProductsRepository, "get", fake_get_product)
    monkeypatch.setattr(clients_router, "create_funnel_image_asset", fake_create_funnel_image_asset)
    monkeypatch.setattr(
        clients_router,
        "list_client_shopify_theme_template_slots",
        fake_list_template_slots,
    )
    monkeypatch.setattr(clients_router.ProductOffersRepository, "list_by_product", fake_list_offers)
    monkeypatch.setattr(
        clients_router,
        "plan_shopify_theme_component_content",
        fake_plan_component_content,
    )
    monkeypatch.setattr(clients_router, "sync_client_shopify_theme_brand", fake_sync_theme_brand)
    monkeypatch.setattr(
        clients_router.settings, "PUBLIC_ASSET_BASE_URL", "https://assets.example.com"
    )

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/sync",
        json={
            "shopDomain": "example.myshopify.com",
            "designSystemId": "design-system-1",
            "productId": "product-123",
            "themeName": "futrgroup2-0theme",
        },
    )

    assert response.status_code == 200
    prompts_by_slot = observed["prompts_by_slot"]
    assert isinstance(prompts_by_slot, dict)
    assert "Feature context: We deliver worldwide Fast shipping worldwide." in (
        prompts_by_slot[feature_slot_one]
    )
    assert "Feature context: Cruelty free care Gentle on all skin types." in (
        prompts_by_slot[feature_slot_two]
    )
    assert "Feature context: Clinically tested Backed by derm experts." in (
        prompts_by_slot[feature_slot_three]
    )
    assert "Feature context: Rechargeable at home Simple routine in 10 minutes." in (
        prompts_by_slot[feature_slot_four]
    )
    assert observed["planner_asset_public_ids"] == {
        "generated-feature-1",
        "generated-feature-2",
        "generated-feature-3",
        "generated-feature-4",
        "generated-hero",
    }
    assert observed["component_image_urls"] == {
        hero_slot: "https://assets.example.com/public/assets/generated-hero",
        feature_slot_one: "https://assets.example.com/public/assets/generated-feature-1",
        feature_slot_two: "https://assets.example.com/public/assets/generated-feature-2",
        feature_slot_three: "https://assets.example.com/public/assets/generated-feature-3",
        feature_slot_four: "https://assets.example.com/public/assets/generated-feature-4",
    }


def test_sync_shopify_theme_brand_returns_422_when_ai_theme_image_generation_fails(
    api_client, monkeypatch
):
    client_id = _create_client(api_client, name="Acme Workspace")

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
            "fontUrls": [
                "https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap"
            ],
            "cssVars": {"--color-brand": "#123456"},
            "brand": {"name": "Acme", "logoAssetPublicId": "logo-public-id"},
            "funnelDefaults": {"containerWidth": "lg"},
        }

    def fake_get_asset(self, *, org_id: str, public_id: str, client_id: str | None = None):
        if public_id in {"logo-public-id"}:
            return type("FakeAsset", (), {"public_id": public_id})()
        return None

    def fake_get_product(self, *, org_id: str, product_id: str):
        return type(
            "FakeProduct",
            (),
            {
                "id": product_id,
                "client_id": client_id,
            },
        )()

    def fake_create_funnel_image_asset(
        *,
        session,
        org_id: str,
        client_id: str,
        prompt: str,
        aspect_ratio: str | None = None,
        usage_context: dict[str, object] | None = None,
        reference_image_bytes=None,
        reference_image_mime_type=None,
        reference_asset_public_id: str | None = None,
        reference_asset_id: str | None = None,
        funnel_id: str | None = None,
        product_id: str | None = None,
        tags: list[str] | None = None,
    ):
        raise RuntimeError("GEMINI_API_KEY not configured")

    def fake_list_template_slots(
        *,
        client_id: str,
        theme_id: str | None,
        theme_name: str | None,
        shop_domain: str | None,
    ):
        return {
            "imageSlots": [
                {
                    "path": "templates/index.json.sections.hero.settings.image",
                    "role": "hero",
                    "recommendedAspect": "16:9",
                    "currentValue": None,
                },
                {
                    "path": "templates/product.json.sections.gallery.settings.image",
                    "role": "gallery",
                    "recommendedAspect": "1:1",
                    "currentValue": None,
                },
            ],
            "textSlots": [],
        }

    monkeypatch.setattr(clients_router, "get_client_shopify_connection_status", fake_status)
    monkeypatch.setattr(clients_router.DesignSystemsRepository, "get", fake_design_system_get)
    monkeypatch.setattr(clients_router, "validate_design_system_tokens", fake_validate)
    monkeypatch.setattr(clients_router.AssetsRepository, "get_by_public_id", fake_get_asset)
    monkeypatch.setattr(clients_router.ProductsRepository, "get", fake_get_product)
    monkeypatch.setattr(clients_router, "create_funnel_image_asset", fake_create_funnel_image_asset)
    monkeypatch.setattr(
        clients_router,
        "list_client_shopify_theme_template_slots",
        fake_list_template_slots,
    )
    monkeypatch.setattr(
        clients_router.settings, "PUBLIC_ASSET_BASE_URL", "https://assets.example.com"
    )

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/sync",
        json={
            "shopDomain": "example.myshopify.com",
            "designSystemId": "design-system-1",
            "productId": "product-123",
            "themeName": "futrgroup2-0theme",
        },
    )

    assert response.status_code == 422
    assert "AI theme image generation failed for Shopify sync" in response.json()["detail"]


def test_sync_shopify_theme_brand_returns_429_when_ai_theme_image_generation_is_rate_limited(
    api_client, monkeypatch
):
    client_id = _create_client(api_client, name="Acme Workspace")

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
            "fontUrls": [
                "https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap"
            ],
            "cssVars": {"--color-brand": "#123456"},
            "brand": {"name": "Acme", "logoAssetPublicId": "logo-public-id"},
            "funnelDefaults": {"containerWidth": "lg"},
        }

    def fake_get_asset(self, *, org_id: str, public_id: str, client_id: str | None = None):
        if public_id in {"logo-public-id"}:
            return type("FakeAsset", (), {"public_id": public_id})()
        return None

    def fake_get_product(self, *, org_id: str, product_id: str):
        return type(
            "FakeProduct",
            (),
            {
                "id": product_id,
                "client_id": client_id,
            },
        )()

    def fake_create_funnel_image_asset(
        *,
        session,
        org_id: str,
        client_id: str,
        prompt: str,
        aspect_ratio: str | None = None,
        usage_context: dict[str, object] | None = None,
        reference_image_bytes=None,
        reference_image_mime_type=None,
        reference_asset_public_id: str | None = None,
        reference_asset_id: str | None = None,
        funnel_id: str | None = None,
        product_id: str | None = None,
        tags: list[str] | None = None,
    ):
        raise RuntimeError(
            "Gemini image request failed (status=429): "
            '{"error":{"status":"RESOURCE_EXHAUSTED","message":"You exceeded your current quota."}}'
        )

    def fake_create_funnel_unsplash_asset(
        *,
        session,
        org_id: str,
        client_id: str,
        query: str,
        usage_context: dict[str, object] | None = None,
        funnel_id: str | None = None,
        product_id: str | None = None,
        tags: list[str] | None = None,
    ):
        raise RuntimeError("UNSPLASH_ACCESS_KEY not configured")

    def fake_list_template_slots(
        *,
        client_id: str,
        theme_id: str | None,
        theme_name: str | None,
        shop_domain: str | None,
    ):
        return {
            "imageSlots": [
                {
                    "path": "templates/index.json.sections.hero.settings.image",
                    "role": "hero",
                    "recommendedAspect": "16:9",
                    "currentValue": None,
                },
                {
                    "path": "templates/product.json.sections.gallery.settings.image",
                    "role": "gallery",
                    "recommendedAspect": "1:1",
                    "currentValue": None,
                },
            ],
            "textSlots": [],
        }

    monkeypatch.setattr(clients_router, "get_client_shopify_connection_status", fake_status)
    monkeypatch.setattr(clients_router.DesignSystemsRepository, "get", fake_design_system_get)
    monkeypatch.setattr(clients_router, "validate_design_system_tokens", fake_validate)
    monkeypatch.setattr(clients_router.AssetsRepository, "get_by_public_id", fake_get_asset)
    monkeypatch.setattr(clients_router.ProductsRepository, "get", fake_get_product)
    monkeypatch.setattr(clients_router, "create_funnel_image_asset", fake_create_funnel_image_asset)
    monkeypatch.setattr(clients_router, "create_funnel_unsplash_asset", fake_create_funnel_unsplash_asset)
    monkeypatch.setattr(
        clients_router,
        "list_client_shopify_theme_template_slots",
        fake_list_template_slots,
    )
    monkeypatch.setattr(
        clients_router.settings, "PUBLIC_ASSET_BASE_URL", "https://assets.example.com"
    )

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/sync",
        json={
            "shopDomain": "example.myshopify.com",
            "designSystemId": "design-system-1",
            "productId": "product-123",
            "themeName": "futrgroup2-0theme",
        },
    )

    assert response.status_code == 429
    assert "AI theme image generation is rate-limited or out of Gemini quota" in response.json()["detail"]


def test_sync_shopify_theme_brand_uses_workspace_default_design_system_when_omitted(
    api_client, monkeypatch
):
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
            "fontUrls": [
                "https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap"
            ],
            "cssVars": {"--color-brand": "#123456"},
            "brand": {"name": "Acme", "logoAssetPublicId": "logo-public-id"},
            "funnelDefaults": {"containerWidth": "lg"},
        }

    def fake_get_logo_asset(self, *, org_id: str, public_id: str, client_id: str | None = None):
        return object()

    def fake_list_template_slots(
        *,
        client_id: str,
        theme_id: str | None,
        theme_name: str | None,
        shop_domain: str | None,
    ):
        return {"imageSlots": [], "textSlots": []}

    def fake_sync_theme_brand(
        *,
        client_id: str,
        workspace_name: str,
        brand_name: str,
        logo_url: str,
        css_vars: dict[str, str],
        font_urls: list[str] | None,
        data_theme: str | None,
        component_image_urls: dict[str, str] | None,
        component_text_values: dict[str, str] | None,
        auto_component_image_urls: list[str] | None,
        theme_id: str | None,
        theme_name: str | None,
        shop_domain: str | None,
    ):
        observed["sync_theme_name"] = theme_name
        observed["component_image_urls"] = component_image_urls
        observed["component_text_values"] = component_text_values
        observed["auto_component_image_urls"] = auto_component_image_urls
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
    monkeypatch.setattr(
        clients_router,
        "list_client_shopify_theme_template_slots",
        fake_list_template_slots,
    )
    monkeypatch.setattr(clients_router, "sync_client_shopify_theme_brand", fake_sync_theme_brand)
    monkeypatch.setattr(
        clients_router.settings, "PUBLIC_ASSET_BASE_URL", "https://assets.example.com"
    )

    response = api_client.post(
        f"/clients/{client_id}/shopify/theme/brand/sync",
        json={"shopDomain": "example.myshopify.com", "themeName": "futrgroup2-0theme"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["designSystemId"] == "workspace-default-design-system"
    assert observed["design_system_id"] == "workspace-default-design-system"
    assert observed["sync_theme_name"] == "futrgroup2-0theme"
    assert observed["component_image_urls"] == {}
    assert observed["component_text_values"] == {}
    assert observed["auto_component_image_urls"] == []


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
