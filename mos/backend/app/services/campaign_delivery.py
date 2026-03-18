from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import ipaddress
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.db.enums import CampaignDeliveryModeEnum, CampaignDeliveryValidationStatusEnum
from app.db.models import CampaignDeliveryConfig
from app.services.paid_ads_qa import _CONTACT_RE, _MAILTO_RE, _PHONE_RE, _PRIVACY_RE, _UNDER_CONSTRUCTION_RE

_HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_HTTP_HEADERS = {"User-Agent": "MOS-CampaignDeliveryValidation/1.0"}
_PUBLIC_HOST_BLOCKLIST_SUFFIXES = (".local", ".internal")


class CampaignDeliveryConfigError(ValueError):
    pass


class CampaignDeliveryValidationError(RuntimeError):
    def __init__(self, message: str, *, results: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.results = results


@dataclass(frozen=True)
class NormalizedCampaignDelivery:
    delivery_mode: CampaignDeliveryModeEnum
    pre_sales_url: str | None
    sales_url: str | None
    checkout_url: str | None
    thank_you_url: str | None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _assert_public_hostname(hostname: str, *, field_name: str) -> None:
    lowered = hostname.strip().lower()
    if not lowered:
        raise CampaignDeliveryConfigError(f"{field_name} must include a public hostname.")
    if lowered == "localhost" or lowered.endswith(_PUBLIC_HOST_BLOCKLIST_SUFFIXES):
        raise CampaignDeliveryConfigError(f"{field_name} must use a public hostname; '{hostname}' is not allowed.")
    try:
        address = ipaddress.ip_address(lowered)
    except ValueError:
        if "." not in lowered:
            raise CampaignDeliveryConfigError(f"{field_name} must use a public hostname; '{hostname}' is not allowed.")
        return
    if not address.is_global:
        raise CampaignDeliveryConfigError(f"{field_name} must use a public IP address; '{hostname}' is not allowed.")


def normalize_public_http_url(raw: str | None, *, field_name: str, required: bool) -> str | None:
    cleaned = _clean_optional_text(raw)
    if not cleaned:
        if required:
            raise CampaignDeliveryConfigError(f"{field_name} is required.")
        return None

    parsed = urlsplit(cleaned)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise CampaignDeliveryConfigError(f"{field_name} must be an absolute public http or https URL.")
    if parsed.username or parsed.password:
        raise CampaignDeliveryConfigError(f"{field_name} must not include embedded credentials.")

    hostname = parsed.hostname or ""
    _assert_public_hostname(hostname, field_name=field_name)

    path = parsed.path or "/"
    normalized = urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            parsed.query,
            "",
        )
    )
    return normalized


def normalize_delivery_payload(
    *,
    delivery_mode: CampaignDeliveryModeEnum,
    pre_sales_url: str | None,
    sales_url: str | None,
    checkout_url: str | None,
    thank_you_url: str | None,
) -> NormalizedCampaignDelivery:
    if delivery_mode == CampaignDeliveryModeEnum.internal_funnel:
        return NormalizedCampaignDelivery(
            delivery_mode=delivery_mode,
            pre_sales_url=None,
            sales_url=None,
            checkout_url=None,
            thank_you_url=None,
        )

    normalized = NormalizedCampaignDelivery(
        delivery_mode=delivery_mode,
        pre_sales_url=normalize_public_http_url(pre_sales_url, field_name="preSalesUrl", required=True),
        sales_url=normalize_public_http_url(sales_url, field_name="salesUrl", required=True),
        checkout_url=normalize_public_http_url(checkout_url, field_name="checkoutUrl", required=False),
        thank_you_url=normalize_public_http_url(thank_you_url, field_name="thankYouUrl", required=False),
    )
    if normalized.pre_sales_url == normalized.sales_url:
        raise CampaignDeliveryConfigError(
            "preSalesUrl and salesUrl must be different in v1; use distinct canonical URLs."
        )
    return normalized


def delivery_payload_changed(
    config: CampaignDeliveryConfig | None,
    normalized: NormalizedCampaignDelivery,
) -> bool:
    if config is None:
        return True
    return any(
        (
            config.delivery_mode != normalized.delivery_mode,
            _clean_optional_text(config.pre_sales_url) != normalized.pre_sales_url,
            _clean_optional_text(config.sales_url) != normalized.sales_url,
            _clean_optional_text(config.checkout_url) != normalized.checkout_url,
            _clean_optional_text(config.thank_you_url) != normalized.thank_you_url,
        )
    )


