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

from app.db.models import (
    Campaign,
    Site,
    SiteFunnel,
    SiteFunnelPath,
    SiteFunnelPathStep,
    SiteFunnelStep,
    SiteFunnelStepOption,
    SitePage,
)


class SiteFunnelError(Exception):
    """Error during site funnel operations."""

    pass


_FUNNEL_VARIANT_STATUSES = {"draft", "active", "paused", "archived"}


def _validate_variant_status(status: str) -> str:
    cleaned = (status or "").strip()
    if cleaned not in _FUNNEL_VARIANT_STATUSES:
        raise SiteFunnelError(
            "Invalid status. Must be one of: "
            f"{', '.join(sorted(_FUNNEL_VARIANT_STATUSES))}"
        )
    return cleaned


def _validate_non_negative_weight(weight: int | None, field_name: str) -> int | None:
    if weight is None:
        return None
    if weight < 0:
        raise SiteFunnelError(f"{field_name} must be >= 0 when provided.")
    return weight


def _get_site_or_error(session: Session, site_id: str) -> Site:
    site = session.scalars(select(Site).where(Site.id == site_id)).first()
    if not site:
        raise SiteFunnelError(f"Site not found: {site_id}")
    return site


def _get_page_or_error(session: Session, *, site_id: str, page_id: str) -> SitePage:
    page = session.scalars(
        select(SitePage).where(SitePage.id == page_id, SitePage.site_id == site_id)
    ).first()
    if not page:
        raise SiteFunnelError(f"Page not found: {page_id}")
    return page


def _get_step_or_error(session: Session, *, funnel_id: str, step_id: str) -> SiteFunnelStep:
    step = session.scalars(
        select(SiteFunnelStep).where(
            SiteFunnelStep.id == step_id,
            SiteFunnelStep.site_funnel_id == funnel_id,
        )
    ).first()
    if not step:
        raise SiteFunnelError(f"Funnel step not found: {step_id}")
    return step


def _get_step_option_for_page(
    session: Session,
    *,
    step_id: str,
    page_id: str,
) -> SiteFunnelStepOption | None:
    return session.scalars(
        select(SiteFunnelStepOption).where(
            SiteFunnelStepOption.site_funnel_step_id == step_id,
            SiteFunnelStepOption.site_page_id == page_id,
        )
    ).first()


def _create_primary_step_option(
    session: Session,
    *,
    step: SiteFunnelStep,
    page: SitePage,
    now: datetime,
) -> SiteFunnelStepOption:
    option = SiteFunnelStepOption(
        id=str(uuid4()),
        site_funnel_step_id=step.id,
        site_page_id=page.id,
        option_key="primary",
        label=page.name,
        status="active",
        traffic_weight=100,
        is_control=True,
        metadata_json={"createdFromPrimaryStepPage": True},
        created_at=now,
        updated_at=now,
    )
    session.add(option)
    return option


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
    _get_site_or_error(session, site_id)

    # Validate entry page if provided
    if entry_page_id:
        _get_page_or_error(session, site_id=site_id, page_id=entry_page_id)

    # Validate steps pages exist
    pages_by_id: dict[str, SitePage] = {}
    if steps:
        for step in steps:
            page_id = step.get("site_page_id")
            if page_id:
                pages_by_id[str(page_id)] = _get_page_or_error(
                    session, site_id=site_id, page_id=str(page_id)
                )

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
            page = pages_by_id.get(str(step["site_page_id"]))
            if page is None:
                raise SiteFunnelError(f"Page not found for step: {step['site_page_id']}")
            session.flush()
            _create_primary_step_option(session, step=funnel_step, page=page, now=now)

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
    valid_statuses = ["draft", "active", "paused", "archived"]
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
    page = _get_page_or_error(session, site_id=site_id, page_id=site_page_id)
    now = datetime.now(timezone.utc)
    step = SiteFunnelStep(
        id=str(uuid4()),
        site_funnel_id=funnel_id,
        site_page_id=site_page_id,
        ordering=ordering,
        step_role=step_role,
        cta_label=cta_label,
        created_at=now,
    )
    session.add(step)
    session.flush()
    _create_primary_step_option(session, step=step, page=page, now=now)
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
    path_step = session.scalars(
        select(SiteFunnelPathStep).where(SiteFunnelPathStep.site_funnel_step_id == step_id)
    ).first()
    if path_step:
        raise SiteFunnelError("Cannot delete a funnel step that is used by a funnel path.")
    session.delete(step)
    session.flush()
    return True


