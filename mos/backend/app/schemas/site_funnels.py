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
    createdAt: datetime


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
    templateImportId: Optional[str] = None
    templateImportLabel: Optional[str] = None
    pageIntent: Optional[str] = None
    campaignId: Optional[str] = None
    selectedAngleId: Optional[str] = None
    preparedPageId: Optional[str] = None
    preparedPageSlug: Optional[str] = None
    latestPreparedVersionId: Optional[str] = None
    preparationReadiness: dict[str, Any] = Field(default_factory=dict)
    preparedAt: Optional[datetime] = None
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
    templateImportId: Optional[str] = None
    templateImportLabel: Optional[str] = None
    pageIntent: Optional[str] = None
    campaignId: Optional[str] = None
    selectedAngleId: Optional[str] = None
    preparedPageId: Optional[str] = None
    preparedPageSlug: Optional[str] = None
    latestPreparedVersionId: Optional[str] = None
    preparationReadiness: dict[str, Any] = Field(default_factory=dict)
    preparedAt: Optional[datetime] = None
    trackingConfig: Optional[dict[str, Any]] = None
    steps: list[SiteFunnelStepSummary] = Field(default_factory=list)
    createdAt: datetime
    updatedAt: datetime


class SiteFunnelStepCreateRequest(BaseModel):
    """Request to create a funnel step."""

    sitePageId: str
    ordering: int = 0
    stepRole: Optional[str] = None
    ctaLabel: Optional[str] = None
    transitionRule: Optional[dict[str, Any]] = None


class SiteFunnelCreateRequest(BaseModel):
    """Request to create a site funnel."""

    name: str
    description: Optional[str] = None
    funnelType: str = "checkout"
    entryPageId: Optional[str] = None
    productId: Optional[str] = None
    selectedOfferId: Optional[str] = None
    templateImportId: Optional[str] = None
    pageIntent: Optional[str] = None
    campaignId: Optional[str] = None
    selectedAngleId: Optional[str] = None
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
    templateImportId: Optional[str] = None
    pageIntent: Optional[str] = None
    campaignId: Optional[str] = None
    selectedAngleId: Optional[str] = None
    trackingConfig: Optional[dict[str, Any]] = None
