from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.db.enums import CampaignDeliveryModeEnum, CampaignDeliveryValidationStatusEnum
from app.db.models import CampaignDeliveryConfig


_DESTINATION_TYPE_ALIASES = {
    "pre_sales": "pre-sales",
    "presales": "pre-sales",
    "presale": "pre-sales",
    "pre-sale": "pre-sales",
    "pre-sales": "pre-sales",
    "presales-page": "pre-sales",
    "pre-sales-page": "pre-sales",
    "pre-sale-page": "pre-sales",
    "presales-listicle": "pre-sales",
    "presales-listicle-page": "pre-sales",
    "pre-sales-listicle": "pre-sales",
    "pre-sales-listicle-page": "pre-sales",
    "pre-sale-listicle": "pre-sales",
    "pre-sale-listicle-page": "pre-sales",
    "sales": "sales",
    "sales-page": "sales",
    "sales_pdp": "sales",
    "sales-pdp": "sales",
    "product-page": "sales",
    "product-detail-page": "sales",
    "checkout": "checkout",
    "checkout-page": "checkout",
    "thank-you": "thank-you",
    "thank_you": "thank-you",
    "thankyou": "thank-you",
    "thank-you-page": "thank-you",
    "thank-you_page": "thank-you",
    "thank-youpage": "thank-you",
}

_DESTINATION_TYPE_LABELS = {
    "pre-sales": "Pre-Sales Landing Page",
    "sales": "Sales Page",
    "checkout": "Checkout Page",
    "thank-you": "Thank You Page",
}


class CampaignDestinationError(ValueError):
    pass


@dataclass(frozen=True)
class CampaignDestinationResolution:
    destination_type: str
    destination_label: str
    delivery_mode: CampaignDeliveryModeEnum
    resolved_url: str | None
    source: str


def clean_optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def normalize_destination_type(value: str | None) -> str | None:
    cleaned = clean_optional_text(value)
    if not cleaned:
        return None
    normalized = cleaned.strip().lower().replace(" ", "-")
    normalized = _DESTINATION_TYPE_ALIASES.get(normalized, normalized)
    return normalized if normalized in _DESTINATION_TYPE_LABELS else None


def destination_label_for_type(destination_type: str | None) -> str | None:
    normalized = normalize_destination_type(destination_type)
    if not normalized:
        return None
    return _DESTINATION_TYPE_LABELS[normalized]


def destination_type_from_funnel_stage(funnel_stage: str | None) -> str | None:
    normalized_stage = clean_optional_text(funnel_stage)
    if not normalized_stage:
        return None
    lowered = normalized_stage.lower()
    if lowered in {"top-of-funnel", "top", "tof", "middle-of-funnel", "middle", "mid", "mof"}:
        return "pre-sales"
    if lowered in {"bottom-of-funnel", "bottom", "bof"}:
        return "sales"
    return None


def requirement_destination_type(*, brief: Mapping[str, Any], requirement: Mapping[str, Any] | None = None) -> str:
    for candidate in (
        requirement.get("destinationType") if requirement else None,
        brief.get("destinationType"),
        destination_type_from_funnel_stage(requirement.get("funnelStage") if requirement else None),
    ):
        normalized = normalize_destination_type(candidate if isinstance(candidate, str) else None)
        if normalized:
            return normalized
    raise CampaignDestinationError(
        "Destination type could not be resolved from asset brief metadata. "
        "Set destinationType or use a supported funnelStage."
    )


def requirement_destination_label(*, brief: Mapping[str, Any], requirement: Mapping[str, Any] | None = None) -> str:
    label = None
    if requirement is not None:
        label = clean_optional_text(requirement.get("destinationLabel"))
    if label is None:
        label = clean_optional_text(brief.get("destinationLabel"))
    return label or _DESTINATION_TYPE_LABELS[requirement_destination_type(brief=brief, requirement=requirement)]


def campaign_delivery_destination_map(config: CampaignDeliveryConfig) -> dict[str, str]:
    destinations: dict[str, str] = {}
    if clean_optional_text(config.pre_sales_url):
        destinations["pre-sales"] = config.pre_sales_url.strip()
    if clean_optional_text(config.sales_url):
        destinations["sales"] = config.sales_url.strip()
    if clean_optional_text(config.checkout_url):
        destinations["checkout"] = config.checkout_url.strip()
    if clean_optional_text(config.thank_you_url):
        destinations["thank-you"] = config.thank_you_url.strip()
    return destinations


def campaign_delivery_snapshot(config: CampaignDeliveryConfig | None) -> dict[str, Any] | None:
    if config is None:
        return None
    return {
        "id": str(config.id),
        "deliveryMode": config.delivery_mode.value,
        "validationStatus": config.validation_status.value,
        "validationError": config.validation_error,
        "validatedAt": config.validated_at.isoformat() if config.validated_at else None,
        "destinations": campaign_delivery_destination_map(config),
    }


def resolve_campaign_delivery_destination(
    *,
    config: CampaignDeliveryConfig,
    destination_type: str,
) -> CampaignDestinationResolution:
    normalized_type = normalize_destination_type(destination_type)
    if not normalized_type:
        raise CampaignDestinationError(f"Unsupported destination type: {destination_type!r}")

    destination_label = _DESTINATION_TYPE_LABELS[normalized_type]
    if config.delivery_mode == CampaignDeliveryModeEnum.internal_funnel:
        return CampaignDestinationResolution(
            destination_type=normalized_type,
            destination_label=destination_label,
            delivery_mode=config.delivery_mode,
            resolved_url=None,
            source="internal_funnel",
        )

    destinations = campaign_delivery_destination_map(config)
    resolved_url = destinations.get(normalized_type)
    if not resolved_url:
        raise CampaignDestinationError(
            "Campaign delivery config is missing a URL for destination type "
            f"{normalized_type!r}."
        )
    return CampaignDestinationResolution(
        destination_type=normalized_type,
        destination_label=destination_label,
        delivery_mode=config.delivery_mode,
        resolved_url=resolved_url,
        source="campaign_delivery_config",
    )


def require_valid_external_delivery(config: CampaignDeliveryConfig | None) -> CampaignDeliveryConfig:
    if config is None:
        raise CampaignDestinationError("Campaign delivery config is missing.")
    if config.delivery_mode != CampaignDeliveryModeEnum.external_urls:
        raise CampaignDestinationError(
            "Asset briefs without funnelId require campaign delivery mode external_urls."
        )
    if config.validation_status != CampaignDeliveryValidationStatusEnum.valid:
        raise CampaignDestinationError(
            "Campaign external URLs must validate successfully before downstream execution."
        )
    return config
