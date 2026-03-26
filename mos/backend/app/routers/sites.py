"""Site management API endpoints.

This module provides endpoints for managing Site-based experiences backed by the dedicated
site runtime (Site/SitePage/SitePageVersion), not the funnel runtime.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.models import (
    DesignSystem,
    Product,
    Site,
    SitePage,
    SitePageVersion,
    Client,
)
from app.db.repositories.sites_runtime import SitesRuntimeRepository
from app.schemas.sites import (
    SiteFamilySummary,
    SiteFamilyDetail,
    SiteCreateRequest,
    SiteSummary,
    SiteDetail,
    SitePageDetail,
    SitePageBlueprintSummary,
    SitePageUpdateRequest,
    SitePageVersionCreateRequest,
    SitePageEditorResponse,
    SitePageVersionSummary,
)
from app.services.site_blueprints import (
    list_site_families,
    get_site_family,
)
from app.services.funnel_templates import get_funnel_template, apply_template_assets
from app.services.design_systems import resolve_design_system_tokens
from app.services.funnels import rewrite_internal_target_ids

router = APIRouter(prefix="/sites", tags=["sites"])


def _parse_uuid_or_400(value: str, field_name: str) -> UUID:
    try:
        return UUID(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must be a valid UUID.",
        ) from exc


def _resolve_site_design_system_tokens(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    site: Site,
    page: SitePage | None = None,
) -> dict[str, Any] | None:
    design_system_id = None
    if page and page.design_system_id:
        design_system_id = str(page.design_system_id)
    elif site.design_system_id:
        design_system_id = str(site.design_system_id)

    if design_system_id:
        design_system = session.scalars(
            select(DesignSystem).where(
                DesignSystem.org_id == UUID(org_id),
                DesignSystem.id == UUID(design_system_id),
            )
        ).first()
        return design_system.tokens if design_system else None

    return resolve_design_system_tokens(
        session=session,
        org_id=org_id,
        client_id=client_id,
    )


# Placeholder page IDs used in templates - these are rewritten to real page IDs after creation
PAGE_TYPE_PLACEHOLDERS = {
    "home": "__PAGE_HOME__",
    "category": "__PAGE_CATEGORY__",
    "product_detail": "__PAGE_PRODUCT_DETAIL__",
    "cart": "__PAGE_CART__",
    "checkout": "__PAGE_CHECKOUT__",
}


@router.get("/families", response_model=list[SiteFamilySummary])
def list_families() -> list[SiteFamilySummary]:
    """List all available site families."""
    families = list_site_families()
    return [
        SiteFamilySummary(
            family=f.family,
            name=f.name,
            description=f.description,
            siteType=f.site_type,
            commerceProvider=f.commerce_provider,
            pageCount=len(f.page_blueprints),
        )
        for f in families
    ]


@router.get("/families/{family}", response_model=SiteFamilyDetail)
def get_family_detail(family: str) -> SiteFamilyDetail:
    """Get detailed information about a specific site family."""
    descriptor = get_site_family(family)
    if not descriptor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Site family '{family}' not found.",
        )
    return SiteFamilyDetail(
        family=descriptor.family,
        name=descriptor.name,
        description=descriptor.description,
        siteType=descriptor.site_type,
        commerceProvider=descriptor.commerce_provider,
        pageBlueprints=[
            SitePageBlueprintSummary(
                pageType=bp.page_type,
                templateId=bp.template_id,
                name=bp.name,
                slug=bp.slug,
                description=bp.description,
                ordering=bp.ordering,
                isEntry=bp.is_entry,
            )
            for bp in descriptor.page_blueprints
        ],
        provenanceNotes=list(descriptor.provenance_notes),
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SiteDetail)
def create_site(
    payload: SiteCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Create a new site from a site family blueprint.

    This endpoint creates a site in the dedicated site runtime (Site/SitePage/SitePageVersion)
    instead of using the funnel runtime. productId is now optional.
    """
    # Validate the site family
    descriptor = get_site_family(payload.family)
    if not descriptor:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown site family: '{payload.family}'.",
        )

    client_uuid = _parse_uuid_or_400(payload.clientId, "clientId")

    # Validate workspace ownership
    client = session.scalars(
        select(Client).where(
            Client.org_id == UUID(auth.org_id),
            Client.id == client_uuid,
        )
    ).first()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or does not belong to this organization.",
        )

    # Validate product if provided
    product_uuid = None
    if payload.productId:
        product_uuid = _parse_uuid_or_400(payload.productId, "productId")
        product = session.scalars(
            select(Product).where(
                Product.org_id == UUID(auth.org_id),
                Product.client_id == client_uuid,
                Product.id == product_uuid,
            )
        ).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found or does not belong to this workspace.",
            )

    # Resolve design system tokens if provided
    design_system_tokens = None
    design_system_id = None
    if payload.designSystemId:
        from app.routers.funnels import _validate_design_system

        design_system = _validate_design_system(
            session=session,
            org_id=auth.org_id,
            client_id=payload.clientId,
            design_system_id=payload.designSystemId,
        )
        design_system_tokens = design_system.tokens
        design_system_id = str(design_system.id)
    else:
        design_system_tokens = resolve_design_system_tokens(
            session=session,
            org_id=auth.org_id,
            client_id=payload.clientId,
        )

    try:
        sites_repo = SitesRuntimeRepository(session)

        # Generate unique route slug for the site
        route_slug = sites_repo._generate_unique_route_slug(
            desired_slug=payload.name or f"{descriptor.family}-site"
        )

        # Create the site row
        site = sites_repo.create_site(
            org_id=str(UUID(auth.org_id)),
            client_id=str(client_uuid),
            name=payload.name,
            description=payload.description or f"{descriptor.name} site",
            site_type=descriptor.site_type,
            site_family=descriptor.family,
            commerce_provider=descriptor.commerce_provider,
            route_slug=route_slug,
            design_system_id=design_system_id,
            product_id=str(product_uuid) if product_uuid else None,
        )

        # Create pages from blueprints
        created_pages: list[dict[str, Any]] = []
        page_id_map: dict[str, str] = {}  # Maps page_type to real page ID
        entry_page_id = None

        for blueprint in descriptor.page_blueprints:
            # Get the template for this page
            template = get_funnel_template(blueprint.template_id)
            if not template:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        f"Site family '{descriptor.family}' references unknown template "
                        f"'{blueprint.template_id}' for page '{blueprint.page_type}'."
                    ),
                )

            try:
                template_puck_data = apply_template_assets(
                    session=session,
                    org_id=auth.org_id,
                    client_id=payload.clientId,
                    template=template,
                    design_system_tokens=design_system_tokens,
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        f"Failed to hydrate template '{blueprint.template_id}' for "
                        f"page '{blueprint.page_type}': {exc}"
                    ),
                ) from exc

            # Create the page
            page = sites_repo.create_page(
                site_id=str(site.id),
                name=blueprint.name,
                slug=blueprint.slug,
                ordering=blueprint.ordering,
                template_id=blueprint.template_id,
                design_system_id=design_system_id,
                page_type=blueprint.page_type,
                adapted_puck_data=template_puck_data,
            )

            # Track page ID for link rewriting
            page_id_map[blueprint.page_type] = str(page.id)

            # Create the initial draft version
            version = sites_repo.create_page_version(
                page_id=str(page.id),
                puck_data=template_puck_data,
                provenance={"source": "blueprint"},
                status="draft",
                source_type="site_template",
                source_id=descriptor.family,
            )
            approved_version = sites_repo.create_page_version(
                page_id=str(page.id),
                puck_data=template_puck_data,
                provenance={"source": "blueprint"},
                status="approved",
                source_type="site_template",
                source_id=descriptor.family,
            )

            # Track entry page
            if blueprint.is_entry:
                entry_page_id = str(page.id)

            created_pages.append(
                {
                    "id": str(page.id),
                    "name": page.name,
                    "slug": page.slug,
                    "pageType": blueprint.page_type,
                    "templateId": blueprint.template_id,
                    "ordering": blueprint.ordering,
                    "designSystemId": design_system_id,
                    "isEntry": blueprint.is_entry,
                    "latestDraftVersionId": str(version.id),
                    "latestApprovedVersionId": str(approved_version.id),
                }
            )

        # Build placeholder-to-real-ID mapping for link rewriting
        placeholder_id_map = {
            PAGE_TYPE_PLACEHOLDERS[page_type]: real_id
            for page_type, real_id in page_id_map.items()
            if page_type in PAGE_TYPE_PLACEHOLDERS
        }

        # Rewrite internal links in all page puck_data
        for page_data in created_pages:
            page_id = page_data["id"]
            page = sites_repo.get_page(site_id=str(site.id), page_id=page_id)
            if not page:
                continue

            # Rewrite puck_data with real page IDs
            rewritten_puck_data = rewrite_internal_target_ids(
                page.adapted_puck_data, placeholder_id_map
            )
            page.adapted_puck_data = rewritten_puck_data
            sites_repo.update_page(page=page)

            for page_version in sites_repo.list_versions_for_page(page_id=page_id):
                page_version.puck_data = rewritten_puck_data
                session.add(page_version)

        # Set entry page on site
        if entry_page_id:
            site.entry_page_id = entry_page_id
            sites_repo.update_site(site=site)

        # Commit all changes atomically
        session.commit()
        session.refresh(site)

        return {
            "id": str(site.id),
            "clientId": str(site.client_id),
            "name": site.name,
            "description": site.description,
            "status": site.status,
            "siteType": site.site_type,
            "siteFamily": site.site_family,
            "commerceProvider": site.commerce_provider,
            "productId": str(site.product_id) if site.product_id else None,
            "designSystemId": str(site.design_system_id) if site.design_system_id else None,
            "routeSlug": site.route_slug,
            "entryPageId": entry_page_id,
            "pages": created_pages,
            "createdAt": site.created_at.isoformat(),
            "updatedAt": site.updated_at.isoformat(),
        }

    except HTTPException:
        session.rollback()
        raise
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create site: {exc}",
        ) from exc


