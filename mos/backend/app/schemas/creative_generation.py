from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AdCopyPackItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    requirement_index: int = Field(alias="requirementIndex")
    channel: str
    format: str
    funnel_stage: str | None = Field(default=None, alias="funnelStage")
    angle: str | None = None
    hook: str | None = None
    destination_type: str | None = Field(default=None, alias="destinationType")
    destination_label: str | None = Field(default=None, alias="destinationLabel")
    creative_concept: str = Field(alias="creativeConcept")
    meta_primary_text: str = Field(alias="metaPrimaryText")
    meta_headline: str = Field(alias="metaHeadline")
    meta_description: str = Field(alias="metaDescription")
    claims_guardrails: list[str] = Field(default_factory=list, alias="claimsGuardrails")


class AdCopyPackArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(alias="schemaVersion")
    asset_brief_id: str = Field(alias="assetBriefId")
    source_brief_artifact_id: str = Field(alias="sourceBriefArtifactId")
    source_brief_sha256: str = Field(alias="sourceBriefSha256")
    source_funnel_id: str | None = Field(default=None, alias="sourceFunnelId")
    campaign_delivery_config_id: str | None = Field(default=None, alias="campaignDeliveryConfigId")
    delivery_mode: str | None = Field(default=None, alias="deliveryMode")
    destination_type: str | None = Field(default=None, alias="destinationType")
    destination_label: str | None = Field(default=None, alias="destinationLabel")
    copy_packs: list[AdCopyPackItem] = Field(default_factory=list, alias="copyPacks")


class CreativeGenerationPlanItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    batch_id: str = Field(alias="batchId")
    asset_brief_id: str = Field(alias="assetBriefId")
    requirement_index: int = Field(alias="requirementIndex")
    channel: str
    format: str
    funnel_stage: str | None = Field(default=None, alias="funnelStage")
    angle: str | None = None
    hook: str | None = None
    delivery_mode: str | None = Field(default=None, alias="deliveryMode")
    destination_type: str | None = Field(default=None, alias="destinationType")
    destination_label: str | None = Field(default=None, alias="destinationLabel")
    campaign_delivery_config_id: str | None = Field(default=None, alias="campaignDeliveryConfigId")
    company_swipe_id: str = Field(alias="companySwipeId")
    source_label: str = Field(alias="sourceLabel")
    source_media_url: str = Field(alias="sourceMediaUrl")
    copy_pack_id: str = Field(alias="copyPackId")
    product_image_policy: bool | None = Field(default=None, alias="productImagePolicy")
    source_set_key: str = Field(alias="sourceSetKey")


class CreativeGenerationPlanArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_brief_id: str = Field(alias="assetBriefId")
    source_brief_artifact_id: str = Field(alias="sourceBriefArtifactId")
    ad_copy_pack_artifact_id: str = Field(alias="adCopyPackArtifactId")
    batch_id: str = Field(alias="batchId")
    source_set_key: str = Field(alias="sourceSetKey")
    source_collection_id: str | None = Field(default=None, alias="sourceCollectionId")
    source_collection_name: str | None = Field(default=None, alias="sourceCollectionName")
    resolved_swipe_asset_ids: list[str] = Field(default_factory=list, alias="resolvedSwipeAssetIds")
    items: list[CreativeGenerationPlanItem] = Field(default_factory=list)


class AdCopyPackStructuredOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    copy_packs: list[AdCopyPackItem] = Field(default_factory=list, alias="copyPacks")


_ALLOWED_META_CTAS = {"Learn More", "Shop Now", "Watch More", "Sign Up"}
_ALLOWED_TIKTOK_CTAS = {"Learn More", "Shop Now"}


