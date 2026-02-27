import concurrent.futures
from contextvars import ContextVar
from datetime import datetime, timezone
import logging
import os
import re
import threading
import time
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.exc import DataError, StatementError
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.config import settings
from app.db.base import SessionLocal
from app.db.deps import get_session
from app.db.models import ClientUserPreference, Product
from app.db.repositories.assets import AssetsRepository
from app.db.repositories.clients import ClientsRepository
from app.db.repositories.design_systems import DesignSystemsRepository
from app.db.repositories.jobs import (
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SUCCEEDED,
    JobsRepository,
)
from app.db.repositories.shopify_theme_template_drafts import (
    ShopifyThemeTemplateDraftsRepository,
)
from app.db.repositories.products import ProductOffersRepository, ProductsRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.enums import ArtifactTypeEnum, AssetStatusEnum
from app.db.repositories.onboarding_payloads import OnboardingPayloadsRepository
from app.schemas.preferences import ActiveProductUpdateRequest
from app.schemas.common import ClientCreate
from app.schemas.clients import ClientDeleteRequest, ClientUpdateRequest
from app.schemas.onboarding import OnboardingStartRequest
from app.schemas.intent import CampaignIntentRequest
from app.schemas.shopify_connection import (
    ShopifyThemeBrandAuditRequest,
    ShopifyThemeBrandAuditResponse,
    ShopifyCreateProductRequest,
    ShopifyDefaultShopRequest,
    ShopifyInstallationDisconnectRequest,
    ShopifyInstallationAutoStorefrontTokenRequest,
    ShopifyProductListResponse,
    ShopifyProductCreateResponse,
    ShopifyConnectionStatusResponse,
    ShopifyInstallationUpdateRequest,
    ShopifyInstallUrlRequest,
    ShopifyInstallUrlResponse,
    ShopifyThemeBrandSyncRequest,
    ShopifyThemeBrandSyncJobStartResponse,
    ShopifyThemeBrandSyncJobProgress,
    ShopifyThemeBrandSyncJobStatusResponse,
    ShopifyThemeBrandSyncResponse,
    ShopifyThemeTemplateBuildJobStartResponse,
    ShopifyThemeTemplateBuildJobStatusResponse,
    ShopifyThemeTemplateBuildRequest,
    ShopifyThemeTemplateBuildResponse,
    ShopifyThemeTemplateDraftData,
    ShopifyThemeTemplateDraftResponse,
    ShopifyThemeTemplateDraftUpdateRequest,
    ShopifyThemeTemplateDraftVersionResponse,
    ShopifyThemeTemplateGenerateImagesJobStartResponse,
    ShopifyThemeTemplateGenerateImagesJobStatusResponse,
    ShopifyThemeTemplateGenerateImagesRequest,
    ShopifyThemeTemplateGenerateImagesResponse,
    ShopifyThemeTemplateImageSlot,
    ShopifyThemeTemplatePublishJobStartResponse,
    ShopifyThemeTemplatePublishJobStatusResponse,
    ShopifyThemeTemplatePublishRequest,
    ShopifyThemeTemplatePublishResponse,
    ShopifyThemeTemplateTextSlot,
)
from app.services.design_system_generation import (
    DesignSystemGenerationError,
    validate_design_system_tokens,
)
from app.services.funnels import (
    create_funnel_image_asset,
    create_funnel_unsplash_asset,
    resolve_funnel_image_model_config,
)
from app.services.media_storage import MediaStorage
from app.services.shopify_connection import (
    audit_client_shopify_theme_brand,
    auto_provision_client_shopify_storefront_token,
    build_client_shopify_install_url,
    create_client_shopify_product,
    disconnect_client_shopify_store,
    get_client_shopify_connection_status,
    list_client_shopify_theme_template_slots,
    list_client_shopify_products,
    list_shopify_installations,
    normalize_shop_domain,
    set_client_shopify_storefront_token,
    sync_client_shopify_theme_brand,
)
from app.services.shopify_theme_copy_agent import (
    generate_shopify_theme_component_copy,
)
from app.services.shopify_theme_content_planner import (
    plan_shopify_theme_component_content,
)
from app.temporal.client import get_temporal_client
from app.temporal.workflows.client_onboarding import (
    ClientOnboardingInput,
    ClientOnboardingWorkflow,
)
from app.temporal.workflows.campaign_intent import (
    CampaignIntentInput,
    CampaignIntentWorkflow,
)

router = APIRouter(prefix="/clients", tags=["clients"])
logger = logging.getLogger(__name__)

_JOB_TYPE_SHOPIFY_THEME_BRAND_SYNC = "shopify_theme_brand_sync"
_JOB_TYPE_SHOPIFY_THEME_TEMPLATE_BUILD = "shopify_theme_template_build"
_JOB_TYPE_SHOPIFY_THEME_TEMPLATE_GENERATE_IMAGES = "shopify_theme_template_generate_images"
_JOB_TYPE_SHOPIFY_THEME_TEMPLATE_PUBLISH = "shopify_theme_template_publish"
_JOB_SUBJECT_TYPE_CLIENT = "client"
_THEME_COMPONENT_HTML_TAG_RE = re.compile(
    r"</?\s*(?:p|strong|em|span|b|i|u|br|div|h[1-6]|li|ul|ol|a)\b[^<>]*>",
    re.IGNORECASE,
)
_THEME_COMPONENT_ORPHAN_CLOSING_TAG_RE = re.compile(
    r"/\s*(?:p|strong|em|span|b|i|u|br|div|h[1-6]|li|ul|ol|a)\b",
    re.IGNORECASE,
)
_THEME_FEATURE_IMAGE_SLOT_PATH_RE = re.compile(
    r"^templates/index\.json\.sections\.ss_feature_1_pro_[^.]+\.blocks\.slide_[^.]+\.settings\.image$",
    re.IGNORECASE,
)
_THEME_IMAGE_PROMPT_TEXT_HINT_MAX_LENGTH = 180
_THEME_IMAGE_PROMPT_GENERAL_CONTEXT_MAX_LENGTH = 2000
_THEME_IMAGE_PROMPT_SLOT_CONTEXT_MAX_LENGTH = 600
_THEME_IMAGE_PROMPT_BRAND_DESCRIPTION_MAX_LENGTH = 480
_THEME_IMAGE_PROMPT_METADATA_BRAND_DESCRIPTION_KEY = "brandDescription"
_THEME_COPY_GUIDELINE_MAX_LENGTH = 180
_THEME_COPY_OPTION_MAX_LENGTH = 32
_THEME_SYNC_AI_IMAGE_PROMPT_BASE = (
    "Premium ecommerce product image for a beauty-tech LED face mask brand. "
    "Modern skincare aesthetic, soft cinematic lighting, high detail, photoreal quality. "
    "No text, no logos, no watermark, no UI."
)
_THEME_SYNC_AI_IMAGE_ROLE_GUIDANCE_BY_NAME = {
    "hero": "Hero composition with the LED mask as the focal subject in a wide cinematic frame.",
    "gallery": "Product detail composition showing texture, contour, and premium materials.",
    "supporting": "Clean supporting visual tied to LED mask benefits and daily routine context.",
    "background": "Ambient background scene that complements the LED mask product.",
    "generic": "Lifestyle composition aligned to a premium beauty-tech brand.",
}
_THEME_SYNC_AI_IMAGE_ASPECT_RATIO_BY_RECOMMENDED_ASPECT = {
    "landscape": "16:9",
    "portrait": "3:4",
    "square": "1:1",
    "any": "4:3",
    "16:9": "16:9",
    "9:16": "9:16",
    "4:3": "4:3",
    "3:4": "3:4",
    "1:1": "1:1",
}
_GEMINI_IMAGE_REFERENCES_ENABLED_TRUE_VALUES = {"1", "true", "yes", "on"}
_THEME_SYNC_IMAGE_GENERATION_MAX_CONCURRENCY = max(
    1, settings.FUNNEL_IMAGE_GENERATION_MAX_CONCURRENCY
)
_SHOPIFY_TEMPLATE_IMAGE_GENERATION_MAX_CONCURRENCY = 1
_SHOPIFY_TEMPLATE_IMAGE_AUTO_RETRY_MAX_ATTEMPTS = 24
_SHOPIFY_TEMPLATE_IMAGE_AUTO_RETRY_BASE_DELAY_SECONDS = 8.0
_SHOPIFY_TEMPLATE_IMAGE_AUTO_RETRY_MAX_DELAY_SECONDS = 120.0
_UNSUPPORTED_THEME_TEXT_VALUE_TRANSLATION = str.maketrans(
    {
        '"': "",
        "'": "’",
        "<": "",
        ">": "",
        "\n": " ",
        "\r": " ",
    }
)
_THEME_SYNC_PROGRESS_CALLBACK: ContextVar[Any | None] = ContextVar(
    "theme_sync_progress_callback", default=None
)


def _has_explicit_gemini_hard_quota_signal(message: str) -> bool:
    if not isinstance(message, str):
        return False
    message_lower = message.lower()
    return (
        "exceeded your current quota" in message_lower
        or "quota exceeded" in message_lower
        or "insufficient quota" in message_lower
        or "billing account" in message_lower
        or "quota has been exhausted" in message_lower
    )


def _is_gemini_hard_quota_exhaustion_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    if "status=429" not in message:
        return False
    return _has_explicit_gemini_hard_quota_signal(message)


def _is_gemini_quota_or_rate_limit_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    if _is_gemini_hard_quota_exhaustion_error(exc):
        return True
    return (
        "status=429" in message
        or "too many requests" in message
        or "status=500" in message
        or "status=502" in message
        or "status=503" in message
        or "status=504" in message
        or "service is currently unavailable" in message
        or "temporarily unavailable" in message
    )


def _emit_theme_sync_progress(update: dict[str, Any]) -> None:
    callback = _THEME_SYNC_PROGRESS_CALLBACK.get()
    if not callable(callback):
        return
    try:
        callback(update)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to publish Shopify theme sync progress update")


def _normalize_asset_public_id(raw_public_id: Any) -> str | None:
    if isinstance(raw_public_id, UUID):
        return str(raw_public_id)
    if isinstance(raw_public_id, str):
        cleaned = raw_public_id.strip()
        if cleaned:
            return cleaned
    return None


def _coerce_non_negative_int(raw_value: Any) -> int | None:
    if isinstance(raw_value, bool):
        return None
    if isinstance(raw_value, int):
        return raw_value if raw_value >= 0 else None
    if isinstance(raw_value, str):
        cleaned = raw_value.strip()
        if cleaned and cleaned.isdigit():
            return int(cleaned)
    return None


def _normalize_theme_template_slot_path_filter(raw_slot_paths: Any) -> list[str]:
    if raw_slot_paths is None:
        return []
    if not isinstance(raw_slot_paths, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="slotPaths must be an array of non-empty strings when provided.",
        )
    normalized: list[str] = []
    seen: set[str] = set()
    for index, raw_path in enumerate(raw_slot_paths):
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"slotPaths[{index}] must be a non-empty string.",
            )
        slot_path = raw_path.strip()
        if slot_path in seen:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"slotPaths contains a duplicate path: {slot_path}",
            )
        seen.add(slot_path)
        normalized.append(slot_path)
    return normalized


@router.get("")
def list_clients(
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list:
    repo = ClientsRepository(session)
    return jsonable_encoder(repo.list(org_id=auth.org_id))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_client(
    payload: ClientCreate,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = ClientsRepository(session)
    client = repo.create(org_id=auth.org_id, name=payload.name, industry=payload.industry)
    return jsonable_encoder(client)


@router.get("/{client_id}")
def get_client(
    client_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = ClientsRepository(session)
    client = repo.get(org_id=auth.org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return jsonable_encoder(client)


def _serialize_active_product(product: Product) -> dict:
    return {
        "id": str(product.id),
        "title": product.title,
        "client_id": str(product.client_id),
        "product_type": product.product_type,
    }


def _get_client_or_404(*, session: Session, org_id: str, client_id: str):
    client = ClientsRepository(session).get(org_id=org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


def _require_client_exists(*, session: Session, org_id: str, client_id: str) -> None:
    _get_client_or_404(session=session, org_id=org_id, client_id=client_id)


def _require_public_asset_base_url() -> str:
    base_url = settings.PUBLIC_ASSET_BASE_URL
    if not isinstance(base_url, str) or not base_url.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "PUBLIC_ASSET_BASE_URL is required to sync Shopify theme brand assets. "
                "Set it in mos/backend and restart."
            ),
        )
    return base_url.rstrip("/")


def _get_client_user_pref(
    *, session: Session, org_id: str, client_id: str, user_external_id: str
) -> ClientUserPreference | None:
    return session.scalar(
        select(ClientUserPreference).where(
            ClientUserPreference.org_id == org_id,
            ClientUserPreference.client_id == client_id,
            ClientUserPreference.user_external_id == user_external_id,
        )
    )


def _get_selected_shop_domain(
    *, session: Session, org_id: str, client_id: str, user_external_id: str
) -> str | None:
    pref = _get_client_user_pref(
        session=session,
        org_id=org_id,
        client_id=client_id,
        user_external_id=user_external_id,
    )
    if not pref:
        return None
    selected = getattr(pref, "selected_shop_domain", None)
    if not isinstance(selected, str) or not selected.strip():
        return None
    return selected.strip().lower()


def _serialize_http_exception_detail(detail: Any) -> dict[str, Any]:
    if isinstance(detail, dict):
        return detail
    if isinstance(detail, list):
        return {"items": detail}
    if isinstance(detail, str):
        return {"message": detail}
    return {"message": str(detail)}


def _sanitize_theme_component_text_value(value: str) -> str:
    without_html_tags = _THEME_COMPONENT_HTML_TAG_RE.sub(" ", value)
    without_orphan_closing_tags = _THEME_COMPONENT_ORPHAN_CLOSING_TAG_RE.sub(
        " ", without_html_tags
    )
    sanitized = without_orphan_closing_tags.translate(
        _UNSUPPORTED_THEME_TEXT_VALUE_TRANSLATION
    )
    return " ".join(sanitized.split()).strip()


def _normalize_theme_copy_instruction_list(
    *,
    field_name: str,
    values: list[str] | None,
) -> list[str]:
    if values is None:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for index, raw_value in enumerate(values):
        if not isinstance(raw_value, str):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field_name}[{index}] must be a string.",
            )
        sanitized_value = _sanitize_theme_component_text_value(raw_value)
        if not sanitized_value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field_name}[{index}] cannot be empty.",
            )
        if len(sanitized_value) > _THEME_COPY_GUIDELINE_MAX_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"{field_name}[{index}] exceeds max length "
                    f"{_THEME_COPY_GUIDELINE_MAX_LENGTH}."
                ),
            )
        dedupe_key = sanitized_value.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(sanitized_value)
    return normalized


def _normalize_theme_copy_option_value(
    *,
    field_name: str,
    value: str | None,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} must be a string when provided.",
        )
    cleaned_value = value.strip()
    if not cleaned_value:
        return None
    if len(cleaned_value) > _THEME_COPY_OPTION_MAX_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} exceeds max length {_THEME_COPY_OPTION_MAX_LENGTH}.",
        )
    return cleaned_value


def _normalize_theme_copy_settings(
    *,
    tone_guidelines: list[str] | None,
    must_avoid_claims: list[str] | None,
    cta_style: str | None,
    reading_level: str | None,
    locale: str | None,
) -> dict[str, Any]:
    return {
        "toneGuidelines": _normalize_theme_copy_instruction_list(
            field_name="toneGuidelines",
            values=tone_guidelines,
        ),
        "mustAvoidClaims": _normalize_theme_copy_instruction_list(
            field_name="mustAvoidClaims",
            values=must_avoid_claims,
        ),
        "ctaStyle": _normalize_theme_copy_option_value(
            field_name="ctaStyle",
            value=cta_style,
        ),
        "readingLevel": _normalize_theme_copy_option_value(
            field_name="readingLevel",
            value=reading_level,
        ),
        "locale": _normalize_theme_copy_option_value(
            field_name="locale",
            value=locale,
        ),
    }


def _build_theme_copy_planner_kwargs(*, copy_settings: dict[str, Any]) -> dict[str, Any]:
    planner_kwargs: dict[str, Any] = {}
    tone_guidelines = copy_settings.get("toneGuidelines")
    if isinstance(tone_guidelines, list) and tone_guidelines:
        planner_kwargs["tone_guidelines"] = tone_guidelines
    must_avoid_claims = copy_settings.get("mustAvoidClaims")
    if isinstance(must_avoid_claims, list) and must_avoid_claims:
        planner_kwargs["must_avoid_claims"] = must_avoid_claims
    cta_style = copy_settings.get("ctaStyle")
    if isinstance(cta_style, str) and cta_style.strip():
        planner_kwargs["cta_style"] = cta_style.strip()
    reading_level = copy_settings.get("readingLevel")
    if isinstance(reading_level, str) and reading_level.strip():
        planner_kwargs["reading_level"] = reading_level.strip()
    locale = copy_settings.get("locale")
    if isinstance(locale, str) and locale.strip():
        planner_kwargs["locale"] = locale.strip()
    return planner_kwargs


def _resolve_theme_copy_settings_from_template_metadata(
    *,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    raw_tone_guidelines = metadata.get("copyToneGuidelines")
    raw_must_avoid_claims = metadata.get("copyMustAvoidClaims")
    raw_cta_style = metadata.get("copyCtaStyle")
    raw_reading_level = metadata.get("copyReadingLevel")
    raw_locale = metadata.get("copyLocale")
    if raw_tone_guidelines is not None and not isinstance(raw_tone_guidelines, list):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Stored Shopify template draft copy settings are invalid. "
                "copyToneGuidelines must be a list when present."
            ),
        )
    if raw_must_avoid_claims is not None and not isinstance(raw_must_avoid_claims, list):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Stored Shopify template draft copy settings are invalid. "
                "copyMustAvoidClaims must be a list when present."
            ),
        )
    if raw_cta_style is not None and not isinstance(raw_cta_style, str):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Stored Shopify template draft copy settings are invalid. "
                "copyCtaStyle must be a string when present."
            ),
        )
    if raw_reading_level is not None and not isinstance(raw_reading_level, str):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Stored Shopify template draft copy settings are invalid. "
                "copyReadingLevel must be a string when present."
            ),
        )
    if raw_locale is not None and not isinstance(raw_locale, str):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Stored Shopify template draft copy settings are invalid. "
                "copyLocale must be a string when present."
            ),
        )
    try:
        return _normalize_theme_copy_settings(
            tone_guidelines=raw_tone_guidelines,
            must_avoid_claims=raw_must_avoid_claims,
            cta_style=raw_cta_style,
            reading_level=raw_reading_level,
            locale=raw_locale,
        )
    except HTTPException as exc:
        detail_payload = _serialize_http_exception_detail(exc.detail)
        detail_message = detail_payload.get("message")
        if not isinstance(detail_message, str) or not detail_message.strip():
            detail_message = "Stored copy settings are invalid."
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Stored Shopify template draft copy settings are invalid. "
                f"{detail_message}"
            ),
        ) from exc


def _resolve_workspace_brand_description(
    *,
    session: Session,
    org_id: str,
    client_id: str,
) -> str | None:
    onboarding_payload = OnboardingPayloadsRepository(session).latest_for_client(
        org_id=org_id,
        client_id=client_id,
    )
    if onboarding_payload is None or not isinstance(onboarding_payload.data, dict):
        return None
    raw_brand_story = onboarding_payload.data.get("brand_story")
    if not isinstance(raw_brand_story, str) or not raw_brand_story.strip():
        return None
    brand_description = _sanitize_theme_component_text_value(raw_brand_story)
    if not brand_description:
        return None
    if len(brand_description) > _THEME_IMAGE_PROMPT_BRAND_DESCRIPTION_MAX_LENGTH:
        brand_description = brand_description[
            :_THEME_IMAGE_PROMPT_BRAND_DESCRIPTION_MAX_LENGTH
        ].rstrip()
    return brand_description


def _resolve_theme_sync_product_reference_image(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    product: Product,
) -> dict[str, Any]:
    product_id = str(product.id).strip()
    if not product_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Product id is required to resolve a Shopify theme image reference.",
        )

    assets_repo = AssetsRepository(session)
    reference_asset: Any | None = None

    primary_asset_id = getattr(product, "primary_asset_id", None)
    if isinstance(primary_asset_id, UUID):
        reference_asset = assets_repo.get(
            org_id=org_id,
            asset_id=str(primary_asset_id),
        )
        if reference_asset is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Product primary asset is missing. Set a valid primary image asset on the product "
                    "before generating Shopify template images with product visual context."
                ),
            )

    if reference_asset is None:
        try:
            product_image_assets = assets_repo.list(
                org_id=org_id,
                client_id=client_id,
                product_id=product_id,
                asset_kind="image",
                statuses=[AssetStatusEnum.approved, AssetStatusEnum.qa_passed],
            )
        except (DataError, StatementError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Product id is invalid for Shopify theme image reference lookup. "
                    f"productId={product_id}."
                ),
            ) from exc
        if not product_image_assets:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Product visual context is required for Shopify template image generation, "
                    "but no approved product images were found. Upload at least one product image "
                    "for this product and retry."
                ),
            )
        reference_asset = product_image_assets[0]

    reference_asset_client_id = str(getattr(reference_asset, "client_id", "")).strip()
    if reference_asset_client_id != client_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product reference asset must belong to this workspace.",
        )

    reference_asset_product_id_raw = getattr(reference_asset, "product_id", None)
    if reference_asset_product_id_raw is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Product reference asset must be linked to the selected product for Shopify template "
                "image generation."
            ),
        )
    reference_asset_product_id = str(reference_asset_product_id_raw).strip()
    if reference_asset_product_id != product_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Product reference asset does not belong to the selected product for Shopify template "
                "image generation."
            ),
        )

    storage_key = getattr(reference_asset, "storage_key", None)
    if not isinstance(storage_key, str) or not storage_key.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Product reference asset is missing media storage metadata (storage_key).",
        )

    storage = MediaStorage()
    try:
        reference_image_bytes, downloaded_mime_type = storage.download_bytes(
            key=storage_key.strip()
        )
    except Exception as exc:  # noqa: BLE001
        reference_asset_public_id = _normalize_asset_public_id(
            getattr(reference_asset, "public_id", None)
        ) or "unknown"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Failed to download product reference asset for Shopify template image generation. "
                f"assetPublicId={reference_asset_public_id}. Error: {exc}"
            ),
        ) from exc
    if not reference_image_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Product reference asset has empty media bytes.",
        )

    configured_mime_type = getattr(reference_asset, "content_type", None)
    mime_type_candidates = [configured_mime_type, downloaded_mime_type]
    reference_mime_type: str | None = None
    for candidate in mime_type_candidates:
        if isinstance(candidate, str) and candidate.strip().lower().startswith("image/"):
            reference_mime_type = candidate.strip()
            break
    if not reference_mime_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Product reference asset content type is not an image. "
                f"contentType={configured_mime_type!r}, downloadedContentType={downloaded_mime_type!r}."
            ),
        )

    reference_asset_public_id = _normalize_asset_public_id(
        getattr(reference_asset, "public_id", None)
    )
    if not reference_asset_public_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Product reference asset does not have a valid public id for Shopify template "
                "image generation."
            ),
        )

    reference_asset_id_raw = getattr(reference_asset, "id", None)
    if not isinstance(reference_asset_id_raw, UUID):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Product reference asset does not have a valid internal id for Shopify template "
                "image generation."
            ),
        )

    return {
        "imageBytes": reference_image_bytes,
        "mimeType": reference_mime_type,
        "assetPublicId": reference_asset_public_id,
        "assetId": str(reference_asset_id_raw),
    }


