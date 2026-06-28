"""Schemas for connected social agent primitives."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _clean_required(value: str, field_name: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError(f"{field_name} is required.")
    return cleaned


class SocialProviderAssetUpsertRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    connection_id: str | None = Field(
        default=None, validation_alias="connectionId", serialization_alias="connectionId"
    )
    provider: str
    provider_asset_id: str = Field(
        validation_alias="providerAssetId", serialization_alias="providerAssetId"
    )
    asset_type: str = Field(validation_alias="assetType", serialization_alias="assetType")
    display_name: str = Field(validation_alias="displayName", serialization_alias="displayName")
    parent_provider_asset_id: str | None = Field(
        default=None,
        validation_alias="parentProviderAssetId",
        serialization_alias="parentProviderAssetId",
    )
    capability_flags: list[str] = Field(
        default_factory=list,
        validation_alias="capabilityFlags",
        serialization_alias="capabilityFlags",
    )
    status: str = "active"
    raw_payload: dict[str, Any] = Field(
        default_factory=dict, validation_alias="rawPayload", serialization_alias="rawPayload"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider", "provider_asset_id", "asset_type", "display_name", "status")
    @classmethod
    def _validate_required(cls, value: str, info) -> str:
        return _clean_required(value, info.field_name)


class SocialProviderAssetResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    connection_id: str | None = Field(
        default=None, validation_alias="connectionId", serialization_alias="connectionId"
    )
    provider: str
    provider_asset_id: str = Field(
        validation_alias="providerAssetId", serialization_alias="providerAssetId"
    )
    asset_type: str = Field(validation_alias="assetType", serialization_alias="assetType")
    display_name: str = Field(validation_alias="displayName", serialization_alias="displayName")
    parent_provider_asset_id: str | None = Field(
        default=None,
        validation_alias="parentProviderAssetId",
        serialization_alias="parentProviderAssetId",
    )
    capability_flags: list[str] = Field(
        default_factory=list,
        validation_alias="capabilityFlags",
        serialization_alias="capabilityFlags",
    )
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    last_synced_at: datetime | None = Field(
        default=None, validation_alias="lastSyncedAt", serialization_alias="lastSyncedAt"
    )
    created_at: datetime = Field(validation_alias="createdAt", serialization_alias="createdAt")
    updated_at: datetime = Field(validation_alias="updatedAt", serialization_alias="updatedAt")


class SocialProviderSnapshotCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    provider_asset_id: str | None = Field(
        default=None, validation_alias="providerAssetId", serialization_alias="providerAssetId"
    )
    provider: str
    snapshot_type: str = Field(validation_alias="snapshotType", serialization_alias="snapshotType")
    time_from: datetime | None = Field(
        default=None, validation_alias="timeFrom", serialization_alias="timeFrom"
    )
    time_to: datetime | None = Field(default=None, validation_alias="timeTo", serialization_alias="timeTo")
    metrics: dict[str, Any] = Field(default_factory=dict)
    raw_payload: dict[str, Any] = Field(
        default_factory=dict, validation_alias="rawPayload", serialization_alias="rawPayload"
    )
    provenance: str = "concrete"

    @field_validator("provider", "snapshot_type", "provenance")
    @classmethod
    def _validate_required(cls, value: str, info) -> str:
        return _clean_required(value, info.field_name)


class SocialProviderSnapshotResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    provider_asset_id: str | None = Field(
        default=None, validation_alias="providerAssetId", serialization_alias="providerAssetId"
    )
    provider: str
    snapshot_type: str = Field(validation_alias="snapshotType", serialization_alias="snapshotType")
    time_from: datetime | None = Field(
        default=None, validation_alias="timeFrom", serialization_alias="timeFrom"
    )
    time_to: datetime | None = Field(default=None, validation_alias="timeTo", serialization_alias="timeTo")
    metrics: dict[str, Any]
    provenance: str
    created_at: datetime = Field(validation_alias="createdAt", serialization_alias="createdAt")


class AgentActionProposalCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    campaign_id: str | None = Field(
        default=None, validation_alias="campaignId", serialization_alias="campaignId"
    )
    source_agent_run_id: str | None = Field(
        default=None, validation_alias="sourceAgentRunId", serialization_alias="sourceAgentRunId"
    )
    action_type: str = Field(validation_alias="actionType", serialization_alias="actionType")
    target_provider: str = Field(
        validation_alias="targetProvider", serialization_alias="targetProvider"
    )
    target_asset_id: str | None = Field(
        default=None, validation_alias="targetAssetId", serialization_alias="targetAssetId"
    )
    target_asset_type: str | None = Field(
        default=None, validation_alias="targetAssetType", serialization_alias="targetAssetType"
    )
    before_snapshot: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="beforeSnapshot",
        serialization_alias="beforeSnapshot",
    )
    proposed_after: dict[str, Any] = Field(
        default_factory=dict, validation_alias="proposedAfter", serialization_alias="proposedAfter"
    )
    rationale: str | None = None
    risk_label: str = Field(default="medium", validation_alias="riskLabel", serialization_alias="riskLabel")
    required_capability: str | None = Field(
        default=None,
        validation_alias="requiredCapability",
        serialization_alias="requiredCapability",
    )
    rollback_hint: dict[str, Any] = Field(
        default_factory=dict, validation_alias="rollbackHint", serialization_alias="rollbackHint"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("action_type", "target_provider", "risk_label")
    @classmethod
    def _validate_required(cls, value: str, info) -> str:
        return _clean_required(value, info.field_name)


class AgentActionProposalResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    campaign_id: str | None = Field(
        default=None, validation_alias="campaignId", serialization_alias="campaignId"
    )
    source_agent_run_id: str | None = Field(
        default=None, validation_alias="sourceAgentRunId", serialization_alias="sourceAgentRunId"
    )
    action_type: str = Field(validation_alias="actionType", serialization_alias="actionType")
    target_provider: str = Field(
        validation_alias="targetProvider", serialization_alias="targetProvider"
    )
    target_asset_id: str | None = Field(
        default=None, validation_alias="targetAssetId", serialization_alias="targetAssetId"
    )
    target_asset_type: str | None = Field(
        default=None, validation_alias="targetAssetType", serialization_alias="targetAssetType"
    )
    before_snapshot: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="beforeSnapshot",
        serialization_alias="beforeSnapshot",
    )
    proposed_after: dict[str, Any] = Field(
        default_factory=dict, validation_alias="proposedAfter", serialization_alias="proposedAfter"
    )
    rationale: str | None = None
    risk_label: str = Field(validation_alias="riskLabel", serialization_alias="riskLabel")
    required_capability: str | None = Field(
        default=None,
        validation_alias="requiredCapability",
        serialization_alias="requiredCapability",
    )
    status: str
    approved_by_user_id: str | None = Field(
        default=None, validation_alias="approvedByUserId", serialization_alias="approvedByUserId"
    )
    approved_at: datetime | None = Field(
        default=None, validation_alias="approvedAt", serialization_alias="approvedAt"
    )
    executed_at: datetime | None = Field(
        default=None, validation_alias="executedAt", serialization_alias="executedAt"
    )
    provider_response: dict[str, Any] | None = Field(
        default=None, validation_alias="providerResponse", serialization_alias="providerResponse"
    )
    rollback_hint: dict[str, Any] = Field(
        default_factory=dict, validation_alias="rollbackHint", serialization_alias="rollbackHint"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(validation_alias="createdAt", serialization_alias="createdAt")
    updated_at: datetime = Field(validation_alias="updatedAt", serialization_alias="updatedAt")


class AgentActionProposalApproveRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    notes: str | None = None
