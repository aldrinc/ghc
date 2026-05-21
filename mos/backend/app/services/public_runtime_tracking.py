from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Funnel
from app.db.repositories.paid_ads_qa import PaidAdsQaRepository
from app.services.paid_ads_qa import clean_optional_text, normalize_tracking_provider
from app.services.posthog_workspace_settings import resolve_client_posthog_tracking

_MOS_META_TRACKING_METADATA_KEY = "mosMetaTracking"
_MOS_POSTHOG_TRACKING_METADATA_KEY = "mosPosthogTracking"
_ALLOWED_POSTHOG_PERSON_PROFILES = {"identified_only", "always"}
_ALLOWED_POSTHOG_OVERRIDE_MODES = {"managed_reverse_proxy", "public_funnel_runtime"}


def _normalize_https_origin(value: Any) -> str | None:
    cleaned = clean_optional_text(str(value)) if value is not None else None
    if not cleaned:
        return None
    parsed = urlsplit(cleaned)
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _resolve_client_meta_platform_profile(*, session: Session, funnel: Funnel):
    return PaidAdsQaRepository(session).get_platform_profile(
        org_id=str(funnel.org_id),
        client_id=str(funnel.client_id),
        platform="meta",
    )


def resolve_public_meta_tracking(*, session: Session, funnel: Funnel) -> dict[str, str] | None:
    profile = _resolve_client_meta_platform_profile(session=session, funnel=funnel)
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
    pixel_id = clean_optional_text(mos_tracking.get("pixelId")) or clean_optional_text(profile.pixel_id)
    if not pixel_id:
        return None
    return {
        "provider": "meta",
        "mode": "public_funnel_runtime",
        "metaPixelId": pixel_id,
    }


def _resolve_posthog_metadata_override(*, session: Session, funnel: Funnel) -> dict[str, str] | None:
    profile = _resolve_client_meta_platform_profile(session=session, funnel=funnel)
    if profile is None:
        return None
    metadata = profile.metadata_json if isinstance(profile.metadata_json, dict) else {}
    posthog_tracking = metadata.get(_MOS_POSTHOG_TRACKING_METADATA_KEY)
    if not isinstance(posthog_tracking, dict):
        return None

    status = normalize_tracking_provider(posthog_tracking.get("status"))
    if status and status != "active":
        return None

    mode = normalize_tracking_provider(posthog_tracking.get("mode"))
    if mode and mode not in _ALLOWED_POSTHOG_OVERRIDE_MODES:
        raise RuntimeError(
            f"{_MOS_POSTHOG_TRACKING_METADATA_KEY}.mode must be one of "
            f"{sorted(_ALLOWED_POSTHOG_OVERRIDE_MODES)} when configured."
        )

    api_key = clean_optional_text(posthog_tracking.get("projectApiKey")) or clean_optional_text(
        posthog_tracking.get("posthogProjectApiKey")
    )
    defaults = clean_optional_text(posthog_tracking.get("defaults")) or clean_optional_text(
        posthog_tracking.get("posthogDefaults")
    )
    person_profiles = clean_optional_text(
        posthog_tracking.get("personProfiles")
    ) or clean_optional_text(posthog_tracking.get("posthogPersonProfiles"))
    api_host_raw = clean_optional_text(posthog_tracking.get("apiHost")) or clean_optional_text(
        posthog_tracking.get("posthogApiHost")
    )
    ui_host_raw = clean_optional_text(posthog_tracking.get("uiHost")) or clean_optional_text(
        posthog_tracking.get("posthogUiHost")
    )

    api_host = _normalize_https_origin(api_host_raw)
    ui_host = _normalize_https_origin(ui_host_raw)

    if api_host_raw and not api_host:
        raise RuntimeError(
            f"{_MOS_POSTHOG_TRACKING_METADATA_KEY}.apiHost must be an https origin without a path."
        )
    if ui_host_raw and not ui_host:
        raise RuntimeError(
            f"{_MOS_POSTHOG_TRACKING_METADATA_KEY}.uiHost must be an https origin without a path."
        )
    if person_profiles and person_profiles not in _ALLOWED_POSTHOG_PERSON_PROFILES:
        raise RuntimeError(
            f"{_MOS_POSTHOG_TRACKING_METADATA_KEY}.personProfiles must be one of "
            f"{sorted(_ALLOWED_POSTHOG_PERSON_PROFILES)} when configured."
        )

    resolved: dict[str, str] = {}
    if api_key:
        resolved["posthogProjectApiKey"] = api_key
    if defaults:
        resolved["posthogDefaults"] = defaults
    if person_profiles:
        resolved["posthogPersonProfiles"] = person_profiles
    if api_host:
        resolved["posthogApiHost"] = api_host
    if ui_host:
        resolved["posthogUiHost"] = ui_host
    return resolved or None


