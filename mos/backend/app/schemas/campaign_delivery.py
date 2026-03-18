from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.enums import CampaignDeliveryModeEnum, CampaignDeliveryValidationStatusEnum


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


class CampaignDeliveryUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deliveryMode: CampaignDeliveryModeEnum
    preSalesUrl: str | None = None
    salesUrl: str | None = None
    checkoutUrl: str | None = None
    thankYouUrl: str | None = None

    @field_validator("preSalesUrl", "salesUrl", "checkoutUrl", "thankYouUrl")
    @classmethod
    def _validate_urls(cls, value: str | None) -> str | None:
        return _clean_optional_text(value)


class CampaignDeliveryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    campaignId: str
    clientId: str
    deliveryMode: CampaignDeliveryModeEnum
    preSalesUrl: str | None = None
    salesUrl: str | None = None
    checkoutUrl: str | None = None
    thankYouUrl: str | None = None
    validationStatus: CampaignDeliveryValidationStatusEnum
    validationError: str | None = None
    validatedAt: str | None = None
    createdAt: str
    updatedAt: str


class CampaignDeliveryValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: Literal["preSalesUrl", "salesUrl", "checkoutUrl", "thankYouUrl"]
    url: str
    finalUrl: str | None = None
    statusCode: int | None = None
    passed: bool
    checks: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class CampaignDeliveryValidationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkedAt: str
    validationStatus: CampaignDeliveryValidationStatusEnum
    validationError: str | None = None
    results: list[CampaignDeliveryValidationResult] = Field(default_factory=list)
    delivery: CampaignDeliveryResponse


class CampaignLaunchContextReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ready: bool
    checkedAt: str
    reason: str | None = None
    sourceStrategyV2WorkflowRunId: str | None = None
    sourceStrategyV2TemporalWorkflowId: str | None = None
    launchContextArtifactId: str | None = None
    refreshed: bool = False
    staleArtifactId: str | None = None
