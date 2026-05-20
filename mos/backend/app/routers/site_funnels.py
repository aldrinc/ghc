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
from app.db.models import Client, Site, SitePage
from app.schemas.site_funnels import (
    SiteFunnelSummary,
    SiteFunnelDetail,
    SiteFunnelCreateRequest,
    SiteFunnelUpdateRequest,
    SiteFunnelStepSummary,
    SiteFunnelPathSummary,
    SiteFunnelPathCreateRequest,
    SiteFunnelPathStepSummary,
    SiteFunnelStepCreateRequest,
    SiteFunnelStepOptionCreateRequest,
    SiteFunnelStepOptionSummary,
)
from app.services.site_funnels import (
    list_funnels,
    list_workspace_funnels,
    get_funnel,
    get_funnel_steps,
    list_step_options,
    list_paths,
    list_path_steps,
    create_funnel,
    update_funnel,
    delete_funnel,
    create_funnel_step,
    delete_funnel_step,
    create_step_option,
    delete_step_option,
    create_path,
    delete_path,
    SiteFunnelError,
)

router = APIRouter(prefix="/sites/{site_id}/funnels", tags=["site-funnels"])


def _serialize_page(page) -> dict[str, str | None] | None:
    if not page:
        return None
    return {
        "id": str(page.id),
        "name": page.name,
        "slug": page.slug,
        "pageType": page.page_type,
    }


def _serialize_option(session: Session, option) -> SiteFunnelStepOptionSummary:
    page = session.scalars(select(SitePage).where(SitePage.id == option.site_page_id)).first()
    return SiteFunnelStepOptionSummary(
        id=str(option.id),
        siteFunnelStepId=str(option.site_funnel_step_id),
        sitePageId=str(option.site_page_id),
        optionKey=option.option_key,
        label=option.label,
        status=option.status,
        trafficWeight=option.traffic_weight,
        isControl=option.is_control,
        metadata=option.metadata_json or {},
        page=_serialize_page(page),
        createdAt=option.created_at,
        updatedAt=option.updated_at,
    )


def _serialize_step(session: Session, step) -> SiteFunnelStepSummary:
    page = session.scalars(select(SitePage).where(SitePage.id == step.site_page_id)).first()
    options = list_step_options(session, step_id=str(step.id))
    return SiteFunnelStepSummary(
        id=str(step.id),
        sitePageId=str(step.site_page_id),
        ordering=step.ordering,
        stepRole=step.step_role,
        ctaLabel=step.cta_label,
        transitionRule=None,
        page=_serialize_page(page),
        options=[_serialize_option(session, option) for option in options],
        createdAt=step.created_at,
    )


def _serialize_path_step(session: Session, path_step) -> SiteFunnelPathStepSummary:
    page = session.scalars(select(SitePage).where(SitePage.id == path_step.site_page_id)).first()
    option = next(
        (
            candidate
            for candidate in list_step_options(session, step_id=str(path_step.site_funnel_step_id))
            if str(candidate.id) == str(path_step.site_funnel_step_option_id)
        ),
        None,
    )
    return SiteFunnelPathStepSummary(
        id=str(path_step.id),
        siteFunnelPathId=str(path_step.site_funnel_path_id),
        siteFunnelStepId=str(path_step.site_funnel_step_id),
        siteFunnelStepOptionId=str(path_step.site_funnel_step_option_id),
        sitePageId=str(path_step.site_page_id),
        ordering=path_step.ordering,
        stepRole=path_step.step_role,
        page=_serialize_page(page),
        option={
            "id": str(option.id),
            "optionKey": option.option_key,
            "label": option.label,
            "status": option.status,
        }
        if option
        else None,
        createdAt=path_step.created_at,
    )


def _serialize_path(session: Session, path) -> SiteFunnelPathSummary:
    steps = list_path_steps(session, path_id=str(path.id))
    return SiteFunnelPathSummary(
        id=str(path.id),
        siteFunnelId=str(path.site_funnel_id),
        campaignId=str(path.campaign_id) if path.campaign_id else None,
        name=path.name,
        slug=path.slug,
        status=path.status,
        trafficWeight=path.traffic_weight,
        isControl=path.is_control,
        experimentSpecId=path.experiment_spec_id,
        variantId=path.variant_id,
        metadata=path.metadata_json or {},
        steps=[_serialize_path_step(session, step) for step in steps],
        createdAt=path.created_at,
        updatedAt=path.updated_at,
    )


def _serialize_funnel_detail(session: Session, funnel) -> SiteFunnelDetail:
    steps = get_funnel_steps(session, str(funnel.id))
    paths = list_paths(session, funnel_id=str(funnel.id))
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
        trackingConfig=funnel.tracking_config,
        steps=[_serialize_step(session, step) for step in steps],
        paths=[_serialize_path(session, path) for path in paths],
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
    return [
        SiteFunnelSummary(
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
            trackingConfig=funnel.tracking_config,
            stepCount=len(get_funnel_steps(session, str(funnel.id))),
            createdAt=funnel.created_at,
            updatedAt=funnel.updated_at,
        )
        for funnel, site_name in rows
    ]


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
    return [
        SiteFunnelSummary(
            id=str(f.id),
            siteId=str(f.site_id),
            name=f.name,
            description=f.description,
            status=f.status,
            funnelType=f.funnel_type,
            entryPageId=str(f.entry_page_id) if f.entry_page_id else None,
            productId=str(f.product_id) if f.product_id else None,
            selectedOfferId=str(f.selected_offer_id) if f.selected_offer_id else None,
            trackingConfig=f.tracking_config,
            stepCount=len(get_funnel_steps(session, str(f.id))),
            createdAt=f.created_at,
            updatedAt=f.updated_at,
        )
        for f in funnels
    ]


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
            tracking_config=request.trackingConfig,
        )
        session.commit()

        return _serialize_funnel_detail(session, funnel)
    except SiteFunnelError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


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


