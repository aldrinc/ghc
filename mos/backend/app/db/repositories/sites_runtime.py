from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db.models import (
    Site,
    SiteLink,
    SitePage,
    SitePageVersion,
    SiteTemplate,
    SiteFunnel,
    SiteFunnelStep,
)


class SitesRuntimeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _slugify(value: str) -> str:
        text = (value or "").strip().lower()
        text = re.sub(r"[^a-z0-9]+", "-", text)
        text = re.sub(r"-{2,}", "-", text).strip("-")
        return text or "site"

    def _generate_unique_route_slug(
        self, *, desired_slug: str, exclude_site_id: str | None = None
    ) -> str:
        """Generate a unique route slug for a site."""
        base = self._slugify(desired_slug)
        suffix = 0
        while True:
            slug = base if suffix == 0 else f"{base}-{suffix}"
            stmt = select(Site.id).where(Site.route_slug == slug)
            if exclude_site_id:
                stmt = stmt.where(Site.id != exclude_site_id)
            exists = self.session.execute(stmt).first()
            if not exists:
                return slug
            suffix += 1

    def create_site(
        self,
        *,
        org_id: str,
        client_id: str,
        site_import_id: str | None = None,
        site_template_id: str | None = None,
        design_system_id: str | None = None,
        product_id: str | None = None,
        name: str,
        description: str | None = None,
        site_type: str | None = None,
        site_family: str | None = None,
        commerce_provider: str | None = None,
        route_slug: str | None = None,
        primary_domain: str | None = None,
        source_hostname: str | None = None,
        entry_page_type: str | None = None,
        entry_page_id: str | None = None,
        imported_page_count: int = 0,
        completeness_state: str = "partial",
        created_by_user_external_id: str | None = None,
    ) -> Site:
        now = datetime.now(timezone.utc)
        site = Site(
            org_id=org_id,
            client_id=client_id,
            site_import_id=site_import_id,
            site_template_id=site_template_id,
            design_system_id=design_system_id,
            product_id=product_id,
            name=name,
            description=description,
            status="draft",
            route_slug=route_slug,
            primary_domain=primary_domain,
            site_type=site_type,
            site_family=site_family,
            commerce_provider=commerce_provider,
            entry_page_id=entry_page_id,
            source_hostname=source_hostname,
            entry_page_type=entry_page_type,
            imported_page_count=imported_page_count,
            completeness_state=completeness_state,
            created_by_user_external_id=created_by_user_external_id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(site)
        self.session.flush()
        self.session.refresh(site)
        return site

    def update_site(self, *, site: Site) -> Site:
        """Update an existing site."""
        site.updated_at = datetime.now(timezone.utc)
        self.session.add(site)
        self.session.flush()
        self.session.refresh(site)
        return site

    def create_page(
        self,
        *,
        site_id: str,
        name: str,
        slug: str,
        page_type: str | None = None,
        page_role: str | None = None,
        template_id: str | None = None,
        page_template_id: str | None = None,
        ordering: int = 0,
        status: str = "draft",
        is_system_page: bool = False,
        design_system_id: str | None = None,
        source_url: str | None = None,
        source_screenshot_refs: list[str] | None = None,
        generated_code: str | None = None,
        adapted_puck_data: dict[str, Any] | None = None,
        outbound_links: list[dict[str, Any]] | None = None,
    ) -> SitePage:
        now = datetime.now(timezone.utc)
        page = SitePage(
            site_id=site_id,
            name=name,
            slug=slug,
            page_type=page_type,
            page_role=page_role,
            template_id=template_id,
            page_template_id=page_template_id,
            ordering=ordering,
            status=status,
            is_system_page=is_system_page,
            design_system_id=design_system_id,
            source_url=source_url,
            source_screenshot_refs=source_screenshot_refs or [],
            generated_code=generated_code,
            adapted_puck_data=adapted_puck_data or {},
            outbound_links=outbound_links or [],
            created_at=now,
            updated_at=now,
        )
        self.session.add(page)
        self.session.flush()
        self.session.refresh(page)
        return page

    def update_page(self, *, page: SitePage) -> SitePage:
        """Update an existing page."""
        page.updated_at = datetime.now(timezone.utc)
        self.session.add(page)
        self.session.flush()
        self.session.refresh(page)
        return page

    def create_page_version(
        self,
        *,
        page_id: str,
        puck_data: dict[str, Any],
        provenance: dict[str, Any] | None = None,
        status: str = "draft",
        source_type: str | None = None,
        source_id: str | None = None,
        ai_metadata: dict[str, Any] | None = None,
        diff_summary: str | None = None,
    ) -> SitePageVersion:
        now = datetime.now(timezone.utc)
        version = SitePageVersion(
            page_id=page_id,
            status=status,
            puck_data=puck_data,
            provenance=provenance or {},
            source_type=source_type,
            source_id=source_id,
            ai_metadata=ai_metadata,
            diff_summary=diff_summary,
            created_at=now,
            updated_at=now,
        )
        self.session.add(version)
        self.session.flush()
        self.session.refresh(version)
        return version

    def create_link(
        self,
        *,
        site_id: str,
        from_page_id: str | None = None,
        to_page_id: str | None = None,
        from_page_type: str | None = None,
        to_page_type: str | None = None,
        label: str | None = None,
        link_kind: str = "internal",
        meta: dict[str, Any] | None = None,
    ) -> SiteLink:
        link = SiteLink(
            site_id=site_id,
            from_page_id=from_page_id,
            to_page_id=to_page_id,
            from_page_type=from_page_type,
            to_page_type=to_page_type,
            label=label,
            link_kind=link_kind,
            meta=meta or {},
        )
        self.session.add(link)
        self.session.flush()
        self.session.refresh(link)
        return link

    def list_sites(self, *, org_id: str, client_id: str) -> list[Site]:
        stmt = (
            select(Site)
            .where(Site.org_id == org_id, Site.client_id == client_id)
            .order_by(Site.created_at.desc())
        )
        return list(self.session.scalars(stmt).all())

    def get_site(self, *, org_id: str, client_id: str, site_id: str) -> Site | None:
        stmt = select(Site).where(
            Site.id == site_id, Site.org_id == org_id, Site.client_id == client_id
        )
        return self.session.scalars(stmt).first()

    def get_site_by_id(self, *, org_id: str, site_id: str) -> Site | None:
        """Get a site by ID within an org (no client_id check)."""
        stmt = select(Site).where(Site.id == site_id, Site.org_id == org_id)
        return self.session.scalars(stmt).first()

    def get_site_by_route_slug(self, *, route_slug: str) -> Site | None:
        stmt = select(Site).where(Site.route_slug == route_slug)
        return self.session.scalars(stmt).first()

    def list_pages(self, *, site_id: str) -> list[SitePage]:
        stmt = select(SitePage).where(SitePage.site_id == site_id).order_by(SitePage.ordering.asc())
        return list(self.session.scalars(stmt).all())

    def get_page(self, *, site_id: str, page_id: str) -> SitePage | None:
        stmt = select(SitePage).where(SitePage.id == page_id, SitePage.site_id == site_id)
        return self.session.scalars(stmt).first()

    def get_page_by_slug(self, *, site_id: str, slug: str) -> SitePage | None:
        stmt = select(SitePage).where(SitePage.site_id == site_id, SitePage.slug == slug)
        return self.session.scalars(stmt).first()

    def latest_version_for_page(
        self, *, page_id: str, status: str | None = None
    ) -> SitePageVersion | None:
        stmt = select(SitePageVersion).where(SitePageVersion.page_id == page_id)
        if status:
            stmt = stmt.where(SitePageVersion.status == status)
        stmt = stmt.order_by(SitePageVersion.created_at.desc())
        return self.session.scalars(stmt).first()

    def list_versions_for_page(self, *, page_id: str) -> list[SitePageVersion]:
        stmt = (
            select(SitePageVersion)
            .where(SitePageVersion.page_id == page_id)
            .order_by(SitePageVersion.created_at.desc())
        )
        return list(self.session.scalars(stmt).all())

    def get_version(self, *, version_id: str) -> SitePageVersion | None:
        stmt = select(SitePageVersion).where(SitePageVersion.id == version_id)
        return self.session.scalars(stmt).first()

    def list_links(self, *, site_id: str) -> list[SiteLink]:
        stmt = select(SiteLink).where(SiteLink.site_id == site_id)
        return list(self.session.scalars(stmt).all())

    def check_slug_unique(
        self, *, site_id: str, slug: str, exclude_page_id: str | None = None
    ) -> bool:
        """Check if a slug is unique within a site."""
        stmt = select(SitePage.id).where(
            SitePage.site_id == site_id,
            SitePage.slug == slug,
        )
        if exclude_page_id:
            stmt = stmt.where(SitePage.id != exclude_page_id)
        return self.session.execute(stmt).first() is None
