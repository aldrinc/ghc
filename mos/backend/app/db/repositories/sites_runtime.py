from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Site, SiteLink, SitePage, SitePageVersion


class SitesRuntimeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_site(
        self,
        *,
        org_id: str,
        client_id: str,
        site_import_id: str | None,
        product_id: str | None,
        name: str,
        description: str | None,
        site_type: str | None,
        site_family: str | None,
        commerce_provider: str | None,
        source_hostname: str | None,
        entry_page_type: str | None,
        imported_page_count: int,
        completeness_state: str,
        created_by_user_external_id: str | None,
    ) -> Site:
        now = datetime.now(timezone.utc)
        site = Site(
            org_id=org_id,
            client_id=client_id,
            site_import_id=site_import_id,
            product_id=product_id,
            name=name,
            description=description,
            status="draft",
            site_type=site_type,
            site_family=site_family,
            commerce_provider=commerce_provider,
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

    def create_page(
        self,
        *,
        site_id: str,
        name: str,
        slug: str,
        page_type: str | None,
        template_id: str | None,
        ordering: int,
        source_url: str | None,
        source_screenshot_refs: list[str],
        generated_code: str | None,
        adapted_puck_data: dict[str, Any],
        outbound_links: list[dict[str, Any]],
    ) -> SitePage:
        now = datetime.now(timezone.utc)
        page = SitePage(
            site_id=site_id,
            name=name,
            slug=slug,
            page_type=page_type,
            template_id=template_id,
            ordering=ordering,
            source_url=source_url,
            source_screenshot_refs=source_screenshot_refs,
            generated_code=generated_code,
            adapted_puck_data=adapted_puck_data,
            outbound_links=outbound_links,
            created_at=now,
            updated_at=now,
        )
        self.session.add(page)
        self.session.flush()
        self.session.refresh(page)
        return page

    def create_page_version(
        self,
        *,
        page_id: str,
        puck_data: dict[str, Any],
        provenance: dict[str, Any],
        status: str = "draft",
    ) -> SitePageVersion:
        now = datetime.now(timezone.utc)
        version = SitePageVersion(
            page_id=page_id,
            status=status,
            puck_data=puck_data,
            provenance=provenance,
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
        from_page_id: str | None,
        to_page_id: str | None,
        from_page_type: str | None,
        to_page_type: str | None,
        label: str | None,
        link_kind: str,
        meta: dict[str, Any],
    ) -> SiteLink:
        link = SiteLink(
            site_id=site_id,
            from_page_id=from_page_id,
            to_page_id=to_page_id,
            from_page_type=from_page_type,
            to_page_type=to_page_type,
            label=label,
            link_kind=link_kind,
            meta=meta,
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

    def list_pages(self, *, site_id: str) -> list[SitePage]:
        stmt = select(SitePage).where(SitePage.site_id == site_id).order_by(SitePage.ordering.asc())
        return list(self.session.scalars(stmt).all())

    def latest_version_for_page(
        self, *, page_id: str, status: str = "draft"
    ) -> SitePageVersion | None:
        stmt = (
            select(SitePageVersion)
            .where(SitePageVersion.page_id == page_id, SitePageVersion.status == status)
            .order_by(SitePageVersion.created_at.desc())
        )
        return self.session.scalars(stmt).first()

    def list_links(self, *, site_id: str) -> list[SiteLink]:
        stmt = select(SiteLink).where(SiteLink.site_id == site_id)
        return list(self.session.scalars(stmt).all())
