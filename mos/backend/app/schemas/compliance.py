from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

BusinessModelLiteral = Literal[
    "ecommerce",
    "saas_subscription",
    "digital_product",
    "online_service",
    "lead_generation",
]

ComplianceClassificationLiteral = Literal[
    "required",
    "strongly_recommended",
    "not_applicable",
]


class ComplianceRulesetSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    effectiveDate: str
    description: str
    sourceCount: int
    ruleCount: int


class ComplianceRulesetSourceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sourceId: str
    platform: str
    title: str
    url: str
    lastUpdated: str | None = None


class ComplianceRuleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ruleId: str
    platform: str
    classification: Literal["required", "strongly_recommended"]
    summary: str
    appliesToModels: list[BusinessModelLiteral] = Field(default_factory=list)
    pageKeys: list[str] = Field(default_factory=list)
    sourceIds: list[str] = Field(default_factory=list)


class ComplianceRulesetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    effectiveDate: str
    description: str
    sources: list[ComplianceRulesetSourceResponse] = Field(default_factory=list)
    rules: list[ComplianceRuleResponse] = Field(default_factory=list)


class ClientComplianceProfileUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rulesetVersion: str = Field(..., min_length=1)
    businessModels: list[BusinessModelLiteral] = Field(..., min_length=1)

    legalBusinessName: str | None = None
    operatingEntityName: str | None = None
    companyAddressText: str | None = None
    businessLicenseIdentifier: str | None = None

    supportEmail: str | None = None
    supportPhone: str | None = None
    supportHoursText: str | None = None
    responseTimeCommitment: str | None = None

    privacyPolicyUrl: str | None = None
    termsOfServiceUrl: str | None = None
    returnsRefundsPolicyUrl: str | None = None
    shippingPolicyUrl: str | None = None
    contactSupportUrl: str | None = None
    companyInformationUrl: str | None = None
    subscriptionTermsAndCancellationUrl: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)


class ClientComplianceProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    orgId: str
    clientId: str
    rulesetVersion: str
    businessModels: list[BusinessModelLiteral] = Field(default_factory=list)

    legalBusinessName: str | None = None
    operatingEntityName: str | None = None
    companyAddressText: str | None = None
    businessLicenseIdentifier: str | None = None

    supportEmail: str | None = None
    supportPhone: str | None = None
    supportHoursText: str | None = None
    responseTimeCommitment: str | None = None

    privacyPolicyUrl: str | None = None
    termsOfServiceUrl: str | None = None
    returnsRefundsPolicyUrl: str | None = None
    shippingPolicyUrl: str | None = None
    contactSupportUrl: str | None = None
    companyInformationUrl: str | None = None
    subscriptionTermsAndCancellationUrl: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)

    createdAt: str
    updatedAt: str


class CompliancePageRequirementResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pageKey: str
    title: str
    classification: ComplianceClassificationLiteral
    configured: bool
    configuredUrl: str | None = None
    profileUrlField: str
    triggeredRuleIds: list[str] = Field(default_factory=list)


class ClientComplianceRequirementsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rulesetVersion: str
    businessModels: list[BusinessModelLiteral] = Field(default_factory=list)
    pages: list[CompliancePageRequirementResponse] = Field(default_factory=list)
    missingRequiredPageKeys: list[str] = Field(default_factory=list)
    missingRecommendedPageKeys: list[str] = Field(default_factory=list)


class ComplianceShopifyPolicySyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shopDomain: str | None = None
    pageKeys: list[str] = Field(default_factory=list)
    includeStronglyRecommended: bool = True


class ComplianceShopifyPolicySyncPageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pageKey: str
    title: str
    handle: str
    pageId: str
    url: str
    operation: Literal["created", "updated"]
    profileUrlField: str


class ComplianceShopifyPolicySyncResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rulesetVersion: str
    shopDomain: str
    pages: list[ComplianceShopifyPolicySyncPageResponse] = Field(default_factory=list)
    updatedProfileUrls: dict[str, str] = Field(default_factory=dict)


class CompliancePolicyTemplateSectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sectionKey: str
    title: str


class CompliancePolicyTemplateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pageKey: str
    title: str
    templateVersion: str
    description: str
    requiredSections: list[CompliancePolicyTemplateSectionResponse] = Field(default_factory=list)
    placeholders: list[str] = Field(default_factory=list)
    templateMarkdown: str
