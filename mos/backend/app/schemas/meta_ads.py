from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from urllib.parse import urlparse

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


MetaPublishSelectionDecision = Literal["excluded"]


class MetaPublishSelectionMutationRequest(BaseModel):
    assetId: str
    decision: MetaPublishSelectionDecision | None = None

    @field_validator("assetId")
    @classmethod
    def _validate_asset_id(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("assetId must be a non-empty string.")
        return value.strip()


class CampaignMetaPublishSelectionsRequest(BaseModel):
    generationKey: str
    decisions: list[MetaPublishSelectionMutationRequest] = Field(default_factory=list)

    @field_validator("generationKey")
    @classmethod
    def _validate_generation_key(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("generationKey must be a non-empty string.")
        return value.strip()

    @field_validator("decisions")
    @classmethod
    def _validate_decisions(
        cls,
        value: list[MetaPublishSelectionMutationRequest],
    ) -> list[MetaPublishSelectionMutationRequest]:
        seen: set[str] = set()
        for decision in value:
            if decision.assetId in seen:
                raise ValueError(f"Duplicate assetId '{decision.assetId}' is not allowed.")
            seen.add(decision.assetId)
        return value


class MetaPublishSelectionResponse(BaseModel):
    id: str
    campaignId: str
    assetId: str
    generationKey: str
    decision: MetaPublishSelectionDecision
    decidedByUserId: str | None = None
    createdAt: str
    updatedAt: str


class MetaAdSetSpecUpdateRequest(BaseModel):
    name: str | None = None
    optimizationGoal: str | None = None
    billingEvent: str | None = None
    targeting: dict[str, Any] | None = None
    placements: dict[str, Any] | None = None
    dailyBudget: int | None = None
    lifetimeBudget: int | None = None
    bidAmount: int | None = None
    startTime: datetime | None = None
    endTime: datetime | None = None
    promotedObject: dict[str, Any] | None = None
    conversionDomain: str | None = None
    metadata: dict[str, Any] | None = None


class MetaPublishRunRequest(BaseModel):
    generationKey: str
    publishBaseUrl: str
    campaignName: str
    campaignObjective: str
    buyingType: str | None = None
    specialAdCategories: list[str] = Field(default_factory=list)

    @field_validator("generationKey")
    @classmethod
    def _validate_publish_generation_key(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("generationKey must be a non-empty string.")
        return value.strip()

    @field_validator("publishBaseUrl")
    @classmethod
    def _validate_publish_base_url(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("publishBaseUrl must be a non-empty string.")
        cleaned = value.strip().rstrip("/")
        parsed = urlparse(cleaned)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("publishBaseUrl must be an absolute http(s) URL.")
        return cleaned

    @field_validator("campaignName")
    @classmethod
    def _validate_campaign_name(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("campaignName must be a non-empty string.")
        return value.strip()

    @field_validator("campaignObjective")
    @classmethod
    def _validate_campaign_objective(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("campaignObjective must be a non-empty string.")
        return value.strip()

    @field_validator("buyingType")
    @classmethod
    def _validate_buying_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("buyingType must be a non-empty string when provided.")
        return value.strip()

    @field_validator("specialAdCategories")
    @classmethod
    def _validate_special_ad_categories(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for entry in value:
            if not isinstance(entry, str) or not entry.strip():
                continue
            normalized = entry.strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            cleaned.append(normalized)
        return cleaned


class MetaPublishPlanValidationItemResponse(BaseModel):
    assetId: str
    creativeSpecId: str | None = None
    adsetSpecId: str | None = None
    resolvedDestinationUrl: str | None = None
    status: Literal["ok", "blocked"]
    blockers: list[str] = Field(default_factory=list)


class MetaPublishPlanValidationResponse(BaseModel):
    campaignId: str
    generationKey: str
    ok: bool
    includedCount: int
    adsetCount: int
    publishBaseUrl: str
    publishDomain: str | None = None
    blockers: list[str] = Field(default_factory=list)
    items: list[MetaPublishPlanValidationItemResponse] = Field(default_factory=list)


class MetaPublishRunItemResponse(BaseModel):
    id: str
    assetId: str
    creativeSpecId: str | None = None
    adsetSpecId: str | None = None
    status: str
    resolvedDestinationUrl: str | None = None
    metaAssetUploadId: str | None = None
    metaCreativeId: str | None = None
    metaAdSetId: str | None = None
    metaAdId: str | None = None
    errorMessage: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    createdAt: str
    updatedAt: str


class MetaPublishRunResponse(BaseModel):
    id: str
    campaignId: str
    generationKey: str
    status: str
    campaignName: str
    campaignObjective: str
    buyingType: str | None = None
    specialAdCategories: list[str] = Field(default_factory=list)
    publishBaseUrl: str
    publishDomain: str | None = None
    adAccountId: str | None = None
    pageId: str | None = None
    metaCampaignId: str | None = None
    errorMessage: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    items: list[MetaPublishRunItemResponse] = Field(default_factory=list)
    createdByUserId: str | None = None
    createdAt: str
    updatedAt: str
    completedAt: str | None = None
