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
from app.db.deps import get_session
from app.db.enums import AssetStatusEnum
from app.db.models import (
    Asset,
    Campaign,
    Client,
    ClientUserPreference,
    Experiment,
    MetaAd,
    MetaAdAccountConnection,
    MetaAdCreative,
    MetaAdSetSpec,
    MetaAssetUpload,
    MetaCampaign,
    MetaCreativeSpec,
    MetaPublishRun,
    MetaPublishRunItem,
    MetaWorkspaceAdConfig,
)
from app.db.repositories.assets import AssetsRepository
from app.db.repositories.campaigns import CampaignsRepository
from app.db.repositories.experiments import ExperimentsRepository
from app.db.repositories.meta_account_configs import MetaAccountConfigsRepository
from app.db.repositories.meta_ads import MetaAdsRepository
from app.schemas.meta_ads import (
    MetaAdAccountConnectionResponse,
    MetaAdAccountConnectionUpsertRequest,
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
    MetaConnectionWorkspaceUsageResponse,
    MetaWorkspaceAdConfigCreateRequest,
    MetaWorkspaceAdConfigResponse,
    MetaWorkspaceAdConfigUpdateRequest,
)
from app.services.image_metadata import (
    ImageMetadataSanitizationError,
    strip_and_validate_image_metadata,
)
from app.services.meta_account_configs import (
    MetaWorkspaceConfigError,
    ResolvedMetaWorkspaceConfig,
    connection_usage_rows,
    merge_meta_profile,
    meta_ads_client_for_connection,
    resolve_workspace_config,
    update_connection_credentials,
)
from app.services.media_storage import MediaStorage
from app.services.meta_ads import MetaAdsClient, MetaAdsError
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
from app.services.paid_ads_qa import RULESET_VERSION, refresh_meta_platform_profile_from_graph
from app.services.storefront_domains import normalize_absolute_origin, resolve_shop_hosted_origin

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
    clientId: str | None = None
    metaConfigId: str | None = None
    mode: Literal["plan_only", "apply"] = "plan_only"
    datePreset: str = "last_3d"
    includeRaw: bool = False
    cutRules: MetaCutRuleConfig | None = None
    eventMappings: _MetaEventMappingsRequest | None = None


def _resolve_ad_account_id(ad_account_id: Optional[str]) -> str:
    resolved = _clean_optional_text(ad_account_id)
    if not resolved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="adAccountId is required.",
        )
    return resolved


def _resolve_page_id(page_id: Optional[str]) -> str:
    resolved = _clean_optional_text(page_id)
    if not resolved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="pageId is required to create ad creatives.",
        )
    return resolved


def _resolve_instagram_actor_id(actor_id: Optional[str]) -> Optional[str]:
    return _clean_optional_text(actor_id)


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


def _meta_connection_usage_response(
    *,
    session: Session,
    connection_id: str,
    org_id: str,
) -> list[MetaConnectionWorkspaceUsageResponse]:
    return [
        MetaConnectionWorkspaceUsageResponse(
            clientId=str(client.id),
            clientName=client.name,
            configId=str(config.id),
            configName=config.name,
            isDefault=bool(config.is_default),
        )
        for config, client in connection_usage_rows(session=session, org_id=org_id, connection_id=connection_id)
    ]


def _meta_connection_response(
    *,
    session: Session,
    connection: MetaAdAccountConnection,
) -> MetaAdAccountConnectionResponse:
    return MetaAdAccountConnectionResponse(
        id=str(connection.id),
        orgId=str(connection.org_id),
        name=connection.name,
        adAccountId=connection.ad_account_id,
        adAccountName=connection.ad_account_name,
        businessManagerId=connection.business_manager_id,
        businessManagerName=connection.business_manager_name,
        graphApiVersion=connection.graph_api_version,
        graphApiBaseUrl=connection.graph_api_base_url,
        credentialType=connection.credential_type,
        hasCredentials=bool(_clean_optional_text(connection.credentials_encrypted)),
        tokenExpiresAt=connection.token_expires_at.isoformat() if connection.token_expires_at else None,
        status=connection.status,
        validationStatus=connection.validation_status,
        lastValidatedAt=connection.last_validated_at.isoformat() if connection.last_validated_at else None,
        lastValidationError=connection.last_validation_error,
        metadata=connection.metadata_json if isinstance(connection.metadata_json, dict) else {},
        usedByWorkspaces=_meta_connection_usage_response(
            session=session,
            connection_id=str(connection.id),
            org_id=str(connection.org_id),
        ),
        createdByUserId=connection.created_by_user_id,
        createdAt=connection.created_at.isoformat(),
        updatedAt=connection.updated_at.isoformat(),
    )


def _meta_workspace_config_response(
    *,
    session: Session,
    workspace_config: MetaWorkspaceAdConfig,
    connection: MetaAdAccountConnection | None = None,
) -> MetaWorkspaceAdConfigResponse:
    resolved_connection = connection
    if resolved_connection is None:
        repo = MetaAccountConfigsRepository(session)
        resolved_connection = repo.get_connection(
            org_id=str(workspace_config.org_id),
            connection_id=str(workspace_config.meta_connection_id),
        )
    if resolved_connection is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Meta workspace config is missing its backing ad account connection.",
        )
    return MetaWorkspaceAdConfigResponse(
        id=str(workspace_config.id),
        orgId=str(workspace_config.org_id),
        clientId=str(workspace_config.client_id),
        connectionId=str(workspace_config.meta_connection_id),
        name=workspace_config.name,
        isDefault=bool(workspace_config.is_default),
        status=workspace_config.status,
        pageId=workspace_config.page_id,
        pageName=workspace_config.page_name,
        instagramActorId=workspace_config.instagram_actor_id,
        pixelId=workspace_config.pixel_id,
        dataSetId=workspace_config.data_set_id,
        verifiedDomain=workspace_config.verified_domain,
        verifiedDomainStatus=workspace_config.verified_domain_status,
        trackingProvider=workspace_config.tracking_provider,
        trackingUrlParameters=workspace_config.tracking_url_parameters,
        attributionClickWindow=workspace_config.attribution_click_window,
        attributionViewWindow=workspace_config.attribution_view_window,
        viewThroughEnabled=workspace_config.view_through_enabled,
        validationStatus=workspace_config.validation_status,
        lastValidatedAt=workspace_config.last_validated_at.isoformat() if workspace_config.last_validated_at else None,
        lastValidationError=workspace_config.last_validation_error,
        metadata=workspace_config.metadata_json if isinstance(workspace_config.metadata_json, dict) else {},
        createdByUserId=workspace_config.created_by_user_id,
        createdAt=workspace_config.created_at.isoformat(),
        updatedAt=workspace_config.updated_at.isoformat(),
        connection=_meta_connection_response(session=session, connection=resolved_connection),
    )


