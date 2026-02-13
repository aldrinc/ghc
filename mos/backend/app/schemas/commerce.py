from __future__ import annotations

from typing import Any, Optional

from pydantic import AnyUrl, BaseModel


class PublicCheckoutRequest(BaseModel):
    publicId: str
    variantId: Optional[str] = None
    selection: dict[str, Any]
    quantity: int
    successUrl: AnyUrl
    cancelUrl: AnyUrl
    pageId: Optional[str] = None
    visitorId: Optional[str] = None
    sessionId: Optional[str] = None
    utm: Optional[dict[str, Any]] = None