def validation_state_for_delivery(
    *,
    delivery_mode: CampaignDeliveryModeEnum,
    changed: bool,
) -> tuple[CampaignDeliveryValidationStatusEnum, str | None, datetime | None]:
    if delivery_mode == CampaignDeliveryModeEnum.internal_funnel:
        return CampaignDeliveryValidationStatusEnum.not_applicable, None, None
    if changed:
        return CampaignDeliveryValidationStatusEnum.not_validated, None, None
    return CampaignDeliveryValidationStatusEnum.not_validated, None, None


def apply_normalized_delivery_update(
    *,
    config: CampaignDeliveryConfig | None,
    normalized: NormalizedCampaignDelivery,
) -> dict[str, Any]:
    changed = delivery_payload_changed(config, normalized)
    validation_status, validation_error, validated_at = validation_state_for_delivery(
        delivery_mode=normalized.delivery_mode,
        changed=changed,
    )
    if not changed and config is not None:
        validation_status = config.validation_status
        validation_error = config.validation_error
        validated_at = config.validated_at
    return {
        "delivery_mode": normalized.delivery_mode,
        "pre_sales_url": normalized.pre_sales_url,
        "sales_url": normalized.sales_url,
        "checkout_url": normalized.checkout_url,
        "thank_you_url": normalized.thank_you_url,
        "validation_status": validation_status,
        "validation_error": validation_error,
        "validated_at": validated_at,
    }


def campaign_delivery_response_payload(config: CampaignDeliveryConfig) -> dict[str, Any]:
    return {
        "id": str(config.id),
        "campaignId": str(config.campaign_id),
        "clientId": str(config.client_id),
        "deliveryMode": config.delivery_mode.value,
        "preSalesUrl": config.pre_sales_url,
        "salesUrl": config.sales_url,
        "checkoutUrl": config.checkout_url,
        "thankYouUrl": config.thank_you_url,
        "validationStatus": config.validation_status.value,
        "validationError": config.validation_error,
        "validatedAt": config.validated_at.isoformat() if config.validated_at else None,
        "createdAt": config.created_at.isoformat(),
        "updatedAt": config.updated_at.isoformat(),
    }


def _fetch_url_validation_result(url: str) -> tuple[int, str, str]:
    with httpx.Client(follow_redirects=True, timeout=_HTTP_TIMEOUT, headers=_HTTP_HEADERS) as client:
        response = client.get(url)
    return response.status_code, str(response.url), response.text[:50000]


def validate_campaign_delivery_config(config: CampaignDeliveryConfig) -> list[dict[str, Any]]:
    if config.delivery_mode != CampaignDeliveryModeEnum.external_urls:
        raise CampaignDeliveryConfigError("Only external_urls campaigns can run destination validation.")

    targets = [
        ("preSalesUrl", config.pre_sales_url, True),
        ("salesUrl", config.sales_url, True),
        ("checkoutUrl", config.checkout_url, False),
        ("thankYouUrl", config.thank_you_url, False),
    ]
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    for field_name, candidate_url, require_page_markers in targets:
        if not candidate_url:
            continue
        checks = ["public_http_https", "fetchable"]
        issues: list[str] = []
        final_url: str | None = None
        status_code: int | None = None
        try:
            status_code, final_url, body_text = _fetch_url_validation_result(candidate_url)
        except Exception as exc:  # noqa: BLE001
            issues.append(f"{field_name} could not be fetched: {exc}")
            body_text = ""
        else:
            if status_code >= 400:
                issues.append(f"{field_name} returned HTTP {status_code}.")
            if require_page_markers:
                checks.extend(["privacy_marker", "contact_marker", "not_under_construction"])
                if _UNDER_CONSTRUCTION_RE.search(body_text):
                    issues.append(f"{field_name} appears under construction or incomplete.")
                if not _PRIVACY_RE.search(body_text):
                    issues.append(f"{field_name} does not visibly reference privacy handling.")
                if not (_CONTACT_RE.search(body_text) or _MAILTO_RE.search(body_text) or _PHONE_RE.search(body_text)):
                    issues.append(f"{field_name} does not visibly expose contact or support information.")

        results.append(
            {
                "field": field_name,
                "url": candidate_url,
                "finalUrl": final_url,
                "statusCode": status_code,
                "passed": not issues,
                "checks": checks,
                "issues": issues,
            }
        )
        errors.extend(issues)

    if errors:
        raise CampaignDeliveryValidationError("; ".join(errors), results=results)
    return results


def validation_response_payload(
    *,
    config: CampaignDeliveryConfig,
    validation_status: CampaignDeliveryValidationStatusEnum,
    validation_error: str | None,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "checkedAt": _iso_now(),
        "validationStatus": validation_status.value,
        "validationError": validation_error,
        "results": results,
        "delivery": campaign_delivery_response_payload(config),
    }
