from __future__ import annotations

from typing import Any, Optional

from datetime import datetime

from pydantic import BaseModel


class ProductCreateRequest(BaseModel):
    clientId: str
    title: str
    description: Optional[str] = None
    handle: Optional[str] = None
    vendor: Optional[str] = None
    productType: Optional[str] = None
    tags: Optional[list[str]] = None
    templateSuffix: Optional[str] = None
    publishedAt: Optional[datetime] = None
    primaryBenefits: Optional[list[str]] = None
    featureBullets: Optional[list[str]] = None
    guaranteeText: Optional[str] = None
    disclaimers: Optional[list[str]] = None


class ProductUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    handle: Optional[str] = None
    vendor: Optional[str] = None
    productType: Optional[str] = None
    tags: Optional[list[str]] = None
    templateSuffix: Optional[str] = None
    publishedAt: Optional[datetime] = None
    primaryBenefits: Optional[list[str]] = None
    featureBullets: Optional[list[str]] = None
    guaranteeText: Optional[str] = None
    disclaimers: Optional[list[str]] = None
    primaryAssetId: Optional[str] = None


class ProductOfferCreateRequest(BaseModel):
    productId: str
    name: str
    description: Optional[str] = None
    businessModel: str
    differentiationBullets: Optional[list[str]] = None
    guaranteeText: Optional[str] = None
    optionsSchema: Optional[dict[str, Any]] = None


class ProductOfferUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    businessModel: Optional[str] = None
    differentiationBullets: Optional[list[str]] = None
    guaranteeText: Optional[str] = None
    optionsSchema: Optional[dict[str, Any]] = None


class ProductOfferPricePointCreateRequest(BaseModel):
    offerId: str
    label: str
    amountCents: int
    currency: str
    provider: Optional[str] = None
    externalPriceId: Optional[str] = None
    optionValues: Optional[dict[str, Any]] = None


class ProductOfferPricePointUpdateRequest(BaseModel):
    label: Optional[str] = None
    amountCents: Optional[int] = None
    currency: Optional[str] = None
    provider: Optional[str] = None
    externalPriceId: Optional[str] = None
    optionValues: Optional[dict[str, Any]] = None


class ProductVariantCreateRequest(BaseModel):
    title: str
    price: int
    currency: str
    compareAtPrice: Optional[int] = None
    provider: Optional[str] = None
    externalPriceId: Optional[str] = None
    optionValues: Optional[dict[str, Any]] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    requiresShipping: Optional[bool] = None
    taxable: Optional[bool] = None
    weight: Optional[float] = None
    weightUnit: Optional[str] = None
    inventoryQuantity: Optional[int] = None
    inventoryPolicy: Optional[str] = None
    inventoryManagement: Optional[str] = None
    incoming: Optional[bool] = None
    nextIncomingDate: Optional[datetime] = None
    unitPrice: Optional[int] = None
    unitPriceMeasurement: Optional[dict[str, Any]] = None
    quantityRule: Optional[dict[str, Any]] = None
    quantityPriceBreaks: Optional[list[dict[str, Any]]] = None


class ProductVariantUpdateRequest(BaseModel):
    title: Optional[str] = None
    price: Optional[int] = None
    currency: Optional[str] = None
    compareAtPrice: Optional[int] = None
    provider: Optional[str] = None
    externalPriceId: Optional[str] = None
    optionValues: Optional[dict[str, Any]] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    requiresShipping: Optional[bool] = None
    taxable: Optional[bool] = None
    weight: Optional[float] = None
    weightUnit: Optional[str] = None
    inventoryQuantity: Optional[int] = None
    inventoryPolicy: Optional[str] = None
    inventoryManagement: Optional[str] = None
    incoming: Optional[bool] = None
    nextIncomingDate: Optional[datetime] = None
    unitPrice: Optional[int] = None
    unitPriceMeasurement: Optional[dict[str, Any]] = None
    quantityRule: Optional[dict[str, Any]] = None
    quantityPriceBreaks: Optional[list[dict[str, Any]]] = None