@router.get("", response_model=list[SiteSummary])
def list_sites(
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """List all sites for a workspace."""
    # Validate workspace ownership
    client = session.scalars(
        select(Client).where(
            Client.org_id == UUID(auth.org_id),
            Client.id == _parse_uuid_or_400(clientId, "clientId"),
        )
    ).first()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or does not belong to this organization.",
        )

    # Query sites from the dedicated site runtime
    sites_repo = SitesRuntimeRepository(session)
    sites = sites_repo.list_sites(org_id=str(UUID(auth.org_id)), client_id=str(UUID(clientId)))

    return [
        {
            "id": str(s.id),
            "clientId": str(s.client_id),
            "name": s.name,
            "description": s.description,
            "status": s.status,
            "siteType": s.site_type,
            "siteFamily": s.site_family,
            "commerceProvider": s.commerce_provider,
            "productId": str(s.product_id) if s.product_id else None,
            "designSystemId": str(s.design_system_id) if s.design_system_id else None,
            "routeSlug": s.route_slug,
            "createdAt": s.created_at.isoformat(),
            "updatedAt": s.updated_at.isoformat(),
        }
        for s in sites
    ]


@router.get("/{site_id}", response_model=SiteDetail)
def get_site(
    site_id: str,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteDetail:
    """Get detailed information about a specific site."""
    # Validate workspace ownership
    client = session.scalars(
        select(Client).where(
            Client.org_id == UUID(auth.org_id),
            Client.id == _parse_uuid_or_400(clientId, "clientId"),
        )
    ).first()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or does not belong to this organization.",
        )

    # Get the site from dedicated site runtime
    sites_repo = SitesRuntimeRepository(session)

    # First check if site exists in this org (regardless of client)
    site = sites_repo.get_site_by_id(
        org_id=str(UUID(auth.org_id)),
        site_id=site_id,
    )

    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found.",
        )

    # Check if site belongs to the specified workspace
    if str(site.client_id) != clientId:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Site does not belong to this workspace.",
        )

    # Get pages
    pages = sites_repo.list_pages(site_id=str(site.id))

    page_summaries = []
    for page in pages:
        draft = sites_repo.latest_version_for_page(page_id=str(page.id), status="draft")
        approved = sites_repo.latest_version_for_page(page_id=str(page.id), status="approved")
        page_summaries.append(
            SitePageDetail(
                id=str(page.id),
                name=page.name,
                slug=page.slug,
                pageType=page.page_type,
                templateId=page.template_id,
                ordering=page.ordering,
                designSystemId=str(page.design_system_id) if page.design_system_id else None,
                isEntry=str(page.id) == str(site.entry_page_id) if site.entry_page_id else False,
                latestDraftVersionId=str(draft.id) if draft else None,
                latestApprovedVersionId=str(approved.id) if approved else None,
            )
        )

    return SiteDetail(
        id=str(site.id),
        clientId=str(site.client_id),
        name=site.name,
        description=site.description,
        status=site.status,
        siteType=site.site_type,
        siteFamily=site.site_family,
        commerceProvider=site.commerce_provider,
        productId=str(site.product_id) if site.product_id else None,
        designSystemId=str(site.design_system_id) if site.design_system_id else None,
        routeSlug=site.route_slug,
        entryPageId=str(site.entry_page_id) if site.entry_page_id else None,
        pages=page_summaries,
        createdAt=site.created_at.isoformat(),
        updatedAt=site.updated_at.isoformat(),
    )


