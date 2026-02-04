from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class DesignSystemCreateRequest(BaseModel):
    name: str
    tokens: dict[str, Any] = Field(default_factory=dict)
    clientId: Optional[str] = None


class DesignSystemUpdateRequest(BaseModel):
    name: Optional[str] = None
    tokens: Optional[dict[str, Any]] = None
    clientId: Optional[str] = None