def list_step_options(session: Session, *, step_id: str) -> list[SiteFunnelStepOption]:
    stmt = (
        select(SiteFunnelStepOption)
        .where(SiteFunnelStepOption.site_funnel_step_id == step_id)
        .order_by(
            SiteFunnelStepOption.is_control.desc(),
            SiteFunnelStepOption.created_at.asc(),
            SiteFunnelStepOption.option_key.asc(),
        )
    )
    return list(session.scalars(stmt).all())


def create_step_option(
    session: Session,
    *,
    site_id: str,
    funnel_id: str,
    step_id: str,
    site_page_id: str,
    option_key: str,
    label: str,
    status: str = "draft",
    traffic_weight: int | None = None,
    is_control: bool = False,
    metadata: dict[str, Any] | None = None,
) -> SiteFunnelStepOption:
    funnel = get_funnel(session, site_id, funnel_id)
    if not funnel:
        raise SiteFunnelError(f"Funnel not found: {funnel_id}")
    step = _get_step_or_error(session, funnel_id=funnel_id, step_id=step_id)
    page = _get_page_or_error(session, site_id=site_id, page_id=site_page_id)

    cleaned_key = option_key.strip()
    if not cleaned_key:
        raise SiteFunnelError("optionKey is required.")
    cleaned_label = label.strip()
    if not cleaned_label:
        raise SiteFunnelError("label is required.")

    duplicate_page = _get_step_option_for_page(session, step_id=step_id, page_id=site_page_id)
    if duplicate_page:
        raise SiteFunnelError("This page is already configured as an option for the funnel step.")
    duplicate_key = session.scalars(
        select(SiteFunnelStepOption).where(
            SiteFunnelStepOption.site_funnel_step_id == step.id,
            SiteFunnelStepOption.option_key == cleaned_key,
        )
    ).first()
    if duplicate_key:
        raise SiteFunnelError(f"Funnel step option key already exists: {cleaned_key}")

    now = datetime.now(timezone.utc)
    option = SiteFunnelStepOption(
        id=str(uuid4()),
        site_funnel_step_id=step.id,
        site_page_id=page.id,
        option_key=cleaned_key,
        label=cleaned_label,
        status=_validate_variant_status(status),
        traffic_weight=_validate_non_negative_weight(traffic_weight, "trafficWeight"),
        is_control=is_control,
        metadata_json=metadata or {},
        created_at=now,
        updated_at=now,
    )
    session.add(option)
    session.flush()
    session.refresh(option)
    return option


def delete_step_option(
    session: Session,
    *,
    funnel_id: str,
    step_id: str,
    option_id: str,
) -> bool:
    _get_step_or_error(session, funnel_id=funnel_id, step_id=step_id)
    option = session.scalars(
        select(SiteFunnelStepOption).where(
            SiteFunnelStepOption.id == option_id,
            SiteFunnelStepOption.site_funnel_step_id == step_id,
        )
    ).first()
    if not option:
        return False
    path_step = session.scalars(
        select(SiteFunnelPathStep).where(SiteFunnelPathStep.site_funnel_step_option_id == option_id)
    ).first()
    if path_step:
        raise SiteFunnelError("Cannot delete a step option that is used by a funnel path.")
    session.delete(option)
    session.flush()
    return True


def list_paths(session: Session, *, funnel_id: str) -> list[SiteFunnelPath]:
    stmt = (
        select(SiteFunnelPath)
        .where(SiteFunnelPath.site_funnel_id == funnel_id)
        .order_by(
            SiteFunnelPath.is_control.desc(),
            SiteFunnelPath.created_at.asc(),
            SiteFunnelPath.slug.asc(),
        )
    )
    return list(session.scalars(stmt).all())


def get_path(session: Session, *, funnel_id: str, path_id: str) -> SiteFunnelPath | None:
    return session.scalars(
        select(SiteFunnelPath).where(
            SiteFunnelPath.id == path_id,
            SiteFunnelPath.site_funnel_id == funnel_id,
        )
    ).first()


def list_path_steps(session: Session, *, path_id: str) -> list[SiteFunnelPathStep]:
    stmt = (
        select(SiteFunnelPathStep)
        .where(SiteFunnelPathStep.site_funnel_path_id == path_id)
        .order_by(SiteFunnelPathStep.ordering.asc())
    )
    return list(session.scalars(stmt).all())