@router.get("/{site_id}/pages/{page_id}", response_model=SitePageEditorResponse)
def get_site_page(
    site_id: str,
    page_id: str,
    clientId: str = Query(..., description="Workspace ID"),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SitePageEditorResponse:
    """Get site page with latest draft and approved versions for the page editor."""
    # Validate workspace ownership
    client = session.scalars(
        select(Client).where(
            Client.org_id == UUID(auth.org_id),
            Client.id == _parse_uuid_or_400(clientId, "clientId"),
        )
    ).first()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or does not belong to this organization.",
        )

    # Get the site
    sites_repo = SitesRuntimeRepository(session)
    site = sites_repo.get_site(
        org_id=str(UUID(auth.org_id)),
        client_id=str(UUID(clientId)),
        site_id=site_id,
    )

    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found.",
        )

    # Get the page
    page = sites_repo.get_page(site_id=site_id, page_id=page_id)
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Page not found.",
        )

    # Get latest draft and approved versions
    latest_draft = sites_repo.latest_version_for_page(page_id=str(page.id), status="draft")
    latest_approved = sites_repo.latest_version_for_page(page_id=str(page.id), status="approved")

    design_system_tokens = _resolve_site_design_system_tokens(
        session=session,
        org_id=auth.org_id,
        client_id=clientId,
        site=site,
        page=page,
    )

    return SitePageEditorResponse(
        site={
            "id": str(site.id),
            "name": site.name,
            "routeSlug": site.route_slug,
            "siteFamily": site.site_family,
            "siteType": site.site_type,
            "commerceProvider": site.commerce_provider,
            "productId": str(site.product_id) if site.product_id else None,
            "designSystemId": str(site.design_system_id) if site.design_system_id else None,
        },
        page={
            "id": str(page.id),
            "siteId": str(page.site_id),
            "name": page.name,
            "slug": page.slug,
            "pageType": page.page_type,
            "templateId": page.template_id,
            "ordering": page.ordering,
            "designSystemId": str(page.design_system_id) if page.design_system_id else None,
        },
        latestDraft={
            "id": str(latest_draft.id),
            "status": latest_draft.status,
            "puckData": latest_draft.puck_data,
            "createdAt": latest_draft.created_at.isoformat(),
        }
        if latest_draft
        else None,
        latestApproved={
            "id": str(latest_approved.id),
            "status": latest_approved.status,
            "puckData": latest_approved.puck_data,
            "createdAt": latest_approved.created_at.isoformat(),
        }
        if latest_approved
        else None,
        designSystemTokens=design_system_tokens,
    )


