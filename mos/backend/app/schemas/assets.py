from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class AssetUpdateRequest(BaseModel):
    assetKind: Optional[str] = None
    tags: Optional[list[str]] = None
    productId: Optional[str] = None
    funnelId: Optional[str] = None
    alt: Optional[str] = None
