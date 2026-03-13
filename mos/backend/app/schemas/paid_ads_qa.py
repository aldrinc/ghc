from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PaidAdsPlatformLiteral = Literal["meta", "tiktok"]
PaidAdsSeverityLiteral = Literal["blocker", "high", "medium", "low"]
PaidAdsFindingStatusLiteral = Literal["failed", "needs_manual_review"]
PaidAdsRunStatusLiteral = Literal["passed", "failed", "needs_manual_review"]


class PaidAdsRulesetSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    effectiveDate: str
    description: str
    sourceCount: int
    ruleCount: int


class PaidAdsRulesetSourceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sourceId: str
    platform: PaidAdsPlatformLiteral
    sourceKind: Literal["official_policy", "operator_requirement"]
    title: str
    url: str | None = None
    lastUpdated: str | None = None
    regionScope: str | None = None
    needsVerification: bool = False


class PaidAdsRuleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ruleId: str
    ruleType: Literal["policy", "operational_readiness"]
    platform: PaidAdsPlatformLiteral
    domain: Literal["copy", "assets", "landing_page", "admin_legal", "account_setup", "campaign"]
    severity: PaidAdsSeverityLiteral
    requirement: str
    policyAnchorQuote: str | None = None
    automated: bool
    manualReviewRequired: bool = False
    sourceId: str
    sourceNeedsVerification: bool = False
    appliesToObjects: list[str] = Field(default_factory=list)
    fixGuidance: list[str] = Field(default_factory=list)
    commonFailureExamples: list[str] = Field(default_factory=list)


class PaidAdsRulesetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    effectiveDate: str
    description: str
    sources: list[PaidAdsRulesetSourceResponse] = Field(default_factory=list)
    rules: list[PaidAdsRuleResponse] = Field(default_factory=list)


class PaidAdsPlatformProfileUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rulesetVersion: str
    businessManagerId: str | None = None
    businessManagerName: str | None = None
    pageId: str | None = None
    pageName: str | None = None
    adAccountId: str | None = None
    adAccountName: str | None = None
    paymentMethodType: str | None = None
    paymentMethodStatus: str | None = None
    pixelId: str | None = None
    dataSetId: str | None = None
    dataSetShopifyPartnerInstalled: bool | None = None
    dataSetDataSharingLevel: str | None = None
    dataSetAssignedToAdAccount: bool | None = None
    verifiedDomain: str | None = None
    verifiedDomainStatus: str | None = None
    attributionClickWindow: str | None = None
    attributionViewWindow: str | None = None
    viewThroughEnabled: bool | None = None
    trackingProvider: str | None = None
    trackingUrlParameters: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PaidAdsPlatformProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    orgId: str
    clientId: str
    platform: PaidAdsPlatformLiteral
    rulesetVersion: str
    businessManagerId: str | None = None
    businessManagerName: str | None = None
    pageId: str | None = None
    pageName: str | None = None
    adAccountId: str | None = None
    adAccountName: str | None = None
    paymentMethodType: str | None = None
    paymentMethodStatus: str | None = None
    pixelId: str | None = None
    dataSetId: str | None = None
    dataSetShopifyPartnerInstalled: bool | None = None
    dataSetDataSharingLevel: str | None = None
    dataSetAssignedToAdAccount: bool | None = None
    verifiedDomain: str | None = None
    verifiedDomainStatus: str | None = None
    attributionClickWindow: str | None = None
    attributionViewWindow: str | None = None
    viewThroughEnabled: bool | None = None
    trackingProvider: str | None = None
    trackingUrlParameters: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    createdAt: str
    updatedAt: str


class PaidAdsQaRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: PaidAdsPlatformLiteral = "meta"
    rulesetVersion: str
    reviewBaseUrl: str | None = None
    generationKey: str | None = None
    funnelId: str | None = None

    @field_validator("funnelId")
    @classmethod
    def _validate_funnel_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("funnelId must be a non-empty string when provided.")
        return value.strip()


class PaidAdsQaFindingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    ruleId: str
    ruleType: Literal["policy", "operational_readiness"]
    platform: PaidAdsPlatformLiteral
    severity: PaidAdsSeverityLiteral
    status: PaidAdsFindingStatusLiteral
    title: str
    message: str
    artifactType: str
    artifactRef: str | None = None
    fixGuidance: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    needsVerification: bool = False
    sourceId: str
    sourceTitle: str
    sourceUrl: str | None = None
    policyAnchorQuote: str | None = None
    createdAt: str


class PaidAdsQaRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    orgId: str
    clientId: str
    campaignId: str | None = None
    platform: PaidAdsPlatformLiteral
    subjectType: str
    subjectId: str
    rulesetVersion: str
    status: PaidAdsRunStatusLiteral
    blockerCount: int
    highCount: int
    mediumCount: int
    lowCount: int
    needsManualReviewCount: int
    checkedRuleIds: list[str] = Field(default_factory=list)
    reportFilePath: str | None = None
    reportMarkdown: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    findings: list[PaidAdsQaFindingResponse] = Field(default_factory=list)
    createdAt: str
    completedAt: str | None = None