def _resolve_meta_workspace_context_or_409(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    config_id: str | None = None,
) -> ResolvedMetaWorkspaceConfig:
    try:
        return resolve_workspace_config(
            session=session,
            org_id=org_id,
            client_id=client_id,
            config_id=config_id,
        )
    except MetaWorkspaceConfigError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


def _require_meta_page_id(
    *,
    workspace_config: MetaWorkspaceAdConfig,
    explicit_page_id: str | None = None,
) -> str:
    page_id = _clean_optional_text(explicit_page_id) or _clean_optional_text(workspace_config.page_id)
    if not page_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The selected Meta workspace config must define pageId before creating creatives.",
        )
    return page_id


def _resolved_ad_account_id_for_context(
    *,
    resolved: ResolvedMetaWorkspaceConfig,
    explicit_ad_account_id: str | None = None,
) -> str:
    context_ad_account_id = _clean_optional_text(resolved.connection.ad_account_id)
    requested_ad_account_id = _clean_optional_text(explicit_ad_account_id)
    if requested_ad_account_id and context_ad_account_id and requested_ad_account_id != context_ad_account_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Requested adAccountId does not match the selected Meta workspace config.",
        )
    return _resolve_ad_account_id(requested_ad_account_id or context_ad_account_id)


def _resolve_meta_workspace_context_for_asset(
    *,
    session: Session,
    auth: AuthContext,
    asset: Asset,
    config_id: str | None = None,
) -> ResolvedMetaWorkspaceConfig:
    return _resolve_meta_workspace_context_or_409(
        session=session,
        org_id=auth.org_id,
        client_id=str(asset.client_id),
        config_id=config_id,
    )


def _resolve_meta_workspace_context_for_campaign(
    *,
    session: Session,
    auth: AuthContext,
    campaign: Campaign,
    config_id: str | None = None,
) -> ResolvedMetaWorkspaceConfig:
    return _resolve_meta_workspace_context_or_409(
        session=session,
        org_id=auth.org_id,
        client_id=str(campaign.client_id),
        config_id=config_id,
    )


def _resolve_meta_workspace_context_for_client_or_config(
    *,
    session: Session,
    auth: AuthContext,
    client_id: str | None = None,
    config_id: str | None = None,
) -> ResolvedMetaWorkspaceConfig:
    resolved_client_id = _clean_optional_text(client_id)
    resolved_config_id = _clean_optional_text(config_id)
    if not resolved_client_id and not resolved_config_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="clientId or metaConfigId is required.",
        )
    if resolved_config_id and not resolved_client_id:
        workspace_config = MetaAccountConfigsRepository(session).get_workspace_config_by_id(
            org_id=auth.org_id,
            config_id=resolved_config_id,
        )
        if workspace_config is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meta workspace config not found")
        resolved_client_id = str(workspace_config.client_id)
    assert resolved_client_id is not None
    return _resolve_meta_workspace_context_or_409(
        session=session,
        org_id=auth.org_id,
        client_id=resolved_client_id,
        config_id=resolved_config_id,
    )


def _get_meta_client(
    *,
    resolved: ResolvedMetaWorkspaceConfig | None = None,
    connection: MetaAdAccountConnection | None = None,
) -> MetaAdsClient:
    target_connection = connection or (resolved.connection if resolved is not None else None)
    if target_connection is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A Meta connection context is required.",
        )
    try:
        return meta_ads_client_for_connection(target_connection)
    except MetaWorkspaceConfigError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


def _get_client_or_404(*, session: Session, org_id: str, client_id: str) -> Client:
    client = session.scalar(
        select(Client).where(
            Client.org_id == org_id,
            Client.id == client_id,
        )
    )
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


def _derive_meta_connection_validation_metadata(
    *,
    ad_account: dict[str, Any],
    ad_account_source: str,
    business: dict[str, Any] | None,
    business_source: str | None,
    pixel_records: list[dict[str, Any]],
    api_version: str,
) -> dict[str, Any]:
    funding_source_details = (
        ad_account.get("funding_source_details")
        if isinstance(ad_account.get("funding_source_details"), dict)
        else {}
    )
    return {
        "metaGraphValidation": {
            "apiVersion": api_version,
            "lastValidatedAt": datetime.now(timezone.utc).isoformat(),
            "validatedFields": [
                "adAccountId",
                "adAccountName",
                "businessManagerId",
                "businessManagerName",
                "paymentMethodStatus",
                "paymentMethodType",
            ],
            "adAccount": {
                "source": ad_account_source,
                "id": _clean_optional_text(ad_account.get("id")),
                "name": _clean_optional_text(ad_account.get("name")),
                "accountStatus": ad_account.get("account_status"),
                "disableReason": ad_account.get("disable_reason"),
            },
            "business": {
                "source": business_source,
                "id": _clean_optional_text((business or {}).get("id")),
                "name": _clean_optional_text((business or {}).get("name")),
                "verificationStatus": _clean_optional_text((business or {}).get("verification_status")),
            },
            "fundingSource": {
                "present": bool(funding_source_details.get("id")),
                "type": funding_source_details.get("type"),
                "displayString": _clean_optional_text(funding_source_details.get("display_string")),
            },
            "pixels": {
                "count": len(pixel_records),
                "ids": [
                    _clean_optional_text(pixel.get("id"))
                    for pixel in pixel_records
                    if _clean_optional_text(pixel.get("id"))
                ],
            },
        }
    }


