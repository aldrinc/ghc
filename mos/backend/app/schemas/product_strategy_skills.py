from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.services.skills_runtime_registry import DEFAULT_SKILL_BUNDLE_KEY


class StrategySkillsBootstrapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    releaseVersion: str = Field(min_length=1)
    strategyRoot: str = Field(min_length=1)
    foundationalRoot: str = Field(min_length=1)
    bundleKey: str = Field(default=DEFAULT_SKILL_BUNDLE_KEY, min_length=1)
    bundleFamily: str = Field(default="ember", min_length=1)
    sourceRevision: str | None = None
    sourceRef: str | None = None


class StrategySkillsStageRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundleKey: str = Field(default=DEFAULT_SKILL_BUNDLE_KEY, min_length=1)
    promoteToActiveBundle: bool = False


class StrategySkillsSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selectedId: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class StrategySkillsApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(min_length=1)


class StrategySkillsActivationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundleId: str = Field(min_length=1)


class StrategySkillsFoundationalApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowIncomplete: bool = False


class StrategySkillsStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clientId: str
    productId: str
    bundleKey: str
    skillsBinding: dict[str, Any] | None = None
    activeFoundationalBundle: dict[str, Any] | None = None
    activeWorkingBundle: dict[str, Any] | None = None
    activeHandoffBundle: dict[str, Any] | None = None
    pendingHandoffBundles: list[dict[str, Any]] = Field(default_factory=list)
    historicalHandoffBundles: list[dict[str, Any]] = Field(default_factory=list)
    foundationalCompleteness: dict[str, Any] | None = None


class StrategySkillsBootstrapResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clientId: str
    productId: str
    release: dict[str, Any]
    binding: dict[str, Any]
    foundationalBundle: dict[str, Any]
    workingBundle: dict[str, Any] | None = None
    handoffBundle: dict[str, Any] | None = None


class StrategySkillsStageRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clientId: str
    productId: str
    result: dict[str, Any]


class StrategySkillsSelectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clientId: str
    productId: str
    result: dict[str, Any]


class StrategySkillsApprovalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clientId: str
    productId: str
    result: dict[str, Any]


class StrategySkillsActivationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clientId: str
    productId: str
    result: dict[str, Any]


class StrategySkillsFoundationalApprovalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clientId: str
    productId: str
    result: dict[str, Any]
