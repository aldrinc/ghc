"""Service for managing site templates.

This service handles:
- Listing and retrieving site templates
- Seeding built-in site blueprints as system templates
- Instantiating templates into actual sites
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Site,
    SitePage,
    SitePageVersion,
    SiteLink,
    SiteTemplate,
    SiteTemplatePage,
    SiteTemplateLink,
    SiteTemplateFunnel,
    SiteTemplateFunnelStep,
    SiteFunnel,
    SiteFunnelStep,
)
from app.db.repositories.sites_runtime import SitesRuntimeRepository
from app.services.site_blueprints import (
    SiteFamilyDescriptor,
    SitePageBlueprint,
    list_site_families,
    get_site_family,
)


class SiteTemplateError(Exception):
    """Error during site template operations."""

    pass


def seed_system_templates(session: Session) -> list[SiteTemplate]:
    """Seed built-in site blueprints as system site templates.

    This function ensures that all built-in site families from site_blueprints
    are persisted as system templates in the database.
    """
    families = list_site_families()
    created_templates = []

    for family_descriptor in families:
        # Check if template already exists
        existing = session.scalars(
            select(SiteTemplate).where(
                SiteTemplate.family == family_descriptor.family,
                SiteTemplate.is_system_template == True,  # noqa: E712
            )
        ).first()

        if existing:
            continue

        # Create the template
        template = SiteTemplate(
            id=str(uuid4()),
            family=family_descriptor.family,
            name=family_descriptor.name,
            description=family_descriptor.description,
            site_type=family_descriptor.site_type,
            commerce_provider=family_descriptor.commerce_provider,
            is_system_template=True,
            provenance_notes=list(family_descriptor.provenance_notes),
            created_at=datetime.now(timezone.utc),
        )
        session.add(template)

        # Create page blueprints
        for blueprint in family_descriptor.page_blueprints:
            page = SiteTemplatePage(
                id=str(uuid4()),
                site_template_id=template.id,
                page_type=blueprint.page_type,
                name=blueprint.name,
                slug=blueprint.slug,
                description=blueprint.description,
                page_template_id=blueprint.template_id,
                ordering=blueprint.ordering,
                is_entry=blueprint.is_entry,
                provenance_notes=[],
                created_at=datetime.now(timezone.utc),
            )
            session.add(page)

        created_templates.append(template)

    if created_templates:
        session.commit()
        for template in created_templates:
            session.refresh(template)

    return created_templates


def list_templates(session: Session) -> list[SiteTemplate]:
    """List all site templates (both system and user-created)."""
    stmt = select(SiteTemplate).order_by(SiteTemplate.created_at.desc())
    return list(session.scalars(stmt).all())


def get_template(session: Session, template_id: str) -> SiteTemplate | None:
    """Get a site template by ID."""
    return session.scalars(select(SiteTemplate).where(SiteTemplate.id == template_id)).first()


def get_template_by_family(session: Session, family: str) -> SiteTemplate | None:
    """Get a site template by family name."""
    return session.scalars(select(SiteTemplate).where(SiteTemplate.family == family)).first()


def get_template_pages(session: Session, template_id: str) -> list[SiteTemplatePage]:
    """Get all pages for a site template."""
    stmt = (
        select(SiteTemplatePage)
        .where(SiteTemplatePage.site_template_id == template_id)
        .order_by(SiteTemplatePage.ordering)
    )
    return list(session.scalars(stmt).all())


def get_template_links(session: Session, template_id: str) -> list[SiteTemplateLink]:
    """Get all links for a site template."""
    stmt = select(SiteTemplateLink).where(SiteTemplateLink.site_template_id == template_id)
    return list(session.scalars(stmt).all())


def get_template_funnels(session: Session, template_id: str) -> list[SiteTemplateFunnel]:
    """Get all funnels for a site template."""
    stmt = select(SiteTemplateFunnel).where(SiteTemplateFunnel.site_template_id == template_id)
    return list(session.scalars(stmt).all())


def get_template_funnel_steps(
    session: Session, template_funnel_id: str
) -> list[SiteTemplateFunnelStep]:
    """Get all steps for a site template funnel."""
    stmt = (
        select(SiteTemplateFunnelStep)
        .where(SiteTemplateFunnelStep.site_template_funnel_id == template_funnel_id)
        .order_by(SiteTemplateFunnelStep.ordering)
    )
    return list(session.scalars(stmt).all())


def instantiate_template(
    session: Session,
    *,
    template_id: str,
    org_id: str,
    client_id: str,
    name: str,
    description: str | None = None,
    product_id: str | None = None,
    design_system_id: str | None = None,
    primary_domain: str | None = None,
    created_by_user_external_id: str | None = None,
) -> dict[str, Any]:
    """Instantiate a site template into a new site.

    This creates a site from a template, including all pages.
    """
    template = get_template(session, template_id)
    if not template:
        raise SiteTemplateError(f"Template not found: {template_id}")

    if getattr(template, "status", "active") == "deprecated":
        raise SiteTemplateError(f"Template is deprecated: {template_id}")

    sites_repo = SitesRuntimeRepository(session)

    # Generate unique route slug
    route_slug = sites_repo._generate_unique_route_slug(desired_slug=name)

    # Create the site
    site = sites_repo.create_site(
        org_id=org_id,
        client_id=client_id,
        site_template_id=template_id,
        design_system_id=design_system_id,
        product_id=product_id,
        name=name,
        description=description or template.description,
        site_type=template.site_type,
        site_family=template.family,
        commerce_provider=template.commerce_provider,
        route_slug=route_slug,
        primary_domain=primary_domain,
        created_by_user_external_id=created_by_user_external_id,
    )

    # Create pages from template pages
    template_pages = get_template_pages(session, template_id)
    page_type_to_id: dict[str, str] = {}
    created_pages: list[dict[str, Any]] = []
    entry_page_id = None

    for tpage in template_pages:
        page = sites_repo.create_page(
            site_id=str(site.id),
            name=tpage.name,
            slug=tpage.slug,
            page_type=tpage.page_type,
            page_role=tpage.page_type,
            page_template_id=tpage.page_template_id,
            ordering=tpage.ordering,
            design_system_id=design_system_id,
        )

        # Create initial draft version
        version = sites_repo.create_page_version(
            page_id=str(page.id),
            puck_data={},
            provenance={
                "source_type": "template",
                "template_id": template_id,
                "page_template_id": tpage.page_template_id,
            },
            status="draft",
            source_type="site_template",
            source_id=template_id,
        )
        approved_version = sites_repo.create_page_version(
            page_id=str(page.id),
            puck_data={},
            provenance={
                "source_type": "template",
                "template_id": template_id,
                "page_template_id": tpage.page_template_id,
            },
            status="approved",
            source_type="site_template",
            source_id=template_id,
        )

        page_type_to_id[tpage.page_type] = str(page.id)
        created_pages.append(
            {
                "pageId": str(page.id),
                "pageType": tpage.page_type,
                "templateId": tpage.page_template_id,
                "versionId": str(version.id),
                "approvedVersionId": str(approved_version.id),
            }
        )

        if tpage.is_entry:
            entry_page_id = str(page.id)

    # Create links from template links
    template_links = get_template_links(session, template_id)
    for tlink in template_links:
        sites_repo.create_link(
            site_id=str(site.id),
            from_page_id=page_type_to_id.get(tlink.from_page_type)
            if tlink.from_page_type
            else None,
            to_page_id=page_type_to_id.get(tlink.to_page_type) if tlink.to_page_type else None,
            from_page_type=tlink.from_page_type,
            to_page_type=tlink.to_page_type,
            label=tlink.label,
            link_kind=tlink.link_kind,
            meta=tlink.meta,
        )

    # Create funnels from template funnels
    template_funnels = get_template_funnels(session, template_id)
    funnel_count = 0

    for tfunnel in template_funnels:
        funnel_entry_page_id = (
            page_type_to_id.get(tfunnel.entry_page_type) if tfunnel.entry_page_type else None
        )
        funnel = SiteFunnel(
            id=str(uuid4()),
            site_id=str(site.id),
            name=tfunnel.name,
            description=tfunnel.description,
            funnel_type=tfunnel.funnel_type,
            entry_page_id=funnel_entry_page_id,
            status="draft",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(funnel)

        # Get funnel steps
        tsteps = get_template_funnel_steps(session, str(tfunnel.id))
        for tstep in tsteps:
            step = SiteFunnelStep(
                id=str(uuid4()),
                site_funnel_id=funnel.id,
                site_page_id=page_type_to_id.get(tstep.page_type, ""),
                ordering=tstep.ordering,
                step_role=tstep.step_role,
                cta_label=tstep.cta_label,
                created_at=datetime.now(timezone.utc),
            )
            session.add(step)

        funnel_count += 1

    # Set entry page on site
    if entry_page_id:
        site.entry_page_id = entry_page_id
        sites_repo.update_site(site=site)

    session.flush()
    session.refresh(site)

    return {
        "siteId": str(site.id),
        "siteName": site.name,
        "pageCount": len(created_pages),
        "funnelCount": funnel_count,
        "entryPageId": entry_page_id,
        "createdAt": site.created_at,
    }
