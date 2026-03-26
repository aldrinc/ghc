"""Service for managing site funnels.

This service handles:
- Creating and managing funnels scoped to a site
- Funnel steps reference existing site pages
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Site, SiteFunnel, SiteFunnelStep, SitePage


class SiteFunnelError(Exception):
    """Error during site funnel operations."""

    pass


def list_funnels(session: Session, site_id: str) -> list[SiteFunnel]:
    """List all funnels for a site."""
    stmt = (
        select(SiteFunnel)
        .where(SiteFunnel.site_id == site_id)
        .order_by(SiteFunnel.created_at.desc())
    )
    return list(session.scalars(stmt).all())


def list_workspace_funnels(session: Session, client_id: str) -> list[tuple[SiteFunnel, str]]:
    stmt = (
        select(SiteFunnel, Site.name)
        .join(Site, Site.id == SiteFunnel.site_id)
        .where(Site.client_id == client_id)
        .order_by(SiteFunnel.created_at.desc())
    )
    return list(session.execute(stmt).all())


def get_funnel(session: Session, site_id: str, funnel_id: str) -> SiteFunnel | None:
    """Get a funnel by ID within a site."""
    return session.scalars(
        select(SiteFunnel).where(
            SiteFunnel.id == funnel_id,
            SiteFunnel.site_id == site_id,
        )
    ).first()


def create_funnel(
    session: Session,
    *,
    site_id: str,
    name: str,
    description: str | None = None,
    funnel_type: str = "checkout",
    entry_page_id: str | None = None,
    product_id: str | None = None,
    selected_offer_id: str | None = None,
    tracking_config: dict[str, Any] | None = None,
    steps: list[dict[str, Any]] | None = None,
) -> SiteFunnel:
    """Create a new funnel for a site."""
    # Validate site exists
    site = session.scalars(select(Site).where(Site.id == site_id)).first()
    if not site:
        raise SiteFunnelError(f"Site not found: {site_id}")

    # Validate entry page if provided
    if entry_page_id:
        page = session.scalars(
            select(SitePage).where(
                SitePage.id == entry_page_id,
                SitePage.site_id == site_id,
            )
        ).first()
        if not page:
            raise SiteFunnelError(f"Page not found: {entry_page_id}")

    # Validate steps pages exist
    if steps:
        for step in steps:
            page_id = step.get("site_page_id")
            if page_id:
                page = session.scalars(
                    select(SitePage).where(
                        SitePage.id == page_id,
                        SitePage.site_id == site_id,
                    )
                ).first()
                if not page:
                    raise SiteFunnelError(f"Page not found for step: {page_id}")

    now = datetime.now(timezone.utc)
    funnel = SiteFunnel(
        id=str(uuid4()),
        site_id=site_id,
        name=name,
        description=description,
        funnel_type=funnel_type,
        entry_page_id=entry_page_id,
        product_id=product_id,
        selected_offer_id=selected_offer_id,
        tracking_config=tracking_config,
        status="draft",
        created_at=now,
        updated_at=now,
    )
    session.add(funnel)
    session.flush()

    # Create funnel steps
    created_steps = []
    if steps:
        for step in steps:
            funnel_step = SiteFunnelStep(
                id=str(uuid4()),
                site_funnel_id=funnel.id,
                site_page_id=step["site_page_id"],
                ordering=step.get("ordering", 0),
                step_role=step.get("step_role"),
                cta_label=step.get("cta_label"),
                created_at=now,
            )
            session.add(funnel_step)
            created_steps.append(funnel_step)

    session.flush()
    session.refresh(funnel)

    return funnel


def update_funnel(
    session: Session,
    *,
    site_id: str,
    funnel_id: str,
    name: str | None = None,
    description: str | None = None,
    status: str | None = None,
    funnel_type: str | None = None,
    entry_page_id: str | None = None,
    product_id: str | None = None,
    selected_offer_id: str | None = None,
    tracking_config: dict[str, Any] | None = None,
) -> SiteFunnel:
    """Update a funnel."""
    funnel = get_funnel(session, site_id, funnel_id)
    if not funnel:
        raise SiteFunnelError(f"Funnel not found: {funnel_id}")

    # Validate status if provided
    valid_statuses = ["draft", "active", "archived"]
    if status and status not in valid_statuses:
        raise SiteFunnelError(f"Invalid status. Must be one of: {valid_statuses}")

    # Validate entry page if provided
    if entry_page_id:
        page = session.scalars(
            select(SitePage).where(
                SitePage.id == entry_page_id,
                SitePage.site_id == site_id,
            )
        ).first()
        if not page:
            raise SiteFunnelError(f"Page not found: {entry_page_id}")

    # Update fields
    if name is not None:
        funnel.name = name
    if description is not None:
        funnel.description = description
    if status is not None:
        funnel.status = status
    if funnel_type is not None:
        funnel.funnel_type = funnel_type
    if entry_page_id is not None:
        funnel.entry_page_id = entry_page_id
    if product_id is not None:
        funnel.product_id = product_id
    if selected_offer_id is not None:
        funnel.selected_offer_id = selected_offer_id
    if tracking_config is not None:
        funnel.tracking_config = tracking_config

    funnel.updated_at = datetime.now(timezone.utc)
    session.add(funnel)
    session.flush()
    session.refresh(funnel)

    return funnel


def get_funnel_steps(session: Session, funnel_id: str) -> list[SiteFunnelStep]:
    """Get all steps for a funnel."""
    stmt = (
        select(SiteFunnelStep)
        .where(SiteFunnelStep.site_funnel_id == funnel_id)
        .order_by(SiteFunnelStep.ordering)
    )
    return list(session.scalars(stmt).all())


def delete_funnel(session: Session, site_id: str, funnel_id: str) -> bool:
    """Delete a funnel and its steps."""
    funnel = get_funnel(session, site_id, funnel_id)
    if not funnel:
        return False

    session.delete(funnel)
    session.flush()
    return True


def create_funnel_step(
    session: Session,
    *,
    site_id: str,
    funnel_id: str,
    site_page_id: str,
    ordering: int = 0,
    step_role: str | None = None,
    cta_label: str | None = None,
) -> SiteFunnelStep:
    funnel = get_funnel(session, site_id, funnel_id)
    if not funnel:
        raise SiteFunnelError(f"Funnel not found: {funnel_id}")
    page = session.scalars(
        select(SitePage).where(SitePage.id == site_page_id, SitePage.site_id == site_id)
    ).first()
    if not page:
        raise SiteFunnelError(f"Page not found: {site_page_id}")
    step = SiteFunnelStep(
        id=str(uuid4()),
        site_funnel_id=funnel_id,
        site_page_id=site_page_id,
        ordering=ordering,
        step_role=step_role,
        cta_label=cta_label,
        created_at=datetime.now(timezone.utc),
    )
    session.add(step)
    session.flush()
    session.refresh(step)
    return step


def delete_funnel_step(session: Session, *, funnel_id: str, step_id: str) -> bool:
    step = session.scalars(
        select(SiteFunnelStep).where(
            SiteFunnelStep.id == step_id, SiteFunnelStep.site_funnel_id == funnel_id
        )
    ).first()
    if not step:
        return False
    session.delete(step)
    session.flush()
    return True
