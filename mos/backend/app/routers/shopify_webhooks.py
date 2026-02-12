from __future__ import annotations

import hmac
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.deps import get_session
from app.db.enums import FunnelEventTypeEnum
from app.db.models import Funnel, FunnelEvent, FunnelOrder
from app.schemas.shopify import ShopifyOrderWebhookPayload

router = APIRouter(prefix="/shopify", tags=["shopify"])


def _parse_metadata_json(value: str | None, label: str) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON in noteAttributes[{label}]",
        ) from exc
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"noteAttributes[{label}] must be a JSON object.",
        )
    return parsed


def _parse_required_uuid(value: str | None, label: str) -> str:
    if not value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required note attribute: {label}",
        )
    try:
        return str(UUID(str(value)))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} must be a valid UUID.",
        ) from exc


def _parse_optional_uuid(value: str | None, label: str) -> str | None:
    if not value:
        return None
    try:
        return str(UUID(str(value)))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} must be a valid UUID.",
        ) from exc


def _parse_quantity(value: str | None) -> int:
    if not value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required note attribute: quantity",
        )
    try:
        quantity = int(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="noteAttributes[quantity] must be an integer.",
        ) from exc
    if quantity < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="noteAttributes[quantity] must be >= 1.",
        )
    return quantity


def _price_to_cents(total_price: str | None) -> int | None:
    if total_price is None:
        return None
    try:
        amount = Decimal(total_price)
    except InvalidOperation as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="totalPrice must be a valid decimal string.",
        ) from exc
    cents = (amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


@router.post("/orders/webhook")
def ingest_shopify_order_webhook(
    payload: ShopifyOrderWebhookPayload,
    request: Request,
    session: Session = Depends(get_session),
):
    if not settings.SHOPIFY_ORDER_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Shopify order webhook secret is not configured.",
        )

    provided_secret = request.headers.get("x-marketi-webhook-secret", "")
    if not hmac.compare_digest(provided_secret, settings.SHOPIFY_ORDER_WEBHOOK_SECRET):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Shopify webhook secret.",
        )

    funnel_id = _parse_required_uuid(payload.noteAttributes.get("funnel_id"), "funnel_id")
    offer_id = _parse_optional_uuid(payload.noteAttributes.get("offer_id"), "offer_id")
    price_point_id = _parse_optional_uuid(payload.noteAttributes.get("price_point_id"), "price_point_id")
    page_id = _parse_optional_uuid(payload.noteAttributes.get("page_id"), "page_id")
    visitor_id = payload.noteAttributes.get("visitor_id") or None
    session_id = payload.noteAttributes.get("session_id") or None
    selection = _parse_metadata_json(payload.noteAttributes.get("selection"), "selection")
    utm = _parse_metadata_json(payload.noteAttributes.get("utm"), "utm")
    quantity = _parse_quantity(payload.noteAttributes.get("quantity"))

    funnel = session.scalars(select(Funnel).where(Funnel.id == funnel_id)).first()
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found for webhook.")

    external_order_ref = f"shopify:{payload.shopDomain}:{payload.orderId}"
    existing = session.scalars(
        select(FunnelOrder).where(FunnelOrder.stripe_session_id == external_order_ref)
    ).first()
    if existing:
        return {"received": True, "duplicate": True}

    order = FunnelOrder(
        org_id=funnel.org_id,
        client_id=funnel.client_id,
        funnel_id=funnel.id,
        publication_id=funnel.active_publication_id,
        page_id=page_id,
        offer_id=offer_id,
        price_point_id=price_point_id,
        stripe_session_id=external_order_ref,
        stripe_payment_intent_id=None,
        amount_cents=_price_to_cents(payload.totalPrice),
        currency=payload.currency,
        quantity=quantity,
        selection=selection or None,
        checkout_metadata={
            "provider": "shopify",
            "shop_domain": payload.shopDomain,
            "shopify_order_id": payload.orderId,
            "shopify_order_name": payload.orderName,
            "note_attributes": payload.noteAttributes,
            "line_items": [item.model_dump(exclude_none=True) for item in payload.lineItems],
        },
        status="completed",
        fulfillment_status="pending",
    )
    session.add(order)

    if funnel.active_publication_id and page_id:
        session.add(
            FunnelEvent(
                occurred_at=datetime.now(timezone.utc),
                org_id=funnel.org_id,
                client_id=funnel.client_id,
                campaign_id=funnel.campaign_id,
                funnel_id=funnel.id,
                publication_id=funnel.active_publication_id,
                page_id=page_id,
                event_type=FunnelEventTypeEnum.order_completed,
                visitor_id=visitor_id,
                session_id=session_id,
                host=None,
                path=None,
                referrer=None,
                utm=utm,
                props={
                    "provider": "shopify",
                    "shop_domain": payload.shopDomain,
                    "shopify_order_id": payload.orderId,
                    "shopify_order_name": payload.orderName,
                    "amount_cents": _price_to_cents(payload.totalPrice),
                    "currency": payload.currency,
                },
            )
        )

    session.commit()
    return {"received": True}
