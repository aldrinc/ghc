"""Pydantic schemas for the Sites API."""

from __future__ import annotations

from typing import Any, Optional
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

    productId is optional in the canonical site runtime.
    """

    clientId: str
    family: str
    name: str
    description: Optional[str] = None
    productId: Optional[str] = None  # Optional for site runtime
    designSystemId: Optional[str] = None


class SitePageUpdateRequest(BaseModel):
    """Request to update a site page."""

    name: Optional[str] = None
    slug: Optional[str] = None
    designSystemId: Optional[str] = None


class SitePageVersionCreateRequest(BaseModel):
    """Request to create a new page version."""

    puckData: dict[str, Any]
    status: str = "draft"
    provenance: Optional[dict[str, Any]] = None


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
    designSystemId: Optional[str] = None
    routeSlug: Optional[str] = None
    primaryDomain: Optional[str] = None
    templateId: Optional[str] = None
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
    designSystemId: Optional[str] = None
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
    siteType: Optional[str] = None
    siteFamily: Optional[str] = None
    commerceProvider: Optional[str] = None
    productId: Optional[str] = None
    designSystemId: Optional[str] = None
    routeSlug: Optional[str] = None
    primaryDomain: Optional[str] = None
    templateId: Optional[str] = None
    entryPageId: Optional[str] = None
    pages: list[SitePageDetail]
    createdAt: str
    updatedAt: str


class SitePageVersionSummary(BaseModel):
    """Summary of a page version."""

    id: str
    status: str
    puckData: dict[str, Any]
    createdAt: str


class SitePageEditorResponse(BaseModel):
    """Response shape for site page editor endpoints.

    Mirrors the funnel page editor API for frontend reuse.
    """

    site: dict[str, Any]
    page: dict[str, Any]
    latestDraft: Optional[dict[str, Any]] = None
    latestApproved: Optional[dict[str, Any]] = None
    designSystemTokens: Optional[dict[str, Any]] = None


class SitePublishResponse(BaseModel):
    """Response from a successful site publish operation."""

    publicationId: str
    artifactId: str
    artifactVersion: int
    siteId: str
    routeSlug: str
    pageCount: int
    funnelCount: int
    productBindingCount: int
    publishedAt: str


class MedusaRuntimeConfig(BaseModel):
    """Runtime Medusa configuration for direct frontend access."""

    baseUrl: Optional[str] = None
    publishableKey: Optional[str] = None
    available: bool = False


class SiteMedusaConfigResponse(BaseModel):
    """Response containing site metadata and optional Medusa runtime config."""

    siteFamily: Optional[str] = None
    commerceProvider: Optional[str] = None
    medusaConfig: Optional[MedusaRuntimeConfig] = None
