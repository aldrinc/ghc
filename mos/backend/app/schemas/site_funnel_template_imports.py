"""Pydantic schemas for site funnel HTML template imports."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SiteFunnelTemplateImportSummary(BaseModel):
    """Summary of a stored HTML template import for a site funnel."""

    id: str
    siteId: str
    sourceLabel: str
    htmlLength: int
    htmlSha256: str
    createdByUserExternalId: str | None = None
    createdAt: datetime
    updatedAt: datetime


class SiteFunnelTemplateImportDetail(SiteFunnelTemplateImportSummary):
    """Detailed HTML template import payload."""

    htmlSnapshot: str


class SiteFunnelTemplateImportCreateRequest(BaseModel):
    """Create a new site funnel HTML template import."""

    sourceLabel: str = Field(min_length=1, max_length=255)
    htmlDocument: str = Field(min_length=1, max_length=500_000)
