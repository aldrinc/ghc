"""Pydantic schemas for Site Product Bindings API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class SiteProductBindingSummary(BaseModel):
    """Summary of a site product binding."""

    id: str
    siteId: str
    productId: str
    sitePageId: Optional[str] = None
    siteFunnelId: Optional[str] = None
    pageRole: str
    variantIds: list[str] = []
    bindingContext: dict[str, Any] = {}
    priority: int = 0
    active: bool = True
    createdAt: datetime
    updatedAt: datetime


class SiteProductBindingDetail(BaseModel):
    """Detail of a site product binding."""

    id: str
    siteId: str
    productId: str
    sitePageId: Optional[str] = None
    siteFunnelId: Optional[str] = None
    pageRole: str
    variantIds: list[str] = []
    bindingContext: dict[str, Any] = {}
    priority: int = 0
    active: bool = True
    site: Optional[dict[str, Any]] = None
    page: Optional[dict[str, Any]] = None
    funnel: Optional[dict[str, Any]] = None
    createdAt: datetime
    updatedAt: datetime


class SiteProductBindingCreateRequest(BaseModel):
    """Request to create a site product binding."""

    productId: str
    sitePageId: Optional[str] = None
    pageRole: str
    siteFunnelId: Optional[str] = None
    priority: int = 0
    active: bool = True
    variantIds: list[str] = []
    bindingContext: dict[str, Any] = {}


class SiteProductBindingUpdateRequest(BaseModel):
    """Request to update a site product binding."""

    sitePageId: Optional[str] = None
    pageRole: Optional[str] = None
    siteFunnelId: Optional[str] = None
    priority: Optional[int] = None
    active: Optional[bool] = None
    variantIds: Optional[list[str]] = None
    bindingContext: Optional[dict[str, Any]] = None