@router.patch("/{site_id}/pages/{page_id}", response_model=SitePageEditorResponse)
def update_site_page(
    site_id: str,
    page_id: str,
    payload: SitePageUpdateRequest,
    clientId: str = Query(..., description="Workspace ID"),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SitePageEditorResponse:
    """Update a site page (name, slug, designSystemId)."""
    # Validate workspace ownership
    client = session.scalars(
        select(Client).where(
            Client.org_id == UUID(auth.org_id),
            Client.id == _parse_uuid_or_400(clientId, "clientId"),
        )
    ).first()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or does not belong to this organization.",
        )

    # Get the site
    sites_repo = SitesRuntimeRepository(session)
    site = sites_repo.get_site(
        org_id=str(UUID(auth.org_id)),
        client_id=str(UUID(clientId)),
        site_id=site_id,
    )

    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found.",
        )

    # Get the page
    page = sites_repo.get_page(site_id=site_id, page_id=page_id)
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Page not found.",
        )

    # Validate slug uniqueness if being changed
    if payload.slug and payload.slug != page.slug:
        if not sites_repo.check_slug_unique(
            site_id=site_id, slug=payload.slug, exclude_page_id=str(page.id)
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Slug '{payload.slug}' is already in use on this site.",
            )

    # Validate design system if being changed (including explicit clear)
    if "designSystemId" in payload.model_fields_set:
        if payload.designSystemId is None:
            page.design_system_id = None
        else:
            from app.routers.funnels import _validate_design_system

            _validate_design_system(
                session=session,
                org_id=auth.org_id,
                client_id=clientId,
                design_system_id=payload.designSystemId,
            )
            page.design_system_id = str(
                _parse_uuid_or_400(payload.designSystemId, "designSystemId")
            )

    # Update fields
    if payload.name:
        page.name = payload.name
    if payload.slug:
        page.slug = payload.slug

    page = sites_repo.update_page(page=page)
    session.commit()

    # Get latest versions
    latest_draft = sites_repo.latest_version_for_page(page_id=str(page.id), status="draft")
    latest_approved = sites_repo.latest_version_for_page(page_id=str(page.id), status="approved")

    design_system_tokens = _resolve_site_design_system_tokens(
        session=session,
        org_id=auth.org_id,
        client_id=clientId,
        site=site,
        page=page,
    )

    return SitePageEditorResponse(
        site={
            "id": str(site.id),
            "name": site.name,
            "routeSlug": site.route_slug,
            "siteFamily": site.site_family,
            "siteType": site.site_type,
            "commerceProvider": site.commerce_provider,
            "productId": str(site.product_id) if site.product_id else None,
            "designSystemId": str(site.design_system_id) if site.design_system_id else None,
        },
        page={
            "id": str(page.id),
            "siteId": str(page.site_id),
            "name": page.name,
            "slug": page.slug,
            "pageType": page.page_type,
            "templateId": page.template_id,
            "ordering": page.ordering,
            "designSystemId": str(page.design_system_id) if page.design_system_id else None,
        },
        latestDraft={
            "id": str(latest_draft.id),
            "status": latest_draft.status,
            "puckData": latest_draft.puck_data,
            "createdAt": latest_draft.created_at.isoformat(),
        }
        if latest_draft
        else None,
        latestApproved={
            "id": str(latest_approved.id),
            "status": latest_approved.status,
            "puckData": latest_approved.puck_data,
            "createdAt": latest_approved.created_at.isoformat(),
        }
        if latest_approved
        else None,
        designSystemTokens=design_system_tokens,
    )


