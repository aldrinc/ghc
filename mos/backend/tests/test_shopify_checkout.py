from __future__ import annotations

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
    PreparedFunnelCheckout,
    Product,
    ProductOffer,
    ProductVariant,
)
from app.routers import public_funnels
from app.services.integration_secrets import encrypt_secret_json


def _seed_shopify_funnel(
    *,
    db_session,
    org_id: UUID,
    with_selected_offer: bool = False,
    shopify_selling_plan_id: str | None = None,
):
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
        shopify_selling_plan_id=shopify_selling_plan_id,
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
            "clickId": "fb-click-123",
            "clickIdType": "fbclid",
            "fbp": "fb.1.1710000000.browser",
            "fbc": "fb.1.1710000001.fb-click-123",
            "eventSourceUrl": "https://funnel.example/sales?utm_source=meta&fbclid=fb-click-123",
            "transitionId": "checkout-transition-123",
            "mosMetaAddToCartEventId": "mos-meta-atc-123",
            "mosMetaInitiateCheckoutEventId": "checkout_started:checkout-transition-123",
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
    assert metadata["click_id"] == "fb-click-123"
    assert metadata["click_id_type"] == "fbclid"
    assert metadata["fbp"] == "fb.1.1710000000.browser"
    assert metadata["fbc"] == "fb.1.1710000001.fb-click-123"
    assert metadata["event_source_url"] == "https://funnel.example/sales?utm_source=meta&fbclid=fb-click-123"
    assert metadata["transition_id"] == "checkout-transition-123"
    assert metadata["mos_meta_add_to_cart_event_id"] == "mos-meta-atc-123"
    assert metadata["mos_meta_initiate_checkout_event_id"] == "checkout_started:checkout-transition-123"
    assert "url_params" not in metadata


