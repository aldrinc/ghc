from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import unquote, urljoin, urlparse
from uuid import uuid4

import httpx

from app.config import settings
from app.services.meta_review import resolve_meta_review_destination_url
from app.services.meta_ads import MetaAdsClient, MetaAdsConfigError, MetaAdsError


LEGACY_RULESET_VERSION = "paid_ads_policy_ruleset_v1"
RULESET_VERSION = "paid_ads_policy_ruleset_v2"
_RULESET_DIR = Path(__file__).resolve().parents[1] / "static" / "paid_ads_policy_rules"
_REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"
_HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_HTTP_HEADERS = {"User-Agent": "MOS-PaidAdsQA/1.0"}
_RULESET_FILES = {
    LEGACY_RULESET_VERSION: "meta_tiktok_v1.json",
    RULESET_VERSION: "meta_tiktok_v2.json",
}
_MOS_META_TRACKING_METADATA_KEY = "mosMetaTracking"
_DEFAULT_META_TRACKING_URL_PARAMETERS = "utm_source=meta&utm_medium=paid"

_PRIVATE_INFO_RE = re.compile(
    r"\b(?:we know you(?:'re| are)?|you have|your (?:medical|health|credit|debt|diabetes|weight|age|skin)|"
    r"enter your (?:ssn|social security|credit card|bank account|phone number|email))\b",
    re.IGNORECASE,
)
_DISCRIMINATION_RE = re.compile(
    r"\b(?:not for|only for|exclude(?:s|d)?|no)\s+"
    r"(?:women|men|mothers|fathers|christians|muslims|jews|black|white|asian|latino|disabled|seniors)\b",
    re.IGNORECASE,
)
_NEGATIVE_SELF_PERCEPTION_RE = re.compile(
    r"\b(?:ugly|fat|ashamed|embarrassed|insecure|unattractive|hide your body|hate your skin)\b",
    re.IGNORECASE,
)
_SIEP_RE = re.compile(
    r"\b(?:vote|election|ballot|candidate|senate|congress|governor|mayor|political|campaign finance)\b",
    re.IGNORECASE,
)
_UNDER_CONSTRUCTION_RE = re.compile(
    r"\b(?:under construction|coming soon|launching soon|page not found|404)\b",
    re.IGNORECASE,
)
_PRIVACY_RE = re.compile(r"\bprivacy\b", re.IGNORECASE)
_CONTACT_RE = re.compile(r"\b(?:contact|support|help center|customer service)\b", re.IGNORECASE)
_MAILTO_RE = re.compile(r"mailto:", re.IGNORECASE)
_PHONE_RE = re.compile(r"\+?\d[\d\s().-]{6,}\d")


class MetaProfileRefreshError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code


def _ruleset_path(version: str) -> Path:
    filename = _RULESET_FILES.get(version)
    if not filename:
        supported = "', '".join(_RULESET_FILES)
        raise KeyError(
            f"Unsupported ruleset version '{version}'. Supported versions: '{supported}'."
        )
    return _RULESET_DIR / filename


@lru_cache(maxsize=8)
def get_ruleset(version: str = RULESET_VERSION) -> dict[str, Any]:
    payload = json.loads(_ruleset_path(version).read_text(encoding="utf-8"))
    return payload


def list_rulesets() -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for version in _RULESET_FILES:
        ruleset = get_ruleset(version)
        summaries.append(
            {
                "version": ruleset["version"],
                "effectiveDate": ruleset["effectiveDate"],
                "description": ruleset["description"],
                "sourceCount": len(ruleset.get("sources", [])),
                "ruleCount": len(ruleset.get("rules", [])),
            }
        )
    return summaries


def normalize_platform(platform: str) -> str:
    cleaned = str(platform or "").strip().lower()
    if cleaned not in {"meta", "tiktok"}:
        raise ValueError("platform must be either 'meta' or 'tiktok'.")
    return cleaned


def clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def normalize_tracking_provider(value: str | None) -> str | None:
    cleaned = clean_optional_text(value)
    return cleaned.lower().replace(" ", "_") if cleaned else None