def _is_theme_feature_image_slot_path(slot_path: str) -> bool:
    return bool(_THEME_FEATURE_IMAGE_SLOT_PATH_RE.fullmatch(slot_path.strip()))


def _collect_theme_sync_text_values_by_path(
    *,
    text_slots: list[dict[str, Any]],
    component_text_values: dict[str, str] | None = None,
) -> dict[str, str]:
    text_values_by_path: dict[str, str] = {}
    for raw_slot in text_slots:
        if not isinstance(raw_slot, dict):
            continue
        raw_path = raw_slot.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        raw_value = raw_slot.get("currentValue")
        if not isinstance(raw_value, str) or not raw_value.strip():
            continue
        normalized_value = _sanitize_theme_component_text_value(raw_value)
        if not normalized_value:
            continue
        text_values_by_path[raw_path.strip()] = normalized_value

    for raw_path, raw_value in (component_text_values or {}).items():
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        if not isinstance(raw_value, str) or not raw_value.strip():
            continue
        normalized_value = _sanitize_theme_component_text_value(raw_value)
        if not normalized_value:
            continue
        text_values_by_path[raw_path.strip()] = normalized_value
    return text_values_by_path


def _build_theme_sync_slot_text_fragments(
    *,
    slot_path: str,
    text_values_by_path: dict[str, str],
) -> list[str]:
    slot_prefix, separator, _ = slot_path.partition(".settings.")
    if not separator:
        return []

    preferred_keys = ("title", "text", "heading", "subheading", "caption")
    text_fragments: list[str] = []
    for key in preferred_keys:
        candidate_path = f"{slot_prefix}.settings.{key}"
        candidate_value = text_values_by_path.get(candidate_path)
        if not candidate_value:
            continue
        if candidate_value in text_fragments:
            continue
        text_fragments.append(candidate_value)

    if not text_fragments:
        slot_text_prefix = f"{slot_prefix}.settings."
        for candidate_path, candidate_value in text_values_by_path.items():
            if not candidate_path.startswith(slot_text_prefix):
                continue
            if candidate_value in text_fragments:
                continue
            text_fragments.append(candidate_value)
            if len(text_fragments) >= 2:
                break
    return text_fragments


def _build_theme_sync_image_slot_text_hints(
    *,
    image_slots: list[dict[str, Any]],
    text_slots: list[dict[str, Any]],
    component_text_values: dict[str, str] | None = None,
    feature_slots_only: bool = True,
) -> dict[str, str]:
    if not image_slots or not text_slots:
        return {}

    text_values_by_path = _collect_theme_sync_text_values_by_path(
        text_slots=text_slots,
        component_text_values=component_text_values,
    )
    if not text_values_by_path:
        return {}

    hints_by_image_slot_path: dict[str, str] = {}
    for raw_image_slot in image_slots:
        if not isinstance(raw_image_slot, dict):
            continue
        raw_image_path = raw_image_slot.get("path")
        if not isinstance(raw_image_path, str) or not raw_image_path.strip():
            continue
        normalized_image_path = raw_image_path.strip()
        if feature_slots_only and not _is_theme_feature_image_slot_path(
            normalized_image_path
        ):
            continue
        text_fragments = _build_theme_sync_slot_text_fragments(
            slot_path=normalized_image_path,
            text_values_by_path=text_values_by_path,
        )
        if not text_fragments:
            continue

        combined_hint = " ".join(text_fragments).strip()
        if len(combined_hint) > _THEME_IMAGE_PROMPT_TEXT_HINT_MAX_LENGTH:
            combined_hint = combined_hint[:_THEME_IMAGE_PROMPT_TEXT_HINT_MAX_LENGTH].rstrip()
        if not combined_hint:
            continue
        hints_by_image_slot_path[normalized_image_path] = combined_hint

    return hints_by_image_slot_path


def _humanize_theme_slot_token(raw_value: str) -> str:
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", raw_value)
    normalized = re.sub(r"[_./-]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return "Image Slot"
    words = [word for word in normalized.split(" ") if word]
    return " ".join(word[:1].upper() + word[1:].lower() for word in words)


def _derive_theme_sync_slot_display_name(
    *,
    slot_path: str,
    slot_key: str,
    slot_role: str,
) -> str:
    haystack = f"{slot_role} {slot_key} {slot_path}".lower()
    if "feature" in haystack:
        return "Feature Image"
    if "hero" in haystack and ("icon" in haystack or "badge" in haystack):
        return "Hero Icon"
    if "hero" in haystack:
        return "Hero Image"
    if "gallery" in haystack:
        return "Gallery Image"
    if "review" in haystack or "testimonial" in haystack:
        return "Review Image"
    if slot_role.strip():
        return _humanize_theme_slot_token(slot_role)
    if slot_key.strip():
        return _humanize_theme_slot_token(slot_key)
    path_leaf = slot_path.split(".")[-1] if "." in slot_path else slot_path
    return _humanize_theme_slot_token(path_leaf)


def _build_theme_sync_default_general_prompt_context(
    *,
    draft_data: ShopifyThemeTemplateDraftData,
    product: Product,
    brand_description: str | None = None,
) -> str:
    context_segments: list[str] = []
    workspace_name = _sanitize_theme_component_text_value(draft_data.workspaceName)
    if workspace_name:
        context_segments.append(f"Workspace: {workspace_name}.")
    brand_name = _sanitize_theme_component_text_value(draft_data.brandName)
    if brand_name:
        context_segments.append(f"Brand: {brand_name}.")
    normalized_brand_description = _sanitize_theme_component_text_value(
        str(brand_description or "")
    )
    if normalized_brand_description:
        context_segments.append(
            f"Brand description: {normalized_brand_description}."
        )
    theme_name = _sanitize_theme_component_text_value(draft_data.themeName)
    if theme_name:
        context_segments.append(f"Shopify theme: {theme_name}.")
    theme_role = _sanitize_theme_component_text_value(draft_data.themeRole)
    if theme_role:
        context_segments.append(f"Theme role: {theme_role}.")

    product_title = _sanitize_theme_component_text_value(str(product.title or ""))
    if product_title:
        context_segments.append(f"Product: {product_title}.")
    product_type = _sanitize_theme_component_text_value(str(product.product_type or ""))
    if product_type:
        context_segments.append(f"Product type: {product_type}.")
    product_description = _sanitize_theme_component_text_value(str(product.description or ""))
    if product_description:
        if len(product_description) > 280:
            product_description = product_description[:280].rstrip()
        context_segments.append(f"Product summary: {product_description}.")
    benefit_values = [
        _sanitize_theme_component_text_value(str(item))
        for item in (product.primary_benefits or [])
        if isinstance(item, str) and item.strip()
    ]
    benefit_values = [item for item in benefit_values if item]
    if benefit_values:
        context_segments.append("Primary benefits: " + "; ".join(benefit_values[:4]) + ".")
    color_brand = draft_data.cssVars.get("--color-brand")
    if isinstance(color_brand, str) and color_brand.strip():
        context_segments.append(f"Primary brand color: {color_brand.strip()}.")
    color_cta = draft_data.cssVars.get("--color-cta")
    if isinstance(color_cta, str) and color_cta.strip():
        context_segments.append(f"CTA color: {color_cta.strip()}.")

    combined_context = " ".join(context_segments).strip()
    if not combined_context:
        return ""
    if len(combined_context) <= _THEME_IMAGE_PROMPT_GENERAL_CONTEXT_MAX_LENGTH:
        return combined_context
    return combined_context[:_THEME_IMAGE_PROMPT_GENERAL_CONTEXT_MAX_LENGTH].rstrip()


def _build_theme_sync_default_slot_prompt_context_by_path(
    *,
    image_slots: list[dict[str, Any]],
    text_slots: list[dict[str, Any]],
    component_text_values: dict[str, str] | None = None,
) -> dict[str, str]:
    text_values_by_path = _collect_theme_sync_text_values_by_path(
        text_slots=text_slots,
        component_text_values=component_text_values,
    )
    context_by_path: dict[str, str] = {}
    for raw_slot in image_slots:
        if not isinstance(raw_slot, dict):
            continue
        raw_path = raw_slot.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        slot_path = raw_path.strip()
        slot_key_raw = raw_slot.get("key")
        slot_key = (
            slot_key_raw.strip()
            if isinstance(slot_key_raw, str) and slot_key_raw.strip()
            else "image"
        )
        slot_role = _normalize_theme_slot_role(raw_slot.get("role"))
        slot_aspect = _normalize_theme_slot_recommended_aspect(
            raw_slot.get("recommendedAspect")
        )
        display_name = _derive_theme_sync_slot_display_name(
            slot_path=slot_path,
            slot_key=slot_key,
            slot_role=slot_role,
        )
        context_segments = [
            f"Purpose: {display_name}.",
            f"Slot role: {slot_role}.",
            f"Target slot key: {slot_key}.",
            f"Preferred aspect: {slot_aspect}.",
        ]
        text_fragments = _build_theme_sync_slot_text_fragments(
            slot_path=slot_path,
            text_values_by_path=text_values_by_path,
        )
        if text_fragments:
            related_text = " ".join(text_fragments).strip()
            if len(related_text) > _THEME_IMAGE_PROMPT_TEXT_HINT_MAX_LENGTH:
                related_text = related_text[:_THEME_IMAGE_PROMPT_TEXT_HINT_MAX_LENGTH].rstrip()
            if related_text:
                context_segments.append(f"Related copy context: {related_text}.")
        context_text = " ".join(context_segments).strip()
        if len(context_text) > _THEME_IMAGE_PROMPT_SLOT_CONTEXT_MAX_LENGTH:
            context_text = context_text[:_THEME_IMAGE_PROMPT_SLOT_CONTEXT_MAX_LENGTH].rstrip()
        if context_text:
            context_by_path[slot_path] = context_text
    return context_by_path


def _normalize_theme_slot_role(raw_role: Any) -> str:
    if not isinstance(raw_role, str):
        return "generic"
    normalized = raw_role.strip().lower()
    if normalized in {"hero", "gallery", "supporting", "background", "generic"}:
        return normalized
    return "generic"


def _normalize_theme_slot_recommended_aspect(raw_aspect: Any) -> str:
    if not isinstance(raw_aspect, str):
        return "any"
    normalized = raw_aspect.strip().lower()
    if normalized in {"landscape", "portrait", "square", "any", "16:9", "9:16", "4:3", "3:4", "1:1"}:
        return normalized
    return "any"


def _resolve_theme_slot_aspect_ratio(raw_recommended_aspect: Any) -> str:
    normalized = _normalize_theme_slot_recommended_aspect(raw_recommended_aspect)
    return _THEME_SYNC_AI_IMAGE_ASPECT_RATIO_BY_RECOMMENDED_ASPECT[normalized]


def _is_gemini_image_references_enabled() -> bool:
    raw_value = os.getenv("GEMINI_IMAGE_REFERENCES_ENABLED", "")
    return raw_value.strip().lower() in _GEMINI_IMAGE_REFERENCES_ENABLED_TRUE_VALUES


def _build_theme_sync_slot_image_prompt(
    *,
    slot_role: str,
    slot_key: str,
    aspect_ratio: str,
    variant_index: int,
    slot_text_hint: str | None = None,
    general_prompt_context: str | None = None,
    slot_prompt_context: str | None = None,
) -> str:
    role_guidance = _THEME_SYNC_AI_IMAGE_ROLE_GUIDANCE_BY_NAME.get(
        slot_role,
        _THEME_SYNC_AI_IMAGE_ROLE_GUIDANCE_BY_NAME["generic"],
    )
    base_prompt = (
        f"{_THEME_SYNC_AI_IMAGE_PROMPT_BASE} "
        f"{role_guidance} "
        f"Target slot key: {slot_key}. "
        f"Aspect ratio: {aspect_ratio}. "
        f"Variation: {variant_index}."
    )
    if isinstance(general_prompt_context, str) and general_prompt_context.strip():
        base_prompt = (
            f"{base_prompt} "
            f"Brand and campaign context: {general_prompt_context.strip()}."
        )
    if isinstance(slot_prompt_context, str) and slot_prompt_context.strip():
        base_prompt = (
            f"{base_prompt} "
            f"Slot-specific objective: {slot_prompt_context.strip()}."
        )
    if not isinstance(slot_text_hint, str) or not slot_text_hint.strip():
        return base_prompt
    return (
        f"{base_prompt} "
        f"Feature context: {slot_text_hint.strip()}. "
        "The image must visually represent this context."
    )


def _select_theme_sync_slots_for_ai_generation(
    *,
    image_slots: list[dict[str, Any]],
    max_images: int | None = None,
) -> list[dict[str, Any]]:
    normalized_slots: list[dict[str, Any]] = []
    for slot in image_slots:
        if not isinstance(slot, dict):
            continue
        raw_path = slot.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        normalized_slots.append(slot)
    if not normalized_slots:
        return []

    sorted_slots = sorted(normalized_slots, key=lambda item: str(item["path"]))
    if max_images is None:
        max_count = len(sorted_slots)
    elif max_images <= 0:
        return []
    else:
        max_count = min(max_images, len(sorted_slots))
    selected: list[dict[str, Any]] = []
    selected_indices: set[int] = set()
    seen_role_aspect: set[tuple[str, str]] = set()

    for idx, slot in enumerate(sorted_slots):
        role = _normalize_theme_slot_role(slot.get("role"))
        aspect = _normalize_theme_slot_recommended_aspect(slot.get("recommendedAspect"))
        role_aspect = (role, aspect)
        if role_aspect in seen_role_aspect:
            continue
        seen_role_aspect.add(role_aspect)
        selected.append(slot)
        selected_indices.add(idx)
        if len(selected) >= max_count:
            return selected

    for idx, slot in enumerate(sorted_slots):
        if len(selected) >= max_count:
            break
        if idx in selected_indices:
            continue
        selected.append(slot)
    return selected


def _generate_theme_sync_ai_image_assets(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    product_id: str | None,
    image_slots: list[dict[str, Any]],
    text_slots: list[dict[str, Any]] | None = None,
    general_prompt_context: str | None = None,
    slot_prompt_context_by_path: dict[str, str] | None = None,
    max_concurrency: int | None = None,
    stop_on_quota_exhausted: bool = False,
    reference_image_bytes: bytes | None = None,
    reference_image_mime_type: str | None = None,
    reference_asset_public_id: str | None = None,
    reference_asset_id: str | None = None,
) -> tuple[list[Any], list[str], dict[str, Any], list[str], dict[str, str]]:
    selected_slots = _select_theme_sync_slots_for_ai_generation(image_slots=image_slots)
    if not selected_slots:
        return [], [], {}, [], {}
    slot_text_hints = _build_theme_sync_image_slot_text_hints(
        image_slots=selected_slots,
        text_slots=text_slots or [],
    )
    normalized_slot_prompt_context_by_path: dict[str, str] = {}
    for raw_path, raw_context in (slot_prompt_context_by_path or {}).items():
        if (
            not isinstance(raw_path, str)
            or not raw_path.strip()
            or not isinstance(raw_context, str)
            or not raw_context.strip()
        ):
            continue
        normalized_slot_prompt_context_by_path[raw_path.strip()] = raw_context.strip()
    if reference_image_bytes is not None:
        if not reference_image_bytes:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Theme image reference bytes are empty.",
            )
        if not isinstance(reference_image_mime_type, str) or not reference_image_mime_type.strip():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Theme image reference mime type is required when reference bytes are provided.",
            )
        if not _is_gemini_image_references_enabled():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Product reference images are configured for Shopify theme generation, but "
                    "Gemini image references are disabled. Set GEMINI_IMAGE_REFERENCES_ENABLED=true "
                    "and retry."
                ),
            )
    elif reference_image_mime_type is not None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Theme image reference mime type was provided without reference bytes.",
        )

    def _generate_single_slot_asset(
        *,
        slot_path: str,
        slot_role: str,
        slot_recommended_aspect: str,
        aspect_ratio: str,
        prompt: str,
    ) -> dict[str, Any]:
        with SessionLocal() as slot_session:
            try:
                generated_asset = create_funnel_image_asset(
                    session=slot_session,
                    org_id=org_id,
                    client_id=client_id,
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                    usage_context={
                        "kind": "shopify_theme_sync_component_image",
                        "slotPath": slot_path,
                        "slotRole": slot_role,
                        "recommendedAspect": slot_recommended_aspect,
                    },
                    reference_image_bytes=reference_image_bytes,
                    reference_image_mime_type=reference_image_mime_type,
                    reference_asset_public_id=reference_asset_public_id,
                    reference_asset_id=reference_asset_id,
                    product_id=product_id,
                    tags=["shopify_theme_sync", "component_image", "ai_generated"],
                )
                return {
                    "slotPath": slot_path,
                    "asset": generated_asset,
                    "source": "ai",
                    "rateLimited": False,
                    "quotaExhausted": False,
                    "error": None,
                }
            except Exception as exc:  # noqa: BLE001
                if _is_gemini_hard_quota_exhaustion_error(exc):
                    return {
                        "slotPath": slot_path,
                        "asset": None,
                        "source": None,
                        "rateLimited": True,
                        "quotaExhausted": True,
                        "error": str(exc),
                    }
                if _is_gemini_quota_or_rate_limit_error(exc):
                    return {
                        "slotPath": slot_path,
                        "asset": None,
                        "source": None,
                        "rateLimited": True,
                        "quotaExhausted": False,
                        "error": str(exc),
                    }
                return {
                    "slotPath": slot_path,
                    "asset": None,
                    "source": None,
                    "rateLimited": False,
                    "quotaExhausted": False,
                    "error": str(exc),
                }

    prepared_slots: list[dict[str, Any]] = []
    generated_assets: list[Any] = []
    rate_limited_slot_paths: list[str] = []
    quota_exhausted_slot_paths: list[str] = []
    slot_error_by_path: dict[str, str] = {}
    generated_asset_by_slot_path: dict[str, Any] = {}
    variant_count_by_role_aspect: dict[tuple[str, str], int] = {}
    for slot in selected_slots:
        slot_path = str(slot["path"]).strip()
        slot_key_raw = slot.get("key")
        slot_key = (
            slot_key_raw.strip()
            if isinstance(slot_key_raw, str) and slot_key_raw.strip()
            else "image"
        )
        slot_role = _normalize_theme_slot_role(slot.get("role"))
        slot_recommended_aspect = _normalize_theme_slot_recommended_aspect(
            slot.get("recommendedAspect")
        )
        aspect_ratio = _resolve_theme_slot_aspect_ratio(slot_recommended_aspect)
        role_aspect = (slot_role, slot_recommended_aspect)
        variant_count = variant_count_by_role_aspect.get(role_aspect, 0) + 1
        variant_count_by_role_aspect[role_aspect] = variant_count
        prompt = _build_theme_sync_slot_image_prompt(
            slot_role=slot_role,
            slot_key=slot_key,
            aspect_ratio=aspect_ratio,
            variant_index=variant_count,
            slot_text_hint=slot_text_hints.get(slot_path),
            general_prompt_context=general_prompt_context,
            slot_prompt_context=normalized_slot_prompt_context_by_path.get(slot_path),
        )
        prepared_slots.append(
            {
                "slotPath": slot_path,
                "slotKey": slot_key,
                "slotRole": slot_role,
                "recommendedAspect": slot_recommended_aspect,
                "aspectRatio": aspect_ratio,
                "prompt": prompt,
            }
        )

    total_slots = len(prepared_slots)
    _emit_theme_sync_progress(
        {
            "stage": "image_generation",
            "message": "Generating component images for Shopify theme sync.",
            "totalImageSlots": total_slots,
            "completedImageSlots": 0,
            "generatedImageCount": 0,
            "skippedImageCount": 0,
        }
    )

    if not prepared_slots:
        return (
            generated_assets,
            rate_limited_slot_paths,
            generated_asset_by_slot_path,
            quota_exhausted_slot_paths,
            slot_error_by_path,
        )

    resolved_max_concurrency = _THEME_SYNC_IMAGE_GENERATION_MAX_CONCURRENCY
    if max_concurrency is not None:
        if not isinstance(max_concurrency, int) or max_concurrency < 1:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Image generation max_concurrency must be a positive integer.",
            )
        resolved_max_concurrency = max_concurrency
    max_workers = min(resolved_max_concurrency, len(prepared_slots))
    outcomes_by_path: dict[str, dict[str, Any]] = {}
    completed_count = 0
    generated_count = 0
    skipped_count = 0
    if max_workers == 1:
        hard_quota_exhausted = False
        hard_quota_slot_path: str | None = None
        for slot in prepared_slots:
            slot_path = slot["slotPath"]
            try:
                outcome = _generate_single_slot_asset(
                    slot_path=slot_path,
                    slot_role=slot["slotRole"],
                    slot_recommended_aspect=slot["recommendedAspect"],
                    aspect_ratio=slot["aspectRatio"],
                    prompt=slot["prompt"],
                )
            except Exception as exc:  # noqa: BLE001
                outcome = {
                    "slotPath": slot_path,
                    "asset": None,
                    "source": None,
                    "rateLimited": False,
                    "quotaExhausted": False,
                    "error": str(exc),
                }
            outcomes_by_path[slot_path] = outcome
            completed_count += 1
            if outcome.get("asset") is not None:
                if outcome.get("source") != "unsplash":
                    generated_count += 1
            elif outcome.get("rateLimited"):
                skipped_count += 1
            _emit_theme_sync_progress(
                {
                    "stage": "image_generation",
                    "message": "Generating component images for Shopify theme sync.",
                    "totalImageSlots": total_slots,
                    "completedImageSlots": completed_count,
                    "generatedImageCount": generated_count,
                    "skippedImageCount": skipped_count,
                }
            )
            if stop_on_quota_exhausted and outcome.get("quotaExhausted"):
                hard_quota_exhausted = True
                hard_quota_slot_path = slot_path
                break

        if hard_quota_exhausted and hard_quota_slot_path:
            for slot in prepared_slots:
                slot_path = slot["slotPath"]
                if slot_path in outcomes_by_path:
                    continue
                outcomes_by_path[slot_path] = {
                    "slotPath": slot_path,
                    "asset": None,
                    "source": None,
                    "rateLimited": True,
                    "quotaExhausted": False,
                    "error": (
                        "Skipped because hard Gemini quota exhaustion was detected "
                        f"at slotPath={hard_quota_slot_path}."
                    ),
                }
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures: dict[concurrent.futures.Future[dict[str, Any]], str] = {}
            for slot in prepared_slots:
                future = pool.submit(
                    _generate_single_slot_asset,
                    slot_path=slot["slotPath"],
                    slot_role=slot["slotRole"],
                    slot_recommended_aspect=slot["recommendedAspect"],
                    aspect_ratio=slot["aspectRatio"],
                    prompt=slot["prompt"],
                )
                futures[future] = slot["slotPath"]
            for future in concurrent.futures.as_completed(futures):
                slot_path = futures[future]
                try:
                    outcome = future.result()
                except Exception as exc:  # noqa: BLE001
                    outcome = {
                        "slotPath": slot_path,
                        "asset": None,
                        "source": None,
                        "rateLimited": False,
                        "quotaExhausted": False,
                        "error": str(exc),
                    }
                outcomes_by_path[slot_path] = outcome
                completed_count += 1
                if outcome.get("asset") is not None:
                    if outcome.get("source") != "unsplash":
                        generated_count += 1
                elif outcome.get("rateLimited"):
                    skipped_count += 1
                _emit_theme_sync_progress(
                    {
                        "stage": "image_generation",
                        "message": "Generating component images for Shopify theme sync.",
                        "totalImageSlots": total_slots,
                        "completedImageSlots": completed_count,
                        "generatedImageCount": generated_count,
                        "skippedImageCount": skipped_count,
                    }
                )

    for slot in prepared_slots:
        slot_path = slot["slotPath"]
        outcome = outcomes_by_path.get(slot_path) or {}
        generated_asset = outcome.get("asset")
        if generated_asset is None:
            raw_slot_error = outcome.get("error")
            if isinstance(raw_slot_error, str) and raw_slot_error.strip():
                slot_error_by_path[slot_path] = raw_slot_error.strip()
            if outcome.get("quotaExhausted"):
                logger.warning(
                    "Theme sync image generation failed for slot due Gemini hard quota exhaustion.",
                    extra={
                        "slotPath": slot_path,
                        "generationError": outcome.get("error"),
                    },
                )
                rate_limited_slot_paths.append(slot_path)
                quota_exhausted_slot_paths.append(slot_path)
                continue
            if outcome.get("rateLimited"):
                logger.warning(
                    "Theme sync image generation failed for slot due Gemini rate limit.",
                    extra={
                        "slotPath": slot_path,
                        "generationError": outcome.get("error"),
                    },
                )
                rate_limited_slot_paths.append(slot_path)
                continue
            error_message = str(outcome.get("error") or "Unknown image generation error.")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "AI theme image generation failed for Shopify sync. "
                    f"slotPath={slot_path}. {error_message}"
                ),
            )

        normalized_public_id = _normalize_asset_public_id(
            getattr(generated_asset, "public_id", None)
        )
        if not normalized_public_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "AI theme image generation produced an invalid asset response without public_id. "
                    f"slotPath={slot_path}."
                ),
            )
        width = (
            generated_asset.width
            if isinstance(getattr(generated_asset, "width", None), int)
            else None
        )
        height = (
            generated_asset.height
            if isinstance(getattr(generated_asset, "height", None), int)
            else None
        )
        generated_asset.width = width
        generated_asset.height = height
        generated_assets.append(generated_asset)
        generated_asset_by_slot_path[slot_path] = generated_asset

    return (
        generated_assets,
        rate_limited_slot_paths,
        generated_asset_by_slot_path,
        quota_exhausted_slot_paths,
        slot_error_by_path,
    )


