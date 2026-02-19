from __future__ import annotations

import mimetypes
from collections import defaultdict
from typing import Any, Optional
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from pydantic import BaseModel, ConfigDict, Field

from app.auth.dependencies import AuthContext, get_current_user
from app.config import settings
from app.db.deps import get_session
from app.db.enums import AssetStatusEnum
from app.db.models import (
    Asset,
    Campaign,
    Experiment,
    MetaAd,
    MetaAdCreative,
    MetaAdSetSpec,
    MetaAssetUpload,
    MetaCampaign,
    MetaCreativeSpec,
)
from app.db.repositories.assets import AssetsRepository
from app.db.repositories.campaigns import CampaignsRepository
from app.db.repositories.experiments import ExperimentsRepository
from app.db.repositories.meta_ads import MetaAdsRepository
from app.schemas.meta_ads import (
    MetaAdCreateRequest,
    MetaAdSetCreateRequest,
    MetaAdSetSpecCreateRequest,
    MetaAssetUploadRequest,
    MetaCampaignCreateRequest,
    MetaCreativeCreateRequest,
    MetaCreativePreviewRequest,
    MetaCreativeSpecCreateRequest,
)
from app.services.media_storage import MediaStorage
from app.services.meta_ads import MetaAdsClient, MetaAdsConfigError, MetaAdsError
from app.services.meta_media_buying import (
    MetaCutRuleConfig,
    MetaEventMappings,
    MetaInsightsConfig,
    build_management_plan,
)

router = APIRouter(prefix="/meta", tags=["meta"])


class _MetaEventMappingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contentViewActionType: str = "offsite_conversion.fb_pixel_view_content"
    addToCartActionType: str = "offsite_conversion.fb_pixel_add_to_cart"
    purchaseActionType: str = "offsite_conversion.fb_pixel_purchase"
    purchaseValueActionType: str = "offsite_conversion.fb_pixel_purchase"


class MetaManagementPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metaCampaignId: str
    adAccountId: str | None = None
    mode: Literal["plan_only", "apply"] = "plan_only"
    datePreset: str = "last_3d"
    includeRaw: bool = False
    cutRules: MetaCutRuleConfig | None = None
    eventMappings: _MetaEventMappingsRequest | None = None


def _resolve_ad_account_id(ad_account_id: Optional[str]) -> str:
    resolved = ad_account_id or settings.META_AD_ACCOUNT_ID
    if not resolved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="adAccountId is required (or set META_AD_ACCOUNT_ID).",
        )
    return resolved


def _resolve_page_id(page_id: Optional[str]) -> str:
    resolved = page_id or settings.META_PAGE_ID
    if not resolved:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="META_PAGE_ID is required to create ad creatives.",
        )
    return resolved


def _resolve_instagram_actor_id(actor_id: Optional[str]) -> Optional[str]:
    return actor_id or settings.META_INSTAGRAM_ACTOR_ID


def _get_meta_client() -> MetaAdsClient:
    try:
        return MetaAdsClient.from_settings()
    except MetaAdsConfigError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


def _resolve_statuses(statuses: list[str] | None) -> list[AssetStatusEnum] | None:
    if not statuses:
        return None
    resolved: list[AssetStatusEnum] = []
    for entry in statuses:
        if entry not in AssetStatusEnum.__members__:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status: {entry}")
        resolved.append(AssetStatusEnum[entry])
    return resolved


def _fetch_all_pages(fetch_page, *, limit: Optional[int], after: Optional[str]) -> dict[str, Any]:
    data: list[Any] = []
    cursor = after
    seen: set[str] = set()
    pages = 0

    while True:
        response = fetch_page(limit=limit, after=cursor)
        page_data = response.get("data") if isinstance(response, dict) else None
        if page_data:
            data.extend(page_data)
        paging = response.get("paging") if isinstance(response, dict) else None
        cursors = paging.get("cursors") if isinstance(paging, dict) else None
        next_cursor = cursors.get("after") if isinstance(cursors, dict) else None
        pages += 1
        if not next_cursor:
            break
        if next_cursor in seen:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Meta pagination cursor repeated; aborting to avoid an infinite loop.",
            )
        seen.add(next_cursor)
        cursor = next_cursor

    return {"data": data, "paging": {"fetched_pages": pages}}


def _raise_meta_error(exc: MetaAdsError) -> None:
    status_code = exc.status_code or status.HTTP_502_BAD_GATEWAY
    detail: Any = {"message": str(exc)}
    if exc.error_payload is not None:
        detail = {"message": str(exc), "meta": exc.error_payload}
    raise HTTPException(status_code=status_code, detail=detail) from exc


