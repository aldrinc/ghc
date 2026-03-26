"""Public site runtime endpoints.

This module provides public read-only endpoints for accessing published site content
under /public/sites/{siteSlug}. These endpoints read from site publications or
site runtime bundle artifacts, not legacy funnel runtime.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.deps import get_session
from app.db.models import (
    Site,
    SitePublication,
    SitePublicationPage,
    SitePublicationFunnel,
    SitePublicationFunnelStep,
    SitePublicationProductBinding,
    SitePageVersion,
    Product,
    ProductVariant,
)
from app.services.site_publications import (
    get_active_site_publication,
    list_site_publication_pages,
    list_site_publication_funnels,
    list_site_publication_funnel_steps,
    list_site_publication_product_bindings,
    list_site_publication_links,
)
from app.services.deploy import (
    build_site_runtime_bundle_artifact_payload,
)
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.enums import ArtifactTypeEnum

router = APIRouter(prefix="/public/sites", tags=["public_sites"])


def _get_site_by_route_slug(
    session: Session,
    site_slug: str,
) -> Site | None:
    """Look up a site by its route_slug."""
    stmt = select(Site).where(Site.route_slug == site_slug)
    return session.scalars(stmt).first()


def _get_site_artifact(
    session: Session,
    site_id: str,
) -> dict[str, Any] | None:
    """Get the latest site_runtime_bundle artifact for a site.

    Returns None if no artifact exists yet.
    """
    artifacts_repo = ArtifactsRepository(session)
    site = session.scalars(select(Site).where(Site.id == site_id)).first()
    if not site:
        return None

    latest = artifacts_repo.get_latest_by_type(
        org_id=site.org_id,
        client_id=str(site.client_id),
        artifact_type=ArtifactTypeEnum.site_runtime_bundle,
    )
    if not latest:
        return None
    return latest.data


@router.get("/{site_slug}/meta")
def get_site_meta(
    site_slug: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Get public metadata for a site by its route slug.

    Returns site-level information useful for previews and SEO.
    """
    site = _get_site_by_route_slug(session, site_slug)
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Site not found: {site_slug}",
        )

    # Try to get from active publication first
    publication = get_active_site_publication(session, site_id=str(site.id))

    if publication:
        return {
            "siteId": str(site.id),
            "name": site.name,
            "description": site.description,
            "routeSlug": site.route_slug,
            "siteType": site.site_type,
            "siteFamily": site.site_family,
            "primaryDomain": site.primary_domain,
            "entryPageSlug": None,  # Would need to look up from pub pages
            "publicationId": str(publication.id),
            "publishedAt": publication.created_at.isoformat() if publication.created_at else None,
        }

    # Fall back to artifact if no publication
    artifact_data = _get_site_artifact(session, str(site.id))
    if artifact_data:
        meta = artifact_data.get("meta", {})
        return {
            "siteId": str(site.id),
            "name": meta.get("siteName", site.name),
            "description": site.description,
            "routeSlug": site.route_slug,
            "siteType": meta.get("siteType", site.site_type),
            "siteFamily": meta.get("siteFamily", site.site_family),
            "primaryDomain": site.primary_domain,
            "publicationId": meta.get("publicationId"),
            "publishedAt": meta.get("publishedAt"),
        }

    # No publication or artifact yet
    return {
        "siteId": str(site.id),
        "name": site.name,
        "description": site.description,
        "routeSlug": site.route_slug,
        "siteType": site.site_type,
        "siteFamily": site.site_family,
        "primaryDomain": site.primary_domain,
        "publicationId": None,
        "publishedAt": None,
    }


