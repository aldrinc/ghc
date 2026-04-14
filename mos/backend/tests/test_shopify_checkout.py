from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

from sqlalchemy import select

from app.config import settings
from app.db.enums import FunnelEventTypeEnum, FunnelPageVersionStatusEnum, FunnelStatusEnum
from app.db.models import (
    Client,
    Funnel,
    FunnelEvent,
    FunnelOrder,
    FunnelPage,
    FunnelPageVersion,
    FunnelPublication,
    FunnelPublicationPage,
    MetaAdAccountConnection,
    MetaWorkspaceAdConfig,
    PaidAdsPlatformProfile,
    Product,
    ProductOffer,
    ProductVariant,
)
from app.routers import public_funnels
from app.services.integration_secrets import encrypt_secret_json
from app.services.meta_ads import MetaAdsClient, MetaAdsError


def _seed_shopify_funnel(*, db_session, org_id: UUID, with_selected_offer: bool = False):
    client = Client(org_id=org_id, name="Shopify Client", industry="Retail")
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)

    product = Product(
        org_id=org_id, client_id=client.id, title="Shopify Product", handle="shopify-product"
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    selected_offer = None
    if with_selected_offer:
        selected_offer = ProductOffer(
            org_id=org_id,
            client_id=client.id,
            product_id=product.id,
            name="Primary Offer",
            business_model="one_time",
        )
        db_session.add(selected_offer)
        db_session.commit()
        db_session.refresh(selected_offer)

    variant = ProductVariant(
        product_id=product.id,
        offer_id=selected_offer.id if selected_offer else None,
        title="Default",
        price=2999,
        currency="USD",
        provider="shopify",
        external_price_id="gid://shopify/ProductVariant/123456789",
        option_values=None,
    )
    db_session.add(variant)
    db_session.commit()
    db_session.refresh(variant)

    funnel = Funnel(
        org_id=org_id,
        client_id=client.id,
        product_id=product.id,
        selected_offer_id=selected_offer.id if selected_offer else None,
        name="Shopify Funnel",
        route_slug=f"shopify-funnel-{uuid4().hex[:8]}",
    )
    db_session.add(funnel)
    db_session.commit()
    db_session.refresh(funnel)

    return {
        "client": client,
        "product": product,
        "offer": selected_offer,
        "variant": variant,
        "funnel": funnel,
    }


def _seed_active_meta_tracking(
    *, db_session, seeded: dict[str, object], org_id: UUID, pixel_id: str = "1234567890"
):
    client = seeded["client"]
    connection = MetaAdAccountConnection(
        org_id=org_id,
        name="Primary Meta Connection",
        ad_account_id="act_123456",
        ad_account_name="Test Ad Account",
        business_manager_id="bm_123",
        business_manager_name="Test Business",
        graph_api_version="v23.0",
        graph_api_base_url="https://graph.facebook.com",
        credentials_encrypted=encrypt_secret_json({"accessToken": "meta-token"}),
        status="active",
        validation_status="passed",
    )
    db_session.add(connection)
    db_session.commit()
    db_session.refresh(connection)

    workspace_config = MetaWorkspaceAdConfig(
        org_id=org_id,
        client_id=client.id,
        meta_connection_id=connection.id,
        name="Primary Meta Workspace Config",
        is_default=True,
        status="active",
        pixel_id=pixel_id,
        validation_status="passed",
    )
    db_session.add(workspace_config)

    platform_profile = PaidAdsPlatformProfile(
        org_id=org_id,
        client_id=client.id,
        platform="meta",
        ruleset_version="paid_ads_policy_ruleset_v2",
        ad_account_id="act_123456",
        ad_account_name="Test Ad Account",
        pixel_id=pixel_id,
        metadata_json={
            "mosMetaTracking": {
                "status": "active",
                "mode": "public_funnel_runtime",
                "channel": "meta",
                "pixelId": pixel_id,
            }
        },
    )
    db_session.add(platform_profile)
    db_session.commit()

    return {
        "connection": connection,
        "workspace_config": workspace_config,
        "platform_profile": platform_profile,
        "pixel_id": pixel_id,
    }


def _publish_sales_page(*, db_session, funnel: Funnel) -> FunnelPage:
    sales_page = FunnelPage(
        funnel_id=funnel.id,
        name="Sales",
        slug="offer",
        template_id="sales-pdp",
        ordering=1,
    )
    db_session.add(sales_page)
    db_session.commit()
    db_session.refresh(sales_page)

    version = FunnelPageVersion(
        page_id=sales_page.id,
        status=FunnelPageVersionStatusEnum.approved,
        puck_data={"root": {}},
    )
    db_session.add(version)
    db_session.commit()
    db_session.refresh(version)

    publication = FunnelPublication(
        funnel_id=funnel.id,
        entry_page_id=sales_page.id,
        created_by="test-user",
    )
    db_session.add(publication)
    db_session.commit()
    db_session.refresh(publication)

    db_session.add(
        FunnelPublicationPage(
            publication_id=publication.id,
            page_id=sales_page.id,
            page_version_id=version.id,
            slug_at_publish=sales_page.slug,
            title_at_publish=sales_page.name,
        )
    )
    funnel.entry_page_id = sales_page.id
    funnel.active_publication_id = publication.id
    funnel.status = FunnelStatusEnum.published
    db_session.add(funnel)
    db_session.commit()
    db_session.refresh(sales_page)
    return sales_page


def test_public_checkout_routes_shopify_provider(api_client, db_session, auth_context, monkeypatch):
    seeded = _seed_shopify_funnel(
        db_session=db_session,
        org_id=UUID(auth_context.org_id),
        with_selected_offer=True,
    )

    observed: dict[str, object] = {}

    def fake_create_shopify_checkout(**kwargs):
        observed.update(kwargs)
        return {
            "checkoutUrl": "https://example-shop.myshopify.com/cart/c/example-token",
            "cartId": "gid://shopify/Cart/example",
        }

    monkeypatch.setattr(public_funnels, "create_shopify_checkout", fake_create_shopify_checkout)

    response = api_client.post(
        "/public/checkout",
        json={
            "funnelSlug": seeded["funnel"].route_slug,
            "variantId": str(seeded["variant"].id),
            "selection": {},
            "quantity": 2,
            "successUrl": "https://funnel.example/success",
            "cancelUrl": "https://funnel.example/cancel",
            "pageId": None,
            "visitorId": "visitor_123",
            "sessionId": "session_123",
            "utm": {"source": "test"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["checkoutUrl"] == "https://example-shop.myshopify.com/cart/c/example-token"
    assert body["sessionId"] == "gid://shopify/Cart/example"

    assert observed["client_id"] == str(seeded["client"].id)
    assert observed["variant_gid"] == "gid://shopify/ProductVariant/123456789"
    assert observed["quantity"] == 2
    metadata = observed["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["funnel_slug"] == seeded["funnel"].route_slug
    assert metadata["funnel_id"] == str(seeded["funnel"].id)
    assert metadata["variant_id"] == str(seeded["variant"].id)
    assert metadata["offer_id"] == str(seeded["offer"].id)


def test_public_checkout_persists_checkout_started_event(
    api_client, db_session, auth_context, monkeypatch
):
    seeded = _seed_shopify_funnel(
        db_session=db_session,
        org_id=UUID(auth_context.org_id),
        with_selected_offer=True,
    )
    sales_page = _publish_sales_page(db_session=db_session, funnel=seeded["funnel"])

    def fake_create_shopify_checkout(**_kwargs):
        return {
            "checkoutUrl": "https://example-shop.myshopify.com/cart/c/example-token",
            "cartId": "gid://shopify/Cart/example",
        }

    monkeypatch.setattr(public_funnels, "create_shopify_checkout", fake_create_shopify_checkout)

    response = api_client.post(
        "/public/checkout",
        json={
            "funnelSlug": seeded["funnel"].route_slug,
            "variantId": str(seeded["variant"].id),
            "selection": {},
            "quantity": 1,
            "successUrl": "https://funnel.example/success",
            "cancelUrl": "https://funnel.example/cancel",
            "pageId": str(sales_page.id),
            "visitorId": "visitor_123",
            "sessionId": "session_123",
            "utm": {"source": "test"},
        },
    )

    assert response.status_code == 200

    event = db_session.scalars(
        select(FunnelEvent).where(
            FunnelEvent.funnel_id == seeded["funnel"].id,
            FunnelEvent.event_type == FunnelEventTypeEnum.checkout_started,
        )
    ).first()
    assert event is not None
    assert event.publication_id == seeded["funnel"].active_publication_id
    assert event.page_id == sales_page.id
    assert event.visitor_id == "visitor_123"
    assert event.session_id == "session_123"
    assert event.utm == {"source": "test"}
    assert event.props["provider"] == "shopify"
    assert event.props["checkout_session_id"] == "gid://shopify/Cart/example"
    assert event.props["variant_id"] == str(seeded["variant"].id)


def test_public_checkout_routes_shopify_provider_with_stale_formatting(
    api_client, db_session, auth_context, monkeypatch
):
    seeded = _seed_shopify_funnel(
        db_session=db_session,
        org_id=UUID(auth_context.org_id),
        with_selected_offer=True,
    )
    seeded["variant"].provider = " Shopify "
    seeded["variant"].external_price_id = " gid://shopify/ProductVariant/123456789 "
    db_session.add(seeded["variant"])
    db_session.commit()

    observed: dict[str, object] = {}

    def fake_create_shopify_checkout(**kwargs):
        observed.update(kwargs)
        return {
            "checkoutUrl": "https://example-shop.myshopify.com/cart/c/example-token",
            "cartId": "gid://shopify/Cart/example",
        }

    monkeypatch.setattr(public_funnels, "create_shopify_checkout", fake_create_shopify_checkout)

    response = api_client.post(
        "/public/checkout",
        json={
            "funnelSlug": seeded["funnel"].route_slug,
            "variantId": str(seeded["variant"].id),
            "selection": {},
            "quantity": 1,
            "successUrl": "https://funnel.example/success",
            "cancelUrl": "https://funnel.example/cancel",
            "pageId": None,
            "visitorId": "visitor_123",
            "sessionId": "session_123",
            "utm": {"source": "test"},
        },
    )

    assert response.status_code == 200
    assert observed["variant_gid"] == "gid://shopify/ProductVariant/123456789"


def test_public_checkout_medusa_provider_errors_cleanly(api_client, db_session, auth_context):
    seeded = _seed_shopify_funnel(
        db_session=db_session,
        org_id=UUID(auth_context.org_id),
        with_selected_offer=True,
    )
    seeded["variant"].provider = "medusa"
    seeded["variant"].external_price_id = "medusa_variant_123"
    db_session.add(seeded["variant"])
    db_session.commit()

    response = api_client.post(
        "/public/checkout",
        json={
            "funnelSlug": seeded["funnel"].route_slug,
            "variantId": str(seeded["variant"].id),
            "selection": {},
            "quantity": 1,
            "successUrl": "https://funnel.example/success",
            "cancelUrl": "https://funnel.example/cancel",
            "pageId": None,
            "visitorId": "visitor_123",
            "sessionId": "session_123",
            "utm": {"source": "test"},
        },
    )

    assert response.status_code == 501
    assert response.json()["detail"] == "Medusa checkout is not implemented yet."


def test_public_funnel_commerce_filters_to_selected_offer_variants(
    api_client, db_session, auth_context
):
    seeded = _seed_shopify_funnel(
        db_session=db_session,
        org_id=UUID(auth_context.org_id),
        with_selected_offer=True,
    )

    secondary_offer = ProductOffer(
        org_id=seeded["offer"].org_id,
        client_id=seeded["offer"].client_id,
        product_id=seeded["product"].id,
        name="Secondary Offer",
        business_model="one_time",
    )
    db_session.add(secondary_offer)
    db_session.commit()
    db_session.refresh(secondary_offer)

    secondary_variant = ProductVariant(
        product_id=seeded["product"].id,
        offer_id=secondary_offer.id,
        title="Other Offer Variant",
        price=4999,
        currency="USD",
        provider="shopify",
        external_price_id="gid://shopify/ProductVariant/999999999",
        option_values={"offerId": "other"},
    )
    db_session.add(secondary_variant)
    duplicate_unconfigured_variant = ProductVariant(
        product_id=seeded["product"].id,
        offer_id=seeded["offer"].id,
        title="Duplicate Unconfigured Variant",
        price=2999,
        currency="USD",
        provider=None,
        external_price_id=None,
        option_values=None,
    )
    db_session.add(duplicate_unconfigured_variant)
    db_session.commit()

    product_slug = str(seeded["product"].id).split("-", 1)[0]
    response = api_client.get(
        f"/public/funnels/{product_slug}/{seeded['funnel'].route_slug}/commerce"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["product"]["variants_count"] == 1
    assert payload["product"]["variants"][0]["id"] == str(seeded["variant"].id)


def test_public_checkout_selection_prefers_checkout_ready_variant(
    api_client, db_session, auth_context, monkeypatch
):
    seeded = _seed_shopify_funnel(
        db_session=db_session,
        org_id=UUID(auth_context.org_id),
        with_selected_offer=True,
    )
    seeded["variant"].option_values = {"offerId": "variant_a"}
    db_session.add(seeded["variant"])
    db_session.commit()

    duplicate_unconfigured_variant = ProductVariant(
        product_id=seeded["product"].id,
        offer_id=seeded["offer"].id,
        title="Duplicate Unconfigured Variant",
        price=2999,
        currency="USD",
        provider=None,
        external_price_id=None,
        option_values={"offerId": "variant_a"},
    )
    db_session.add(duplicate_unconfigured_variant)
    db_session.commit()

    observed: dict[str, object] = {}

    def fake_create_shopify_checkout(**kwargs):
        observed.update(kwargs)
        return {
            "checkoutUrl": "https://example-shop.myshopify.com/cart/c/example-token",
            "cartId": "gid://shopify/Cart/example",
        }

    monkeypatch.setattr(public_funnels, "create_shopify_checkout", fake_create_shopify_checkout)

    response = api_client.post(
        "/public/checkout",
        json={
            "funnelSlug": seeded["funnel"].route_slug,
            "selection": {"offerId": "variant_a"},
            "quantity": 1,
            "successUrl": "https://funnel.example/success",
            "cancelUrl": "https://funnel.example/cancel",
            "pageId": None,
            "visitorId": "visitor_123",
            "sessionId": "session_123",
            "utm": {"source": "test"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["checkoutUrl"] == "https://example-shop.myshopify.com/cart/c/example-token"
    assert observed["variant_gid"] == "gid://shopify/ProductVariant/123456789"


def test_shopify_orders_webhook_persists_funnel_order(
    api_client, db_session, auth_context, monkeypatch
):
    seeded = _seed_shopify_funnel(db_session=db_session, org_id=UUID(auth_context.org_id))
    monkeypatch.setattr(settings, "SHOPIFY_ORDER_WEBHOOK_SECRET", "test_shopify_secret")

    response = api_client.post(
        "/shopify/orders/webhook",
        headers={"x-marketi-webhook-secret": "test_shopify_secret"},
        json={
            "shopDomain": "example-shop.myshopify.com",
            "orderId": "987654321",
            "orderName": "#1001",
            "currency": "USD",
            "totalPrice": "49.95",
            "createdAt": "2026-02-12T10:00:00Z",
            "noteAttributes": {
                "funnel_id": str(seeded["funnel"].id),
                "price_point_id": str(seeded["variant"].id),
                "quantity": "1",
                "selection": '{"offerId":"base"}',
                "utm": '{"source":"test"}',
            },
            "lineItems": [
                {
                    "id": "1",
                    "variantId": "123456789",
                    "quantity": 1,
                    "title": "Shopify Product",
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {"received": True}

    saved = db_session.scalars(
        select(FunnelOrder).where(FunnelOrder.funnel_id == seeded["funnel"].id)
    ).all()
    assert len(saved) == 1
    assert saved[0].stripe_session_id == "shopify:example-shop.myshopify.com:987654321"
    assert saved[0].amount_cents == 4995
    assert saved[0].currency == "USD"
    assert saved[0].checkout_metadata["provider"] == "shopify"


def test_shopify_orders_webhook_sends_meta_purchase_when_tracking_is_active(
    api_client, db_session, auth_context, monkeypatch
):
    seeded = _seed_shopify_funnel(db_session=db_session, org_id=UUID(auth_context.org_id))
    meta_seed = _seed_active_meta_tracking(
        db_session=db_session,
        seeded=seeded,
        org_id=UUID(auth_context.org_id),
    )
    monkeypatch.setattr(settings, "SHOPIFY_ORDER_WEBHOOK_SECRET", "test_shopify_secret")

    observed: dict[str, object] = {}

    def fake_send_pixel_events(self, *, pixel_id: str, payload: dict[str, object]):
        observed["pixel_id"] = pixel_id
        observed["payload"] = payload
        return {"events_received": 1, "messages": []}

    monkeypatch.setattr(MetaAdsClient, "send_pixel_events", fake_send_pixel_events)

    response = api_client.post(
        "/shopify/orders/webhook",
        headers={"x-marketi-webhook-secret": "test_shopify_secret"},
        json={
            "shopDomain": "example-shop.myshopify.com",
            "orderId": "987654321",
            "orderName": "#1001",
            "email": "Buyer@example.com ",
            "phone": "+1 (312) 555-0100",
            "browserIp": "203.0.113.10",
            "userAgent": "Mozilla/5.0 Test Browser",
            "currency": "usd",
            "totalPrice": "49.95",
            "createdAt": "2026-02-12T10:00:00Z",
            "noteAttributes": {
                "funnel_id": str(seeded["funnel"].id),
                "variant_id": str(seeded["variant"].id),
                "quantity": "1",
                "session_id": "session_123",
                "visitor_id": "visitor_123",
                "selection": '{"offerId":"base"}',
                "utm": '{"source":"test"}',
            },
            "lineItems": [
                {
                    "id": "1",
                    "variantId": "123456789",
                    "quantity": 1,
                    "title": "Shopify Product",
                }
            ],
        },
    )

    assert response.status_code == 200
    assert observed["pixel_id"] == meta_seed["pixel_id"]
    meta_payload = observed["payload"]
    assert isinstance(meta_payload, dict)
    event = meta_payload["data"][0]
    assert event["event_name"] == "Purchase"
    assert event["action_source"] == "website"
    assert event["event_id"] == "shopify:example-shop.myshopify.com:987654321"
    assert event["custom_data"]["order_id"] == "987654321"
    assert event["custom_data"]["currency"] == "USD"
    assert event["custom_data"]["value"] == 49.95
    assert event["custom_data"]["content_ids"] == [str(seeded["variant"].id)]
    assert event["user_data"]["em"] == [
        hashlib.sha256("buyer@example.com".encode("utf-8")).hexdigest()
    ]
    assert event["user_data"]["ph"] == [hashlib.sha256("13125550100".encode("utf-8")).hexdigest()]
    assert event["user_data"]["external_id"] == [
        hashlib.sha256("session_123".encode("utf-8")).hexdigest()
    ]
    assert event["user_data"]["client_ip_address"] == "203.0.113.10"
    assert event["user_data"]["client_user_agent"] == "Mozilla/5.0 Test Browser"

    saved = db_session.scalars(
        select(FunnelOrder).where(FunnelOrder.funnel_id == seeded["funnel"].id)
    ).all()
    assert len(saved) == 1
    assert (
        saved[0].checkout_metadata["meta_conversion"]["eventId"]
        == "shopify:example-shop.myshopify.com:987654321"
    )
    assert saved[0].checkout_metadata["meta_conversion"]["pixelId"] == meta_seed["pixel_id"]


def test_shopify_orders_webhook_returns_retryable_error_when_meta_send_fails(
    api_client, db_session, auth_context, monkeypatch
):
    seeded = _seed_shopify_funnel(db_session=db_session, org_id=UUID(auth_context.org_id))
    _seed_active_meta_tracking(
        db_session=db_session,
        seeded=seeded,
        org_id=UUID(auth_context.org_id),
    )
    monkeypatch.setattr(settings, "SHOPIFY_ORDER_WEBHOOK_SECRET", "test_shopify_secret")

    def fake_send_pixel_events(self, *, pixel_id: str, payload: dict[str, object]):
        raise MetaAdsError("Meta Graph API error (500).")

    monkeypatch.setattr(MetaAdsClient, "send_pixel_events", fake_send_pixel_events)

    response = api_client.post(
        "/shopify/orders/webhook",
        headers={"x-marketi-webhook-secret": "test_shopify_secret"},
        json={
            "shopDomain": "example-shop.myshopify.com",
            "orderId": "987654321",
            "orderName": "#1001",
            "currency": "USD",
            "totalPrice": "49.95",
            "createdAt": "2026-02-12T10:00:00Z",
            "noteAttributes": {
                "funnel_id": str(seeded["funnel"].id),
                "variant_id": str(seeded["variant"].id),
                "quantity": "1",
                "session_id": "session_123",
                "selection": '{"offerId":"base"}',
                "utm": '{"source":"test"}',
            },
            "lineItems": [
                {
                    "id": "1",
                    "variantId": "123456789",
                    "quantity": 1,
                    "title": "Shopify Product",
                }
            ],
        },
    )

    assert response.status_code == 502
    assert "Meta Purchase conversion send failed" in response.text

    saved = db_session.scalars(
        select(FunnelOrder).where(FunnelOrder.funnel_id == seeded["funnel"].id)
    ).all()
    assert saved == []
