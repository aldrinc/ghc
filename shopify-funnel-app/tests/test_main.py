from __future__ import annotations

import hashlib
import hmac

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
def api_client():
    with TestClient(main_module.app) as client:
        yield client


def test_auth_callback_auto_provisions_storefront_token(api_client, db_session, monkeypatch):
    shop_domain = "example.myshopify.com"
    oauth_state = OAuthState(state="state_1", shop_domain=shop_domain, client_id="client_1")
    db_session.add(oauth_state)
    db_session.commit()

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

    response = api_client.get(
        "/auth/callback",
        params=_build_oauth_callback_params(
            shop=shop_domain,
            code="oauth_code",
            state="state_1",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["hasStorefrontAccessToken"] is True
    assert payload["storefrontTokenAutoProvisioned"] is True
    assert payload["storefrontTokenAutoProvisioningError"] is None

    installation = db_session.scalars(
        select(ShopInstallation).where(ShopInstallation.shop_domain == shop_domain)
    ).first()
    assert installation is not None
    assert installation.client_id == "client_1"
    assert installation.storefront_access_token == "shpat_auto_token"


def test_auth_callback_keeps_installation_when_auto_provision_fails(
    api_client, db_session, monkeypatch
):
    shop_domain = "example.myshopify.com"
    oauth_state = OAuthState(state="state_2", shop_domain=shop_domain, client_id="client_2")
    db_session.add(oauth_state)
    db_session.commit()

    async def fake_exchange_code_for_access_token(*, shop_domain: str, code: str):
        return "admin_access_token", "read_products,write_products"

    async def fake_register_webhook(*, shop_domain: str, access_token: str, topic: str, callback_url: str):
        return "gid://shopify/WebhookSubscription/2"

    async def fake_create_storefront_access_token(*, shop_domain: str, access_token: str, title: str = "Marketi Funnel Checkout"):
        raise ShopifyApiError(
            message="storefrontAccessTokenCreate failed: access denied",
            status_code=409,
        )

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

    response = api_client.get(
        "/auth/callback",
        params=_build_oauth_callback_params(
            shop=shop_domain,
            code="oauth_code",
            state="state_2",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["hasStorefrontAccessToken"] is False
    assert payload["storefrontTokenAutoProvisioned"] is False
    assert "storefrontAccessTokenCreate failed: access denied" in payload["storefrontTokenAutoProvisioningError"]

    installation = db_session.scalars(
        select(ShopInstallation).where(ShopInstallation.shop_domain == shop_domain)
    ).first()
    assert installation is not None
    assert installation.client_id == "client_2"
    assert installation.admin_access_token == "admin_access_token"
    assert installation.storefront_access_token is None


def test_auto_storefront_token_endpoint_sets_token_for_active_installation(
    api_client, db_session, monkeypatch
):
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

    monkeypatch.setattr(
        main_module.shopify_api,
        "create_storefront_access_token",
        fake_create_storefront_access_token,
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