def create_path(
    session: Session,
    *,
    site_id: str,
    funnel_id: str,
    name: str,
    slug: str,
    status: str = "draft",
    campaign_id: str | None = None,
    traffic_weight: int | None = None,
    is_control: bool = False,
    experiment_spec_id: str | None = None,
    variant_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    steps: list[dict[str, str]],
) -> SiteFunnelPath:
    site = _get_site_or_error(session, site_id)
    funnel = get_funnel(session, site_id, funnel_id)
    if not funnel:
        raise SiteFunnelError(f"Funnel not found: {funnel_id}")
    if campaign_id:
        campaign = session.scalars(
            select(Campaign).where(
                Campaign.id == campaign_id,
                Campaign.org_id == site.org_id,
                Campaign.client_id == site.client_id,
            )
        ).first()
        if not campaign:
            raise SiteFunnelError(f"Campaign not found for site funnel path: {campaign_id}")

    cleaned_name = name.strip()
    if not cleaned_name:
        raise SiteFunnelError("name is required.")
    cleaned_slug = slug.strip()
    if not cleaned_slug:
        raise SiteFunnelError("slug is required.")
    if not steps:
        raise SiteFunnelError("steps must include one page selection for each funnel step.")

    duplicate_slug = session.scalars(
        select(SiteFunnelPath).where(
            SiteFunnelPath.site_funnel_id == funnel.id,
            SiteFunnelPath.slug == cleaned_slug,
        )
    ).first()
    if duplicate_slug:
        raise SiteFunnelError(f"Funnel path slug already exists: {cleaned_slug}")

    funnel_steps = get_funnel_steps(session, str(funnel.id))
    funnel_step_ids = {str(step.id) for step in funnel_steps}
    requested_step_ids = {str(step.get("site_funnel_step_id") or "") for step in steps}
    missing_step_ids = sorted(funnel_step_ids.difference(requested_step_ids))
    extra_step_ids = sorted(requested_step_ids.difference(funnel_step_ids))
    if missing_step_ids:
        raise SiteFunnelError(
            "Funnel path is missing page selections for step ids: " + ", ".join(missing_step_ids)
        )
    if extra_step_ids:
        raise SiteFunnelError(
            "Funnel path includes step ids that do not belong to this funnel: "
            + ", ".join(extra_step_ids)
        )

    seen_step_ids: set[str] = set()
    resolved_steps: list[tuple[SiteFunnelStep, SiteFunnelStepOption]] = []
    steps_by_id = {str(step.id): step for step in funnel_steps}
    for raw_step in steps:
        step_id = str(raw_step.get("site_funnel_step_id") or "").strip()
        page_id = str(raw_step.get("site_page_id") or "").strip()
        if not step_id or not page_id:
            raise SiteFunnelError("Each path step requires siteFunnelStepId and sitePageId.")
        if step_id in seen_step_ids:
            raise SiteFunnelError(f"Funnel path includes duplicate step id: {step_id}")
        seen_step_ids.add(step_id)
        step = steps_by_id[step_id]
        _get_page_or_error(session, site_id=site_id, page_id=page_id)
        option = _get_step_option_for_page(session, step_id=step_id, page_id=page_id)
        if not option:
            raise SiteFunnelError(
                f"Page {page_id} is not configured as an option for funnel step {step_id}."
            )
        resolved_steps.append((step, option))

    now = datetime.now(timezone.utc)
    path = SiteFunnelPath(
        id=str(uuid4()),
        site_funnel_id=funnel.id,
        campaign_id=campaign_id,
        name=cleaned_name,
        slug=cleaned_slug,
        status=_validate_variant_status(status),
        traffic_weight=_validate_non_negative_weight(traffic_weight, "trafficWeight"),
        is_control=is_control,
        experiment_spec_id=experiment_spec_id,
        variant_id=variant_id,
        metadata_json=metadata or {},
        created_at=now,
        updated_at=now,
    )
    session.add(path)
    session.flush()

    for step, option in sorted(resolved_steps, key=lambda item: item[0].ordering):
        path_step = SiteFunnelPathStep(
            id=str(uuid4()),
            site_funnel_path_id=path.id,
            site_funnel_step_id=step.id,
            site_funnel_step_option_id=option.id,
            site_page_id=option.site_page_id,
            ordering=step.ordering,
            step_role=step.step_role,
            created_at=now,
        )
        session.add(path_step)

    session.flush()
    session.refresh(path)
    return path


def delete_path(session: Session, *, funnel_id: str, path_id: str) -> bool:
    path = get_path(session, funnel_id=funnel_id, path_id=path_id)
    if not path:
        return False
    session.delete(path)
    session.flush()
    return True