def _infer_media_type(content_type: Optional[str], asset_kind: Optional[str]) -> Optional[str]:
    if content_type:
        if content_type.startswith("image/"):
            return "image"
        if content_type.startswith("video/"):
            return "video"
    if asset_kind in ("image", "video"):
        return asset_kind
    return None


def _asset_filename(asset_id: str, content_type: Optional[str]) -> str:
    ext = mimetypes.guess_extension(content_type or "") or ".bin"
    return f"{asset_id}{ext}"


@router.post("/assets/{asset_id}/upload", status_code=status.HTTP_201_CREATED)
def upload_meta_asset(
    asset_id: str,
    payload: MetaAssetUploadRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    ad_account_id = _resolve_ad_account_id(payload.adAccountId)
    repo = MetaAdsRepository(session)

    existing_request = repo.get_asset_upload_by_request(
        org_id=auth.org_id, ad_account_id=ad_account_id, request_id=payload.requestId
    )
    if existing_request:
        return jsonable_encoder(existing_request)

    existing_asset = repo.get_asset_upload(org_id=auth.org_id, ad_account_id=ad_account_id, asset_id=asset_id)
    if existing_asset:
        if existing_asset.request_id != payload.requestId:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Asset already uploaded with a different requestId.",
            )
        return jsonable_encoder(existing_asset)

    assets_repo = AssetsRepository(session)
    asset = assets_repo.get(org_id=auth.org_id, asset_id=asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    if asset.file_status != "ready" or not asset.storage_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Asset file is not ready for upload.",
        )

    storage = MediaStorage()
    data, detected_type = storage.download_bytes(key=asset.storage_key)
    content_type = asset.content_type or detected_type
    media_type = _infer_media_type(content_type, asset.asset_kind)
    if not media_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Asset must be an image or video with a valid content type.",
        )

    client = _get_meta_client()
    filename = _asset_filename(str(asset.id), content_type)

    try:
        if media_type == "image":
            response = client.upload_image(
                ad_account_id=ad_account_id,
                filename=filename,
                content=data,
                content_type=content_type,
                name=asset.alt,
            )
            images = response.get("images") if isinstance(response, dict) else None
            if not images or not isinstance(images, dict):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Meta image upload response did not include images data.",
                )
            first_key = next(iter(images))
            image_data = images.get(first_key) if isinstance(images, dict) else None
            image_hash = image_data.get("hash") if isinstance(image_data, dict) else None
            if not image_hash:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Meta image upload response did not include an image hash.",
                )
            record = repo.create_asset_upload(
                org_id=auth.org_id,
                asset_id=str(asset.id),
                ad_account_id=ad_account_id,
                request_id=payload.requestId,
                media_type=media_type,
                meta_image_hash=image_hash,
                meta_video_id=None,
                status="uploaded",
                metadata_json=response,
            )
            return jsonable_encoder(record)

        response = client.upload_video(
            ad_account_id=ad_account_id,
            filename=filename,
            content=data,
            content_type=content_type,
            name=asset.alt,
        )
        video_id = response.get("id") if isinstance(response, dict) else None
        if not video_id:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Meta video upload response did not include an id.",
            )
        record = repo.create_asset_upload(
            org_id=auth.org_id,
            asset_id=str(asset.id),
            ad_account_id=ad_account_id,
            request_id=payload.requestId,
            media_type=media_type,
            meta_image_hash=None,
            meta_video_id=video_id,
            status="uploaded",
            metadata_json=response,
        )
        return jsonable_encoder(record)
    except MetaAdsError as exc:
        _raise_meta_error(exc)