@router.post(
    "/{funnel_id}/steps/{step_id}/options",
    response_model=SiteFunnelStepOptionSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_site_funnel_step_option_endpoint(
    site_id: str,
    funnel_id: str,
    step_id: str,
    clientId: str,
    request: SiteFunnelStepOptionCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteFunnelStepOptionSummary:
    _get_workspace_or_404(session, clientId, auth.org_id)
    _parse_uuid_or_400(site_id, "siteId")
    _parse_uuid_or_400(funnel_id, "funnelId")
    _parse_uuid_or_400(step_id, "stepId")
    _parse_uuid_or_400(request.sitePageId, "sitePageId")
    _get_site_for_workspace_or_404(session, site_id=site_id, client_id=clientId, org_id=auth.org_id)
    try:
        option = create_step_option(
            session,
            site_id=site_id,
            funnel_id=funnel_id,
            step_id=step_id,
            site_page_id=request.sitePageId,
            option_key=request.optionKey,
            label=request.label,
            status=request.status,
            traffic_weight=request.trafficWeight,
            is_control=request.isControl,
            metadata=request.metadata,
        )
        session.commit()
        return _serialize_option(session, option)
    except SiteFunnelError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{funnel_id}/steps/{step_id}/options/{option_id}", status_code=status.HTTP_200_OK)
def delete_site_funnel_step_option_endpoint(
    site_id: str,
    funnel_id: str,
    step_id: str,
    option_id: str,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    _get_workspace_or_404(session, clientId, auth.org_id)
    _parse_uuid_or_400(site_id, "siteId")
    _parse_uuid_or_400(funnel_id, "funnelId")
    _parse_uuid_or_400(step_id, "stepId")
    _parse_uuid_or_400(option_id, "optionId")
    _get_site_for_workspace_or_404(session, site_id=site_id, client_id=clientId, org_id=auth.org_id)
    try:
        deleted = delete_step_option(
            session,
            funnel_id=funnel_id,
            step_id=step_id,
            option_id=option_id,
        )
    except SiteFunnelError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Step option not found.")
    session.commit()


@router.get("/{funnel_id}/paths", response_model=list[SiteFunnelPathSummary])
def list_site_funnel_paths_endpoint(
    site_id: str,
    funnel_id: str,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[SiteFunnelPathSummary]:
    _get_workspace_or_404(session, clientId, auth.org_id)
    _parse_uuid_or_400(site_id, "siteId")
    _parse_uuid_or_400(funnel_id, "funnelId")
    _get_site_for_workspace_or_404(session, site_id=site_id, client_id=clientId, org_id=auth.org_id)
    if not get_funnel(session, site_id, funnel_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found.")
    return [_serialize_path(session, path) for path in list_paths(session, funnel_id=funnel_id)]


@router.post(
    "/{funnel_id}/paths",
    response_model=SiteFunnelPathSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_site_funnel_path_endpoint(
    site_id: str,
    funnel_id: str,
    clientId: str,
    request: SiteFunnelPathCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteFunnelPathSummary:
    _get_workspace_or_404(session, clientId, auth.org_id)
    _parse_uuid_or_400(site_id, "siteId")
    _parse_uuid_or_400(funnel_id, "funnelId")
    if request.campaignId:
        _parse_uuid_or_400(request.campaignId, "campaignId")
    for step in request.steps:
        _parse_uuid_or_400(step.siteFunnelStepId, "siteFunnelStepId")
        _parse_uuid_or_400(step.sitePageId, "sitePageId")
    _get_site_for_workspace_or_404(session, site_id=site_id, client_id=clientId, org_id=auth.org_id)
    try:
        path = create_path(
            session,
            site_id=site_id,
            funnel_id=funnel_id,
            name=request.name,
            slug=request.slug,
            status=request.status,
            campaign_id=request.campaignId,
            traffic_weight=request.trafficWeight,
            is_control=request.isControl,
            experiment_spec_id=request.experimentSpecId,
            variant_id=request.variantId,
            metadata=request.metadata,
            steps=[
                {
                    "site_funnel_step_id": step.siteFunnelStepId,
                    "site_page_id": step.sitePageId,
                }
                for step in request.steps
            ],
        )
        session.commit()
        return _serialize_path(session, path)
    except SiteFunnelError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{funnel_id}/paths/{path_id}", status_code=status.HTTP_200_OK)
def delete_site_funnel_path_endpoint(
    site_id: str,
    funnel_id: str,
    path_id: str,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    _get_workspace_or_404(session, clientId, auth.org_id)
    _parse_uuid_or_400(site_id, "siteId")
    _parse_uuid_or_400(funnel_id, "funnelId")
    _parse_uuid_or_400(path_id, "pathId")
    _get_site_for_workspace_or_404(session, site_id=site_id, client_id=clientId, org_id=auth.org_id)
    if not delete_path(session, funnel_id=funnel_id, path_id=path_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel path not found.")
    session.commit()


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
    try:
        deleted = delete_funnel_step(session, funnel_id=funnel_id, step_id=step_id)
    except SiteFunnelError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not deleted:
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