def rules_by_id(ruleset: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {rule["ruleId"]: rule for rule in ruleset.get("rules", [])}


def sources_by_id(ruleset: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {source["sourceId"]: source for source in ruleset.get("sources", [])}


def _new_finding(
    *,
    ruleset: dict[str, Any],
    rule_id: str,
    status: str,
    title: str,
    message: str,
    artifact_type: str,
    artifact_ref: str | None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rule = rules_by_id(ruleset)[rule_id]
    source = sources_by_id(ruleset)[rule["sourceId"]]
    return {
        "ruleId": rule["ruleId"],
        "ruleType": rule["ruleType"],
        "platform": rule["platform"],
        "severity": rule["severity"],
        "status": status,
        "title": title,
        "message": message,
        "artifactType": artifact_type,
        "artifactRef": artifact_ref,
        "fixGuidance": list(rule.get("fixGuidance") or []),
        "evidence": evidence or {},
        "needsVerification": bool(rule.get("sourceNeedsVerification") or source.get("needsVerification")),
        "sourceId": source["sourceId"],
        "sourceTitle": source["title"],
        "sourceUrl": source.get("url"),
        "policyAnchorQuote": rule.get("policyAnchorQuote"),
    }


def _maybe_add_missing_text_finding(
    findings: list[dict[str, Any]],
    *,
    ruleset: dict[str, Any],
    rule_id: str,
    value: str | None,
    label: str,
    artifact_type: str,
    artifact_ref: str | None,
) -> None:
    if clean_optional_text(value):
        return
    findings.append(
        _new_finding(
            ruleset=ruleset,
            rule_id=rule_id,
            status="failed",
            title=f"Missing {label}",
            message=f"{label} is not configured.",
            artifact_type=artifact_type,
            artifact_ref=artifact_ref,
            evidence={"field": label},
        )
    )


def _read_bool(metadata: dict[str, Any], key: str) -> bool | None:
    value = metadata.get(key)
    if isinstance(value, bool):
        return value
    return None


def _read_text(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    return clean_optional_text(value) if isinstance(value, str) else None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _profile_metadata(profile: dict[str, Any]) -> dict[str, Any]:
    metadata = profile.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def _ruleset_uses_mos_meta_tracking(version: str) -> bool:
    return version != LEGACY_RULESET_VERSION


def _normalize_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = clean_optional_text(value) if isinstance(value, str) else None
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def _mos_meta_tracking_metadata(profile: dict[str, Any]) -> dict[str, Any]:
    metadata = _profile_metadata(profile)
    raw = metadata.get(_MOS_META_TRACKING_METADATA_KEY)
    return dict(raw) if isinstance(raw, dict) else {}


def _meta_account_008_legacy_ready(profile: dict[str, Any]) -> bool:
    return profile.get("dataSetShopifyPartnerInstalled") is True and normalize_tracking_provider(
        profile.get("dataSetDataSharingLevel")
    ) == "maximum"


def _meta_account_008_mos_tracking_ready(profile: dict[str, Any]) -> bool:
    metadata = _mos_meta_tracking_metadata(profile)
    pixel_id = clean_optional_text(metadata.get("pixelId")) or clean_optional_text(profile.get("pixelId"))
    status = normalize_tracking_provider(metadata.get("status"))
    mode = normalize_tracking_provider(metadata.get("mode"))
    channel = normalize_tracking_provider(metadata.get("channel"))
    browser_events = _normalize_string_list(metadata.get("browserEvents"))
    return (
        bool(pixel_id)
        and status == "active"
        and mode == "public_funnel_runtime"
        and channel == "meta"
        and "pageview" in {item.replace("_", "").lower() for item in browser_events}
        and "initiatecheckout" in {item.replace("_", "").lower() for item in browser_events}
    )


def activate_mos_meta_funnel_tracking_profile(
    *,
    profile: dict[str, Any],
    funnel_ids: list[str],
    ruleset_version: str = RULESET_VERSION,
) -> dict[str, Any]:
    refreshed = refresh_meta_platform_profile_from_graph(profile=profile, ruleset_version=ruleset_version)
    pixel_id = clean_optional_text(refreshed.get("pixelId"))
    data_set_id = clean_optional_text(refreshed.get("dataSetId"))
    data_set_assigned = refreshed.get("dataSetAssignedToAdAccount")
    if not pixel_id:
        raise MetaProfileRefreshError(
            "Meta funnel tracking automation requires a resolved pixelId. "
            "Select a single Meta pixel/data set in MOS before generating funnels.",
        )
    if not data_set_id or data_set_assigned is not True:
        raise MetaProfileRefreshError(
            "Meta funnel tracking automation requires a Data Set that is assigned to the ad account.",
        )

    metadata = _profile_metadata(refreshed)
    existing_tracking = _mos_meta_tracking_metadata(refreshed)
    configured_funnel_ids = _normalize_string_list(existing_tracking.get("funnelIds"))
    merged_funnel_ids = configured_funnel_ids[:]
    seen_funnel_ids = set(configured_funnel_ids)
    for funnel_id in funnel_ids:
        cleaned = clean_optional_text(funnel_id)
        if not cleaned or cleaned in seen_funnel_ids:
            continue
        seen_funnel_ids.add(cleaned)
        merged_funnel_ids.append(cleaned)

    metadata[_MOS_META_TRACKING_METADATA_KEY] = {
        **existing_tracking,
        "status": "active",
        "channel": "meta",
        "mode": "public_funnel_runtime",
        "pixelId": pixel_id,
        "dataSetId": data_set_id,
        "browserEvents": ["PageView", "InitiateCheckout"],
        "internalEvents": ["page_view", "cta_click"],
        "funnelIds": merged_funnel_ids,
        "enabledAt": existing_tracking.get("enabledAt") or _iso_now(),
        "lastSyncedAt": _iso_now(),
        "source": "campaign_funnel_generation",
    }

    refreshed["rulesetVersion"] = ruleset_version
    refreshed["metadata"] = metadata
    if not clean_optional_text(refreshed.get("trackingProvider")):
        refreshed["trackingProvider"] = "mos"
    if not clean_optional_text(refreshed.get("trackingUrlParameters")):
        refreshed["trackingUrlParameters"] = _DEFAULT_META_TRACKING_URL_PARAMETERS
    return refreshed


def _graphql_candidate_source(profile_value: str | None, settings_value: str | None, *, settings_label: str) -> tuple[str | None, str | None]:
    cleaned_profile_value = clean_optional_text(profile_value)
    if cleaned_profile_value:
        return cleaned_profile_value, "profile"
    cleaned_settings_value = clean_optional_text(settings_value)
    if cleaned_settings_value:
        return cleaned_settings_value, settings_label
    return None, None


def _single_graph_node(
    *,
    items: list[dict[str, Any]],
    description: str,
    edge_name: str,
) -> tuple[dict[str, Any], str]:
    if len(items) == 1:
        return items[0], edge_name
    if not items:
        raise MetaProfileRefreshError(f"Meta Graph returned no accessible {description}. Configure it explicitly in MOS.")
    raise MetaProfileRefreshError(
        f"Meta Graph returned multiple accessible {description} values. Configure the intended {description} explicitly in MOS."
    )


def _fetch_meta_page(client: MetaAdsClient, *, profile: dict[str, Any]) -> tuple[dict[str, Any], str]:
    candidate_id, candidate_source = _graphql_candidate_source(
        profile.get("pageId"),
        settings.META_PAGE_ID,
        settings_label="settings.META_PAGE_ID",
    )
    fields = "id,name,verification_status,link,business"
    if candidate_id:
        try:
            return client.get_object(object_id=candidate_id, fields=fields), candidate_source or "profile"
        except MetaAdsError as exc:
            raise MetaProfileRefreshError(
                f"Unable to validate Meta Page '{candidate_id}' from {candidate_source or 'profile'}: {exc}"
            ) from exc
    try:
        pages = client.list_user_pages(fields=fields, limit=10).get("data") or []
    except MetaAdsError as exc:
        raise MetaProfileRefreshError(f"Unable to list Meta Pages from Graph: {exc}", status_code=503) from exc
    return _single_graph_node(items=pages, description="Meta Page", edge_name="graph.me/accounts")


def _fetch_meta_ad_account(client: MetaAdsClient, *, profile: dict[str, Any]) -> tuple[dict[str, Any], str]:
    candidate_id, candidate_source = _graphql_candidate_source(
        profile.get("adAccountId"),
        settings.META_AD_ACCOUNT_ID,
        settings_label="settings.META_AD_ACCOUNT_ID",
    )
    fields = "id,name,account_status,disable_reason,business,funding_source_details"
    if candidate_id:
        try:
            return client.get_ad_account(ad_account_id=candidate_id, fields=fields), candidate_source or "profile"
        except MetaAdsError as exc:
            raise MetaProfileRefreshError(
                f"Unable to validate Meta Ad Account '{candidate_id}' from {candidate_source or 'profile'}: {exc}"
            ) from exc
    try:
        accounts = client.list_user_adaccounts(fields=fields, limit=10).get("data") or []
    except MetaAdsError as exc:
        raise MetaProfileRefreshError(f"Unable to list Meta Ad Accounts from Graph: {exc}", status_code=503) from exc
    return _single_graph_node(items=accounts, description="Meta Ad Account", edge_name="graph.me/adaccounts")


def _fetch_meta_business(
    client: MetaAdsClient,
    *,
    page: dict[str, Any],
    ad_account: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    page_business = page.get("business") if isinstance(page.get("business"), dict) else {}
    ad_account_business = ad_account.get("business") if isinstance(ad_account.get("business"), dict) else {}
    business_id = clean_optional_text(page_business.get("id")) or clean_optional_text(ad_account_business.get("id"))
    business_source = "page.business" if clean_optional_text(page_business.get("id")) else None
    if not business_id:
        business_id = clean_optional_text(ad_account_business.get("id"))
        if business_id:
            business_source = "ad_account.business"
    if not business_id:
        return None, None
    try:
        return client.get_object(object_id=business_id, fields="id,name,verification_status,owned_pages{id,name}"), business_source
    except MetaAdsError as exc:
        raise MetaProfileRefreshError(f"Unable to validate Meta Business '{business_id}' from {business_source}: {exc}") from exc


def _derive_payment_method_type(funding_source_details: dict[str, Any] | None) -> str | None:
    if not isinstance(funding_source_details, dict):
        return None
    display_string = clean_optional_text(str(funding_source_details.get("display_string") or ""))
    normalized_display = display_string.lower() if display_string else ""
    if "paypal" in normalized_display:
        return "paypal"
    if any(brand in normalized_display for brand in ("visa", "mastercard", "american express", "amex", "discover")):
        return "credit_card"
    if funding_source_details.get("type") == 1:
        return "credit_card"
    if display_string:
        return "other"
    return None


def _pick_pixel_record(
    *,
    profile: dict[str, Any],
    pixel_records: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    profile_pixel_id = clean_optional_text(profile.get("pixelId"))
    if profile_pixel_id:
        for pixel in pixel_records:
            if clean_optional_text(pixel.get("id")) == profile_pixel_id:
                return pixel, "profile.pixelId", None
        return None, None, "Configured pixelId was not returned by Meta Graph for the validated ad account."
    if len(pixel_records) == 1:
        return pixel_records[0], "graph.adspixels.single", None
    if len(pixel_records) > 1:
        return None, None, "Multiple Meta pixels/data sets are assigned to the ad account. Select the intended one in MOS."
    return None, None, None


def refresh_meta_platform_profile_from_graph(
    *,
    profile: dict[str, Any],
    ruleset_version: str = RULESET_VERSION,
) -> dict[str, Any]:
    normalized_platform = normalize_platform(profile.get("platform") or "meta")
    if normalized_platform != "meta":
        return profile

    try:
        client = MetaAdsClient.from_settings()
    except MetaAdsConfigError as exc:
        raise MetaProfileRefreshError(str(exc), status_code=503) from exc

    page, page_source = _fetch_meta_page(client, profile=profile)
    ad_account, ad_account_source = _fetch_meta_ad_account(client, profile=profile)
    business, business_source = _fetch_meta_business(client, page=page, ad_account=ad_account)

    try:
        pixel_records = client.list_ad_pixels(
            ad_account_id=str(ad_account.get("id") or ""),
            fields="id,name,creation_time",
            limit=25,
        ).get("data") or []
    except MetaAdsError as exc:
        raise MetaProfileRefreshError(
            f"Unable to validate Meta pixel/data set assignments for ad account '{ad_account.get('id')}': {exc}",
            status_code=503,
        ) from exc

    selected_pixel, pixel_source, pixel_warning = _pick_pixel_record(profile=profile, pixel_records=pixel_records)
    existing_metadata = _profile_metadata(profile)
    validation_metadata = {
        "apiVersion": settings.META_GRAPH_API_VERSION,
        "lastValidatedAt": _iso_now(),
        "validatedFields": [
            "pageId",
            "pageName",
            "adAccountId",
            "adAccountName",
            "businessManagerId",
            "businessManagerName",
            "paymentMethodStatus",
            "paymentMethodType",
            "pixelId",
            "dataSetId",
            "dataSetAssignedToAdAccount",
        ],
        "unsupportedLiveChecks": [
            "dataSetShopifyPartnerInstalled",
            "dataSetDataSharingLevel",
            "verifiedDomain",
            "verifiedDomainStatus",
            "attributionClickWindow",
            "attributionViewWindow",
            "viewThroughEnabled",
            "trackingProvider",
            "trackingUrlParameters",
        ],
        "page": {
            "source": page_source,
            "id": clean_optional_text(page.get("id")),
            "name": clean_optional_text(page.get("name")),
            "verificationStatus": clean_optional_text(page.get("verification_status")),
        },
        "adAccount": {
            "source": ad_account_source,
            "id": clean_optional_text(ad_account.get("id")),
            "name": clean_optional_text(ad_account.get("name")),
            "accountStatus": ad_account.get("account_status"),
            "disableReason": ad_account.get("disable_reason"),
        },
        "business": {
            "source": business_source,
            "id": clean_optional_text((business or {}).get("id")),
            "name": clean_optional_text((business or {}).get("name")),
            "verificationStatus": clean_optional_text((business or {}).get("verification_status")),
        },
        "fundingSource": {
            "present": bool(isinstance(ad_account.get("funding_source_details"), dict) and ad_account["funding_source_details"].get("id")),
            "type": (ad_account.get("funding_source_details") or {}).get("type")
            if isinstance(ad_account.get("funding_source_details"), dict)
            else None,
            "displayString": clean_optional_text((ad_account.get("funding_source_details") or {}).get("display_string"))
            if isinstance(ad_account.get("funding_source_details"), dict)
            else None,
        },
        "pixels": {
            "count": len(pixel_records),
            "ids": [clean_optional_text(pixel.get("id")) for pixel in pixel_records if clean_optional_text(pixel.get("id"))],
            "selectionSource": pixel_source,
            "selectedPixelId": clean_optional_text((selected_pixel or {}).get("id")),
            "warning": pixel_warning,
        },
    }
    merged_metadata = {**existing_metadata, "metaGraphValidation": validation_metadata}

    selected_pixel_id = clean_optional_text((selected_pixel or {}).get("id"))
    selected_pixel_name = clean_optional_text((selected_pixel or {}).get("name"))
    existing_dataset_id = clean_optional_text(profile.get("dataSetId"))
    data_set_id = existing_dataset_id
    if existing_dataset_id:
        matching_data_set = any(clean_optional_text(pixel.get("id")) == existing_dataset_id for pixel in pixel_records)
        data_set_assigned = matching_data_set
    else:
        data_set_id = selected_pixel_id
        data_set_assigned = bool(data_set_id)

    return {
        **profile,
        "platform": "meta",
        "rulesetVersion": str(profile.get("rulesetVersion") or ruleset_version),
        "businessManagerId": clean_optional_text((business or {}).get("id")),
        "businessManagerName": clean_optional_text((business or {}).get("name")),
        "pageId": clean_optional_text(page.get("id")),
        "pageName": clean_optional_text(page.get("name")),
        "adAccountId": clean_optional_text(ad_account.get("id")),
        "adAccountName": clean_optional_text(ad_account.get("name")),
        "paymentMethodType": _derive_payment_method_type(
            ad_account.get("funding_source_details") if isinstance(ad_account.get("funding_source_details"), dict) else None
        ),
        "paymentMethodStatus": "active"
        if isinstance(ad_account.get("funding_source_details"), dict) and clean_optional_text(ad_account["funding_source_details"].get("id"))
        else None,
        "pixelId": selected_pixel_id,
        "dataSetId": data_set_id,
        "dataSetAssignedToAdAccount": data_set_assigned,
        "metadata": {
            **merged_metadata,
            "metaPixelName": selected_pixel_name,
        },
    }


def evaluate_platform_profile(
    *,
    platform: str,
    profile: dict[str, Any],
    ruleset_version: str = RULESET_VERSION,
) -> dict[str, Any]:
    ruleset = get_ruleset(ruleset_version)
    normalized_platform = normalize_platform(platform)
    findings: list[dict[str, Any]] = []
    artifact_ref = normalized_platform
    profile_metadata = _profile_metadata(profile)
    assessment_metadata: dict[str, Any] = {"assessmentKind": "platform_profile"}
    if isinstance(profile_metadata.get("metaGraphValidation"), dict):
        assessment_metadata["profileValidation"] = profile_metadata["metaGraphValidation"]

    if normalized_platform == "meta":
        _maybe_add_missing_text_finding(
            findings,
            ruleset=ruleset,
            rule_id="META-ACCOUNT-001",
            value=profile.get("businessManagerId"),
            label="businessManagerId",
            artifact_type="platform_profile",
            artifact_ref=artifact_ref,
        )
        _maybe_add_missing_text_finding(
            findings,
            ruleset=ruleset,
            rule_id="META-ACCOUNT-002",
            value=profile.get("pageId"),
            label="pageId",
            artifact_type="platform_profile",
            artifact_ref=artifact_ref,
        )
        _maybe_add_missing_text_finding(
            findings,
            ruleset=ruleset,
            rule_id="META-ACCOUNT-003",
            value=profile.get("adAccountId"),
            label="adAccountId",
            artifact_type="platform_profile",
            artifact_ref=artifact_ref,
        )
        payment_status = clean_optional_text(profile.get("paymentMethodStatus"))
        if not payment_status or payment_status.lower() not in {"active", "configured"}:
            findings.append(
                _new_finding(
                    ruleset=ruleset,
                    rule_id="META-ACCOUNT-004",
                    status="failed",
                    title="Payment method not active",
                    message="Meta paymentMethodStatus must be active before launch review.",
                    artifact_type="platform_profile",
                    artifact_ref=artifact_ref,
                    evidence={"paymentMethodStatus": payment_status},
                )
            )
        payment_type = normalize_tracking_provider(profile.get("paymentMethodType"))
        if payment_type != "credit_card":
            findings.append(
                _new_finding(
                    ruleset=ruleset,
                    rule_id="META-ACCOUNT-005",
                    status="failed",
                    title="Payment method is not credit card",
                    message="Meta paymentMethodType should be set to credit_card for this launch checklist.",
                    artifact_type="platform_profile",
                    artifact_ref=artifact_ref,
                    evidence={"paymentMethodType": payment_type},
                )
            )
        _maybe_add_missing_text_finding(
            findings,
            ruleset=ruleset,
            rule_id="META-ACCOUNT-006",
            value=profile.get("pixelId"),
            label="pixelId",
            artifact_type="platform_profile",
            artifact_ref=artifact_ref,
        )
        data_set_id = clean_optional_text(profile.get("dataSetId"))
        data_set_assigned = profile.get("dataSetAssignedToAdAccount")
        if not data_set_id or data_set_assigned is not True:
            findings.append(
                _new_finding(
                    ruleset=ruleset,
                    rule_id="META-ACCOUNT-007",
                    status="failed",
                    title="Data Set missing or unassigned",
                    message="Meta Data Set must exist and be assigned to the ad account.",
                    artifact_type="platform_profile",
                    artifact_ref=artifact_ref,
                    evidence={
                        "dataSetId": data_set_id,
                        "dataSetAssignedToAdAccount": data_set_assigned,
                    },
                )
            )
        legacy_meta_tracking_ready = _meta_account_008_legacy_ready(profile)
        mos_meta_tracking_ready = _meta_account_008_mos_tracking_ready(profile)
        if not legacy_meta_tracking_ready and (
            not _ruleset_uses_mos_meta_tracking(ruleset_version) or not mos_meta_tracking_ready
        ):
            mos_tracking_metadata = _mos_meta_tracking_metadata(profile)
            findings.append(
                _new_finding(
                    ruleset=ruleset,
                    rule_id="META-ACCOUNT-008",
                    status="failed",
                    title="Data Set integration is incomplete",
                    message=(
                        "Meta Data Set should use the Shopify partner integration and Maximum data sharing, "
                        "or have MOS-managed funnel tracking automation active."
                        if _ruleset_uses_mos_meta_tracking(ruleset_version)
                        else "Meta Data Set should use the Shopify partner integration and Maximum data sharing."
                    ),
                    artifact_type="platform_profile",
                    artifact_ref=artifact_ref,
                    evidence={
                        "dataSetShopifyPartnerInstalled": profile.get("dataSetShopifyPartnerInstalled"),
                        "dataSetDataSharingLevel": profile.get("dataSetDataSharingLevel"),
                        "mosMetaTrackingStatus": mos_tracking_metadata.get("status"),
                        "mosMetaTrackingMode": mos_tracking_metadata.get("mode"),
                        "mosMetaTrackingPixelId": mos_tracking_metadata.get("pixelId"),
                    },
                )
            )
        verified_domain = clean_optional_text(profile.get("verifiedDomain"))
        verified_status = normalize_tracking_provider(profile.get("verifiedDomainStatus"))
        if not verified_domain or verified_status != "verified":
            findings.append(
                _new_finding(
                    ruleset=ruleset,
                    rule_id="META-ACCOUNT-009",
                    status="failed",
                    title="Verified domain missing",
                    message="Meta verifiedDomain must be set and verifiedDomainStatus must equal verified.",
                    artifact_type="platform_profile",
                    artifact_ref=artifact_ref,
                    evidence={"verifiedDomain": verified_domain, "verifiedDomainStatus": verified_status},
                )
            )
        if normalize_tracking_provider(profile.get("attributionClickWindow")) != "7d" or normalize_tracking_provider(
            profile.get("attributionViewWindow")
        ) != "1d":
            findings.append(
                _new_finding(
                    ruleset=ruleset,
                    rule_id="META-ACCOUNT-010",
                    status="failed",
                    title="Attribution windows do not match checklist",
                    message="Meta attribution should be 7d click and 1d view for the launch checklist.",
                    artifact_type="platform_profile",
                    artifact_ref=artifact_ref,
                    evidence={
                        "attributionClickWindow": profile.get("attributionClickWindow"),
                        "attributionViewWindow": profile.get("attributionViewWindow"),
                    },
                )
            )
        if profile.get("viewThroughEnabled") is not False:
            findings.append(
                _new_finding(
                    ruleset=ruleset,
                    rule_id="META-ACCOUNT-011",
                    status="failed",
                    title="View-through is not disabled",
                    message="Meta viewThroughEnabled should be false for the initial launch checklist.",
                    artifact_type="platform_profile",
                    artifact_ref=artifact_ref,
                    evidence={"viewThroughEnabled": profile.get("viewThroughEnabled")},
                )
            )
        tracking_provider = normalize_tracking_provider(profile.get("trackingProvider"))
        tracking_url_parameters = clean_optional_text(profile.get("trackingUrlParameters"))
        if not tracking_provider or not tracking_url_parameters:
            findings.append(
                _new_finding(
                    ruleset=ruleset,
                    rule_id="META-ACCOUNT-012",
                    status="failed",
                    title="Tracking configuration missing",
                    message="Tracking provider and URL parameters should be explicitly recorded before launch review.",
                    artifact_type="platform_profile",
                    artifact_ref=artifact_ref,
                    evidence={
                        "trackingProvider": tracking_provider,
                        "trackingUrlParameters": tracking_url_parameters,
                    },
                )
            )
        return {
            "platform": normalized_platform,
            "checkedRuleIds": [
                "META-ACCOUNT-001",
                "META-ACCOUNT-002",
                "META-ACCOUNT-003",
                "META-ACCOUNT-004",
                "META-ACCOUNT-005",
                "META-ACCOUNT-006",
                "META-ACCOUNT-007",
                "META-ACCOUNT-008",
                "META-ACCOUNT-009",
                "META-ACCOUNT-010",
                "META-ACCOUNT-011",
                "META-ACCOUNT-012",
            ],
            "findings": findings,
            "metadata": assessment_metadata,
        }

    _maybe_add_missing_text_finding(
        findings,
        ruleset=ruleset,
        rule_id="TTK-ACCOUNT-001",
        value=profile.get("adAccountId"),
        label="adAccountId",
        artifact_type="platform_profile",
        artifact_ref=artifact_ref,
    )
    if not clean_optional_text(profile.get("pixelId")) and not clean_optional_text(_read_text(profile.get("metadata") or {}, "eventsManagerId")):
        findings.append(
            _new_finding(
                ruleset=ruleset,
                rule_id="TTK-ACCOUNT-002",
                status="failed",
                title="TikTok pixel or events configuration missing",
                message="TikTok assessment requires a pixelId or equivalent events configuration in metadata.",
                artifact_type="platform_profile",
                artifact_ref=artifact_ref,
                evidence={"pixelId": profile.get("pixelId")},
            )
        )
    profile_metadata = profile.get("metadata") if isinstance(profile.get("metadata"), dict) else {}
    if _read_bool(profile_metadata, "regulatedVertical") is True and _read_text(profile_metadata, "certificationStatus") != "approved":
        findings.append(
            _new_finding(
                ruleset=ruleset,
                rule_id="TTK-ACCOUNT-003",
                status="needs_manual_review",
                title="TikTok regulated vertical requires certification review",
                message="The profile is marked as regulatedVertical but certificationStatus is not approved.",
                artifact_type="platform_profile",
                artifact_ref=artifact_ref,
                evidence={
                    "regulatedVertical": profile_metadata.get("regulatedVertical"),
                    "certificationStatus": profile_metadata.get("certificationStatus"),
                },
            )
        )
    return {
        "platform": normalized_platform,
        "checkedRuleIds": ["TTK-ACCOUNT-001", "TTK-ACCOUNT-002", "TTK-ACCOUNT-003"],
        "findings": findings,
        "metadata": assessment_metadata,
    }


def _combine_copy_fields(spec: dict[str, Any]) -> str:
    return " ".join(
        value.strip()
        for value in (
            str(spec.get("primary_text") or ""),
            str(spec.get("headline") or ""),
            str(spec.get("description") or ""),
        )
        if isinstance(value, str) and value.strip()
    )


def list_meta_copy_policy_issues(spec: dict[str, Any]) -> list[dict[str, str]]:
    copy_blob = _combine_copy_fields(spec)
    issues: list[dict[str, str]] = []
    if _PRIVATE_INFO_RE.search(copy_blob):
        issues.append(
            {
                "ruleId": "META-COPY-002",
                "title": "Copy appears to reference private information",
                "message": "The Meta draft copy appears to ask for or imply knowledge of private user information.",
            }
        )
    if _DISCRIMINATION_RE.search(copy_blob):
        issues.append(
            {
                "ruleId": "META-COPY-003",
                "title": "Copy appears discriminatory",
                "message": "The Meta draft copy appears to contain discriminatory or exclusionary language.",
            }
        )
    if _NEGATIVE_SELF_PERCEPTION_RE.search(copy_blob):
        issues.append(
            {
                "ruleId": "META-COPY-005",
                "title": "Negative self-perception language detected",
                "message": "The Meta draft copy appears to use shaming or negative self-perception language.",
            }
        )
    return issues


def _looks_absolute_http_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _resolve_public_destination_url(value: str | None, *, review_base_url: str | None = None) -> str | None:
    cleaned = clean_optional_text(value)
    if not cleaned:
        return None
    if _looks_absolute_http_url(cleaned):
        return cleaned
    base = clean_optional_text(review_base_url) or clean_optional_text(settings.DEPLOY_PUBLIC_BASE_URL)
    if not base or not cleaned.startswith("/"):
        return None
    return urljoin(f"{base.rstrip('/')}/", cleaned.lstrip("/"))


def _extract_text_fragments(value: Any) -> list[str]:
    fragments: list[str] = []
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned:
            fragments.append(cleaned)
        return fragments
    if isinstance(value, dict):
        for nested in value.values():
            fragments.extend(_extract_text_fragments(nested))
        return fragments
    if isinstance(value, list):
        for nested in value:
            fragments.extend(_extract_text_fragments(nested))
    return fragments


def _parse_public_funnel_route(url: str) -> tuple[str, str, str | None] | None:
    parsed = urlparse(url)
    raw_segments = [unquote(segment).strip() for segment in parsed.path.split("/") if segment.strip()]
    if len(raw_segments) >= 4 and raw_segments[0] == "f":
        product_slug, funnel_slug = raw_segments[1], raw_segments[2]
        page_slug = raw_segments[3] if len(raw_segments) >= 4 else None
        return product_slug, funnel_slug, page_slug
    if len(raw_segments) >= 3:
        product_slug, funnel_slug, page_slug = raw_segments[0], raw_segments[1], raw_segments[2]
        return product_slug, funnel_slug, page_slug
    return None


def _public_funnel_api_base_url() -> str | None:
    return clean_optional_text(settings.DEPLOY_PUBLIC_API_BASE_URL)


def _load_public_funnel_snapshot(url: str) -> dict[str, Any] | None:
    route = _parse_public_funnel_route(url)
    api_base_url = _public_funnel_api_base_url()
    if route is None or not api_base_url:
        return None

    product_slug, funnel_slug, page_slug = route
    with httpx.Client(follow_redirects=True, timeout=_HTTP_TIMEOUT, headers=_HTTP_HEADERS) as client:
        resolved_page_slug = page_slug
        if not resolved_page_slug:
            meta_response = client.get(
                f"{api_base_url.rstrip('/')}/public/funnels/{product_slug}/{funnel_slug}/meta"
            )
            meta_response.raise_for_status()
            meta_payload = meta_response.json()
            if not isinstance(meta_payload, dict):
                raise httpx.DecodingError("Public funnel meta response must be a JSON object.")
            resolved_page_slug = clean_optional_text(meta_payload.get("entrySlug"))
            if not resolved_page_slug:
                raise httpx.DecodingError("Public funnel meta response is missing entrySlug.")

        page_response = client.get(
            f"{api_base_url.rstrip('/')}/public/funnels/{product_slug}/{funnel_slug}/pages/{resolved_page_slug}"
        )
        page_response.raise_for_status()
        page_payload = page_response.json()
        if not isinstance(page_payload, dict):
            raise httpx.DecodingError("Public funnel page response must be a JSON object.")

    extracted_text = "\n".join(
        _extract_text_fragments(page_payload.get("metadata"))
        + _extract_text_fragments(page_payload.get("puckData"))
    )
    return {
        "requestedUrl": url,
        "finalUrl": url,
        "statusCode": 200,
        "bodyText": extracted_text[:50000],
        "inspectionSource": "public_funnel_api",
    }


def _landing_page_snapshot(url: str) -> dict[str, Any]:
    public_funnel_snapshot = _load_public_funnel_snapshot(url)
    if public_funnel_snapshot is not None:
        return public_funnel_snapshot
    with httpx.Client(follow_redirects=True, timeout=_HTTP_TIMEOUT, headers=_HTTP_HEADERS) as client:
        response = client.get(url)
    return {
        "requestedUrl": url,
        "finalUrl": str(response.url),
        "statusCode": response.status_code,
        "bodyText": response.text[:50000],
        "inspectionSource": "http_fetch",
    }


def _creative_spec_destination(spec: dict[str, Any]) -> tuple[str | None, str | None]:
    direct = clean_optional_text(spec.get("destination_url"))
    metadata = spec.get("metadata_json") if isinstance(spec.get("metadata_json"), dict) else {}
    if direct:
        return direct, "stored_destination_url"
    destination_page = clean_optional_text(metadata.get("destinationPage"))
    review_paths = metadata.get("reviewPaths") if isinstance(metadata.get("reviewPaths"), dict) else {}
    resolved_review_path = resolve_meta_review_destination_url(
        destination_page=destination_page or "",
        review_paths=review_paths,
    )
    if resolved_review_path:
        return resolved_review_path, "review_path"
    if destination_page and (destination_page.startswith("/") or _looks_absolute_http_url(destination_page)):
        return destination_page, "destination_page"
    return None, None


def evaluate_meta_campaign(
    *,
    campaign: Any,
    creative_specs: list[Any],
    adset_specs: list[Any],
    ready_assets: list[Any],
    platform_profile: dict[str, Any],
    review_base_url: str | None = None,
    ruleset_version: str = RULESET_VERSION,
) -> dict[str, Any]:
    ruleset = get_ruleset(ruleset_version)
    findings: list[dict[str, Any]] = []
    checked_rule_ids: list[str] = []

    profile_result = evaluate_platform_profile(platform="meta", profile=platform_profile, ruleset_version=ruleset_version)
    findings.extend(profile_result["findings"])
    checked_rule_ids.extend(profile_result["checkedRuleIds"])

    checked_rule_ids.extend(["META-CAMPAIGN-001", "META-CAMPAIGN-002"])
    if not creative_specs:
        findings.append(
            _new_finding(
                ruleset=ruleset,
                rule_id="META-CAMPAIGN-001",
                status="failed",
                title="Campaign has no Meta creative specs",
                message="Run Prepare Meta review before running campaign QA.",
                artifact_type="campaign",
                artifact_ref=str(campaign.id),
                evidence={"campaignId": str(campaign.id)},
            )
        )
    if not adset_specs:
        findings.append(
            _new_finding(
                ruleset=ruleset,
                rule_id="META-CAMPAIGN-002",
                status="failed",
                title="Campaign has no Meta ad set specs",
                message="Create draft Meta ad set specs before running campaign QA.",
                artifact_type="campaign",
                artifact_ref=str(campaign.id),
                evidence={"campaignId": str(campaign.id)},
            )
        )

    ready_asset_ids = {str(asset.id) for asset in ready_assets}
    creative_asset_ids = {str(spec.asset_id) for spec in creative_specs if getattr(spec, "asset_id", None)}
    missing_asset_ids = sorted(ready_asset_ids - creative_asset_ids)
    if missing_asset_ids:
        findings.append(
            _new_finding(
                ruleset=ruleset,
                rule_id="META-CAMPAIGN-001",
                status="failed",
                title="Ready assets are missing prepared Meta specs",
                message="Some ready campaign assets still do not have prepared Meta creative specs.",
                artifact_type="campaign",
                artifact_ref=str(campaign.id),
                evidence={"missingAssetIds": missing_asset_ids},
            )
        )

    checked_rule_ids.extend(
        [
            "META-COPY-002",
            "META-COPY-003",
            "META-COPY-004",
            "META-COPY-005",
            "META-LP-001",
            "META-LP-002",
            "META-LP-003",
            "META-LP-004",
            "META-LP-005",
            "META-LP-006",
        ]
    )
    for spec in creative_specs:
        spec_dict = {
            "id": str(spec.id),
            "asset_id": str(spec.asset_id),
            "primary_text": spec.primary_text,
            "headline": spec.headline,
            "description": spec.description,
            "destination_url": spec.destination_url,
            "metadata_json": spec.metadata_json if isinstance(spec.metadata_json, dict) else {},
        }
        artifact_ref = str(spec.id)
        copy_blob = _combine_copy_fields(spec_dict)
        copy_issues = list_meta_copy_policy_issues(spec_dict)
        if any(issue["ruleId"] == "META-COPY-002" for issue in copy_issues):
            findings.append(
                _new_finding(
                    ruleset=ruleset,
                    rule_id="META-COPY-002",
                    status="failed",
                    title="Copy appears to reference private information",
                    message="The Meta draft copy appears to ask for or imply knowledge of private user information.",
                    artifact_type="creative_spec",
                    artifact_ref=artifact_ref,
                    evidence={"copy": copy_blob},
                )
            )
        if any(issue["ruleId"] == "META-COPY-003" for issue in copy_issues):
            findings.append(
                _new_finding(
                    ruleset=ruleset,
                    rule_id="META-COPY-003",
                    status="failed",
                    title="Copy appears discriminatory",
                    message="The Meta draft copy appears to contain discriminatory or exclusionary language.",
                    artifact_type="creative_spec",
                    artifact_ref=artifact_ref,
                    evidence={"copy": copy_blob},
                )
            )
        if _SIEP_RE.search(copy_blob):
            findings.append(
                _new_finding(
                    ruleset=ruleset,
                    rule_id="META-COPY-004",
                    status="needs_manual_review",
                    title="Potential SIEP copy detected",
                    message="The Meta draft copy contains possible social-issues, election, or politics keywords and needs manual review.",
                    artifact_type="creative_spec",
                    artifact_ref=artifact_ref,
                    evidence={"copy": copy_blob},
                )
            )
        if any(issue["ruleId"] == "META-COPY-005" for issue in copy_issues):
            findings.append(
                _new_finding(
                    ruleset=ruleset,
                    rule_id="META-COPY-005",
                    status="failed",
                    title="Negative self-perception language detected",
                    message="The Meta draft copy appears to use shaming or negative self-perception language.",
                    artifact_type="creative_spec",
                    artifact_ref=artifact_ref,
                    evidence={"copy": copy_blob},
                )
            )

        destination_value, destination_source = _creative_spec_destination(spec_dict)
        if not destination_value:
            findings.append(
                _new_finding(
                    ruleset=ruleset,
                    rule_id="META-LP-001",
                    status="failed",
                    title="Destination URL missing",
                    message="The Meta draft creative spec has no destination URL to review.",
                    artifact_type="creative_spec",
                    artifact_ref=artifact_ref,
                    evidence={"destinationSource": destination_source},
                )
            )
            continue

        public_destination = _resolve_public_destination_url(destination_value, review_base_url=review_base_url)
        if not public_destination:
            findings.append(
                _new_finding(
                    ruleset=ruleset,
                    rule_id="META-LP-002",
                    status="failed",
                    title="Destination URL is not public and absolute",
                    message="The Meta destination URL is not an absolute public URL that can be validated for launch review.",
                    artifact_type="creative_spec",
                    artifact_ref=artifact_ref,
                    evidence={
                        "destinationUrl": destination_value,
                        "destinationSource": destination_source,
                        "reviewBaseUrl": clean_optional_text(review_base_url),
                        "deployPublicBaseUrl": clean_optional_text(settings.DEPLOY_PUBLIC_BASE_URL),
                    },
                )
            )
            continue

        try:
            page = _landing_page_snapshot(public_destination)
        except httpx.HTTPError as exc:
            findings.append(
                _new_finding(
                    ruleset=ruleset,
                    rule_id="META-LP-003",
                    status="failed",
                    title="Destination URL could not be fetched",
                    message=f"The destination page could not be fetched: {exc}",
                    artifact_type="creative_spec",
                    artifact_ref=artifact_ref,
                    evidence={"destinationUrl": public_destination},
                )
            )
            continue

        body_text = page["bodyText"]
        if int(page["statusCode"]) >= 400:
            findings.append(
                _new_finding(
                    ruleset=ruleset,
                    rule_id="META-LP-003",
                    status="failed",
                    title="Destination URL returned an error status",
                    message=f"The destination page returned HTTP {page['statusCode']}.",
                    artifact_type="creative_spec",
                    artifact_ref=artifact_ref,
                    evidence=page,
                )
            )
        if _UNDER_CONSTRUCTION_RE.search(body_text):
            findings.append(
                _new_finding(
                    ruleset=ruleset,
                    rule_id="META-LP-004",
                    status="failed",
                    title="Destination appears incomplete",
                    message="The destination page appears to be under construction or incomplete.",
                    artifact_type="creative_spec",
                    artifact_ref=artifact_ref,
                    evidence=page,
                )
            )
        if not _PRIVACY_RE.search(body_text):
            findings.append(
                _new_finding(
                    ruleset=ruleset,
                    rule_id="META-LP-005",
                    status="failed",
                    title="Privacy policy marker not found on destination",
                    message="The destination page does not visibly reference privacy handling.",
                    artifact_type="creative_spec",
                    artifact_ref=artifact_ref,
                    evidence={"destinationUrl": public_destination, "finalUrl": page["finalUrl"]},
                )
            )
        if not (_CONTACT_RE.search(body_text) or _MAILTO_RE.search(body_text) or _PHONE_RE.search(body_text)):
            findings.append(
                _new_finding(
                    ruleset=ruleset,
                    rule_id="META-LP-006",
                    status="failed",
                    title="Contact or support marker not found on destination",
                    message="The destination page does not visibly expose contact or support information.",
                    artifact_type="creative_spec",
                    artifact_ref=artifact_ref,
                    evidence={"destinationUrl": public_destination, "finalUrl": page["finalUrl"]},
                )
            )

    return {
        "platform": "meta",
        "checkedRuleIds": checked_rule_ids,
        "findings": findings,
        "metadata": {
            "assessmentKind": "campaign",
            "campaignId": str(campaign.id),
            "creativeSpecCount": len(creative_specs),
            "adSetSpecCount": len(adset_specs),
            "readyAssetCount": len(ready_assets),
            "reviewBaseUrl": clean_optional_text(review_base_url),
            "profileValidation": _profile_metadata(platform_profile).get("metaGraphValidation"),
        },
    }


def summarize_findings(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts = defaultdict(int)
    manual_count = 0
    for finding in findings:
        counts[finding["severity"]] += 1
        if finding["status"] == "needs_manual_review":
            manual_count += 1
    return {
        "blockerCount": counts["blocker"],
        "highCount": counts["high"],
        "mediumCount": counts["medium"],
        "lowCount": counts["low"],
        "needsManualReviewCount": manual_count,
    }


def derive_run_status(findings: list[dict[str, Any]]) -> str:
    if any(finding["status"] == "failed" for finding in findings):
        return "failed"
    if any(finding["status"] == "needs_manual_review" for finding in findings):
        return "needs_manual_review"
    return "passed"


def render_report_markdown(
    *,
    subject_type: str,
    subject_id: str,
    platform: str,
    ruleset_version: str,
    status: str,
    checked_rule_ids: list[str],
    findings: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> str:
    summary = summarize_findings(findings)
    lines = [
        "# Paid Ads QA Report",
        "",
        f"- Generated at: `{datetime.now(timezone.utc).isoformat()}`",
        f"- Platform: `{platform}`",
        f"- Subject type: `{subject_type}`",
        f"- Subject id: `{subject_id}`",
        f"- Ruleset version: `{ruleset_version}`",
        f"- Status: `{status}`",
        f"- Checked rules: `{len(checked_rule_ids)}`",
        f"- Blockers: `{summary['blockerCount']}`",
        f"- High: `{summary['highCount']}`",
        f"- Medium: `{summary['mediumCount']}`",
        f"- Low: `{summary['lowCount']}`",
        f"- Manual review: `{summary['needsManualReviewCount']}`",
        "",
        "## Metadata",
        "",
        "```json",
        json.dumps(metadata, indent=2, sort_keys=True),
        "```",
        "",
        "## Findings",
        "",
    ]
    if not findings:
        lines.append("No findings.")
    else:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for finding in findings:
            grouped[finding["severity"]].append(finding)
        for severity in ("blocker", "high", "medium", "low"):
            bucket = grouped.get(severity) or []
            if not bucket:
                continue
            lines.extend([f"### {severity.title()}", ""])
            for finding in bucket:
                lines.append(f"- `{finding['ruleId']}` {finding['title']}")
                lines.append(f"  - Status: `{finding['status']}`")
                lines.append(f"  - Message: {finding['message']}")
                lines.append(f"  - Artifact: `{finding['artifactType']}` `{finding['artifactRef'] or '—'}`")
                lines.append(f"  - Source: `{finding['sourceTitle']}`")
                if finding.get("sourceUrl"):
                    lines.append(f"  - Source URL: {finding['sourceUrl']}")
                if finding.get("policyAnchorQuote"):
                    lines.append(f"  - Anchor quote: \"{finding['policyAnchorQuote']}\"")
                if finding.get("needsVerification"):
                    lines.append("  - Needs verification: `true`")
                if finding.get("fixGuidance"):
                    lines.append("  - Fix guidance:")
                    for item in finding["fixGuidance"]:
                        lines.append(f"    - {item}")
                if finding.get("evidence"):
                    lines.append("  - Evidence:")
                    lines.append("```json")
                    lines.append(json.dumps(finding["evidence"], indent=2, sort_keys=True))
                    lines.append("```")
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_report_file(
    *,
    run_id: str,
    subject_type: str,
    subject_id: str,
    platform: str,
    report_markdown: str,
) -> str:
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_subject = re.sub(r"[^a-zA-Z0-9._-]+", "-", subject_id).strip("-") or "subject"
    filename = f"paid_ads_qa_{platform}_{subject_type}_{safe_subject}_{run_id}.md"
    path = _REPORTS_DIR / filename
    path.write_text(report_markdown, encoding="utf-8")
    return str(path)
