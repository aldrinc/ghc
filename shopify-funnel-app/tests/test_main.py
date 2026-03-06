from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

import app.main as main_module
from app.config import settings
from app.db import SessionLocal, init_db
from app.models import OAuthState, ProcessedWebhookEvent, ShopInstallation
from app.shopify_api import ShopifyApiError


def _build_oauth_callback_params(
    *,
    shop: str,
    code: str,
    state: str,
) -> dict[str, str]:
    items = [("code", code), ("shop", shop), ("state", state)]
    message = "&".join(f"{key}={value}" for key, value in sorted(items, key=lambda item: item[0]))
    digest = hmac.new(
        settings.SHOPIFY_APP_API_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {"shop": shop, "code": code, "state": state, "hmac": digest}


def _build_webhook_headers(
    *,
    body: bytes,
    shop_domain: str,
    event_id: str,
    topic: str | None = None,
) -> dict[str, str]:
    digest = hmac.new(
        settings.SHOPIFY_APP_API_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    headers = {
        "x-shopify-hmac-sha256": base64.b64encode(digest).decode("utf-8"),
        "x-shopify-shop-domain": shop_domain,
        "x-shopify-event-id": event_id,
    }
    if topic:
        headers["x-shopify-topic"] = topic
    return headers


@pytest.fixture()
def db_session():
    init_db()
    session = SessionLocal()
    session.execute(delete(ProcessedWebhookEvent))
    session.execute(delete(OAuthState))
    session.execute(delete(ShopInstallation))
    session.commit()
    try:
        yield session
    finally:
        session.execute(delete(ProcessedWebhookEvent))
        session.execute(delete(OAuthState))
        session.execute(delete(ShopInstallation))
        session.commit()
        session.close()


@pytest.fixture()
def api_client(monkeypatch):
    monkeypatch.setattr(settings, "SHOPIFY_INSTALL_SUCCESS_REDIRECT_URL", None)
    with TestClient(main_module.app) as client:
        yield client


def test_auth_callback_auto_provisions_storefront_token(api_client, db_session, monkeypatch):
    shop_domain = "example.myshopify.com"
    oauth_state = OAuthState(state="state_1", shop_domain=shop_domain, client_id="client_1")
    db_session.add(oauth_state)
    db_session.commit()
    observed_default_syncs: list[tuple[str, str]] = []

    async def fake_exchange_code_for_access_token(*, shop_domain: str, code: str):
        assert shop_domain == "example.myshopify.com"
        assert code == "oauth_code"
        return "admin_access_token", "read_products,write_products"

    async def fake_register_webhook(*, shop_domain: str, access_token: str, topic: str, callback_url: str):
        assert shop_domain == "example.myshopify.com"
        assert access_token == "admin_access_token"
        assert topic == "APP_UNINSTALLED"
        return "gid://shopify/WebhookSubscription/1"

    async def fake_create_storefront_access_token(*, shop_domain: str, access_token: str, title: str = "Marketi Funnel Checkout"):
        assert shop_domain == "example.myshopify.com"
        assert access_token == "admin_access_token"
        assert title == "Marketi Funnel Checkout"
        return "shpat_auto_token"

    async def fake_apply_shop_connection_defaults(
        *,
        shop_domain: str,
        admin_access_token: str,
    ):
        observed_default_syncs.append((shop_domain, admin_access_token))
        assert shop_domain == "example.myshopify.com"
        assert admin_access_token == "admin_access_token"

    monkeypatch.setattr(
        main_module.shopify_api,
        "exchange_code_for_access_token",
        fake_exchange_code_for_access_token,
    )
    monkeypatch.setattr(
        main_module.shopify_api,
        "register_webhook",
        fake_register_webhook,
    )
    monkeypatch.setattr(
        main_module.shopify_api,
        "create_storefront_access_token",
        fake_create_storefront_access_token,
    )
    monkeypatch.setattr(
        main_module,
        "_apply_shop_connection_defaults",
        fake_apply_shop_connection_defaults,
    )

    response = api_client.get(
        "/auth/callback",
        params=_build_oauth_callback_params(
            shop=shop_domain,
            code="oauth_code",
            state="state_1",
        ),
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"].startswith(
        f"{settings.app_base_url}/app?shop={shop_domain}"
    )

    installation = db_session.scalars(
        select(ShopInstallation).where(ShopInstallation.shop_domain == shop_domain)
    ).first()
    assert installation is not None
    assert installation.client_id == "client_1"
    assert installation.storefront_access_token == "shpat_auto_token"
    assert observed_default_syncs == [("example.myshopify.com", "admin_access_token")]


def test_auth_callback_keeps_installation_when_auto_provision_fails(
    api_client, db_session, monkeypatch
):
    shop_domain = "example.myshopify.com"
    oauth_state = OAuthState(state="state_2", shop_domain=shop_domain, client_id="client_2")
    db_session.add(oauth_state)
    db_session.commit()
    observed_default_syncs: list[tuple[str, str]] = []

    async def fake_exchange_code_for_access_token(*, shop_domain: str, code: str):
        return "admin_access_token", "read_products,write_products"

    async def fake_register_webhook(*, shop_domain: str, access_token: str, topic: str, callback_url: str):
        return "gid://shopify/WebhookSubscription/2"

    async def fake_create_storefront_access_token(*, shop_domain: str, access_token: str, title: str = "Marketi Funnel Checkout"):
        raise ShopifyApiError(
            message="storefrontAccessTokenCreate failed: access denied",
            status_code=409,
        )

    async def fake_apply_shop_connection_defaults(
        *,
        shop_domain: str,
        admin_access_token: str,
    ):
        observed_default_syncs.append((shop_domain, admin_access_token))
        assert shop_domain == "example.myshopify.com"
        assert admin_access_token == "admin_access_token"

    monkeypatch.setattr(
        main_module.shopify_api,
        "exchange_code_for_access_token",
        fake_exchange_code_for_access_token,
    )
    monkeypatch.setattr(
        main_module.shopify_api,
        "register_webhook",
        fake_register_webhook,
    )
    monkeypatch.setattr(
        main_module.shopify_api,
        "create_storefront_access_token",
        fake_create_storefront_access_token,
    )
    monkeypatch.setattr(
        main_module,
        "_apply_shop_connection_defaults",
        fake_apply_shop_connection_defaults,
    )

    response = api_client.get(
        "/auth/callback",
        params=_build_oauth_callback_params(
            shop=shop_domain,
            code="oauth_code",
            state="state_2",
        ),
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"].startswith(
        f"{settings.app_base_url}/app?shop={shop_domain}"
    )

    installation = db_session.scalars(
        select(ShopInstallation).where(ShopInstallation.shop_domain == shop_domain)
    ).first()
    assert installation is not None
    assert installation.client_id == "client_2"
    assert installation.admin_access_token == "admin_access_token"
    assert installation.storefront_access_token is None
    assert observed_default_syncs == [("example.myshopify.com", "admin_access_token")]


def test_auth_callback_redirects_to_embedded_app(api_client, db_session, monkeypatch):
    shop_domain = "example.myshopify.com"
    oauth_state = OAuthState(state="state_public_1", shop_domain=shop_domain, client_id="client_3")
    db_session.add(oauth_state)
    db_session.commit()
    async def fake_exchange_code_for_access_token(*, shop_domain: str, code: str):
        return "admin_access_token", "read_products,write_products"

    async def fake_register_webhook(*, shop_domain: str, access_token: str, topic: str, callback_url: str):
        return "gid://shopify/WebhookSubscription/3"

    async def fake_create_storefront_access_token(*, shop_domain: str, access_token: str, title: str = "Marketi Funnel Checkout"):
        return "shpat_public"

    async def fake_apply_shop_connection_defaults(
        *,
        shop_domain: str,
        admin_access_token: str,
    ):
        assert shop_domain == "example.myshopify.com"
        assert admin_access_token == "admin_access_token"

    monkeypatch.setattr(
        main_module.shopify_api,
        "exchange_code_for_access_token",
        fake_exchange_code_for_access_token,
    )
    monkeypatch.setattr(
        main_module.shopify_api,
        "register_webhook",
        fake_register_webhook,
    )
    monkeypatch.setattr(
        main_module.shopify_api,
        "create_storefront_access_token",
        fake_create_storefront_access_token,
    )
    monkeypatch.setattr(
        main_module,
        "_apply_shop_connection_defaults",
        fake_apply_shop_connection_defaults,
    )

    response = api_client.get(
        "/auth/callback",
        params={
            **_build_oauth_callback_params(
                shop=shop_domain,
                code="oauth_code",
                state="state_public_1",
            ),
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"].startswith(f"{settings.app_base_url}/app?shop={shop_domain}")


def test_app_url_entrypoint_redirects_install_when_shop_is_present(api_client):
    response = api_client.get(
        "/",
        params={"shop": "Example-Store.myshopify.com", "client_id": "client_123"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert (
        response.headers["location"]
        == f"{settings.app_base_url}/auth/install?shop=example-store.myshopify.com&client_id=client_123"
    )


def test_app_url_entrypoint_redirects_to_embedded_shell_when_host_is_present(api_client):
    response = api_client.get(
        "/",
        params={"host": "Zm9vLmJhcg==", "shop": "example.myshopify.com"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert (
        response.headers["location"]
        == f"{settings.app_base_url}/app?host=Zm9vLmJhcg%3D%3D&shop=example.myshopify.com"
    )


def test_app_url_entrypoint_returns_info_page_without_shop_context(api_client):
    response = api_client.get("/")

    assert response.status_code == 200
    assert "reserved for Shopify app launch and install flows" in response.text


def test_embedded_shell_loads_latest_app_bridge_script(api_client):
    response = api_client.get("/app")

    assert response.status_code == 200
    assert "https://cdn.shopify.com/shopifycloud/app-bridge.js" in response.text
    assert "unpkg.com/@shopify/app-bridge" not in response.text


def test_apply_shop_connection_defaults_only_ensures_catalog_route(monkeypatch):
    observed: dict[str, object] = {}

    async def fake_ensure_catalog_collection_route_is_available(
        *,
        shop_domain: str,
        access_token: str,
        sync_all_products: bool = True,
    ):
        observed["shop_domain"] = shop_domain
        observed["access_token"] = access_token
        observed["sync_all_products"] = sync_all_products
        return {
            "collectionId": "gid://shopify/Collection/1",
            "collectionHandle": "all",
            "collectionTitle": "Catalog",
            "addedProductCount": 0,
        }

    async def fake_normalize_catalog_in_default_store_navigation(
        *,
        shop_domain: str,
        access_token: str,
    ):
        observed["normalized_shop_domain"] = shop_domain
        observed["normalized_access_token"] = access_token
        return {
            "handle": "main-menu",
            "updated": True,
            "reason": "catalog_normalized",
        }

    monkeypatch.setattr(
        main_module.shopify_api,
        "ensure_catalog_collection_route_is_available",
        fake_ensure_catalog_collection_route_is_available,
    )
    monkeypatch.setattr(
        main_module.shopify_api,
        "normalize_catalog_in_default_store_navigation",
        fake_normalize_catalog_in_default_store_navigation,
    )

    asyncio.run(
        main_module._apply_shop_connection_defaults(
            shop_domain="example.myshopify.com",
            admin_access_token=" admin_access_token ",
        )
    )

    assert observed == {
        "shop_domain": "example.myshopify.com",
        "access_token": "admin_access_token",
        "sync_all_products": False,
        "normalized_shop_domain": "example.myshopify.com",
        "normalized_access_token": "admin_access_token",
    }


def test_auto_storefront_token_endpoint_sets_token_for_active_installation(
    api_client, db_session, monkeypatch
):
    observed_default_syncs: list[tuple[str, str]] = []
    installation = ShopInstallation(
        shop_domain="example.myshopify.com",
        client_id="client_1",
        admin_access_token="admin_access_token",
        storefront_access_token=None,
        scopes="read_products",
    )
    db_session.add(installation)
    db_session.commit()

    async def fake_create_storefront_access_token(*, shop_domain: str, access_token: str, title: str = "Marketi Funnel Checkout"):
        assert shop_domain == "example.myshopify.com"
        assert access_token == "admin_access_token"
        return "shpat_retry"

    async def fake_apply_shop_connection_defaults(
        *,
        shop_domain: str,
        admin_access_token: str,
    ):
        observed_default_syncs.append((shop_domain, admin_access_token))
        assert shop_domain == "example.myshopify.com"
        assert admin_access_token == "admin_access_token"

    monkeypatch.setattr(
        main_module.shopify_api,
        "create_storefront_access_token",
        fake_create_storefront_access_token,
    )
    monkeypatch.setattr(
        main_module,
        "_apply_shop_connection_defaults",
        fake_apply_shop_connection_defaults,
    )

    response = api_client.post(
        "/admin/installations/example.myshopify.com/storefront-token/auto",
        headers={"Authorization": f"Bearer {settings.SHOPIFY_INTERNAL_API_TOKEN}"},
        json={"clientId": "client_1"},
    )

    assert response.status_code == 200
    assert response.json()["hasStorefrontAccessToken"] is True

    refreshed = db_session.scalars(
        select(ShopInstallation).where(
            ShopInstallation.shop_domain == "example.myshopify.com"
        )
    ).first()
    assert refreshed is not None
    assert refreshed.storefront_access_token == "shpat_retry"
    assert observed_default_syncs == [("example.myshopify.com", "admin_access_token")]


def test_sync_catalog_collection_endpoint_uses_target_product_gids(
    api_client, db_session, monkeypatch
):
    installation = ShopInstallation(
        shop_domain="example.myshopify.com",
        client_id="client_1",
        admin_access_token="admin_access_token",
        storefront_access_token="storefront_token",
        scopes="read_products",
    )
    db_session.add(installation)
    db_session.commit()

    observed: dict[str, object] = {}

    async def fake_ensure_catalog_collection_contains_products(
        *,
        shop_domain: str,
        access_token: str,
        product_gids: list[str],
    ):
        observed["shop_domain"] = shop_domain
        observed["access_token"] = access_token
        observed["product_gids"] = product_gids
        return {
            "collectionId": "gid://shopify/Collection/1",
            "collectionHandle": "all",
            "collectionTitle": "Catalog",
            "requestedProductCount": 2,
            "addedProductCount": 1,
        }

    monkeypatch.setattr(
        main_module.shopify_api,
        "ensure_catalog_collection_contains_products",
        fake_ensure_catalog_collection_contains_products,
    )

    response = api_client.post(
        "/v1/catalog/collection/sync",
        headers={"Authorization": f"Bearer {settings.SHOPIFY_INTERNAL_API_TOKEN}"},
        json={
            "clientId": "client_1",
            "productGids": [
                "gid://shopify/Product/10",
                "gid://shopify/Product/11",
            ],
        },
    )

    assert response.status_code == 200
    assert observed == {
        "shop_domain": "example.myshopify.com",
        "access_token": "admin_access_token",
        "product_gids": [
            "gid://shopify/Product/10",
            "gid://shopify/Product/11",
        ],
    }
    assert response.json() == {
        "shopDomain": "example.myshopify.com",
        "collectionId": "gid://shopify/Collection/1",
        "collectionHandle": "all",
        "collectionTitle": "Catalog",
        "requestedProductCount": 2,
        "addedProductCount": 1,
    }


def test_auto_storefront_token_endpoint_rejects_workspace_mismatch(
    api_client, db_session
):
    installation = ShopInstallation(
        shop_domain="example.myshopify.com",
        client_id="client_other",
        admin_access_token="admin_access_token",
        storefront_access_token=None,
        scopes="read_products",
    )
    db_session.add(installation)
    db_session.commit()

    response = api_client.post(
        "/admin/installations/example.myshopify.com/storefront-token/auto",
        headers={"Authorization": f"Bearer {settings.SHOPIFY_INTERNAL_API_TOKEN}"},
        json={"clientId": "client_1"},
    )

    assert response.status_code == 409
    assert (
        response.json()["detail"]
        == "This Shopify store is already connected to a different workspace. connectedWorkspaceId=client_other"
    )


def test_compliance_customers_data_request_webhook_is_acknowledged(
    api_client, db_session
):
    shop_domain = "example.myshopify.com"
    payload = {"shop_domain": shop_domain, "customer": {"id": 123456789}}
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    response = api_client.post(
        "/webhooks/compliance",
        content=body,
        headers=_build_webhook_headers(
            body=body,
            shop_domain=shop_domain,
            event_id="evt_customers_data_request_1",
            topic="customers/data_request",
        ),
    )

    assert response.status_code == 200
    assert response.json()["topic"] == "customers/data_request"

    event = db_session.scalars(
        select(ProcessedWebhookEvent).where(
            ProcessedWebhookEvent.shop_domain == shop_domain,
            ProcessedWebhookEvent.topic == "customers/data_request",
            ProcessedWebhookEvent.event_id == "evt_customers_data_request_1",
        )
    ).first()
    assert event is not None
    assert event.status == "no_local_customer_data_for_requested_customer"


def test_compliance_shop_redact_webhook_purges_shop_data(api_client, db_session):
    shop_domain = "example.myshopify.com"
    db_session.add(
        ShopInstallation(
            shop_domain=shop_domain,
            client_id="client_1",
            admin_access_token="admin_access_token",
            storefront_access_token="storefront_token",
            scopes="read_products",
        )
    )
    db_session.add(
        OAuthState(state="redact_state_1", shop_domain=shop_domain, client_id="client_1")
    )
    db_session.add(
        ProcessedWebhookEvent(
            shop_domain=shop_domain,
            topic="ORDERS_CREATE",
            event_id="evt_order_1",
            status="forwarded",
        )
    )
    db_session.commit()

    payload = {"shop_domain": shop_domain, "shop_id": 987654321}
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    response = api_client.post(
        "/webhooks/compliance",
        content=body,
        headers=_build_webhook_headers(
            body=body,
            shop_domain=shop_domain,
            event_id="evt_shop_redact_1",
            topic="shop/redact",
        ),
    )

    assert response.status_code == 200
    assert response.json()["topic"] == "shop/redact"

    remaining_installation = db_session.scalars(
        select(ShopInstallation).where(ShopInstallation.shop_domain == shop_domain)
    ).first()
    remaining_oauth_state = db_session.scalars(
        select(OAuthState).where(OAuthState.shop_domain == shop_domain)
    ).first()
    remaining_events = db_session.scalars(
        select(ProcessedWebhookEvent).where(
            ProcessedWebhookEvent.shop_domain == shop_domain
        )
    ).all()

    assert remaining_installation is None
    assert remaining_oauth_state is None
    assert remaining_events == []


def test_export_theme_brand_endpoint_is_disabled(api_client, db_session):
    installation = ShopInstallation(
        shop_domain="example.myshopify.com",
        client_id="client_1",
        admin_access_token="admin_access_token",
        storefront_access_token="storefront_token",
        scopes="read_products",
    )
    db_session.add(installation)
    db_session.commit()

    response = api_client.post(
        "/v1/themes/brand/export",
        headers={"Authorization": f"Bearer {settings.SHOPIFY_INTERNAL_API_TOKEN}"},
        json={
            "clientId": "client_1",
            "workspaceName": "Acme Workspace",
            "brandName": "Acme",
            "logoUrl": "https://assets.example.com/public/assets/logo-1",
            "cssVars": {"--color-brand": "#123456"},
            "fontUrls": [],
            "componentImageUrls": {
                "templates/index.json.sections.hero.settings.image": "https://assets.example.com/public/assets/hero"
            },
            "componentTextValues": {},
            "autoComponentImageUrls": [],
            "dataTheme": "light",
            "themeName": "futrgroup2-0theme",
        },
    )

    assert response.status_code == 403
    assert (
        response.json()["detail"]
        == "Theme file export for manual storefront code changes is disabled. Use theme app extensions for storefront updates."
    )


def test_embedded_session_reports_installation_state(api_client, db_session):
    shop_domain = "example.myshopify.com"
    db_session.add(
        ShopInstallation(
            shop_domain=shop_domain,
            client_id="client_1",
            admin_access_token="admin_access_token",
            storefront_access_token="storefront_token",
            scopes="read_products",
        )
    )
    db_session.commit()

    api_client.app.dependency_overrides[
        main_module.require_shopify_session_shop_domain
    ] = lambda: shop_domain
    try:
        response = api_client.get("/app/api/session")
    finally:
        api_client.app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["shopDomain"] == shop_domain
    assert payload["isInstalled"] is True
    assert payload["linkedWorkspaceId"] == "client_1"
    assert payload["installationState"] == "installed"


def test_embedded_link_workspace_updates_client_binding(api_client, db_session, monkeypatch):
    shop_domain = "example.myshopify.com"
    observed_default_syncs: list[tuple[str, str]] = []
    db_session.add(
        ShopInstallation(
            shop_domain=shop_domain,
            client_id=None,
            admin_access_token="admin_access_token",
            storefront_access_token=None,
            scopes="read_products",
        )
    )
    db_session.commit()

    async def fake_apply_shop_connection_defaults(
        *,
        shop_domain: str,
        admin_access_token: str,
    ):
        observed_default_syncs.append((shop_domain, admin_access_token))
        assert shop_domain == "example.myshopify.com"
        assert admin_access_token == "admin_access_token"

    monkeypatch.setattr(
        main_module,
        "_apply_shop_connection_defaults",
        fake_apply_shop_connection_defaults,
    )

    api_client.app.dependency_overrides[
        main_module.require_shopify_session_shop_domain
    ] = lambda: shop_domain
    try:
        response = api_client.post(
            "/app/api/link-workspace",
            json={"clientId": "client_abc"},
        )
    finally:
        api_client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["linkedWorkspaceId"] == "client_abc"

    refreshed = db_session.scalars(
        select(ShopInstallation).where(
            ShopInstallation.shop_domain == "example.myshopify.com"
        )
    ).first()
    assert refreshed is not None
    assert refreshed.client_id == "client_abc"
    assert observed_default_syncs == [("example.myshopify.com", "admin_access_token")]


def test_embedded_auto_storefront_token_provisions_token(api_client, db_session, monkeypatch):
    shop_domain = "example.myshopify.com"
    observed_default_syncs: list[tuple[str, str]] = []
    db_session.add(
        ShopInstallation(
            shop_domain=shop_domain,
            client_id="client_1",
            admin_access_token="admin_access_token",
            storefront_access_token=None,
            scopes="read_products",
        )
    )
    db_session.commit()

    async def fake_create_storefront_access_token(
        *,
        shop_domain: str,
        access_token: str,
        title: str = "Marketi Funnel Checkout",
    ):
        assert shop_domain == "example.myshopify.com"
        assert access_token == "admin_access_token"
        assert title == "Marketi Funnel Checkout"
        return "shpat_embedded"

    async def fake_apply_shop_connection_defaults(
        *,
        shop_domain: str,
        admin_access_token: str,
    ):
        observed_default_syncs.append((shop_domain, admin_access_token))
        assert shop_domain == "example.myshopify.com"
        assert admin_access_token == "admin_access_token"

    monkeypatch.setattr(
        main_module.shopify_api,
        "create_storefront_access_token",
        fake_create_storefront_access_token,
    )
    monkeypatch.setattr(
        main_module,
        "_apply_shop_connection_defaults",
        fake_apply_shop_connection_defaults,
    )

    api_client.app.dependency_overrides[
        main_module.require_shopify_session_shop_domain
    ] = lambda: shop_domain
    try:
        response = api_client.post(
            "/app/api/storefront-token/auto",
            json={"clientId": "client_1"},
        )
    finally:
        api_client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["hasStorefrontAccessToken"] is True
    assert response.json()["installationState"] == "installed"

    refreshed = db_session.scalars(
        select(ShopInstallation).where(ShopInstallation.shop_domain == shop_domain)
    ).first()
    assert refreshed is not None
    assert refreshed.storefront_access_token == "shpat_embedded"
    assert observed_default_syncs == [("example.myshopify.com", "admin_access_token")]


def test_embedded_auto_storefront_token_rejects_workspace_mismatch(
    api_client, db_session
):
    shop_domain = "example.myshopify.com"
    db_session.add(
        ShopInstallation(
            shop_domain=shop_domain,
            client_id="client_existing",
            admin_access_token="admin_access_token",
            storefront_access_token=None,
            scopes="read_products",
        )
    )
    db_session.commit()

    api_client.app.dependency_overrides[
        main_module.require_shopify_session_shop_domain
    ] = lambda: shop_domain
    try:
        response = api_client.post(
            "/app/api/storefront-token/auto",
            json={"clientId": "client_other"},
        )
    finally:
        api_client.app.dependency_overrides.clear()

    assert response.status_code == 409
    assert (
        response.json()["detail"]
        == "This Shopify store is already linked to a different mOS workspace. linkedWorkspaceId=client_existing"
    )


def test_theme_write_endpoint_is_disabled(api_client, db_session, monkeypatch):
    installation = ShopInstallation(
        shop_domain="example.myshopify.com",
        client_id="client_1",
        admin_access_token="admin_access_token",
        storefront_access_token="storefront_token",
        scopes="read_products",
    )
    db_session.add(installation)
    db_session.commit()
    response = api_client.post(
        "/v1/themes/brand/sync",
        headers={"Authorization": f"Bearer {settings.SHOPIFY_INTERNAL_API_TOKEN}"},
        json={
            "clientId": "client_1",
            "workspaceName": "Acme Workspace",
            "brandName": "Acme",
            "logoUrl": "https://assets.example.com/public/assets/logo-1",
            "cssVars": {"--color-brand": "#123456"},
            "fontUrls": [],
            "themeName": "futrgroup2-0theme",
        },
    )

    assert response.status_code == 403
    assert "Direct theme write operations are disabled." in response.json()["detail"]