def resolve_public_posthog_tracking(*, session: Session, funnel: Funnel) -> dict[str, str] | None:
    if not settings.POSTHOG_FUNNELS_ENABLED:
        return None

    override = _resolve_posthog_metadata_override(session=session, funnel=funnel) or {}
    client_tracking = resolve_client_posthog_tracking(
        session=session,
        org_id=str(funnel.org_id),
        client_id=str(funnel.client_id),
    ) or {}
    api_key = override.get("posthogProjectApiKey") or clean_optional_text(
        client_tracking.get("posthogProjectApiKey")
    ) or clean_optional_text(
        settings.POSTHOG_FUNNELS_PROJECT_API_KEY
    )
    defaults = (
        override.get("posthogDefaults")
        or clean_optional_text(client_tracking.get("posthogDefaults"))
        or clean_optional_text(settings.POSTHOG_FUNNELS_DEFAULTS)
    )
    person_profiles = (
        override.get("posthogPersonProfiles")
        or clean_optional_text(client_tracking.get("posthogPersonProfiles"))
        or clean_optional_text(settings.POSTHOG_FUNNELS_PERSON_PROFILES)
        or "always"
    )

    if not api_key:
        raise RuntimeError(
            "POSTHOG_FUNNELS_PROJECT_API_KEY is required when POSTHOG_FUNNELS_ENABLED is true."
        )
    if not defaults:
        raise RuntimeError(
            "POSTHOG_FUNNELS_DEFAULTS is required when POSTHOG_FUNNELS_ENABLED is true."
        )
    if person_profiles not in _ALLOWED_POSTHOG_PERSON_PROFILES:
        raise RuntimeError(
            "POSTHOG_FUNNELS_PERSON_PROFILES must be 'identified_only' or 'always' when "
            "POSTHOG_FUNNELS_ENABLED is true."
        )

    api_host = (
        override.get("posthogApiHost")
        or clean_optional_text(client_tracking.get("posthogApiHost"))
        or clean_optional_text(settings.POSTHOG_FUNNELS_API_HOST)
    )
    ui_host = (
        override.get("posthogUiHost")
        or clean_optional_text(client_tracking.get("posthogUiHost"))
        or clean_optional_text(settings.POSTHOG_FUNNELS_UI_HOST)
    )

    if not api_host:
        raise RuntimeError(
            "POSTHOG_FUNNELS_API_HOST is required when POSTHOG_FUNNELS_ENABLED is true."
        )

    resolved = {
        "provider": "posthog",
        "mode": "public_funnel_runtime",
        "posthogProjectApiKey": api_key,
        "posthogApiHost": api_host,
        "posthogDefaults": defaults,
        "posthogPersonProfiles": person_profiles,
    }
    if ui_host:
        normalized_ui_host = _normalize_https_origin(ui_host)
        if not normalized_ui_host:
            raise RuntimeError("POSTHOG_FUNNELS_UI_HOST must be an https origin without a path.")
        resolved["posthogUiHost"] = normalized_ui_host
    return resolved


def resolve_public_runtime_tracking(
    *,
    session: Session,
    funnel: Funnel,
    include_posthog: bool,
) -> dict[str, str] | None:
    tracking: dict[str, str] = {}

    meta_tracking = resolve_public_meta_tracking(session=session, funnel=funnel)
    if meta_tracking:
        tracking.update(meta_tracking)

    if include_posthog:
        posthog_tracking = resolve_public_posthog_tracking(session=session, funnel=funnel)
        if posthog_tracking:
            tracking.update(posthog_tracking)
            if "provider" not in tracking or tracking["provider"] == "posthog":
                tracking["provider"] = "posthog"
            if "mode" not in tracking:
                tracking["mode"] = "public_funnel_runtime"

    return tracking or None
