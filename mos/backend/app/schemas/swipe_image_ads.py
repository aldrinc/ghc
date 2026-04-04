from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SwipeImageAdGenerateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    client_id: str = Field(..., validation_alias="clientId", serialization_alias="clientId")
    product_id: str = Field(..., validation_alias="productId", serialization_alias="productId")
    campaign_id: str = Field(..., validation_alias="campaignId", serialization_alias="campaignId")

    asset_brief_id: str = Field(..., validation_alias="assetBriefId", serialization_alias="assetBriefId")
    requirement_index: int = Field(
        0,
        ge=0,
        validation_alias="requirementIndex",
        serialization_alias="requirementIndex",
    )

    company_swipe_id: str | None = Field(
        None,
        validation_alias="companySwipeId",
        serialization_alias="companySwipeId",
    )
    swipe_image_url: str | None = Field(
        None,
        validation_alias="swipeImageUrl",
        serialization_alias="swipeImageUrl",
    )
    swipe_requires_product_image: bool | None = Field(
        None,
        validation_alias="swipeRequiresProductImage",
        serialization_alias="swipeRequiresProductImage",
    )
    swipe_context_mode: Literal["workspace", "minimal"] = Field(
        "workspace",
        validation_alias="swipeContextMode",
        serialization_alias="swipeContextMode",
    )
    swipe_brand_name: str | None = Field(
        None,
        validation_alias="swipeBrandName",
        serialization_alias="swipeBrandName",
    )
    swipe_product_name: str | None = Field(
        None,
        validation_alias="swipeProductName",
        serialization_alias="swipeProductName",
    )
    swipe_angle: str | None = Field(
        None,
        validation_alias="swipeAngle",
        serialization_alias="swipeAngle",
    )
    swipe_hook: str | None = Field(
        None,
        validation_alias="swipeHook",
        serialization_alias="swipeHook",
    )

    model: str | None = Field(None, description="Gemini model name to use for swipe prompt generation.")
    render_model_id: str | None = Field(
        None,
        description="Model id for the final image-rendering step only.",
        validation_alias="renderModelId",
        serialization_alias="renderModelId",
    )
    max_output_tokens: int | None = Field(
        None,
        ge=256,
        le=32000,
        validation_alias="maxOutputTokens",
        serialization_alias="maxOutputTokens",
    )

    aspect_ratio: str = Field(
        "1:1",
        validation_alias="aspectRatio",
        serialization_alias="aspectRatio",
    )
    count: int = Field(1, ge=1, le=6)

    @model_validator(mode="after")
    def _validate_swipe_source(self) -> "SwipeImageAdGenerateRequest":
        if bool(self.company_swipe_id) == bool(self.swipe_image_url):
            raise ValueError("Provide exactly one of companySwipeId or swipeImageUrl.")
        model_value = (self.model or "").strip().lower()
        if model_value and (
            "image-preview" in model_value
            or "image-generation" in model_value
            or model_value.endswith("-image")
        ):
            raise ValueError(
                "model is only for stage-1 prompt generation. "
                "Use renderModelId for final image rendering models."
            )
        return self


class SwipeTemplateTestimonialsGenerateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    campaign_id: str = Field(..., validation_alias="campaignId", serialization_alias="campaignId")
    asset_brief_id: str = Field(..., validation_alias="assetBriefId", serialization_alias="assetBriefId")
    aspect_ratio: str = Field("1:1", validation_alias="aspectRatio", serialization_alias="aspectRatio")
    model: str | None = Field(None, description="Gemini model name to use for swipe prompt generation.")
    render_model_id: str | None = Field(
        None,
        description="Model id for the final image-rendering step only.",
        validation_alias="renderModelId",
        serialization_alias="renderModelId",
    )
    max_output_tokens: int | None = Field(
        None,
        ge=256,
        le=32000,
        validation_alias="maxOutputTokens",
        serialization_alias="maxOutputTokens",
    )

    @model_validator(mode="after")
    def _validate_models(self) -> "SwipeTemplateTestimonialsGenerateRequest":
        model_value = (self.model or "").strip().lower()
        if model_value and (
            "image-preview" in model_value
            or "image-generation" in model_value
            or model_value.endswith("-image")
        ):
            raise ValueError(
                "model is only for stage-1 prompt generation. "
                "Use renderModelId for final image rendering models."
            )
        return self


class SwipeTemplateTestimonialsRun(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    template_file: str = Field(..., validation_alias="templateFile", serialization_alias="templateFile")
    template_label: str = Field(..., validation_alias="templateLabel", serialization_alias="templateLabel")
    staged_asset_id: str = Field(..., validation_alias="stagedAssetId", serialization_alias="stagedAssetId")
    staged_public_id: str = Field(..., validation_alias="stagedPublicId", serialization_alias="stagedPublicId")
    staged_public_url: str = Field(..., validation_alias="stagedPublicUrl", serialization_alias="stagedPublicUrl")
    workflow_run_id: str = Field(..., validation_alias="workflowRunId", serialization_alias="workflowRunId")
    temporal_workflow_id: str = Field(
        ...,
        validation_alias="temporalWorkflowId",
        serialization_alias="temporalWorkflowId",
    )


class SwipeTemplateTestimonialsGenerateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    campaign_id: str = Field(..., validation_alias="campaignId", serialization_alias="campaignId")
    asset_brief_id: str = Field(..., validation_alias="assetBriefId", serialization_alias="assetBriefId")
    client_id: str = Field(..., validation_alias="clientId", serialization_alias="clientId")
    product_id: str = Field(..., validation_alias="productId", serialization_alias="productId")
    requirement_index: int = Field(
        ...,
        validation_alias="requirementIndex",
        serialization_alias="requirementIndex",
    )
    template_runs: list[SwipeTemplateTestimonialsRun] = Field(
        default_factory=list,
        validation_alias="templateRuns",
        serialization_alias="templateRuns",
    )
