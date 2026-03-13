from __future__ import annotations

import mimetypes
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional
from typing import Literal
from urllib.parse import urljoin, urlparse
from uuid import UUID

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
    MetaPublishRun,
    MetaPublishRunItem,
)
from app.db.repositories.assets import AssetsRepository
from app.db.repositories.campaigns import CampaignsRepository
from app.db.repositories.experiments import ExperimentsRepository
from app.db.repositories.meta_ads import MetaAdsRepository
from app.db.repositories.paid_ads_qa import PaidAdsQaRepository
from app.schemas.meta_ads import (
    MetaAdCreateRequest,
    MetaAdSetCreateRequest,
    MetaAdSetSpecCreateRequest,
    MetaAdSetSpecUpdateRequest,
    MetaAssetUploadRequest,
    MetaCampaignCreateRequest,
    MetaPublishPlanValidationResponse,
    MetaPublishPlanValidationItemResponse,
    MetaPublishRunItemResponse,
    MetaPublishRunRequest,
    MetaPublishRunResponse,
    CampaignMetaPublishSelectionsRequest,
    MetaCreativeCreateRequest,
    MetaCreativePreviewRequest,
    MetaCreativeSpecCreateRequest,
    MetaPublishSelectionResponse,
)
from app.services.image_metadata import (
    ImageMetadataSanitizationError,
    strip_and_validate_image_metadata,
)
from app.services.media_storage import MediaStorage
from app.services.meta_ads import MetaAdsClient, MetaAdsConfigError, MetaAdsError
from app.services.meta_review import (
    asset_funnel_id_from_briefs,
    asset_generation_key,
    collect_asset_funnel_ids,
    load_campaign_asset_brief_map,
)
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


def _meta_experiment_key(*, experiment_id: Optional[str], metadata_json: Any) -> str | None:
    if isinstance(experiment_id, str) and experiment_id.strip():
        return experiment_id.strip()
    if isinstance(metadata_json, dict):
        raw = metadata_json.get("experimentSpecId")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def _asset_generation_key(asset: Asset) -> str:
    return asset_generation_key(asset)


def _resolve_generation_assets(
    *,
    campaign: Campaign,
    generation_key: str,
    funnel_id: str | None,
    auth: AuthContext,
    session: Session,
) -> list[Asset]:
    assets = AssetsRepository(session).list(
        org_id=auth.org_id,
        campaign_id=str(campaign.id),
    )
    generation_assets = [asset for asset in assets if _asset_generation_key(asset) == generation_key]
    if not funnel_id:
        return generation_assets
    brief_map = load_campaign_asset_brief_map(
        org_id=auth.org_id,
        client_id=str(campaign.client_id),
        campaign_id=str(campaign.id),
        session=session,
    )
    return [
        asset
        for asset in generation_assets
        if asset_funnel_id_from_briefs(asset, brief_map=brief_map) == funnel_id
    ]


def _publish_selection_response(record: Any) -> MetaPublishSelectionResponse:
    return MetaPublishSelectionResponse(
        id=str(record.id),
        campaignId=str(record.campaign_id),
        assetId=str(record.asset_id),
        generationKey=record.generation_key,
        decision=record.decision,
        decidedByUserId=record.decided_by_user_id,
        createdAt=record.created_at.isoformat(),
        updatedAt=record.updated_at.isoformat(),
    )


def _clean_optional_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _resolve_publish_destination_url(*, destination_url: str | None, publish_base_url: str) -> str | None:
    cleaned = _clean_optional_text(destination_url)
    if not cleaned:
        return None
    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        return cleaned
    if cleaned.startswith("/"):
        return urljoin(f"{publish_base_url.rstrip('/')}/", cleaned.lstrip("/"))
    return None


def _publish_run_item_response(record: MetaPublishRunItem) -> MetaPublishRunItemResponse:
    return MetaPublishRunItemResponse(
        id=str(record.id),
        assetId=str(record.asset_id),
        creativeSpecId=str(record.creative_spec_id) if record.creative_spec_id else None,
        adsetSpecId=str(record.adset_spec_id) if record.adset_spec_id else None,
        status=record.status,
        resolvedDestinationUrl=record.resolved_destination_url,
        metaAssetUploadId=record.meta_asset_upload_id,
        metaCreativeId=record.meta_creative_id,
        metaAdSetId=record.meta_adset_id,
        metaAdId=record.meta_ad_id,
        errorMessage=record.error_message,
        metadata=record.metadata_json if isinstance(record.metadata_json, dict) else {},
        createdAt=record.created_at.isoformat(),
        updatedAt=record.updated_at.isoformat(),
    )


