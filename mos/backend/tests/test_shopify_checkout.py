from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select

from app.config import settings
from app.db.models import Client, Funnel, FunnelOrder, Product, ProductOffer, ProductVariant
from app.routers import public_funnels


def _seed_shopify_funnel(*, db_session, org_id: UUID, with_selected_offer: bool = False):
    client = Client(org_id=org_id, name="Shopify Client", industry="Retail")
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)

    product = Product(org_id=org_id, client_id=client.id, title="Shopify Product")
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
        public_id=uuid4(),
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
            "publicId": str(seeded["funnel"].public_id),
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
    assert metadata["funnel_id"] == str(seeded["funnel"].id)
    assert metadata["variant_id"] == str(seeded["variant"].id)
    assert metadata["offer_id"] == str(seeded["offer"].id)


def test_public_funnel_commerce_filters_to_selected_offer_variants(api_client, db_session, auth_context):
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
    db_session.commit()

    response = api_client.get(f"/public/funnels/{seeded['funnel'].public_id}/commerce")
    assert response.status_code == 200
    payload = response.json()
    assert payload["product"]["variants_count"] == 1
    assert payload["product"]["variants"][0]["id"] == str(seeded["variant"].id)


def test_shopify_orders_webhook_persists_funnel_order(api_client, db_session, auth_context, monkeypatch):
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
