"""Site management API endpoints.

This module provides endpoints for managing Site-based experiences backed by the existing
funnel/page runtime. Sites are funnels with experience_kind='site' and additional metadata.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.enums import FunnelPageVersionStatusEnum, FunnelPageVersionSourceEnum, FunnelStatusEnum
from app.db.models import Funnel, FunnelPage, FunnelPageVersion, Product
from app.db.repositories.funnels import (
    FunnelsRepository,
    FunnelPagesRepository,
    FunnelPageVersionsRepository,
)
from app.schemas.sites import (
    SiteFamilySummary,
    SiteFamilyDetail,
    SiteCreateRequest,
    SiteSummary,
    SiteDetail,
    SitePageDetail,
    SitePageBlueprintSummary,
    SiteMedusaConfigResponse,
    MedusaRuntimeConfig,
)
from app.services.site_blueprints import (
    list_site_families,
    get_site_family,
    get_entry_page_blueprint,
)
from app.services.funnel_templates import get_funnel_template, apply_template_assets
from app.services.design_systems import resolve_design_system_tokens
from app.services.funnels import default_puck_data, rewrite_internal_target_ids

router = APIRouter(prefix="/sites", tags=["sites"])


def _parse_uuid_or_400(value: str, field_name: str) -> UUID:
    try:
        return UUID(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must be a valid UUID.",
        ) from exc


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

    This endpoint requires a product context because the existing funnel runtime
    requires funnels to have a product_id for publication and public rendering.
    """
    # Validate the site family
    descriptor = get_site_family(payload.family)
    if not descriptor:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown site family: '{payload.family}'.",
        )

    # Validate product exists and belongs to the workspace
    if not payload.productId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="productId is required. Sites require a product context for publication.",
        )

    client_uuid = _parse_uuid_or_400(payload.clientId, "clientId")
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
    if payload.designSystemId:
        from app.routers.funnels import _validate_design_system

        design_system = _validate_design_system(
            session=session,
            org_id=auth.org_id,
            client_id=payload.clientId,
            design_system_id=payload.designSystemId,
        )
        design_system_tokens = design_system.tokens
    else:
        design_system_tokens = resolve_design_system_tokens(
            session=session,
            org_id=auth.org_id,
            client_id=payload.clientId,
        )

    try:
        # Create the funnel (site) row
        funnels_repo = FunnelsRepository(session)
        pages_repo = FunnelPagesRepository(session)
        versions_repo = FunnelPageVersionsRepository(session)

        # Generate unique route slug for the site
        route_slug = funnels_repo._generate_unique_route_slug(
            desired_slug=payload.name or f"{descriptor.family}-site"
        )

        # Create the funnel row directly (not using repository.create to avoid auto-commit)
        site_funnel = Funnel(
            org_id=UUID(auth.org_id),
            client_id=client_uuid,
            name=payload.name,
            description=payload.description or f"{descriptor.name} site",
            status=FunnelStatusEnum.draft,
            route_slug=route_slug,
            experience_kind="site",
            site_type=descriptor.site_type,
            site_family=descriptor.family,
            commerce_provider=descriptor.commerce_provider,
            product_id=product_uuid,
        )
        session.add(site_funnel)
        session.flush()  # Get the ID without committing

        # Create pages from blueprints
        created_pages: list[dict[str, Any]] = []
        page_id_map: dict[str, str] = {}  # Maps page_type to real page ID
        entry_page_id = None

        for blueprint in descriptor.page_blueprints:
            # Get the template for this page
            template = get_funnel_template(blueprint.template_id)
            if template:
                try:
                    template_puck_data = apply_template_assets(
                        session=session,
                        org_id=auth.org_id,
                        client_id=payload.clientId,
                        template=template,
                        design_system_tokens=design_system_tokens,
                    )
                except ValueError:
                    template_puck_data = default_puck_data()
            else:
                template_puck_data = default_puck_data()

            # Create the page
            page = FunnelPage(
                funnel_id=site_funnel.id,
                name=blueprint.name,
                slug=blueprint.slug,
                ordering=blueprint.ordering,
                template_id=blueprint.template_id,
                design_system_id=UUID(payload.designSystemId) if payload.designSystemId else None,
                page_type=blueprint.page_type,
            )
            session.add(page)
            session.flush()

            # Track page ID for link rewriting
            page_id_map[blueprint.page_type] = str(page.id)

            # Create the initial draft version
            version = FunnelPageVersion(
                page_id=page.id,
                status=FunnelPageVersionStatusEnum.draft,
                puck_data=template_puck_data,
                source=FunnelPageVersionSourceEnum.human,
                created_at=datetime.now(timezone.utc),
            )
            session.add(version)
            session.flush()

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
                    "isEntry": blueprint.is_entry,
                    "latestDraftVersionId": str(version.id),
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
            page_id = UUID(page_data["id"])
            page = session.scalars(select(FunnelPage).where(FunnelPage.id == page_id)).first()
            if not page:
                continue

            version = versions_repo.latest_for_page(
                page_id=str(page_id), status=FunnelPageVersionStatusEnum.draft
            )
            if not version:
                continue

            # Rewrite placeholder IDs to real page IDs
            rewritten_puck_data = rewrite_internal_target_ids(version.puck_data, placeholder_id_map)

            # Update the version with rewritten puck_data
            version.puck_data = rewritten_puck_data
            session.add(version)

        # Set entry page
        if entry_page_id:
            site_funnel.entry_page_id = entry_page_id
            session.add(site_funnel)

        # Commit all changes atomically
        session.commit()
        session.refresh(site_funnel)

        return {
            "id": str(site_funnel.id),
            "clientId": str(site_funnel.client_id),
            "name": site_funnel.name,
            "description": site_funnel.description,
            "status": site_funnel.status.value,
            "experienceKind": site_funnel.experience_kind,
            "siteType": site_funnel.site_type,
            "siteFamily": site_funnel.site_family,
            "commerceProvider": site_funnel.commerce_provider,
            "productId": str(site_funnel.product_id) if site_funnel.product_id else None,
            "entryPageId": entry_page_id,
            "pages": created_pages,
            "createdAt": site_funnel.created_at.isoformat(),
            "updatedAt": site_funnel.updated_at.isoformat(),
        }

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
    from app.db.models import Client

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

    # Query funnels with experience_kind='site'
    sites = session.scalars(
        select(Funnel)
        .where(
            Funnel.org_id == UUID(auth.org_id),
            Funnel.client_id == UUID(clientId),
            Funnel.experience_kind == "site",
        )
        .order_by(Funnel.created_at.desc())
    ).all()

    return [
        {
            "id": str(site.id),
            "clientId": str(site.client_id),
            "name": site.name,
            "description": site.description,
            "status": site.status.value,
            "siteType": site.site_type,
            "siteFamily": site.site_family,
            "commerceProvider": site.commerce_provider,
            "productId": str(site.product_id) if site.product_id else None,
            "createdAt": site.created_at.isoformat(),
            "updatedAt": site.updated_at.isoformat(),
        }
        for site in sites
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
    from app.db.models import Client

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

    # Get the funnel (site)
    site_funnel = session.scalars(
        select(Funnel).where(
            Funnel.org_id == UUID(auth.org_id),
            Funnel.id == _parse_uuid_or_400(site_id, "site_id"),
        )
    ).first()

    if not site_funnel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found.",
        )

    # Verify it's a site
    if site_funnel.experience_kind != "site":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not a site.",
        )

    # Verify client matches
    if str(site_funnel.client_id) != clientId:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Site does not belong to this workspace.",
        )

    # Get pages
    pages = session.scalars(
        select(FunnelPage)
        .where(FunnelPage.funnel_id == site_funnel.id)
        .order_by(FunnelPage.ordering.asc(), FunnelPage.created_at.asc())
    ).all()

    page_summaries = []
    for page in pages:
        draft = session.scalars(
            select(FunnelPageVersion)
            .where(
                FunnelPageVersion.page_id == page.id,
                FunnelPageVersion.status == FunnelPageVersionStatusEnum.draft,
            )
            .order_by(FunnelPageVersion.created_at.desc())
        ).first()
        approved = session.scalars(
            select(FunnelPageVersion)
            .where(
                FunnelPageVersion.page_id == page.id,
                FunnelPageVersion.status == FunnelPageVersionStatusEnum.approved,
            )
            .order_by(FunnelPageVersion.created_at.desc())
        ).first()
        page_summaries.append(
            SitePageDetail(
                id=str(page.id),
                name=page.name,
                slug=page.slug,
                pageType=page.page_type,
                templateId=page.template_id,
                ordering=page.ordering,
                isEntry=str(page.id) == str(site_funnel.entry_page_id)
                if site_funnel.entry_page_id
                else False,
                latestDraftVersionId=str(draft.id) if draft else None,
                latestApprovedVersionId=str(approved.id) if approved else None,
            )
        )

    return SiteDetail(
        id=str(site_funnel.id),
        clientId=str(site_funnel.client_id),
        name=site_funnel.name,
        description=site_funnel.description,
        status=site_funnel.status.value,
        experienceKind=site_funnel.experience_kind,
        siteType=site_funnel.site_type,
        siteFamily=site_funnel.site_family,
        commerceProvider=site_funnel.commerce_provider,
        productId=str(site_funnel.product_id) if site_funnel.product_id else None,
        entryPageId=str(site_funnel.entry_page_id) if site_funnel.entry_page_id else None,
        pages=page_summaries,
        createdAt=site_funnel.created_at.isoformat(),
        updatedAt=site_funnel.updated_at.isoformat(),
    )