def _publish_run_response(run: MetaPublishRun, items: list[MetaPublishRunItem]) -> MetaPublishRunResponse:
    special_ad_categories = run.special_ad_categories_json if isinstance(run.special_ad_categories_json, list) else []
    return MetaPublishRunResponse(
        id=str(run.id),
        campaignId=str(run.campaign_id),
        generationKey=run.generation_key,
        status=run.status,
        campaignName=run.campaign_name,
        campaignObjective=run.campaign_objective,
        buyingType=run.buying_type,
        specialAdCategories=[str(entry).strip() for entry in special_ad_categories if isinstance(entry, str) and entry.strip()],
        publishBaseUrl=run.publish_base_url,
        publishDomain=run.publish_domain,
        adAccountId=run.ad_account_id,
        pageId=run.page_id,
        metaCampaignId=run.meta_campaign_id,
        errorMessage=run.error_message,
        metadata=run.metadata_json if isinstance(run.metadata_json, dict) else {},
        items=[_publish_run_item_response(item) for item in items],
        createdByUserId=run.created_by_user_id,
        createdAt=run.created_at.isoformat(),
        updatedAt=run.updated_at.isoformat(),
        completedAt=run.completed_at.isoformat() if run.completed_at else None,
    )


def _validate_publish_plan(
    *,
    campaign: Campaign,
    payload: MetaPublishRunRequest,
    auth: AuthContext,
    session: Session,
) -> tuple[MetaPublishPlanValidationResponse, list[dict[str, Any]]]:
    meta_repo = MetaAdsRepository(session)
    all_generation_assets = _resolve_generation_assets(
        campaign=campaign,
        generation_key=payload.generationKey,
        funnel_id=None,
        auth=auth,
        session=session,
    )
    brief_map = load_campaign_asset_brief_map(
        org_id=auth.org_id,
        client_id=str(campaign.client_id),
        campaign_id=str(campaign.id),
        session=session,
    )
    generation_funnel_ids = collect_asset_funnel_ids(assets=all_generation_assets, brief_map=brief_map)
    resolved_funnel_id = _clean_optional_text(payload.funnelId)

    blockers: list[str] = []
    if resolved_funnel_id is None and len(generation_funnel_ids) > 1:
        blockers.append(
            "Publish validation requires an explicit funnel when the selected generation spans multiple funnels."
        )
    if resolved_funnel_id and generation_funnel_ids and resolved_funnel_id not in generation_funnel_ids:
        blockers.append("The requested funnel has no generated assets in the selected publish generation.")
    if resolved_funnel_id is None and len(generation_funnel_ids) == 1:
        resolved_funnel_id = next(iter(generation_funnel_ids))

    generation_assets = (
        [
            asset
            for asset in all_generation_assets
            if asset_funnel_id_from_briefs(asset, brief_map=brief_map) == resolved_funnel_id
        ]
        if resolved_funnel_id
        else all_generation_assets
    )
    excluded_asset_ids = {
        str(selection.asset_id)
        for selection in meta_repo.list_publish_selections(
            org_id=auth.org_id,
            campaign_id=str(campaign.id),
            generation_key=payload.generationKey,
            decision="excluded",
        )
    }
    selected_assets = [asset for asset in generation_assets if str(asset.id) not in excluded_asset_ids]
    if not generation_assets:
        if resolved_funnel_id:
            blockers.append("No campaign assets were found for this funnel in the selected publish generation.")
        else:
            blockers.append("No campaign assets were found for this publish generation.")
    elif not selected_assets:
        blockers.append("All creatives are excluded from the final Meta package for this generation.")

    profile = PaidAdsQaRepository(session).get_platform_profile(
        org_id=auth.org_id,
        client_id=str(campaign.client_id),
        platform="meta",
    )
    ad_account_id = _clean_optional_text(getattr(profile, "ad_account_id", None))
    profile_page_id = _clean_optional_text(getattr(profile, "page_id", None))
    if not ad_account_id:
        blockers.append("Meta platform profile is missing adAccountId.")

    asset_ids = [str(asset.id) for asset in selected_assets]
    asset_rows = session.scalars(
        select(Asset).where(
            Asset.org_id == auth.org_id,
            Asset.campaign_id == str(campaign.id),
            Asset.id.in_(asset_ids),
        )
    ).all()
    assets_by_id = {str(asset.id): asset for asset in asset_rows}

    creative_specs = session.scalars(
        select(MetaCreativeSpec).where(
            MetaCreativeSpec.org_id == auth.org_id,
            MetaCreativeSpec.asset_id.in_(asset_ids),
        )
    ).all()
    creative_specs_by_asset_id = {str(spec.asset_id): spec for spec in creative_specs}

    adset_specs = session.scalars(
        select(MetaAdSetSpec).where(
            MetaAdSetSpec.org_id == auth.org_id,
            MetaAdSetSpec.campaign_id == str(campaign.id),
        )
    ).all()
    adset_spec_map: dict[str, list[MetaAdSetSpec]] = defaultdict(list)
    for spec in adset_specs:
        experiment_key = _meta_experiment_key(
            experiment_id=str(spec.experiment_id) if spec.experiment_id else None,
            metadata_json=spec.metadata_json,
        )
        if experiment_key:
            adset_spec_map[experiment_key].append(spec)

    validation_items: list[MetaPublishPlanValidationItemResponse] = []
    resolved_items: list[dict[str, Any]] = []
    publish_domains: set[str] = set()

    for asset in selected_assets:
        asset_id = str(asset.id)
        item_blockers: list[str] = []
        asset = assets_by_id.get(asset_id)
        creative_spec = creative_specs_by_asset_id.get(asset_id)
        adset_spec: MetaAdSetSpec | None = None
        resolved_destination_url: str | None = None

        if asset is None:
            item_blockers.append("Final-package asset was not found on this campaign.")
        if creative_spec is None:
            item_blockers.append("Final-package asset is missing a prepared Meta creative spec.")

        if asset is not None and creative_spec is not None:
            experiment_key = (
                str(asset.experiment_id)
                if asset.experiment_id
                else _meta_experiment_key(
                    experiment_id=str(creative_spec.experiment_id) if creative_spec.experiment_id else None,
                    metadata_json=creative_spec.metadata_json,
                )
            )
            linked_adset_specs = adset_spec_map.get(experiment_key, []) if experiment_key else []
            if not linked_adset_specs:
                item_blockers.append("Final-package asset is missing a linked Meta ad set spec.")
            elif len(linked_adset_specs) > 1:
                item_blockers.append(
                    "Final-package asset resolves to multiple Meta ad set specs. Publish requires exactly one."
                )
            else:
                adset_spec = linked_adset_specs[0]
                if not _clean_optional_text(adset_spec.name):
                    item_blockers.append("Linked Meta ad set spec is missing a name.")
                if not _clean_optional_text(adset_spec.optimization_goal):
                    item_blockers.append("Linked Meta ad set spec is missing optimizationGoal.")
                if not _clean_optional_text(adset_spec.billing_event):
                    item_blockers.append("Linked Meta ad set spec is missing billingEvent.")
                if not isinstance(adset_spec.targeting, dict) or not adset_spec.targeting:
                    item_blockers.append("Linked Meta ad set spec is missing targeting.")
                if adset_spec.daily_budget is None and adset_spec.lifetime_budget is None:
                    item_blockers.append("Linked Meta ad set spec must set either dailyBudget or lifetimeBudget.")
                if adset_spec.daily_budget is not None and adset_spec.lifetime_budget is not None:
                    item_blockers.append("Linked Meta ad set spec cannot set both dailyBudget and lifetimeBudget.")
                if adset_spec.start_time and adset_spec.end_time and adset_spec.end_time <= adset_spec.start_time:
                    item_blockers.append("Linked Meta ad set spec endTime must be after startTime.")

            effective_page_id = _clean_optional_text(creative_spec.page_id) or profile_page_id
            if not effective_page_id:
                item_blockers.append("Final-package asset is missing an effective Meta pageId.")

            resolved_destination_url = _resolve_publish_destination_url(
                destination_url=_clean_optional_text(creative_spec.destination_url),
                publish_base_url=payload.publishBaseUrl,
            )
            if not resolved_destination_url:
                item_blockers.append(
                    "Creative destination URL must be absolute or start with '/' so it can resolve against publishBaseUrl."
                )
            else:
                destination_host = urlparse(resolved_destination_url).hostname
                if destination_host:
                    publish_domains.add(destination_host.lower())

        validation_items.append(
            MetaPublishPlanValidationItemResponse(
                assetId=asset_id,
                creativeSpecId=str(creative_spec.id) if creative_spec else None,
                adsetSpecId=str(adset_spec.id) if adset_spec else None,
                resolvedDestinationUrl=resolved_destination_url,
                status="blocked" if item_blockers else "ok",
                blockers=item_blockers,
            )
        )

        if not item_blockers and asset is not None and creative_spec is not None and adset_spec is not None:
            resolved_items.append(
                {
                    "asset": asset,
                    "creative_spec": creative_spec,
                    "adset_spec": adset_spec,
                    "resolved_destination_url": resolved_destination_url,
                    "effective_page_id": _clean_optional_text(creative_spec.page_id) or profile_page_id,
                }
            )

    if len(publish_domains) > 1:
        blockers.append("Final-package creatives resolve to multiple publish domains. Use one launch domain per publish run.")

    validation_response = MetaPublishPlanValidationResponse(
        campaignId=str(campaign.id),
        generationKey=payload.generationKey,
        ok=not blockers and all(item.status == "ok" for item in validation_items),
        includedCount=len(selected_assets),
        adsetCount=len({str(item["adset_spec"].id) for item in resolved_items}),
        publishBaseUrl=payload.publishBaseUrl,
        publishDomain=next(iter(publish_domains)) if len(publish_domains) == 1 else None,
        blockers=blockers,
        items=validation_items,
    )
    return validation_response, resolved_items


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

    if media_type == "image":
        try:
            sanitized = strip_and_validate_image_metadata(content=data, content_type=content_type)
        except ImageMetadataSanitizationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Asset metadata sanitization failed: {exc}",
            ) from exc
        data = sanitized.content
        content_type = sanitized.content_type

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


