from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GetHookdCredentialsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    api_token: str = Field(validation_alias="apiToken", serialization_alias="apiToken")

    @field_validator("api_token")
    @classmethod
    def _validate_api_token(cls, value: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValueError("apiToken is required.")
        return cleaned


class GetHookdCredentialsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    has_credentials: bool = Field(
        validation_alias="hasCredentials", serialization_alias="hasCredentials"
    )
    last_validated_at: datetime | None = Field(
        default=None,
        validation_alias="lastValidatedAt",
        serialization_alias="lastValidatedAt",
    )
    last_validation_error: str | None = Field(
        default=None,
        validation_alias="lastValidationError",
        serialization_alias="lastValidationError",
    )


class GetHookdSyncFeedBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str
    enabled: bool = True
    filters_json: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="filters",
        serialization_alias="filters",
    )
    max_pages_per_run: int = Field(
        default=5,
        validation_alias="maxPagesPerRun",
        serialization_alias="maxPagesPerRun",
    )
    per_page: int = Field(default=100, validation_alias="perPage", serialization_alias="perPage")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValueError("name is required.")
        return cleaned


class GetHookdSyncFeedCreateRequest(GetHookdSyncFeedBase):
    pass


class GetHookdSyncFeedUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str | None = None
    enabled: bool | None = None
    filters_json: dict[str, Any] | None = Field(
        default=None,
        validation_alias="filters",
        serialization_alias="filters",
    )
    max_pages_per_run: int | None = Field(
        default=None,
        validation_alias="maxPagesPerRun",
        serialization_alias="maxPagesPerRun",
    )
    per_page: int | None = Field(
        default=None,
        validation_alias="perPage",
        serialization_alias="perPage",
    )


class GetHookdSyncFeedResponse(GetHookdSyncFeedBase):
    id: str
    created_at: datetime = Field(validation_alias="createdAt", serialization_alias="createdAt")
    updated_at: datetime = Field(validation_alias="updatedAt", serialization_alias="updatedAt")


class SwipeReviewBulkRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    swipe_asset_ids: list[str] = Field(
        validation_alias="swipeAssetIds",
        serialization_alias="swipeAssetIds",
    )
    collection_id: str | None = Field(
        default=None,
        validation_alias="collectionId",
        serialization_alias="collectionId",
    )

    @field_validator("swipe_asset_ids")
    @classmethod
    def _validate_swipe_asset_ids(cls, value: list[str]) -> list[str]:
        cleaned = [str(item or "").strip() for item in value if str(item or "").strip()]
        deduped = list(dict.fromkeys(cleaned))
        if not deduped:
            raise ValueError("swipeAssetIds must contain at least one id.")
        return deduped


class CampaignSwipeDefaultResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    swipe_collection_id: str | None = Field(
        default=None,
        validation_alias="swipeCollectionId",
        serialization_alias="swipeCollectionId",
    )
    swipe_collection_name: str | None = Field(
        default=None,
        validation_alias="swipeCollectionName",
        serialization_alias="swipeCollectionName",
    )
    ready_swipe_count: int = Field(
        default=0,
        validation_alias="readySwipeCount",
        serialization_alias="readySwipeCount",
    )


class CampaignSwipeDefaultUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    swipe_collection_id: str | None = Field(
        default=None,
        validation_alias="swipeCollectionId",
        serialization_alias="swipeCollectionId",
    )
