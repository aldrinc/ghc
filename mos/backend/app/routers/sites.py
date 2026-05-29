"""Site management API endpoints.

This module provides endpoints for managing Site-based experiences backed by the dedicated
site runtime (Site/SitePage/SitePageVersion), not the funnel runtime.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
    SitePublication,
)
from app.db.repositories.sites_runtime import SitesRuntimeRepository
from app.schemas.sites import (
    SiteFamilySummary,
    SiteFamilyDetail,
    SiteCreateRequest,
    SiteCreateTemplateRequest,
    SiteUpdateRequest,
    SiteSummary,
    SiteDetail,
    SitePageDetail,
    SitePageBlueprintSummary,
    SitePageUpdateRequest,
    SitePageVersionCreateRequest,
    SitePageEditorResponse,
    SitePageVersionSummary,
    SiteMedusaConfigResponse,
    MedusaRuntimeConfig,
)
from app.schemas.commerce import (
    SiteCommerceCartCreateRequest,
    SiteCommerceCartResponse,
    SiteCommerceCartUpdateRequest,
    SiteCommerceLineItemAddRequest,
    SiteCommerceLineItemUpdateRequest,
)
from app.schemas.site_templates import SiteTemplateSummary
from app.schemas.funnels import FunnelPageAIGenerateRequest, FunnelPageAIGenerateResponse
from app.services.site_blueprints import (
    list_site_families,
    get_site_family,
    validate_theme_requirement,
)
from app.services.funnel_templates import get_funnel_template, apply_template_assets
from app.services.design_systems import resolve_design_system_tokens
from app.services.funnels import rewrite_internal_target_ids
from app.services.site_page_ai import generate_site_page_draft, SitePageAiError
from app.services.site_templates import (
    SiteTemplateError,
    create_template_from_site,
    get_template_pages,
    get_template_funnels,
    get_template_theme_requirement,
)
from app.services.medusa_connection import (
    get_client_medusa_config,
    get_stripe_account_profile_by_id,
)
from app.services.medusa_store_runtime import (
    filter_payment_providers_by_allowlist,
    get_medusa_store_config,
    medusa_add_cart_line_item,
    medusa_create_payment_collection,
    medusa_create_cart,
    medusa_delete_cart_line_item,
    medusa_get_cart,
    medusa_initialize_payment_session,
    medusa_list_payment_providers,
    medusa_update_cart,
    medusa_update_cart_line_item,
    resolve_default_payment_provider_id,
    validate_provider_id_against_allowlist,
)

router = APIRouter(prefix="/sites", tags=["sites"])


def _resolve_site_publication_state(session: Session, site: Site) -> tuple[str | None, str | None]:
    publication_id = str(site.active_site_publication_id) if site.active_site_publication_id else None
    if not publication_id:
        return None, None
    publication = session.scalars(
        select(SitePublication).where(SitePublication.id == site.active_site_publication_id)
    ).first()
    return publication_id, publication.created_at.isoformat() if publication and publication.created_at else None


def _resolve_medusa_runtime_stripe_account_id(
    *,
    session: Session,
    medusa_config,
) -> str | None:
    profile_id = medusa_config.stripe_account_profile_id
    if not profile_id:
        return None
    profile = get_stripe_account_profile_by_id(
        session=session,
        profile_id=str(profile_id),
    )
    if not profile:
        return None
    return profile.stripe_account_id


def _site_uses_b2c_medusa_runtime(site: Site) -> bool:
    if site.site_family == "medusa-b2b-starter":
        return False
    return site.commerce_provider == "medusa"


def _get_authenticated_site_or_404(
    *,
    site_id: str,
    auth: AuthContext,
    session: Session,
) -> Site:
    site_uuid = _parse_uuid_or_400(site_id, "site_id")
    site = session.scalars(
        select(Site).where(
            Site.id == site_uuid,
            Site.org_id == UUID(auth.org_id),
        )
    ).first()

    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found.",
        )

    return site


def _get_authenticated_site_medusa_store_config(
    *,
    site: Site,
    session: Session,
):
    if site.commerce_provider != "medusa":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This site does not use Medusa commerce.",
        )

    medusa_config = get_client_medusa_config(
        session=session,
        org_id=str(site.org_id),
        client_id=str(site.client_id),
    )
    if not medusa_config:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Medusa configuration not found for this workspace.",
        )

    config = get_medusa_store_config(
        session=session,
        org_id=str(site.org_id),
        client_id=str(site.client_id),
    )
    if not config:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Medusa Store API is not configured for this workspace. A publishable key is required.",
        )

    return config


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
    """Resolve design system tokens using explicit site theme binding mode.

    Resolution order:
    1. Page-level override (if page.design_system_id is set)
    2. Site mode resolution:
       - standalone: return None (no tokens)
       - workspace_default: resolve from workspace default design system
       - design_system: resolve from site.design_system_id
    """
    # Page-level override takes precedence
    if page and page.design_system_id:
        design_system_id = str(page.design_system_id)
        design_system = session.scalars(
            select(DesignSystem).where(
                DesignSystem.org_id == UUID(org_id),
                DesignSystem.id == UUID(design_system_id),
            )
        ).first()
        if not design_system:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    f"Page '{page.id}' references design_system_id '{design_system_id}' "
                    "which no longer exists. Please reconfigure the page override."
                ),
            )
        return design_system.tokens

    # Site-level resolution based on explicit theme binding mode
    site_mode = (
        site.theme_binding_mode.value
        if hasattr(site.theme_binding_mode, "value")
        else site.theme_binding_mode
    )

    if site_mode == "standalone":
        # Standalone sites have no design system binding
        return None

    if site_mode == "design_system":
        # Use the site's explicitly selected design system
        if not site.design_system_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    f"Site '{site.id}' has theme_binding_mode 'design_system' "
                    "but is missing a bound design_system_id. "
                    "This is an inconsistent state that should never occur."
                ),
            )
        design_system = session.scalars(
            select(DesignSystem).where(
                DesignSystem.org_id == UUID(org_id),
                DesignSystem.id == site.design_system_id,
            )
        ).first()
        if not design_system:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    f"Site '{site.id}' references design_system_id '{site.design_system_id}' "
                    "which no longer exists. Please reconfigure the site's theme binding."
                ),
            )
        return design_system.tokens

    # workspace_default mode - resolve from workspace/client default
    if site_mode == "workspace_default":
        return resolve_design_system_tokens(
            session=session,
            org_id=org_id,
            client_id=client_id,
        )

    # Unrecognized mode - this is an error
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=(
            f"Site '{site.id}' has unrecognized theme_binding_mode '{site_mode}'. "
            "Valid modes are: standalone, workspace_default, design_system."
        ),
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
            themeRequirement=f.theme_requirement,
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
        themeRequirement=descriptor.theme_requirement,
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
    theme_binding_mode = payload.themeBindingMode or "standalone"

    try:
        validate_theme_requirement(
            descriptor,
            theme_binding_mode=theme_binding_mode,
            subject=f"Site family '{descriptor.family}'",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # Validate theme binding mode semantics
    if theme_binding_mode == "design_system":
        if not payload.designSystemId:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="themeBindingMode 'design_system' requires a non-empty designSystemId.",
            )
        from app.routers.funnels import _validate_design_system

        design_system = _validate_design_system(
            session=session,
            org_id=auth.org_id,
            client_id=payload.clientId,
            design_system_id=payload.designSystemId,
        )
        design_system_tokens = design_system.tokens
        design_system_id = str(design_system.id)
    elif theme_binding_mode == "standalone":
        # standalone mode ignores any provided designSystemId
        design_system_id = None
        design_system_tokens = None
    else:
        # workspace_default mode - resolve from workspace default for template hydration
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
            theme_binding_mode=theme_binding_mode,
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
            # NOTE: Pages do NOT inherit site.design_system_id. They inherit from the site
            # at token-resolution time only when they don't have an explicit override.
            page = sites_repo.create_page(
                site_id=str(site.id),
                name=blueprint.name,
                slug=blueprint.slug,
                ordering=blueprint.ordering,
                template_id=blueprint.template_id,
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
                    "designSystemId": str(page.design_system_id) if page.design_system_id else None,
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
            "themeBindingMode": site.theme_binding_mode.value
            if hasattr(site.theme_binding_mode, "value")
            else site.theme_binding_mode,
            "routeSlug": site.route_slug,
            "primaryDomain": site.primary_domain,
            "templateId": str(site.site_template_id) if site.site_template_id else None,
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

    items: list[dict[str, Any]] = []
    for s in sites:
        active_site_publication_id, last_published_at = _resolve_site_publication_state(session, s)
        items.append({
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
            "themeBindingMode": s.theme_binding_mode.value
            if hasattr(s.theme_binding_mode, "value")
            else s.theme_binding_mode,
            "routeSlug": s.route_slug,
            "primaryDomain": s.primary_domain,
            "templateId": str(s.site_template_id) if s.site_template_id else None,
            "activeSitePublicationId": active_site_publication_id,
            "lastPublishedAt": last_published_at,
            "createdAt": s.created_at.isoformat(),
            "updatedAt": s.updated_at.isoformat(),
        })
    return items


@router.get("/{site_id}", response_model=SiteDetail)
def get_site(
    site_id: str,
    clientId: str | None = Query(None, description="Workspace ID"),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteDetail:
    """Get detailed information about a specific site."""
    parsed_site_id = _parse_uuid_or_400(site_id, "siteId")

    # Validate workspace ownership when the caller scopes the request to a workspace.
    if clientId is not None:
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
        site_id=str(parsed_site_id),
    )

    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found.",
        )

    # Check if site belongs to the specified workspace when one is provided.
    if clientId is not None and str(site.client_id) != clientId:
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

    active_site_publication_id, last_published_at = _resolve_site_publication_state(session, site)

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
        themeBindingMode=site.theme_binding_mode.value
        if hasattr(site.theme_binding_mode, "value")
        else site.theme_binding_mode,
        routeSlug=site.route_slug,
        primaryDomain=site.primary_domain,
        templateId=str(site.site_template_id) if site.site_template_id else None,
        activeSitePublicationId=active_site_publication_id,
        lastPublishedAt=last_published_at,
        entryPageId=str(site.entry_page_id) if site.entry_page_id else None,
        pages=page_summaries,
        createdAt=site.created_at.isoformat(),
        updatedAt=site.updated_at.isoformat(),
    )


@router.post(
    "/{site_id}/create-template",
    response_model=SiteTemplateSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_site_template_from_site(
    site_id: str,
    request: SiteCreateTemplateRequest,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteTemplateSummary:
    """Create a reusable site template from an existing site runtime record."""
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

    try:
        template = create_template_from_site(
            session,
            site_id=site_id,
            org_id=str(UUID(auth.org_id)),
            client_id=str(UUID(clientId)),
            name=request.name,
            description=request.description,
            created_by_user_external_id=auth.user_id,
        )
        session.commit()
        session.refresh(template)
    except SiteTemplateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return SiteTemplateSummary(
        id=str(template.id),
        family=template.family,
        name=template.name,
        description=template.description,
        siteType=template.site_type,
        commerceProvider=template.commerce_provider,
        themeRequirement=get_template_theme_requirement(template.family),
        isSystemTemplate=template.is_system_template,
        pageCount=len(get_template_pages(session, str(template.id))),
        funnelCount=len(get_template_funnels(session, str(template.id))),
        createdAt=template.created_at,
    )


@router.patch("/{site_id}", response_model=SiteDetail)
def update_site(
    site_id: str,
    payload: SiteUpdateRequest,
    clientId: str = Query(..., description="Workspace ID"),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteDetail:
    """Update site-level settings including theme binding configuration."""
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

    # Update basic fields
    if payload.name is not None:
        site.name = payload.name
    if payload.description is not None:
        site.description = payload.description
    if payload.routeSlug is not None:
        # Validate slug uniqueness if being changed
        if payload.routeSlug != site.route_slug:
            existing = sites_repo.get_site_by_route_slug(route_slug=payload.routeSlug)
            if existing and str(existing.id) != site_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Route slug '{payload.routeSlug}' is already in use.",
                )
        site.route_slug = payload.routeSlug
    if payload.primaryDomain is not None:
        site.primary_domain = payload.primaryDomain

    # Handle theme binding mode changes
    if payload.themeBindingMode is not None:
        theme_binding_mode = payload.themeBindingMode

        # Validate design_system mode requires designSystemId
        if theme_binding_mode == "design_system":
            if not payload.designSystemId:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="themeBindingMode 'design_system' requires a non-empty designSystemId.",
                )
            # Validate and set the design system
            from app.routers.funnels import _validate_design_system

            _validate_design_system(
                session=session,
                org_id=auth.org_id,
                client_id=clientId,
                design_system_id=payload.designSystemId,
            )
            site.design_system_id = str(
                _parse_uuid_or_400(payload.designSystemId, "designSystemId")
            )
            site.theme_binding_mode = theme_binding_mode
        elif theme_binding_mode == "standalone":
            # standalone mode clears design_system_id
            site.design_system_id = None
            site.theme_binding_mode = theme_binding_mode
        else:
            # workspace_default mode - clear site design_system_id
            site.design_system_id = None
            site.theme_binding_mode = theme_binding_mode

    # Handle designSystemId changes without mode change
    elif payload.designSystemId is not None:
        # If theme_binding_mode is design_system, allow designSystemId update
        current_mode = (
            site.theme_binding_mode.value
            if hasattr(site.theme_binding_mode, "value")
            else site.theme_binding_mode
        )
        if current_mode == "design_system":
            from app.routers.funnels import _validate_design_system

            _validate_design_system(
                session=session,
                org_id=auth.org_id,
                client_id=clientId,
                design_system_id=payload.designSystemId,
            )
            site.design_system_id = str(
                _parse_uuid_or_400(payload.designSystemId, "designSystemId")
            )
        # For other modes, designSystemId updates are ignored (not an error per spec)

    # Persist changes
    site = sites_repo.update_site(site=site)
    session.commit()
    session.refresh(site)

    # Get pages for response
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
        themeBindingMode=site.theme_binding_mode.value
        if hasattr(site.theme_binding_mode, "value")
        else site.theme_binding_mode,
        routeSlug=site.route_slug,
        primaryDomain=site.primary_domain,
        templateId=str(site.site_template_id) if site.site_template_id else None,
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


@router.post(
    "/{site_id}/pages/{page_id}/ai/generate",
    response_model=FunnelPageAIGenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
def ai_generate_site_page_draft(
    site_id: str,
    page_id: str,
    payload: FunnelPageAIGenerateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    try:
        assistant_message, version, puck_data = generate_site_page_draft(
            session=session,
            org_id=auth.org_id,
            user_id=auth.user_id,
            site_id=site_id,
            page_id=page_id,
            prompt=payload.prompt,
            messages=[message.model_dump() for message in payload.messages] if payload.messages else None,
            current_puck_data=payload.currentPuckData,
            model=payload.model,
            temperature=payload.temperature,
            max_tokens=payload.maxTokens,
            attached_assets=[asset.model_dump() for asset in payload.attachedAssets] if payload.attachedAssets else None,
            generate_images=payload.generateImages,
        )
    except SitePageAiError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return {
        "assistantMessage": assistant_message,
        "puckData": puck_data,
        "draftVersionId": str(version.id),
        "generatedImages": [],
        "generatedCarouselImages": [],
        "imagePlans": [],
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


@router.get("/{site_id}/medusa-config", response_model=SiteMedusaConfigResponse)
def get_site_medusa_config(
    site_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteMedusaConfigResponse:
    """Get Medusa runtime configuration for a canonical site.

    This exposes workspace-level Medusa config for B2C storefronts that are
    designed to call Medusa directly from the browser runtime.
    """
    site_uuid = _parse_uuid_or_400(site_id, "site_id")
    site = session.scalars(
        select(Site).where(
            Site.id == site_uuid,
            Site.org_id == UUID(auth.org_id),
        )
    ).first()

    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found.",
        )

    if not _site_uses_b2c_medusa_runtime(site):
        return SiteMedusaConfigResponse(
            siteFamily=site.site_family,
            commerceProvider=site.commerce_provider,
            medusaConfig=None,
        )

    medusa_config = get_client_medusa_config(
        session=session,
        org_id=str(site.org_id),
        client_id=str(site.client_id),
    )

    if not medusa_config or not medusa_config.base_url:
        return SiteMedusaConfigResponse(
            siteFamily=site.site_family,
            commerceProvider=site.commerce_provider,
            medusaConfig=MedusaRuntimeConfig(available=False),
        )

    if not medusa_config.publishable_key_encrypted:
        return SiteMedusaConfigResponse(
            siteFamily=site.site_family,
            commerceProvider=site.commerce_provider,
            medusaConfig=MedusaRuntimeConfig(
                baseUrl=medusa_config.base_url,
                available=False,
            ),
        )

    return SiteMedusaConfigResponse(
        siteFamily=site.site_family,
        commerceProvider=site.commerce_provider,
        medusaConfig=MedusaRuntimeConfig(
            baseUrl=medusa_config.base_url,
            publishableKey=medusa_config.publishable_key_encrypted,
            stripeAccountId=_resolve_medusa_runtime_stripe_account_id(
                session=session,
                medusa_config=medusa_config,
            ),
            available=True,
        ),
    )


@router.get("/{site_id}/medusa/cart", response_model=SiteCommerceCartResponse)
def get_site_medusa_cart(
    site_id: str,
    cart_id: str = Query(...),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Get a Medusa cart for an authenticated site preview."""
    site = _get_authenticated_site_or_404(site_id=site_id, auth=auth, session=session)
    config = _get_authenticated_site_medusa_store_config(site=site, session=session)
    cart = medusa_get_cart(config=config, cart_id=cart_id)
    return {"cart": cart}