@router.put("/specs/adsets/{adset_spec_id}")
def update_meta_adset_spec(
    adset_spec_id: str,
    payload: MetaAdSetSpecUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = MetaAdsRepository(session)
    record = repo.get_adset_spec(org_id=auth.org_id, adset_spec_id=adset_spec_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meta ad set spec not found")

    update_fields = payload.model_dump(exclude_unset=True)
    if not update_fields:
        return jsonable_encoder(record)

    daily_budget = update_fields.get("dailyBudget", record.daily_budget)
    lifetime_budget = update_fields.get("lifetimeBudget", record.lifetime_budget)
    if daily_budget is not None and lifetime_budget is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at most one of dailyBudget or lifetimeBudget.",
        )

    start_time = update_fields.get("startTime", record.start_time)
    end_time = update_fields.get("endTime", record.end_time)
    if start_time and end_time and end_time <= start_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="endTime must be after startTime.",
        )

    updated = repo.update_adset_spec(
        record,
        name=_clean_optional_text(update_fields["name"]) if "name" in update_fields else record.name,
        optimization_goal=(
            _clean_optional_text(update_fields["optimizationGoal"])
            if "optimizationGoal" in update_fields
            else record.optimization_goal
        ),
        billing_event=(
            _clean_optional_text(update_fields["billingEvent"])
            if "billingEvent" in update_fields
            else record.billing_event
        ),
        targeting=update_fields["targeting"] if "targeting" in update_fields else record.targeting,
        placements=update_fields["placements"] if "placements" in update_fields else record.placements,
        daily_budget=daily_budget,
        lifetime_budget=lifetime_budget,
        bid_amount=update_fields["bidAmount"] if "bidAmount" in update_fields else record.bid_amount,
        start_time=start_time,
        end_time=end_time,
        promoted_object=update_fields["promotedObject"] if "promotedObject" in update_fields else record.promoted_object,
        conversion_domain=(
            _clean_optional_text(update_fields["conversionDomain"])
            if "conversionDomain" in update_fields
            else record.conversion_domain
        ),
        metadata_json=(
            update_fields["metadata"]
            if "metadata" in update_fields and update_fields["metadata"] is not None
            else record.metadata_json
        ),
    )
    return jsonable_encoder(updated)


