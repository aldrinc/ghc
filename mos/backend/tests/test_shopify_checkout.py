from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select

from app.config import settings
from app.db.models import Client, Funnel, FunnelOrder, Product, ProductOffer, ProductOfferPricePoint
from app.routers import public_funnels


def _seed_shopify_funnel(*, db_session, org_id: UUID):
    client = Client(org_id=org_id, name="Shopify Client", industry="Retail")
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)

    product = Product(org_id=org_id, client_id=client.id, name="Shopify Product")
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    offer = ProductOffer(
        org_id=org_id,
        client_id=client.id,
        product_id=product.id,
        name="Default Offer",
        business_model="one_time",
    )
    db_session.add(offer)
    db_session.commit()
    db_session.refresh(offer)

    price_point = ProductOfferPricePoint(
        offer_id=offer.id,
        label="Default",
        amount_cents=2999,
        currency="USD",
        provider="shopify",
        external_price_id="gid://shopify/ProductVariant/123456789",
        option_values={"offerId": "base"},
    )
    db_session.add(price_point)
    db_session.commit()
    db_session.refresh(price_point)

    funnel = Funnel(
        org_id=org_id,
        client_id=client.id,
        product_id=product.id,
        selected_offer_id=offer.id,
        name="Shopify Funnel",
        public_id=uuid4(),
    )
    db_session.add(funnel)
    db_session.commit()
    db_session.refresh(funnel)

    return {
        "client": client,
        "product": product,
        "offer": offer,
        "price_point": price_point,
        "funnel": funnel,
    }


def test_public_checkout_routes_shopify_provider(api_client, db_session, auth_context, monkeypatch):
    seeded = _seed_shopify_funnel(db_session=db_session, org_id=UUID(auth_context.org_id))

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
            "offerId": str(seeded["offer"].id),
            "pricePointId": str(seeded["price_point"].id),
            "selection": {"offerId": "base"},
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
    assert metadata["offer_id"] == str(seeded["offer"].id)


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
                "offer_id": str(seeded["offer"].id),
                "price_point_id": str(seeded["price_point"].id),
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
