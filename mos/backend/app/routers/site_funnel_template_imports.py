"""API endpoints for HTML template imports used by Site Funnels."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.models import Client, Site
from app.schemas.site_funnel_template_imports import (
    SiteFunnelTemplateImportCreateRequest,
    SiteFunnelTemplateImportDetail,
    SiteFunnelTemplateImportSummary,
)
from app.services.site_funnel_template_imports import (
    SiteFunnelTemplateImportError,
    create_template_import,
    get_template_import,
    list_template_imports,
)

router = APIRouter(
    prefix="/sites/{site_id}/funnel-template-imports",
    tags=["site-funnel-template-imports"],
)


def _get_workspace_or_404(session: Session, client_id: str, org_id: str) -> Client:
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


def _serialize_summary(template_import) -> SiteFunnelTemplateImportSummary:
    return SiteFunnelTemplateImportSummary(
        id=str(template_import.id),
        siteId=str(template_import.site_id),
        sourceLabel=template_import.source_label,
        htmlLength=len(template_import.html_snapshot or ""),
        htmlSha256=template_import.html_sha256,
        createdByUserExternalId=template_import.created_by_user_external_id,
        createdAt=template_import.created_at,
        updatedAt=template_import.updated_at,
    )


@router.get("", response_model=list[SiteFunnelTemplateImportSummary])
def list_site_funnel_template_imports(
    site_id: str,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[SiteFunnelTemplateImportSummary]:
    _get_workspace_or_404(session, clientId, auth.org_id)
    _parse_uuid_or_400(site_id, "siteId")
    _get_site_for_workspace_or_404(session, site_id=site_id, client_id=clientId, org_id=auth.org_id)
    return [_serialize_summary(item) for item in list_template_imports(session, site_id)]


@router.post("", response_model=SiteFunnelTemplateImportDetail, status_code=status.HTTP_201_CREATED)
def create_site_funnel_template_import(
    site_id: str,
    clientId: str,
    request: SiteFunnelTemplateImportCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteFunnelTemplateImportDetail:
    _get_workspace_or_404(session, clientId, auth.org_id)
    _parse_uuid_or_400(site_id, "siteId")
    _get_site_for_workspace_or_404(session, site_id=site_id, client_id=clientId, org_id=auth.org_id)

    try:
        template_import = create_template_import(
            session,
            site_id=site_id,
            source_label=request.sourceLabel,
            html_document=request.htmlDocument,
            created_by_user_external_id=auth.user_id,
        )
        session.commit()
    except SiteFunnelTemplateImportError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return SiteFunnelTemplateImportDetail(
        **_serialize_summary(template_import).model_dump(),
        htmlSnapshot=template_import.html_snapshot,
    )


@router.get("/{template_import_id}", response_model=SiteFunnelTemplateImportDetail)
def get_site_funnel_template_import_endpoint(
    site_id: str,
    template_import_id: str,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteFunnelTemplateImportDetail:
    _get_workspace_or_404(session, clientId, auth.org_id)
    _parse_uuid_or_400(site_id, "siteId")
    _parse_uuid_or_400(template_import_id, "templateImportId")
    _get_site_for_workspace_or_404(session, site_id=site_id, client_id=clientId, org_id=auth.org_id)

    template_import = get_template_import(
        session,
        site_id=site_id,
        template_import_id=template_import_id,
    )
    if template_import is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template import not found.")

    return SiteFunnelTemplateImportDetail(
        **_serialize_summary(template_import).model_dump(),
        htmlSnapshot=template_import.html_snapshot,
    )