@router.get("/campaigns/{campaign_id}/publish-selections", response_model=list[MetaPublishSelectionResponse])
def list_meta_publish_selections(
    campaign_id: str,
    generationKey: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    generation_key = generationKey.strip()
    if not generation_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="generationKey is required.")

    campaigns_repo = CampaignsRepository(session)
    campaign = campaigns_repo.get(org_id=auth.org_id, campaign_id=campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    repo = MetaAdsRepository(session)
    records = repo.list_publish_selections(
        org_id=auth.org_id,
        campaign_id=str(campaign.id),
        generation_key=generation_key,
        decision="excluded",
    )
    return [_publish_selection_response(record) for record in records]


@router.put("/campaigns/{campaign_id}/publish-selections", response_model=list[MetaPublishSelectionResponse])
def update_meta_publish_selections(
    campaign_id: str,
    payload: CampaignMetaPublishSelectionsRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    campaigns_repo = CampaignsRepository(session)
    campaign = campaigns_repo.get(org_id=auth.org_id, campaign_id=campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    repo = MetaAdsRepository(session)
    asset_ids = [decision.assetId for decision in payload.decisions]
    if asset_ids:
        asset_rows = session.scalars(
            select(Asset).where(
                Asset.org_id == auth.org_id,
                Asset.campaign_id == str(campaign.id),
                Asset.id.in_(asset_ids),
            )
        ).all()
        assets_by_id = {str(asset.id): asset for asset in asset_rows}
        missing_asset_ids = sorted(set(asset_ids).difference(assets_by_id.keys()))
        if missing_asset_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "message": "Some campaign assets were not found for publish selection.",
                    "missingAssetIds": missing_asset_ids,
                },
            )
        invalid_generation_asset_ids = [
            asset_id for asset_id, asset in assets_by_id.items() if _asset_generation_key(asset) != payload.generationKey
        ]
        if invalid_generation_asset_ids:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Some campaign assets do not belong to the requested publish generation.",
                    "invalidAssetIds": sorted(invalid_generation_asset_ids),
                },
            )

    existing_by_asset_id = {
        str(record.asset_id): record
        for record in repo.list_publish_selections(
            org_id=auth.org_id,
            campaign_id=str(campaign.id),
            generation_key=payload.generationKey,
        )
    }

    for mutation in payload.decisions:
        existing = existing_by_asset_id.get(mutation.assetId)
        if mutation.decision is None:
            if existing is not None:
                repo.delete_publish_selection(existing)
            continue
        if existing is None:
            repo.create_publish_selection(
                org_id=auth.org_id,
                campaign_id=str(campaign.id),
                asset_id=mutation.assetId,
                generation_key=payload.generationKey,
                decision=mutation.decision,
                decided_by_user_id=auth.user_id,
                metadata_json={},
            )
            continue
        repo.update_publish_selection(
            existing,
            decision=mutation.decision,
            decided_by_user_id=auth.user_id,
        )

    records = repo.list_publish_selections(
        org_id=auth.org_id,
        campaign_id=str(campaign.id),
        generation_key=payload.generationKey,
        decision="excluded",
    )
    return [_publish_selection_response(record) for record in records]