@router.post("/creatives", status_code=status.HTTP_201_CREATED)
def create_meta_creative(
    payload: MetaCreativeCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    ad_account_id = _resolve_ad_account_id(payload.adAccountId)
    page_id = _resolve_page_id(payload.pageId)
    instagram_actor_id = _resolve_instagram_actor_id(payload.instagramActorId)
    repo = MetaAdsRepository(session)

    existing = repo.get_creative_by_request(
        org_id=auth.org_id, ad_account_id=ad_account_id, request_id=payload.requestId
    )
    if existing:
        return jsonable_encoder(existing)

    assets_repo = AssetsRepository(session)
    asset = assets_repo.get(org_id=auth.org_id, asset_id=payload.assetId)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    upload = repo.get_asset_upload(org_id=auth.org_id, ad_account_id=ad_account_id, asset_id=str(asset.id))
    if not upload:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Asset must be uploaded to Meta before creating a creative.",
        )

    if upload.meta_image_hash:
        link_data: dict[str, Any] = {
            "link": payload.linkUrl,
            "image_hash": upload.meta_image_hash,
        }
        if payload.message:
            link_data["message"] = payload.message
        if payload.headline:
            link_data["name"] = payload.headline
        if payload.description:
            link_data["description"] = payload.description
        if payload.callToActionType:
            link_data["call_to_action"] = {
                "type": payload.callToActionType,
                "value": {"link": payload.linkUrl},
            }
        object_story_spec: dict[str, Any] = {
            "page_id": page_id,
            "link_data": link_data,
        }
    elif upload.meta_video_id:
        video_data: dict[str, Any] = {
            "video_id": upload.meta_video_id,
            "link": payload.linkUrl,
        }
        if payload.message:
            video_data["message"] = payload.message
        if payload.headline:
            video_data["title"] = payload.headline
        if payload.description:
            video_data["link_description"] = payload.description
        if payload.callToActionType:
            video_data["call_to_action"] = {
                "type": payload.callToActionType,
                "value": {"link": payload.linkUrl},
            }
        object_story_spec = {
            "page_id": page_id,
            "video_data": video_data,
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Meta asset upload is missing image hash or video id.",
        )

    if instagram_actor_id:
        object_story_spec["instagram_actor_id"] = instagram_actor_id

    request_payload: dict[str, Any] = {
        "name": payload.name,
        "object_story_spec": object_story_spec,
    }
    if payload.validateOnly:
        request_payload["execution_options"] = ["validate_only"]

    client = _get_meta_client()
    try:
        response = client.create_adcreative(ad_account_id=ad_account_id, payload=request_payload)
    except MetaAdsError as exc:
        _raise_meta_error(exc)

    if payload.validateOnly:
        return {"validateOnly": True, "response": response}

    creative_id = response.get("id") if isinstance(response, dict) else None
    if not creative_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Meta ad creative response did not include an id.",
        )

    record = repo.create_creative(
        org_id=auth.org_id,
        asset_id=str(asset.id),
        ad_account_id=ad_account_id,
        request_id=payload.requestId,
        meta_creative_id=creative_id,
        name=payload.name,
        status=response.get("status"),
        object_story_spec=object_story_spec,
        metadata_json=response,
    )
    return jsonable_encoder(record)


@router.post("/campaigns", status_code=status.HTTP_201_CREATED)
def create_meta_campaign(
    payload: MetaCampaignCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    ad_account_id = _resolve_ad_account_id(payload.adAccountId)
    repo = MetaAdsRepository(session)

    existing = repo.get_campaign_by_request(
        org_id=auth.org_id, ad_account_id=ad_account_id, request_id=payload.requestId
    )
    if existing:
        return jsonable_encoder(existing)

    campaign_id: Optional[str] = None
    if payload.campaignId:
        campaigns_repo = CampaignsRepository(session)
        campaign = campaigns_repo.get(org_id=auth.org_id, campaign_id=payload.campaignId)
        if not campaign:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
        campaign_id = str(campaign.id)

    request_payload: dict[str, Any] = {
        "name": payload.name,
        "objective": payload.objective,
        "status": payload.status,
    }
    # Meta requires passing this param even when empty.
    request_payload["special_ad_categories"] = payload.specialAdCategories
    if payload.buyingType:
        request_payload["buying_type"] = payload.buyingType

    if payload.dailyBudget is not None and payload.lifetimeBudget is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at most one of dailyBudget or lifetimeBudget.",
        )
    if payload.dailyBudget is None and payload.lifetimeBudget is None:
        if payload.isAdsetBudgetSharingEnabled is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provide dailyBudget/lifetimeBudget for CBO campaigns, or isAdsetBudgetSharingEnabled for ABO campaigns without a campaign budget.",
            )
        request_payload["is_adset_budget_sharing_enabled"] = payload.isAdsetBudgetSharingEnabled
    else:
        if payload.dailyBudget is not None:
            request_payload["daily_budget"] = payload.dailyBudget
        if payload.lifetimeBudget is not None:
            request_payload["lifetime_budget"] = payload.lifetimeBudget
        if payload.isAdsetBudgetSharingEnabled is not None:
            request_payload["is_adset_budget_sharing_enabled"] = payload.isAdsetBudgetSharingEnabled

    if payload.validateOnly:
        request_payload["execution_options"] = ["validate_only"]

    client = _get_meta_client()
    try:
        response = client.create_campaign(ad_account_id=ad_account_id, payload=request_payload)
    except MetaAdsError as exc:
        _raise_meta_error(exc)

    if payload.validateOnly:
        return {"validateOnly": True, "response": response}

    meta_campaign_id = response.get("id") if isinstance(response, dict) else None
    if not meta_campaign_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Meta campaign response did not include an id.",
        )

    record = repo.create_campaign(
        org_id=auth.org_id,
        campaign_id=campaign_id,
        ad_account_id=ad_account_id,
        request_id=payload.requestId,
        meta_campaign_id=meta_campaign_id,
        name=payload.name,
        objective=payload.objective,
        status=payload.status,
        metadata_json=response,
    )
    return jsonable_encoder(record)