@router.get("/{site_slug}/pages/{page_slug}")
def get_site_page(
    site_slug: str,
    page_slug: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Get a specific published page from a site by its route slug and page slug.

    Returns the page's puck data and metadata.
    """
    site = _get_site_by_route_slug(session, site_slug)
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Site not found: {site_slug}",
        )

    # Try active publication first
    publication = get_active_site_publication(session, site_id=str(site.id))

    if publication:
        pub_pages = list_site_publication_pages(session, publication_id=publication.id)
        for pub_page in pub_pages:
            if pub_page.slug_at_publish == page_slug:
                version = session.scalars(
                    select(SitePageVersion).where(SitePageVersion.id == pub_page.page_version_id)
                ).first()

                return {
                    "pageId": str(pub_page.page_id),
                    "versionId": str(pub_page.page_version_id),
                    "slug": pub_page.slug_at_publish,
                    "title": pub_page.title_at_publish,
                    "description": pub_page.description_at_publish,
                    "pageType": pub_page.page_type_at_publish,
                    "pageRole": pub_page.page_role_at_publish,
                    "ordering": pub_page.ordering_at_publish,
                    "puckData": version.puck_data if version else {},
                    "publicationId": str(publication.id),
                }

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Page not found: {page_slug}",
        )

    # Fall back to artifact
    artifact_data = _get_site_artifact(session, str(site.id))
    if artifact_data:
        pages = artifact_data.get("pages", {})
        page_data = pages.get(page_slug)
        if page_data:
            return {
                "pageId": page_data.get("pageId"),
                "versionId": page_data.get("versionId"),
                "slug": page_slug,
                "title": page_data.get("title"),
                "description": page_data.get("description"),
                "pageType": page_data.get("pageType"),
                "pageRole": page_data.get("pageRole"),
                "ordering": page_data.get("ordering"),
                "puckData": page_data.get("puckData", {}),
                "publicationId": artifact_data.get("meta", {}).get("publicationId"),
            }

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Site has no published content yet: {site_slug}",
    )


@router.get("/{site_slug}/graph")
def get_site_graph(
    site_slug: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Get the full page graph (pages and links) for a site.

    Returns all pages with their metadata and navigation links.
    """
    site = _get_site_by_route_slug(session, site_slug)
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Site not found: {site_slug}",
        )

    # Try active publication first
    publication = get_active_site_publication(session, site_id=str(site.id))

    if publication:
        pub_pages = list_site_publication_pages(session, publication_id=publication.id)
        pub_links = list_site_publication_links(session, publication_id=publication.id)

        pages_list: list[dict[str, Any]] = []
        links_list: list[dict[str, Any]] = []

        for pub_page in pub_pages:
            pages_list.append(
                {
                    "pageId": str(pub_page.page_id),
                    "slug": pub_page.slug_at_publish,
                    "title": pub_page.title_at_publish,
                    "pageType": pub_page.page_type_at_publish,
                    "pageRole": pub_page.page_role_at_publish,
                    "ordering": pub_page.ordering_at_publish,
                }
            )

        for pub_link in pub_links:
            links_list.append(
                {
                    "fromPageSlug": pub_link.from_page_slug_at_publish,
                    "toPageSlug": pub_link.to_page_slug_at_publish,
                    "label": pub_link.label_at_publish,
                    "kind": pub_link.link_kind_at_publish,
                }
            )

        return {
            "siteId": str(site.id),
            "siteName": site.name,
            "routeSlug": site.route_slug,
            "publicationId": str(publication.id),
            "pages": pages_list,
            "links": links_list,
        }

    # Fall back to artifact
    artifact_data = _get_site_artifact(session, str(site.id))
    if artifact_data:
        pages_raw = artifact_data.get("pages", {})
        pages_list = []
        for slug, page_data in pages_raw.items():
            pages_list.append(
                {
                    "pageId": page_data.get("pageId"),
                    "slug": slug,
                    "title": page_data.get("title"),
                    "pageType": page_data.get("pageType"),
                    "pageRole": page_data.get("pageRole"),
                    "ordering": page_data.get("ordering"),
                }
            )

        links_raw = artifact_data.get("links", [])
        links_list = []
        for link_data in links_raw:
            links_list.append(
                {
                    "fromPageSlug": link_data.get("fromPageSlug"),
                    "toPageSlug": link_data.get("toPageSlug"),
                    "label": link_data.get("label"),
                    "kind": link_data.get("kind"),
                }
            )

        return {
            "siteId": str(site.id),
            "siteName": artifact_data.get("meta", {}).get("siteName", site.name),
            "routeSlug": site.route_slug,
            "publicationId": artifact_data.get("meta", {}).get("publicationId"),
            "pages": pages_list,
            "links": links_list,
        }

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Site has no published content yet: {site_slug}",
    )


