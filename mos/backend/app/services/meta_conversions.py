from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models import Funnel
from app.db.repositories.paid_ads_qa import PaidAdsQaRepository
from app.schemas.shopify import ShopifyOrderWebhookPayload
from app.services.meta_account_configs import (
    MetaWorkspaceConfigError,
    meta_ads_client_for_connection,
    resolve_workspace_config,
)
from app.services.meta_ads import MetaAdsClient, MetaAdsError
from app.services.paid_ads_qa import clean_optional_text, normalize_tracking_provider

_MOS_META_TRACKING_METADATA_KEY = "mosMetaTracking"
_NON_DIGIT_RE = re.compile(r"\D+")


class MetaConversionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResolvedMetaPixelTracking:
    pixel_id: str
    client: MetaAdsClient


def _normalize_email(value: str | None) -> str | None:
    cleaned = clean_optional_text(value)
    return cleaned.lower() if cleaned else None


def _normalize_phone(value: str | None) -> str | None:
    cleaned = clean_optional_text(value)
    if not cleaned:
        return None
    digits = _NON_DIGIT_RE.sub("", cleaned)
    return digits or None


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _event_time(created_at: str | None) -> int:
    cleaned = clean_optional_text(created_at)
    if not cleaned:
        return int(datetime.now(timezone.utc).timestamp())
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MetaConversionError(
            "Shopify order payload createdAt must be an ISO-8601 timestamp."
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def resolve_active_meta_pixel_tracking(
    *,
    session: Session,
    funnel: Funnel,
) -> ResolvedMetaPixelTracking | None:
    profile = PaidAdsQaRepository(session).get_platform_profile(
        org_id=str(funnel.org_id),
        client_id=str(funnel.client_id),
        platform="meta",
    )
    if profile is None:
        return None
    metadata = profile.metadata_json if isinstance(profile.metadata_json, dict) else {}
    mos_tracking = metadata.get(_MOS_META_TRACKING_METADATA_KEY)
    if not isinstance(mos_tracking, dict):
        return None
    if normalize_tracking_provider(mos_tracking.get("status")) != "active":
        return None
    if normalize_tracking_provider(mos_tracking.get("mode")) != "public_funnel_runtime":
        return None
    if normalize_tracking_provider(mos_tracking.get("channel")) != "meta":
        return None

    pixel_id = clean_optional_text(mos_tracking.get("pixelId")) or clean_optional_text(
        profile.pixel_id
    )
    if not pixel_id:
        raise MetaConversionError("Active Meta funnel tracking is missing a pixel ID.")

    try:
        resolved = resolve_workspace_config(
            session=session,
            org_id=str(funnel.org_id),
            client_id=str(funnel.client_id),
        )
    except MetaWorkspaceConfigError as exc:
        raise MetaConversionError(
            "Active Meta funnel tracking is configured, but the default Meta workspace config "
            "could not be resolved."
        ) from exc

    config_pixel_id = clean_optional_text(resolved.workspace_config.pixel_id)
    if config_pixel_id and config_pixel_id != pixel_id:
        raise MetaConversionError(
            "Active Meta funnel tracking pixel does not match the default Meta workspace "
            "config pixel."
        )

    return ResolvedMetaPixelTracking(
        pixel_id=pixel_id,
        client=meta_ads_client_for_connection(resolved.connection),
    )


def _build_user_data(
    *,
    payload: ShopifyOrderWebhookPayload,
    session_id: str | None,
    visitor_id: str | None,
    external_order_ref: str,
) -> dict[str, object]:
    user_data: dict[str, object] = {}

    normalized_email = _normalize_email(payload.email)
    if normalized_email:
        user_data["em"] = [_sha256_hex(normalized_email)]

    normalized_phone = _normalize_phone(payload.phone)
    if normalized_phone:
        user_data["ph"] = [_sha256_hex(normalized_phone)]

    external_id_source = (
        clean_optional_text(session_id) or clean_optional_text(visitor_id) or external_order_ref
    )
    if external_id_source:
        user_data["external_id"] = [_sha256_hex(external_id_source)]

    browser_ip = clean_optional_text(payload.browserIp)
    if browser_ip:
        user_data["client_ip_address"] = browser_ip

    user_agent = clean_optional_text(payload.userAgent)
    if user_agent:
        user_data["client_user_agent"] = user_agent

    fbp = clean_optional_text(payload.noteAttributes.get("fbp"))
    if fbp:
        user_data["fbp"] = fbp

    fbc = clean_optional_text(payload.noteAttributes.get("fbc"))
    if fbc:
        user_data["fbc"] = fbc

    return user_data


def _build_custom_data(
    *,
    payload: ShopifyOrderWebhookPayload,
    amount_cents: int | None,
    currency: str | None,
    quantity: int,
    variant_id: str | None,
) -> dict[str, object]:
    custom_data: dict[str, object] = {"order_id": payload.orderId}

    normalized_currency = clean_optional_text(currency)
    if amount_cents is not None and normalized_currency:
        value = (Decimal(amount_cents) / Decimal("100")).quantize(Decimal("0.01"))
        custom_data["value"] = float(value)
        custom_data["currency"] = normalized_currency.upper()

    cleaned_variant_id = clean_optional_text(variant_id)
    if cleaned_variant_id:
        custom_data["content_ids"] = [cleaned_variant_id]
        item: dict[str, object] = {"id": cleaned_variant_id, "quantity": quantity}
        if amount_cents is not None and quantity > 0:
            item_price = (Decimal(amount_cents) / Decimal("100") / Decimal(quantity)).quantize(
                Decimal("0.01")
            )
            item["item_price"] = float(item_price)
        custom_data["contents"] = [item]
        custom_data["content_type"] = "product"

    return custom_data


def send_shopify_purchase_event(
    *,
    session: Session,
    funnel: Funnel,
    payload: ShopifyOrderWebhookPayload,
    external_order_ref: str,
    amount_cents: int | None,
    currency: str | None,
    quantity: int,
    variant_id: str | None,
    session_id: str | None,
    visitor_id: str | None,
) -> dict[str, object] | None:
    tracking = resolve_active_meta_pixel_tracking(session=session, funnel=funnel)
    if tracking is None:
        return None

    user_data = _build_user_data(
        payload=payload,
        session_id=session_id,
        visitor_id=visitor_id,
        external_order_ref=external_order_ref,
    )
    event_id = external_order_ref
    event_source_url = clean_optional_text(payload.noteAttributes.get("event_source_url"))
    event_payload = {
        "data": [
            {
                "event_name": "Purchase",
                "event_time": _event_time(payload.createdAt),
                "action_source": "website",
                "event_id": event_id,
                **({"event_source_url": event_source_url} if event_source_url else {}),
                "user_data": user_data,
                "custom_data": _build_custom_data(
                    payload=payload,
                    amount_cents=amount_cents,
                    currency=currency,
                    quantity=quantity,
                    variant_id=variant_id,
                ),
            }
        ]
    }

    try:
        response = tracking.client.send_pixel_events(
            pixel_id=tracking.pixel_id,
            payload=event_payload,
        )
    except MetaAdsError as exc:
        detail = str(exc)
        raise MetaConversionError(f"Meta Purchase conversion send failed: {detail}") from exc

    return {
        "provider": "meta",
        "eventId": event_id,
        "pixelId": tracking.pixel_id,
        "response": response,
    }