class SwipeAdCopyPack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: str
    requirement_index: int = Field(alias="requirementIndex")
    channel: str
    format: str
    funnel_stage: str | None = Field(default=None, alias="funnelStage")
    angle: str | None = None
    hook: str | None = None
    destination_type: str = Field(alias="destinationType")
    selected_variation: str = Field(alias="selectedVariation")
    formatted_variations_markdown: str = Field(alias="formattedVariationsMarkdown")
    meta_primary_text: str | None = Field(default=None, alias="metaPrimaryText")
    meta_headline: str | None = Field(default=None, alias="metaHeadline")
    meta_description: str | None = Field(default=None, alias="metaDescription")
    meta_cta: str | None = Field(default=None, alias="metaCta")
    tiktok_caption: str | None = Field(default=None, alias="tiktokCaption")
    tiktok_on_screen_text: str | None = Field(default=None, alias="tiktokOnScreenText")
    tiktok_cta: str | None = Field(default=None, alias="tiktokCta")
    claims_guardrails: list[str] = Field(default_factory=list, alias="claimsGuardrails")

    @model_validator(mode="after")
    def _validate_platform_fields(self) -> "SwipeAdCopyPack":
        normalized_platform = self.platform.strip().lower()
        if normalized_platform not in {"meta", "tiktok"}:
            raise ValueError("platform must be either 'Meta' or 'TikTok'.")
        markdown = self.formatted_variations_markdown.strip()
        if "```" not in markdown:
            raise ValueError("formattedVariationsMarkdown must contain a markdown code block.")
        if not self.selected_variation.strip():
            raise ValueError("selectedVariation must be a non-empty string.")

        if normalized_platform == "meta":
            required_values = {
                "metaPrimaryText": self.meta_primary_text,
                "metaHeadline": self.meta_headline,
                "metaDescription": self.meta_description,
                "metaCta": self.meta_cta,
            }
            missing = [key for key, value in required_values.items() if not isinstance(value, str) or not value.strip()]
            if missing:
                raise ValueError(
                    "Meta swipe copy pack is missing required fields: " + ", ".join(missing)
                )
            if self.meta_cta not in _ALLOWED_META_CTAS:
                raise ValueError(
                    "metaCta must be one of: " + ", ".join(sorted(_ALLOWED_META_CTAS))
                )
        else:
            required_values = {
                "tiktokCaption": self.tiktok_caption,
                "tiktokOnScreenText": self.tiktok_on_screen_text,
                "tiktokCta": self.tiktok_cta,
            }
            missing = [key for key, value in required_values.items() if not isinstance(value, str) or not value.strip()]
            if missing:
                raise ValueError(
                    "TikTok swipe copy pack is missing required fields: " + ", ".join(missing)
                )
            if self.tiktok_cta not in _ALLOWED_TIKTOK_CTAS:
                raise ValueError(
                    "tiktokCta must be one of: " + ", ".join(sorted(_ALLOWED_TIKTOK_CTAS))
                )

        return self


class SwipeCopyInputMedia(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_kind: str | None = Field(default=None, alias="sourceKind")
    asset_type: str = Field(alias="assetType")
    source_label: str | None = Field(default=None, alias="sourceLabel")
    source_url: str = Field(alias="sourceUrl")
    mime_type: str | None = Field(default=None, alias="mimeType")
    storage_key: str | None = Field(default=None, alias="storageKey")
    remote_asset_id: str | None = Field(default=None, alias="remoteAssetId")

    @model_validator(mode="after")
    def _validate_source(self) -> "SwipeCopyInputMedia":
        if self.source_kind is not None and self.source_kind not in {"source_swipe", "rendered_output"}:
            raise ValueError("sourceKind must be either 'source_swipe' or 'rendered_output' when provided.")
        if not self.asset_type.strip():
            raise ValueError("assetType must be a non-empty string.")
        if not self.source_url.strip():
            raise ValueError("sourceUrl must be a non-empty string.")
        return self


class SwipeCopySourceSwipeProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_swipe_id: str | None = Field(default=None, alias="companySwipeId")
    source_label: str | None = Field(default=None, alias="sourceLabel")
    source_url: str | None = Field(default=None, alias="sourceUrl")
    mime_type: str | None = Field(default=None, alias="mimeType")


class SwipeCopyInputs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: str
    ad_image_or_video: SwipeCopyInputMedia = Field(alias="adImageOrVideo")
    angle_used: str = Field(alias="angleUsed")
    destination_page: str = Field(alias="destinationPage")
    ad_copy_pack_id: str | None = Field(default=None, alias="adCopyPackId")
    ad_copy_pack_artifact_id: str | None = Field(default=None, alias="adCopyPackArtifactId")
    source_swipe: SwipeCopySourceSwipeProvenance | None = Field(default=None, alias="sourceSwipe")

    @model_validator(mode="after")
    def _validate_required_fields(self) -> "SwipeCopyInputs":
        if not self.platform.strip():
            raise ValueError("platform must be a non-empty string.")
        if not self.angle_used.strip():
            raise ValueError("angleUsed must be a non-empty string.")
        if not self.destination_page.strip():
            raise ValueError("destinationPage must be a non-empty string.")
        return self


class CreativeGenerationPlanSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: str = Field(alias="batchId")
    asset_brief_id: str = Field(alias="assetBriefId")
    item_count: int = Field(alias="itemCount")
    requirement_indexes: list[int] = Field(default_factory=list, alias="requirementIndexes")
    source_labels: list[str] = Field(default_factory=list, alias="sourceLabels")
    metadata: dict[str, Any] = Field(default_factory=dict)
