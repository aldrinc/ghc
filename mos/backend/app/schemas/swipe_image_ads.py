from __future__ import annotations

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

    model: str | None = Field(None, description="Gemini model name to use for swipe prompt generation.")
    max_output_tokens: int | None = Field(
        None,
        ge=256,
        le=24000,
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
        return self