def _normalize_theme_template_component_image_asset_map(
    component_image_asset_map_raw: dict[str, str] | None,
) -> dict[str, str]:
    normalized_component_image_asset_map: dict[str, str] = {}
    for raw_setting_path, raw_asset_public_id in (component_image_asset_map_raw or {}).items():
        if not isinstance(raw_setting_path, str) or not raw_setting_path.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="componentImageAssetMap keys must be non-empty strings.",
            )
        setting_path = raw_setting_path.strip()
        if setting_path in normalized_component_image_asset_map:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "componentImageAssetMap contains duplicate path after normalization: "
                    f"{setting_path}"
                ),
            )
        if not isinstance(raw_asset_public_id, str) or not raw_asset_public_id.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "componentImageAssetMap values must be non-empty asset public ids. "
                    f"Invalid value at path {setting_path}."
                ),
            )
        normalized_component_image_asset_map[setting_path] = raw_asset_public_id.strip()
    return normalized_component_image_asset_map


def _normalize_theme_template_component_text_values(
    component_text_values_raw: dict[str, str] | None,
) -> dict[str, str]:
    normalized_component_text_values: dict[str, str] = {}
    for raw_setting_path, raw_text_value in (component_text_values_raw or {}).items():
        if not isinstance(raw_setting_path, str) or not raw_setting_path.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="componentTextValues keys must be non-empty strings.",
            )
        setting_path = raw_setting_path.strip()
        if setting_path in normalized_component_text_values:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "componentTextValues contains duplicate path after normalization: "
                    f"{setting_path}"
                ),
            )
        if not isinstance(raw_text_value, str) or not raw_text_value.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "componentTextValues values must be non-empty strings. "
                    f"Invalid value at path {setting_path}."
                ),
            )
        sanitized_value = _sanitize_theme_component_text_value(raw_text_value)
        if not sanitized_value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "componentTextValues value became empty after sanitization. "
                    f"path={setting_path}."
                ),
            )
        normalized_component_text_values[setting_path] = sanitized_value
    return normalized_component_text_values


def _prepare_shopify_theme_template_build_data(
    *,
    client_id: str,
    payload: ShopifyThemeTemplateBuildRequest,
    auth: AuthContext,
    session: Session,
) -> ShopifyThemeTemplateDraftData:
    _emit_theme_sync_progress(
        {
            "stage": "preparing",
            "message": "Validating Shopify template build request and workspace data.",
        }
    )
    client = _get_client_or_404(session=session, org_id=auth.org_id, client_id=client_id)
    selected_shop_domain = _get_selected_shop_domain(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        user_external_id=auth.user_id,
    )
    effective_shop_domain = payload.shopDomain or selected_shop_domain
    status_payload = get_client_shopify_connection_status(
        client_id=client_id,
        selected_shop_domain=effective_shop_domain,
    )
    if status_payload["state"] != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Shopify connection is not ready: {status_payload['message']}",
        )

    requested_design_system_id = payload.designSystemId.strip() if payload.designSystemId else None
    resolved_design_system_id = requested_design_system_id or (
        str(client.design_system_id) if client.design_system_id else None
    )
    if not resolved_design_system_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "No design system selected for Shopify template build. "
                "Set a workspace default design system or provide designSystemId."
            ),
        )

    design_system_repo = DesignSystemsRepository(session)
    design_system = design_system_repo.get(
        org_id=auth.org_id,
        design_system_id=resolved_design_system_id,
    )
    if not design_system:
        if requested_design_system_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Design system not found"
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workspace default design system was not found.",
        )

    design_system_client_id = str(design_system.client_id) if design_system.client_id else None
    if design_system_client_id and design_system_client_id != client_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Design system must belong to this workspace.",
        )

    try:
        validated_tokens = validate_design_system_tokens(design_system.tokens)
    except DesignSystemGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    brand_obj = validated_tokens.get("brand")
    if not isinstance(brand_obj, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.brand must be a JSON object.",
        )
    brand_name_raw = brand_obj.get("name")
    if not isinstance(brand_name_raw, str) or not brand_name_raw.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.brand.name must be a non-empty string.",
        )
    logo_public_id_raw = brand_obj.get("logoAssetPublicId")
    if not isinstance(logo_public_id_raw, str) or not logo_public_id_raw.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.brand.logoAssetPublicId must be a non-empty string.",
        )
    brand_name = brand_name_raw.strip()
    logo_public_id = logo_public_id_raw.strip()

    css_vars_raw = validated_tokens.get("cssVars")
    if not isinstance(css_vars_raw, dict) or not css_vars_raw:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.cssVars must be a non-empty JSON object.",
        )
    css_vars: dict[str, str] = {}
    for raw_key, raw_value in css_vars_raw.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Design system tokens.cssVars keys must be non-empty strings.",
            )
        if not isinstance(raw_value, (str, int, float)):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Design system cssVars[{raw_key}] must be a string or number.",
            )
        if isinstance(raw_value, str):
            cleaned_value = raw_value.strip()
            if not cleaned_value:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Design system cssVars[{raw_key}] must not be an empty string.",
                )
        else:
            cleaned_value = str(raw_value)
        css_vars[raw_key.strip()] = cleaned_value

    font_urls_raw = validated_tokens.get("fontUrls")
    if not isinstance(font_urls_raw, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.fontUrls must be a list of non-empty strings.",
        )
    font_urls: list[str] = []
    for item in font_urls_raw:
        if not isinstance(item, str) or not item.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Design system tokens.fontUrls must be a list of non-empty strings.",
            )
        font_urls.append(item.strip())

    data_theme_raw = validated_tokens.get("dataTheme")
    if not isinstance(data_theme_raw, str) or not data_theme_raw.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.dataTheme must be a non-empty string.",
        )
    data_theme = data_theme_raw.strip()

    assets_repo = AssetsRepository(session)
    logo_asset = assets_repo.get_by_public_id(
        org_id=auth.org_id,
        public_id=logo_public_id,
        client_id=client_id,
    )
    if not logo_asset:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Design system brand.logoAssetPublicId does not reference an existing logo asset "
                "for this workspace."
            ),
        )

    normalized_component_image_asset_map = _normalize_theme_template_component_image_asset_map(
        payload.componentImageAssetMap
    )
    normalized_manual_component_text_values = _normalize_theme_template_component_text_values(
        payload.componentTextValues
    )
    copy_settings = _normalize_theme_copy_settings(
        tone_guidelines=payload.toneGuidelines,
        must_avoid_claims=payload.mustAvoidClaims,
        cta_style=payload.ctaStyle,
        reading_level=payload.readingLevel,
        locale=payload.locale,
    )
    planner_copy_kwargs = _build_theme_copy_planner_kwargs(copy_settings=copy_settings)

    requested_product_id = payload.productId.strip() if payload.productId else None
    resolved_product: Product | None = None
    resolved_product_storage_id: str | None = None
    if requested_product_id:
        product = ProductsRepository(session).get(
            org_id=auth.org_id, product_id=requested_product_id
        )
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product not found for productId={requested_product_id}.",
            )
        resolved_product = product
        product_client_id = str(product.client_id).strip()
        if product_client_id != client_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Product must belong to this workspace.",
            )
        resolved_product_storage_id = str(product.id).strip()

    workspace_name = str(client.name).strip()
    if not workspace_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Workspace name is required to build Shopify theme template drafts.",
        )
    workspace_brand_description = _resolve_workspace_brand_description(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
    )

    public_asset_base_url = _require_public_asset_base_url()
    logo_url = f"{public_asset_base_url}/public/assets/{logo_public_id}"

    for setting_path, asset_public_id in normalized_component_image_asset_map.items():
        mapped_asset = assets_repo.get_by_public_id(
            org_id=auth.org_id,
            public_id=asset_public_id,
            client_id=client_id,
        )
        if not mapped_asset:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "componentImageAssetMap references an asset that does not exist for this workspace. "
                    f"path={setting_path}, assetPublicId={asset_public_id}."
                ),
            )

    _emit_theme_sync_progress(
        {
            "stage": "discover_slots",
            "message": "Discovering theme component slots for template build.",
        }
    )
    discovered_slots = list_client_shopify_theme_template_slots(
        client_id=client_id,
        theme_id=payload.themeId,
        theme_name=payload.themeName,
        shop_domain=effective_shop_domain,
    )
    raw_image_slots = discovered_slots.get("imageSlots")
    raw_text_slots = discovered_slots.get("textSlots")
    image_slots = raw_image_slots if isinstance(raw_image_slots, list) else []
    text_slots = raw_text_slots if isinstance(raw_text_slots, list) else []

    explicit_image_paths = set(normalized_component_image_asset_map.keys())
    planner_image_slots = [
        slot
        for slot in image_slots
        if isinstance(slot, dict)
        and isinstance(slot.get("path"), str)
        and slot["path"] not in explicit_image_paths
    ]
    _emit_theme_sync_progress(
        {
            "stage": "discover_slots",
            "message": "Theme component slot discovery completed.",
            "totalImageSlots": len(planner_image_slots),
            "totalTextSlots": len(text_slots),
        }
    )

    if requested_product_id and not planner_image_slots and not text_slots:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "No image or text component slots were discovered for AI product content mapping. "
                f"productId={requested_product_id}."
            ),
        )

    generated_theme_assets: list[Any] = []
    generated_asset_by_slot_path: dict[str, Any] = {}
    rate_limited_slot_paths: list[str] = []
    quota_exhausted_slot_paths: list[str] = []
    slot_error_by_path: dict[str, str] = {}
    product_reference_image: dict[str, Any] | None = None
    if requested_product_id and resolved_product is not None and planner_image_slots:
        product_reference_image = _resolve_theme_sync_product_reference_image(
            session=session,
            org_id=auth.org_id,
            client_id=client_id,
            product=resolved_product,
        )
    if planner_image_slots:
        (
            generated_theme_assets,
            rate_limited_slot_paths,
            generated_asset_by_slot_path,
            quota_exhausted_slot_paths,
            slot_error_by_path,
        ) = _generate_theme_sync_ai_image_assets(
            session=session,
            org_id=auth.org_id,
            client_id=client_id,
            product_id=resolved_product_storage_id,
            image_slots=planner_image_slots,
            text_slots=text_slots,
            reference_image_bytes=(
                product_reference_image["imageBytes"] if product_reference_image else None
            ),
            reference_image_mime_type=(
                product_reference_image["mimeType"] if product_reference_image else None
            ),
            reference_asset_public_id=(
                product_reference_image["assetPublicId"]
                if product_reference_image
                else None
            ),
            reference_asset_id=(
                product_reference_image["assetId"] if product_reference_image else None
            ),
        )

    component_image_asset_map: dict[str, str] = dict(normalized_component_image_asset_map)
    component_text_values: dict[str, str] = {}
    copy_agent_model: str | None = None

    if requested_product_id and resolved_product is not None:
        product_image_assets = assets_repo.list(
            org_id=auth.org_id,
            client_id=client_id,
            product_id=resolved_product_storage_id,
            asset_kind="image",
            statuses=[AssetStatusEnum.approved, AssetStatusEnum.qa_passed],
        )
        product_image_assets_by_public_id: dict[str, Any] = {}
        for existing_asset in product_image_assets:
            normalized_existing_public_id = _normalize_asset_public_id(
                getattr(existing_asset, "public_id", None)
            )
            if not normalized_existing_public_id:
                continue
            product_image_assets_by_public_id[normalized_existing_public_id] = existing_asset
        for generated_asset in generated_theme_assets:
            normalized_public_id = _normalize_asset_public_id(
                getattr(generated_asset, "public_id", None)
            )
            if not normalized_public_id:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "AI theme image generation returned an asset without a valid public id. "
                        f"productId={requested_product_id}."
                    ),
                )
            if normalized_public_id in product_image_assets_by_public_id:
                continue
            product_image_assets_by_public_id[normalized_public_id] = generated_asset
            product_image_assets.append(generated_asset)
        if planner_image_slots and not product_image_assets:
            if rate_limited_slot_paths:
                if quota_exhausted_slot_paths:
                    first_quota_slot_path = quota_exhausted_slot_paths[0]
                    first_quota_error = slot_error_by_path.get(first_quota_slot_path)
                    first_quota_error_note = (
                        f" Gemini error: {first_quota_error}"
                        if isinstance(first_quota_error, str) and first_quota_error.strip()
                        else ""
                    )
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=(
                            "AI theme image generation exhausted Gemini quota for template build, "
                            "and no existing product images were available. "
                            f"productId={requested_product_id}. "
                            + first_quota_error_note
                            + " "
                            "Retry after quota reset or upload product images / provide componentImageAssetMap "
                            "for these slots: "
                            + ", ".join(sorted(quota_exhausted_slot_paths))
                        ),
                    )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        "AI theme image generation is rate-limited or out of Gemini quota for template build, "
                        "and no existing product images were available. "
                        f"productId={requested_product_id}. "
                        "Upload product images or provide componentImageAssetMap for these slots: "
                        + ", ".join(sorted(rate_limited_slot_paths))
                    ),
                )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "No usable product image assets were available for Shopify theme image slot planning. "
                    f"productId={requested_product_id}."
                ),
            )

        offers = ProductOffersRepository(session).list_by_product(
            product_id=str(resolved_product.id)
        )
        _emit_theme_sync_progress(
            {
                "stage": "planning_content",
                "message": "Planning product copy and image-to-slot assignments.",
                "totalImageSlots": len(planner_image_slots),
                "totalTextSlots": len(text_slots),
            }
        )
        try:
            planner_output = plan_shopify_theme_component_content(
                product=resolved_product,
                offers=offers,
                product_image_assets=product_image_assets,
                image_slots=planner_image_slots,
                text_slots=text_slots,
                **planner_copy_kwargs,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "AI theme component planner failed for template build. "
                    f"productId={requested_product_id}. {exc}"
                ),
            ) from exc

        planner_image_map = planner_output.get("componentImageAssetMap") or {}
        if not isinstance(planner_image_map, dict):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI theme component planner returned an invalid componentImageAssetMap payload.",
            )
        for setting_path, asset_public_id in planner_image_map.items():
            if not isinstance(setting_path, str) or not setting_path.strip():
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="AI theme component planner returned an invalid image mapping path.",
                )
            if not isinstance(asset_public_id, str) or not asset_public_id.strip():
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "AI theme component planner returned an invalid image mapping asset id "
                        f"for path {setting_path}."
                    ),
                )
            normalized_path = setting_path.strip()
            normalized_asset_public_id = asset_public_id.strip()
            if _is_theme_feature_image_slot_path(normalized_path):
                generated_feature_asset = generated_asset_by_slot_path.get(normalized_path)
                if generated_feature_asset is not None:
                    generated_feature_asset_public_id = _normalize_asset_public_id(
                        getattr(generated_feature_asset, "public_id", None)
                    )
                    if (
                        generated_feature_asset_public_id
                        and generated_feature_asset_public_id
                        in product_image_assets_by_public_id
                    ):
                        normalized_asset_public_id = generated_feature_asset_public_id
            if normalized_asset_public_id not in product_image_assets_by_public_id:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "AI theme component planner returned an image asset id that does not belong to "
                        "the product asset set. "
                        f"path={normalized_path}, assetPublicId={normalized_asset_public_id}."
                    ),
                )
            component_image_asset_map[normalized_path] = normalized_asset_public_id

        planner_text_values = planner_output.get("componentTextValues") or {}
        if not isinstance(planner_text_values, dict):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI theme component planner returned an invalid componentTextValues payload.",
            )
        for setting_path, value in planner_text_values.items():
            if not isinstance(setting_path, str) or not setting_path.strip():
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="AI theme component planner returned an invalid text mapping path.",
                )
            if not isinstance(value, str) or not value.strip():
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "AI theme component planner returned an invalid text value "
                        f"for path {setting_path}."
                    ),
                )
            normalized_path = setting_path.strip()
            sanitized_value = _sanitize_theme_component_text_value(value)
            if not sanitized_value:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "AI theme component planner returned text that became empty after "
                        f"sanitization for path {normalized_path}."
                    ),
                )
            component_text_values[normalized_path] = sanitized_value
        copy_agent_model_raw = planner_output.get("copyAgentModel")
        if isinstance(copy_agent_model_raw, str) and copy_agent_model_raw.strip():
            copy_agent_model = copy_agent_model_raw.strip()
    else:
        if rate_limited_slot_paths:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "AI theme image generation is rate-limited or out of Gemini quota for template build, "
                    "and productId was not provided for fallback product images. "
                    "Provide componentImageAssetMap for these slots: "
                    + ", ".join(sorted(rate_limited_slot_paths))
                ),
            )
        for slot_path, generated_asset in generated_asset_by_slot_path.items():
            normalized_public_id = _normalize_asset_public_id(
                getattr(generated_asset, "public_id", None)
            )
            if not normalized_public_id:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "AI theme image generation returned an asset without a valid public id. "
                        f"slotPath={slot_path}."
                    ),
                )
            component_image_asset_map[slot_path] = normalized_public_id

    for setting_path, asset_public_id in normalized_component_image_asset_map.items():
        component_image_asset_map[setting_path] = asset_public_id

    component_text_values.update(normalized_manual_component_text_values)

    component_image_urls: dict[str, str] = {}
    for setting_path, asset_public_id in component_image_asset_map.items():
        component_image_urls[setting_path] = (
            f"{public_asset_base_url}/public/assets/{asset_public_id}"
        )

    discovered_theme_id_raw = discovered_slots.get("themeId")
    discovered_theme_name_raw = discovered_slots.get("themeName")
    discovered_theme_role_raw = discovered_slots.get("themeRole")
    if not isinstance(discovered_theme_id_raw, str) or not discovered_theme_id_raw.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Theme slot discovery did not return a valid themeId.",
        )
    if not isinstance(discovered_theme_name_raw, str) or not discovered_theme_name_raw.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Theme slot discovery did not return a valid themeName.",
        )
    if not isinstance(discovered_theme_role_raw, str) or not discovered_theme_role_raw.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Theme slot discovery did not return a valid themeRole.",
        )

    image_slot_payloads: list[ShopifyThemeTemplateImageSlot] = []
    for raw_slot in image_slots:
        if not isinstance(raw_slot, dict):
            continue
        path = raw_slot.get("path")
        key = raw_slot.get("key")
        role = raw_slot.get("role")
        recommended_aspect = raw_slot.get("recommendedAspect")
        current_value = raw_slot.get("currentValue")
        if (
            not isinstance(path, str)
            or not path.strip()
            or not isinstance(key, str)
            or not key.strip()
            or not isinstance(role, str)
            or not role.strip()
            or not isinstance(recommended_aspect, str)
            or not recommended_aspect.strip()
        ):
            continue
        image_slot_payloads.append(
            ShopifyThemeTemplateImageSlot(
                path=path.strip(),
                key=key.strip(),
                role=role.strip(),
                recommendedAspect=recommended_aspect.strip(),
                currentValue=current_value if isinstance(current_value, str) else None,
            )
        )

    text_slot_payloads: list[ShopifyThemeTemplateTextSlot] = []
    for raw_slot in text_slots:
        if not isinstance(raw_slot, dict):
            continue
        path = raw_slot.get("path")
        key = raw_slot.get("key")
        current_value = raw_slot.get("currentValue")
        if (
            not isinstance(path, str)
            or not path.strip()
            or not isinstance(key, str)
            or not key.strip()
        ):
            continue
        text_slot_payloads.append(
            ShopifyThemeTemplateTextSlot(
                path=path.strip(),
                key=key.strip(),
                currentValue=current_value if isinstance(current_value, str) else None,
            )
        )

    metadata = {
        "componentImageUrlCount": len(component_image_urls),
        "componentTextValueCount": len(component_text_values),
        "generatedImageCount": len(generated_theme_assets),
        "rateLimitedSlotPaths": sorted(rate_limited_slot_paths),
    }
    copy_tone_guidelines = copy_settings.get("toneGuidelines")
    if isinstance(copy_tone_guidelines, list) and copy_tone_guidelines:
        metadata["copyToneGuidelines"] = copy_tone_guidelines
    copy_must_avoid_claims = copy_settings.get("mustAvoidClaims")
    if isinstance(copy_must_avoid_claims, list) and copy_must_avoid_claims:
        metadata["copyMustAvoidClaims"] = copy_must_avoid_claims
    copy_cta_style = copy_settings.get("ctaStyle")
    if isinstance(copy_cta_style, str) and copy_cta_style.strip():
        metadata["copyCtaStyle"] = copy_cta_style.strip()
    copy_reading_level = copy_settings.get("readingLevel")
    if isinstance(copy_reading_level, str) and copy_reading_level.strip():
        metadata["copyReadingLevel"] = copy_reading_level.strip()
    copy_locale = copy_settings.get("locale")
    if isinstance(copy_locale, str) and copy_locale.strip():
        metadata["copyLocale"] = copy_locale.strip()
    if isinstance(copy_agent_model, str) and copy_agent_model.strip():
        metadata["copyAgentModel"] = copy_agent_model.strip()
    if workspace_brand_description:
        metadata[_THEME_IMAGE_PROMPT_METADATA_BRAND_DESCRIPTION_KEY] = (
            workspace_brand_description
        )

    return ShopifyThemeTemplateDraftData(
        shopDomain=effective_shop_domain or str(status_payload.get("shopDomain") or ""),
        workspaceName=workspace_name,
        designSystemId=str(design_system.id),
        designSystemName=str(design_system.name),
        brandName=brand_name,
        logoAssetPublicId=logo_public_id,
        logoUrl=logo_url,
        themeId=discovered_theme_id_raw.strip(),
        themeName=discovered_theme_name_raw.strip(),
        themeRole=discovered_theme_role_raw.strip(),
        cssVars=css_vars,
        fontUrls=font_urls,
        dataTheme=data_theme,
        productId=requested_product_id,
        componentImageAssetMap=component_image_asset_map,
        componentTextValues=component_text_values,
        imageSlots=image_slot_payloads,
        textSlots=text_slot_payloads,
        metadata=metadata,
    )