def _persist_refreshed_workspace_profile(
    *,
    repo: MetaAccountConfigsRepository,
    connection: MetaAdAccountConnection,
    workspace_config: MetaWorkspaceAdConfig,
    refreshed_profile: dict[str, Any],
) -> tuple[MetaAdAccountConnection, MetaWorkspaceAdConfig]:
    profile_metadata = refreshed_profile.get("metadata")
    workspace_metadata = dict(profile_metadata) if isinstance(profile_metadata, dict) else {}
    workspace_metadata["rulesetVersion"] = str(refreshed_profile.get("rulesetVersion") or RULESET_VERSION)
    connection_metadata = dict(connection.metadata_json) if isinstance(connection.metadata_json, dict) else {}
    connection_metadata.update(
        {
            "paymentMethodType": _clean_optional_text(refreshed_profile.get("paymentMethodType")),
            "paymentMethodStatus": _clean_optional_text(refreshed_profile.get("paymentMethodStatus")),
            "dataSetShopifyPartnerInstalled": refreshed_profile.get("dataSetShopifyPartnerInstalled"),
            "dataSetDataSharingLevel": _clean_optional_text(refreshed_profile.get("dataSetDataSharingLevel")),
            "dataSetAssignedToAdAccount": refreshed_profile.get("dataSetAssignedToAdAccount"),
        }
    )
    if isinstance(workspace_metadata.get("metaGraphValidation"), dict):
        connection_metadata["metaGraphValidation"] = workspace_metadata["metaGraphValidation"]

    updated_connection = repo.update_connection(
        connection,
        ad_account_id=_clean_optional_text(refreshed_profile.get("adAccountId")),
        ad_account_name=_clean_optional_text(refreshed_profile.get("adAccountName")),
        business_manager_id=_clean_optional_text(refreshed_profile.get("businessManagerId")),
        business_manager_name=_clean_optional_text(refreshed_profile.get("businessManagerName")),
        validation_status="valid",
        last_validated_at=datetime.now(timezone.utc),
        last_validation_error=None,
        metadata_json=connection_metadata,
    )
    updated_workspace_config = repo.update_workspace_config(
        workspace_config,
        page_id=_clean_optional_text(refreshed_profile.get("pageId")),
        page_name=_clean_optional_text(refreshed_profile.get("pageName")),
        instagram_actor_id=_clean_optional_text(refreshed_profile.get("instagramActorId")),
        pixel_id=_clean_optional_text(refreshed_profile.get("pixelId")),
        data_set_id=_clean_optional_text(refreshed_profile.get("dataSetId")),
        verified_domain=_clean_optional_text(refreshed_profile.get("verifiedDomain")),
        verified_domain_status=_clean_optional_text(refreshed_profile.get("verifiedDomainStatus")),
        tracking_provider=_clean_optional_text(refreshed_profile.get("trackingProvider")),
        tracking_url_parameters=_clean_optional_text(refreshed_profile.get("trackingUrlParameters")),
        attribution_click_window=_clean_optional_text(refreshed_profile.get("attributionClickWindow")),
        attribution_view_window=_clean_optional_text(refreshed_profile.get("attributionViewWindow")),
        view_through_enabled=refreshed_profile.get("viewThroughEnabled"),
        validation_status="valid",
        last_validated_at=datetime.now(timezone.utc),
        last_validation_error=None,
        metadata_json=workspace_metadata,
    )
    return updated_connection, updated_workspace_config


def _resolve_meta_remote_context(
    *,
    session: Session,
    auth: AuthContext,
    client_id: str | None,
    config_id: str | None,
    explicit_ad_account_id: str | None,
) -> tuple[ResolvedMetaWorkspaceConfig, str]:
    resolved = _resolve_meta_workspace_context_for_client_or_config(
        session=session,
        auth=auth,
        client_id=client_id,
        config_id=config_id,
    )
    ad_account_id = _resolved_ad_account_id_for_context(
        resolved=resolved,
        explicit_ad_account_id=explicit_ad_account_id,
    )
    return resolved, ad_account_id


def _selected_shop_storefront_origin(
    *,
    session: Session,
    auth: AuthContext,
    client_id: str,
) -> str | None:
    preference = session.scalar(
        select(ClientUserPreference).where(
            ClientUserPreference.org_id == auth.org_id,
            ClientUserPreference.client_id == client_id,
            ClientUserPreference.user_external_id == auth.user_id,
        )
    )
    selected = _clean_optional_text(
        getattr(preference, "selected_shop_storefront_domain", None) if preference is not None else None
    )
    return resolve_shop_hosted_origin(selected)


def _validated_publish_base_url(
    *,
    session: Session,
    auth: AuthContext,
    client_id: str,
    publish_base_url: str,
) -> str:
    normalized_publish_base_url = normalize_absolute_origin(publish_base_url)
    if normalized_publish_base_url is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="publishBaseUrl must be an absolute http(s) URL.",
        )

    expected_storefront_origin = _selected_shop_storefront_origin(
        session=session,
        auth=auth,
        client_id=client_id,
    )
    if expected_storefront_origin and normalized_publish_base_url != expected_storefront_origin:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "publishBaseUrl must match the selected storefront host for this client.",
                "publishBaseUrl": normalized_publish_base_url,
                "expectedPublishBaseUrl": expected_storefront_origin,
            },
        )

    return normalized_publish_base_url


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
        metaConfigId=str(run.meta_workspace_config_id) if run.meta_workspace_config_id else None,
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
) -> tuple[MetaPublishPlanValidationResponse, list[dict[str, Any]], ResolvedMetaWorkspaceConfig]:
    publish_base_url = _validated_publish_base_url(
        session=session,
        auth=auth,
        client_id=str(campaign.client_id),
        publish_base_url=payload.publishBaseUrl,
    )
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

    resolved_meta_config = _resolve_meta_workspace_context_for_campaign(
        session=session,
        auth=auth,
        campaign=campaign,
        config_id=_clean_optional_text(payload.metaConfigId),
    )
    ad_account_id = _clean_optional_text(resolved_meta_config.connection.ad_account_id)
    profile_page_id = _clean_optional_text(resolved_meta_config.workspace_config.page_id)
    if not ad_account_id:
        blockers.append("The selected Meta workspace config is missing adAccountId.")

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
                publish_base_url=publish_base_url,
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
        publishBaseUrl=publish_base_url,
        publishDomain=next(iter(publish_domains)) if len(publish_domains) == 1 else None,
        blockers=blockers,
        items=validation_items,
    )
    return validation_response, resolved_items, resolved_meta_config


def _upload_meta_asset_internal(
    *,
    asset_id: str,
    payload: MetaAssetUploadRequest,
    auth: AuthContext,
    session: Session,
    resolved_meta_config: ResolvedMetaWorkspaceConfig | None = None,
):
    repo = MetaAdsRepository(session)
    assets_repo = AssetsRepository(session)
    asset = assets_repo.get(org_id=auth.org_id, asset_id=asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    if asset.file_status != "ready" or not asset.storage_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Asset file is not ready for upload.",
        )

    resolved = resolved_meta_config or _resolve_meta_workspace_context_for_asset(
        session=session,
        auth=auth,
        asset=asset,
        config_id=_clean_optional_text(payload.metaConfigId),
    )
    ad_account_id = _resolved_ad_account_id_for_context(
        resolved=resolved,
        explicit_ad_account_id=payload.adAccountId,
    )
    workspace_config_id = str(resolved.workspace_config.id)

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

    client = _get_meta_client(resolved=resolved)
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
                meta_workspace_config_id=workspace_config_id,
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
            meta_workspace_config_id=workspace_config_id,
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


