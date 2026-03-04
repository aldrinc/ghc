from __future__ import annotations

from typing import Literal
from typing import Any

from pydantic import BaseModel, Field


class ShopifyWebhookLineItem(BaseModel):
    id: str | int | None = None
    variantId: str | int | None = None
    quantity: int | None = None
    sku: str | None = None
    title: str | None = None


class ShopifyOrderWebhookPayload(BaseModel):
    shopDomain: str
    orderId: str
    orderName: str | None = None
    currency: str | None = None
    totalPrice: str | None = None
    createdAt: str | None = None
    noteAttributes: dict[str, str] = Field(default_factory=dict)
    lineItems: list[ShopifyWebhookLineItem] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class ShopifyComplianceWebhookPayload(BaseModel):
    topic: Literal["customers/data_request", "customers/redact", "shop/redact"]
    shopDomain: str = Field(min_length=1)
    eventId: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
