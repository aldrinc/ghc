from __future__ import annotations

from datetime import datetime
from typing import Any

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


class UpdateInstallationRequest(BaseModel):
    clientId: str | None = None
    storefrontAccessToken: str | None = None


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