def _serialize_shopify_theme_template_draft_version(
    *,
    version: Any,
) -> ShopifyThemeTemplateDraftVersionResponse:
    payload_raw = version.payload if isinstance(version.payload, dict) else {}
    try:
        data = ShopifyThemeTemplateDraftData(**payload_raw)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stored Shopify theme template draft version payload is invalid: {exc}",
        ) from exc

    return ShopifyThemeTemplateDraftVersionResponse(
        id=str(version.id),
        draftId=str(version.draft_id),
        versionNumber=int(version.version_number),
        source=str(version.source),
        notes=str(version.notes) if isinstance(version.notes, str) else None,
        createdByUserExternalId=(
            str(version.created_by_user_external_id)
            if isinstance(version.created_by_user_external_id, str)
            else None
        ),
        createdAt=version.created_at,
        data=data,
    )


def _serialize_shopify_theme_template_draft(
    *,
    draft: Any,
    latest_version: Any | None,
) -> ShopifyThemeTemplateDraftResponse:
    latest_version_payload: ShopifyThemeTemplateDraftVersionResponse | None = None
    if latest_version is not None:
        latest_version_payload = _serialize_shopify_theme_template_draft_version(
            version=latest_version
        )

    return ShopifyThemeTemplateDraftResponse(
        id=str(draft.id),
        status=str(draft.status),
        shopDomain=str(draft.shop_domain),
        themeId=str(draft.theme_id),
        themeName=str(draft.theme_name),
        themeRole=str(draft.theme_role),
        designSystemId=(str(draft.design_system_id) if draft.design_system_id else None),
        productId=(str(draft.product_id) if draft.product_id else None),
        createdByUserExternalId=(
            str(draft.created_by_user_external_id)
            if isinstance(draft.created_by_user_external_id, str)
            else None
        ),
        createdAt=draft.created_at,
        updatedAt=draft.updated_at,
        publishedAt=draft.published_at,
        latestVersion=latest_version_payload,
    )


def _resolve_component_image_urls_from_asset_map(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    component_image_asset_map: dict[str, str],
) -> dict[str, str]:
    public_asset_base_url = _require_public_asset_base_url()
    assets_repo = AssetsRepository(session)
    component_image_urls: dict[str, str] = {}
    for setting_path, asset_public_id in component_image_asset_map.items():
        mapped_asset = assets_repo.get_by_public_id(
            org_id=org_id,
            public_id=asset_public_id,
            client_id=client_id,
        )
        if not mapped_asset:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Stored theme template draft references an asset that does not exist for this workspace. "
                    f"path={setting_path}, assetPublicId={asset_public_id}."
                ),
            )
        component_image_urls[setting_path] = (
            f"{public_asset_base_url}/public/assets/{asset_public_id}"
        )
    return component_image_urls


def _run_client_shopify_theme_brand_sync_job(job_id: str) -> None:
    session = SessionLocal()
    progress_token = None
    try:
        jobs_repo = JobsRepository(session)
        job = jobs_repo.mark_running(job_id)
        if not job:
            return
        progress_state: dict[str, Any] = {
            "stage": "running",
            "message": "Shopify theme sync job started.",
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }

        def publish_progress(update: dict[str, Any]) -> None:
            if not isinstance(update, dict):
                return
            progress_state.update(update)
            progress_state["updatedAt"] = datetime.now(timezone.utc).isoformat()
            progress_session = SessionLocal()
            try:
                JobsRepository(progress_session).set_output(
                    job_id,
                    output={"progress": dict(progress_state)},
                )
            finally:
                progress_session.close()

        publish_progress({})
        progress_token = _THEME_SYNC_PROGRESS_CALLBACK.set(publish_progress)

        input_payload = job.input if isinstance(job.input, dict) else {}
        client_id = input_payload.get("clientId")
        raw_request_payload = input_payload.get("payload")
        raw_auth_context = input_payload.get("auth")

        if not isinstance(client_id, str) or not client_id.strip():
            publish_progress(
                {
                    "stage": "failed",
                    "message": "Queued job payload is missing clientId.",
                }
            )
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: missing clientId.",
                output={"progress": dict(progress_state)},
            )
            return
        if not isinstance(raw_request_payload, dict):
            publish_progress(
                {
                    "stage": "failed",
                    "message": "Queued job payload is missing sync request data.",
                }
            )
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: payload must be an object.",
                output={"progress": dict(progress_state)},
            )
            return
        if not isinstance(raw_auth_context, dict):
            publish_progress(
                {
                    "stage": "failed",
                    "message": "Queued job payload is missing auth context.",
                }
            )
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: auth context must be an object.",
                output={"progress": dict(progress_state)},
            )
            return

        user_id = raw_auth_context.get("userId")
        org_id = raw_auth_context.get("orgId")
        if (
            not isinstance(user_id, str)
            or not user_id.strip()
            or not isinstance(org_id, str)
            or not org_id.strip()
        ):
            publish_progress(
                {
                    "stage": "failed",
                    "message": "Queued job payload has invalid auth context values.",
                }
            )
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: missing auth.userId or auth.orgId.",
                output={"progress": dict(progress_state)},
            )
            return

        try:
            payload = ShopifyThemeBrandSyncRequest(**raw_request_payload)
        except Exception as exc:  # noqa: BLE001
            publish_progress(
                {
                    "stage": "failed",
                    "message": "Queued job payload failed validation.",
                }
            )
            jobs_repo.mark_failed(
                job_id,
                error=f"Invalid queued job payload: {exc}",
                output={"progress": dict(progress_state)},
            )
            return

        auth = AuthContext(user_id=user_id.strip(), org_id=org_id.strip())
        publish_progress(
            {
                "stage": "running",
                "message": "Running Shopify theme sync.",
            }
        )
        try:
            sync_response = sync_client_shopify_theme_brand_route(
                client_id=client_id.strip(),
                payload=payload,
                auth=auth,
                session=session,
            )
        except HTTPException as exc:
            detail_payload = _serialize_http_exception_detail(exc.detail)
            error_message = detail_payload.get("message")
            if not isinstance(error_message, str) or not error_message.strip():
                error_message = f"Shopify theme brand sync failed with status {exc.status_code}."
            publish_progress(
                {
                    "stage": "failed",
                    "message": error_message,
                }
            )
            jobs_repo.mark_failed(
                job_id,
                error=error_message,
                output={
                    "statusCode": exc.status_code,
                    "detail": detail_payload,
                    "progress": dict(progress_state),
                },
            )
            return

        if isinstance(sync_response, ShopifyThemeBrandSyncResponse):
            result_payload = sync_response.model_dump(mode="json")
        elif isinstance(sync_response, dict):
            result_payload = sync_response
        else:
            result_payload = jsonable_encoder(sync_response)

        publish_progress(
            {
                "stage": "succeeded",
                "message": "Shopify theme sync completed successfully.",
            }
        )
        jobs_repo.mark_succeeded(
            job_id,
            output={"result": result_payload, "progress": dict(progress_state)},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Unhandled exception while running Shopify theme brand sync job",
            extra={"job_id": job_id},
        )
        try:
            JobsRepository(session).mark_failed(
                job_id,
                error=str(exc) or "Unhandled error while running Shopify theme brand sync job.",
                output={
                    "progress": {
                        "stage": "failed",
                        "message": str(exc)
                        or "Unhandled error while running Shopify theme brand sync job.",
                        "updatedAt": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to mark Shopify theme brand sync job as failed after exception",
                extra={"job_id": job_id},
            )
    finally:
        if progress_token is not None:
            _THEME_SYNC_PROGRESS_CALLBACK.reset(progress_token)
        session.close()


def _build_or_update_shopify_theme_template_draft(
    *,
    client_id: str,
    payload: ShopifyThemeTemplateBuildRequest,
    auth: AuthContext,
    session: Session,
) -> ShopifyThemeTemplateBuildResponse:
    build_data = _prepare_shopify_theme_template_build_data(
        client_id=client_id,
        payload=payload,
        auth=auth,
        session=session,
    )
    drafts_repo = ShopifyThemeTemplateDraftsRepository(session)

    draft_id = payload.draftId.strip() if payload.draftId else None
    if draft_id:
        draft = drafts_repo.get(org_id=auth.org_id, client_id=client_id, draft_id=draft_id)
        if not draft:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shopify theme template draft not found.",
            )
        if str(draft.theme_id) != build_data.themeId:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Requested draft does not match the discovered Shopify theme. "
                    "Create a new draft or use the matching theme selector."
                ),
            )
        if str(draft.shop_domain).strip().lower() != build_data.shopDomain.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Requested draft belongs to a different Shopify store. "
                    "Build against the same shopDomain or create a new draft."
                ),
            )
        draft.design_system_id = build_data.designSystemId
        draft.product_id = build_data.productId
        draft.theme_name = build_data.themeName
        draft.theme_role = build_data.themeRole
        draft.status = "draft"
    else:
        draft = drafts_repo.create_draft(
            org_id=auth.org_id,
            client_id=client_id,
            design_system_id=build_data.designSystemId,
            product_id=build_data.productId,
            shop_domain=build_data.shopDomain,
            theme_id=build_data.themeId,
            theme_name=build_data.themeName,
            theme_role=build_data.themeRole,
            created_by_user_external_id=auth.user_id,
            status="draft",
        )

    version = drafts_repo.create_version(
        draft=draft,
        payload=build_data.model_dump(mode="json"),
        source="build_job",
        created_by_user_external_id=auth.user_id,
    )
    serialized_version = _serialize_shopify_theme_template_draft_version(version=version)
    serialized_draft = _serialize_shopify_theme_template_draft(
        draft=draft,
        latest_version=version,
    )
    return ShopifyThemeTemplateBuildResponse(
        draft=serialized_draft,
        version=serialized_version,
    )


