from __future__ import annotations

import json
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.deps import get_session
from app.db.enums import FunnelEventTypeEnum
from app.db.models import Funnel, FunnelEvent, FunnelOrder

router = APIRouter(prefix="/stripe", tags=["stripe"])


def _require_metadata(metadata: dict[str, str] | None, key: str) -> str:
    if not metadata or not metadata.get(key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required metadata: {key}",
        )
    return metadata[key]


def _parse_metadata_json(value: str | None, label: str) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON in metadata: {label}",
        ) from exc
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Metadata {label} must be a JSON object.",
        )
    return parsed


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    session: Session = Depends(get_session),
):
    webhook_secret = settings.STRIPE_WEBHOOK_SECRET
    if not webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stripe webhook secret is not configured.",
        )

    signature = request.headers.get("stripe-signature")
    if not signature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Stripe signature header.")

    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(payload, signature, webhook_secret)
    except stripe.error.SignatureVerificationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe signature.") from exc

    if event.get("type") != "checkout.session.completed":
        return {"received": True}

    data = event.get("data", {})
    session_obj = data.get("object") if isinstance(data, dict) else None
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Stripe session payload.")

    stripe_session_id = session_obj.get("id")
    if not stripe_session_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Stripe session ID.")

    existing = session.scalars(
        select(FunnelOrder).where(FunnelOrder.stripe_session_id == stripe_session_id)
    ).first()
    if existing:
        return {"received": True}

    metadata = session_obj.get("metadata") or {}
    funnel_id = _require_metadata(metadata, "funnel_id")
    # New schema uses variant_id; keep price_point_id as a legacy alias.
    variant_id = metadata.get("variant_id") or metadata.get("price_point_id")
    if not variant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required metadata: variant_id",
        )
    offer_id = metadata.get("offer_id") or None

    funnel = session.scalars(select(Funnel).where(Funnel.id == funnel_id)).first()
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found for webhook.")

    publication_id = funnel.active_publication_id
    page_id = metadata.get("page_id") or None
    visitor_id = metadata.get("visitor_id") or None
    session_id = metadata.get("session_id") or None
    selection = _parse_metadata_json(metadata.get("selection"), "selection")
    utm = _parse_metadata_json(metadata.get("utm"), "utm")
    quantity_raw = metadata.get("quantity")
    quantity = 1
    if quantity_raw:
        try:
            quantity = int(quantity_raw)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid quantity in metadata.",
            ) from exc

    amount_total = session_obj.get("amount_total")
    currency = session_obj.get("currency")
    payment_intent = session_obj.get("payment_intent")

    order = FunnelOrder(
        org_id=funnel.org_id,
        client_id=funnel.client_id,
        funnel_id=funnel.id,
        publication_id=publication_id,
        page_id=page_id,
        offer_id=offer_id,
        price_point_id=variant_id,
        stripe_session_id=stripe_session_id,
        stripe_payment_intent_id=payment_intent,
        amount_cents=amount_total,
        currency=currency,
        quantity=quantity,
        selection=selection or None,
        checkout_metadata=metadata,
        status="completed",
        fulfillment_status="pending",
    )
    session.add(order)

    if publication_id and page_id:
        session.add(
            FunnelEvent(
                occurred_at=datetime.now(timezone.utc),
                org_id=funnel.org_id,
                client_id=funnel.client_id,
                campaign_id=funnel.campaign_id,
                funnel_id=funnel.id,
                publication_id=publication_id,
                page_id=page_id,
                event_type=FunnelEventTypeEnum.order_completed,
                visitor_id=visitor_id,
                session_id=session_id,
                host=None,
                path=None,
                referrer=None,
                utm=utm,
                props={
                    "stripe_session_id": stripe_session_id,
                    "payment_intent": payment_intent,
                    "amount_cents": amount_total,
                    "currency": currency,
                },
            )
        )

    session.commit()
    return {"received": True}
