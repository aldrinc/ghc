"""Service for site publication operations.

This service handles:
- Creating immutable site publication snapshots
- Validating site state before publishing
- Building site runtime bundle artifact payloads
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Artifact,
    ArtifactTypeEnum,
    Site,
    SitePage,
    SitePageVersion,
    SitePublication,
    SitePublicationPage,
    SitePublicationLink,
    SitePublicationFunnel,
    SitePublicationFunnelStep,
    SitePublicationFunnelPath,
    SitePublicationFunnelPathStep,
    SitePublicationFunnelStepOption,
    SitePublicationProductBinding,
    SiteFunnel,
    SiteFunnelPath,
    SiteFunnelPathStep,
    SiteFunnelStep,
    SiteFunnelStepOption,
    SiteLink,
    SiteProductPageBinding,
    Product,
    ProductVariant,
)


class SitePublicationError(Exception):
    """Error during site publication operations."""

    pass


def validate_site_for_publish(
    session: Session,
    *,
    site_id: str,
    org_id: str,
) -> Site:
    """Validate that a site is ready for publishing.

    Checks:
    - Site exists and belongs to the org
    - Site has at least one page with a published version
    - Funnel steps point to valid site pages
    - Product bindings point to existing products/pages

    Raises SitePublicationError if validation fails.
    """
    site = session.scalars(select(Site).where(Site.id == site_id, Site.org_id == org_id)).first()

    if not site:
        raise SitePublicationError(f"Site not found: {site_id}")

    # Get all pages for this site
    pages = list(session.scalars(select(SitePage).where(SitePage.site_id == site_id)).all())

    if not pages:
        raise SitePublicationError(f"Site {site_id} has no pages")

    # Validate each page has an explicit publishable version (approved or published)
    for page in pages:
        version = session.scalars(
            select(SitePageVersion)
            .where(
                SitePageVersion.page_id == page.id,
                SitePageVersion.status.in_(["approved", "published"]),
            )
            .order_by(SitePageVersion.created_at.desc())
        ).first()

        if not version:
            raise SitePublicationError(
                f"Page '{page.slug}' ({page.id}) has no approved or published version"
            )

    # Validate site funnels if any exist
    funnels = list(session.scalars(select(SiteFunnel).where(SiteFunnel.site_id == site_id)).all())

    for funnel in funnels:
        if funnel.entry_page_id:
            entry_page = session.scalars(
                select(SitePage).where(
                    SitePage.id == funnel.entry_page_id,
                    SitePage.site_id == site_id,
                )
            ).first()
            if not entry_page:
                raise SitePublicationError(
                    f"Funnel '{funnel.name}' ({funnel.id}) references "
                    f"non-existent entry page: {funnel.entry_page_id}"
                )

        # Validate funnel steps
        steps = list(
            session.scalars(
                select(SiteFunnelStep).where(SiteFunnelStep.site_funnel_id == funnel.id)
            ).all()
        )

        for step in steps:
            page = session.scalars(
                select(SitePage).where(
                    SitePage.id == step.site_page_id,
                    SitePage.site_id == site_id,
                )
            ).first()
            if not page:
                raise SitePublicationError(
                    f"Funnel '{funnel.name}' ({funnel.id}) step references "
                    f"non-existent page: {step.site_page_id}"
                )
            options = list(
                session.scalars(
                    select(SiteFunnelStepOption).where(
                        SiteFunnelStepOption.site_funnel_step_id == step.id
                    )
                ).all()
            )
            for option in options:
                option_page = session.scalars(
                    select(SitePage).where(
                        SitePage.id == option.site_page_id,
                        SitePage.site_id == site_id,
                    )
                ).first()
                if not option_page:
                    raise SitePublicationError(
                        f"Funnel '{funnel.name}' ({funnel.id}) step option references "
                        f"non-existent page: {option.site_page_id}"
                    )

        step_ids = {str(step.id) for step in steps}
        paths = list(
            session.scalars(
                select(SiteFunnelPath).where(SiteFunnelPath.site_funnel_id == funnel.id)
            ).all()
        )
        for path in paths:
            path_steps = list(
                session.scalars(
                    select(SiteFunnelPathStep).where(
                        SiteFunnelPathStep.site_funnel_path_id == path.id
                    )
                ).all()
            )
            path_step_ids = {str(path_step.site_funnel_step_id) for path_step in path_steps}
            missing_step_ids = sorted(step_ids.difference(path_step_ids))
            extra_step_ids = sorted(path_step_ids.difference(step_ids))
            if missing_step_ids:
                raise SitePublicationError(
                    f"Funnel path '{path.name}' ({path.id}) is missing step ids: "
                    + ", ".join(missing_step_ids)
                )
            if extra_step_ids:
                raise SitePublicationError(
                    f"Funnel path '{path.name}' ({path.id}) includes invalid step ids: "
                    + ", ".join(extra_step_ids)
                )
            for path_step in path_steps:
                option = session.scalars(
                    select(SiteFunnelStepOption).where(
                        SiteFunnelStepOption.id == path_step.site_funnel_step_option_id,
                        SiteFunnelStepOption.site_funnel_step_id == path_step.site_funnel_step_id,
                        SiteFunnelStepOption.site_page_id == path_step.site_page_id,
                    )
                ).first()
                if not option:
                    raise SitePublicationError(
                        f"Funnel path '{path.name}' ({path.id}) references a page "
                        "that is not configured as an option for its step."
                    )
                path_page = session.scalars(
                    select(SitePage).where(
                        SitePage.id == path_step.site_page_id,
                        SitePage.site_id == site_id,
                    )
                ).first()
                if not path_page:
                    raise SitePublicationError(
                        f"Funnel path '{path.name}' ({path.id}) references "
                        f"non-existent page: {path_step.site_page_id}"
                    )

    # Validate product bindings
    bindings = list(
        session.scalars(
            select(SiteProductPageBinding).where(SiteProductPageBinding.site_id == site_id)
        ).all()
    )

    for binding in bindings:
        # Validate product exists
        product = session.scalars(select(Product).where(Product.id == binding.product_id)).first()
        if not product:
            raise SitePublicationError(
                f"Product binding ({binding.id}) references "
                f"non-existent product: {binding.product_id}"
            )

        # Validate page if specified
        if binding.site_page_id:
            page = session.scalars(
                select(SitePage).where(
                    SitePage.id == binding.site_page_id,
                    SitePage.site_id == site_id,
                )
            ).first()
            if not page:
                raise SitePublicationError(
                    f"Product binding ({binding.id}) references "
                    f"non-existent page: {binding.site_page_id}"
                )

    return site


def create_site_publication(
    session: Session,
    *,
    site_id: str,
    created_by: str | None = None,
    meta: dict[str, Any] | None = None,
) -> SitePublication:
    """Create an immutable publication snapshot of a site.

    This captures the current state of all site pages, links, funnels, and
    product bindings at a point in time.
    """
    now = datetime.now(timezone.utc)

    # Get site with its pages
    site = session.scalars(select(Site).where(Site.id == site_id)).first()
    if not site:
        raise SitePublicationError(f"Site not found: {site_id}")

    # Create the publication record
    publication = SitePublication(
        id=str(uuid4()),
        site_id=site_id,
        entry_page_id=site.entry_page_id,
        created_by=created_by,
        meta=meta or {},
        created_at=now,
    )
    session.add(publication)
    session.flush()

    # Snapshot all pages with their latest versions
    pages = list(
        session.scalars(
            select(SitePage).where(SitePage.site_id == site_id).order_by(SitePage.ordering.asc())
        ).all()
    )

    page_slug_by_id = {page.id: page.slug for page in pages}

    for page in pages:
        # Get the latest explicit publishable version
        version = session.scalars(
            select(SitePageVersion)
            .where(
                SitePageVersion.page_id == page.id,
                SitePageVersion.status.in_(["published", "approved"]),
            )
            .order_by(
                (SitePageVersion.status == "published").desc(),
                SitePageVersion.created_at.desc(),
            )
        ).first()

        if not version:
            raise SitePublicationError(
                f"Page '{page.slug}' ({page.id}) has no approved or published version"
            )

        pub_page = SitePublicationPage(
            id=str(uuid4()),
            publication_id=publication.id,
            page_id=page.id,
            page_version_id=version.id,
            slug_at_publish=page.slug,
            title_at_publish=page.name,
            description_at_publish=None,
            page_type_at_publish=page.page_type,
            page_role_at_publish=page.page_role,
            ordering_at_publish=page.ordering,
            created_at=now,
        )
        session.add(pub_page)

    session.flush()

    # Snapshot all links
    links = list(session.scalars(select(SiteLink).where(SiteLink.site_id == site_id)).all())

    for link in links:
        pub_link = SitePublicationLink(
            id=str(uuid4()),
            publication_id=publication.id,
            site_link_id=link.id,
            from_page_id_at_publish=link.from_page_id,
            to_page_id_at_publish=link.to_page_id,
            from_page_slug_at_publish=page_slug_by_id.get(link.from_page_id),
            to_page_slug_at_publish=page_slug_by_id.get(link.to_page_id),
            label_at_publish=link.label,
            link_kind_at_publish=link.link_kind,
            meta_at_publish=link.meta,
            created_at=now,
        )
        session.add(pub_link)

    # Snapshot all funnels with their steps
    funnels = list(session.scalars(select(SiteFunnel).where(SiteFunnel.site_id == site_id)).all())

    for funnel in funnels:
        pub_funnel = SitePublicationFunnel(
            id=str(uuid4()),
            publication_id=publication.id,
            site_funnel_id=funnel.id,
            name_at_publish=funnel.name,
            funnel_type_at_publish=funnel.funnel_type,
            entry_page_id_at_publish=funnel.entry_page_id,
            created_at=now,
        )
        session.add(pub_funnel)
        session.flush()

        # Snapshot funnel steps
        steps = list(
            session.scalars(
                select(SiteFunnelStep)
                .where(SiteFunnelStep.site_funnel_id == funnel.id)
                .order_by(SiteFunnelStep.ordering.asc())
            ).all()
        )

        for step in steps:
            # Get the page slug for this step
            page = session.scalars(select(SitePage).where(SitePage.id == step.site_page_id)).first()

            pub_step = SitePublicationFunnelStep(
                id=str(uuid4()),
                publication_funnel_id=pub_funnel.id,
                site_funnel_step_id=step.id,
                page_id_at_publish=step.site_page_id,
                slug_at_publish=page.slug if page else "",
                ordering_at_publish=step.ordering,
                step_role_at_publish=step.step_role,
                cta_label_at_publish=step.cta_label,
                created_at=now,
            )
            session.add(pub_step)

            options = list(
                session.scalars(
                    select(SiteFunnelStepOption)
                    .where(SiteFunnelStepOption.site_funnel_step_id == step.id)
                    .order_by(
                        SiteFunnelStepOption.is_control.desc(),
                        SiteFunnelStepOption.created_at.asc(),
                    )
                ).all()
            )
            for option in options:
                pub_option = SitePublicationFunnelStepOption(
                    id=str(uuid4()),
                    publication_funnel_id=pub_funnel.id,
                    site_funnel_step_option_id=option.id,
                    site_funnel_step_id_at_publish=option.site_funnel_step_id,
                    page_id_at_publish=option.site_page_id,
                    slug_at_publish=page_slug_by_id.get(option.site_page_id, ""),
                    option_key_at_publish=option.option_key,
                    label_at_publish=option.label,
                    status_at_publish=option.status,
                    traffic_weight_at_publish=option.traffic_weight,
                    is_control_at_publish=option.is_control,
                    metadata_at_publish=option.metadata_json,
                    created_at=now,
                )
                session.add(pub_option)

        paths = list(
            session.scalars(
                select(SiteFunnelPath)
                .where(SiteFunnelPath.site_funnel_id == funnel.id)
                .order_by(
                    SiteFunnelPath.is_control.desc(),
                    SiteFunnelPath.created_at.asc(),
                )
            ).all()
        )
        for path in paths:
            pub_path = SitePublicationFunnelPath(
                id=str(uuid4()),
                publication_funnel_id=pub_funnel.id,
                site_funnel_path_id=path.id,
                campaign_id_at_publish=path.campaign_id,
                name_at_publish=path.name,
                slug_at_publish=path.slug,
                status_at_publish=path.status,
                traffic_weight_at_publish=path.traffic_weight,
                is_control_at_publish=path.is_control,
                experiment_spec_id_at_publish=path.experiment_spec_id,
                variant_id_at_publish=path.variant_id,
                metadata_at_publish=path.metadata_json,
                created_at=now,
            )
            session.add(pub_path)
            session.flush()

            path_steps = list(
                session.scalars(
                    select(SiteFunnelPathStep)
                    .where(SiteFunnelPathStep.site_funnel_path_id == path.id)
                    .order_by(SiteFunnelPathStep.ordering.asc())
                ).all()
            )
            for path_step in path_steps:
                pub_path_step = SitePublicationFunnelPathStep(
                    id=str(uuid4()),
                    publication_funnel_path_id=pub_path.id,
                    site_funnel_path_step_id=path_step.id,
                    site_funnel_step_id_at_publish=path_step.site_funnel_step_id,
                    site_funnel_step_option_id_at_publish=path_step.site_funnel_step_option_id,
                    page_id_at_publish=path_step.site_page_id,
                    slug_at_publish=page_slug_by_id.get(path_step.site_page_id, ""),
                    ordering_at_publish=path_step.ordering,
                    step_role_at_publish=path_step.step_role,
                    created_at=now,
                )
                session.add(pub_path_step)

    # Snapshot product bindings
    bindings = list(
        session.scalars(
            select(SiteProductPageBinding).where(SiteProductPageBinding.site_id == site_id)
        ).all()
    )

    for binding in bindings:
        pub_binding = SitePublicationProductBinding(
            id=str(uuid4()),
            publication_id=publication.id,
            site_product_binding_id=binding.id,
            product_id_at_publish=binding.product_id,
            page_id_at_publish=binding.site_page_id,
            page_role_at_publish=binding.page_role,
            variant_ids_at_publish=binding.variant_ids,
            binding_context_at_publish=binding.binding_context,
            priority_at_publish=binding.priority,
            active_at_publish=binding.active,
            created_at=now,
        )
        session.add(pub_binding)

    session.flush()

    # Update site's active publication reference
    site.active_site_publication_id = publication.id
    session.add(site)

    return publication


def get_site_publication(
    session: Session,
    *,
    publication_id: str,
) -> SitePublication | None:
    """Get a site publication by ID."""
    return session.scalars(
        select(SitePublication).where(SitePublication.id == publication_id)
    ).first()


def get_active_site_publication(
    session: Session,
    *,
    site_id: str,
) -> SitePublication | None:
    """Get the active site publication for a site."""
    site = session.scalars(select(Site).where(Site.id == site_id)).first()
    if not site or not site.active_site_publication_id:
        return None
    return get_site_publication(session, publication_id=str(site.active_site_publication_id))


def list_site_publication_pages(
    session: Session,
    *,
    publication_id: str,
) -> list[SitePublicationPage]:
    """List all pages in a publication snapshot."""
    return list(
        session.scalars(
            select(SitePublicationPage)
            .where(SitePublicationPage.publication_id == publication_id)
            .order_by(SitePublicationPage.ordering_at_publish.asc())
        ).all()
    )


def list_site_publication_funnels(
    session: Session,
    *,
    publication_id: str,
) -> list[SitePublicationFunnel]:
    """List all funnels in a publication snapshot."""
    return list(
        session.scalars(
            select(SitePublicationFunnel).where(
                SitePublicationFunnel.publication_id == publication_id
            )
        ).all()
    )


def list_site_publication_funnel_steps(
    session: Session,
    *,
    publication_funnel_id: str,
) -> list[SitePublicationFunnelStep]:
    """List all steps in a publication funnel snapshot."""
    return list(
        session.scalars(
            select(SitePublicationFunnelStep)
            .where(SitePublicationFunnelStep.publication_funnel_id == publication_funnel_id)
            .order_by(SitePublicationFunnelStep.ordering_at_publish.asc())
        ).all()
    )


def list_site_publication_funnel_step_options(
    session: Session,
    *,
    publication_funnel_id: str,
) -> list[SitePublicationFunnelStepOption]:
    """List all step page options in a publication funnel snapshot."""
    return list(
        session.scalars(
            select(SitePublicationFunnelStepOption)
            .where(SitePublicationFunnelStepOption.publication_funnel_id == publication_funnel_id)
            .order_by(
                SitePublicationFunnelStepOption.is_control_at_publish.desc(),
                SitePublicationFunnelStepOption.created_at.asc(),
            )
        ).all()
    )


def list_site_publication_funnel_paths(
    session: Session,
    *,
    publication_funnel_id: str,
) -> list[SitePublicationFunnelPath]:
    """List all internal paths in a publication funnel snapshot."""
    return list(
        session.scalars(
            select(SitePublicationFunnelPath)
            .where(SitePublicationFunnelPath.publication_funnel_id == publication_funnel_id)
            .order_by(
                SitePublicationFunnelPath.is_control_at_publish.desc(),
                SitePublicationFunnelPath.created_at.asc(),
            )
        ).all()
    )


def list_site_publication_funnel_path_steps(
    session: Session,
    *,
    publication_funnel_path_id: str,
) -> list[SitePublicationFunnelPathStep]:
    """List selected pages for an internal published funnel path."""
    return list(
        session.scalars(
            select(SitePublicationFunnelPathStep)
            .where(
                SitePublicationFunnelPathStep.publication_funnel_path_id
                == publication_funnel_path_id
            )
            .order_by(SitePublicationFunnelPathStep.ordering_at_publish.asc())
        ).all()
    )


def list_site_publication_product_bindings(
    session: Session,
    *,
    publication_id: str,
) -> list[SitePublicationProductBinding]:
    """List all product bindings in a publication snapshot."""
    return list(
        session.scalars(
            select(SitePublicationProductBinding).where(
                SitePublicationProductBinding.publication_id == publication_id
            )
        ).all()
    )


def list_site_publication_links(
    session: Session,
    *,
    publication_id: str,
) -> list[SitePublicationLink]:
    """List all links in a publication snapshot."""
    return list(
        session.scalars(
            select(SitePublicationLink).where(SitePublicationLink.publication_id == publication_id)
        ).all()
    )
