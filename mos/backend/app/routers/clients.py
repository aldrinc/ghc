import concurrent.futures
from contextvars import ContextVar
from datetime import datetime, timezone
import logging
import re
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
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
from app.services.funnels import create_funnel_image_asset, create_funnel_unsplash_asset
from app.services.shopify_connection import (
    audit_client_shopify_theme_brand,
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
_THEME_SYNC_IMAGE_GENERATION_MAX_CONCURRENCY = max(
    1, settings.FUNNEL_IMAGE_GENERATION_MAX_CONCURRENCY
)
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


def _is_gemini_quota_or_rate_limit_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return (
        "status=429" in message
        or "too many requests" in message
        or "resource_exhausted" in message
    )


def _emit_theme_sync_progress(update: dict[str, Any]) -> None:
    callback = _THEME_SYNC_PROGRESS_CALLBACK.get()
    if not callable(callback):
        return
    try:
        callback(update)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to publish Shopify theme sync progress update")


def _build_theme_sync_slot_unsplash_query(*, slot_role: str, slot_key: str) -> str:
    role_query_by_name = {
        "hero": "beauty tech skincare lifestyle portrait",
        "gallery": "premium skincare product closeup",
        "supporting": "clean beauty wellness routine",
        "background": "minimal neutral skincare background",
        "generic": "beauty wellness lifestyle",
    }
    base_query = role_query_by_name.get(slot_role, role_query_by_name["generic"])
    if slot_key and slot_key != "image":
        return f"{base_query} {slot_key}".strip()
    return base_query


def _normalize_asset_public_id(raw_public_id: Any) -> str | None:
    if isinstance(raw_public_id, UUID):
        return str(raw_public_id)
    if isinstance(raw_public_id, str):
        cleaned = raw_public_id.strip()
        if cleaned:
            return cleaned
    return None


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


def _is_theme_feature_image_slot_path(slot_path: str) -> bool:
    return bool(_THEME_FEATURE_IMAGE_SLOT_PATH_RE.fullmatch(slot_path.strip()))


def _build_theme_sync_image_slot_text_hints(
    *,
    image_slots: list[dict[str, Any]],
    text_slots: list[dict[str, Any]],
) -> dict[str, str]:
    if not image_slots or not text_slots:
        return {}

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

    hints_by_image_slot_path: dict[str, str] = {}
    for raw_image_slot in image_slots:
        if not isinstance(raw_image_slot, dict):
            continue
        raw_image_path = raw_image_slot.get("path")
        if not isinstance(raw_image_path, str) or not raw_image_path.strip():
            continue
        normalized_image_path = raw_image_path.strip()
        if not _is_theme_feature_image_slot_path(normalized_image_path):
            continue
        slot_prefix, separator, _ = normalized_image_path.partition(".settings.")
        if not separator:
            continue

        preferred_keys = ("title", "text", "heading", "subheading", "caption")
        feature_text_fragments: list[str] = []
        for key in preferred_keys:
            candidate_path = f"{slot_prefix}.settings.{key}"
            candidate_value = text_values_by_path.get(candidate_path)
            if not candidate_value:
                continue
            if candidate_value in feature_text_fragments:
                continue
            feature_text_fragments.append(candidate_value)

        if not feature_text_fragments:
            slot_text_prefix = f"{slot_prefix}.settings."
            for candidate_path, candidate_value in text_values_by_path.items():
                if not candidate_path.startswith(slot_text_prefix):
                    continue
                if candidate_value in feature_text_fragments:
                    continue
                feature_text_fragments.append(candidate_value)
                if len(feature_text_fragments) >= 2:
                    break

        if not feature_text_fragments:
            continue

        combined_hint = " ".join(feature_text_fragments).strip()
        if len(combined_hint) > _THEME_IMAGE_PROMPT_TEXT_HINT_MAX_LENGTH:
            combined_hint = combined_hint[:_THEME_IMAGE_PROMPT_TEXT_HINT_MAX_LENGTH].rstrip()
        if not combined_hint:
            continue
        hints_by_image_slot_path[normalized_image_path] = combined_hint

    return hints_by_image_slot_path


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


def _build_theme_sync_slot_image_prompt(
    *,
    slot_role: str,
    slot_key: str,
    aspect_ratio: str,
    variant_index: int,
    slot_text_hint: str | None = None,
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
) -> tuple[list[Any], list[str], dict[str, Any]]:
    selected_slots = _select_theme_sync_slots_for_ai_generation(image_slots=image_slots)
    if not selected_slots:
        return [], [], {}
    slot_text_hints = _build_theme_sync_image_slot_text_hints(
        image_slots=selected_slots,
        text_slots=text_slots or [],
    )

    def _generate_single_slot_asset(
        *,
        slot_path: str,
        slot_key: str,
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
                    product_id=product_id,
                    tags=["shopify_theme_sync", "component_image", "ai_generated"],
                )
                return {
                    "slotPath": slot_path,
                    "asset": generated_asset,
                    "source": "ai",
                    "rateLimited": False,
                    "error": None,
                }
            except Exception as exc:  # noqa: BLE001
                if _is_gemini_quota_or_rate_limit_error(exc):
                    try:
                        generated_asset = create_funnel_unsplash_asset(
                            session=slot_session,
                            org_id=org_id,
                            client_id=client_id,
                            query=_build_theme_sync_slot_unsplash_query(
                                slot_role=slot_role, slot_key=slot_key
                            ),
                            usage_context={
                                "kind": "shopify_theme_sync_component_image",
                                "slotPath": slot_path,
                                "slotRole": slot_role,
                                "recommendedAspect": slot_recommended_aspect,
                                "fallbackSource": "unsplash_after_gemini_rate_limit",
                            },
                            product_id=product_id,
                            tags=[
                                "shopify_theme_sync",
                                "component_image",
                                "unsplash",
                                "fallback_after_rate_limit",
                            ],
                        )
                        return {
                            "slotPath": slot_path,
                            "asset": generated_asset,
                            "source": "unsplash",
                            "rateLimited": True,
                            "error": None,
                        }
                    except Exception as unsplash_exc:  # noqa: BLE001
                        return {
                            "slotPath": slot_path,
                            "asset": None,
                            "source": None,
                            "rateLimited": True,
                            "error": str(unsplash_exc),
                            "geminiError": str(exc),
                        }
                return {
                    "slotPath": slot_path,
                    "asset": None,
                    "source": None,
                    "rateLimited": False,
                    "error": str(exc),
                }

    prepared_slots: list[dict[str, Any]] = []
    generated_assets: list[Any] = []
    rate_limited_slot_paths: list[str] = []
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
            "fallbackImageCount": 0,
            "skippedImageCount": 0,
        }
    )

    if not prepared_slots:
        return generated_assets, rate_limited_slot_paths, generated_asset_by_slot_path

    max_workers = min(_THEME_SYNC_IMAGE_GENERATION_MAX_CONCURRENCY, len(prepared_slots))
    outcomes_by_path: dict[str, dict[str, Any]] = {}
    completed_count = 0
    generated_count = 0
    fallback_count = 0
    skipped_count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures: dict[concurrent.futures.Future[dict[str, Any]], str] = {}
        for slot in prepared_slots:
            future = pool.submit(
                _generate_single_slot_asset,
                slot_path=slot["slotPath"],
                slot_key=slot["slotKey"],
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
                    "error": str(exc),
                }
            outcomes_by_path[slot_path] = outcome
            completed_count += 1
            if outcome.get("asset") is not None:
                if outcome.get("source") == "unsplash":
                    fallback_count += 1
                else:
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
                    "fallbackImageCount": fallback_count,
                    "skippedImageCount": skipped_count,
                    "currentSlotPath": slot_path,
                    "currentSlotSource": outcome.get("source"),
                }
            )

    for slot in prepared_slots:
        slot_path = slot["slotPath"]
        outcome = outcomes_by_path.get(slot_path) or {}
        generated_asset = outcome.get("asset")
        if generated_asset is None:
            if outcome.get("rateLimited"):
                logger.warning(
                    "Theme sync image generation failed for slot after Gemini rate limit; skipping slot.",
                    extra={
                        "slotPath": slot_path,
                        "geminiError": outcome.get("geminiError"),
                        "unsplashError": outcome.get("error"),
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

    return generated_assets, rate_limited_slot_paths, generated_asset_by_slot_path


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

    requested_product_id = payload.productId.strip() if payload.productId else None
    resolved_product: Product | None = None
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

    workspace_name = str(client.name).strip()
    if not workspace_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Workspace name is required to build Shopify theme template drafts.",
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
    if planner_image_slots:
        (
            generated_theme_assets,
            rate_limited_slot_paths,
            generated_asset_by_slot_path,
        ) = _generate_theme_sync_ai_image_assets(
            session=session,
            org_id=auth.org_id,
            client_id=client_id,
            product_id=requested_product_id,
            image_slots=planner_image_slots,
            text_slots=text_slots,
        )

    component_image_asset_map: dict[str, str] = dict(normalized_component_image_asset_map)
    component_text_values: dict[str, str] = {}

    if requested_product_id and resolved_product is not None:
        product_image_assets = assets_repo.list(
            org_id=auth.org_id,
            client_id=client_id,
            product_id=requested_product_id,
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
    "/{client_id}/shopify/theme/brand/template/publish-async",
    response_model=ShopifyThemeTemplatePublishJobStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_client_shopify_theme_template_publish_route(
    client_id: str,
    payload: ShopifyThemeTemplatePublishRequest,
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
    background_tasks.add_task(_run_client_shopify_theme_template_publish_job, str(job.id))

    return ShopifyThemeTemplatePublishJobStartResponse(
        jobId=str(job.id),
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

    requested_product_id = payload.productId.strip() if payload.productId else None
    resolved_product: Product | None = None
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
            (
                generated_theme_assets,
                rate_limited_slot_paths,
                generated_asset_by_slot_path,
            ) = _generate_theme_sync_ai_image_assets(
                session=session,
                org_id=auth.org_id,
                client_id=client_id,
                product_id=requested_product_id,
                image_slots=planner_image_slots,
                text_slots=text_slots,
            )

        if not requested_product_id:
            if rate_limited_slot_paths:
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
            product_id=requested_product_id,
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
