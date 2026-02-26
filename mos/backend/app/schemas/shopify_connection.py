from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ShopifyInstallUrlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shopDomain: str = Field(..., min_length=1)


class ShopifyInstallUrlResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    installUrl: str


class ShopifyInstallationUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shopDomain: str = Field(..., min_length=1)
    storefrontAccessToken: str = Field(..., min_length=1)


class ShopifyInstallationDisconnectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shopDomain: str = Field(..., min_length=1)


class ShopifyDefaultShopRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shopDomain: str = Field(..., min_length=1)


class ShopifyConnectionStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal[
        "not_connected",
        "installed_missing_storefront_token",
        "multiple_installations_conflict",
        "ready",
        "error",
    ]
    message: str
    shopDomain: str | None = None
    shopDomains: list[str] = Field(default_factory=list)
    selectedShopDomain: str | None = None
    hasStorefrontAccessToken: bool = False
    missingScopes: list[str] = Field(default_factory=list)


class ShopifyCatalogProductSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    productGid: str
    title: str
    handle: str
    status: str


class ShopifyProductListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shopDomain: str
    products: list[ShopifyCatalogProductSummary] = Field(default_factory=list)


class ShopifyCreateProductVariantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1)
    priceCents: int = Field(..., ge=0)
    currency: str = Field(..., min_length=3, max_length=3)


class ShopifyCreateProductRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1)
    description: str | None = None
    handle: str | None = None
    vendor: str | None = None
    productType: str | None = None
    tags: list[str] = Field(default_factory=list)
    status: Literal["ACTIVE", "DRAFT"] = "DRAFT"
    variants: list[ShopifyCreateProductVariantRequest] = Field(..., min_length=1)
    shopDomain: str | None = None


class ShopifyCreatedVariant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variantGid: str
    title: str
    priceCents: int
    currency: str


class ShopifyProductCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shopDomain: str
    productGid: str
    title: str
    handle: str
    status: str
    variants: list[ShopifyCreatedVariant] = Field(default_factory=list)


class ShopifyThemeBrandSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shopDomain: str | None = None
    designSystemId: str | None = Field(default=None, min_length=1)
    productId: str | None = Field(default=None, min_length=1)
    componentImageAssetMap: dict[str, str] = Field(default_factory=dict)
    themeId: str | None = None
    themeName: str | None = None

    @model_validator(mode="after")
    def validate_theme_selector(self) -> "ShopifyThemeBrandSyncRequest":
        has_theme_id = bool(self.themeId and self.themeId.strip())
        has_theme_name = bool(self.themeName and self.themeName.strip())
        if has_theme_id == has_theme_name:
            raise ValueError("Exactly one of themeId or themeName is required")
        return self


class ShopifyThemeCoverageSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requiredSourceVars: list[str] = Field(default_factory=list)
    requiredThemeVars: list[str] = Field(default_factory=list)
    missingSourceVars: list[str] = Field(default_factory=list)
    missingThemeVars: list[str] = Field(default_factory=list)


class ShopifyThemeSettingsSyncSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    settingsFilename: str | None = None
    expectedPaths: list[str] = Field(default_factory=list)
    updatedPaths: list[str] = Field(default_factory=list)
    missingPaths: list[str] = Field(default_factory=list)
    requiredMissingPaths: list[str] = Field(default_factory=list)
    semanticUpdatedPaths: list[str] = Field(default_factory=list)
    unmappedColorPaths: list[str] = Field(default_factory=list)
    semanticTypographyUpdatedPaths: list[str] = Field(default_factory=list)
    unmappedTypographyPaths: list[str] = Field(default_factory=list)


class ShopifyThemeSettingsAuditSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    settingsFilename: str | None = None
    expectedPaths: list[str] = Field(default_factory=list)
    syncedPaths: list[str] = Field(default_factory=list)
    mismatchedPaths: list[str] = Field(default_factory=list)
    missingPaths: list[str] = Field(default_factory=list)
    requiredMissingPaths: list[str] = Field(default_factory=list)
    requiredMismatchedPaths: list[str] = Field(default_factory=list)
    semanticSyncedPaths: list[str] = Field(default_factory=list)
    semanticMismatchedPaths: list[str] = Field(default_factory=list)
    unmappedColorPaths: list[str] = Field(default_factory=list)
    semanticTypographySyncedPaths: list[str] = Field(default_factory=list)
    semanticTypographyMismatchedPaths: list[str] = Field(default_factory=list)
    unmappedTypographyPaths: list[str] = Field(default_factory=list)


class ShopifyThemeBrandSyncResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shopDomain: str
    workspaceName: str
    designSystemId: str
    designSystemName: str
    brandName: str
    logoAssetPublicId: str
    logoUrl: str
    themeId: str
    themeName: str
    themeRole: str
    layoutFilename: str
    cssFilename: str
    settingsFilename: str | None = None
    jobId: str | None = None
    coverage: ShopifyThemeCoverageSummary
    settingsSync: ShopifyThemeSettingsSyncSummary


class ShopifyThemeBrandSyncJobStartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobId: str
    status: Literal["queued", "running", "succeeded", "failed"]
    statusPath: str


class ShopifyThemeBrandSyncJobProgress(BaseModel):
    model_config = ConfigDict(extra="allow")

    stage: str | None = None
    message: str | None = None
    totalImageSlots: int | None = None
    completedImageSlots: int | None = None
    generatedImageCount: int | None = None
    fallbackImageCount: int | None = None
    skippedImageCount: int | None = None
    totalTextSlots: int | None = None
    componentImageUrlCount: int | None = None
    componentTextValueCount: int | None = None
    currentSlotPath: str | None = None
    currentSlotSource: str | None = None
    updatedAt: str | None = None


class ShopifyThemeBrandSyncJobStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobId: str
    status: Literal["queued", "running", "succeeded", "failed"]
    error: str | None = None
    progress: ShopifyThemeBrandSyncJobProgress | None = None
    result: ShopifyThemeBrandSyncResponse | None = None
    createdAt: datetime
    updatedAt: datetime
    startedAt: datetime | None = None
    finishedAt: datetime | None = None


class ShopifyThemeTemplateBuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draftId: str | None = Field(default=None, min_length=1)
    shopDomain: str | None = None
    designSystemId: str | None = Field(default=None, min_length=1)
    productId: str | None = Field(default=None, min_length=1)
    componentImageAssetMap: dict[str, str] = Field(default_factory=dict)
    componentTextValues: dict[str, str] = Field(default_factory=dict)
    themeId: str | None = None
    themeName: str | None = None

    @model_validator(mode="after")
    def validate_theme_selector(self) -> "ShopifyThemeTemplateBuildRequest":
        has_theme_id = bool(self.themeId and self.themeId.strip())
        has_theme_name = bool(self.themeName and self.themeName.strip())
        if has_theme_id == has_theme_name:
            raise ValueError("Exactly one of themeId or themeName is required")
        return self


class ShopifyThemeTemplateImageSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    key: str
    role: str
    recommendedAspect: str
    currentValue: str | None = None


class ShopifyThemeTemplateTextSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    key: str
    currentValue: str | None = None


class ShopifyThemeTemplateDraftData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shopDomain: str
    workspaceName: str
    designSystemId: str
    designSystemName: str
    brandName: str
    logoAssetPublicId: str
    logoUrl: str
    themeId: str
    themeName: str
    themeRole: str
    cssVars: dict[str, str] = Field(default_factory=dict)
    fontUrls: list[str] = Field(default_factory=list)
    dataTheme: str
    productId: str | None = None
    componentImageAssetMap: dict[str, str] = Field(default_factory=dict)
    componentTextValues: dict[str, str] = Field(default_factory=dict)
    imageSlots: list[ShopifyThemeTemplateImageSlot] = Field(default_factory=list)
    textSlots: list[ShopifyThemeTemplateTextSlot] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ShopifyThemeTemplateDraftVersionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    draftId: str
    versionNumber: int
    source: str
    notes: str | None = None
    createdByUserExternalId: str | None = None
    createdAt: datetime
    data: ShopifyThemeTemplateDraftData


class ShopifyThemeTemplateDraftResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: str
    shopDomain: str
    themeId: str
    themeName: str
    themeRole: str
    designSystemId: str | None = None
    productId: str | None = None
    createdByUserExternalId: str | None = None
    createdAt: datetime
    updatedAt: datetime
    publishedAt: datetime | None = None
    latestVersion: ShopifyThemeTemplateDraftVersionResponse | None = None


class ShopifyThemeTemplateBuildResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft: ShopifyThemeTemplateDraftResponse
    version: ShopifyThemeTemplateDraftVersionResponse


class ShopifyThemeTemplateDraftUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    componentImageAssetMap: dict[str, str] | None = None
    componentTextValues: dict[str, str] | None = None
    notes: str | None = None


class ShopifyThemeTemplateGenerateImagesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draftId: str = Field(..., min_length=1)
    productId: str | None = Field(default=None, min_length=1)


class ShopifyThemeTemplateGenerateImagesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft: ShopifyThemeTemplateDraftResponse
    version: ShopifyThemeTemplateDraftVersionResponse
    generatedImageCount: int
    requestedImageModel: str | None = None
    requestedImageModelSource: str | None = None
    generatedSlotPaths: list[str] = Field(default_factory=list)
    imageModels: list[str] = Field(default_factory=list)
    imageModelBySlotPath: dict[str, str] = Field(default_factory=dict)
    imageSourceBySlotPath: dict[str, str] = Field(default_factory=dict)
    promptTokenCountBySlotPath: dict[str, int] = Field(default_factory=dict)
    promptTokenCountTotal: int = 0
    rateLimitedSlotPaths: list[str] = Field(default_factory=list)
    remainingSlotPaths: list[str] = Field(default_factory=list)
    quotaExhaustedSlotPaths: list[str] = Field(default_factory=list)


class ShopifyThemeTemplateGenerateImagesJobStartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobId: str
    status: Literal["queued", "running", "succeeded", "failed"]
    statusPath: str


class ShopifyThemeTemplateGenerateImagesJobStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobId: str
    status: Literal["queued", "running", "succeeded", "failed"]
    error: str | None = None
    progress: ShopifyThemeBrandSyncJobProgress | None = None
    result: ShopifyThemeTemplateGenerateImagesResponse | None = None
    createdAt: datetime
    updatedAt: datetime
    startedAt: datetime | None = None
    finishedAt: datetime | None = None


class ShopifyThemeTemplateBuildJobStartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobId: str
    status: Literal["queued", "running", "succeeded", "failed"]
    statusPath: str


class ShopifyThemeTemplateBuildJobStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobId: str
    status: Literal["queued", "running", "succeeded", "failed"]
    error: str | None = None
    progress: ShopifyThemeBrandSyncJobProgress | None = None
    result: ShopifyThemeTemplateBuildResponse | None = None
    createdAt: datetime
    updatedAt: datetime
    startedAt: datetime | None = None
    finishedAt: datetime | None = None


class ShopifyThemeTemplatePublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draftId: str = Field(..., min_length=1)


class ShopifyThemeTemplatePublishResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft: ShopifyThemeTemplateDraftResponse
    version: ShopifyThemeTemplateDraftVersionResponse
    sync: ShopifyThemeBrandSyncResponse


class ShopifyThemeTemplatePublishJobStartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobId: str
    status: Literal["queued", "running", "succeeded", "failed"]
    statusPath: str


class ShopifyThemeTemplatePublishJobStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobId: str
    status: Literal["queued", "running", "succeeded", "failed"]
    error: str | None = None
    progress: ShopifyThemeBrandSyncJobProgress | None = None
    result: ShopifyThemeTemplatePublishResponse | None = None
    createdAt: datetime
    updatedAt: datetime
    startedAt: datetime | None = None
    finishedAt: datetime | None = None


class ShopifyThemeBrandAuditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shopDomain: str | None = None
    designSystemId: str | None = Field(default=None, min_length=1)
    themeId: str | None = None
    themeName: str | None = None

    @model_validator(mode="after")
    def validate_theme_selector(self) -> "ShopifyThemeBrandAuditRequest":
        has_theme_id = bool(self.themeId and self.themeId.strip())
        has_theme_name = bool(self.themeName and self.themeName.strip())
        if has_theme_id == has_theme_name:
            raise ValueError("Exactly one of themeId or themeName is required")
        return self


class ShopifyThemeBrandAuditResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shopDomain: str
    workspaceName: str
    designSystemId: str
    designSystemName: str
    themeId: str
    themeName: str
    themeRole: str
    layoutFilename: str
    cssFilename: str
    settingsFilename: str | None = None
    hasManagedMarkerBlock: bool
    layoutIncludesManagedCssAsset: bool
    managedCssAssetExists: bool
    coverage: ShopifyThemeCoverageSummary
    settingsAudit: ShopifyThemeSettingsAuditSummary
    isReady: bool


class ShopifySyncProductVariantsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shopDomain: str | None = None


class ShopifyCatalogVariant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variantGid: str
    title: str
    priceCents: int
    currency: str
    compareAtPriceCents: int | None = None
    sku: str | None = None
    barcode: str | None = None
    taxable: bool
    requiresShipping: bool
    inventoryPolicy: str | None = None
    inventoryManagement: str | None = None
    inventoryQuantity: int | None = None
    optionValues: dict[str, str] = Field(default_factory=dict)


class ShopifyProductVariantSyncResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shopDomain: str
    productGid: str
    createdCount: int = Field(..., ge=0)
    updatedCount: int = Field(..., ge=0)
    totalFetched: int = Field(..., ge=0)
    variants: list[ShopifyCatalogVariant] = Field(default_factory=list)