def test_public_checkout_explicit_variant_can_use_variant_specific_offer(
    api_client, db_session, auth_context, monkeypatch
):
    seeded = _seed_shopify_funnel(
        db_session=db_session,
        org_id=UUID(auth_context.org_id),
        with_selected_offer=True,
    )
    alternate_offer = ProductOffer(
        org_id=UUID(auth_context.org_id),
        client_id=seeded["client"].id,
        product_id=seeded["product"].id,
        name="Alternate Offer",
        business_model="subscription",
    )
    db_session.add(alternate_offer)
    db_session.commit()
    db_session.refresh(alternate_offer)

    alternate_variant = ProductVariant(
        product_id=seeded["product"].id,
        offer_id=alternate_offer.id,
        title="Alternate",
        price=1999,
        currency="USD",
        provider="shopify",
        external_price_id="gid://shopify/ProductVariant/987654321",
        option_values=None,
    )
    db_session.add(alternate_variant)
    db_session.commit()
    db_session.refresh(alternate_variant)

    observed: dict[str, object] = {}

    def fake_create_shopify_checkout(**kwargs):
        observed.update(kwargs)
        return {
            "checkoutUrl": "https://example-shop.myshopify.com/cart/c/alternate-token",
            "cartId": "gid://shopify/Cart/alternate",
        }

    monkeypatch.setattr(public_funnels, "create_shopify_checkout", fake_create_shopify_checkout)

    response = api_client.post(
        "/public/checkout",
        json={
            "funnelSlug": seeded["funnel"].route_slug,
            "variantId": str(alternate_variant.id),
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
    assert observed["variant_gid"] == "gid://shopify/ProductVariant/987654321"
    metadata = observed["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["offer_id"] == str(alternate_offer.id)


def test_public_checkout_routes_shopify_subscription_by_purchase_mode(
    api_client, db_session, auth_context, monkeypatch
):
    seeded = _seed_shopify_funnel(
        db_session=db_session,
        org_id=UUID(auth_context.org_id),
        with_selected_offer=True,
        shopify_selling_plan_id="gid://shopify/SellingPlan/222",
    )
    seeded["variant"].option_values = {"Pack": "2x"}
    db_session.add(seeded["variant"])
    db_session.commit()

    observed: dict[str, object] = {}

    def fake_create_shopify_checkout(**kwargs):
        observed.update(kwargs)
        return {
            "checkoutUrl": "https://example-shop.myshopify.com/cart/c/subscription-token",
            "cartId": "gid://shopify/Cart/subscription",
        }

    monkeypatch.setattr(public_funnels, "create_shopify_checkout", fake_create_shopify_checkout)

    response = api_client.post(
        "/public/checkout",
        json={
            "funnelSlug": seeded["funnel"].route_slug,
            "selection": {"Pack": "2x", "PurchaseMode": "subscribe"},
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
    assert observed["selling_plan_id"] == "gid://shopify/SellingPlan/222"
    metadata = observed["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["purchase_mode"] == "subscribe"


def test_public_checkout_rejects_subscribe_when_selling_plan_is_missing(
    api_client, db_session, auth_context
):
    seeded = _seed_shopify_funnel(
        db_session=db_session,
        org_id=UUID(auth_context.org_id),
        with_selected_offer=True,
    )
    seeded["variant"].option_values = {"Pack": "2x"}
    db_session.add(seeded["variant"])
    db_session.commit()

    response = api_client.post(
        "/public/checkout",
        json={
            "funnelSlug": seeded["funnel"].route_slug,
            "selection": {"Pack": "2x", "PurchaseMode": "subscribe"},
            "quantity": 1,
            "successUrl": "https://funnel.example/success",
            "cancelUrl": "https://funnel.example/cancel",
            "pageId": None,
            "visitorId": "visitor_123",
            "sessionId": "session_123",
            "utm": {"source": "test"},
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Subscribe & save is not configured for this selection."


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
            "transitionId": "checkout-transition-123",
            "mosMetaAddToCartEventId": "mos-meta-atc-123",
            "mosMetaInitiateCheckoutEventId": "checkout_started:checkout-transition-123",
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
    assert event.props["transition_id"] == "checkout-transition-123"
    assert event.props["mos_meta_add_to_cart_event_id"] == "mos-meta-atc-123"
    assert event.props["mos_meta_initiate_checkout_event_id"] == "checkout_started:checkout-transition-123"


def test_prepared_public_checkout_reuses_prepared_cart_and_tracks_on_consume(
    api_client, db_session, auth_context, monkeypatch
):
    seeded = _seed_shopify_funnel(
        db_session=db_session,
        org_id=UUID(auth_context.org_id),
        with_selected_offer=True,
    )
    sales_page = _publish_sales_page(db_session=db_session, funnel=seeded["funnel"])

    observed: list[dict[str, object]] = []

    def fake_create_shopify_checkout(**kwargs):
        observed.append(kwargs)
        return {
            "checkoutUrl": "https://example-shop.myshopify.com/cart/c/prepared-token",
            "cartId": "gid://shopify/Cart/prepared",
        }

    monkeypatch.setattr(public_funnels, "create_shopify_checkout", fake_create_shopify_checkout)

    payload = {
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
        "transitionId": "checkout-transition-prepared-123",
        "mosMetaAddToCartEventId": "mos-meta-atc-prepared-123",
        "mosMetaInitiateCheckoutEventId": "checkout_started:checkout-transition-prepared-123",
    }

    prepare_response = api_client.post("/public/checkout/prepare", json=payload)
    assert prepare_response.status_code == 200
    prepared_payload = prepare_response.json()
    prepared_id = prepared_payload["preparedCheckoutId"]

    status_response = api_client.get(f"/public/checkout/prepare/{prepared_id}")
    assert status_response.status_code == 200
    prepared_status = status_response.json()
    assert prepared_status["status"] == "ready"

    prepared_record = db_session.get(PreparedFunnelCheckout, UUID(prepared_id))
    assert prepared_record is not None
    assert prepared_record.checkout_url == "https://example-shop.myshopify.com/cart/c/prepared-token"
    assert prepared_record.checkout_session_id == "gid://shopify/Cart/prepared"
    assert prepared_record.consumed_at is None
    assert len(observed) == 1
    assert observed[0]["metadata"]["mos_meta_add_to_cart_event_id"] == "mos-meta-atc-prepared-123"
    assert (
        observed[0]["metadata"]["mos_meta_initiate_checkout_event_id"]
        == "checkout_started:checkout-transition-prepared-123"
    )

    existing_event = db_session.scalars(
        select(FunnelEvent).where(
            FunnelEvent.funnel_id == seeded["funnel"].id,
            FunnelEvent.event_type == FunnelEventTypeEnum.checkout_started,
        )
    ).first()
    assert existing_event is None

    second_prepare_response = api_client.post("/public/checkout/prepare", json=payload)
    assert second_prepare_response.status_code == 200
    assert second_prepare_response.json()["preparedCheckoutId"] == prepared_id
    assert len(observed) == 1

    consume_response = api_client.post(f"/public/checkout/prepare/{prepared_id}/consume")
    assert consume_response.status_code == 200
    assert consume_response.json() == {
        "checkoutUrl": "https://example-shop.myshopify.com/cart/c/prepared-token",
        "sessionId": "gid://shopify/Cart/prepared",
    }

    db_session.expire_all()
    consumed_record = db_session.get(PreparedFunnelCheckout, UUID(prepared_id))
    assert consumed_record is not None
    assert consumed_record.consumed_at is not None

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
    assert event.props["provider"] == "shopify"
    assert event.props["checkout_session_id"] == "gid://shopify/Cart/prepared"
    assert event.props["variant_id"] == str(seeded["variant"].id)
    assert event.props["transition_id"] == "checkout-transition-prepared-123"
    assert event.props["mos_meta_add_to_cart_event_id"] == "mos-meta-atc-prepared-123"
    assert (
        event.props["mos_meta_initiate_checkout_event_id"]
        == "checkout_started:checkout-transition-prepared-123"
    )


def test_prepared_public_checkout_routes_shopify_subscription_by_purchase_mode(
    api_client, db_session, auth_context, monkeypatch
):
    seeded = _seed_shopify_funnel(
        db_session=db_session,
        org_id=UUID(auth_context.org_id),
        with_selected_offer=True,
        shopify_selling_plan_id="gid://shopify/SellingPlan/333",
    )
    seeded["variant"].option_values = {"Pack": "3x"}
    db_session.add(seeded["variant"])
    db_session.commit()
    sales_page = _publish_sales_page(db_session=db_session, funnel=seeded["funnel"])

    observed: list[dict[str, object]] = []

    def fake_create_shopify_checkout(**kwargs):
        observed.append(kwargs)
        return {
            "checkoutUrl": "https://example-shop.myshopify.com/cart/c/prepared-subscription-token",
            "cartId": "gid://shopify/Cart/prepared-subscription",
        }

    monkeypatch.setattr(public_funnels, "create_shopify_checkout", fake_create_shopify_checkout)

    response = api_client.post(
        "/public/checkout/prepare",
        json={
            "funnelSlug": seeded["funnel"].route_slug,
            "selection": {"Pack": "3x", "PurchaseMode": "subscribe"},
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
    prepared_id = response.json()["preparedCheckoutId"]
    status_response = api_client.get(f"/public/checkout/prepare/{prepared_id}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "ready"
    assert len(observed) == 1
    assert observed[0]["selling_plan_id"] == "gid://shopify/SellingPlan/333"


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


def test_shopify_orders_webhook_records_order_without_mos_meta_purchase_send(
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

    saved = db_session.scalars(
        select(FunnelOrder).where(FunnelOrder.funnel_id == seeded["funnel"].id)
    ).all()
    assert len(saved) == 1
    assert "meta_conversion" not in saved[0].checkout_metadata
