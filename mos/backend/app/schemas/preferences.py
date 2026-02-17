from __future__ import annotations

from pydantic import BaseModel, Field


class ActiveProductUpdateRequest(BaseModel):
    product_id: str = Field(..., min_length=1)