@router.post("/adsets", status_code=status.HTTP_201_CREATED)
def create_meta_adset(
    payload: MetaAdSetCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    ad_account_id = _resolve_ad_account_id(payload.adAccountId)
    repo = MetaAdsRepository(session)

    existing = repo.get_adset_by_request(
        org_id=auth.org_id, ad_account_id=ad_account_id, request_id=payload.requestId
    )
    if existing:
        return jsonable_encoder(existing)

    if payload.dailyBudget is not None and payload.lifetimeBudget is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at most one of dailyBudget or lifetimeBudget.",
        )

    request_payload: dict[str, Any] = {
        "name": payload.name,
        "campaign_id": payload.campaignId,
        "status": payload.status,
        "billing_event": payload.billingEvent,
        "optimization_goal": payload.optimizationGoal,
        "targeting": payload.targeting,
    }
    if payload.dailyBudget is not None:
        request_payload["daily_budget"] = payload.dailyBudget
    if payload.lifetimeBudget is not None:
        request_payload["lifetime_budget"] = payload.lifetimeBudget
    if payload.startTime:
        request_payload["start_time"] = payload.startTime
    if payload.endTime:
        request_payload["end_time"] = payload.endTime
    if payload.bidAmount is not None:
        request_payload["bid_amount"] = payload.bidAmount
    if payload.promotedObject:
        request_payload["promoted_object"] = payload.promotedObject
    if payload.validateOnly:
        request_payload["execution_options"] = ["validate_only"]

    client = _get_meta_client()
    try:
        response = client.create_adset(ad_account_id=ad_account_id, payload=request_payload)
    except MetaAdsError as exc:
        _raise_meta_error(exc)

    if payload.validateOnly:
        return {"validateOnly": True, "response": response}

    meta_adset_id = response.get("id") if isinstance(response, dict) else None
    if not meta_adset_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Meta ad set response did not include an id.",
        )

    meta_campaign = repo.get_campaign_by_meta_id(
        org_id=auth.org_id, ad_account_id=ad_account_id, meta_campaign_id=payload.campaignId
    )
    internal_campaign_id = str(meta_campaign.campaign_id) if meta_campaign and meta_campaign.campaign_id else None

    record = repo.create_adset(
        org_id=auth.org_id,
        campaign_id=internal_campaign_id,
        ad_account_id=ad_account_id,
        request_id=payload.requestId,
        meta_campaign_id=payload.campaignId,
        meta_adset_id=meta_adset_id,
        name=payload.name,
        status=payload.status,
        metadata_json=response,
    )
    return jsonable_encoder(record)


@router.post("/ads", status_code=status.HTTP_201_CREATED)
def create_meta_ad(
    payload: MetaAdCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    ad_account_id = _resolve_ad_account_id(payload.adAccountId)
    repo = MetaAdsRepository(session)

    existing = repo.get_ad_by_request(org_id=auth.org_id, ad_account_id=ad_account_id, request_id=payload.requestId)
    if existing:
        return jsonable_encoder(existing)

    request_payload: dict[str, Any] = {
        "name": payload.name,
        "adset_id": payload.adsetId,
        "creative": {"creative_id": payload.creativeId},
        "status": payload.status,
    }
    if payload.trackingSpecs:
        request_payload["tracking_specs"] = payload.trackingSpecs
    if payload.conversionDomain:
        request_payload["conversion_domain"] = payload.conversionDomain
    if payload.validateOnly:
        request_payload["execution_options"] = ["validate_only"]

    client = _get_meta_client()
    try:
        response = client.create_ad(ad_account_id=ad_account_id, payload=request_payload)
    except MetaAdsError as exc:
        _raise_meta_error(exc)

    if payload.validateOnly:
        return {"validateOnly": True, "response": response}

    meta_ad_id = response.get("id") if isinstance(response, dict) else None
    if not meta_ad_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Meta ad response did not include an id.",
        )

    meta_adset = repo.get_adset_by_meta_id(
        org_id=auth.org_id, ad_account_id=ad_account_id, meta_adset_id=payload.adsetId
    )
    internal_campaign_id = str(meta_adset.campaign_id) if meta_adset and meta_adset.campaign_id else None

    record = repo.create_ad(
        org_id=auth.org_id,
        campaign_id=internal_campaign_id,
        ad_account_id=ad_account_id,
        request_id=payload.requestId,
        meta_ad_id=meta_ad_id,
        meta_adset_id=payload.adsetId,
        meta_creative_id=payload.creativeId,
        name=payload.name,
        status=payload.status,
        metadata_json=response,
    )
    return jsonable_encoder(record)