@router.post("/{site_id}/medusa/cart", response_model=SiteCommerceCartResponse)
def create_site_medusa_cart(
    site_id: str,
    payload: SiteCommerceCartCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Create a Medusa cart for an authenticated site preview."""
    site = _get_authenticated_site_or_404(site_id=site_id, auth=auth, session=session)
    config = _get_authenticated_site_medusa_store_config(site=site, session=session)
    cart = medusa_create_cart(
        config=config,
        region_id=payload.region_id,
        country_code=payload.country_code,
        email=payload.email,
        shipping_address=payload.shipping_address,
        items=payload.items,
    )
    return {"cart": cart}


@router.post("/{site_id}/medusa/cart/{cart_id}", response_model=SiteCommerceCartResponse)
def update_site_medusa_cart(
    site_id: str,
    cart_id: str,
    payload: SiteCommerceCartUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Update a Medusa cart for an authenticated site preview."""
    site = _get_authenticated_site_or_404(site_id=site_id, auth=auth, session=session)
    config = _get_authenticated_site_medusa_store_config(site=site, session=session)
    cart = medusa_update_cart(
        config=config,
        cart_id=cart_id,
        email=payload.email,
        shipping_address=payload.shipping_address,
        billing_address=payload.billing_address,
    )
    return {"cart": cart}


@router.post("/{site_id}/medusa/cart/{cart_id}/items", response_model=SiteCommerceCartResponse)
def add_site_medusa_cart_item(
    site_id: str,
    cart_id: str,
    payload: SiteCommerceLineItemAddRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Add a Medusa cart line item for an authenticated site preview."""
    site = _get_authenticated_site_or_404(site_id=site_id, auth=auth, session=session)
    config = _get_authenticated_site_medusa_store_config(site=site, session=session)
    cart = medusa_add_cart_line_item(
        config=config,
        cart_id=cart_id,
        variant_id=payload.variant_id,
        quantity=payload.quantity,
    )
    return {"cart": cart}


@router.post("/{site_id}/medusa/cart/{cart_id}/items/{line_id}", response_model=SiteCommerceCartResponse)
def update_site_medusa_cart_item(
    site_id: str,
    cart_id: str,
    line_id: str,
    payload: SiteCommerceLineItemUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Update a Medusa cart line item for an authenticated site preview."""
    site = _get_authenticated_site_or_404(site_id=site_id, auth=auth, session=session)
    config = _get_authenticated_site_medusa_store_config(site=site, session=session)

    if payload.quantity == 0:
        medusa_delete_cart_line_item(
            config=config,
            cart_id=cart_id,
            line_id=line_id,
        )
        cart = medusa_get_cart(config=config, cart_id=cart_id)
    else:
        cart = medusa_update_cart_line_item(
            config=config,
            cart_id=cart_id,
            line_id=line_id,
            quantity=payload.quantity,
        )
    return {"cart": cart}


@router.delete("/{site_id}/medusa/cart/{cart_id}/items/{line_id}")
def delete_site_medusa_cart_item(
    site_id: str,
    cart_id: str,
    line_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Delete a Medusa cart line item for an authenticated site preview."""
    site = _get_authenticated_site_or_404(site_id=site_id, auth=auth, session=session)
    config = _get_authenticated_site_medusa_store_config(site=site, session=session)
    medusa_delete_cart_line_item(
        config=config,
        cart_id=cart_id,
        line_id=line_id,
    )
    return {"deleted": True}


@router.get("/{site_id}/medusa/payment-providers")
def get_site_medusa_payment_providers(
    site_id: str,
    region_id: str = Query(...),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """List Medusa payment providers for an authenticated site preview."""
    site_uuid = _parse_uuid_or_400(site_id, "site_id")
    site = session.scalars(
        select(Site).where(
            Site.id == site_uuid,
            Site.org_id == UUID(auth.org_id),
        )
    ).first()

    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found.",
        )

    if site.commerce_provider != "medusa":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This site does not use Medusa commerce.",
        )

    medusa_config = get_client_medusa_config(
        session=session,
        org_id=str(site.org_id),
        client_id=str(site.client_id),
    )
    if not medusa_config:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Medusa configuration not found for this workspace.",
        )

    config = get_medusa_store_config(
        session=session,
        org_id=str(site.org_id),
        client_id=str(site.client_id),
    )
    if not config:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Medusa Store API is not configured for this workspace. A publishable key is required.",
        )

    allowed_provider_ids = list(medusa_config.allowed_payment_provider_ids or [])
    default_payment_provider_id = medusa_config.default_payment_provider_id

    payment_providers = medusa_list_payment_providers(
        config=config,
        region_id=region_id,
    )
    filtered_providers = filter_payment_providers_by_allowlist(
        providers=payment_providers,
        allowed_provider_ids=allowed_provider_ids,
    )
    resolved_default = resolve_default_payment_provider_id(
        allowed_provider_ids=allowed_provider_ids,
        default_payment_provider_id=default_payment_provider_id,
        available_providers=filtered_providers,
    )

    return {
        "payment_providers": filtered_providers,
        "default_payment_provider_id": resolved_default,
    }


@router.post("/{site_id}/medusa/checkout/session")
def create_site_medusa_checkout_session(
    site_id: str,
    cart_id: str = Query(...),
    provider_id: str = Query(...),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Initialize a payment session for an authenticated site preview."""
    site_uuid = _parse_uuid_or_400(site_id, "site_id")
    site = session.scalars(
        select(Site).where(
            Site.id == site_uuid,
            Site.org_id == UUID(auth.org_id),
        )
    ).first()

    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found.",
        )

    if site.commerce_provider != "medusa":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This site does not use Medusa commerce.",
        )

    medusa_config = get_client_medusa_config(
        session=session,
        org_id=str(site.org_id),
        client_id=str(site.client_id),
    )
    if not medusa_config:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Medusa configuration not found for this workspace.",
        )

    config = get_medusa_store_config(
        session=session,
        org_id=str(site.org_id),
        client_id=str(site.client_id),
    )
    if not config:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Medusa Store API is not configured for this workspace. A publishable key is required.",
        )

    validate_provider_id_against_allowlist(
        provider_id=provider_id,
        allowed_provider_ids=list(medusa_config.allowed_payment_provider_ids or []),
    )

    payment_collection = medusa_create_payment_collection(
        config=config,
        cart_id=cart_id,
    )
    payment_collection = medusa_initialize_payment_session(
        config=config,
        payment_collection_id=payment_collection["id"],
        provider_id=provider_id,
    )

    return {"payment_collection": payment_collection}
