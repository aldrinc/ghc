from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CheckoutLine(BaseModel):
    merchandiseId: str = Field(min_length=1)
    quantity: int = Field(ge=1)


class CheckoutBuyerIdentity(BaseModel):
    email: str | None = None
    countryCode: str | None = Field(default=None, min_length=2, max_length=2)
    phone: str | None = None


class CreateCheckoutRequest(BaseModel):
    clientId: str | None = None
    shopDomain: str | None = None
    lines: list[CheckoutLine] = Field(min_length=1)
    discountCodes: list[str] = Field(default_factory=list)
    attributes: dict[str, str] = Field(default_factory=dict)
    note: str | None = None
    buyerIdentity: CheckoutBuyerIdentity | None = None
    context: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_target(self) -> "CreateCheckoutRequest":
        has_client = bool(self.clientId)
        has_shop = bool(self.shopDomain)
        if has_client == has_shop:
            raise ValueError("Exactly one of clientId or shopDomain is required")
        return self


class CreateCheckoutResponse(BaseModel):
    shopDomain: str
    cartId: str
    checkoutUrl: str


class VerifyProductRequest(BaseModel):
    clientId: str | None = None
    shopDomain: str | None = None
    productGid: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_target(self) -> "VerifyProductRequest":
        has_client = bool(self.clientId)
        has_shop = bool(self.shopDomain)
        if has_client == has_shop:
            raise ValueError("Exactly one of clientId or shopDomain is required")
        return self


class VerifyProductResponse(BaseModel):
    shopDomain: str
    productGid: str
    handle: str
    title: str


class ListProductsRequest(BaseModel):
    clientId: str | None = None
    shopDomain: str | None = None
    query: str | None = None
    limit: int = Field(default=20, ge=1, le=50)

    @model_validator(mode="after")
    def validate_target(self) -> "ListProductsRequest":
        has_client = bool(self.clientId)
        has_shop = bool(self.shopDomain)
        if has_client == has_shop:
            raise ValueError("Exactly one of clientId or shopDomain is required")
        return self


class CatalogProductSummary(BaseModel):
    productGid: str
    title: str
    handle: str
    status: str


class ListProductsResponse(BaseModel):
    shopDomain: str
    products: list[CatalogProductSummary]


class GetProductRequest(BaseModel):
    clientId: str | None = None
    shopDomain: str | None = None
    productGid: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_target(self) -> "GetProductRequest":
        has_client = bool(self.clientId)
        has_shop = bool(self.shopDomain)
        if has_client == has_shop:
            raise ValueError("Exactly one of clientId or shopDomain is required")
        return self


class CatalogProductVariant(BaseModel):
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


class GetProductResponse(BaseModel):
    shopDomain: str
    productGid: str
    title: str
    handle: str
    status: str
    variants: list[CatalogProductVariant]


class CreateCatalogProductVariantRequest(BaseModel):
    title: str = Field(min_length=1)
    priceCents: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)


class CreateCatalogProductRequest(BaseModel):
    clientId: str | None = None
    shopDomain: str | None = None
    title: str = Field(min_length=1)
    description: str | None = None
    handle: str | None = None
    vendor: str | None = None
    productType: str | None = None
    tags: list[str] = Field(default_factory=list)
    status: Literal["ACTIVE", "DRAFT"] = "DRAFT"
    variants: list[CreateCatalogProductVariantRequest] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_target(self) -> "CreateCatalogProductRequest":
        has_client = bool(self.clientId)
        has_shop = bool(self.shopDomain)
        if has_client == has_shop:
            raise ValueError("Exactly one of clientId or shopDomain is required")
        return self


class CreatedCatalogVariant(BaseModel):
    variantGid: str
    title: str
    priceCents: int
    currency: str


class CreateCatalogProductResponse(BaseModel):
    shopDomain: str
    productGid: str
    title: str
    handle: str
    status: str
    variants: list[CreatedCatalogVariant]