@router.post("/creatives/{creative_id}/previews")
def preview_meta_creative(
    creative_id: str,
    payload: MetaCreativePreviewRequest,
    auth: AuthContext = Depends(get_current_user),
):
    _ = auth
    client = _get_meta_client()
    try:
        response = client.get_creative_previews(
            creative_id=creative_id, ad_format=payload.adFormat, render_type=payload.renderType
        )
    except MetaAdsError as exc:
        _raise_meta_error(exc)
    return response


@router.get("/config")
def get_meta_config(auth: AuthContext = Depends(get_current_user)) -> dict:
    _ = auth
    if not settings.META_AD_ACCOUNT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="META_AD_ACCOUNT_ID is required to access Meta integration.",
        )
    if not settings.META_GRAPH_API_VERSION:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="META_GRAPH_API_VERSION is required to access Meta integration.",
        )
    return {
        "adAccountId": settings.META_AD_ACCOUNT_ID,
        "pageId": settings.META_PAGE_ID,
        "instagramActorId": settings.META_INSTAGRAM_ACTOR_ID,
        "graphApiVersion": settings.META_GRAPH_API_VERSION,
        "graphApiBaseUrl": settings.META_GRAPH_API_BASE_URL,
    }


@router.post("/management/plan")
def plan_meta_management(
    payload: MetaManagementPlanRequest,
    auth: AuthContext = Depends(get_current_user),
):
    """
    Plan-only media buying evaluation for a Meta campaign.

    This endpoint does not mutate Meta objects; it only returns the computed dashboard
    metrics and the actions that would be taken under the current ruleset.
    """
    _ = auth
    ad_account_id = _resolve_ad_account_id(payload.adAccountId)
    cut_rules = payload.cutRules or MetaCutRuleConfig()
    mappings_req = payload.eventMappings or _MetaEventMappingsRequest()
    event_mappings = MetaEventMappings(
        content_view_action_type=mappings_req.contentViewActionType,
        add_to_cart_action_type=mappings_req.addToCartActionType,
        purchase_action_type=mappings_req.purchaseActionType,
        purchase_value_action_type=mappings_req.purchaseValueActionType,
    )
    plan = build_management_plan(
        ad_account_id=ad_account_id,
        campaign_id=payload.metaCampaignId,
        mode=payload.mode,
        insights=MetaInsightsConfig(datePreset=payload.datePreset),
        cut_rules=cut_rules,
        event_mappings=event_mappings,
        include_raw=payload.includeRaw,
    )
    return jsonable_encoder(plan)


@router.post("/specs/creatives", status_code=status.HTTP_201_CREATED)
def create_meta_creative_spec(
    payload: MetaCreativeSpecCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    assets_repo = AssetsRepository(session)
    asset = assets_repo.get(org_id=auth.org_id, asset_id=payload.assetId)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    if payload.campaignId:
        campaigns_repo = CampaignsRepository(session)
        campaign = campaigns_repo.get(org_id=auth.org_id, campaign_id=payload.campaignId)
        if not campaign:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    if payload.experimentId:
        experiments_repo = ExperimentsRepository(session)
        experiment = experiments_repo.get(org_id=auth.org_id, experiment_id=payload.experimentId)
        if not experiment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experiment not found")

    repo = MetaAdsRepository(session)
    existing = repo.get_creative_spec_by_asset(org_id=auth.org_id, asset_id=payload.assetId)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Creative spec already exists for this asset.",
        )

    record = repo.create_creative_spec(
        org_id=auth.org_id,
        asset_id=payload.assetId,
        campaign_id=payload.campaignId,
        experiment_id=payload.experimentId,
        name=payload.name,
        primary_text=payload.primaryText,
        headline=payload.headline,
        description=payload.description,
        call_to_action_type=payload.callToActionType,
        destination_url=payload.destinationUrl,
        page_id=payload.pageId,
        instagram_actor_id=payload.instagramActorId,
        status=payload.status or "draft",
        metadata_json=payload.metadata or {},
    )
    return jsonable_encoder(record)


