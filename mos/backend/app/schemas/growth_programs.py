"""Schemas for content growth programs and TikTok carousel agent primitives."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _required(value: str, field_name: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError(f"{field_name} is required.")
    return cleaned


class ConversionSourceCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    provider: str
    name: str
    status: str = "draft"
    goal_events: list[str] = Field(
        default_factory=list, validation_alias="goalEvents", serialization_alias="goalEvents"
    )
    config: dict[str, Any] = Field(default_factory=dict)
    credentials_metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="credentialsMetadata",
        serialization_alias="credentialsMetadata",
    )

    @field_validator("provider", "name", "status")
    @classmethod
    def _validate_required(cls, value: str, info) -> str:
        return _required(value, info.field_name)


class ConversionSourceResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    provider: str
    name: str
    status: str
    goal_events: list[str] = Field(
        default_factory=list, validation_alias="goalEvents", serialization_alias="goalEvents"
    )
    config: dict[str, Any] = Field(default_factory=dict)
    credentials_metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="credentialsMetadata",
        serialization_alias="credentialsMetadata",
    )
    last_synced_at: datetime | None = Field(
        default=None, validation_alias="lastSyncedAt", serialization_alias="lastSyncedAt"
    )
    last_error: str | None = Field(
        default=None, validation_alias="lastError", serialization_alias="lastError"
    )
    created_at: datetime = Field(validation_alias="createdAt", serialization_alias="createdAt")
    updated_at: datetime = Field(validation_alias="updatedAt", serialization_alias="updatedAt")


class ContentGrowthProgramCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    product_id: str | None = Field(default=None, validation_alias="productId", serialization_alias="productId")
    campaign_id: str | None = Field(
        default=None, validation_alias="campaignId", serialization_alias="campaignId"
    )
    conversion_source_id: str | None = Field(
        default=None,
        validation_alias="conversionSourceId",
        serialization_alias="conversionSourceId",
    )
    name: str
    objective: str
    platform_key: str = Field(
        default="tiktok", validation_alias="platformKey", serialization_alias="platformKey"
    )
    format_key: str = Field(
        default="tiktok_carousel", validation_alias="formatKey", serialization_alias="formatKey"
    )
    authority_mode: str = Field(
        default="approval_required",
        validation_alias="authorityMode",
        serialization_alias="authorityMode",
    )
    status: str = "draft"
    settings: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", "objective", "platform_key", "format_key", "authority_mode", "status")
    @classmethod
    def _validate_required(cls, value: str, info) -> str:
        return _required(value, info.field_name)


class ContentGrowthProgramResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    product_id: str | None = Field(default=None, validation_alias="productId", serialization_alias="productId")
    campaign_id: str | None = Field(
        default=None, validation_alias="campaignId", serialization_alias="campaignId"
    )
    conversion_source_id: str | None = Field(
        default=None,
        validation_alias="conversionSourceId",
        serialization_alias="conversionSourceId",
    )
    name: str
    objective: str
    platform_key: str = Field(validation_alias="platformKey", serialization_alias="platformKey")
    format_key: str = Field(validation_alias="formatKey", serialization_alias="formatKey")
    authority_mode: str = Field(validation_alias="authorityMode", serialization_alias="authorityMode")
    status: str
    settings: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(validation_alias="createdAt", serialization_alias="createdAt")
    updated_at: datetime = Field(validation_alias="updatedAt", serialization_alias="updatedAt")


class ContentExperimentCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str
    hypothesis: str
    hook_family: str | None = Field(
        default=None, validation_alias="hookFamily", serialization_alias="hookFamily"
    )
    cta_family: str | None = Field(
        default=None, validation_alias="ctaFamily", serialization_alias="ctaFamily"
    )
    audience: str | None = None
    status: str = "draft"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", "hypothesis", "status")
    @classmethod
    def _validate_required(cls, value: str, info) -> str:
        return _required(value, info.field_name)


class ContentExperimentResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    growth_program_id: str = Field(
        validation_alias="growthProgramId", serialization_alias="growthProgramId"
    )
    name: str
    hypothesis: str
    hook_family: str | None = Field(
        default=None, validation_alias="hookFamily", serialization_alias="hookFamily"
    )
    cta_family: str | None = Field(
        default=None, validation_alias="ctaFamily", serialization_alias="ctaFamily"
    )
    audience: str | None = None
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(validation_alias="createdAt", serialization_alias="createdAt")
    updated_at: datetime = Field(validation_alias="updatedAt", serialization_alias="updatedAt")


class ContentVariantSlideInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    slide_index: int = Field(validation_alias="slideIndex", serialization_alias="slideIndex")
    visual_role: str | None = Field(
        default=None, validation_alias="visualRole", serialization_alias="visualRole"
    )
    prompt: str | None = None
    overlay_text: str = Field(validation_alias="overlayText", serialization_alias="overlayText")
    source_asset_id: str | None = Field(
        default=None, validation_alias="sourceAssetId", serialization_alias="sourceAssetId"
    )
    rendered_asset_id: str | None = Field(
        default=None, validation_alias="renderedAssetId", serialization_alias="renderedAssetId"
    )
    render_status: str = Field(
        default="draft", validation_alias="renderStatus", serialization_alias="renderStatus"
    )
    renderer_version: str | None = Field(
        default=None, validation_alias="rendererVersion", serialization_alias="rendererVersion"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("slide_index")
    @classmethod
    def _validate_slide_index(cls, value: int) -> int:
        if value < 1:
            raise ValueError("slideIndex must be >= 1.")
        return value

    @field_validator("overlay_text", "render_status")
    @classmethod
    def _validate_required(cls, value: str, info) -> str:
        return _required(value, info.field_name)


class ContentVariantCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    experiment_id: str | None = Field(
        default=None, validation_alias="experimentId", serialization_alias="experimentId"
    )
    platform_key: str = Field(
        default="tiktok", validation_alias="platformKey", serialization_alias="platformKey"
    )
    format_key: str = Field(
        default="tiktok_carousel", validation_alias="formatKey", serialization_alias="formatKey"
    )
    title: str | None = None
    caption: str | None = None
    cta: str | None = None
    slide_count: int = Field(default=6, validation_alias="slideCount", serialization_alias="slideCount")
    status: str = "draft"
    storyboard: dict[str, Any] = Field(default_factory=dict)
    provider_payload: dict[str, Any] = Field(
        default_factory=dict, validation_alias="providerPayload", serialization_alias="providerPayload"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
    slides: list[ContentVariantSlideInput] = Field(default_factory=list)

    @field_validator("platform_key", "format_key", "status")
    @classmethod
    def _validate_required(cls, value: str, info) -> str:
        return _required(value, info.field_name)

    @field_validator("slide_count")
    @classmethod
    def _validate_slide_count(cls, value: int) -> int:
        if value < 1:
            raise ValueError("slideCount must be >= 1.")
        return value

    @model_validator(mode="after")
    def _validate_tiktok_carousel_slides(self) -> "ContentVariantCreateRequest":
        if self.format_key == "tiktok_carousel" and self.slides and len(self.slides) != self.slide_count:
            raise ValueError("TikTok carousel slide count must match provided slides.")
        return self


class ContentVariantSlideResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    slide_index: int = Field(validation_alias="slideIndex", serialization_alias="slideIndex")
    visual_role: str | None = Field(
        default=None, validation_alias="visualRole", serialization_alias="visualRole"
    )
    prompt: str | None = None
    overlay_text: str = Field(validation_alias="overlayText", serialization_alias="overlayText")
    source_asset_id: str | None = Field(
        default=None, validation_alias="sourceAssetId", serialization_alias="sourceAssetId"
    )
    rendered_asset_id: str | None = Field(
        default=None, validation_alias="renderedAssetId", serialization_alias="renderedAssetId"
    )
    render_status: str = Field(validation_alias="renderStatus", serialization_alias="renderStatus")
    renderer_version: str | None = Field(
        default=None, validation_alias="rendererVersion", serialization_alias="rendererVersion"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(validation_alias="createdAt", serialization_alias="createdAt")
    updated_at: datetime = Field(validation_alias="updatedAt", serialization_alias="updatedAt")


class ContentVariantResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    growth_program_id: str = Field(
        validation_alias="growthProgramId", serialization_alias="growthProgramId"
    )
    experiment_id: str | None = Field(
        default=None, validation_alias="experimentId", serialization_alias="experimentId"
    )
    platform_key: str = Field(validation_alias="platformKey", serialization_alias="platformKey")
    format_key: str = Field(validation_alias="formatKey", serialization_alias="formatKey")
    title: str | None = None
    caption: str | None = None
    cta: str | None = None
    slide_count: int = Field(validation_alias="slideCount", serialization_alias="slideCount")
    status: str
    approved_by_user_id: str | None = Field(
        default=None, validation_alias="approvedByUserId", serialization_alias="approvedByUserId"
    )
    approved_at: datetime | None = Field(
        default=None, validation_alias="approvedAt", serialization_alias="approvedAt"
    )
    storyboard: dict[str, Any] = Field(default_factory=dict)
    provider_payload: dict[str, Any] = Field(
        default_factory=dict, validation_alias="providerPayload", serialization_alias="providerPayload"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
    slides: list[ContentVariantSlideResponse] = Field(default_factory=list)
    created_at: datetime = Field(validation_alias="createdAt", serialization_alias="createdAt")
    updated_at: datetime = Field(validation_alias="updatedAt", serialization_alias="updatedAt")


class ContentVariantApproveRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    notes: str | None = None


class ContentVariantPostizProposalCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    content: str | None = None
    post_type: str = Field(
        default="draft", validation_alias="postType", serialization_alias="postType"
    )
    scheduled_for: datetime | None = Field(
        default=None, validation_alias="scheduledFor", serialization_alias="scheduledFor"
    )
    channel_ids: list[str] = Field(
        default_factory=list, validation_alias="channelIds", serialization_alias="channelIds"
    )
    media_urls: list[str] = Field(
        default_factory=list, validation_alias="mediaUrls", serialization_alias="mediaUrls"
    )
    link_url: str | None = Field(
        default=None, validation_alias="linkUrl", serialization_alias="linkUrl"
    )
    posting_profile_id: str | None = Field(
        default=None, validation_alias="postingProfileId", serialization_alias="postingProfileId"
    )
    provider_settings_by_identifier: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="providerSettingsByIdentifier",
        serialization_alias="providerSettingsByIdentifier",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("post_type")
    @classmethod
    def _validate_post_type(cls, value: str) -> str:
        cleaned = str(value or "").strip().lower()
        if cleaned not in {"draft", "schedule", "now"}:
            raise ValueError("postType must be one of: draft, schedule, now.")
        return cleaned

    @field_validator("channel_ids", "media_urls")
    @classmethod
    def _clean_string_list(cls, value: list[str]) -> list[str]:
        return [str(item or "").strip() for item in value if str(item or "").strip()]

    @field_validator("content", "link_url", "posting_profile_id")
    @classmethod
    def _clean_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @model_validator(mode="after")
    def _validate_schedule(self) -> "ContentVariantPostizProposalCreateRequest":
        if self.post_type == "schedule" and self.scheduled_for is None:
            raise ValueError("scheduledFor is required when postType is schedule.")
        return self


class ContentVariantPostizProposalResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    proposal_id: str = Field(validation_alias="proposalId", serialization_alias="proposalId")
    action_type: str = Field(validation_alias="actionType", serialization_alias="actionType")
    target_provider: str = Field(
        validation_alias="targetProvider", serialization_alias="targetProvider"
    )
    growth_program_id: str = Field(
        validation_alias="growthProgramId", serialization_alias="growthProgramId"
    )
    variant_id: str = Field(validation_alias="variantId", serialization_alias="variantId")
    status: str
    postiz_payload: dict[str, Any] = Field(
        default_factory=dict, validation_alias="postizPayload", serialization_alias="postizPayload"
    )
    created_at: datetime = Field(validation_alias="createdAt", serialization_alias="createdAt")


class ConversionEventCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    conversion_source_id: str = Field(
        validation_alias="conversionSourceId", serialization_alias="conversionSourceId"
    )
    provider_event_id: str = Field(
        validation_alias="providerEventId", serialization_alias="providerEventId"
    )
    event_name: str = Field(validation_alias="eventName", serialization_alias="eventName")
    occurred_at: datetime = Field(validation_alias="occurredAt", serialization_alias="occurredAt")
    value: Decimal | None = None
    currency: str | None = None
    user_id_hash: str | None = Field(
        default=None, validation_alias="userIdHash", serialization_alias="userIdHash"
    )
    campaign_ref: str | None = Field(
        default=None, validation_alias="campaignRef", serialization_alias="campaignRef"
    )
    content_experiment_id: str | None = Field(
        default=None,
        validation_alias="contentExperimentId",
        serialization_alias="contentExperimentId",
    )
    content_variant_id: str | None = Field(
        default=None,
        validation_alias="contentVariantId",
        serialization_alias="contentVariantId",
    )
    postiz_post_id: str | None = Field(
        default=None,
        validation_alias="postizPostId",
        serialization_alias="postizPostId",
    )
    postiz_channel_id: str | None = Field(
        default=None,
        validation_alias="postizChannelId",
        serialization_alias="postizChannelId",
    )
    attribution: dict[str, Any] = Field(default_factory=dict)
    raw_payload: dict[str, Any] = Field(
        default_factory=dict, validation_alias="rawPayload", serialization_alias="rawPayload"
    )
    provenance: str = "concrete"

    @field_validator("conversion_source_id", "provider_event_id", "event_name", "provenance")
    @classmethod
    def _validate_required(cls, value: str, info) -> str:
        return _required(value, info.field_name)
