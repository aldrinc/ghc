"""Pydantic schemas for Site Templates API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel


class SiteTemplatePageSummary(BaseModel):
    """Summary of a page within a site template."""

    id: str
    pageType: str
    name: str
    slug: str
    description: Optional[str] = None
    pageTemplateId: Optional[str] = None
    ordering: int
    isEntry: bool = False


class SiteTemplateLinkSummary(BaseModel):
    """Summary of a link within a site template."""

    id: str
    fromPageType: Optional[str] = None
    toPageType: Optional[str] = None
    label: Optional[str] = None
    linkKind: str = "internal"


class SiteTemplateFunnelStepSummary(BaseModel):
    """Summary of a funnel step within a site template."""

    id: str
    pageType: str
    ordering: int
    stepRole: Optional[str] = None
    ctaLabel: Optional[str] = None


class SiteTemplateFunnelSummary(BaseModel):
    """Summary of a funnel within a site template."""

    id: str
    name: str
    description: Optional[str] = None
    funnelType: str = "checkout"
    entryPageType: Optional[str] = None
    steps: list[SiteTemplateFunnelStepSummary] = []


class SiteTemplateSummary(BaseModel):
    """Summary of a site template."""

    id: str
    family: str
    name: str
    description: Optional[str] = None
    siteType: str
    commerceProvider: str
    themeRequirement: Optional[Literal["optional", "required"]] = None
    isSystemTemplate: bool = False
    pageCount: int = 0
    funnelCount: int = 0
    createdAt: datetime


class SiteTemplateDetail(BaseModel):
    """Detail of a site template with all sub-objects."""

    id: str
    family: str
    name: str
    description: Optional[str] = None
    siteType: str
    commerceProvider: str
    themeRequirement: Optional[Literal["optional", "required"]] = None
    isSystemTemplate: bool = False
    provenanceNotes: list[str] = []
    pages: list[SiteTemplatePageSummary] = []
    links: list[SiteTemplateLinkSummary] = []
    funnels: list[SiteTemplateFunnelSummary] = []
    createdAt: datetime


class SiteTemplateCreateRequest(BaseModel):
    """Request to create a new site template."""

    family: str
    name: str
    description: Optional[str] = None
    siteType: str
    commerceProvider: str


class SiteTemplateInstantiateRequest(BaseModel):
    """Request to instantiate a site template into a new site."""

    clientId: str
    name: str
    description: Optional[str] = None
    productId: Optional[str] = None
    themeBindingMode: Optional[str] = None  # standalone, workspace_default, design_system
    designSystemId: Optional[str] = None
    primaryDomain: Optional[str] = None


class SiteTemplateInstantiateResponse(BaseModel):
    """Response after instantiating a site template."""

    siteId: str
    siteName: str
    pageCount: int
    funnelCount: int
    entryPageId: Optional[str] = None
    createdAt: datetime