@router.get("/specs/creatives")
def list_meta_creative_specs(
    campaignId: str | None = None,
    experimentId: str | None = None,
    assetId: str | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list:
    repo = MetaAdsRepository(session)
    records = repo.list_creative_specs(
        org_id=auth.org_id,
        campaign_id=campaignId,
        experiment_id=experimentId,
        asset_id=assetId,
    )
    return jsonable_encoder(records)


@router.post("/specs/adsets", status_code=status.HTTP_201_CREATED)
def create_meta_adset_spec(
    payload: MetaAdSetSpecCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if not payload.campaignId and not payload.experimentId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide campaignId and/or experimentId for ad set spec.",
        )

    if payload.campaignId:
        campaigns_repo = CampaignsRepository(session)
        campaign = campaigns_repo.get(org_id=auth.org_id, campaign_id=payload.campaignId)
        if not campaign:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    if payload.experimentId:
        experiments_repo = ExperimentsRepository(session)
        experiment = experiments_repo.get(org_id=auth.org_id, experiment_id=payload.experimentId)
        if not experiment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experiment not found")

    repo = MetaAdsRepository(session)
    record = repo.create_adset_spec(
        org_id=auth.org_id,
        campaign_id=payload.campaignId,
        experiment_id=payload.experimentId,
        name=payload.name,
        status=payload.status or "draft",
        optimization_goal=payload.optimizationGoal,
        billing_event=payload.billingEvent,
        targeting=payload.targeting,
        placements=payload.placements,
        daily_budget=payload.dailyBudget,
        lifetime_budget=payload.lifetimeBudget,
        bid_amount=payload.bidAmount,
        start_time=payload.startTime,
        end_time=payload.endTime,
        promoted_object=payload.promotedObject,
        conversion_domain=payload.conversionDomain,
        metadata_json=payload.metadata or {},
    )
    return jsonable_encoder(record)


@router.get("/specs/adsets")
def list_meta_adset_specs(
    campaignId: str | None = None,
    experimentId: str | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list:
    repo = MetaAdsRepository(session)
    records = repo.list_adset_specs(
        org_id=auth.org_id,
        campaign_id=campaignId,
        experiment_id=experimentId,
    )
    return jsonable_encoder(records)


@router.get("/pipeline/assets")
def list_meta_pipeline_assets(
    clientId: str | None = None,
    productId: str | None = None,
    campaignId: str | None = None,
    experimentId: str | None = None,
    assetKind: str | None = None,
    statuses: list[str] | None = None,
    adAccountId: str | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list:
    if (clientId and not productId) or (productId and not clientId):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="clientId and productId are required together.",
        )
    ad_account_id = _resolve_ad_account_id(adAccountId)
    assets_repo = AssetsRepository(session)
    resolved_statuses = _resolve_statuses(statuses)
    assets = assets_repo.list(
        org_id=auth.org_id,
        client_id=clientId,
        campaign_id=campaignId,
        experiment_id=experimentId,
        product_id=productId,
        asset_kind=assetKind,
        statuses=resolved_statuses,
    )
    if not assets:
        return []

    asset_ids = [str(asset.id) for asset in assets]
    campaign_ids = {str(asset.campaign_id) for asset in assets if asset.campaign_id}
    experiment_ids = {str(asset.experiment_id) for asset in assets if asset.experiment_id}

    uploads = session.scalars(
        select(MetaAssetUpload).where(
            MetaAssetUpload.org_id == auth.org_id,
            MetaAssetUpload.ad_account_id == ad_account_id,
            MetaAssetUpload.asset_id.in_(asset_ids),
        )
    ).all()
    upload_map = {str(upload.asset_id): upload for upload in uploads}

    creatives = session.scalars(
        select(MetaAdCreative).where(
            MetaAdCreative.org_id == auth.org_id,
            MetaAdCreative.ad_account_id == ad_account_id,
            MetaAdCreative.asset_id.in_(asset_ids),
        )
    ).all()
    creative_map: dict[str, list[MetaAdCreative]] = defaultdict(list)
    creative_ids: list[str] = []
    for creative in creatives:
        creative_map[str(creative.asset_id)].append(creative)
        creative_ids.append(str(creative.meta_creative_id))

    ads_by_creative: dict[str, list[MetaAd]] = defaultdict(list)
    if creative_ids:
        ads = session.scalars(
            select(MetaAd).where(
                MetaAd.org_id == auth.org_id,
                MetaAd.ad_account_id == ad_account_id,
                MetaAd.meta_creative_id.in_(creative_ids),
            )
        ).all()
        for ad in ads:
            ads_by_creative[str(ad.meta_creative_id)].append(ad)

    creative_specs = session.scalars(
        select(MetaCreativeSpec).where(
            MetaCreativeSpec.org_id == auth.org_id,
            MetaCreativeSpec.asset_id.in_(asset_ids),
        )
    ).all()
    creative_spec_map = {str(spec.asset_id): spec for spec in creative_specs}

    adset_specs = []
    if experiment_ids:
        adset_specs = session.scalars(
            select(MetaAdSetSpec).where(
                MetaAdSetSpec.org_id == auth.org_id,
                MetaAdSetSpec.experiment_id.in_(list(experiment_ids)),
            )
        ).all()
    adset_spec_map: dict[str, list[MetaAdSetSpec]] = defaultdict(list)
    for spec in adset_specs:
        if spec.experiment_id:
            adset_spec_map[str(spec.experiment_id)].append(spec)

    campaigns = []
    if campaign_ids:
        campaigns = session.scalars(
            select(Campaign).where(
                Campaign.org_id == auth.org_id,
                Campaign.id.in_(list(campaign_ids)),
            )
        ).all()
    campaign_map = {str(campaign.id): campaign for campaign in campaigns}

    experiments = []
    if experiment_ids:
        experiments = session.scalars(
            select(Experiment).where(
                Experiment.org_id == auth.org_id,
                Experiment.id.in_(list(experiment_ids)),
            )
        ).all()
    experiment_map = {str(exp.id): exp for exp in experiments}

    meta_campaigns = []
    if campaign_ids:
        meta_campaigns = session.scalars(
            select(MetaCampaign).where(
                MetaCampaign.org_id == auth.org_id,
                MetaCampaign.ad_account_id == ad_account_id,
                MetaCampaign.campaign_id.in_(list(campaign_ids)),
            )
        ).all()
    meta_campaign_map = {str(mc.campaign_id): mc for mc in meta_campaigns if mc.campaign_id}

    results: list[dict[str, Any]] = []
    for asset in assets:
        asset_id = str(asset.id)
        campaign_id = str(asset.campaign_id) if asset.campaign_id else None
        experiment_id = str(asset.experiment_id) if asset.experiment_id else None
        campaign = campaign_map.get(campaign_id) if campaign_id else None
        experiment = experiment_map.get(experiment_id) if experiment_id else None
        creative_list = creative_map.get(asset_id, [])
        ads_for_asset: list[MetaAd] = []
        for creative in creative_list:
            ads_for_asset.extend(ads_by_creative.get(str(creative.meta_creative_id), []))

        results.append(
            {
                "asset": {
                    "id": asset_id,
                    "public_id": str(asset.public_id),
                    "status": asset.status,
                    "asset_kind": asset.asset_kind,
                    "client_id": str(asset.client_id),
                    "campaign_id": campaign_id,
                    "experiment_id": experiment_id,
                    "asset_brief_artifact_id": str(asset.asset_brief_artifact_id)
                    if asset.asset_brief_artifact_id
                    else None,
                    "file_status": asset.file_status,
                    "content_type": asset.content_type,
                    "width": asset.width,
                    "height": asset.height,
                    "created_at": asset.created_at,
                    "public_url": f"/public/assets/{asset.public_id}",
                },
                "campaign": {
                    "id": str(campaign.id),
                    "name": campaign.name,
                }
                if campaign
                else None,
                "experiment": {
                    "id": str(experiment.id),
                    "name": experiment.name,
                }
                if experiment
                else None,
                "creative_spec": creative_spec_map.get(asset_id),
                "adset_specs": adset_spec_map.get(experiment_id, []) if experiment_id else [],
                "meta": {
                    "upload": upload_map.get(asset_id),
                    "creatives": creative_list,
                    "ads": ads_for_asset,
                    "meta_campaign": meta_campaign_map.get(campaign_id) if campaign_id else None,
                },
            }
        )

    return jsonable_encoder(results)


@router.get("/remote/adimages")
def list_meta_adimages(
    adAccountId: str | None = None,
    fields: str | None = None,
    limit: int | None = None,
    after: str | None = None,
    fetchAll: bool | None = None,
    auth: AuthContext = Depends(get_current_user),
):
    _ = auth
    ad_account_id = _resolve_ad_account_id(adAccountId)
    client = _get_meta_client()
    resolved_fields = fields or "hash,name,url,created_time,updated_time"

    def fetch_page(*, limit: Optional[int], after: Optional[str]) -> dict[str, Any]:
        return client.list_ad_images(
            ad_account_id=ad_account_id,
            fields=resolved_fields,
            limit=limit,
            after=after,
        )

    if fetchAll:
        return _fetch_all_pages(fetch_page, limit=limit, after=after)
    return fetch_page(limit=limit, after=after)


@router.get("/remote/advideos")
def list_meta_advideos(
    adAccountId: str | None = None,
    fields: str | None = None,
    limit: int | None = None,
    after: str | None = None,
    fetchAll: bool | None = None,
    auth: AuthContext = Depends(get_current_user),
):
    _ = auth
    ad_account_id = _resolve_ad_account_id(adAccountId)
    client = _get_meta_client()
    resolved_fields = fields or "id,title,status,length,created_time,updated_time,thumbnail_url,source"

    def fetch_page(*, limit: Optional[int], after: Optional[str]) -> dict[str, Any]:
        return client.list_ad_videos(
            ad_account_id=ad_account_id,
            fields=resolved_fields,
            limit=limit,
            after=after,
        )

    if fetchAll:
        return _fetch_all_pages(fetch_page, limit=limit, after=after)
    return fetch_page(limit=limit, after=after)


@router.get("/remote/adcreatives")
def list_meta_adcreatives(
    adAccountId: str | None = None,
    fields: str | None = None,
    limit: int | None = None,
    after: str | None = None,
    fetchAll: bool | None = None,
    auth: AuthContext = Depends(get_current_user),
):
    _ = auth
    ad_account_id = _resolve_ad_account_id(adAccountId)
    client = _get_meta_client()
    resolved_fields = fields or "id,name,status,object_story_spec,created_time,updated_time"

    def fetch_page(*, limit: Optional[int], after: Optional[str]) -> dict[str, Any]:
        return client.list_ad_creatives(
            ad_account_id=ad_account_id,
            fields=resolved_fields,
            limit=limit,
            after=after,
        )

    if fetchAll:
        return _fetch_all_pages(fetch_page, limit=limit, after=after)
    return fetch_page(limit=limit, after=after)


@router.get("/remote/campaigns")
def list_meta_campaigns(
    adAccountId: str | None = None,
    fields: str | None = None,
    limit: int | None = None,
    after: str | None = None,
    fetchAll: bool | None = None,
    auth: AuthContext = Depends(get_current_user),
):
    _ = auth
    ad_account_id = _resolve_ad_account_id(adAccountId)
    client = _get_meta_client()
    resolved_fields = fields or "id,name,status,effective_status,objective,created_time,updated_time"

    def fetch_page(*, limit: Optional[int], after: Optional[str]) -> dict[str, Any]:
        return client.list_campaigns(
            ad_account_id=ad_account_id,
            fields=resolved_fields,
            limit=limit,
            after=after,
        )

    if fetchAll:
        return _fetch_all_pages(fetch_page, limit=limit, after=after)
    return fetch_page(limit=limit, after=after)


@router.get("/remote/adsets")
def list_meta_adsets(
    adAccountId: str | None = None,
    fields: str | None = None,
    limit: int | None = None,
    after: str | None = None,
    fetchAll: bool | None = None,
    auth: AuthContext = Depends(get_current_user),
):
    _ = auth
    ad_account_id = _resolve_ad_account_id(adAccountId)
    client = _get_meta_client()
    resolved_fields = fields or "id,name,status,effective_status,campaign_id,created_time,updated_time"

    def fetch_page(*, limit: Optional[int], after: Optional[str]) -> dict[str, Any]:
        return client.list_adsets(
            ad_account_id=ad_account_id,
            fields=resolved_fields,
            limit=limit,
            after=after,
        )

    if fetchAll:
        return _fetch_all_pages(fetch_page, limit=limit, after=after)
    return fetch_page(limit=limit, after=after)


@router.get("/remote/ads")
def list_meta_ads(
    adAccountId: str | None = None,
    fields: str | None = None,
    limit: int | None = None,
    after: str | None = None,
    fetchAll: bool | None = None,
    auth: AuthContext = Depends(get_current_user),
):
    _ = auth
    ad_account_id = _resolve_ad_account_id(adAccountId)
    client = _get_meta_client()
    resolved_fields = fields or "id,name,status,effective_status,adset_id,campaign_id,creative,created_time,updated_time"

    def fetch_page(*, limit: Optional[int], after: Optional[str]) -> dict[str, Any]:
        return client.list_ads(
            ad_account_id=ad_account_id,
            fields=resolved_fields,
            limit=limit,
            after=after,
        )

    if fetchAll:
        return _fetch_all_pages(fetch_page, limit=limit, after=after)
    return fetch_page(limit=limit, after=after)
