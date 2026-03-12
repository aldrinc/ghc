from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.asset_brief_types import (
    normalize_optional_asset_brief_types,
    normalize_required_asset_brief_types,
)


def _normalize_required_string_list(value: list[str], *, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must include at least one non-empty value.")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} must contain non-empty strings.")
        cleaned = item.strip()
        if cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    if not normalized:
        raise ValueError(f"{field_name} must include at least one non-empty value.")
    return normalized


def _normalize_optional_string_list(value: list[str] | None, *, field_name: str) -> list[str] | None:
    if value is None:
        return None
    return _normalize_required_string_list(value, field_name=field_name)


class StrategyV2LaunchAngleCampaignRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    channels: list[str]
    asset_brief_types: list[str] = Field(
        ...,
        validation_alias="assetBriefTypes",
        serialization_alias="assetBriefTypes",
    )
    experiment_variant_policy: str = Field(
        ...,
        min_length=1,
        validation_alias="experimentVariantPolicy",
        serialization_alias="experimentVariantPolicy",
    )

    @field_validator("channels")
    @classmethod
    def _validate_channels(cls, value: list[str]) -> list[str]:
        return _normalize_required_string_list(value, field_name="channels")

    @field_validator("asset_brief_types")
    @classmethod
    def _validate_asset_brief_types(cls, value: list[str]) -> list[str]:
        return normalize_required_asset_brief_types(value, field_name="assetBriefTypes")

    @field_validator("experiment_variant_policy")
    @classmethod
    def _validate_experiment_variant_policy(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("experimentVariantPolicy must be a non-empty string.")
        return cleaned


class StrategyV2LaunchAdditionalUmsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    campaign_id: str = Field(..., min_length=1, validation_alias="campaignId", serialization_alias="campaignId")
    ums_selection_ids: list[str] = Field(
        ...,
        min_length=1,
        validation_alias="umsSelectionIds",
        serialization_alias="umsSelectionIds",
    )
    launch_name_prefix: str = Field(
        ...,
        min_length=1,
        validation_alias="launchNamePrefix",
        serialization_alias="launchNamePrefix",
    )
    channels: list[str] | None = None
    asset_brief_types: list[str] | None = Field(
        default=None,
        validation_alias="assetBriefTypes",
        serialization_alias="assetBriefTypes",
    )

    @field_validator("campaign_id")
    @classmethod
    def _validate_campaign_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("campaignId must be a non-empty string.")
        return cleaned

    @field_validator("ums_selection_ids")
    @classmethod
    def _validate_ums_selection_ids(cls, value: list[str]) -> list[str]:
        return _normalize_required_string_list(value, field_name="umsSelectionIds")

    @field_validator("launch_name_prefix")
    @classmethod
    def _validate_launch_name_prefix(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("launchNamePrefix must be a non-empty string.")
        return cleaned

    @field_validator("channels")
    @classmethod
    def _validate_channels(cls, value: list[str] | None) -> list[str] | None:
        return _normalize_optional_string_list(value, field_name="channels")

    @field_validator("asset_brief_types")
    @classmethod
    def _validate_asset_brief_types(cls, value: list[str] | None) -> list[str] | None:
        return normalize_optional_asset_brief_types(value, field_name="assetBriefTypes")


class StrategyV2LaunchAdditionalAngleRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    selected_angle_ids: list[str] = Field(
        ...,
        min_length=1,
        validation_alias="selectedAngleIds",
        serialization_alias="selectedAngleIds",
    )
    channels: list[str]
    asset_brief_types: list[str] = Field(
        ...,
        validation_alias="assetBriefTypes",
        serialization_alias="assetBriefTypes",
    )

    @field_validator("selected_angle_ids")
    @classmethod
    def _validate_selected_angle_ids(cls, value: list[str]) -> list[str]:
        return _normalize_required_string_list(value, field_name="selectedAngleIds")

    @field_validator("channels")
    @classmethod
    def _validate_channels(cls, value: list[str]) -> list[str]:
        return _normalize_required_string_list(value, field_name="channels")

    @field_validator("asset_brief_types")
    @classmethod
    def _validate_asset_brief_types(cls, value: list[str]) -> list[str]:
        return normalize_required_asset_brief_types(value, field_name="assetBriefTypes")


class StrategyV2LaunchRecordResponse(BaseModel):
    id: str
    launch_type: Literal["initial_angle", "additional_ums", "additional_angle"]
    launch_key: str
    campaign_id: str | None = None
    funnel_id: str | None = None
    angle_id: str
    angle_run_id: str
    selected_ums_id: str | None = None
    selected_variant_id: str | None = None
    launch_index: int | None = None
    launch_workflow_run_id: str | None = None
    launch_temporal_workflow_id: str | None = None
    launch_status: str | None = None
    created_by_user: str | None = None
    created_at: str


class StrategyV2LaunchActionResponse(BaseModel):
    launch_workflow_run_id: str
    launch_temporal_workflow_id: str
    campaign_ids: list[str]
    funnel_workflow_run_ids: list[str]
    launch_records: list[StrategyV2LaunchRecordResponse]
