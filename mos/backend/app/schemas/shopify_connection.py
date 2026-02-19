from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
