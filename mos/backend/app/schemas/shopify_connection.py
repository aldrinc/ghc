from __future__ import annotations

from typing import Literal

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
