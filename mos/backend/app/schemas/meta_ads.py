from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class MetaAssetUploadRequest(BaseModel):
    requestId: str
    adAccountId: Optional[str] = None


class MetaCreativeCreateRequest(BaseModel):
    requestId: str
    adAccountId: Optional[str] = None
    assetId: str
    name: str
    pageId: Optional[str] = None
    instagramActorId: Optional[str] = None
    linkUrl: str
    message: Optional[str] = None
    headline: Optional[str] = None
    description: Optional[str] = None
    callToActionType: Optional[str] = None
    validateOnly: Optional[bool] = None


class MetaCampaignCreateRequest(BaseModel):
    requestId: str
    adAccountId: Optional[str] = None
    campaignId: Optional[str] = None
    name: str
    objective: str
    status: str
    # Meta requires this param even when empty.
    specialAdCategories: list[str] = Field(default_factory=list)
    buyingType: Optional[str] = None
    dailyBudget: Optional[int] = None
    lifetimeBudget: Optional[int] = None
    # Required by Meta when creating ABO campaigns without a campaign-level budget.
    # For Structure B (CBO), you should set a campaign budget instead.
    isAdsetBudgetSharingEnabled: Optional[bool] = None
    validateOnly: Optional[bool] = None


class MetaAdSetCreateRequest(BaseModel):
    requestId: str
    adAccountId: Optional[str] = None
    campaignId: str
    name: str
    status: str
    dailyBudget: Optional[int] = None
    lifetimeBudget: Optional[int] = None
    billingEvent: str
    optimizationGoal: str
    targeting: dict[str, Any]
    startTime: Optional[str] = None
    endTime: Optional[str] = None
    bidAmount: Optional[int] = None
    promotedObject: Optional[dict[str, Any]] = None
    validateOnly: Optional[bool] = None


class MetaAdCreateRequest(BaseModel):
    requestId: str
    adAccountId: Optional[str] = None
    adsetId: str
    creativeId: str
    name: str
    status: str
    trackingSpecs: Optional[list[dict[str, Any]]] = None
    conversionDomain: Optional[str] = None
    validateOnly: Optional[bool] = None


class MetaCreativePreviewRequest(BaseModel):
    adFormat: str
    renderType: Optional[str] = None


class MetaCreativeSpecCreateRequest(BaseModel):
    assetId: str
    campaignId: Optional[str] = None
    experimentId: Optional[str] = None
    name: Optional[str] = None
    primaryText: Optional[str] = None
    headline: Optional[str] = None
    description: Optional[str] = None
    callToActionType: Optional[str] = None
    destinationUrl: Optional[str] = None
    pageId: Optional[str] = None
    instagramActorId: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class MetaAdSetSpecCreateRequest(BaseModel):
    campaignId: Optional[str] = None
    experimentId: Optional[str] = None
    name: Optional[str] = None
    status: Optional[str] = None
    optimizationGoal: Optional[str] = None
    billingEvent: Optional[str] = None
    targeting: Optional[dict[str, Any]] = None
    placements: Optional[dict[str, Any]] = None
    dailyBudget: Optional[int] = None
    lifetimeBudget: Optional[int] = None
    bidAmount: Optional[int] = None
    startTime: Optional[datetime] = None
    endTime: Optional[datetime] = None
    promotedObject: Optional[dict[str, Any]] = None
    conversionDomain: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class CampaignMetaReviewSetupRequest(BaseModel):
    assetBriefIds: list[str] = Field(default_factory=list)
    generationBatchId: str | None = None

    @field_validator("assetBriefIds")
    @classmethod
    def _validate_asset_brief_ids(cls, value: list[str]) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("assetBriefIds must be a list.")
        cleaned: list[str] = []
        seen: set[str] = set()
        for entry in value:
            if not isinstance(entry, str) or not entry.strip():
                raise ValueError("assetBriefIds must contain non-empty strings.")
            normalized = entry.strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            cleaned.append(normalized)
        return cleaned

    @field_validator("generationBatchId")
    @classmethod
    def _validate_generation_batch_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("generationBatchId must be a non-empty string when provided.")
        return value.strip()
