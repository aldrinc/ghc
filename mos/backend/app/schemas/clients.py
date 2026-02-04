from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ClientUpdateRequest(BaseModel):
    name: Optional[str] = None
    industry: Optional[str] = None
    designSystemId: Optional[str] = None


class ClientDeleteRequest(BaseModel):
    confirm: bool
    confirm_name: str