def _generate_shopify_theme_template_draft_images(
    *,
    client_id: str,
    payload: ShopifyThemeTemplateGenerateImagesRequest,
    auth: AuthContext,
    session: Session,
    image_generation_max_concurrency: int | None = None,
    generate_text: bool = True,
) -> ShopifyThemeTemplateGenerateImagesResponse:
    drafts_repo = ShopifyThemeTemplateDraftsRepository(session)
    draft = drafts_repo.get(
        org_id=auth.org_id,
        client_id=client_id,
        draft_id=payload.draftId.strip(),
    )
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shopify theme template draft not found.",
        )
    latest_version = drafts_repo.get_latest_version(draft_id=str(draft.id))
    if not latest_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Shopify theme template draft has no versions to generate images from.",
        )

    latest_data = _serialize_shopify_theme_template_draft_version(
        version=latest_version
    ).data
    image_slots = [
        slot.model_dump(mode="json")
        for slot in latest_data.imageSlots
        if isinstance(slot.path, str) and slot.path.strip()
    ]
    text_slots = [slot.model_dump(mode="json") for slot in latest_data.textSlots]
    if not image_slots and not text_slots:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Template draft has no image or text slots available for generation.",
        )
    requested_image_model, requested_image_model_source = resolve_funnel_image_model_config()

    all_slot_paths = sorted(
        {
            str(slot.get("path")).strip()
            for slot in image_slots
            if isinstance(slot.get("path"), str) and str(slot.get("path")).strip()
        }
    )
    requested_slot_paths = _normalize_theme_template_slot_path_filter(payload.slotPaths)
    if requested_slot_paths:
        unknown_requested_slot_paths = sorted(
            {
                slot_path
                for slot_path in requested_slot_paths
                if slot_path not in all_slot_paths
            }
        )
        if unknown_requested_slot_paths:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "slotPaths contains one or more unknown template image slot paths: "
                    + ", ".join(unknown_requested_slot_paths)
                ),
            )
        generation_scope_slot_path_set = set(requested_slot_paths)
        generation_scope_slot_paths = list(requested_slot_paths)
    else:
        generation_scope_slot_path_set = set(all_slot_paths)
        generation_scope_slot_paths = list(all_slot_paths)
    next_component_image_asset_map = dict(latest_data.componentImageAssetMap)
    next_component_text_values = dict(latest_data.componentTextValues)
    latest_metadata = dict(latest_data.metadata or {})
    mapped_slot_paths = {
        raw_path.strip()
        for raw_path, raw_asset_public_id in next_component_image_asset_map.items()
        if isinstance(raw_path, str)
        and raw_path.strip()
        and isinstance(raw_asset_public_id, str)
        and raw_asset_public_id.strip()
    }
    image_slots_pending_generation = [
        slot
        for slot in image_slots
        if isinstance(slot.get("path"), str)
        and str(slot.get("path")).strip()
        and str(slot.get("path")).strip() in generation_scope_slot_path_set
        and str(slot.get("path")).strip() not in mapped_slot_paths
    ]
    should_generate_images = bool(image_slots_pending_generation)
    should_generate_text = bool(text_slots) and generate_text
    if not should_generate_images and not should_generate_text:
        serialized_draft = _serialize_shopify_theme_template_draft(
            draft=draft,
            latest_version=latest_version,
        )
        serialized_version = _serialize_shopify_theme_template_draft_version(
            version=latest_version
        )
        return ShopifyThemeTemplateGenerateImagesResponse(
            draft=serialized_draft,
            version=serialized_version,
            generatedImageCount=0,
            generatedTextCount=0,
            copyAgentModel=None,
            requestedImageModel=requested_image_model,
            requestedImageModelSource=requested_image_model_source,
            generatedSlotPaths=[],
            imageModels=[],
            imageModelBySlotPath={},
            imageSourceBySlotPath={},
            promptTokenCountBySlotPath={},
            promptTokenCountTotal=0,
            rateLimitedSlotPaths=[],
            remainingSlotPaths=[],
            quotaExhaustedSlotPaths=[],
            slotErrorsByPath={},
        )

    resolved_product_id = payload.productId.strip() if payload.productId else None
    if not resolved_product_id and isinstance(latest_data.productId, str):
        candidate = latest_data.productId.strip()
        if candidate:
            resolved_product_id = candidate
    if not resolved_product_id and isinstance(draft.product_id, UUID):
        resolved_product_id = str(draft.product_id)
    if not resolved_product_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Template image and copy generation requires a productId so assets and copy can "
                "be generated for a workspace product."
            ),
        )

    resolved_product = ProductsRepository(session).get(
        org_id=auth.org_id,
        product_id=resolved_product_id,
    )
    if not resolved_product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product not found for productId={resolved_product_id}.",
        )
    if str(resolved_product.client_id).strip() != client_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product must belong to this workspace.",
        )
    workspace_brand_description = _resolve_workspace_brand_description(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
    )
    rate_limited_slot_paths: list[str] = []
    quota_exhausted_slot_paths: list[str] = []
    slot_error_by_path: dict[str, str] = {}
    generated_asset_by_slot_path: dict[str, Any] = {}
    if should_generate_images:
        default_general_context = _build_theme_sync_default_general_prompt_context(
            draft_data=latest_data,
            product=resolved_product,
            brand_description=workspace_brand_description,
        )
        default_slot_context_by_path = _build_theme_sync_default_slot_prompt_context_by_path(
            image_slots=image_slots,
            text_slots=text_slots,
            component_text_values=latest_data.componentTextValues,
        )
        effective_general_context = default_general_context
        effective_slot_context_by_path = dict(default_slot_context_by_path)
        product_reference_image = _resolve_theme_sync_product_reference_image(
            session=session,
            org_id=auth.org_id,
            client_id=client_id,
            product=resolved_product,
        )

        _emit_theme_sync_progress(
            {
                "stage": "image_generation",
                "message": (
                    "Generating template images from deterministic slot requirements."
                    if not requested_slot_paths
                    else (
                        "Generating template images from deterministic slot requirements "
                        f"for {len(requested_slot_paths)} selected slot(s)."
                    )
                ),
                "totalImageSlots": len(image_slots_pending_generation),
                "completedImageSlots": 0,
                "generatedImageCount": 0,
                "fallbackImageCount": 0,
                "skippedImageCount": 0,
            }
        )
        (
            _,
            rate_limited_slot_paths,
            generated_asset_by_slot_path,
            quota_exhausted_slot_paths,
            slot_error_by_path,
        ) = _generate_theme_sync_ai_image_assets(
            session=session,
            org_id=auth.org_id,
            client_id=client_id,
            product_id=resolved_product_id,
            image_slots=image_slots_pending_generation,
            text_slots=text_slots,
            general_prompt_context=effective_general_context,
            slot_prompt_context_by_path=effective_slot_context_by_path,
            max_concurrency=image_generation_max_concurrency,
            stop_on_quota_exhausted=True,
            reference_image_bytes=product_reference_image["imageBytes"],
            reference_image_mime_type=product_reference_image["mimeType"],
            reference_asset_public_id=product_reference_image["assetPublicId"],
            reference_asset_id=product_reference_image["assetId"],
        )
        rate_limited_slot_paths = sorted(
            {
                slot_path.strip()
                for slot_path in rate_limited_slot_paths
                if isinstance(slot_path, str) and slot_path.strip()
            }
        )
        quota_exhausted_slot_paths = sorted(
            {
                slot_path.strip()
                for slot_path in quota_exhausted_slot_paths
                if isinstance(slot_path, str) and slot_path.strip()
            }
        )
    rate_limited_slot_path_set = set(rate_limited_slot_paths)

    generated_slot_paths: list[str] = []
    image_model_by_slot_path: dict[str, str] = {}
    image_source_by_slot_path: dict[str, str] = {}
    prompt_token_count_by_slot_path: dict[str, int] = {}
    for image_slot in image_slots_pending_generation:
        slot_path = str(image_slot["path"]).strip()
        generated_asset = generated_asset_by_slot_path.get(slot_path)
        if generated_asset is None:
            if slot_path in rate_limited_slot_path_set:
                continue
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Image generation did not return an asset for a required template slot. "
                    f"slotPath={slot_path}."
                ),
            )
        normalized_public_id = _normalize_asset_public_id(
            getattr(generated_asset, "public_id", None)
        )
        if not normalized_public_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Image generation returned an invalid asset without public_id. "
                    f"slotPath={slot_path}."
                ),
            )
        next_component_image_asset_map[slot_path] = normalized_public_id
        generated_slot_paths.append(slot_path)
        raw_ai_metadata = getattr(generated_asset, "ai_metadata", None)
        if isinstance(raw_ai_metadata, dict):
            raw_model = raw_ai_metadata.get("model")
            if isinstance(raw_model, str) and raw_model.strip():
                image_model_by_slot_path[slot_path] = raw_model.strip()
            raw_source = raw_ai_metadata.get("source")
            if isinstance(raw_source, str) and raw_source.strip():
                image_source_by_slot_path[slot_path] = raw_source.strip()
            raw_prompt_token_count = _coerce_non_negative_int(
                raw_ai_metadata.get("promptTokenCount")
            )
            if raw_prompt_token_count is not None:
                prompt_token_count_by_slot_path[slot_path] = raw_prompt_token_count
        if slot_path not in image_source_by_slot_path:
            raw_file_source = getattr(generated_asset, "file_source", None)
            if isinstance(raw_file_source, str) and raw_file_source.strip():
                image_source_by_slot_path[slot_path] = raw_file_source.strip()

    generated_component_text_values: dict[str, str] = {}
    copy_agent_model: str | None = None
    if should_generate_text:
        copy_settings = _resolve_theme_copy_settings_from_template_metadata(
            metadata=latest_metadata
        )
        planner_copy_kwargs = _build_theme_copy_planner_kwargs(copy_settings=copy_settings)
        offers = ProductOffersRepository(session).list_by_product(
            product_id=str(resolved_product.id)
        )
        _emit_theme_sync_progress(
            {
                "stage": "planning_content",
                "message": "Generating template copy for discovered text slots.",
                "totalTextSlots": len(text_slots),
            }
        )
        try:
            copy_agent_output = generate_shopify_theme_component_copy(
                product=resolved_product,
                offers=offers,
                text_slots=text_slots,
                **planner_copy_kwargs,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Theme copy agent failed for Shopify template generation. "
                    f"productId={resolved_product_id}. {exc}"
                ),
            ) from exc

        copy_text_values = copy_agent_output.get("componentTextValues")
        if not isinstance(copy_text_values, dict):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Theme copy agent returned an invalid componentTextValues payload.",
            )
        expected_text_slot_paths = {
            str(slot.get("path")).strip()
            for slot in text_slots
            if isinstance(slot.get("path"), str) and str(slot.get("path")).strip()
        }
        for setting_path, value in copy_text_values.items():
            if not isinstance(setting_path, str) or not setting_path.strip():
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Theme copy agent returned an invalid text mapping path.",
                )
            normalized_path = setting_path.strip()
            if normalized_path not in expected_text_slot_paths:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "Theme copy agent returned an unknown text slot path: "
                        f"{normalized_path}."
                    ),
                )
            if not isinstance(value, str) or not value.strip():
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "Theme copy agent returned an invalid text value for path "
                        f"{normalized_path}."
                    ),
                )
            sanitized_value = _sanitize_theme_component_text_value(value)
            if not sanitized_value:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "Theme copy agent returned text that became empty after sanitization "
                        f"for path {normalized_path}."
                    ),
                )
            if normalized_path in generated_component_text_values:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "Theme copy agent returned duplicate text mapping path "
                        f"{normalized_path}."
                    ),
                )
            generated_component_text_values[normalized_path] = sanitized_value
        if expected_text_slot_paths != set(generated_component_text_values.keys()):
            missing_paths = sorted(
                expected_text_slot_paths - set(generated_component_text_values.keys())
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Theme copy agent did not assign all text slots: "
                    + ", ".join(missing_paths)
                    + "."
                ),
            )
        next_component_text_values.update(generated_component_text_values)
        copy_model_raw = copy_agent_output.get("model")
        if isinstance(copy_model_raw, str) and copy_model_raw.strip():
            copy_agent_model = copy_model_raw.strip()

    normalized_component_image_asset_map = (
        _normalize_theme_template_component_image_asset_map(next_component_image_asset_map)
    )
    normalized_component_text_values = _normalize_theme_template_component_text_values(
        next_component_text_values
    )
    image_models = sorted(
        {
            model_name
            for model_name in image_model_by_slot_path.values()
            if isinstance(model_name, str) and model_name.strip()
        }
    )
    prompt_token_count_total = sum(prompt_token_count_by_slot_path.values())
    remaining_slot_paths = sorted(
        {
            slot_path
            for slot_path in generation_scope_slot_paths
            if slot_path not in normalized_component_image_asset_map
        }
    )

    if not generated_slot_paths and not generated_component_text_values:
        serialized_draft = _serialize_shopify_theme_template_draft(
            draft=draft,
            latest_version=latest_version,
        )
        serialized_version = _serialize_shopify_theme_template_draft_version(
            version=latest_version
        )
        return ShopifyThemeTemplateGenerateImagesResponse(
            draft=serialized_draft,
            version=serialized_version,
            generatedImageCount=0,
            generatedTextCount=0,
            copyAgentModel=None,
            requestedImageModel=requested_image_model,
            requestedImageModelSource=requested_image_model_source,
            generatedSlotPaths=[],
            imageModels=[],
            imageModelBySlotPath={},
            imageSourceBySlotPath={},
            promptTokenCountBySlotPath={},
            promptTokenCountTotal=0,
            rateLimitedSlotPaths=rate_limited_slot_paths,
            remainingSlotPaths=remaining_slot_paths,
            quotaExhaustedSlotPaths=quota_exhausted_slot_paths,
            slotErrorsByPath=slot_error_by_path,
        )

    merged_metadata = dict(latest_metadata)
    merged_metadata.update(
        {
            "generatedImageCount": len(generated_slot_paths),
            "generatedTextCount": len(generated_component_text_values),
            "rateLimitedSlotPaths": rate_limited_slot_paths,
            "remainingSlotPaths": remaining_slot_paths,
            "quotaExhaustedSlotPaths": quota_exhausted_slot_paths,
            "imageGenerationSlotCount": len(generated_slot_paths),
            "imageModels": image_models,
            "imageModelBySlotPath": image_model_by_slot_path,
            "imageSourceBySlotPath": image_source_by_slot_path,
            "requestedImageModel": requested_image_model,
            "requestedImageModelSource": requested_image_model_source,
            "promptTokenCountBySlotPath": prompt_token_count_by_slot_path,
            "promptTokenCountTotal": prompt_token_count_total,
            "componentImageAssetCount": len(normalized_component_image_asset_map),
            "componentTextValueCount": len(normalized_component_text_values),
        }
    )
    if should_generate_images:
        merged_metadata["imageGenerationGeneratedAt"] = datetime.now(timezone.utc).isoformat()
    if generated_component_text_values:
        merged_metadata["copyGenerationGeneratedAt"] = datetime.now(timezone.utc).isoformat()
    if isinstance(copy_agent_model, str) and copy_agent_model.strip():
        merged_metadata["copyAgentModel"] = copy_agent_model.strip()
    if workspace_brand_description:
        merged_metadata[_THEME_IMAGE_PROMPT_METADATA_BRAND_DESCRIPTION_KEY] = (
            workspace_brand_description
        )

    next_data = latest_data.model_copy(
        update={
            "productId": resolved_product_id,
            "componentImageAssetMap": normalized_component_image_asset_map,
            "componentTextValues": normalized_component_text_values,
            "metadata": merged_metadata,
        }
    )
    draft.product_id = resolved_product.id
    next_version = drafts_repo.create_version(
        draft=draft,
        payload=next_data.model_dump(mode="json"),
        source="agent_image_generation_job",
        created_by_user_external_id=auth.user_id,
    )
    serialized_draft = _serialize_shopify_theme_template_draft(
        draft=draft,
        latest_version=next_version,
    )
    serialized_version = _serialize_shopify_theme_template_draft_version(
        version=next_version
    )
    return ShopifyThemeTemplateGenerateImagesResponse(
        draft=serialized_draft,
        version=serialized_version,
        generatedImageCount=len(generated_slot_paths),
        generatedTextCount=len(generated_component_text_values),
        copyAgentModel=copy_agent_model,
        requestedImageModel=requested_image_model,
        requestedImageModelSource=requested_image_model_source,
        generatedSlotPaths=sorted(generated_slot_paths),
        imageModels=image_models,
        imageModelBySlotPath=image_model_by_slot_path,
        imageSourceBySlotPath=image_source_by_slot_path,
        promptTokenCountBySlotPath=prompt_token_count_by_slot_path,
        promptTokenCountTotal=prompt_token_count_total,
        rateLimitedSlotPaths=rate_limited_slot_paths,
        remainingSlotPaths=remaining_slot_paths,
        quotaExhaustedSlotPaths=quota_exhausted_slot_paths,
        slotErrorsByPath=slot_error_by_path,
    )


def _publish_shopify_theme_template_draft(
    *,
    client_id: str,
    payload: ShopifyThemeTemplatePublishRequest,
    auth: AuthContext,
    session: Session,
) -> ShopifyThemeTemplatePublishResponse:
    drafts_repo = ShopifyThemeTemplateDraftsRepository(session)
    draft = drafts_repo.get(
        org_id=auth.org_id,
        client_id=client_id,
        draft_id=payload.draftId.strip(),
    )
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shopify theme template draft not found.",
        )
    version = drafts_repo.get_latest_version(draft_id=str(draft.id))
    if not version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Shopify theme template draft has no versions to publish.",
        )

    serialized_version = _serialize_shopify_theme_template_draft_version(version=version)
    draft_data = serialized_version.data

    status_payload = get_client_shopify_connection_status(
        client_id=client_id,
        selected_shop_domain=draft_data.shopDomain,
    )
    if status_payload["state"] != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Shopify connection is not ready for template publish: "
                f"{status_payload['message']}"
            ),
        )

    component_image_asset_map = _normalize_theme_template_component_image_asset_map(
        draft_data.componentImageAssetMap
    )
    component_text_values = _normalize_theme_template_component_text_values(
        draft_data.componentTextValues
    )
    component_image_urls = _resolve_component_image_urls_from_asset_map(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        component_image_asset_map=component_image_asset_map,
    )

    _emit_theme_sync_progress(
        {
            "stage": "sync_theme",
            "message": "Publishing approved Shopify theme template draft.",
            "componentImageUrlCount": len(component_image_urls),
            "componentTextValueCount": len(component_text_values),
        }
    )
    synced = sync_client_shopify_theme_brand(
        client_id=client_id,
        workspace_name=draft_data.workspaceName,
        brand_name=draft_data.brandName,
        logo_url=draft_data.logoUrl,
        css_vars=draft_data.cssVars,
        font_urls=draft_data.fontUrls,
        data_theme=draft_data.dataTheme,
        component_image_urls=component_image_urls,
        component_text_values=component_text_values,
        auto_component_image_urls=[],
        theme_id=draft_data.themeId,
        theme_name=None,
        shop_domain=draft_data.shopDomain,
    )

    drafts_repo.mark_published(draft=draft)
    serialized_draft = _serialize_shopify_theme_template_draft(
        draft=draft,
        latest_version=version,
    )
    sync_response = ShopifyThemeBrandSyncResponse(
        shopDomain=synced["shopDomain"],
        workspaceName=draft_data.workspaceName,
        designSystemId=draft_data.designSystemId,
        designSystemName=draft_data.designSystemName,
        brandName=draft_data.brandName,
        logoAssetPublicId=draft_data.logoAssetPublicId,
        logoUrl=draft_data.logoUrl,
        themeId=synced["themeId"],
        themeName=synced["themeName"],
        themeRole=synced["themeRole"],
        layoutFilename=synced["layoutFilename"],
        cssFilename=synced["cssFilename"],
        settingsFilename=synced.get("settingsFilename"),
        jobId=synced["jobId"],
        coverage=synced["coverage"],
        settingsSync=synced["settingsSync"],
    )

    return ShopifyThemeTemplatePublishResponse(
        draft=serialized_draft,
        version=serialized_version,
        sync=sync_response,
    )


def _run_client_shopify_theme_template_build_job(job_id: str) -> None:
    session = SessionLocal()
    progress_token = None
    try:
        jobs_repo = JobsRepository(session)
        job = jobs_repo.mark_running(job_id)
        if not job:
            return
        progress_state: dict[str, Any] = {
            "stage": "running",
            "message": "Shopify theme template build job started.",
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }

        def publish_progress(update: dict[str, Any]) -> None:
            if not isinstance(update, dict):
                return
            progress_state.update(update)
            progress_state["updatedAt"] = datetime.now(timezone.utc).isoformat()
            progress_session = SessionLocal()
            try:
                JobsRepository(progress_session).set_output(
                    job_id,
                    output={"progress": dict(progress_state)},
                )
            finally:
                progress_session.close()

        publish_progress({})
        progress_token = _THEME_SYNC_PROGRESS_CALLBACK.set(publish_progress)

        input_payload = job.input if isinstance(job.input, dict) else {}
        client_id = input_payload.get("clientId")
        raw_request_payload = input_payload.get("payload")
        raw_auth_context = input_payload.get("auth")

        if not isinstance(client_id, str) or not client_id.strip():
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: missing clientId.",
                output={"progress": dict(progress_state)},
            )
            return
        if not isinstance(raw_request_payload, dict):
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: payload must be an object.",
                output={"progress": dict(progress_state)},
            )
            return
        if not isinstance(raw_auth_context, dict):
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: auth context must be an object.",
                output={"progress": dict(progress_state)},
            )
            return

        user_id = raw_auth_context.get("userId")
        org_id = raw_auth_context.get("orgId")
        if (
            not isinstance(user_id, str)
            or not user_id.strip()
            or not isinstance(org_id, str)
            or not org_id.strip()
        ):
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: missing auth.userId or auth.orgId.",
                output={"progress": dict(progress_state)},
            )
            return

        try:
            payload = ShopifyThemeTemplateBuildRequest(**raw_request_payload)
        except Exception as exc:  # noqa: BLE001
            jobs_repo.mark_failed(
                job_id,
                error=f"Invalid queued job payload: {exc}",
                output={"progress": dict(progress_state)},
            )
            return

        auth = AuthContext(user_id=user_id.strip(), org_id=org_id.strip())
        publish_progress(
            {
                "stage": "running",
                "message": "Building Shopify theme template draft.",
            }
        )
        try:
            build_response = _build_or_update_shopify_theme_template_draft(
                client_id=client_id.strip(),
                payload=payload,
                auth=auth,
                session=session,
            )
        except HTTPException as exc:
            detail_payload = _serialize_http_exception_detail(exc.detail)
            error_message = detail_payload.get("message")
            if not isinstance(error_message, str) or not error_message.strip():
                error_message = (
                    f"Shopify theme template build failed with status {exc.status_code}."
                )
            publish_progress({"stage": "failed", "message": error_message})
            jobs_repo.mark_failed(
                job_id,
                error=error_message,
                output={
                    "statusCode": exc.status_code,
                    "detail": detail_payload,
                    "progress": dict(progress_state),
                },
            )
            return

        result_payload = build_response.model_dump(mode="json")
        publish_progress(
            {
                "stage": "succeeded",
                "message": "Shopify theme template draft built successfully.",
                "draftId": build_response.draft.id,
                "draftVersionNumber": build_response.version.versionNumber,
            }
        )
        jobs_repo.mark_succeeded(
            job_id,
            output={"result": result_payload, "progress": dict(progress_state)},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Unhandled exception while running Shopify theme template build job",
            extra={"job_id": job_id},
        )
        try:
            JobsRepository(session).mark_failed(
                job_id,
                error=str(exc) or "Unhandled error while running Shopify theme template build job.",
                output={
                    "progress": {
                        "stage": "failed",
                        "message": str(exc)
                        or "Unhandled error while running Shopify theme template build job.",
                        "updatedAt": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to mark Shopify theme template build job as failed after exception",
                extra={"job_id": job_id},
            )
    finally:
        if progress_token is not None:
            _THEME_SYNC_PROGRESS_CALLBACK.reset(progress_token)
        session.close()


def _compute_shopify_template_image_retry_delay_seconds(attempt_number: int) -> float:
    if attempt_number <= 1:
        return 0.0
    retry_power = max(0, attempt_number - 2)
    delay_seconds = _SHOPIFY_TEMPLATE_IMAGE_AUTO_RETRY_BASE_DELAY_SECONDS * (2**retry_power)
    return min(_SHOPIFY_TEMPLATE_IMAGE_AUTO_RETRY_MAX_DELAY_SECONDS, delay_seconds)


def _generate_shopify_theme_template_draft_images_with_retry(
    *,
    client_id: str,
    payload: ShopifyThemeTemplateGenerateImagesRequest,
    auth: AuthContext,
    session: Session,
    publish_progress: Any,
) -> ShopifyThemeTemplateGenerateImagesResponse:
    aggregated_slot_paths: set[str] = set()
    aggregated_generated_text_count = 0
    aggregated_copy_agent_model: str | None = None
    aggregated_model_by_slot_path: dict[str, str] = {}
    aggregated_source_by_slot_path: dict[str, str] = {}
    aggregated_prompt_token_count_by_slot_path: dict[str, int] = {}
    aggregated_slot_errors_by_path: dict[str, str] = {}
    last_remaining_slot_paths: list[str] = []
    final_response: ShopifyThemeTemplateGenerateImagesResponse | None = None

    max_attempts = max(1, _SHOPIFY_TEMPLATE_IMAGE_AUTO_RETRY_MAX_ATTEMPTS)
    template_max_concurrency = max(
        1,
        min(
            _THEME_SYNC_IMAGE_GENERATION_MAX_CONCURRENCY,
            _SHOPIFY_TEMPLATE_IMAGE_GENERATION_MAX_CONCURRENCY,
        ),
    )
    for attempt_number in range(1, max_attempts + 1):
        if attempt_number > 1:
            delay_seconds = _compute_shopify_template_image_retry_delay_seconds(
                attempt_number
            )
            publish_progress(
                {
                    "stage": "waiting_for_retry",
                    "message": (
                        "Template image generation is rate-limited. "
                        f"Retrying pending slots in {delay_seconds:.0f}s "
                        f"(attempt {attempt_number}/{max_attempts})."
                    ),
                    "generatedImageCount": len(aggregated_slot_paths),
                    "skippedImageCount": len(last_remaining_slot_paths),
                }
            )
            time.sleep(delay_seconds)

        publish_progress(
            {
                "stage": "running",
                "message": (
                    "Generating images for Shopify theme template draft "
                    f"(attempt {attempt_number}/{max_attempts}, "
                    f"concurrency={template_max_concurrency})."
                ),
                "generatedImageCount": len(aggregated_slot_paths),
                "skippedImageCount": len(last_remaining_slot_paths),
            }
        )
        response = _generate_shopify_theme_template_draft_images(
            client_id=client_id,
            payload=payload,
            auth=auth,
            session=session,
            image_generation_max_concurrency=template_max_concurrency,
            generate_text=attempt_number == 1,
        )
        final_response = response

        if response.generatedTextCount > 0:
            aggregated_generated_text_count = max(
                aggregated_generated_text_count,
                response.generatedTextCount,
            )
        if (
            aggregated_copy_agent_model is None
            and isinstance(response.copyAgentModel, str)
            and response.copyAgentModel.strip()
        ):
            aggregated_copy_agent_model = response.copyAgentModel.strip()
        aggregated_slot_paths.update(response.generatedSlotPaths)
        aggregated_model_by_slot_path.update(response.imageModelBySlotPath)
        aggregated_source_by_slot_path.update(response.imageSourceBySlotPath)
        for slot_path, raw_error in response.slotErrorsByPath.items():
            if (
                not isinstance(slot_path, str)
                or not slot_path.strip()
                or not isinstance(raw_error, str)
                or not raw_error.strip()
            ):
                continue
            aggregated_slot_errors_by_path[slot_path.strip()] = raw_error.strip()
        for slot_path in response.generatedSlotPaths:
            if not isinstance(slot_path, str) or not slot_path.strip():
                continue
            aggregated_slot_errors_by_path.pop(slot_path.strip(), None)
        for slot_path, raw_prompt_token_count in response.promptTokenCountBySlotPath.items():
            if not isinstance(slot_path, str) or not slot_path.strip():
                continue
            normalized_prompt_token_count = _coerce_non_negative_int(raw_prompt_token_count)
            if normalized_prompt_token_count is None:
                continue
            aggregated_prompt_token_count_by_slot_path[
                slot_path.strip()
            ] = normalized_prompt_token_count
        quota_exhausted_slot_paths = sorted(
            {
                slot_path.strip()
                for slot_path in response.quotaExhaustedSlotPaths
                if isinstance(slot_path, str) and slot_path.strip()
            }
        )
        if quota_exhausted_slot_paths:
            generated_so_far = len(aggregated_slot_paths)
            model_note = (
                f" model={response.requestedImageModel}, source={response.requestedImageModelSource}."
                if isinstance(response.requestedImageModel, str)
                and response.requestedImageModel.strip()
                else ""
            )
            first_quota_slot_path = quota_exhausted_slot_paths[0]
            first_quota_error = response.slotErrorsByPath.get(first_quota_slot_path)
            first_quota_error_note = (
                f" Gemini error: {first_quota_error}"
                if isinstance(first_quota_error, str) and first_quota_error.strip()
                else ""
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "Template image generation stopped early because Gemini quota is exhausted. "
                    f"Generated {generated_so_far} slot(s) before stopping.{model_note}"
                    f"{first_quota_error_note} "
                    "Retry once quota resets. Slots: "
                    + ", ".join(quota_exhausted_slot_paths)
                ),
            )

        remaining_slot_paths = sorted(
            {
                slot_path.strip()
                for slot_path in response.remainingSlotPaths
                if isinstance(slot_path, str) and slot_path.strip()
            }
        )
        rate_limited_slot_paths = sorted(
            {
                slot_path.strip()
                for slot_path in response.rateLimitedSlotPaths
                if isinstance(slot_path, str) and slot_path.strip()
            }
        )
        last_remaining_slot_paths = remaining_slot_paths
        if not remaining_slot_paths:
            break

        if not rate_limited_slot_paths:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Template image generation left pending image slots without a retryable "
                    "rate-limit signal. Remaining slots: "
                    + ", ".join(remaining_slot_paths)
                ),
            )

    if final_response is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Template image generation did not produce a response payload.",
        )

    if last_remaining_slot_paths:
        first_remaining_slot_path = last_remaining_slot_paths[0]
        first_remaining_slot_error = aggregated_slot_errors_by_path.get(first_remaining_slot_path)
        first_remaining_slot_error_note = (
            f" Latest Gemini error: {first_remaining_slot_error} "
            if isinstance(first_remaining_slot_error, str) and first_remaining_slot_error.strip()
            else ""
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Template image generation remained rate-limited after "
                f"{max_attempts} attempts."
                f"{first_remaining_slot_error_note}"
                "Remaining slots: "
                + ", ".join(last_remaining_slot_paths)
            ),
        )

    if (
        not aggregated_slot_paths
        and final_response.generatedImageCount == 0
        and not final_response.generatedSlotPaths
    ):
        return final_response.model_copy(
            update={
                "generatedTextCount": aggregated_generated_text_count,
                "copyAgentModel": aggregated_copy_agent_model,
            }
        )

    merged_model_by_slot_path = dict(aggregated_model_by_slot_path)
    merged_source_by_slot_path = dict(aggregated_source_by_slot_path)
    merged_prompt_token_count_by_slot_path = dict(
        sorted(aggregated_prompt_token_count_by_slot_path.items())
    )
    merged_slot_errors_by_path = dict(sorted(aggregated_slot_errors_by_path.items()))
    merged_image_models = sorted(
        {
            model_name.strip()
            for model_name in merged_model_by_slot_path.values()
            if isinstance(model_name, str) and model_name.strip()
        }
    )
    merged_prompt_token_count_total = sum(merged_prompt_token_count_by_slot_path.values())

    return final_response.model_copy(
        update={
            "generatedImageCount": len(aggregated_slot_paths),
            "generatedTextCount": aggregated_generated_text_count,
            "copyAgentModel": aggregated_copy_agent_model,
            "generatedSlotPaths": sorted(aggregated_slot_paths),
            "imageModels": merged_image_models,
            "imageModelBySlotPath": merged_model_by_slot_path,
            "imageSourceBySlotPath": merged_source_by_slot_path,
            "promptTokenCountBySlotPath": merged_prompt_token_count_by_slot_path,
            "promptTokenCountTotal": merged_prompt_token_count_total,
            "rateLimitedSlotPaths": [],
            "remainingSlotPaths": [],
            "quotaExhaustedSlotPaths": [],
            "slotErrorsByPath": merged_slot_errors_by_path,
        }
    )