@router.get("/{site_id}/medusa-config", response_model=SiteMedusaConfigResponse)
def get_site_medusa_config(
    site_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteMedusaConfigResponse:
    """Get Medusa runtime configuration for a site.

    This endpoint exposes workspace-level Medusa config (base URL and publishable key)
    for direct frontend access. The frontend uses this to initialize the Medusa JS SDK
    without going through MOS as a commerce proxy.

    Returns null medusaConfig when:
    - Site is not found
    - Site family is not 'medusa-b2c-starter'
    - Medusa is not configured for the workspace

    This is intentional: we only expose Medusa config to frontends for B2C storefronts
    that are designed to talk to Medusa directly.
    """
    site_uuid = _parse_uuid_or_400(site_id, "site_id")

    # Get the site (funnel with experience_kind='site')
    # Sites are scoped to org_id only - client_id filtering happens at repository level
    site_funnel = session.scalars(
        select(Funnel).where(
            Funnel.id == site_uuid,
            Funnel.org_id == UUID(auth.org_id),
        )
    ).first()

    if not site_funnel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found.",
        )

    # Only expose Medusa config for medusa-b2c-starter family
    if site_funnel.site_family != "medusa-b2c-starter":
        return SiteMedusaConfigResponse(
            siteFamily=site_funnel.site_family,
            commerceProvider=site_funnel.commerce_provider,
            medusaConfig=None,
        )

    # Get workspace Medusa config
    from app.services.medusa_connection import get_client_medusa_config

    client_uuid = site_funnel.client_id
    medusa_config = get_client_medusa_config(
        session=session,
        org_id=str(site_funnel.org_id),
        client_id=str(client_uuid),
    )

    if not medusa_config or not medusa_config.base_url:
        return SiteMedusaConfigResponse(
            siteFamily=site_funnel.site_family,
            commerceProvider=site_funnel.commerce_provider,
            medusaConfig=MedusaRuntimeConfig(available=False),
        )

    if not medusa_config.publishable_key_encrypted:
        return SiteMedusaConfigResponse(
            siteFamily=site_funnel.site_family,
            commerceProvider=site_funnel.commerce_provider,
            medusaConfig=MedusaRuntimeConfig(
                baseUrl=medusa_config.base_url,
                available=False,
            ),
        )

    return SiteMedusaConfigResponse(
        siteFamily=site_funnel.site_family,
        commerceProvider=site_funnel.commerce_provider,
        medusaConfig=MedusaRuntimeConfig(
            baseUrl=medusa_config.base_url,
            publishableKey=medusa_config.publishable_key_encrypted,
            available=True,
        ),
    )
