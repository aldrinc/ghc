from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class CompanySwipeBrandModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    external_brand_id: str | None = None
    name: str
    slug: str | None = None
    ad_library_link: HttpUrl | None = None
    brand_page_link: HttpUrl | None = None
    logo_url: HttpUrl | None = None
    categories: list | None = None


class CompanySwipeMediaModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    swipe_asset_id: str
    external_media_id: str | None = None
    path: str | None = None
    url: str | None = None
    thumbnail_path: str | None = None
    thumbnail_url: str | None = None
    disk: str | None = None
    type: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    video_length: int | None = None
    download_url: str | None = None


class CompanySwipeAssetModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    source_kind: str
    origin_system: str
    external_ad_id: str | None = None
    external_platform_ad_id: str | None = None
    brand_id: str | None = None
    title: str | None = None
    body: str | None = None
    platforms: str | None = None
    cta_type: str | None = None
    cta_text: str | None = None
    display_format: str | None = None
    landing_page: str | None = None
    link_description: str | None = None
    ad_source_link: str | None = None
    analysis_status: str
    analysis_error: str | None = None
    analysis_model: str | None = None
    analysis_updated_at: datetime | None = None
    ad_unit_format: str | None = None
    placement_shape: str | None = None
    channel: str | None = None
    destination_type: str | None = None
    funnel_stage: str | None = None
    angle_family: str | None = None
    hook_type: str | None = None
    visual_archetype: str | None = None
    product_presence: str | None = None
    proof_type: str | None = None
    claim_risk: str | None = None
    product_image_policy: str | None = None
    media: list[CompanySwipeMediaModel] = Field(default_factory=list)


class ClientSwipeAssetModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    client_id: str
    company_swipe_id: str | None = None
    custom_title: str | None = None
    custom_body: str | None = None
    custom_channel: str | None = None
    custom_format: str | None = None
    custom_landing_page: str | None = None
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    is_good_example: bool | None = None
    is_bad_example: bool | None = None


class SwipeCollectionModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    name: str
    kind: str
    cloned_from_collection_id: str | None = None
    created_by_user_id: str | None = None
    created_at: datetime
    writable: bool = True
    item_count: int = 0
    analysis_counts: dict[str, int] = Field(default_factory=dict)


class SwipeCollectionDetailModel(SwipeCollectionModel):
    swipes: list[CompanySwipeAssetModel] = Field(default_factory=list)


class SwipeCollectionCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str
    kind: Literal["uploaded", "curated"] = "curated"

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name is required.")
        return cleaned


class SwipeCollectionCloneRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name is required.")
        return cleaned


class SwipeCollectionItemsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    swipe_asset_ids: list[str] = Field(
        ...,
        validation_alias="swipeAssetIds",
        serialization_alias="swipeAssetIds",
    )

    @field_validator("swipe_asset_ids")
    @classmethod
    def _validate_swipe_asset_ids(cls, value: list[str]) -> list[str]:
        if not isinstance(value, list) or not value:
            raise ValueError("swipeAssetIds must be a non-empty list.")
        deduped: list[str] = []
        seen: set[str] = set()
        for entry in value:
            cleaned = str(entry or "").strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            deduped.append(cleaned)
        if not deduped:
            raise ValueError("swipeAssetIds must contain at least one id.")
        return deduped


class SwipeAssetUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    title: str | None = None
    body: str | None = None
    landing_page: str | None = None
    channel: Literal["meta", "tiktok", "google"] | None = None
    destination_type: (
        Literal[
            "product_page",
            "collection_page",
            "advertorial",
            "listicle",
            "quiz",
            "lead_form",
            "article",
            "app_store",
            "marketplace",
        ]
        | None
    ) = None
    funnel_stage: Literal["cold", "warm", "hot"] | None = None
    angle_family: (
        Literal[
            "problem",
            "symptom",
            "mechanism",
            "outcome",
            "identity",
            "comparison",
            "objection",
            "authority",
            "offer",
            "urgency",
        ]
        | None
    ) = None
    hook_type: (
        Literal[
            "direct_benefit",
            "curiosity_gap",
            "pain_agitation",
            "question_hook",
            "stat_hook",
            "contrarian_hook",
            "authority_hook",
            "before_after_hook",
            "demo_hook",
            "social_proof_hook",
            "founder_story_hook",
        ]
        | None
    ) = None
    visual_archetype: (
        Literal[
            "ugc_selfie",
            "ugc_spokesperson",
            "founder_facecam",
            "product_demo",
            "before_after",
            "text_heavy_static",
            "testimonial_screenshot",
            "comparison_chart",
            "meme_native",
            "offer_card",
            "advertorial_mock",
            "lifestyle_scene",
        ]
        | None
    ) = None
    product_presence: (
        Literal["hero_product", "in_use_product", "contextual_product", "packaging_only", "no_product"] | None
    ) = None
    proof_type: (
        Literal[
            "testimonial",
            "review_volume",
            "authority",
            "statistic",
            "before_after",
            "demo",
            "ingredient",
            "press",
            "guarantee",
            "comparison",
        ]
        | None
    ) = None
    claim_risk: Literal["low", "medium", "high", "regulated"] | None = None
    product_image_policy: Literal["requires_product_image", "no_product_image", "either"] | None = None


class SwipeCollectionUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    collection_id: str
    created_swipes: list[CompanySwipeAssetModel] = Field(default_factory=list)


class SwipeTaxonomyGeminiOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["swipe_taxonomy_v1"]
    channel: Literal["meta", "tiktok", "google"] | None = None
    destination_type: (
        Literal[
            "product_page",
            "collection_page",
            "advertorial",
            "listicle",
            "quiz",
            "lead_form",
            "article",
            "app_store",
            "marketplace",
        ]
        | None
    ) = None
    funnel_stage: Literal["cold", "warm", "hot"] | None = None
    angle_family: (
        Literal[
            "problem",
            "symptom",
            "mechanism",
            "outcome",
            "identity",
            "comparison",
            "objection",
            "authority",
            "offer",
            "urgency",
        ]
        | None
    ) = None
    hook_type: (
        Literal[
            "direct_benefit",
            "curiosity_gap",
            "pain_agitation",
            "question_hook",
            "stat_hook",
            "contrarian_hook",
            "authority_hook",
            "before_after_hook",
            "demo_hook",
            "social_proof_hook",
            "founder_story_hook",
        ]
        | None
    ) = None
    visual_archetype: (
        Literal[
            "ugc_selfie",
            "ugc_spokesperson",
            "founder_facecam",
            "product_demo",
            "before_after",
            "text_heavy_static",
            "testimonial_screenshot",
            "comparison_chart",
            "meme_native",
            "offer_card",
            "advertorial_mock",
            "lifestyle_scene",
        ]
        | None
    ) = None
    product_presence: (
        Literal["hero_product", "in_use_product", "contextual_product", "packaging_only", "no_product"] | None
    ) = None
    proof_type: (
        Literal[
            "testimonial",
            "review_volume",
            "authority",
            "statistic",
            "before_after",
            "demo",
            "ingredient",
            "press",
            "guarantee",
            "comparison",
        ]
        | None
    ) = None
    claim_risk: Literal["low", "medium", "high", "regulated"] | None = None
    product_image_policy: Literal["requires_product_image", "no_product_image", "either"] | None = None