def _run_client_shopify_theme_template_generate_images_job(job_id: str) -> None:
    session = SessionLocal()
    progress_token = None
    try:
        jobs_repo = JobsRepository(session)
        job = jobs_repo.mark_running(job_id)
        if not job:
            return
        progress_state: dict[str, Any] = {
            "stage": "running",
            "message": "Shopify template image and copy generation job started.",
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }

        def publish_progress(update: dict[str, Any]) -> None:
            if not isinstance(update, dict):
                return
            progress_state.update(update)
            progress_state["updatedAt"] = datetime.now(timezone.utc).isoformat()
            progress_session = SessionLocal()
            try:
                JobsRepository(progress_session).set_output(
                    job_id,
                    output={"progress": dict(progress_state)},
                )
            finally:
                progress_session.close()

        publish_progress({})
        progress_token = _THEME_SYNC_PROGRESS_CALLBACK.set(publish_progress)

        input_payload = job.input if isinstance(job.input, dict) else {}
        client_id = input_payload.get("clientId")
        raw_request_payload = input_payload.get("payload")
        raw_auth_context = input_payload.get("auth")

        if not isinstance(client_id, str) or not client_id.strip():
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: missing clientId.",
                output={"progress": dict(progress_state)},
            )
            return
        if not isinstance(raw_request_payload, dict):
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: payload must be an object.",
                output={"progress": dict(progress_state)},
            )
            return
        if not isinstance(raw_auth_context, dict):
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: auth context must be an object.",
                output={"progress": dict(progress_state)},
            )
            return

        user_id = raw_auth_context.get("userId")
        org_id = raw_auth_context.get("orgId")
        if (
            not isinstance(user_id, str)
            or not user_id.strip()
            or not isinstance(org_id, str)
            or not org_id.strip()
        ):
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: missing auth.userId or auth.orgId.",
                output={"progress": dict(progress_state)},
            )
            return

        try:
            payload = ShopifyThemeTemplateGenerateImagesRequest(**raw_request_payload)
        except Exception as exc:  # noqa: BLE001
            jobs_repo.mark_failed(
                job_id,
                error=f"Invalid queued job payload: {exc}",
                output={"progress": dict(progress_state)},
            )
            return

        auth = AuthContext(user_id=user_id.strip(), org_id=org_id.strip())
        requested_image_model, requested_image_model_source = (
            resolve_funnel_image_model_config()
        )
        publish_progress(
            {
                "stage": "running",
                "message": (
                    "Generating images and copy for Shopify theme template draft "
                    f"(model={requested_image_model}, source={requested_image_model_source})."
                ),
            }
        )
        try:
            generate_images_response = _generate_shopify_theme_template_draft_images_with_retry(
                client_id=client_id.strip(),
                payload=payload,
                auth=auth,
                session=session,
                publish_progress=publish_progress,
            )
        except HTTPException as exc:
            detail_payload = _serialize_http_exception_detail(exc.detail)
            error_message = detail_payload.get("message")
            if not isinstance(error_message, str) or not error_message.strip():
                error_message = (
                    "Shopify template image generation failed "
                    f"with status {exc.status_code}."
                )
            publish_progress({"stage": "failed", "message": error_message})
            jobs_repo.mark_failed(
                job_id,
                error=error_message,
                output={
                    "statusCode": exc.status_code,
                    "detail": detail_payload,
                    "progress": dict(progress_state),
                },
            )
            return

        result_payload = generate_images_response.model_dump(mode="json")
        publish_progress(
            {
                "stage": "succeeded",
                "message": "Shopify template images and copy generated successfully.",
                "draftId": generate_images_response.draft.id,
                "draftVersionNumber": generate_images_response.version.versionNumber,
                "generatedImageCount": generate_images_response.generatedImageCount,
                "generatedTextCount": generate_images_response.generatedTextCount,
            }
        )
        jobs_repo.mark_succeeded(
            job_id,
            output={"result": result_payload, "progress": dict(progress_state)},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Unhandled exception while running Shopify theme template image generation job",
            extra={"job_id": job_id},
        )
        try:
            JobsRepository(session).mark_failed(
                job_id,
                error=str(exc)
                or "Unhandled error while running Shopify template image generation job.",
                output={
                    "progress": {
                        "stage": "failed",
                        "message": str(exc)
                        or "Unhandled error while running Shopify template image generation job.",
                        "updatedAt": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to mark Shopify template image generation job as failed after exception",
                extra={"job_id": job_id},
            )
    finally:
        if progress_token is not None:
            _THEME_SYNC_PROGRESS_CALLBACK.reset(progress_token)
        session.close()


def _run_client_shopify_theme_template_publish_job(job_id: str) -> None:
    session = SessionLocal()
    progress_token = None
    try:
        jobs_repo = JobsRepository(session)
        job = jobs_repo.mark_running(job_id)
        if not job:
            return
        progress_state: dict[str, Any] = {
            "stage": "running",
            "message": "Shopify theme template publish job started.",
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }

        def publish_progress(update: dict[str, Any]) -> None:
            if not isinstance(update, dict):
                return
            progress_state.update(update)
            progress_state["updatedAt"] = datetime.now(timezone.utc).isoformat()
            progress_session = SessionLocal()
            try:
                JobsRepository(progress_session).set_output(
                    job_id,
                    output={"progress": dict(progress_state)},
                )
            finally:
                progress_session.close()

        publish_progress({})
        progress_token = _THEME_SYNC_PROGRESS_CALLBACK.set(publish_progress)

        input_payload = job.input if isinstance(job.input, dict) else {}
        client_id = input_payload.get("clientId")
        raw_request_payload = input_payload.get("payload")
        raw_auth_context = input_payload.get("auth")

        if not isinstance(client_id, str) or not client_id.strip():
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: missing clientId.",
                output={"progress": dict(progress_state)},
            )
            return
        if not isinstance(raw_request_payload, dict):
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: payload must be an object.",
                output={"progress": dict(progress_state)},
            )
            return
        if not isinstance(raw_auth_context, dict):
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: auth context must be an object.",
                output={"progress": dict(progress_state)},
            )
            return

        user_id = raw_auth_context.get("userId")
        org_id = raw_auth_context.get("orgId")
        if (
            not isinstance(user_id, str)
            or not user_id.strip()
            or not isinstance(org_id, str)
            or not org_id.strip()
        ):
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: missing auth.userId or auth.orgId.",
                output={"progress": dict(progress_state)},
            )
            return

        try:
            payload = ShopifyThemeTemplatePublishRequest(**raw_request_payload)
        except Exception as exc:  # noqa: BLE001
            jobs_repo.mark_failed(
                job_id,
                error=f"Invalid queued job payload: {exc}",
                output={"progress": dict(progress_state)},
            )
            return

        auth = AuthContext(user_id=user_id.strip(), org_id=org_id.strip())
        publish_progress(
            {
                "stage": "running",
                "message": "Publishing Shopify theme template draft.",
            }
        )
        try:
            publish_response = _publish_shopify_theme_template_draft(
                client_id=client_id.strip(),
                payload=payload,
                auth=auth,
                session=session,
            )
        except HTTPException as exc:
            detail_payload = _serialize_http_exception_detail(exc.detail)
            error_message = detail_payload.get("message")
            if not isinstance(error_message, str) or not error_message.strip():
                error_message = (
                    f"Shopify theme template publish failed with status {exc.status_code}."
                )
            publish_progress({"stage": "failed", "message": error_message})
            jobs_repo.mark_failed(
                job_id,
                error=error_message,
                output={
                    "statusCode": exc.status_code,
                    "detail": detail_payload,
                    "progress": dict(progress_state),
                },
            )
            return

        result_payload = publish_response.model_dump(mode="json")
        publish_progress(
            {
                "stage": "succeeded",
                "message": "Shopify theme template draft published successfully.",
                "draftId": publish_response.draft.id,
                "draftVersionNumber": publish_response.version.versionNumber,
            }
        )
        jobs_repo.mark_succeeded(
            job_id,
            output={"result": result_payload, "progress": dict(progress_state)},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Unhandled exception while running Shopify theme template publish job",
            extra={"job_id": job_id},
        )
        try:
            JobsRepository(session).mark_failed(
                job_id,
                error=str(exc) or "Unhandled error while running Shopify theme template publish job.",
                output={
                    "progress": {
                        "stage": "failed",
                        "message": str(exc)
                        or "Unhandled error while running Shopify theme template publish job.",
                        "updatedAt": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to mark Shopify theme template publish job as failed after exception",
                extra={"job_id": job_id},
            )
    finally:
        if progress_token is not None:
            _THEME_SYNC_PROGRESS_CALLBACK.reset(progress_token)
        session.close()


@router.get("/{client_id}/shopify/status", response_model=ShopifyConnectionStatusResponse)
def get_client_shopify_status(
    client_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    selected_shop_domain = _get_selected_shop_domain(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        user_external_id=auth.user_id,
    )
    status_payload = get_client_shopify_connection_status(
        client_id=client_id,
        selected_shop_domain=selected_shop_domain,
    )
    return ShopifyConnectionStatusResponse(**status_payload)


@router.post("/{client_id}/shopify/install-url", response_model=ShopifyInstallUrlResponse)
def create_client_shopify_install_url(
    client_id: str,
    payload: ShopifyInstallUrlRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    install_url = build_client_shopify_install_url(
        client_id=client_id, shop_domain=payload.shopDomain
    )
    return ShopifyInstallUrlResponse(installUrl=install_url)


@router.patch("/{client_id}/shopify/installation", response_model=ShopifyConnectionStatusResponse)
def update_client_shopify_installation(
    client_id: str,
    payload: ShopifyInstallationUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    set_client_shopify_storefront_token(
        client_id=client_id,
        shop_domain=payload.shopDomain,
        storefront_access_token=payload.storefrontAccessToken,
    )
    selected_shop_domain = _get_selected_shop_domain(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        user_external_id=auth.user_id,
    )
    status_payload = get_client_shopify_connection_status(
        client_id=client_id,
        selected_shop_domain=selected_shop_domain,
    )
    return ShopifyConnectionStatusResponse(**status_payload)


@router.post(
    "/{client_id}/shopify/installation/auto-storefront-token",
    response_model=ShopifyConnectionStatusResponse,
)
def auto_provision_client_shopify_installation_storefront_token(
    client_id: str,
    payload: ShopifyInstallationAutoStorefrontTokenRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    auto_provision_client_shopify_storefront_token(
        client_id=client_id,
        shop_domain=payload.shopDomain,
    )
    selected_shop_domain = _get_selected_shop_domain(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        user_external_id=auth.user_id,
    )
    status_payload = get_client_shopify_connection_status(
        client_id=client_id,
        selected_shop_domain=selected_shop_domain,
    )
    return ShopifyConnectionStatusResponse(**status_payload)


@router.delete("/{client_id}/shopify/installation", response_model=ShopifyConnectionStatusResponse)
def disconnect_client_shopify_installation(
    client_id: str,
    payload: ShopifyInstallationDisconnectRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    normalized_shop = normalize_shop_domain(payload.shopDomain)
    disconnect_client_shopify_store(client_id=client_id, shop_domain=normalized_shop)

    prefs_with_selected_shop = session.scalars(
        select(ClientUserPreference).where(
            ClientUserPreference.org_id == auth.org_id,
            ClientUserPreference.client_id == client_id,
            ClientUserPreference.selected_shop_domain == normalized_shop,
        )
    ).all()
    if prefs_with_selected_shop:
        for pref in prefs_with_selected_shop:
            pref.selected_shop_domain = None
            pref.updated_at = func.now()
        session.commit()

    selected_shop_domain = _get_selected_shop_domain(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        user_external_id=auth.user_id,
    )
    status_payload = get_client_shopify_connection_status(
        client_id=client_id,
        selected_shop_domain=selected_shop_domain,
    )
    return ShopifyConnectionStatusResponse(**status_payload)


@router.put("/{client_id}/shopify/default-shop", response_model=ShopifyConnectionStatusResponse)
def set_client_shopify_default_shop(
    client_id: str,
    payload: ShopifyDefaultShopRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    normalized_shop = normalize_shop_domain(payload.shopDomain)

    installations = list_shopify_installations()
    active_installation = next(
        (
            installation
            for installation in installations
            if installation.client_id == client_id
            and installation.uninstalled_at is None
            and installation.shop_domain == normalized_shop
        ),
        None,
    )
    if not active_installation:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Selected shopDomain is not an active Shopify installation for this workspace.",
        )

    pref = _get_client_user_pref(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        user_external_id=auth.user_id,
    )
    if pref:
        pref.selected_shop_domain = normalized_shop
        pref.updated_at = func.now()
    else:
        session.add(
            ClientUserPreference(
                org_id=auth.org_id,
                client_id=client_id,
                user_external_id=auth.user_id,
                selected_shop_domain=normalized_shop,
            )
        )
    session.commit()

    status_payload = get_client_shopify_connection_status(
        client_id=client_id,
        selected_shop_domain=normalized_shop,
    )
    return ShopifyConnectionStatusResponse(**status_payload)


@router.get("/{client_id}/shopify/products", response_model=ShopifyProductListResponse)
def list_client_shopify_products_route(
    client_id: str,
    query: str | None = Query(default=None),
    limit: int = Query(default=20),
    shopDomain: str | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    selected_shop_domain = _get_selected_shop_domain(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        user_external_id=auth.user_id,
    )
    effective_shop_domain = shopDomain or selected_shop_domain
    payload = list_client_shopify_products(
        client_id=client_id,
        query=query,
        limit=limit,
        shop_domain=effective_shop_domain,
    )
    return ShopifyProductListResponse(**payload)


@router.post("/{client_id}/shopify/products", response_model=ShopifyProductCreateResponse)
def create_client_shopify_product_route(
    client_id: str,
    payload: ShopifyCreateProductRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    selected_shop_domain = _get_selected_shop_domain(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        user_external_id=auth.user_id,
    )
    effective_shop_domain = payload.shopDomain or selected_shop_domain
    status_payload = get_client_shopify_connection_status(
        client_id=client_id,
        selected_shop_domain=effective_shop_domain,
    )
    if status_payload["state"] != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Shopify connection is not ready: {status_payload['message']}",
        )
    created = create_client_shopify_product(
        client_id=client_id,
        title=payload.title,
        description=payload.description,
        handle=payload.handle,
        vendor=payload.vendor,
        product_type=payload.productType,
        tags=payload.tags,
        status_text=payload.status,
        variants=[variant.model_dump() for variant in payload.variants],
        shop_domain=effective_shop_domain,
    )
    return ShopifyProductCreateResponse(**created)


@router.post(
    "/{client_id}/shopify/theme/brand/template/build-async",
    response_model=ShopifyThemeTemplateBuildJobStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_client_shopify_theme_template_build_route(
    client_id: str,
    payload: ShopifyThemeTemplateBuildRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)

    jobs_repo = JobsRepository(session)
    job, _ = jobs_repo.get_or_create(
        org_id=auth.org_id,
        client_id=client_id,
        research_run_id=None,
        job_type=_JOB_TYPE_SHOPIFY_THEME_TEMPLATE_BUILD,
        subject_type=_JOB_SUBJECT_TYPE_CLIENT,
        subject_id=client_id,
        dedupe_key=None,
        input_payload={
            "clientId": client_id,
            "payload": payload.model_dump(mode="json"),
            "auth": {
                "userId": auth.user_id,
                "orgId": auth.org_id,
            },
        },
        status=JOB_STATUS_QUEUED,
    )
    background_tasks.add_task(_run_client_shopify_theme_template_build_job, str(job.id))

    return ShopifyThemeTemplateBuildJobStartResponse(
        jobId=str(job.id),
        status=job.status,
        statusPath=f"/clients/{client_id}/shopify/theme/brand/template/build-jobs/{job.id}",
    )


@router.get(
    "/{client_id}/shopify/theme/brand/template/build-jobs/{job_id}",
    response_model=ShopifyThemeTemplateBuildJobStatusResponse,
)
def get_client_shopify_theme_template_build_job_status_route(
    client_id: str,
    job_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    job = JobsRepository(session).get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Build job not found.")

    if (
        str(job.org_id) != auth.org_id
        or str(job.subject_id) != client_id
        or job.job_type != _JOB_TYPE_SHOPIFY_THEME_TEMPLATE_BUILD
        or job.subject_type != _JOB_SUBJECT_TYPE_CLIENT
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Build job not found.")

    if job.status not in {
        JOB_STATUS_QUEUED,
        JOB_STATUS_RUNNING,
        JOB_STATUS_SUCCEEDED,
        JOB_STATUS_FAILED,
    }:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Build job is in an unsupported state: {job.status}",
        )

    output_payload = job.output if isinstance(job.output, dict) else {}
    raw_progress = output_payload.get("progress")
    progress: ShopifyThemeBrandSyncJobProgress | None = None
    if isinstance(raw_progress, dict):
        try:
            progress = ShopifyThemeBrandSyncJobProgress(**raw_progress)
        except Exception:  # noqa: BLE001
            progress = None
    raw_result = output_payload.get("result")
    result: ShopifyThemeTemplateBuildResponse | None = None
    if isinstance(raw_result, dict):
        try:
            result = ShopifyThemeTemplateBuildResponse(**raw_result)
        except Exception:  # noqa: BLE001
            result = None

    error = job.error.strip() if isinstance(job.error, str) and job.error.strip() else None
    return ShopifyThemeTemplateBuildJobStatusResponse(
        jobId=str(job.id),
        status=job.status,
        error=error,
        progress=progress,
        result=result,
        createdAt=job.created_at,
        updatedAt=job.updated_at,
        startedAt=job.started_at,
        finishedAt=job.finished_at,
    )


@router.get(
    "/{client_id}/shopify/theme/brand/template/drafts",
    response_model=list[ShopifyThemeTemplateDraftResponse],
)
def list_client_shopify_theme_template_drafts_route(
    client_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    drafts_repo = ShopifyThemeTemplateDraftsRepository(session)
    drafts = drafts_repo.list_for_client(org_id=auth.org_id, client_id=client_id, limit=limit)
    response_payload: list[ShopifyThemeTemplateDraftResponse] = []
    for draft in drafts:
        latest_version = drafts_repo.get_latest_version(draft_id=str(draft.id))
        response_payload.append(
            _serialize_shopify_theme_template_draft(
                draft=draft,
                latest_version=latest_version,
            )
        )
    return response_payload


@router.get(
    "/{client_id}/shopify/theme/brand/template/drafts/{draft_id}",
    response_model=ShopifyThemeTemplateDraftResponse,
)
def get_client_shopify_theme_template_draft_route(
    client_id: str,
    draft_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    drafts_repo = ShopifyThemeTemplateDraftsRepository(session)
    draft = drafts_repo.get(org_id=auth.org_id, client_id=client_id, draft_id=draft_id)
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shopify theme template draft not found.",
        )
    latest_version = drafts_repo.get_latest_version(draft_id=str(draft.id))
    return _serialize_shopify_theme_template_draft(
        draft=draft,
        latest_version=latest_version,
    )


@router.put(
    "/{client_id}/shopify/theme/brand/template/drafts/{draft_id}",
    response_model=ShopifyThemeTemplateDraftResponse,
)
def update_client_shopify_theme_template_draft_route(
    client_id: str,
    draft_id: str,
    payload: ShopifyThemeTemplateDraftUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    drafts_repo = ShopifyThemeTemplateDraftsRepository(session)
    draft = drafts_repo.get(org_id=auth.org_id, client_id=client_id, draft_id=draft_id)
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shopify theme template draft not found.",
        )
    latest_version = drafts_repo.get_latest_version(draft_id=str(draft.id))
    if not latest_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Shopify theme template draft has no versions to update.",
        )
    serialized_latest_version = _serialize_shopify_theme_template_draft_version(
        version=latest_version
    )
    latest_data = serialized_latest_version.data

    if payload.componentImageAssetMap is None:
        component_image_asset_map = dict(latest_data.componentImageAssetMap)
    else:
        component_image_asset_map = _normalize_theme_template_component_image_asset_map(
            payload.componentImageAssetMap
        )
    if payload.componentTextValues is None:
        component_text_values = dict(latest_data.componentTextValues)
    else:
        component_text_values = _normalize_theme_template_component_text_values(
            payload.componentTextValues
        )

    _resolve_component_image_urls_from_asset_map(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        component_image_asset_map=component_image_asset_map,
    )

    merged_metadata = dict(latest_data.metadata or {})
    merged_metadata["componentImageAssetCount"] = len(component_image_asset_map)
    merged_metadata["componentTextValueCount"] = len(component_text_values)

    next_data = latest_data.model_copy(
        update={
            "componentImageAssetMap": component_image_asset_map,
            "componentTextValues": component_text_values,
            "metadata": merged_metadata,
        }
    )
    next_version = drafts_repo.create_version(
        draft=draft,
        payload=next_data.model_dump(mode="json"),
        source="manual_edit",
        notes=(payload.notes.strip() if isinstance(payload.notes, str) and payload.notes.strip() else None),
        created_by_user_external_id=auth.user_id,
    )
    return _serialize_shopify_theme_template_draft(
        draft=draft,
        latest_version=next_version,
    )


@router.post(
    "/{client_id}/shopify/theme/brand/template/generate-images-async",
    response_model=ShopifyThemeTemplateGenerateImagesJobStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_client_shopify_theme_template_generate_images_route(
    client_id: str,
    payload: ShopifyThemeTemplateGenerateImagesRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)

    jobs_repo = JobsRepository(session)
    job, _ = jobs_repo.get_or_create(
        org_id=auth.org_id,
        client_id=client_id,
        research_run_id=None,
        job_type=_JOB_TYPE_SHOPIFY_THEME_TEMPLATE_GENERATE_IMAGES,
        subject_type=_JOB_SUBJECT_TYPE_CLIENT,
        subject_id=client_id,
        dedupe_key=None,
        input_payload={
            "clientId": client_id,
            "payload": payload.model_dump(mode="json"),
            "auth": {
                "userId": auth.user_id,
                "orgId": auth.org_id,
            },
        },
        status=JOB_STATUS_QUEUED,
    )
    background_tasks.add_task(
        _run_client_shopify_theme_template_generate_images_job, str(job.id)
    )

    return ShopifyThemeTemplateGenerateImagesJobStartResponse(
        jobId=str(job.id),
        status=job.status,
        statusPath=f"/clients/{client_id}/shopify/theme/brand/template/generate-images-jobs/{job.id}",
    )


@router.get(
    "/{client_id}/shopify/theme/brand/template/generate-images-jobs/{job_id}",
    response_model=ShopifyThemeTemplateGenerateImagesJobStatusResponse,
)
def get_client_shopify_theme_template_generate_images_job_status_route(
    client_id: str,
    job_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    job = JobsRepository(session).get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template image generation job not found.",
        )

    if (
        str(job.org_id) != auth.org_id
        or str(job.subject_id) != client_id
        or job.job_type != _JOB_TYPE_SHOPIFY_THEME_TEMPLATE_GENERATE_IMAGES
        or job.subject_type != _JOB_SUBJECT_TYPE_CLIENT
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template image generation job not found.",
        )

    if job.status not in {
        JOB_STATUS_QUEUED,
        JOB_STATUS_RUNNING,
        JOB_STATUS_SUCCEEDED,
        JOB_STATUS_FAILED,
    }:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Template image generation job is in an unsupported state: "
                f"{job.status}"
            ),
        )

    output_payload = job.output if isinstance(job.output, dict) else {}
    raw_progress = output_payload.get("progress")
    progress: ShopifyThemeBrandSyncJobProgress | None = None
    if isinstance(raw_progress, dict):
        try:
            progress = ShopifyThemeBrandSyncJobProgress(**raw_progress)
        except Exception:  # noqa: BLE001
            progress = None
    raw_result = output_payload.get("result")
    result: ShopifyThemeTemplateGenerateImagesResponse | None = None
    if isinstance(raw_result, dict):
        try:
            result = ShopifyThemeTemplateGenerateImagesResponse(**raw_result)
        except Exception:  # noqa: BLE001
            result = None

    error = job.error.strip() if isinstance(job.error, str) and job.error.strip() else None
    return ShopifyThemeTemplateGenerateImagesJobStatusResponse(
        jobId=str(job.id),
        status=job.status,
        error=error,
        progress=progress,
        result=result,
        createdAt=job.created_at,
        updatedAt=job.updated_at,
        startedAt=job.started_at,
        finishedAt=job.finished_at,
    )


@router.post(
    "/{client_id}/shopify/theme/brand/template/publish-async",
    response_model=ShopifyThemeTemplatePublishJobStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_client_shopify_theme_template_publish_route(
    client_id: str,
    payload: ShopifyThemeTemplatePublishRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)

    jobs_repo = JobsRepository(session)
    job, _ = jobs_repo.get_or_create(
        org_id=auth.org_id,
        client_id=client_id,
        research_run_id=None,
        job_type=_JOB_TYPE_SHOPIFY_THEME_TEMPLATE_PUBLISH,
        subject_type=_JOB_SUBJECT_TYPE_CLIENT,
        subject_id=client_id,
        dedupe_key=None,
        input_payload={
            "clientId": client_id,
            "payload": payload.model_dump(mode="json"),
            "auth": {
                "userId": auth.user_id,
                "orgId": auth.org_id,
            },
        },
        status=JOB_STATUS_QUEUED,
    )
    job_id = str(job.id)
    threading.Thread(
        target=_run_client_shopify_theme_template_publish_job,
        args=(job_id,),
        daemon=True,
        name=f"shopify-template-publish-{job_id}",
    ).start()

    return ShopifyThemeTemplatePublishJobStartResponse(
        jobId=job_id,
        status=job.status,
        statusPath=f"/clients/{client_id}/shopify/theme/brand/template/publish-jobs/{job.id}",
    )


@router.get(
    "/{client_id}/shopify/theme/brand/template/publish-jobs/{job_id}",
    response_model=ShopifyThemeTemplatePublishJobStatusResponse,
)
def get_client_shopify_theme_template_publish_job_status_route(
    client_id: str,
    job_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    job = JobsRepository(session).get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publish job not found.")

    if (
        str(job.org_id) != auth.org_id
        or str(job.subject_id) != client_id
        or job.job_type != _JOB_TYPE_SHOPIFY_THEME_TEMPLATE_PUBLISH
        or job.subject_type != _JOB_SUBJECT_TYPE_CLIENT
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publish job not found.")

    if job.status not in {
        JOB_STATUS_QUEUED,
        JOB_STATUS_RUNNING,
        JOB_STATUS_SUCCEEDED,
        JOB_STATUS_FAILED,
    }:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Publish job is in an unsupported state: {job.status}",
        )

    output_payload = job.output if isinstance(job.output, dict) else {}
    raw_progress = output_payload.get("progress")
    progress: ShopifyThemeBrandSyncJobProgress | None = None
    if isinstance(raw_progress, dict):
        try:
            progress = ShopifyThemeBrandSyncJobProgress(**raw_progress)
        except Exception:  # noqa: BLE001
            progress = None
    raw_result = output_payload.get("result")
    result: ShopifyThemeTemplatePublishResponse | None = None
    if isinstance(raw_result, dict):
        try:
            result = ShopifyThemeTemplatePublishResponse(**raw_result)
        except Exception:  # noqa: BLE001
            result = None

    error = job.error.strip() if isinstance(job.error, str) and job.error.strip() else None
    return ShopifyThemeTemplatePublishJobStatusResponse(
        jobId=str(job.id),
        status=job.status,
        error=error,
        progress=progress,
        result=result,
        createdAt=job.created_at,
        updatedAt=job.updated_at,
        startedAt=job.started_at,
        finishedAt=job.finished_at,
    )


@router.post(
    "/{client_id}/shopify/theme/brand/sync-async",
    response_model=ShopifyThemeBrandSyncJobStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_client_shopify_theme_brand_sync_route(
    client_id: str,
    payload: ShopifyThemeBrandSyncRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)

    jobs_repo = JobsRepository(session)
    job, _ = jobs_repo.get_or_create(
        org_id=auth.org_id,
        client_id=client_id,
        research_run_id=None,
        job_type=_JOB_TYPE_SHOPIFY_THEME_BRAND_SYNC,
        subject_type=_JOB_SUBJECT_TYPE_CLIENT,
        subject_id=client_id,
        dedupe_key=None,
        input_payload={
            "clientId": client_id,
            "payload": payload.model_dump(mode="json"),
            "auth": {
                "userId": auth.user_id,
                "orgId": auth.org_id,
            },
        },
        status=JOB_STATUS_QUEUED,
    )
    background_tasks.add_task(_run_client_shopify_theme_brand_sync_job, str(job.id))

    return ShopifyThemeBrandSyncJobStartResponse(
        jobId=str(job.id),
        status=job.status,
        statusPath=f"/clients/{client_id}/shopify/theme/brand/sync-jobs/{job.id}",
    )


@router.get(
    "/{client_id}/shopify/theme/brand/sync-jobs/{job_id}",
    response_model=ShopifyThemeBrandSyncJobStatusResponse,
)
def get_client_shopify_theme_brand_sync_job_status_route(
    client_id: str,
    job_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    job = JobsRepository(session).get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync job not found.")

    if (
        str(job.org_id) != auth.org_id
        or str(job.subject_id) != client_id
        or job.job_type != _JOB_TYPE_SHOPIFY_THEME_BRAND_SYNC
        or job.subject_type != _JOB_SUBJECT_TYPE_CLIENT
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync job not found.")

    if job.status not in {
        JOB_STATUS_QUEUED,
        JOB_STATUS_RUNNING,
        JOB_STATUS_SUCCEEDED,
        JOB_STATUS_FAILED,
    }:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync job is in an unsupported state: {job.status}",
        )

    output_payload = job.output if isinstance(job.output, dict) else {}
    raw_progress = output_payload.get("progress")
    progress: ShopifyThemeBrandSyncJobProgress | None = None
    if isinstance(raw_progress, dict):
        try:
            progress = ShopifyThemeBrandSyncJobProgress(**raw_progress)
        except Exception:  # noqa: BLE001
            progress = None
    raw_result = output_payload.get("result")
    result: ShopifyThemeBrandSyncResponse | None = None
    if isinstance(raw_result, dict):
        try:
            result = ShopifyThemeBrandSyncResponse(**raw_result)
        except Exception:  # noqa: BLE001
            result = None

    error = job.error.strip() if isinstance(job.error, str) and job.error.strip() else None
    return ShopifyThemeBrandSyncJobStatusResponse(
        jobId=str(job.id),
        status=job.status,
        error=error,
        progress=progress,
        result=result,
        createdAt=job.created_at,
        updatedAt=job.updated_at,
        startedAt=job.started_at,
        finishedAt=job.finished_at,
    )


@router.post(
    "/{client_id}/shopify/theme/brand/sync",
    response_model=ShopifyThemeBrandSyncResponse,
)
def sync_client_shopify_theme_brand_route(
    client_id: str,
    payload: ShopifyThemeBrandSyncRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _emit_theme_sync_progress(
        {
            "stage": "preparing",
            "message": "Validating Shopify theme sync request and workspace data.",
        }
    )
    client = _get_client_or_404(session=session, org_id=auth.org_id, client_id=client_id)
    selected_shop_domain = _get_selected_shop_domain(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        user_external_id=auth.user_id,
    )
    effective_shop_domain = payload.shopDomain or selected_shop_domain
    status_payload = get_client_shopify_connection_status(
        client_id=client_id,
        selected_shop_domain=effective_shop_domain,
    )
    if status_payload["state"] != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Shopify connection is not ready: {status_payload['message']}",
        )

    requested_design_system_id = payload.designSystemId.strip() if payload.designSystemId else None
    resolved_design_system_id = requested_design_system_id or (
        str(client.design_system_id) if client.design_system_id else None
    )
    if not resolved_design_system_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "No design system selected for Shopify theme sync. "
                "Set a workspace default design system or provide designSystemId."
            ),
        )

    design_system_repo = DesignSystemsRepository(session)
    design_system = design_system_repo.get(
        org_id=auth.org_id,
        design_system_id=resolved_design_system_id,
    )
    if not design_system:
        if requested_design_system_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Design system not found"
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workspace default design system was not found.",
        )

    design_system_client_id = str(design_system.client_id) if design_system.client_id else None
    if design_system_client_id and design_system_client_id != client_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Design system must belong to this workspace.",
        )

    try:
        validated_tokens = validate_design_system_tokens(design_system.tokens)
    except DesignSystemGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    brand_obj = validated_tokens.get("brand")
    if not isinstance(brand_obj, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.brand must be a JSON object.",
        )
    brand_name_raw = brand_obj.get("name")
    if not isinstance(brand_name_raw, str) or not brand_name_raw.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.brand.name must be a non-empty string.",
        )
    logo_public_id_raw = brand_obj.get("logoAssetPublicId")
    if not isinstance(logo_public_id_raw, str) or not logo_public_id_raw.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.brand.logoAssetPublicId must be a non-empty string.",
        )
    brand_name = brand_name_raw.strip()
    logo_public_id = logo_public_id_raw.strip()

    css_vars_raw = validated_tokens.get("cssVars")
    if not isinstance(css_vars_raw, dict) or not css_vars_raw:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.cssVars must be a non-empty JSON object.",
        )
    css_vars: dict[str, str] = {}
    for raw_key, raw_value in css_vars_raw.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Design system tokens.cssVars keys must be non-empty strings.",
            )
        if not isinstance(raw_value, (str, int, float)):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Design system cssVars[{raw_key}] must be a string or number.",
            )
        if isinstance(raw_value, str):
            cleaned_value = raw_value.strip()
            if not cleaned_value:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Design system cssVars[{raw_key}] must not be an empty string.",
                )
        else:
            cleaned_value = str(raw_value)
        css_vars[raw_key.strip()] = cleaned_value

    font_urls_raw = validated_tokens.get("fontUrls")
    if not isinstance(font_urls_raw, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.fontUrls must be a list of non-empty strings.",
        )
    font_urls: list[str] = []
    for item in font_urls_raw:
        if not isinstance(item, str) or not item.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Design system tokens.fontUrls must be a list of non-empty strings.",
            )
        font_urls.append(item.strip())

    data_theme_raw = validated_tokens.get("dataTheme")
    if not isinstance(data_theme_raw, str) or not data_theme_raw.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.dataTheme must be a non-empty string.",
        )
    data_theme = data_theme_raw.strip()

    assets_repo = AssetsRepository(session)
    logo_asset = assets_repo.get_by_public_id(
        org_id=auth.org_id,
        public_id=logo_public_id,
        client_id=client_id,
    )
    if not logo_asset:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Design system brand.logoAssetPublicId does not reference an existing logo asset "
                "for this workspace."
            ),
        )

    component_image_asset_map_raw = payload.componentImageAssetMap or {}
    normalized_component_image_asset_map: dict[str, str] = {}
    for raw_setting_path, raw_asset_public_id in component_image_asset_map_raw.items():
        if not isinstance(raw_setting_path, str) or not raw_setting_path.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="componentImageAssetMap keys must be non-empty strings.",
            )
        setting_path = raw_setting_path.strip()
        if setting_path in normalized_component_image_asset_map:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"componentImageAssetMap contains duplicate path after normalization: {setting_path}",
            )
        if not isinstance(raw_asset_public_id, str) or not raw_asset_public_id.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "componentImageAssetMap values must be non-empty asset public ids. "
                    f"Invalid value at path {setting_path}."
                ),
            )
        normalized_component_image_asset_map[setting_path] = raw_asset_public_id.strip()
    normalized_manual_component_text_values = _normalize_theme_template_component_text_values(
        payload.componentTextValues
    )
    copy_settings = _normalize_theme_copy_settings(
        tone_guidelines=payload.toneGuidelines,
        must_avoid_claims=payload.mustAvoidClaims,
        cta_style=payload.ctaStyle,
        reading_level=payload.readingLevel,
        locale=payload.locale,
    )
    planner_copy_kwargs = _build_theme_copy_planner_kwargs(copy_settings=copy_settings)

    requested_product_id = payload.productId.strip() if payload.productId else None
    resolved_product: Product | None = None
    resolved_product_storage_id: str | None = None
    if requested_product_id:
        product = ProductsRepository(session).get(
            org_id=auth.org_id, product_id=requested_product_id
        )
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product not found for productId={requested_product_id}.",
            )
        resolved_product = product
        product_client_id = str(product.client_id).strip()
        if product_client_id != client_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Product must belong to this workspace.",
            )
        resolved_product_storage_id = str(product.id).strip()

    workspace_name = str(client.name).strip()
    if not workspace_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Workspace name is required to sync Shopify theme brand assets.",
        )

    public_asset_base_url = _require_public_asset_base_url()
    logo_url = f"{public_asset_base_url}/public/assets/{logo_public_id}"
    component_image_urls: dict[str, str] = {}
    component_text_values: dict[str, str] = {}
    if normalized_component_image_asset_map:
        for (
            setting_path,
            asset_public_id,
        ) in normalized_component_image_asset_map.items():
            mapped_asset = assets_repo.get_by_public_id(
                org_id=auth.org_id,
                public_id=asset_public_id,
                client_id=client_id,
            )
            if not mapped_asset:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "componentImageAssetMap references an asset that does not exist for this workspace. "
                        f"path={setting_path}, assetPublicId={asset_public_id}."
                    ),
                )
            component_image_urls[setting_path] = (
                f"{public_asset_base_url}/public/assets/{asset_public_id}"
            )
    auto_component_image_urls: list[str] = []

    should_discover_slots_for_ai = bool(
        requested_product_id or not normalized_component_image_asset_map
    )
    planner_image_slots: list[dict[str, Any]] = []
    text_slots: list[dict[str, Any]] = []
    generated_theme_assets: list[Any] = []
    generated_asset_by_slot_path: dict[str, Any] = {}
    rate_limited_slot_paths: list[str] = []
    quota_exhausted_slot_paths: list[str] = []
    slot_error_by_slot_path: dict[str, str] = {}
    product_reference_image: dict[str, Any] | None = None
    if should_discover_slots_for_ai:
        _emit_theme_sync_progress(
            {
                "stage": "discover_slots",
                "message": "Discovering theme component slots for AI mapping.",
            }
        )
        discovered_slots = list_client_shopify_theme_template_slots(
            client_id=client_id,
            theme_id=payload.themeId,
            theme_name=payload.themeName,
            shop_domain=effective_shop_domain,
        )
        raw_image_slots = discovered_slots.get("imageSlots")
        raw_text_slots = discovered_slots.get("textSlots")
        image_slots = raw_image_slots if isinstance(raw_image_slots, list) else []
        text_slots = raw_text_slots if isinstance(raw_text_slots, list) else []
        explicit_image_paths = set(normalized_component_image_asset_map.keys())
        planner_image_slots = [
            slot
            for slot in image_slots
            if isinstance(slot, dict)
            and isinstance(slot.get("path"), str)
            and slot["path"] not in explicit_image_paths
        ]
        _emit_theme_sync_progress(
            {
                "stage": "discover_slots",
                "message": "Theme component slot discovery completed.",
                "totalImageSlots": len(planner_image_slots),
                "totalTextSlots": len(text_slots),
            }
        )

        if requested_product_id and not planner_image_slots and not text_slots:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "No image or text component slots were discovered for AI product content mapping. "
                    f"productId={requested_product_id}."
                ),
            )

        if planner_image_slots:
            if (
                requested_product_id
                and resolved_product is not None
                and _is_gemini_image_references_enabled()
            ):
                product_reference_image = _resolve_theme_sync_product_reference_image(
                    session=session,
                    org_id=auth.org_id,
                    client_id=client_id,
                    product=resolved_product,
                )
            (
                generated_theme_assets,
                rate_limited_slot_paths,
                generated_asset_by_slot_path,
                quota_exhausted_slot_paths,
                slot_error_by_slot_path,
            ) = _generate_theme_sync_ai_image_assets(
                session=session,
                org_id=auth.org_id,
                client_id=client_id,
                product_id=resolved_product_storage_id,
                image_slots=planner_image_slots,
                text_slots=text_slots,
                reference_image_bytes=(
                    product_reference_image["imageBytes"] if product_reference_image else None
                ),
                reference_image_mime_type=(
                    product_reference_image["mimeType"] if product_reference_image else None
                ),
                reference_asset_public_id=(
                    product_reference_image["assetPublicId"]
                    if product_reference_image
                    else None
                ),
                reference_asset_id=(
                    product_reference_image["assetId"] if product_reference_image else None
                ),
            )

        if not requested_product_id:
            if rate_limited_slot_paths:
                if quota_exhausted_slot_paths:
                    first_quota_slot_path = quota_exhausted_slot_paths[0]
                    first_quota_error = slot_error_by_slot_path.get(first_quota_slot_path)
                    first_quota_error_note = (
                        f" Gemini error: {first_quota_error}"
                        if isinstance(first_quota_error, str) and first_quota_error.strip()
                        else ""
                    )
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=(
                            "AI theme image generation exhausted Gemini quota for Shopify sync. "
                            + first_quota_error_note
                            + " "
                            "Retry after quota reset or provide componentImageAssetMap for these slots: "
                            + ", ".join(sorted(quota_exhausted_slot_paths))
                        ),
                    )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        "AI theme image generation is rate-limited or out of Gemini quota for Shopify sync, "
                        "and productId was not provided for fallback product images. "
                        "Provide componentImageAssetMap for these slots: "
                        + ", ".join(sorted(rate_limited_slot_paths))
                    ),
                )
            for slot_path, generated_asset in generated_asset_by_slot_path.items():
                normalized_public_id = _normalize_asset_public_id(
                    getattr(generated_asset, "public_id", None)
                )
                if not normalized_public_id:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=(
                            "AI theme image generation returned an asset without a valid public id. "
                            f"slotPath={slot_path}."
                        ),
                    )
                component_image_urls[slot_path] = (
                    f"{public_asset_base_url}/public/assets/{normalized_public_id}"
                )

    if requested_product_id and resolved_product is not None:
        product_image_assets = assets_repo.list(
            org_id=auth.org_id,
            client_id=client_id,
            product_id=resolved_product_storage_id,
            asset_kind="image",
            statuses=[AssetStatusEnum.approved, AssetStatusEnum.qa_passed],
        )
        product_image_assets_by_public_id: dict[str, Any] = {}
        for existing_asset in product_image_assets:
            normalized_existing_public_id = _normalize_asset_public_id(
                getattr(existing_asset, "public_id", None)
            )
            if not normalized_existing_public_id:
                continue
            product_image_assets_by_public_id[normalized_existing_public_id] = existing_asset
        for generated_asset in generated_theme_assets:
            normalized_public_id = _normalize_asset_public_id(
                getattr(generated_asset, "public_id", None)
            )
            if not normalized_public_id:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "AI theme image generation returned an asset without a valid public id. "
                        f"productId={requested_product_id}."
                    ),
                )
            if normalized_public_id in product_image_assets_by_public_id:
                continue
            product_image_assets_by_public_id[normalized_public_id] = generated_asset
            product_image_assets.append(generated_asset)
        if planner_image_slots and not product_image_assets:
            if rate_limited_slot_paths:
                if quota_exhausted_slot_paths:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=(
                            "AI theme image generation exhausted Gemini quota for Shopify sync, "
                            "and no existing product images were available. "
                            f"productId={requested_product_id}. "
                            "Upload product images or provide componentImageAssetMap for these slots: "
                            + ", ".join(sorted(quota_exhausted_slot_paths))
                        ),
                    )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        "AI theme image generation is rate-limited or out of Gemini quota for Shopify sync, "
                        "and no existing product images were available. "
                        f"productId={requested_product_id}. "
                        "Upload product images or provide componentImageAssetMap for these slots: "
                        + ", ".join(sorted(rate_limited_slot_paths))
                    ),
                )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "No usable product image assets were available for Shopify theme image slot planning. "
                    f"productId={requested_product_id}."
                ),
            )

        offers = ProductOffersRepository(session).list_by_product(
            product_id=str(resolved_product.id)
        )
        _emit_theme_sync_progress(
            {
                "stage": "planning_content",
                "message": "Planning product copy and image-to-slot assignments.",
                "totalImageSlots": len(planner_image_slots),
                "totalTextSlots": len(text_slots),
            }
        )
        try:
            planner_output = plan_shopify_theme_component_content(
                product=resolved_product,
                offers=offers,
                product_image_assets=product_image_assets,
                image_slots=planner_image_slots,
                text_slots=text_slots,
                **planner_copy_kwargs,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "AI theme component planner failed for Shopify sync. "
                    f"productId={requested_product_id}. {exc}"
                ),
            ) from exc

        planner_image_map = planner_output.get("componentImageAssetMap") or {}
        if not isinstance(planner_image_map, dict):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI theme component planner returned an invalid componentImageAssetMap payload.",
            )
        for setting_path, asset_public_id in planner_image_map.items():
            if not isinstance(setting_path, str) or not setting_path.strip():
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="AI theme component planner returned an invalid image mapping path.",
                )
            if not isinstance(asset_public_id, str) or not asset_public_id.strip():
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "AI theme component planner returned an invalid image mapping asset id "
                        f"for path {setting_path}."
                    ),
                )
            normalized_path = setting_path.strip()
            normalized_asset_public_id = asset_public_id.strip()
            if _is_theme_feature_image_slot_path(normalized_path):
                generated_feature_asset = generated_asset_by_slot_path.get(normalized_path)
                if generated_feature_asset is not None:
                    generated_feature_asset_public_id = _normalize_asset_public_id(
                        getattr(generated_feature_asset, "public_id", None)
                    )
                    if (
                        generated_feature_asset_public_id
                        and generated_feature_asset_public_id
                        in product_image_assets_by_public_id
                    ):
                        normalized_asset_public_id = generated_feature_asset_public_id
            if normalized_asset_public_id not in product_image_assets_by_public_id:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "AI theme component planner returned an image asset id that does not belong to "
                        f"the product asset set. path={normalized_path}, assetPublicId={normalized_asset_public_id}."
                    ),
                )
            component_image_urls[normalized_path] = (
                f"{public_asset_base_url}/public/assets/{normalized_asset_public_id}"
            )

        planner_text_values = planner_output.get("componentTextValues") or {}
        if not isinstance(planner_text_values, dict):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI theme component planner returned an invalid componentTextValues payload.",
            )
        for setting_path, value in planner_text_values.items():
            if not isinstance(setting_path, str) or not setting_path.strip():
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="AI theme component planner returned an invalid text mapping path.",
                )
            if not isinstance(value, str) or not value.strip():
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "AI theme component planner returned an invalid text value "
                        f"for path {setting_path}."
                    ),
                )
            normalized_path = setting_path.strip()
            sanitized_value = _sanitize_theme_component_text_value(value)
            if not sanitized_value:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "AI theme component planner returned text that became empty after "
                        f"sanitization for path {normalized_path}."
                    ),
                )
            component_text_values[normalized_path] = sanitized_value

        for (
            setting_path,
            asset_public_id,
        ) in normalized_component_image_asset_map.items():
            component_image_urls[setting_path] = (
                f"{public_asset_base_url}/public/assets/{asset_public_id}"
            )

    component_text_values.update(normalized_manual_component_text_values)

    _emit_theme_sync_progress(
        {
            "stage": "sync_theme",
            "message": "Applying generated component assets and copy to Shopify theme.",
            "componentImageUrlCount": len(component_image_urls),
            "componentTextValueCount": len(component_text_values),
        }
    )
    synced = sync_client_shopify_theme_brand(
        client_id=client_id,
        workspace_name=workspace_name,
        brand_name=brand_name,
        logo_url=logo_url,
        css_vars=css_vars,
        font_urls=font_urls,
        data_theme=data_theme,
        component_image_urls=component_image_urls,
        component_text_values=component_text_values,
        auto_component_image_urls=auto_component_image_urls,
        theme_id=payload.themeId,
        theme_name=payload.themeName,
        shop_domain=effective_shop_domain,
    )

    return ShopifyThemeBrandSyncResponse(
        shopDomain=synced["shopDomain"],
        workspaceName=workspace_name,
        designSystemId=str(design_system.id),
        designSystemName=str(design_system.name),
        brandName=brand_name,
        logoAssetPublicId=logo_public_id,
        logoUrl=logo_url,
        themeId=synced["themeId"],
        themeName=synced["themeName"],
        themeRole=synced["themeRole"],
        layoutFilename=synced["layoutFilename"],
        cssFilename=synced["cssFilename"],
        settingsFilename=synced.get("settingsFilename"),
        jobId=synced["jobId"],
        coverage=synced["coverage"],
        settingsSync=synced["settingsSync"],
    )