def _create_meta_creative_internal(
    *,
    payload: MetaCreativeCreateRequest,
    auth: AuthContext,
    session: Session,
    resolved_meta_config: ResolvedMetaWorkspaceConfig | None = None,
):
    repo = MetaAdsRepository(session)
    assets_repo = AssetsRepository(session)
    asset = assets_repo.get(org_id=auth.org_id, asset_id=payload.assetId)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    resolved = resolved_meta_config or _resolve_meta_workspace_context_for_asset(
        session=session,
        auth=auth,
        asset=asset,
        config_id=_clean_optional_text(payload.metaConfigId),
    )
    ad_account_id = _resolved_ad_account_id_for_context(
        resolved=resolved,
        explicit_ad_account_id=payload.adAccountId,
    )
    page_id = _require_meta_page_id(
        workspace_config=resolved.workspace_config,
        explicit_page_id=payload.pageId,
    )
    instagram_actor_id = _resolve_instagram_actor_id(payload.instagramActorId) or _clean_optional_text(
        resolved.workspace_config.instagram_actor_id
    )

    existing = repo.get_creative_by_request(
        org_id=auth.org_id, ad_account_id=ad_account_id, request_id=payload.requestId
    )
    if existing:
        return jsonable_encoder(existing)

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

    client = _get_meta_client(resolved=resolved)
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
        meta_workspace_config_id=str(resolved.workspace_config.id),
        ad_account_id=ad_account_id,
        request_id=payload.requestId,
        meta_creative_id=creative_id,
        name=payload.name,
        status=response.get("status"),
        object_story_spec=object_story_spec,
        metadata_json=response,
    )
    return jsonable_encoder(record)


def _create_meta_campaign_internal(
    *,
    payload: MetaCampaignCreateRequest,
    auth: AuthContext,
    session: Session,
    resolved_meta_config: ResolvedMetaWorkspaceConfig | None = None,
):
    repo = MetaAdsRepository(session)
    campaign_id: Optional[str] = None
    resolved = resolved_meta_config
    if payload.campaignId:
        campaigns_repo = CampaignsRepository(session)
        campaign = campaigns_repo.get(org_id=auth.org_id, campaign_id=payload.campaignId)
        if not campaign:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
        campaign_id = str(campaign.id)
        if resolved is None:
            resolved = _resolve_meta_workspace_context_for_campaign(
                session=session,
                auth=auth,
                campaign=campaign,
                config_id=_clean_optional_text(payload.metaConfigId),
            )
    if resolved is None:
        config_id = _clean_optional_text(payload.metaConfigId)
        if not config_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="metaConfigId is required when creating a Meta campaign without an internal campaignId.",
            )
        repo_configs = MetaAccountConfigsRepository(session)
        workspace_config = repo_configs.get_workspace_config_by_id(org_id=auth.org_id, config_id=config_id)
        if not workspace_config:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meta workspace config not found")
        resolved = _resolve_meta_workspace_context_or_409(
            session=session,
            org_id=auth.org_id,
            client_id=str(workspace_config.client_id),
            config_id=config_id,
        )

    ad_account_id = _resolved_ad_account_id_for_context(
        resolved=resolved,
        explicit_ad_account_id=payload.adAccountId,
    )
    existing = repo.get_campaign_by_request(
        org_id=auth.org_id, ad_account_id=ad_account_id, request_id=payload.requestId
    )
    if existing:
        return jsonable_encoder(existing)

    request_payload: dict[str, Any] = {
        "name": payload.name,
        "objective": payload.objective,
        "status": payload.status,
    }
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

    client = _get_meta_client(resolved=resolved)
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
        meta_workspace_config_id=str(resolved.workspace_config.id),
        ad_account_id=ad_account_id,
        request_id=payload.requestId,
        meta_campaign_id=meta_campaign_id,
        name=payload.name,
        objective=payload.objective,
        status=payload.status,
        metadata_json=response,
    )
    return jsonable_encoder(record)


def _create_meta_adset_internal(
    *,
    payload: MetaAdSetCreateRequest,
    auth: AuthContext,
    session: Session,
    resolved_meta_config: ResolvedMetaWorkspaceConfig | None = None,
):
    repo = MetaAdsRepository(session)
    resolved = resolved_meta_config
    if resolved is None:
        config_id = _clean_optional_text(payload.metaConfigId)
        if not config_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="metaConfigId is required when creating Meta ad sets directly.",
            )
        repo_configs = MetaAccountConfigsRepository(session)
        workspace_config = repo_configs.get_workspace_config_by_id(org_id=auth.org_id, config_id=config_id)
        if not workspace_config:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meta workspace config not found")
        resolved = _resolve_meta_workspace_context_or_409(
            session=session,
            org_id=auth.org_id,
            client_id=str(workspace_config.client_id),
            config_id=config_id,
        )

    ad_account_id = _resolved_ad_account_id_for_context(
        resolved=resolved,
        explicit_ad_account_id=payload.adAccountId,
    )
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

    client = _get_meta_client(resolved=resolved)
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
        meta_workspace_config_id=str(resolved.workspace_config.id),
        ad_account_id=ad_account_id,
        request_id=payload.requestId,
        meta_campaign_id=payload.campaignId,
        meta_adset_id=meta_adset_id,
        name=payload.name,
        status=payload.status,
        metadata_json=response,
    )
    return jsonable_encoder(record)


def _create_meta_ad_internal(
    *,
    payload: MetaAdCreateRequest,
    auth: AuthContext,
    session: Session,
    resolved_meta_config: ResolvedMetaWorkspaceConfig | None = None,
):
    repo = MetaAdsRepository(session)
    resolved = resolved_meta_config
    if resolved is None:
        config_id = _clean_optional_text(payload.metaConfigId)
        if not config_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="metaConfigId is required when creating Meta ads directly.",
            )
        repo_configs = MetaAccountConfigsRepository(session)
        workspace_config = repo_configs.get_workspace_config_by_id(org_id=auth.org_id, config_id=config_id)
        if not workspace_config:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meta workspace config not found")
        resolved = _resolve_meta_workspace_context_or_409(
            session=session,
            org_id=auth.org_id,
            client_id=str(workspace_config.client_id),
            config_id=config_id,
        )

    ad_account_id = _resolved_ad_account_id_for_context(
        resolved=resolved,
        explicit_ad_account_id=payload.adAccountId,
    )
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

    client = _get_meta_client(resolved=resolved)
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
        meta_workspace_config_id=str(resolved.workspace_config.id),
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


