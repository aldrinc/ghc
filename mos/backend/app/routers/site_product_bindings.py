"""Site Product Bindings API endpoints.

Endpoints for managing product bindings scoped to a site.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.models import Client, Site, SitePage, SiteFunnel, SiteProductPageBinding
from app.schemas.site_product_bindings import (
    SiteProductBindingSummary,
    SiteProductBindingDetail,
    SiteProductBindingCreateRequest,
    SiteProductBindingUpdateRequest,
)
from app.services.site_product_bindings import (
    list_bindings,
    get_binding,
    create_binding,
    update_binding,
    delete_binding,
    SiteProductBindingError,
)

router = APIRouter(prefix="/sites/{site_id}/product-bindings", tags=["site-product-bindings"])
products_router = APIRouter(prefix="/products", tags=["site-product-bindings"])


def _serialize_binding(session: Session, binding) -> SiteProductBindingDetail:
    site = session.scalars(select(Site).where(Site.id == binding.site_id)).first()
    page = (
        session.scalars(select(SitePage).where(SitePage.id == binding.site_page_id)).first()
        if binding.site_page_id
        else None
    )
    funnel = (
        session.scalars(select(SiteFunnel).where(SiteFunnel.id == binding.site_funnel_id)).first()
        if binding.site_funnel_id
        else None
    )
    return SiteProductBindingDetail(
        id=str(binding.id),
        siteId=str(binding.site_id),
        productId=str(binding.product_id),
        sitePageId=str(binding.site_page_id) if binding.site_page_id else None,
        siteFunnelId=str(binding.site_funnel_id) if binding.site_funnel_id else None,
        pageRole=binding.page_role,
        variantIds=list(binding.variant_ids or []),
        bindingContext=dict(binding.binding_context or {}),
        priority=binding.priority,
        active=binding.active,
        site={"id": str(site.id), "name": site.name, "routeSlug": site.route_slug}
        if site
        else None,
        page={
            "id": str(page.id),
            "name": page.name,
            "slug": page.slug,
            "pageType": page.page_type,
        }
        if page
        else None,
        funnel={"id": str(funnel.id), "name": funnel.name} if funnel else None,
        createdAt=binding.created_at,
        updatedAt=binding.updated_at,
    )


def _get_workspace_or_404(session: Session, client_id: str, org_id: str) -> Client:
    """Validate workspace exists and belongs to the org."""
    try:
        UUID(client_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")

    client = session.scalars(
        select(Client).where(Client.id == client_id, Client.org_id == org_id)
    ).first()
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
    return client


def _parse_uuid_or_400(value: str, field_name: str) -> UUID:
    """Parse UUID or raise 400."""
    try:
        return UUID(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must be a valid UUID.",
        ) from exc


def _get_site_for_workspace_or_404(
    session: Session, *, site_id: str, client_id: str, org_id: str
) -> Site:
    site = session.scalars(
        select(Site).where(
            Site.id == site_id,
            Site.client_id == client_id,
            Site.org_id == org_id,
        )
    ).first()
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found.")
    return site


@router.get("", response_model=list[SiteProductBindingDetail])
def list_site_product_bindings(
    site_id: str,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[SiteProductBindingSummary]:
    """List all product bindings for a site."""
    # Validate workspace
    _get_workspace_or_404(session, clientId, auth.org_id)

    # Validate site_id format
    _parse_uuid_or_400(site_id, "siteId")
    _get_site_for_workspace_or_404(session, site_id=site_id, client_id=clientId, org_id=auth.org_id)

    bindings = list_bindings(session, site_id)
    return [_serialize_binding(session, b) for b in bindings]


@router.post("", response_model=SiteProductBindingDetail, status_code=status.HTTP_201_CREATED)
def create_site_product_binding(
    site_id: str,
    clientId: str,
    request: SiteProductBindingCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteProductBindingDetail:
    """Create a new product binding for a site."""
    # Validate workspace
    _get_workspace_or_404(session, clientId, auth.org_id)

    # Validate site_id format
    _parse_uuid_or_400(site_id, "siteId")
    _get_site_for_workspace_or_404(session, site_id=site_id, client_id=clientId, org_id=auth.org_id)

    try:
        binding = create_binding(
            session,
            site_id=site_id,
            product_id=request.productId,
            page_role=request.pageRole,
            site_page_id=request.sitePageId,
            site_funnel_id=request.siteFunnelId,
            priority=request.priority,
            active=request.active,
            variant_ids=request.variantIds,
            binding_context=request.bindingContext,
        )
        session.commit()
        return _serialize_binding(session, binding)
    except SiteProductBindingError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{binding_id}", status_code=status.HTTP_200_OK)
def delete_site_product_binding(
    site_id: str,
    binding_id: str,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    _get_workspace_or_404(session, clientId, auth.org_id)
    _get_site_for_workspace_or_404(session, site_id=site_id, client_id=clientId, org_id=auth.org_id)
    if not delete_binding(session, site_id, binding_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product binding not found."
        )
    session.commit()


@router.get("/{binding_id}", response_model=SiteProductBindingDetail)
def get_site_product_binding(
    site_id: str,
    binding_id: str,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteProductBindingDetail:
    """Get a specific product binding."""
    # Validate workspace
    _get_workspace_or_404(session, clientId, auth.org_id)

    # Validate IDs format
    _parse_uuid_or_400(site_id, "siteId")
    _parse_uuid_or_400(binding_id, "bindingId")
    _get_site_for_workspace_or_404(session, site_id=site_id, client_id=clientId, org_id=auth.org_id)

    binding = get_binding(session, site_id, binding_id)
    if not binding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product binding not found.",
        )

    return _serialize_binding(session, binding)


@router.patch("/{binding_id}", response_model=SiteProductBindingDetail)
def update_site_product_binding(
    site_id: str,
    binding_id: str,
    clientId: str,
    request: SiteProductBindingUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteProductBindingDetail:
    """Update a product binding."""
    # Validate workspace
    _get_workspace_or_404(session, clientId, auth.org_id)

    # Validate IDs format
    _parse_uuid_or_400(site_id, "siteId")
    _parse_uuid_or_400(binding_id, "bindingId")
    _get_site_for_workspace_or_404(session, site_id=site_id, client_id=clientId, org_id=auth.org_id)

    try:
        binding = update_binding(
            session,
            site_id=site_id,
            binding_id=binding_id,
            site_page_id=request.sitePageId,
            page_role=request.pageRole,
            site_funnel_id=request.siteFunnelId,
            priority=request.priority,
            active=request.active,
            variant_ids=request.variantIds,
            binding_context=request.bindingContext,
        )
        session.commit()
        return _serialize_binding(session, binding)
    except SiteProductBindingError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@products_router.get("/{product_id}/site-bindings", response_model=list[SiteProductBindingDetail])
def list_product_site_bindings(
    product_id: str,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[SiteProductBindingDetail]:
    _get_workspace_or_404(session, clientId, auth.org_id)
    bindings = session.scalars(
        select(SiteProductPageBinding)
        .join(Site, Site.id == SiteProductPageBinding.site_id)
        .where(
            SiteProductPageBinding.product_id == product_id,
            Site.client_id == clientId,
            Site.org_id == auth.org_id,
        )
    ).all()
    return [_serialize_binding(session, binding) for binding in bindings]


@products_router.get("/{product_id}/sites")
def list_product_sites(
    product_id: str,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    _get_workspace_or_404(session, clientId, auth.org_id)
    sites = session.scalars(
        select(Site)
        .where(Site.client_id == clientId, Site.org_id == auth.org_id)
        .order_by(Site.created_at.desc())
    ).all()
    bindings = session.scalars(
        select(SiteProductPageBinding)
        .join(Site, Site.id == SiteProductPageBinding.site_id)
        .where(
            SiteProductPageBinding.product_id == product_id,
            Site.client_id == clientId,
            Site.org_id == auth.org_id,
        )
    ).all()
    binding_site_ids = {str(binding.site_id) for binding in bindings}
    results: list[dict[str, Any]] = []
    for site in sites:
        uses_product = str(site.product_id) == product_id or str(site.id) in binding_site_ids
        if not uses_product:
            continue
        results.append(
            {
                "siteId": str(site.id),
                "siteName": site.name,
                "hasBinding": str(site.id) in binding_site_ids,
            }
        )
    return results