@router.post(
    "/campaigns/{campaign_id}/publish-plan/validate",
    response_model=MetaPublishPlanValidationResponse,
)
def validate_meta_publish_plan(
    campaign_id: str,
    payload: MetaPublishRunRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    campaigns_repo = CampaignsRepository(session)
    campaign = campaigns_repo.get(org_id=auth.org_id, campaign_id=campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    validation_response, _resolved_items = _validate_publish_plan(
        campaign=campaign,
        payload=payload,
        auth=auth,
        session=session,
    )
    return validation_response


@router.get("/campaigns/{campaign_id}/publish-runs", response_model=list[MetaPublishRunResponse])
def list_meta_publish_runs(
    campaign_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    campaigns_repo = CampaignsRepository(session)
    campaign = campaigns_repo.get(org_id=auth.org_id, campaign_id=campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    repo = MetaAdsRepository(session)
    runs = repo.list_publish_runs(org_id=auth.org_id, campaign_id=str(campaign.id))
    return [
        _publish_run_response(run, repo.list_publish_run_items(org_id=auth.org_id, publish_run_id=str(run.id)))
        for run in runs
    ]


@router.post("/campaigns/{campaign_id}/publish-runs", response_model=MetaPublishRunResponse)
def create_meta_publish_run(
    campaign_id: str,
    payload: MetaPublishRunRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    campaigns_repo = CampaignsRepository(session)
    campaign = campaigns_repo.get(org_id=auth.org_id, campaign_id=campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    validation_response, resolved_items = _validate_publish_plan(
        campaign=campaign,
        payload=payload,
        auth=auth,
        session=session,
    )
    if not validation_response.ok:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Publish plan is blocked.",
                "validation": jsonable_encoder(validation_response),
            },
        )

    profile = PaidAdsQaRepository(session).get_platform_profile(
        org_id=auth.org_id,
        client_id=str(campaign.client_id),
        platform="meta",
    )
    ad_account_id = _clean_optional_text(getattr(profile, "ad_account_id", None))
    page_id = _clean_optional_text(getattr(profile, "page_id", None))
    if not ad_account_id or not page_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Meta platform profile must have adAccountId and pageId before publishing.",
        )

    repo = MetaAdsRepository(session)
    run = repo.create_publish_run(
        org_id=auth.org_id,
        campaign_id=str(campaign.id),
        generation_key=payload.generationKey,
        status="running",
        campaign_name=payload.campaignName,
        campaign_objective=payload.campaignObjective,
        buying_type=payload.buyingType,
        special_ad_categories_json=payload.specialAdCategories,
        publish_base_url=payload.publishBaseUrl,
        publish_domain=validation_response.publishDomain,
        ad_account_id=ad_account_id,
        page_id=page_id,
        meta_campaign_id=None,
        created_by_user_id=auth.user_id,
        error_message=None,
        metadata_json={
            "validation": validation_response.model_dump(mode="json"),
            "funnelId": _clean_optional_text(payload.funnelId),
        },
        completed_at=None,
    )

    run_items_by_asset_id: dict[str, MetaPublishRunItem] = {}
    for resolved in resolved_items:
        asset = resolved["asset"]
        creative_spec = resolved["creative_spec"]
        adset_spec = resolved["adset_spec"]
        run_item = repo.create_publish_run_item(
            org_id=auth.org_id,
            publish_run_id=str(run.id),
            asset_id=str(asset.id),
            creative_spec_id=str(creative_spec.id),
            adset_spec_id=str(adset_spec.id),
            status="pending",
            resolved_destination_url=resolved["resolved_destination_url"],
            meta_asset_upload_id=None,
            meta_creative_id=None,
            meta_adset_id=None,
            meta_ad_id=None,
            error_message=None,
            metadata_json={
                "assetPublicId": str(asset.public_id),
                "creativeSpecName": creative_spec.name,
                "adsetSpecName": adset_spec.name,
            },
        )
        run_items_by_asset_id[str(asset.id)] = run_item

    try:
        created_campaign = create_meta_campaign(
            MetaCampaignCreateRequest(
                requestId=f"meta-publish-run:{run.id}:campaign",
                adAccountId=ad_account_id,
                campaignId=str(campaign.id),
                name=payload.campaignName,
                objective=payload.campaignObjective,
                status="PAUSED",
                specialAdCategories=payload.specialAdCategories,
                buyingType=payload.buyingType,
                isAdsetBudgetSharingEnabled=False,
            ),
            auth=auth,
            session=session,
        )
        meta_campaign_id = _clean_optional_text(created_campaign.get("meta_campaign_id"))
        run = repo.update_publish_run(
            run,
            meta_campaign_id=meta_campaign_id,
            metadata_json={
                **(run.metadata_json if isinstance(run.metadata_json, dict) else {}),
                "campaign": created_campaign,
            },
        )

        meta_adset_id_by_spec_id: dict[str, str] = {}
        unique_adset_specs: dict[str, MetaAdSetSpec] = {}
        for resolved in resolved_items:
            unique_adset_specs[str(resolved["adset_spec"].id)] = resolved["adset_spec"]

        for adset_spec_id, adset_spec in unique_adset_specs.items():
            created_adset = create_meta_adset(
                MetaAdSetCreateRequest(
                    requestId=f"meta-publish-run:{run.id}:adset:{adset_spec_id}",
                    adAccountId=ad_account_id,
                    campaignId=meta_campaign_id or "",
                    name=_clean_optional_text(adset_spec.name) or adset_spec_id,
                    status="PAUSED",
                    dailyBudget=adset_spec.daily_budget,
                    lifetimeBudget=adset_spec.lifetime_budget,
                    billingEvent=_clean_optional_text(adset_spec.billing_event) or "",
                    optimizationGoal=_clean_optional_text(adset_spec.optimization_goal) or "",
                    targeting=adset_spec.targeting or {},
                    startTime=adset_spec.start_time.isoformat() if adset_spec.start_time else None,
                    endTime=adset_spec.end_time.isoformat() if adset_spec.end_time else None,
                    bidAmount=adset_spec.bid_amount,
                    promotedObject=adset_spec.promoted_object,
                    validateOnly=False,
                ),
                auth=auth,
                session=session,
            )
            meta_adset_id = _clean_optional_text(created_adset.get("meta_adset_id"))
            if not meta_adset_id:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Meta publish run did not receive a meta_adset_id for ad set spec {adset_spec_id}.",
                )
            meta_adset_id_by_spec_id[adset_spec_id] = meta_adset_id

        for resolved in resolved_items:
            asset = resolved["asset"]
            creative_spec = resolved["creative_spec"]
            adset_spec = resolved["adset_spec"]
            run_item = run_items_by_asset_id[str(asset.id)]

            uploaded_asset = upload_meta_asset(
                str(asset.id),
                MetaAssetUploadRequest(
                    requestId=f"meta-publish-run:{run.id}:asset:{asset.id}:upload",
                    adAccountId=ad_account_id,
                ),
                auth=auth,
                session=session,
            )
            created_creative = create_meta_creative(
                MetaCreativeCreateRequest(
                    requestId=f"meta-publish-run:{run.id}:asset:{asset.id}:creative",
                    adAccountId=ad_account_id,
                    assetId=str(asset.id),
                    name=_clean_optional_text(creative_spec.name) or str(asset.public_id),
                    pageId=resolved["effective_page_id"],
                    instagramActorId=_clean_optional_text(creative_spec.instagram_actor_id),
                    linkUrl=resolved["resolved_destination_url"],
                    message=_clean_optional_text(creative_spec.primary_text),
                    headline=_clean_optional_text(creative_spec.headline),
                    description=_clean_optional_text(creative_spec.description),
                    callToActionType=_clean_optional_text(creative_spec.call_to_action_type),
                    validateOnly=False,
                ),
                auth=auth,
                session=session,
            )
            meta_creative_id = _clean_optional_text(created_creative.get("meta_creative_id"))
            if not meta_creative_id:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Meta publish run did not receive a meta_creative_id for asset {asset.id}.",
                )

            created_ad = create_meta_ad(
                MetaAdCreateRequest(
                    requestId=f"meta-publish-run:{run.id}:asset:{asset.id}:ad",
                    adAccountId=ad_account_id,
                    adsetId=meta_adset_id_by_spec_id[str(adset_spec.id)],
                    creativeId=meta_creative_id,
                    name=_clean_optional_text(creative_spec.name) or str(asset.public_id),
                    status="PAUSED",
                    trackingSpecs=None,
                    conversionDomain=_clean_optional_text(adset_spec.conversion_domain),
                    validateOnly=False,
                ),
                auth=auth,
                session=session,
            )
            meta_ad_id = _clean_optional_text(created_ad.get("meta_ad_id"))
            if not meta_ad_id:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Meta publish run did not receive a meta_ad_id for asset {asset.id}.",
                )

            updated_item = repo.update_publish_run_item(
                run_item,
                status="published",
                meta_asset_upload_id=_clean_optional_text(uploaded_asset.get("id")),
                meta_creative_id=meta_creative_id,
                meta_adset_id=meta_adset_id_by_spec_id[str(adset_spec.id)],
                meta_ad_id=meta_ad_id,
                metadata_json={
                    **(run_item.metadata_json if isinstance(run_item.metadata_json, dict) else {}),
                    "upload": uploaded_asset,
                    "creative": created_creative,
                    "ad": created_ad,
                },
            )
            run_items_by_asset_id[str(asset.id)] = updated_item

        run = repo.update_publish_run(
            run,
            status="published",
            completed_at=datetime.now(timezone.utc),
        )
    except HTTPException as exc:
        error_message = exc.detail if isinstance(exc.detail, str) else jsonable_encoder(exc.detail)
        run = repo.update_publish_run(
            run,
            status="failed",
            error_message=error_message if isinstance(error_message, str) else str(error_message),
            completed_at=datetime.now(timezone.utc),
        )
        for item in run_items_by_asset_id.values():
            if item.status == "published":
                continue
            repo.update_publish_run_item(
                item,
                status="failed",
                error_message=error_message if isinstance(error_message, str) else str(error_message),
            )
    except Exception as exc:  # noqa: BLE001
        run = repo.update_publish_run(
            run,
            status="failed",
            error_message=str(exc),
            completed_at=datetime.now(timezone.utc),
        )
        for item in run_items_by_asset_id.values():
            if item.status == "published":
                continue
            repo.update_publish_run_item(item, status="failed", error_message=str(exc))

    items = repo.list_publish_run_items(org_id=auth.org_id, publish_run_id=str(run.id))
    return _publish_run_response(run, items)


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
    ad_account_id = adAccountId or settings.META_AD_ACCOUNT_ID
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

    uploads = []
    if ad_account_id:
        uploads = session.scalars(
            select(MetaAssetUpload).where(
                MetaAssetUpload.org_id == auth.org_id,
                MetaAssetUpload.ad_account_id == ad_account_id,
                MetaAssetUpload.asset_id.in_(asset_ids),
            )
        ).all()
    upload_map = {str(upload.asset_id): upload for upload in uploads}

    creatives = []
    if ad_account_id:
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
    if creative_ids and ad_account_id:
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
    experiment_keys_from_specs = {
        key
        for key in (
            _meta_experiment_key(experiment_id=str(spec.experiment_id) if spec.experiment_id else None, metadata_json=spec.metadata_json)
            for spec in creative_specs
        )
        if key
    }
    experiment_ids.update(experiment_keys_from_specs)

    adset_specs = []
    if campaignId:
        adset_specs = session.scalars(
            select(MetaAdSetSpec).where(
                MetaAdSetSpec.org_id == auth.org_id,
                MetaAdSetSpec.campaign_id == campaignId,
            )
        ).all()
    elif experiment_ids:
        adset_specs = session.scalars(
            select(MetaAdSetSpec).where(
                MetaAdSetSpec.org_id == auth.org_id,
                MetaAdSetSpec.experiment_id.in_(list(experiment_ids)),
            )
        ).all()
    adset_spec_map: dict[str, list[MetaAdSetSpec]] = defaultdict(list)
    for spec in adset_specs:
        experiment_key = _meta_experiment_key(
            experiment_id=str(spec.experiment_id) if spec.experiment_id else None,
            metadata_json=spec.metadata_json,
        )
        if experiment_key:
            adset_spec_map[experiment_key].append(spec)

    campaigns = []
    if campaign_ids:
        campaigns = session.scalars(
            select(Campaign).where(
                Campaign.org_id == auth.org_id,
                Campaign.id.in_(list(campaign_ids)),
            )
        ).all()
    campaign_map = {str(campaign.id): campaign for campaign in campaigns}

    internal_experiment_ids: list[str] = []
    for experiment_id in experiment_ids:
        try:
            internal_experiment_ids.append(str(UUID(experiment_id)))
        except (TypeError, ValueError):
            continue

    experiments = []
    if internal_experiment_ids:
        experiments = session.scalars(
            select(Experiment).where(
                Experiment.org_id == auth.org_id,
                Experiment.id.in_(internal_experiment_ids),
            )
        ).all()
    experiment_map = {str(exp.id): exp for exp in experiments}

    meta_campaigns = []
    if campaign_ids and ad_account_id:
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
        creative_spec = creative_spec_map.get(asset_id)
        experiment_id = (
            str(asset.experiment_id)
            if asset.experiment_id
            else _meta_experiment_key(
                experiment_id=str(creative_spec.experiment_id) if creative_spec and creative_spec.experiment_id else None,
                metadata_json=creative_spec.metadata_json if creative_spec else None,
            )
        )
        campaign = campaign_map.get(campaign_id) if campaign_id else None
        experiment = experiment_map.get(experiment_id) if experiment_id else None
        creative_metadata = creative_spec.metadata_json if creative_spec and isinstance(creative_spec.metadata_json, dict) else {}
        experiment_name = None
        if experiment:
            experiment_name = experiment.name
        elif isinstance(creative_metadata.get("experimentName"), str) and creative_metadata.get("experimentName").strip():
            experiment_name = creative_metadata.get("experimentName").strip()
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
                    "ai_metadata": asset.ai_metadata if isinstance(asset.ai_metadata, dict) else None,
                },
                "campaign": {
                    "id": str(campaign.id),
                    "name": campaign.name,
                }
                if campaign
                else None,
                "experiment": {
                    "id": experiment_id,
                    "name": experiment_name or experiment_id,
                }
                if experiment_id
                else None,
                "creative_spec": creative_spec,
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
