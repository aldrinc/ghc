from __future__ import annotations

import uuid

from app.config import settings
from app.db.models import Client, Org, ShopifyThemeTemplateDraft


def test_shopify_compliance_webhook_requires_valid_secret(api_client, monkeypatch):
    monkeypatch.setattr(settings, "SHOPIFY_COMPLIANCE_WEBHOOK_SECRET", "test-secret")

    response = api_client.post(
        "/shopify/compliance/webhook",
        json={
            "topic": "customers/data_request",
            "shopDomain": "example.myshopify.com",
            "eventId": "evt_1",
            "payload": {"shop_domain": "example.myshopify.com"},
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid Shopify compliance webhook secret."


def test_shopify_compliance_shop_redact_deletes_template_drafts(
    api_client,
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "SHOPIFY_COMPLIANCE_WEBHOOK_SECRET", "test-secret")
    org = db_session.query(Org).first()
    assert org is not None
    client = Client(org_id=org.id, name="Compliance Client", industry="Supplements")
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)

    draft = ShopifyThemeTemplateDraft(
        id=uuid.uuid4(),
        org_id=org.id,
        client_id=client.id,
        shop_domain="example.myshopify.com",
        theme_id="gid://shopify/OnlineStoreTheme/1",
        theme_name="futrgroup2-0theme",
        theme_role="MAIN",
        status="draft",
    )
    db_session.add(draft)
    db_session.commit()

    response = api_client.post(
        "/shopify/compliance/webhook",
        headers={"x-marketi-webhook-secret": "test-secret"},
        json={
            "topic": "shop/redact",
            "shopDomain": "example.myshopify.com",
            "eventId": "evt_shop_redact_1",
            "payload": {"shop_domain": "example.myshopify.com"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["topic"] == "shop/redact"
    assert body["deletedThemeTemplateDrafts"] == 1

    remaining = db_session.query(ShopifyThemeTemplateDraft).filter(
        ShopifyThemeTemplateDraft.shop_domain == "example.myshopify.com"
    ).all()
    assert remaining == []
