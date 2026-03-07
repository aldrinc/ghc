from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AdCopyPackItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    requirement_index: int = Field(alias="requirementIndex")
    channel: str
    format: str
    funnel_stage: str | None = Field(default=None, alias="funnelStage")
    angle: str | None = None
    hook: str | None = None
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
    items: list[CreativeGenerationPlanItem] = Field(default_factory=list)


class AdCopyPackStructuredOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    copy_packs: list[AdCopyPackItem] = Field(default_factory=list, alias="copyPacks")


class CreativeGenerationPlanSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: str = Field(alias="batchId")
    asset_brief_id: str = Field(alias="assetBriefId")
    item_count: int = Field(alias="itemCount")
    requirement_indexes: list[int] = Field(default_factory=list, alias="requirementIndexes")
    source_labels: list[str] = Field(default_factory=list, alias="sourceLabels")
    metadata: dict[str, Any] = Field(default_factory=dict)
