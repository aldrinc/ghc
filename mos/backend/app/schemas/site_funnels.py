"""Pydantic schemas for Site Funnels API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class SiteFunnelStepSummary(BaseModel):
    """Summary of a funnel step."""

    id: str
    sitePageId: str
    ordering: int
    stepRole: Optional[str] = None
    ctaLabel: Optional[str] = None
    transitionRule: Optional[dict[str, Any]] = None
    page: Optional[dict[str, Any]] = None
    options: list["SiteFunnelStepOptionSummary"] = Field(default_factory=list)
    createdAt: datetime


class SiteFunnelStepOptionSummary(BaseModel):
    """A page option that can satisfy a funnel step."""

    id: str
    siteFunnelStepId: str
    sitePageId: str
    optionKey: str
    label: str
    status: str
    trafficWeight: int | None = None
    isControl: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    page: Optional[dict[str, Any]] = None
    createdAt: datetime
    updatedAt: datetime


class SiteFunnelPathStepSummary(BaseModel):
    """A resolved step inside an internal funnel path."""

    id: str
    siteFunnelPathId: str
    siteFunnelStepId: str
    siteFunnelStepOptionId: str
    sitePageId: str
    ordering: int
    stepRole: Optional[str] = None
    page: Optional[dict[str, Any]] = None
    option: Optional[dict[str, Any]] = None
    createdAt: datetime


class SiteFunnelPathSummary(BaseModel):
    """Internal page combination owned by a funnel."""

    id: str
    siteFunnelId: str
    campaignId: Optional[str] = None
    name: str
    slug: str
    status: str
    trafficWeight: int | None = None
    isControl: bool = False
    experimentSpecId: Optional[str] = None
    variantId: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    steps: list[SiteFunnelPathStepSummary] = Field(default_factory=list)
    createdAt: datetime
    updatedAt: datetime


class SiteFunnelSummary(BaseModel):
    """Summary of a site funnel."""

    id: str
    siteId: str
    name: str
    description: Optional[str] = None
    status: str
    funnelType: str = "checkout"
    entryPageId: Optional[str] = None
    productId: Optional[str] = None
    selectedOfferId: Optional[str] = None
    trackingConfig: Optional[dict[str, Any]] = None
    siteName: Optional[str] = None
    stepCount: int = 0
    createdAt: datetime
    updatedAt: datetime


class SiteFunnelDetail(BaseModel):
    """Detail of a site funnel with steps."""

    id: str
    siteId: str
    name: str
    description: Optional[str] = None
    status: str
    funnelType: str = "checkout"
    entryPageId: Optional[str] = None
    productId: Optional[str] = None
    selectedOfferId: Optional[str] = None
    trackingConfig: Optional[dict[str, Any]] = None
    steps: list[SiteFunnelStepSummary] = Field(default_factory=list)
    paths: list[SiteFunnelPathSummary] = Field(default_factory=list)
    createdAt: datetime
    updatedAt: datetime


class SiteFunnelStepCreateRequest(BaseModel):
    """Request to create a funnel step."""

    sitePageId: str
    ordering: int = 0
    stepRole: Optional[str] = None
    ctaLabel: Optional[str] = None
    transitionRule: Optional[dict[str, Any]] = None


class SiteFunnelStepOptionCreateRequest(BaseModel):
    """Request to add a page option to a funnel step."""

    sitePageId: str
    optionKey: str
    label: str
    status: str = "draft"
    trafficWeight: int | None = None
    isControl: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class SiteFunnelPathStepCreateRequest(BaseModel):
    """Request row for one page selected inside a path."""

    siteFunnelStepId: str
    sitePageId: str


class SiteFunnelPathCreateRequest(BaseModel):
    """Request to create an internal page path for a site funnel."""

    name: str
    slug: str
    status: str = "draft"
    campaignId: Optional[str] = None
    trafficWeight: int | None = None
    isControl: bool = False
    experimentSpecId: Optional[str] = None
    variantId: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    steps: list[SiteFunnelPathStepCreateRequest]


class SiteFunnelCreateRequest(BaseModel):
    """Request to create a site funnel."""

    name: str
    description: Optional[str] = None
    funnelType: str = "checkout"
    entryPageId: Optional[str] = None
    productId: Optional[str] = None
    selectedOfferId: Optional[str] = None
    trackingConfig: Optional[dict[str, Any]] = None
    steps: list[SiteFunnelStepCreateRequest] = Field(default_factory=list)


class SiteFunnelUpdateRequest(BaseModel):
    """Request to update a site funnel."""

    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    funnelType: Optional[str] = None
    entryPageId: Optional[str] = None
    productId: Optional[str] = None
    selectedOfferId: Optional[str] = None
    trackingConfig: Optional[dict[str, Any]] = None
