"""Pydantic models for Medusa connection API requests and responses."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MedusaConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseUrl: str = Field(..., min_length=1)
    adminApiKey: str | None = None
    publishableKey: str | None = None


class MedusaConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    baseUrl: str | None = None
    hasAdminApiKey: bool = False
    hasPublishableKey: bool = False
    connectionStatus: str = "not_configured"
    lastConnectionCheckAt: datetime | None = None
    lastConnectionError: str | None = None
    createdAt: datetime | None = None
    updatedAt: datetime | None = None


class MedusaConnectionStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal[
        "not_configured",
        "not_tested",
        "connected",
        "error",
    ]
    message: str
    baseUrl: str | None = None
    lastCheckAt: datetime | None = None


class MedusaVariantCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1)
    price: int = Field(..., ge=0, description="Price in cents")
    currency: str = Field(..., min_length=3, max_length=3, description="3-letter ISO currency code")
    compareAtPrice: int | None = Field(None, ge=0, description="Compare-at price in cents")
    inventoryQuantity: int | None = Field(None, ge=0)
    inventoryPolicy: Literal["deny", "continue"] | None = None
    optionValues: dict[str, str] | None = None
    sku: str | None = None
    barcode: str | None = None


class MedusaVariantCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variantId: str
    medusaVariantId: str
    medusaProductId: str
    title: str
    priceCents: int
    currency: str
    compareAtPriceCents: int | None = None
    sku: str | None = None
    barcode: str | None = None
    inventoryQuantity: int | None = None
    inventoryPolicy: str | None = None
    optionValues: dict[str, str] | None = None
