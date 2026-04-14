from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.experiment_spec import ExperimentSpec


def _clean_required_text(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("value must be a non-empty string.")
    return cleaned


class CampaignCreativeContextProviderEnum(str, Enum):
    strategy_v2 = "strategy_v2"
    manual = "manual"
    skills = "skills"


class CampaignCreativeContextProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: CampaignCreativeContextProviderEnum


class ManualAngleEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    angleId: str
    angleName: str
    description: str
    evidence: list[str] = Field(default_factory=list)

    @field_validator("angleId", "angleName", "description")
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        return _clean_required_text(value)


class ManualAnglesDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selectedAngleId: str
    angleLibrary: list[ManualAngleEntry] = Field(min_length=1)

    @field_validator("selectedAngleId")
    @classmethod
    def _validate_selected_angle_id(cls, value: str) -> str:
        return _clean_required_text(value)

    @model_validator(mode="after")
    def _validate_selected_angle_exists(self) -> "ManualAnglesDocument":
        known_angle_ids = {entry.angleId for entry in self.angleLibrary}
        if self.selectedAngleId not in known_angle_ids:
            raise ValueError("selectedAngleId must match one angleLibrary entry.")
        return self


class ManualOfferDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ump: str
    ums: str
    corePromise: str
    valueStackSummary: str
    guaranteeType: str | None = None
    pricingRationale: str
    selectedVariantId: str
    selectedVariantName: str
    offerDetailsMarkdown: str

    @field_validator(
        "ump",
        "ums",
        "corePromise",
        "valueStackSummary",
        "pricingRationale",
        "selectedVariantId",
        "selectedVariantName",
        "offerDetailsMarkdown",
    )
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        return _clean_required_text(value)

    @field_validator("guaranteeType")
    @classmethod
    def _validate_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_required_text(value)


class ManualPromiseContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    loopQuestion: str
    specificPromise: str
    deliveryTest: str
    minimumDelivery: str

    @field_validator("loopQuestion", "specificPromise", "deliveryTest", "minimumDelivery")
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        return _clean_required_text(value)


class ManualCopyDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str
    promiseContract: ManualPromiseContract
    presellMarkdown: str
    salesPageMarkdown: str
    templatePayloads: dict[str, Any] | None = None

    @field_validator("headline", "presellMarkdown", "salesPageMarkdown")
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        return _clean_required_text(value)


class ManualCopyContextDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audienceProductMarkdown: str
    brandVoiceMarkdown: str
    complianceMarkdown: str
    mentalModelsMarkdown: str
    awarenessAngleMatrixMarkdown: str

    @field_validator(
        "audienceProductMarkdown",
        "brandVoiceMarkdown",
        "complianceMarkdown",
        "mentalModelsMarkdown",
        "awarenessAngleMatrixMarkdown",
    )
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        return _clean_required_text(value)


class CampaignManualCreativeContextUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal[1] = 1
    provider: Literal["manual"] = "manual"
    angles: ManualAnglesDocument
    offer: ManualOfferDocument
    copyDocument: ManualCopyDocument
    copyContext: ManualCopyContextDocument
    experimentSpecs: list[ExperimentSpec] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _map_copy_alias(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        if "copy" in value and "copyDocument" not in value:
            cloned = dict(value)
            cloned["copyDocument"] = cloned.pop("copy")
            return cloned
        return value


class CampaignCreativeContextProviderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaignId: str
    provider: CampaignCreativeContextProviderEnum
    creativeContextArtifactId: str | None = None
    checkedAt: str


class CampaignManualCreativeContextUpsertResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaignId: str
    provider: Literal["manual"] = "manual"
    creativeContextArtifactId: str
    experimentSpecArtifactId: str
    artifactIds: dict[str, str]
    uploadedDocKeys: list[str]
    checkedAt: str


class CampaignSkillsCreativeContextMaterializeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaignId: str
    provider: Literal["skills"] = "skills"
    creativeContextArtifactId: str
    artifactIds: dict[str, str]
    sourceArtifactIds: dict[str, str | None]
    strategyBundleId: str
    strategyBundleType: str
    uploadedDocKeys: list[str]
    refreshed: bool
    staleArtifactId: str | None = None
    checkedAt: str


class CampaignCreativeContextReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: CampaignCreativeContextProviderEnum
    ready: bool
    checkedAt: str
    reason: str | None = None
    sourceStrategyV2WorkflowRunId: str | None = None
    sourceStrategyV2TemporalWorkflowId: str | None = None
    launchContextArtifactId: str | None = None
    manualCreativeContextArtifactId: str | None = None
    creativeContextArtifactId: str | None = None
    materializedCreativeContextArtifactId: str | None = None
    materializedArtifactIds: dict[str, str] | None = None
    strategyBundleId: str | None = None
    strategyBundleType: str | None = None
    refreshed: bool = False
    staleArtifactId: str | None = None
    missingArtifacts: list[str] = Field(default_factory=list)
