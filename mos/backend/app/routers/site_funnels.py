"""Site Funnels API endpoints.

Endpoints for managing funnels scoped to a site.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.models import Client, Site, SitePage, SiteFunnelTemplateImport
from app.schemas.site_funnels import (
    SiteFunnelSummary,
    SiteFunnelDetail,
    SiteFunnelCreateRequest,
    SiteFunnelUpdateRequest,
    SiteFunnelStepSummary,
    SiteFunnelStepCreateRequest,
)
from app.services.site_funnels import (
    list_funnels,
    list_workspace_funnels,
    get_funnel,
    get_funnel_steps,
    create_funnel,
    update_funnel,
    delete_funnel,
    create_funnel_step,
    delete_funnel_step,
    SiteFunnelError,
)
from app.services.site_funnel_preparation import SiteFunnelPreparationError, prepare_site_funnel_template

router = APIRouter(prefix="/sites/{site_id}/funnels", tags=["site-funnels"])


def _serialize_step(session: Session, step) -> SiteFunnelStepSummary:
    page = session.scalars(select(SitePage).where(SitePage.id == step.site_page_id)).first()
    return SiteFunnelStepSummary(
        id=str(step.id),
        sitePageId=str(step.site_page_id),
        ordering=step.ordering,
        stepRole=step.step_role,
        ctaLabel=step.cta_label,
        transitionRule=None,
        page={
            "id": str(page.id),
            "name": page.name,
            "slug": page.slug,
            "pageType": page.page_type,
        }
        if page
        else None,
        createdAt=step.created_at,
    )


def _read_template_import_label(session: Session, template_import_id: str | None) -> str | None:
    if not template_import_id:
        return None
    template_import = session.scalars(
        select(SiteFunnelTemplateImport).where(SiteFunnelTemplateImport.id == template_import_id)
    ).first()
    if template_import is None:
        return None
    return template_import.source_label


def _serialize_funnel_summary(session: Session, funnel, site_name: str | None = None) -> SiteFunnelSummary:
    prepared_page = None
    if funnel.prepared_page_id:
        prepared_page = session.scalars(
            select(SitePage).where(SitePage.id == funnel.prepared_page_id)
        ).first()
    return SiteFunnelSummary(
        id=str(funnel.id),
        siteId=str(funnel.site_id),
        siteName=site_name,
        name=funnel.name,
        description=funnel.description,
        status=funnel.status,
        funnelType=funnel.funnel_type,
        entryPageId=str(funnel.entry_page_id) if funnel.entry_page_id else None,
        productId=str(funnel.product_id) if funnel.product_id else None,
        selectedOfferId=str(funnel.selected_offer_id) if funnel.selected_offer_id else None,
        templateImportId=str(funnel.template_import_id) if funnel.template_import_id else None,
        templateImportLabel=_read_template_import_label(session, str(funnel.template_import_id) if funnel.template_import_id else None),
        pageIntent=funnel.page_intent,
        campaignId=str(funnel.campaign_id) if funnel.campaign_id else None,
        selectedAngleId=funnel.selected_angle_id,
        preparedPageId=str(funnel.prepared_page_id) if funnel.prepared_page_id else None,
        preparedPageSlug=prepared_page.slug if prepared_page else None,
        latestPreparedVersionId=(
            str(funnel.latest_prepared_version_id) if funnel.latest_prepared_version_id else None
        ),
        preparationReadiness=funnel.preparation_readiness if isinstance(funnel.preparation_readiness, dict) else {},
        preparedAt=funnel.prepared_at,
        trackingConfig=funnel.tracking_config,
        stepCount=len(get_funnel_steps(session, str(funnel.id))),
        createdAt=funnel.created_at,
        updatedAt=funnel.updated_at,
    )


def _serialize_funnel_detail(session: Session, funnel) -> SiteFunnelDetail:
    steps = get_funnel_steps(session, str(funnel.id))
    prepared_page = None
    if funnel.prepared_page_id:
        prepared_page = session.scalars(
            select(SitePage).where(SitePage.id == funnel.prepared_page_id)
        ).first()
    return SiteFunnelDetail(
        id=str(funnel.id),
        siteId=str(funnel.site_id),
        name=funnel.name,
        description=funnel.description,
        status=funnel.status,
        funnelType=funnel.funnel_type,
        entryPageId=str(funnel.entry_page_id) if funnel.entry_page_id else None,
        productId=str(funnel.product_id) if funnel.product_id else None,
        selectedOfferId=str(funnel.selected_offer_id) if funnel.selected_offer_id else None,
        templateImportId=str(funnel.template_import_id) if funnel.template_import_id else None,
        templateImportLabel=_read_template_import_label(session, str(funnel.template_import_id) if funnel.template_import_id else None),
        pageIntent=funnel.page_intent,
        campaignId=str(funnel.campaign_id) if funnel.campaign_id else None,
        selectedAngleId=funnel.selected_angle_id,
        preparedPageId=str(funnel.prepared_page_id) if funnel.prepared_page_id else None,
        preparedPageSlug=prepared_page.slug if prepared_page else None,
        latestPreparedVersionId=(
            str(funnel.latest_prepared_version_id) if funnel.latest_prepared_version_id else None
        ),
        preparationReadiness=funnel.preparation_readiness if isinstance(funnel.preparation_readiness, dict) else {},
        preparedAt=funnel.prepared_at,
        trackingConfig=funnel.tracking_config,
        steps=[_serialize_step(session, step) for step in steps],
        createdAt=funnel.created_at,
        updatedAt=funnel.updated_at,
    )


@router.get("/workspace", response_model=list[SiteFunnelSummary], include_in_schema=False)
def _noop_workspace_alias() -> list[SiteFunnelSummary]:  # pragma: no cover
    return []


workspace_router = APIRouter(prefix="/sites", tags=["site-funnels"])


@workspace_router.get("/funnels", response_model=list[SiteFunnelSummary])
def list_workspace_site_funnels(
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[SiteFunnelSummary]:
    _get_workspace_or_404(session, clientId, auth.org_id)
    rows = list_workspace_funnels(session, clientId)
    return [_serialize_funnel_summary(session, funnel, site_name) for funnel, site_name in rows]


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
    if not site:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found.")
    return site


@router.get("", response_model=list[SiteFunnelSummary])
def list_site_funnels(
    site_id: str,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[SiteFunnelSummary]:
    """List all funnels for a site."""
    # Validate workspace
    _get_workspace_or_404(session, clientId, auth.org_id)

    # Validate site_id format
    _parse_uuid_or_400(site_id, "siteId")
    _get_site_for_workspace_or_404(session, site_id=site_id, client_id=clientId, org_id=auth.org_id)

    funnels = list_funnels(session, site_id)
    return [_serialize_funnel_summary(session, funnel) for funnel in funnels]


@router.post("", response_model=SiteFunnelDetail, status_code=status.HTTP_201_CREATED)
def create_site_funnel(
    site_id: str,
    clientId: str,
    request: SiteFunnelCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteFunnelDetail:
    """Create a new funnel for a site."""
    # Validate workspace
    _get_workspace_or_404(session, clientId, auth.org_id)

    # Validate site_id format
    _parse_uuid_or_400(site_id, "siteId")
    _get_site_for_workspace_or_404(session, site_id=site_id, client_id=clientId, org_id=auth.org_id)

    try:
        steps_data = [
            {
                "site_page_id": step.sitePageId,
                "ordering": step.ordering,
                "step_role": step.stepRole,
                "cta_label": step.ctaLabel,
            }
            for step in (request.steps or [])
        ]

        funnel = create_funnel(
            session,
            site_id=site_id,
            name=request.name,
            description=request.description,
            funnel_type=request.funnelType,
            entry_page_id=request.entryPageId,
            product_id=request.productId,
            selected_offer_id=request.selectedOfferId,
            template_import_id=request.templateImportId,
            page_intent=request.pageIntent,
            campaign_id=request.campaignId,
            selected_angle_id=request.selectedAngleId,
            tracking_config=request.trackingConfig,
            steps=steps_data if steps_data else None,
        )
        session.commit()
        return _serialize_funnel_detail(session, funnel)
    except SiteFunnelError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{funnel_id}", response_model=SiteFunnelDetail)
def get_site_funnel(
    site_id: str,
    funnel_id: str,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteFunnelDetail:
    """Get a specific funnel."""
    # Validate workspace
    _get_workspace_or_404(session, clientId, auth.org_id)

    # Validate IDs format
    _parse_uuid_or_400(site_id, "siteId")
    _parse_uuid_or_400(funnel_id, "funnelId")
    _get_site_for_workspace_or_404(session, site_id=site_id, client_id=clientId, org_id=auth.org_id)

    funnel = get_funnel(session, site_id, funnel_id)
    if not funnel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Funnel not found.",
        )

    return _serialize_funnel_detail(session, funnel)


@router.patch("/{funnel_id}", response_model=SiteFunnelDetail)
def update_site_funnel(
    site_id: str,
    funnel_id: str,
    clientId: str,
    request: SiteFunnelUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteFunnelDetail:
    """Update a funnel."""
    # Validate workspace
    _get_workspace_or_404(session, clientId, auth.org_id)

    # Validate IDs format
    _parse_uuid_or_400(site_id, "siteId")
    _parse_uuid_or_400(funnel_id, "funnelId")
    _get_site_for_workspace_or_404(session, site_id=site_id, client_id=clientId, org_id=auth.org_id)

    try:
        funnel = update_funnel(
            session,
            site_id=site_id,
            funnel_id=funnel_id,
            name=request.name,
            description=request.description,
            status=request.status,
            funnel_type=request.funnelType,
            entry_page_id=request.entryPageId,
            product_id=request.productId,
            selected_offer_id=request.selectedOfferId,
            template_import_id=request.templateImportId,
            page_intent=request.pageIntent,
            campaign_id=request.campaignId,
            selected_angle_id=request.selectedAngleId,
            tracking_config=request.trackingConfig,
        )
        session.commit()
        return _serialize_funnel_detail(session, funnel)
    except SiteFunnelError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{funnel_id}/prepare",
    response_model=SiteFunnelDetail,
    status_code=status.HTTP_200_OK,
)
def prepare_site_funnel_endpoint(
    site_id: str,
    funnel_id: str,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteFunnelDetail:
    _get_workspace_or_404(session, clientId, auth.org_id)
    _parse_uuid_or_400(site_id, "siteId")
    _parse_uuid_or_400(funnel_id, "funnelId")
    _get_site_for_workspace_or_404(session, site_id=site_id, client_id=clientId, org_id=auth.org_id)

    try:
        funnel = prepare_site_funnel_template(
            session=session,
            org_id=auth.org_id,
            client_id=clientId,
            site_id=site_id,
            funnel_id=funnel_id,
            created_by_user_external_id=auth.user_id,
        )
        session.commit()
        return _serialize_funnel_detail(session, funnel)
    except SiteFunnelPreparationError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/{funnel_id}/steps", response_model=SiteFunnelStepSummary, status_code=status.HTTP_201_CREATED
)
def create_site_funnel_step_endpoint(
    site_id: str,
    funnel_id: str,
    clientId: str,
    request: SiteFunnelStepCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteFunnelStepSummary:
    _get_workspace_or_404(session, clientId, auth.org_id)
    _get_site_for_workspace_or_404(session, site_id=site_id, client_id=clientId, org_id=auth.org_id)
    try:
        step = create_funnel_step(
            session,
            site_id=site_id,
            funnel_id=funnel_id,
            site_page_id=request.sitePageId,
            ordering=request.ordering,
            step_role=request.stepRole,
            cta_label=request.ctaLabel,
        )
        session.commit()
        return _serialize_step(session, step)
    except SiteFunnelError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{funnel_id}/steps/{step_id}", status_code=status.HTTP_200_OK)
def delete_site_funnel_step_endpoint(
    site_id: str,
    funnel_id: str,
    step_id: str,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    _get_workspace_or_404(session, clientId, auth.org_id)
    _get_site_for_workspace_or_404(session, site_id=site_id, client_id=clientId, org_id=auth.org_id)
    if not delete_funnel_step(session, funnel_id=funnel_id, step_id=step_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Step not found.")
    session.commit()


@router.delete("/{funnel_id}", status_code=status.HTTP_200_OK)
def delete_site_funnel_endpoint(
    site_id: str,
    funnel_id: str,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    _get_workspace_or_404(session, clientId, auth.org_id)
    _get_site_for_workspace_or_404(session, site_id=site_id, client_id=clientId, org_id=auth.org_id)
    if not delete_funnel(session, site_id, funnel_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found.")
    session.commit()
