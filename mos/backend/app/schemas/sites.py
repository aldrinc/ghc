"""Pydantic schemas for the Sites API."""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class SiteFamilySummary(BaseModel):
    """Summary of a site family."""

    family: str
    name: str
    description: str
    siteType: str
    commerceProvider: str
    pageCount: int


class SitePageBlueprintSummary(BaseModel):
    """Summary of a page blueprint within a site family."""

    pageType: str
    templateId: str
    name: str
    slug: str
    description: Optional[str] = None
    ordering: int
    isEntry: bool = False


class SiteFamilyDetail(BaseModel):
    """Detailed information about a site family."""

    family: str
    name: str
    description: str
    siteType: str
    commerceProvider: str
    pageBlueprints: list[SitePageBlueprintSummary]
    provenanceNotes: list[str]


class SiteCreateRequest(BaseModel):
    """Request to create a new site from a family blueprint.

    productId is required because the existing funnel runtime requires funnels
    to have a product_id for publication and public rendering.
    """

    clientId: str
    family: str
    name: str
    description: Optional[str] = None
    productId: str  # Required for publication
    designSystemId: Optional[str] = None


class SiteSummary(BaseModel):
    """Summary of a site."""

    id: str
    clientId: str
    name: str
    description: Optional[str] = None
    status: str
    siteType: Optional[str] = None
    siteFamily: Optional[str] = None
    commerceProvider: Optional[str] = None
    productId: Optional[str] = None
    createdAt: str
    updatedAt: str


class SitePageDetail(BaseModel):
    """Detail of a page within a site."""

    id: str
    name: str
    slug: str
    pageType: Optional[str] = None
    templateId: Optional[str] = None
    ordering: int
    isEntry: bool = False
    latestDraftVersionId: Optional[str] = None
    latestApprovedVersionId: Optional[str] = None


class SiteDetail(BaseModel):
    """Detailed information about a site."""

    id: str
    clientId: str
    name: str
    description: Optional[str] = None
    status: str
    experienceKind: Optional[str] = None
    siteType: Optional[str] = None
    siteFamily: Optional[str] = None
    commerceProvider: Optional[str] = None
    productId: Optional[str] = None
    entryPageId: Optional[str] = None
    pages: list[SitePageDetail]
    createdAt: str
    updatedAt: str