@router.post(
    "/{client_id}/shopify/theme/brand/audit",
    response_model=ShopifyThemeBrandAuditResponse,
)
def audit_client_shopify_theme_brand_route(
    client_id: str,
    payload: ShopifyThemeBrandAuditRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    client = _get_client_or_404(session=session, org_id=auth.org_id, client_id=client_id)
    selected_shop_domain = _get_selected_shop_domain(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        user_external_id=auth.user_id,
    )
    effective_shop_domain = payload.shopDomain or selected_shop_domain
    status_payload = get_client_shopify_connection_status(
        client_id=client_id,
        selected_shop_domain=effective_shop_domain,
    )
    if status_payload["state"] != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Shopify connection is not ready: {status_payload['message']}",
        )

    requested_design_system_id = payload.designSystemId.strip() if payload.designSystemId else None
    resolved_design_system_id = requested_design_system_id or (
        str(client.design_system_id) if client.design_system_id else None
    )
    if not resolved_design_system_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "No design system selected for Shopify theme audit. "
                "Set a workspace default design system or provide designSystemId."
            ),
        )

    design_system_repo = DesignSystemsRepository(session)
    design_system = design_system_repo.get(
        org_id=auth.org_id,
        design_system_id=resolved_design_system_id,
    )
    if not design_system:
        if requested_design_system_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Design system not found"
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workspace default design system was not found.",
        )

    design_system_client_id = str(design_system.client_id) if design_system.client_id else None
    if design_system_client_id and design_system_client_id != client_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Design system must belong to this workspace.",
        )

    try:
        validated_tokens = validate_design_system_tokens(design_system.tokens)
    except DesignSystemGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    css_vars_raw = validated_tokens.get("cssVars")
    if not isinstance(css_vars_raw, dict) or not css_vars_raw:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.cssVars must be a non-empty JSON object.",
        )
    css_vars: dict[str, str] = {}
    for raw_key, raw_value in css_vars_raw.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Design system tokens.cssVars keys must be non-empty strings.",
            )
        if not isinstance(raw_value, (str, int, float)):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Design system cssVars[{raw_key}] must be a string or number.",
            )
        if isinstance(raw_value, str):
            cleaned_value = raw_value.strip()
            if not cleaned_value:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Design system cssVars[{raw_key}] must not be an empty string.",
                )
        else:
            cleaned_value = str(raw_value)
        css_vars[raw_key.strip()] = cleaned_value

    data_theme_raw = validated_tokens.get("dataTheme")
    if not isinstance(data_theme_raw, str) or not data_theme_raw.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Design system tokens.dataTheme must be a non-empty string.",
        )
    data_theme = data_theme_raw.strip()

    workspace_name = str(client.name).strip()
    if not workspace_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Workspace name is required to audit Shopify theme brand assets.",
        )

    audited = audit_client_shopify_theme_brand(
        client_id=client_id,
        workspace_name=workspace_name,
        css_vars=css_vars,
        data_theme=data_theme,
        theme_id=payload.themeId,
        theme_name=payload.themeName,
        shop_domain=effective_shop_domain,
    )

    return ShopifyThemeBrandAuditResponse(
        shopDomain=audited["shopDomain"],
        workspaceName=workspace_name,
        designSystemId=str(design_system.id),
        designSystemName=str(design_system.name),
        themeId=audited["themeId"],
        themeName=audited["themeName"],
        themeRole=audited["themeRole"],
        layoutFilename=audited["layoutFilename"],
        cssFilename=audited["cssFilename"],
        settingsFilename=audited.get("settingsFilename"),
        hasManagedMarkerBlock=audited["hasManagedMarkerBlock"],
        layoutIncludesManagedCssAsset=audited["layoutIncludesManagedCssAsset"],
        managedCssAssetExists=audited["managedCssAssetExists"],
        coverage=audited["coverage"],
        settingsAudit=audited["settingsAudit"],
        isReady=audited["isReady"],
    )