@router.post("/assets/{asset_id}/upload", status_code=status.HTTP_201_CREATED)
def upload_meta_asset(
    asset_id: str,
    payload: MetaAssetUploadRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return _upload_meta_asset_internal(
        asset_id=asset_id,
        payload=payload,
        auth=auth,
        session=session,
    )


@router.get("/connections", response_model=list[MetaAdAccountConnectionResponse])
def list_meta_connections(
    includeArchived: bool = False,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = MetaAccountConfigsRepository(session)
    return [
        _meta_connection_response(session=session, connection=connection)
        for connection in repo.list_connections(org_id=auth.org_id, include_archived=includeArchived)
    ]


@router.post("/connections", response_model=MetaAdAccountConnectionResponse, status_code=status.HTTP_201_CREATED)
def create_meta_connection(
    payload: MetaAdAccountConnectionUpsertRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    access_token = _clean_optional_text(payload.accessToken)
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="accessToken is required when creating a Meta ad account connection.",
        )

    repo = MetaAccountConfigsRepository(session)
    ad_account_id = _clean_optional_text(payload.adAccountId)
    if ad_account_id:
        existing = repo.get_connection_by_ad_account_id(org_id=auth.org_id, ad_account_id=ad_account_id)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A Meta ad account connection already exists for this adAccountId.",
            )

    connection = repo.create_connection(
        org_id=auth.org_id,
        name=payload.name.strip(),
        ad_account_id=ad_account_id,
        ad_account_name=_clean_optional_text(payload.adAccountName),
        business_manager_id=_clean_optional_text(payload.businessManagerId),
        business_manager_name=_clean_optional_text(payload.businessManagerName),
        graph_api_version=payload.graphApiVersion.strip(),
        graph_api_base_url=payload.graphApiBaseUrl.strip(),
        credential_type="access_token",
        credentials_encrypted=None,
        credentials_last_updated_at=None,
        token_expires_at=payload.tokenExpiresAt,
        status=payload.status,
        validation_status="pending",
        last_validated_at=None,
        last_validation_error=None,
        metadata_json=payload.metadata or {},
        created_by_user_id=auth.user_id,
    )
    connection = update_connection_credentials(
        repo=repo,
        connection=connection,
        access_token=access_token,
        token_expires_at=payload.tokenExpiresAt,
    )
    return _meta_connection_response(session=session, connection=connection)


@router.get("/connections/{connection_id}", response_model=MetaAdAccountConnectionResponse)
def get_meta_connection(
    connection_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = MetaAccountConfigsRepository(session)
    connection = repo.get_connection(org_id=auth.org_id, connection_id=connection_id)
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meta ad account connection not found")
    return _meta_connection_response(session=session, connection=connection)


@router.patch("/connections/{connection_id}", response_model=MetaAdAccountConnectionResponse)
def update_meta_connection(
    connection_id: str,
    payload: MetaAdAccountConnectionUpsertRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = MetaAccountConfigsRepository(session)
    connection = repo.get_connection(org_id=auth.org_id, connection_id=connection_id)
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meta ad account connection not found")

    ad_account_id = _clean_optional_text(payload.adAccountId)
    if ad_account_id and ad_account_id != _clean_optional_text(connection.ad_account_id):
        existing = repo.get_connection_by_ad_account_id(org_id=auth.org_id, ad_account_id=ad_account_id)
        if existing is not None and str(existing.id) != str(connection.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A Meta ad account connection already exists for this adAccountId.",
            )

    connection = repo.update_connection(
        connection,
        name=payload.name.strip(),
        ad_account_id=ad_account_id,
        ad_account_name=_clean_optional_text(payload.adAccountName),
        business_manager_id=_clean_optional_text(payload.businessManagerId),
        business_manager_name=_clean_optional_text(payload.businessManagerName),
        graph_api_version=payload.graphApiVersion.strip(),
        graph_api_base_url=payload.graphApiBaseUrl.strip(),
        status=payload.status,
        metadata_json=payload.metadata or {},
        token_expires_at=payload.tokenExpiresAt,
    )
    access_token = _clean_optional_text(payload.accessToken)
    if access_token:
        connection = update_connection_credentials(
            repo=repo,
            connection=connection,
            access_token=access_token,
            token_expires_at=payload.tokenExpiresAt,
        )
    return _meta_connection_response(session=session, connection=connection)


@router.post("/connections/{connection_id}/validate", response_model=MetaAdAccountConnectionResponse)
def validate_meta_connection(
    connection_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = MetaAccountConfigsRepository(session)
    connection = repo.get_connection(org_id=auth.org_id, connection_id=connection_id)
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meta ad account connection not found")

    def _single_ad_account(accounts: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
        if len(accounts) == 1:
            return accounts[0], "graph.me/adaccounts"
        if not accounts:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Meta Graph returned no accessible ad accounts. Configure adAccountId explicitly on the connection.",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Meta Graph returned multiple accessible ad accounts. Configure adAccountId explicitly on the connection.",
        )

    try:
        client = _get_meta_client(connection=connection)
        ad_account_id = _clean_optional_text(connection.ad_account_id)
        if ad_account_id:
            ad_account = client.get_ad_account(
                ad_account_id=ad_account_id,
                fields="id,name,account_status,disable_reason,business,funding_source_details",
            )
            ad_account_source = "connection.adAccountId"
        else:
            ad_accounts = client.list_user_adaccounts(
                fields="id,name,account_status,disable_reason,business,funding_source_details",
                limit=10,
            ).get("data") or []
            ad_account, ad_account_source = _single_ad_account(ad_accounts)

        business_id = _clean_optional_text(
            (ad_account.get("business") or {}).get("id") if isinstance(ad_account.get("business"), dict) else None
        )
        business = (
            client.get_object(object_id=business_id, fields="id,name,verification_status") if business_id else None
        )
        pixel_records = client.list_ad_pixels(
            ad_account_id=str(ad_account.get("id") or ""),
            fields="id,name,creation_time",
            limit=25,
        ).get("data") or []

        funding_source_details = (
            ad_account.get("funding_source_details")
            if isinstance(ad_account.get("funding_source_details"), dict)
            else {}
        )
        payment_type = None
        display_string = _clean_optional_text(funding_source_details.get("display_string"))
        normalized_display = display_string.lower() if display_string else ""
        if "paypal" in normalized_display:
            payment_type = "paypal"
        elif any(
            brand in normalized_display for brand in ("visa", "mastercard", "american express", "amex", "discover")
        ):
            payment_type = "credit_card"
        elif funding_source_details.get("type") == 1:
            payment_type = "credit_card"
        elif display_string:
            payment_type = "other"

        metadata = dict(connection.metadata_json) if isinstance(connection.metadata_json, dict) else {}
        metadata.update(
            {
                "paymentMethodType": payment_type,
                "paymentMethodStatus": "active" if funding_source_details.get("id") else None,
                **_derive_meta_connection_validation_metadata(
                    ad_account=ad_account,
                    ad_account_source=ad_account_source,
                    business=business,
                    business_source="ad_account.business" if business_id else None,
                    pixel_records=pixel_records,
                    api_version=connection.graph_api_version,
                ),
            }
        )
        connection = repo.update_connection(
            connection,
            ad_account_id=_clean_optional_text(ad_account.get("id")),
            ad_account_name=_clean_optional_text(ad_account.get("name")),
            business_manager_id=_clean_optional_text((business or {}).get("id")),
            business_manager_name=_clean_optional_text((business or {}).get("name")),
            validation_status="valid",
            last_validated_at=datetime.now(timezone.utc),
            last_validation_error=None,
            metadata_json=metadata,
        )
    except HTTPException as exc:
        repo.update_connection(
            connection,
            validation_status="invalid",
            last_validated_at=datetime.now(timezone.utc),
            last_validation_error=str(exc.detail),
        )
        raise
    except MetaAdsError as exc:
        repo.update_connection(
            connection,
            validation_status="invalid",
            last_validated_at=datetime.now(timezone.utc),
            last_validation_error=str(exc),
        )
        _raise_meta_error(exc)

    return _meta_connection_response(session=session, connection=connection)


@router.get("/clients/{client_id}/configs", response_model=list[MetaWorkspaceAdConfigResponse])
def list_workspace_meta_configs(
    client_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _get_client_or_404(session=session, org_id=auth.org_id, client_id=client_id)
    repo = MetaAccountConfigsRepository(session)
    configs = repo.list_workspace_configs(org_id=auth.org_id, client_id=client_id)
    return [_meta_workspace_config_response(session=session, workspace_config=config) for config in configs]


@router.post("/clients/{client_id}/configs", response_model=MetaWorkspaceAdConfigResponse, status_code=status.HTTP_201_CREATED)
def create_workspace_meta_config(
    client_id: str,
    payload: MetaWorkspaceAdConfigCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _get_client_or_404(session=session, org_id=auth.org_id, client_id=client_id)
    repo = MetaAccountConfigsRepository(session)
    connection = repo.get_connection(org_id=auth.org_id, connection_id=payload.connectionId)
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meta ad account connection not found")

    existing = repo.list_workspace_configs(org_id=auth.org_id, client_id=client_id, include_archived=True)
    if any(str(config.meta_connection_id) == str(connection.id) for config in existing):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This Meta ad account is already attached to the workspace.",
        )
    if payload.isDefault:
        repo.clear_default_workspace_config(org_id=auth.org_id, client_id=client_id)

    config = repo.create_workspace_config(
        org_id=auth.org_id,
        client_id=client_id,
        meta_connection_id=str(connection.id),
        name=payload.name.strip(),
        is_default=payload.isDefault,
        status=payload.status,
        page_id=_clean_optional_text(payload.pageId),
        page_name=_clean_optional_text(payload.pageName),
        instagram_actor_id=_clean_optional_text(payload.instagramActorId),
        pixel_id=_clean_optional_text(payload.pixelId),
        data_set_id=_clean_optional_text(payload.dataSetId),
        verified_domain=_clean_optional_text(payload.verifiedDomain),
        verified_domain_status=_clean_optional_text(payload.verifiedDomainStatus),
        tracking_provider=_clean_optional_text(payload.trackingProvider),
        tracking_url_parameters=_clean_optional_text(payload.trackingUrlParameters),
        attribution_click_window=_clean_optional_text(payload.attributionClickWindow),
        attribution_view_window=_clean_optional_text(payload.attributionViewWindow),
        view_through_enabled=payload.viewThroughEnabled,
        validation_status="pending",
        last_validated_at=None,
        last_validation_error=None,
        metadata_json=payload.metadata or {},
        created_by_user_id=auth.user_id,
    )
    return _meta_workspace_config_response(session=session, workspace_config=config, connection=connection)


@router.get("/clients/{client_id}/configs/{config_id}", response_model=MetaWorkspaceAdConfigResponse)
def get_workspace_meta_config(
    client_id: str,
    config_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _get_client_or_404(session=session, org_id=auth.org_id, client_id=client_id)
    repo = MetaAccountConfigsRepository(session)
    config = repo.get_workspace_config(org_id=auth.org_id, client_id=client_id, config_id=config_id)
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meta workspace config not found")
    return _meta_workspace_config_response(session=session, workspace_config=config)


@router.patch("/clients/{client_id}/configs/{config_id}", response_model=MetaWorkspaceAdConfigResponse)
def update_workspace_meta_config(
    client_id: str,
    config_id: str,
    payload: MetaWorkspaceAdConfigUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _get_client_or_404(session=session, org_id=auth.org_id, client_id=client_id)
    repo = MetaAccountConfigsRepository(session)
    config = repo.get_workspace_config(org_id=auth.org_id, client_id=client_id, config_id=config_id)
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meta workspace config not found")

    updates = payload.model_dump(exclude_unset=True)
    if "isDefault" in updates and updates["isDefault"] is True:
        repo.clear_default_workspace_config(org_id=auth.org_id, client_id=client_id)

    config = repo.update_workspace_config(
        config,
        name=_clean_optional_text(updates["name"]) if "name" in updates else config.name,
        is_default=updates.get("isDefault", config.is_default),
        page_id=_clean_optional_text(updates["pageId"]) if "pageId" in updates else config.page_id,
        page_name=_clean_optional_text(updates["pageName"]) if "pageName" in updates else config.page_name,
        instagram_actor_id=(
            _clean_optional_text(updates["instagramActorId"])
            if "instagramActorId" in updates
            else config.instagram_actor_id
        ),
        pixel_id=_clean_optional_text(updates["pixelId"]) if "pixelId" in updates else config.pixel_id,
        data_set_id=_clean_optional_text(updates["dataSetId"]) if "dataSetId" in updates else config.data_set_id,
        verified_domain=(
            _clean_optional_text(updates["verifiedDomain"]) if "verifiedDomain" in updates else config.verified_domain
        ),
        verified_domain_status=(
            _clean_optional_text(updates["verifiedDomainStatus"])
            if "verifiedDomainStatus" in updates
            else config.verified_domain_status
        ),
        tracking_provider=(
            _clean_optional_text(updates["trackingProvider"])
            if "trackingProvider" in updates
            else config.tracking_provider
        ),
        tracking_url_parameters=(
            _clean_optional_text(updates["trackingUrlParameters"])
            if "trackingUrlParameters" in updates
            else config.tracking_url_parameters
        ),
        attribution_click_window=(
            _clean_optional_text(updates["attributionClickWindow"])
            if "attributionClickWindow" in updates
            else config.attribution_click_window
        ),
        attribution_view_window=(
            _clean_optional_text(updates["attributionViewWindow"])
            if "attributionViewWindow" in updates
            else config.attribution_view_window
        ),
        view_through_enabled=updates.get("viewThroughEnabled", config.view_through_enabled),
        status=updates.get("status", config.status),
        metadata_json=updates["metadata"] if "metadata" in updates and updates["metadata"] is not None else config.metadata_json,
    )
    return _meta_workspace_config_response(session=session, workspace_config=config)


@router.post("/clients/{client_id}/configs/{config_id}/select", response_model=MetaWorkspaceAdConfigResponse)
def select_workspace_meta_config(
    client_id: str,
    config_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _get_client_or_404(session=session, org_id=auth.org_id, client_id=client_id)
    repo = MetaAccountConfigsRepository(session)
    config = repo.get_workspace_config(org_id=auth.org_id, client_id=client_id, config_id=config_id)
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meta workspace config not found")
    repo.clear_default_workspace_config(org_id=auth.org_id, client_id=client_id)
    config = repo.update_workspace_config(config, is_default=True)
    return _meta_workspace_config_response(session=session, workspace_config=config)


@router.post("/clients/{client_id}/configs/{config_id}/validate", response_model=MetaWorkspaceAdConfigResponse)
def validate_workspace_meta_config(
    client_id: str,
    config_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _get_client_or_404(session=session, org_id=auth.org_id, client_id=client_id)
    repo = MetaAccountConfigsRepository(session)
    config = repo.get_workspace_config(org_id=auth.org_id, client_id=client_id, config_id=config_id)
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meta workspace config not found")
    connection = repo.get_connection(org_id=auth.org_id, connection_id=str(config.meta_connection_id))
    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Meta workspace config is missing its ad account connection.",
        )

    try:
        refreshed = refresh_meta_platform_profile_from_graph(
            profile=merge_meta_profile(connection=connection, workspace_config=config),
            ruleset_version=str(
                (
                    config.metadata_json.get("rulesetVersion")
                    if isinstance(config.metadata_json, dict)
                    else None
                )
                or RULESET_VERSION
            ),
            client=_get_meta_client(connection=connection),
            api_version=connection.graph_api_version,
        )
        connection, config = _persist_refreshed_workspace_profile(
            repo=repo,
            connection=connection,
            workspace_config=config,
            refreshed_profile=refreshed,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        config = repo.update_workspace_config(
            config,
            validation_status="invalid",
            last_validated_at=datetime.now(timezone.utc),
            last_validation_error=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return _meta_workspace_config_response(session=session, workspace_config=config, connection=connection)


@router.get("/clients/{client_id}/active-config", response_model=MetaWorkspaceAdConfigResponse)
def get_workspace_active_meta_config(
    client_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _get_client_or_404(session=session, org_id=auth.org_id, client_id=client_id)
    resolved = _resolve_meta_workspace_context_for_client_or_config(
        session=session,
        auth=auth,
        client_id=client_id,
    )
    return _meta_workspace_config_response(
        session=session,
        workspace_config=resolved.workspace_config,
        connection=resolved.connection,
    )


@router.post("/creatives", status_code=status.HTTP_201_CREATED)
def create_meta_creative(
    payload: MetaCreativeCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return _create_meta_creative_internal(payload=payload, auth=auth, session=session)


@router.post("/campaigns", status_code=status.HTTP_201_CREATED)
def create_meta_campaign(
    payload: MetaCampaignCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return _create_meta_campaign_internal(payload=payload, auth=auth, session=session)


@router.post("/adsets", status_code=status.HTTP_201_CREATED)
def create_meta_adset(
    payload: MetaAdSetCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return _create_meta_adset_internal(payload=payload, auth=auth, session=session)


@router.post("/ads", status_code=status.HTTP_201_CREATED)
def create_meta_ad(
    payload: MetaAdCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return _create_meta_ad_internal(payload=payload, auth=auth, session=session)


@router.post("/creatives/{creative_id}/previews")
def preview_meta_creative(
    creative_id: str,
    payload: MetaCreativePreviewRequest,
    auth: AuthContext = Depends(get_current_user),
    clientId: str | None = None,
    metaConfigId: str | None = None,
    session: Session = Depends(get_session),
):
    resolved = _resolve_meta_workspace_context_for_client_or_config(
        session=session,
        auth=auth,
        client_id=clientId,
        config_id=metaConfigId,
    )
    client = _get_meta_client(resolved=resolved)
    try:
        response = client.get_creative_previews(
            creative_id=creative_id, ad_format=payload.adFormat, render_type=payload.renderType
        )
    except MetaAdsError as exc:
        _raise_meta_error(exc)
    return response


@router.get("/config", response_model=MetaWorkspaceAdConfigResponse)
def get_meta_config(
    clientId: str | None = None,
    metaConfigId: str | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    resolved = _resolve_meta_workspace_context_for_client_or_config(
        session=session,
        auth=auth,
        client_id=clientId,
        config_id=metaConfigId,
    )
    return _meta_workspace_config_response(
        session=session,
        workspace_config=resolved.workspace_config,
        connection=resolved.connection,
    )


@router.post("/management/plan")
def plan_meta_management(
    payload: MetaManagementPlanRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Plan-only media buying evaluation for a Meta campaign.

    This endpoint does not mutate Meta objects; it only returns the computed dashboard
    metrics and the actions that would be taken under the current ruleset.
    """
    resolved = _resolve_meta_workspace_context_for_client_or_config(
        session=session,
        auth=auth,
        client_id=payload.clientId,
        config_id=payload.metaConfigId,
    )
    ad_account_id = _resolved_ad_account_id_for_context(resolved=resolved)
    cut_rules = payload.cutRules or MetaCutRuleConfig()
    mappings_req = payload.eventMappings or _MetaEventMappingsRequest()
    event_mappings = MetaEventMappings(
        content_view_action_type=mappings_req.contentViewActionType,
        add_to_cart_action_type=mappings_req.addToCartActionType,
        purchase_action_type=mappings_req.purchaseActionType,
        purchase_value_action_type=mappings_req.purchaseValueActionType,
    )
    plan = build_management_plan(
        client=_get_meta_client(resolved=resolved),
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

    validation_response, _resolved_items, _resolved_meta_config = _validate_publish_plan(
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

    validation_response, resolved_items, resolved_meta_config = _validate_publish_plan(
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

    ad_account_id = _resolved_ad_account_id_for_context(resolved=resolved_meta_config)
    page_id = _require_meta_page_id(workspace_config=resolved_meta_config.workspace_config)

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
        publish_base_url=validation_response.publishBaseUrl,
        publish_domain=validation_response.publishDomain,
        meta_workspace_config_id=str(resolved_meta_config.workspace_config.id),
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
        created_campaign = _create_meta_campaign_internal(
            payload=MetaCampaignCreateRequest(
                requestId=f"meta-publish-run:{run.id}:campaign",
                adAccountId=ad_account_id,
                metaConfigId=str(resolved_meta_config.workspace_config.id),
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
            resolved_meta_config=resolved_meta_config,
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
            created_adset = _create_meta_adset_internal(
                payload=MetaAdSetCreateRequest(
                    requestId=f"meta-publish-run:{run.id}:adset:{adset_spec_id}",
                    adAccountId=ad_account_id,
                    metaConfigId=str(resolved_meta_config.workspace_config.id),
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
                resolved_meta_config=resolved_meta_config,
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

            uploaded_asset = _upload_meta_asset_internal(
                asset_id=str(asset.id),
                payload=MetaAssetUploadRequest(
                    requestId=f"meta-publish-run:{run.id}:asset:{asset.id}:upload",
                    adAccountId=ad_account_id,
                    metaConfigId=str(resolved_meta_config.workspace_config.id),
                ),
                auth=auth,
                session=session,
                resolved_meta_config=resolved_meta_config,
            )
            created_creative = _create_meta_creative_internal(
                payload=MetaCreativeCreateRequest(
                    requestId=f"meta-publish-run:{run.id}:asset:{asset.id}:creative",
                    adAccountId=ad_account_id,
                    metaConfigId=str(resolved_meta_config.workspace_config.id),
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
                resolved_meta_config=resolved_meta_config,
            )
            meta_creative_id = _clean_optional_text(created_creative.get("meta_creative_id"))
            if not meta_creative_id:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Meta publish run did not receive a meta_creative_id for asset {asset.id}.",
                )

            created_ad = _create_meta_ad_internal(
                payload=MetaAdCreateRequest(
                    requestId=f"meta-publish-run:{run.id}:asset:{asset.id}:ad",
                    adAccountId=ad_account_id,
                    metaConfigId=str(resolved_meta_config.workspace_config.id),
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
                resolved_meta_config=resolved_meta_config,
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
    metaConfigId: str | None = None,
    adAccountId: str | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list:
    if (clientId and not productId) or (productId and not clientId):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="clientId and productId are required together.",
        )
    ad_account_id = _clean_optional_text(adAccountId)
    if clientId or metaConfigId:
        resolved, ad_account_id = _resolve_meta_remote_context(
            session=session,
            auth=auth,
            client_id=clientId,
            config_id=metaConfigId,
            explicit_ad_account_id=adAccountId,
        )
        if clientId and str(resolved.workspace_config.client_id) != clientId:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="metaConfigId does not belong to the requested clientId.",
            )
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
    experiment_keys = {str(asset.experiment_id) for asset in assets if asset.experiment_id}
    internal_experiment_ids = set(experiment_keys)

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
    experiment_keys.update(experiment_keys_from_specs)
    internal_experiment_ids.update(str(spec.experiment_id) for spec in creative_specs if spec.experiment_id)

    adset_specs = []
    if campaignId:
        adset_specs = session.scalars(
            select(MetaAdSetSpec).where(
                MetaAdSetSpec.org_id == auth.org_id,
                MetaAdSetSpec.campaign_id == campaignId,
            )
        ).all()
    elif campaign_ids:
        adset_specs = session.scalars(
            select(MetaAdSetSpec).where(
                MetaAdSetSpec.org_id == auth.org_id,
                MetaAdSetSpec.campaign_id.in_(list(campaign_ids)),
            )
        ).all()
    elif internal_experiment_ids:
        adset_specs = session.scalars(
            select(MetaAdSetSpec).where(
                MetaAdSetSpec.org_id == auth.org_id,
                MetaAdSetSpec.experiment_id.in_(list(internal_experiment_ids)),
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

    internal_experiment_id_values: list[str] = []
    for experiment_id in internal_experiment_ids:
        try:
            internal_experiment_id_values.append(str(UUID(experiment_id)))
        except (TypeError, ValueError):
            continue

    experiments = []
    if internal_experiment_id_values:
        experiments = session.scalars(
            select(Experiment).where(
                Experiment.org_id == auth.org_id,
                Experiment.id.in_(internal_experiment_id_values),
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
    clientId: str | None = None,
    metaConfigId: str | None = None,
    adAccountId: str | None = None,
    fields: str | None = None,
    limit: int | None = None,
    after: str | None = None,
    fetchAll: bool | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    resolved, ad_account_id = _resolve_meta_remote_context(
        session=session,
        auth=auth,
        client_id=clientId,
        config_id=metaConfigId,
        explicit_ad_account_id=adAccountId,
    )
    client = _get_meta_client(resolved=resolved)
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
    clientId: str | None = None,
    metaConfigId: str | None = None,
    adAccountId: str | None = None,
    fields: str | None = None,
    limit: int | None = None,
    after: str | None = None,
    fetchAll: bool | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    resolved, ad_account_id = _resolve_meta_remote_context(
        session=session,
        auth=auth,
        client_id=clientId,
        config_id=metaConfigId,
        explicit_ad_account_id=adAccountId,
    )
    client = _get_meta_client(resolved=resolved)
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
    clientId: str | None = None,
    metaConfigId: str | None = None,
    adAccountId: str | None = None,
    fields: str | None = None,
    limit: int | None = None,
    after: str | None = None,
    fetchAll: bool | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    resolved, ad_account_id = _resolve_meta_remote_context(
        session=session,
        auth=auth,
        client_id=clientId,
        config_id=metaConfigId,
        explicit_ad_account_id=adAccountId,
    )
    client = _get_meta_client(resolved=resolved)
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
    clientId: str | None = None,
    metaConfigId: str | None = None,
    adAccountId: str | None = None,
    fields: str | None = None,
    limit: int | None = None,
    after: str | None = None,
    fetchAll: bool | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    resolved, ad_account_id = _resolve_meta_remote_context(
        session=session,
        auth=auth,
        client_id=clientId,
        config_id=metaConfigId,
        explicit_ad_account_id=adAccountId,
    )
    client = _get_meta_client(resolved=resolved)
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
    clientId: str | None = None,
    metaConfigId: str | None = None,
    adAccountId: str | None = None,
    fields: str | None = None,
    limit: int | None = None,
    after: str | None = None,
    fetchAll: bool | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    resolved, ad_account_id = _resolve_meta_remote_context(
        session=session,
        auth=auth,
        client_id=clientId,
        config_id=metaConfigId,
        explicit_ad_account_id=adAccountId,
    )
    client = _get_meta_client(resolved=resolved)
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
    clientId: str | None = None,
    metaConfigId: str | None = None,
    adAccountId: str | None = None,
    fields: str | None = None,
    limit: int | None = None,
    after: str | None = None,
    fetchAll: bool | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    resolved, ad_account_id = _resolve_meta_remote_context(
        session=session,
        auth=auth,
        client_id=clientId,
        config_id=metaConfigId,
        explicit_ad_account_id=adAccountId,
    )
    client = _get_meta_client(resolved=resolved)
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