@router.get("/{site_slug}/products/{product_slug}")
def get_site_product(
    site_slug: str,
    product_slug: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Get product information bound to a site, by product slug.

    Returns product details with variants for commerce display.
    """
    site = _get_site_by_route_slug(session, site_slug)
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Site not found: {site_slug}",
        )

    # Look up product by handle/slug
    product = session.scalars(
        select(Product).where(
            Product.client_id == site.client_id,
            Product.handle == product_slug,
        )
    ).first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product not found: {product_slug}",
        )

    # Get variants
    variants = list(
        session.scalars(select(ProductVariant).where(ProductVariant.product_id == product.id)).all()
    )

    variants_payload: list[dict[str, Any]] = []
    for variant in variants:
        variants_payload.append(
            {
                "id": str(variant.id),
                "title": variant.title,
                "price": variant.price,
                "currency": variant.currency,
                "sku": variant.sku,
                "inventoryQuantity": variant.inventory_quantity,
                "optionValues": variant.option_values,
            }
        )

    # Try to get binding info from publication
    publication = get_active_site_publication(session, site_id=str(site.id))
    binding_info: dict[str, Any] | None = None

    if publication:
        pub_bindings = list_site_publication_product_bindings(
            session, publication_id=publication.id
        )
        for pub_binding in pub_bindings:
            if str(pub_binding.product_id_at_publish) == str(product.id):
                binding_info = {
                    "pageRole": pub_binding.page_role_at_publish,
                    "pageSlug": None,  # Would need to map page_id to slug
                    "variantIds": pub_binding.variant_ids_at_publish,
                    "bindingContext": pub_binding.binding_context_at_publish,
                    "priority": pub_binding.priority_at_publish,
                }
                break

    return {
        "productId": str(product.id),
        "title": product.title,
        "description": product.description,
        "handle": product.handle,
        "productType": product.product_type,
        "vendor": product.vendor,
        "tags": list(product.tags),
        "variants": variants_payload,
        "binding": binding_info,
    }


@router.get("/{site_slug}/funnels/{funnel_name}")
def get_site_funnel(
    site_slug: str,
    funnel_name: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Get a specific funnel by name for a published site.

    Returns funnel metadata with ordered steps.
    """
    site = _get_site_by_route_slug(session, site_slug)
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Site not found: {site_slug}",
        )

    # Try active publication first
    publication = get_active_site_publication(session, site_id=str(site.id))

    if publication:
        pub_funnels = list_site_publication_funnels(session, publication_id=publication.id)

        for pub_funnel in pub_funnels:
            funnel_key = str(pub_funnel.site_funnel_id)
            # Match by name (we store name directly now)
            if pub_funnel.name_at_publish.lower().replace(" ", "-") == funnel_name.lower().replace(
                " ", "-"
            ):
                pub_steps = list_site_publication_funnel_steps(
                    session, publication_funnel_id=pub_funnel.id
                )

                steps_payload: list[dict[str, Any]] = []
                for pub_step in pub_steps:
                    steps_payload.append(
                        {
                            "pageSlug": pub_step.slug_at_publish,
                            "ordering": pub_step.ordering_at_publish,
                            "stepRole": pub_step.step_role_at_publish,
                            "ctaLabel": pub_step.cta_label_at_publish,
                        }
                    )

                return {
                    "funnelId": funnel_key,
                    "name": pub_funnel.name_at_publish,
                    "funnelType": pub_funnel.funnel_type_at_publish,
                    "entryPageSlug": None,  # Would need page_id mapping
                    "publicationId": str(publication.id),
                    "steps": steps_payload,
                }

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Funnel not found: {funnel_name}",
        )

    # Fall back to artifact
    artifact_data = _get_site_artifact(session, str(site.id))
    if artifact_data:
        funnels = artifact_data.get("funnels", {})
        for funnel_id, funnel_data in funnels.items():
            funnel_key = funnel_id.lower().replace(" ", "-")
            if funnel_key == funnel_name.lower().replace(" ", "-"):
                return {
                    "funnelId": funnel_id,
                    "name": funnel_data.get("name"),
                    "funnelType": funnel_data.get("funnelType"),
                    "entryPageSlug": funnel_data.get("entryPageSlug"),
                    "publicationId": artifact_data.get("meta", {}).get("publicationId"),
                    "steps": funnel_data.get("steps", []),
                }

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Site has no published content yet: {site_slug}",
    )