@router.get("/{client_id}/active-product")
def get_active_product(
    client_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    clients_repo = ClientsRepository(session)
    client = clients_repo.get(org_id=auth.org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    pref = session.scalar(
        select(ClientUserPreference).where(
            ClientUserPreference.org_id == auth.org_id,
            ClientUserPreference.client_id == client_id,
            ClientUserPreference.user_external_id == auth.user_id,
        )
    )

    active_product: Product | None = None
    if pref and pref.active_product_id:
        active_product = session.scalar(
            select(Product).where(
                Product.org_id == auth.org_id,
                Product.id == pref.active_product_id,
            )
        )
        if not active_product or str(active_product.client_id) != str(client_id):
            pref.active_product_id = None
            pref.updated_at = func.now()
            session.commit()
            active_product = None

    if not active_product:
        active_product = session.scalar(
            select(Product)
            .where(Product.org_id == auth.org_id, Product.client_id == client_id)
            .order_by(Product.created_at.desc(), Product.id.asc())
            .limit(1)
        )
        if not active_product:
            return {"active_product_id": None, "active_product": None}

        if pref:
            pref.active_product_id = active_product.id
            pref.updated_at = func.now()
        else:
            session.add(
                ClientUserPreference(
                    org_id=auth.org_id,
                    client_id=client_id,
                    user_external_id=auth.user_id,
                    active_product_id=active_product.id,
                )
            )
        session.commit()

    return {
        "active_product_id": str(active_product.id),
        "active_product": _serialize_active_product(active_product),
    }


@router.put("/{client_id}/active-product")
def set_active_product(
    client_id: str,
    payload: ActiveProductUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    clients_repo = ClientsRepository(session)
    client = clients_repo.get(org_id=auth.org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    product = session.scalar(
        select(Product).where(
            Product.org_id == auth.org_id,
            Product.id == payload.product_id,
        )
    )
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if str(product.client_id) != str(client_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product must belong to the selected client.",
        )

    pref = session.scalar(
        select(ClientUserPreference).where(
            ClientUserPreference.org_id == auth.org_id,
            ClientUserPreference.client_id == client_id,
            ClientUserPreference.user_external_id == auth.user_id,
        )
    )
    if pref:
        pref.active_product_id = product.id
        pref.updated_at = func.now()
    else:
        session.add(
            ClientUserPreference(
                org_id=auth.org_id,
                client_id=client_id,
                user_external_id=auth.user_id,
                active_product_id=product.id,
            )
        )
    session.commit()

    return {
        "active_product_id": str(product.id),
        "active_product": _serialize_active_product(product),
    }


@router.patch("/{client_id}")
def update_client(
    client_id: str,
    payload: ClientUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = ClientsRepository(session)
    client = repo.get(org_id=auth.org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    fields: dict[str, object] = {}
    if payload.name is not None:
        fields["name"] = payload.name
    if payload.industry is not None:
        fields["industry"] = payload.industry
    if "designSystemId" in payload.model_fields_set:
        design_system_id = payload.designSystemId or None
        if design_system_id:
            design_system_repo = DesignSystemsRepository(session)
            design_system = design_system_repo.get(
                org_id=auth.org_id, design_system_id=design_system_id
            )
            if not design_system:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Design system not found",
                )
            if design_system.client_id and str(design_system.client_id) != str(client_id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Design system must belong to the same client",
                )
        fields["design_system_id"] = design_system_id

    updated = repo.update(org_id=auth.org_id, client_id=client_id, **fields)
    return jsonable_encoder(updated)


@router.delete("/{client_id}")
def delete_client(
    client_id: str,
    payload: ClientDeleteRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = ClientsRepository(session)
    client = repo.get(org_id=auth.org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    if not payload.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Deletion not confirmed"
        )

    if payload.confirm_name != client.name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation name does not match workspace name",
        )

    deleted = repo.delete(org_id=auth.org_id, client_id=client_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete client",
        )

    return {"ok": True}


@router.post("/{client_id}/onboarding")
async def start_client_onboarding(
    client_id: str,
    payload: OnboardingStartRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if payload.business_type != "new":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Existing customer onboarding is not supported yet.",
        )
    onboarding_repo = OnboardingPayloadsRepository(session)
    clients_repo = ClientsRepository(session)
    products_repo = ProductsRepository(session)
    offers_repo = ProductOffersRepository(session)

    client = clients_repo.get(org_id=auth.org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    product_fields: dict[str, object] = {"title": payload.product_name}
    if payload.product_description is not None:
        product_fields["description"] = payload.product_description
    if payload.product_category is not None:
        product_fields["product_type"] = payload.product_category
    if payload.primary_benefits is not None:
        product_fields["primary_benefits"] = payload.primary_benefits
    if payload.feature_bullets is not None:
        product_fields["feature_bullets"] = payload.feature_bullets
    if payload.guarantee_text is not None:
        product_fields["guarantee_text"] = payload.guarantee_text
    if payload.disclaimers is not None:
        product_fields["disclaimers"] = payload.disclaimers

    product = products_repo.create(
        org_id=auth.org_id,
        client_id=client_id,
        **product_fields,
    )

    offer_fields: dict[str, object] = {
        "name": product.title,
        "business_model": "unspecified",
    }
    if payload.product_description is not None:
        offer_fields["description"] = payload.product_description
    if payload.primary_benefits:
        offer_fields["differentiation_bullets"] = payload.primary_benefits
    if payload.guarantee_text is not None:
        offer_fields["guarantee_text"] = payload.guarantee_text

    default_offer = offers_repo.create(
        org_id=auth.org_id,
        client_id=client_id,
        product_id=str(product.id),
        **offer_fields,
    )

    payload_data = payload.model_dump()
    payload_data["product_id"] = str(product.id)
    payload_data["default_offer_id"] = str(default_offer.id)

    onboarding_payload = onboarding_repo.create(
        org_id=auth.org_id,
        client_id=client_id,
        product_id=str(product.id),
        data=payload_data,
    )

    temporal = await get_temporal_client()
    handle = await temporal.start_workflow(
        ClientOnboardingWorkflow.run,
        ClientOnboardingInput(
            org_id=auth.org_id,
            client_id=client_id,
            onboarding_payload_id=str(onboarding_payload.id),
            product_id=str(product.id),
        ),
        id=f"client-onboarding-{auth.org_id}-{client_id}-{onboarding_payload.id}",
        task_queue=settings.TEMPORAL_TASK_QUEUE,
    )

    workflows_repo = WorkflowsRepository(session)
    run = workflows_repo.create_run(
        org_id=auth.org_id,
        client_id=client_id,
        product_id=str(product.id),
        campaign_id=None,
        temporal_workflow_id=handle.id,
        temporal_run_id=handle.first_execution_run_id,
        kind="client_onboarding",
    )
    workflows_repo.log_activity(
        workflow_run_id=str(run.id),
        step="client_onboarding",
        status="started",
        payload_in={
            "client_id": client_id,
            "product_id": str(product.id),
            "onboarding_payload_id": str(onboarding_payload.id),
        },
    )

    return {
        "workflow_run_id": str(run.id),
        "temporal_workflow_id": handle.id,
        "product_id": str(product.id),
        "product_name": product.title,
        "default_offer_id": str(default_offer.id),
    }


@router.post("/{client_id}/intent")
async def start_campaign_intent(
    client_id: str,
    payload: CampaignIntentRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    clients_repo = ClientsRepository(session)
    client = clients_repo.get(org_id=auth.org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    product_id = payload.productId
    products_repo = ProductsRepository(session)
    product = products_repo.get(org_id=auth.org_id, product_id=product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if str(product.client_id) != client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="productId does not belong to the selected workspace.",
        )
    if not payload.channels or not all(
        isinstance(ch, str) and ch.strip() for ch in payload.channels
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="channels must include at least one non-empty value.",
        )
    if not payload.assetBriefTypes or not all(
        isinstance(t, str) and t.strip() for t in payload.assetBriefTypes
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="assetBriefTypes must include at least one non-empty value.",
        )

    artifacts_repo = ArtifactsRepository(session)
    canon = artifacts_repo.get_latest_by_type(
        org_id=auth.org_id,
        client_id=client_id,
        product_id=product_id,
        artifact_type=ArtifactTypeEnum.client_canon,
    )
    metric = artifacts_repo.get_latest_by_type(
        org_id=auth.org_id,
        client_id=client_id,
        product_id=product_id,
        artifact_type=ArtifactTypeEnum.metric_schema,
    )
    wf_repo = WorkflowsRepository(session)
    if not canon or not metric:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete client onboarding (canon + metric schema) before starting campaign intent.",
        )

    temporal = await get_temporal_client()
    handle = await temporal.start_workflow(
        CampaignIntentWorkflow.run,
        CampaignIntentInput(
            org_id=auth.org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_name=payload.campaignName,
            channels=payload.channels,
            asset_brief_types=payload.assetBriefTypes,
            goal_description=payload.goalDescription,
            objective_type=payload.objectiveType,
            numeric_target=payload.numericTarget,
            baseline=payload.baseline,
            timeframe_days=payload.timeframeDays,
            budget_min=payload.budgetMin,
            budget_max=payload.budgetMax,
        ),
        id=f"campaign-intent-{auth.org_id}-{client_id}-{uuid4()}",
        task_queue=settings.TEMPORAL_TASK_QUEUE,
    )

    run = wf_repo.create_run(
        org_id=auth.org_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=None,
        temporal_workflow_id=handle.id,
        temporal_run_id=handle.first_execution_run_id,
        kind="campaign_intent",
    )
    wf_repo.log_activity(
        workflow_run_id=str(run.id),
        step="campaign_intent",
        status="started",
        payload_in={
            "client_id": client_id,
            "product_id": product_id,
            "campaign_name": payload.campaignName,
        },
    )

    return {"workflow_run_id": str(run.id), "temporal_workflow_id": handle.id}
