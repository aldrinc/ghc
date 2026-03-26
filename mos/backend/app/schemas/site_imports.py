"""Pydantic schemas for canonical Site Imports API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class SiteImportSummary(BaseModel):
    """Summary of a site import."""

    id: str
    sourceUrl: str
    sourceHostname: Optional[str] = None
    pageTypeHint: Optional[str] = None
    siteFamilyHint: Optional[str] = None
    status: str
    title: Optional[str] = None
    suggestedTemplateFamily: Optional[str] = None
    savedSiteId: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime


class SiteImportApplicationSummary(BaseModel):
    """Summary of a site import application (audit trail)."""

    id: str
    siteImportId: str
    action: str
    status: str
    siteId: Optional[str] = None
    siteTemplateId: Optional[str] = None
    templateVariantId: Optional[str] = None
    errorDetail: Optional[str] = None
    createdByUserExternalId: Optional[str] = None
    createdAt: datetime


class SiteImportCreateRequest(BaseModel):
    """Request to create a site import."""

    sourceUrl: str
    pageTypeHint: Optional[str] = None
    siteFamilyHint: Optional[str] = None


class SiteImportCreateSiteRequest(BaseModel):
    """Request to create a site from a completed import."""

    siteName: str
    description: Optional[str] = None


class SiteImportAddPagesRequest(BaseModel):
    """Request to add pages from a completed import to an existing site."""

    siteId: str


class SiteImportCreateSiteTemplateRequest(BaseModel):
    """Request to create a site template from a completed import."""

    name: str
    family: str
    description: Optional[str] = None


class SiteImportCreatePageTemplateRequest(BaseModel):
    """Request to create a page template variant from a completed import."""

    name: str
    family: str
    pageType: str
    acceptedSectionIds: list[str]
    reviewNotes: Optional[str] = None


class SiteImportApplyRequest(BaseModel):
    """Generic apply request used by the site-first import workflow."""

    action: str
    siteTemplateId: Optional[str] = None
    targetSiteId: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    family: Optional[str] = None
    pageType: Optional[str] = None
    acceptedSectionIds: list[str] = []
    reviewNotes: Optional[str] = None


class SiteImportCreateSiteResponse(BaseModel):
    """Response after creating a site from import."""

    siteId: str
    siteName: str
    pageCount: int
    entryPageType: Optional[str] = None
    createdPages: list[dict[str, Any]] = []
    createdAt: datetime


class SiteImportAddPagesResponse(BaseModel):
    """Response after adding pages from import to existing site."""

    siteId: str
    pageCount: int
    createdPages: list[dict[str, Any]] = []


class SiteImportCreateSiteTemplateResponse(BaseModel):
    """Response after creating a site template from import."""

    siteTemplateId: str
    name: str
    family: str
    pageCount: int
    funnelCount: int
    createdAt: datetime


class SiteImportCreatePageTemplateResponse(BaseModel):
    """Response after creating a page template variant from import."""

    variantId: str
    stylePresetId: Optional[str] = None
    name: str
    family: str
    pageType: str
    createdAt: datetime


class SiteImportSnapshotResponse(BaseModel):
    """Response containing the import snapshot."""

    id: str
    htmlSnapshot: str
    desktopScreenshotDataUrl: str
    mobileScreenshotDataUrl: str
    captureMetadata: dict[str, Any] = {}
    createdAt: datetime


class SiteImportApplyResponse(BaseModel):
    """Generic apply response for site import actions."""

    applicationId: str
    siteId: Optional[str] = None
    siteTemplateId: Optional[str] = None
    pageTemplateId: Optional[str] = None