@router.post("/{site_id}/pages/{page_id}/versions", response_model=SitePageVersionSummary)
def create_site_page_version(
    site_id: str,
    page_id: str,
    payload: SitePageVersionCreateRequest,
    clientId: str = Query(..., description="Workspace ID"),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Create a new version for a site page."""
    # Validate workspace ownership
    client = session.scalars(
        select(Client).where(
            Client.org_id == UUID(auth.org_id),
            Client.id == _parse_uuid_or_400(clientId, "clientId"),
        )
    ).first()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or does not belong to this organization.",
        )

    # Get the site
    sites_repo = SitesRuntimeRepository(session)
    site = sites_repo.get_site(
        org_id=str(UUID(auth.org_id)),
        client_id=str(UUID(clientId)),
        site_id=site_id,
    )

    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found.",
        )

    # Get the page
    page = sites_repo.get_page(site_id=site_id, page_id=page_id)
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Page not found.",
        )

    # Validate status
    valid_statuses = ["draft", "approved"]
    if payload.status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}",
        )

    # Create the new version
    version = sites_repo.create_page_version(
        page_id=str(page.id),
        puck_data=payload.puckData,
        provenance=payload.provenance or {"source": "editor"},
        status=payload.status,
    )

    session.commit()
    session.refresh(version)

    return {
        "id": str(version.id),
        "status": version.status,
        "puckData": version.puck_data,
        "createdAt": version.created_at.isoformat(),
    }


@router.post("/{site_id}/publish", response_model=dict[str, Any])
def publish_site(
    site_id: str,
    clientId: str = Query(..., description="Workspace ID"),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Publish a site, creating an immutable snapshot and runtime artifact.

    This endpoint:
    - Validates the site exists and belongs to the workspace
    - Validates all pages have publishable versions
    - Validates funnel steps point to valid site pages
    - Validates product bindings point to existing products/pages
    - Creates an immutable snapshot in site_publications* tables
    - Persists a site_runtime_bundle artifact
    - Returns publish metadata
    """
    from sqlalchemy import select

    from app.db.models import Client, Artifact
    from app.schemas.sites import SitePublishResponse
    from app.services.site_publications import (
        SitePublicationError,
        validate_site_for_publish,
        create_site_publication,
        list_site_publication_pages,
        list_site_publication_funnels,
        list_site_publication_product_bindings,
    )
    from app.services.deploy import (
        persist_site_runtime_bundle_artifact,
    )

    # Validate workspace ownership
    client = session.scalars(
        select(Client).where(
            Client.org_id == UUID(auth.org_id),
            Client.id == _parse_uuid_or_400(clientId, "clientId"),
        )
    ).first()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or does not belong to this organization.",
        )

    # Get the site
    sites_repo = SitesRuntimeRepository(session)
    site = sites_repo.get_site(
        org_id=str(UUID(auth.org_id)),
        client_id=str(UUID(clientId)),
        site_id=site_id,
    )

    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found.",
        )

    # Validate site is ready for publishing
    try:
        validate_site_for_publish(
            session=session,
            site_id=site_id,
            org_id=str(UUID(auth.org_id)),
        )
    except SitePublicationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # Create immutable publication snapshot
    try:
        publication = create_site_publication(
            session=session,
            site_id=site_id,
            created_by=auth.user_id,
            meta={
                "clientId": clientId,
                "publishedBy": auth.user_id,
            },
        )
    except SitePublicationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create publication snapshot: {exc}",
        )

    # Persist site_runtime_bundle artifact
    try:
        artifact_result = persist_site_runtime_bundle_artifact(
            session=session,
            org_id=str(UUID(auth.org_id)),
            site_id=site_id,
            publication_id=publication.id,
            created_by_user_id=auth.user_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to persist runtime artifact: {exc}",
        )

    # Get counts for response
    page_count = len(list_site_publication_pages(session, publication_id=publication.id))
    funnel_count = len(list_site_publication_funnels(session, publication_id=publication.id))
    binding_count = len(
        list_site_publication_product_bindings(session, publication_id=publication.id)
    )

    site.active_site_publication_id = publication.id
    site.status = "published"
    session.add(site)

    session.commit()

    return SitePublishResponse(
        publicationId=str(publication.id),
        artifactId=str(artifact_result["artifact_id"]),
        artifactVersion=artifact_result["artifact_version"],
        siteId=site_id,
        routeSlug=site.route_slug or "",
        pageCount=page_count,
        funnelCount=funnel_count,
        productBindingCount=binding_count,
        publishedAt=publication.created_at.isoformat(),
    ).model_dump()