class UpdateCatalogVariantRequest(BaseModel):
    clientId: str | None = None
    shopDomain: str | None = None
    variantGid: str = Field(min_length=1)
    title: str | None = None
    priceCents: int | None = Field(default=None, ge=0)
    compareAtPriceCents: int | None = Field(default=None, ge=0)
    sku: str | None = None
    barcode: str | None = None
    inventoryPolicy: str | None = None
    inventoryManagement: str | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "UpdateCatalogVariantRequest":
        has_client = bool(self.clientId)
        has_shop = bool(self.shopDomain)
        if has_client == has_shop:
            raise ValueError("Exactly one of clientId or shopDomain is required")

        fields_set = self.model_fields_set
        if not any(
            name in fields_set
            for name in {
                "title",
                "priceCents",
                "compareAtPriceCents",
                "sku",
                "barcode",
                "inventoryPolicy",
                "inventoryManagement",
            }
        ):
            raise ValueError("At least one variant update field is required")
        return self


class UpdateCatalogVariantResponse(BaseModel):
    shopDomain: str
    productGid: str
    variantGid: str


class UpsertPolicyPageRequest(BaseModel):
    pageKey: str = Field(min_length=1)
    title: str = Field(min_length=1)
    handle: str = Field(min_length=1, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    bodyHtml: str = Field(min_length=1)


class UpsertPolicyPagesRequest(BaseModel):
    clientId: str | None = None
    shopDomain: str | None = None
    pages: list[UpsertPolicyPageRequest] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_target(self) -> "UpsertPolicyPagesRequest":
        has_client = bool(self.clientId)
        has_shop = bool(self.shopDomain)
        if has_client == has_shop:
            raise ValueError("Exactly one of clientId or shopDomain is required")
        return self


class UpsertedPolicyPage(BaseModel):
    pageKey: str
    pageId: str
    title: str
    handle: str
    url: str
    operation: Literal["created", "updated"]


class UpsertPolicyPagesResponse(BaseModel):
    shopDomain: str
    pages: list[UpsertedPolicyPage]


class SyncThemeBrandRequest(BaseModel):
    clientId: str | None = None
    shopDomain: str | None = None
    workspaceName: str = Field(min_length=1)
    brandName: str = Field(min_length=1)
    logoUrl: str = Field(min_length=1)
    cssVars: dict[str, str] = Field(default_factory=dict, min_length=1)
    fontUrls: list[str] = Field(default_factory=list)
    componentImageUrls: dict[str, str] = Field(default_factory=dict)
    componentTextValues: dict[str, str] = Field(default_factory=dict)
    autoComponentImageUrls: list[str] = Field(default_factory=list)
    dataTheme: str | None = None
    themeId: str | None = None
    themeName: str | None = None

    @model_validator(mode="after")
    def validate_target(self) -> "SyncThemeBrandRequest":
        has_client = bool(self.clientId)
        has_shop = bool(self.shopDomain)
        if has_client == has_shop:
            raise ValueError("Exactly one of clientId or shopDomain is required")
        has_theme_id = bool(self.themeId and self.themeId.strip())
        has_theme_name = bool(self.themeName and self.themeName.strip())
        if has_theme_id == has_theme_name:
            raise ValueError("Exactly one of themeId or themeName is required")
        return self


class ThemeBrandCoverageSummary(BaseModel):
    requiredSourceVars: list[str] = Field(default_factory=list)
    requiredThemeVars: list[str] = Field(default_factory=list)
    missingSourceVars: list[str] = Field(default_factory=list)
    missingThemeVars: list[str] = Field(default_factory=list)


class ThemeBrandSettingsSyncSummary(BaseModel):
    settingsFilename: str | None = None
    expectedPaths: list[str] = Field(default_factory=list)
    updatedPaths: list[str] = Field(default_factory=list)
    missingPaths: list[str] = Field(default_factory=list)
    requiredMissingPaths: list[str] = Field(default_factory=list)
    semanticUpdatedPaths: list[str] = Field(default_factory=list)
    unmappedColorPaths: list[str] = Field(default_factory=list)
    semanticTypographyUpdatedPaths: list[str] = Field(default_factory=list)
    unmappedTypographyPaths: list[str] = Field(default_factory=list)


class ThemeBrandSettingsAuditSummary(BaseModel):
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


class SyncThemeBrandResponse(BaseModel):
    shopDomain: str
    themeId: str
    themeName: str
    themeRole: str
    layoutFilename: str
    cssFilename: str
    settingsFilename: str | None = None
    jobId: str | None = None
    coverage: ThemeBrandCoverageSummary
    settingsSync: ThemeBrandSettingsSyncSummary


class ListThemeBrandTemplateSlotsRequest(BaseModel):
    clientId: str | None = None
    shopDomain: str | None = None
    themeId: str | None = None
    themeName: str | None = None

    @model_validator(mode="after")
    def validate_target(self) -> "ListThemeBrandTemplateSlotsRequest":
        has_client = bool(self.clientId)
        has_shop = bool(self.shopDomain)
        if has_client == has_shop:
            raise ValueError("Exactly one of clientId or shopDomain is required")
        has_theme_id = bool(self.themeId and self.themeId.strip())
        has_theme_name = bool(self.themeName and self.themeName.strip())
        if has_theme_id == has_theme_name:
            raise ValueError("Exactly one of themeId or themeName is required")
        return self


class ThemeTemplateImageSlot(BaseModel):
    path: str
    key: str
    currentValue: str | None = None
    role: str
    recommendedAspect: Literal["landscape", "portrait", "square", "any"]


class ThemeTemplateTextSlot(BaseModel):
    path: str
    key: str
    currentValue: str | None = None
    role: str
    maxLength: int


class ListThemeBrandTemplateSlotsResponse(BaseModel):
    shopDomain: str
    themeId: str
    themeName: str
    themeRole: str
    imageSlots: list[ThemeTemplateImageSlot] = Field(default_factory=list)
    textSlots: list[ThemeTemplateTextSlot] = Field(default_factory=list)


class AuditThemeBrandRequest(BaseModel):
    clientId: str | None = None
    shopDomain: str | None = None
    workspaceName: str = Field(min_length=1)
    cssVars: dict[str, str] = Field(default_factory=dict, min_length=1)
    dataTheme: str | None = None
    themeId: str | None = None
    themeName: str | None = None

    @model_validator(mode="after")
    def validate_target(self) -> "AuditThemeBrandRequest":
        has_client = bool(self.clientId)
        has_shop = bool(self.shopDomain)
        if has_client == has_shop:
            raise ValueError("Exactly one of clientId or shopDomain is required")
        has_theme_id = bool(self.themeId and self.themeId.strip())
        has_theme_name = bool(self.themeName and self.themeName.strip())
        if has_theme_id == has_theme_name:
            raise ValueError("Exactly one of themeId or themeName is required")
        return self


class AuditThemeBrandResponse(BaseModel):
    shopDomain: str
    themeId: str
    themeName: str
    themeRole: str
    layoutFilename: str
    cssFilename: str
    settingsFilename: str | None = None
    hasManagedMarkerBlock: bool
    layoutIncludesManagedCssAsset: bool
    managedCssAssetExists: bool
    coverage: ThemeBrandCoverageSummary
    settingsAudit: ThemeBrandSettingsAuditSummary
    isReady: bool


class UpdateInstallationRequest(BaseModel):
    clientId: str | None = None
    storefrontAccessToken: str | None = None


class AutoProvisionStorefrontTokenRequest(BaseModel):
    clientId: str | None = None


class InstallationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    shopDomain: str
    clientId: str | None
    hasStorefrontAccessToken: bool
    scopes: list[str]
    installedAt: datetime
    updatedAt: datetime
    uninstalledAt: datetime | None


class ForwardOrderPayload(BaseModel):
    shopDomain: str
    orderId: str
    orderName: str | None = None
    currency: str | None = None
    totalPrice: str | None = None
    createdAt: str | None = None
    noteAttributes: dict[str, str] = Field(default_factory=dict)
    lineItems: list[dict[str, Any]] = Field(default_factory=list)
