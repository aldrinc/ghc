from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class ProductCreateRequest(BaseModel):
    clientId: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    primaryBenefits: Optional[list[str]] = None
    featureBullets: Optional[list[str]] = None
    guaranteeText: Optional[str] = None
    disclaimers: Optional[list[str]] = None


class ProductUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
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
