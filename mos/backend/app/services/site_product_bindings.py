"""Service for managing site product page bindings.

This service handles:
- Creating and managing bindings between sites, products, and pages
- Product bindings support site/product/page role assignment
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Site, SitePage, SiteProductPageBinding, Product


class SiteProductBindingError(Exception):
    """Error during site product binding operations."""

    pass


def list_bindings(session: Session, site_id: str) -> list[SiteProductPageBinding]:
    """List all product bindings for a site."""
    stmt = (
        select(SiteProductPageBinding)
        .where(SiteProductPageBinding.site_id == site_id)
        .order_by(SiteProductPageBinding.created_at.desc())
    )
    return list(session.scalars(stmt).all())


def get_binding(session: Session, site_id: str, binding_id: str) -> SiteProductPageBinding | None:
    """Get a binding by ID within a site."""
    return session.scalars(
        select(SiteProductPageBinding).where(
            SiteProductPageBinding.id == binding_id,
            SiteProductPageBinding.site_id == site_id,
        )
    ).first()


def create_binding(
    session: Session,
    *,
    site_id: str,
    product_id: str,
    page_role: str,
    site_page_id: str | None = None,
    site_funnel_id: str | None = None,
    priority: int = 0,
    active: bool = True,
    variant_ids: list[str] | None = None,
    binding_context: dict[str, Any] | None = None,
) -> SiteProductPageBinding:
    """Create a new product binding for a site."""
    # Validate site exists
    site = session.scalars(select(Site).where(Site.id == site_id)).first()
    if not site:
        raise SiteProductBindingError(f"Site not found: {site_id}")

    # Validate product exists and belongs to org
    product = session.scalars(
        select(Product).where(
            Product.id == product_id,
            Product.client_id == site.client_id,
        )
    ).first()
    if not product:
        raise SiteProductBindingError(f"Product not found: {product_id}")

    # Validate site page if provided
    if site_page_id:
        page = session.scalars(
            select(SitePage).where(
                SitePage.id == site_page_id,
                SitePage.site_id == site_id,
            )
        ).first()
        if not page:
            raise SiteProductBindingError(f"Page not found: {site_page_id}")

    # Check for duplicate binding (same site + product + role)
    existing = session.scalars(
        select(SiteProductPageBinding).where(
            SiteProductPageBinding.site_id == site_id,
            SiteProductPageBinding.product_id == product_id,
            SiteProductPageBinding.page_role == page_role,
            SiteProductPageBinding.site_funnel_id == site_funnel_id,
        )
    ).first()
    if existing:
        raise SiteProductBindingError(
            f"Binding already exists for product {product_id} with role {page_role} in this funnel context"
        )

    now = datetime.now(timezone.utc)
    binding = SiteProductPageBinding(
        id=str(uuid4()),
        site_id=site_id,
        product_id=product_id,
        site_page_id=site_page_id,
        site_funnel_id=site_funnel_id,
        page_role=page_role,
        variant_ids=variant_ids or [],
        binding_context=binding_context or {},
        priority=priority,
        active=active,
        created_at=now,
        updated_at=now,
    )
    session.add(binding)
    session.flush()
    session.refresh(binding)

    return binding


def update_binding(
    session: Session,
    *,
    site_id: str,
    binding_id: str,
    site_page_id: str | None = None,
    page_role: str | None = None,
    site_funnel_id: str | None = None,
    priority: int | None = None,
    active: bool | None = None,
    variant_ids: list[str] | None = None,
    binding_context: dict[str, Any] | None = None,
) -> SiteProductPageBinding:
    """Update a product binding."""
    binding = get_binding(session, site_id, binding_id)
    if not binding:
        raise SiteProductBindingError(f"Binding not found: {binding_id}")

    # Validate site page if being changed
    if site_page_id is not None and site_page_id:
        page = session.scalars(
            select(SitePage).where(
                SitePage.id == site_page_id,
                SitePage.site_id == site_id,
            )
        ).first()
        if not page:
            raise SiteProductBindingError(f"Page not found: {site_page_id}")

    next_page_role = page_role if page_role is not None else binding.page_role
    next_site_funnel_id = site_funnel_id if site_funnel_id is not None else binding.site_funnel_id

    # Check for duplicate if role or funnel context is being changed
    if next_page_role != binding.page_role or next_site_funnel_id != binding.site_funnel_id:
        existing = session.scalars(
            select(SiteProductPageBinding).where(
                SiteProductPageBinding.id != binding_id,
                SiteProductPageBinding.site_id == site_id,
                SiteProductPageBinding.product_id == binding.product_id,
                SiteProductPageBinding.page_role == next_page_role,
                SiteProductPageBinding.site_funnel_id == next_site_funnel_id,
            )
        ).first()
        if existing:
            raise SiteProductBindingError(
                f"Binding already exists for product {binding.product_id} with role {next_page_role} in this funnel context"
            )

    # Update fields
    if site_page_id is not None:
        binding.site_page_id = site_page_id if site_page_id else None
    if page_role is not None:
        binding.page_role = page_role
    if site_funnel_id is not None:
        binding.site_funnel_id = site_funnel_id
    if priority is not None:
        binding.priority = priority
    if active is not None:
        binding.active = active
    if variant_ids is not None:
        binding.variant_ids = variant_ids
    if binding_context is not None:
        binding.binding_context = binding_context

    binding.updated_at = datetime.now(timezone.utc)
    session.add(binding)
    session.flush()
    session.refresh(binding)

    return binding


def delete_binding(session: Session, site_id: str, binding_id: str) -> bool:
    """Delete a product binding."""
    binding = get_binding(session, site_id, binding_id)
    if not binding:
        return False

    session.delete(binding)
    session.flush()
    return True


def get_product_binding_for_page(
    session: Session, site_id: str, site_page_id: str
) -> SiteProductPageBinding | None:
    """Get the binding for a specific site page."""
    return session.scalars(
        select(SiteProductPageBinding).where(
            SiteProductPageBinding.site_id == site_id,
            SiteProductPageBinding.site_page_id == site_page_id,
        )
    ).first()


def get_bindings_for_product(
    session: Session, site_id: str, product_id: str
) -> list[SiteProductPageBinding]:
    """Get all bindings for a specific product in a site."""
    return list(
        session.scalars(
            select(SiteProductPageBinding).where(
                SiteProductPageBinding.site_id == site_id,
                SiteProductPageBinding.product_id == product_id,
            )
        ).all()
    )
