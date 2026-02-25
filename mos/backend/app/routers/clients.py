import logging
import re
from typing import Any
from uuid import uuid4

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
from app.db.repositories.products import ProductOffersRepository, ProductsRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.enums import ArtifactTypeEnum
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
    ShopifyThemeBrandSyncJobStatusResponse,
    ShopifyThemeBrandSyncResponse,
)
from app.services.design_system_generation import (
    DesignSystemGenerationError,
    validate_design_system_tokens,
)
from app.services import funnel_ai
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
_JOB_SUBJECT_TYPE_CLIENT = "client"
_THEME_COMPONENT_INLINE_MARKUP_TAG_RE = re.compile(
    r"</?\s*(?:strong|em)\s*>",
    re.IGNORECASE,
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
    without_inline_markup = _THEME_COMPONENT_INLINE_MARKUP_TAG_RE.sub(" ", value)
    sanitized = without_inline_markup.translate(_UNSUPPORTED_THEME_TEXT_VALUE_TRANSLATION)
    return " ".join(sanitized.split()).strip()


def _run_client_shopify_theme_brand_sync_job(job_id: str) -> None:
    session = SessionLocal()
    try:
        jobs_repo = JobsRepository(session)
        job = jobs_repo.mark_running(job_id)
        if not job:
            return

        input_payload = job.input if isinstance(job.input, dict) else {}
        client_id = input_payload.get("clientId")
        raw_request_payload = input_payload.get("payload")
        raw_auth_context = input_payload.get("auth")

        if not isinstance(client_id, str) or not client_id.strip():
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: missing clientId.",
            )
            return
        if not isinstance(raw_request_payload, dict):
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: payload must be an object.",
            )
            return
        if not isinstance(raw_auth_context, dict):
            jobs_repo.mark_failed(
                job_id,
                error="Invalid queued job payload: auth context must be an object.",
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
            )
            return

        try:
            payload = ShopifyThemeBrandSyncRequest(**raw_request_payload)
        except Exception as exc:  # noqa: BLE001
            jobs_repo.mark_failed(
                job_id,
                error=f"Invalid queued job payload: {exc}",
            )
            return

        auth = AuthContext(user_id=user_id.strip(), org_id=org_id.strip())
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
            jobs_repo.mark_failed(
                job_id,
                error=error_message,
                output={
                    "statusCode": exc.status_code,
                    "detail": detail_payload,
                },
            )
            return

        if isinstance(sync_response, ShopifyThemeBrandSyncResponse):
            result_payload = sync_response.model_dump(mode="json")
        elif isinstance(sync_response, dict):
            result_payload = sync_response
        else:
            result_payload = jsonable_encoder(sync_response)

        jobs_repo.mark_succeeded(
            job_id,
            output={"result": result_payload},
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
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to mark Shopify theme brand sync job as failed after exception",
                extra={"job_id": job_id},
            )
    finally:
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
    product_image_asset_public_ids: list[str] = []
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
        try:
            product_image_asset_public_ids = funnel_ai._collect_product_image_public_ids(
                session=session,
                org_id=auth.org_id,
                client_id=client_id,
                product=product,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unable to resolve product image assets for productId={requested_product_id}: {exc}",
            ) from exc
        product_image_asset_public_ids = [
            public_id for public_id in product_image_asset_public_ids if public_id != logo_public_id
        ]
        if not product_image_asset_public_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "No product image assets available for theme sync after excluding the brand logo. "
                    f"productId={requested_product_id}."
                ),
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

    if requested_product_id and resolved_product is not None:
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
        unique_product_image_asset_public_ids = {
            public_id.strip()
            for public_id in product_image_asset_public_ids
            if isinstance(public_id, str) and public_id.strip()
        }

        if len(planner_image_slots) > 1 and len(unique_product_image_asset_public_ids) < 2:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Theme sync discovered multiple image component slots, but fewer than two "
                    "eligible product images were available after filtering. "
                    f"productId={requested_product_id}. Provide additional product images or set "
                    "componentImageAssetMap for explicit slot mapping."
                ),
            )

        if not planner_image_slots and not text_slots:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "No image or text component slots were discovered for AI product content mapping. "
                    f"productId={requested_product_id}."
                ),
            )

        product_image_assets: list[Any] = []
        product_image_assets_by_public_id: dict[str, Any] = {}
        for asset_public_id in product_image_asset_public_ids:
            mapped_asset = assets_repo.get_by_public_id(
                org_id=auth.org_id,
                public_id=asset_public_id,
                client_id=client_id,
            )
            if not mapped_asset:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Product image asset for theme sync could not be resolved in this workspace. "
                        f"assetPublicId={asset_public_id}, productId={requested_product_id}."
                    ),
                )
            product_image_assets.append(mapped_asset)
            product_image_assets_by_public_id[asset_public_id] = mapped_asset

        offers = ProductOffersRepository(session).list_by_product(
            product_id=str(resolved_product.id)
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
