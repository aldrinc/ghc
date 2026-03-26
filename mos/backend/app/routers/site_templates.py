"""Site Templates API endpoints.

Canonical endpoints for site template management.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from datetime import datetime, timezone
from uuid import uuid4

from app.db.models import Client, SiteTemplate
from app.schemas.site_templates import (
    SiteTemplateCreateRequest,
    SiteTemplateSummary,
    SiteTemplateDetail,
    SiteTemplatePageSummary,
    SiteTemplateLinkSummary,
    SiteTemplateFunnelSummary,
    SiteTemplateFunnelStepSummary,
    SiteTemplateInstantiateRequest,
    SiteTemplateInstantiateResponse,
)
from app.services.site_templates import (
    list_templates,
    get_template,
    get_template_pages,
    get_template_links,
    get_template_funnels,
    get_template_funnel_steps,
    instantiate_template,
    seed_system_templates,
    SiteTemplateError,
)

router = APIRouter(prefix="/site-templates", tags=["site-templates"])


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


@router.get("", response_model=list[SiteTemplateSummary])
def list_site_templates(
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[SiteTemplateSummary]:
    """List all available site templates."""
    # Seed system templates on first access
    seed_system_templates(session)

    templates = list_templates(session)
    return [
        SiteTemplateSummary(
            id=str(t.id),
            family=t.family,
            name=t.name,
            description=t.description,
            siteType=t.site_type,
            commerceProvider=t.commerce_provider,
            isSystemTemplate=t.is_system_template,
            pageCount=len(get_template_pages(session, str(t.id))),
            funnelCount=len(get_template_funnels(session, str(t.id))),
            createdAt=t.created_at,
        )
        for t in templates
    ]


@router.post("", response_model=SiteTemplateSummary, status_code=status.HTTP_201_CREATED)
def create_site_template(
    request: SiteTemplateCreateRequest,
    clientId: str | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteTemplateSummary:
    """Create a workspace-scoped site template header."""
    if clientId is not None:
        _get_workspace_or_404(session, clientId, auth.org_id)

    template = SiteTemplate(
        id=str(uuid4()),
        family=request.family,
        name=request.name,
        description=request.description,
        site_type=request.siteType,
        commerce_provider=request.commerceProvider,
        is_system_template=False,
        provenance_notes=[],
        created_at=datetime.now(timezone.utc),
    )
    session.add(template)
    session.commit()
    session.refresh(template)
    return SiteTemplateSummary(
        id=str(template.id),
        family=template.family,
        name=template.name,
        description=template.description,
        siteType=template.site_type,
        commerceProvider=template.commerce_provider,
        isSystemTemplate=template.is_system_template,
        pageCount=0,
        funnelCount=0,
        createdAt=template.created_at,
    )


@router.get("/{template_id}", response_model=SiteTemplateDetail)
def get_site_template(
    template_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteTemplateDetail:
    """Get detailed information about a site template."""
    # Validate template_id format
    _parse_uuid_or_400(template_id, "templateId")

    template = get_template(session, template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site template not found.",
        )

    # Get sub-objects
    pages = get_template_pages(session, template_id)
    links = get_template_links(session, template_id)
    funnels = get_template_funnels(session, template_id)

    funnel_summaries = []
    for funnel in funnels:
        steps = get_template_funnel_steps(session, str(funnel.id))
        funnel_summaries.append(
            SiteTemplateFunnelSummary(
                id=str(funnel.id),
                name=funnel.name,
                description=funnel.description,
                funnelType=funnel.funnel_type,
                entryPageType=funnel.entry_page_type,
                steps=[
                    SiteTemplateFunnelStepSummary(
                        id=str(step.id),
                        pageType=step.page_type,
                        ordering=step.ordering,
                        stepRole=step.step_role,
                        ctaLabel=step.cta_label,
                    )
                    for step in steps
                ],
            )
        )

    return SiteTemplateDetail(
        id=str(template.id),
        family=template.family,
        name=template.name,
        description=template.description,
        siteType=template.site_type,
        commerceProvider=template.commerce_provider,
        isSystemTemplate=template.is_system_template,
        provenanceNotes=list(template.provenance_notes or []),
        pages=[
            SiteTemplatePageSummary(
                id=str(p.id),
                pageType=p.page_type,
                name=p.name,
                slug=p.slug,
                description=p.description,
                pageTemplateId=p.page_template_id,
                ordering=p.ordering,
                isEntry=p.is_entry,
            )
            for p in pages
        ],
        links=[
            SiteTemplateLinkSummary(
                id=str(l.id),
                fromPageType=l.from_page_type,
                toPageType=l.to_page_type,
                label=l.label,
                linkKind=l.link_kind,
            )
            for l in links
        ],
        funnels=funnel_summaries,
        createdAt=template.created_at,
    )


@router.post("/{template_id}/instantiate", response_model=SiteTemplateInstantiateResponse)
def instantiate_site_template(
    template_id: str,
    request: SiteTemplateInstantiateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteTemplateInstantiateResponse:
    """Instantiate a site template into a new site."""
    # Validate template_id format
    _parse_uuid_or_400(template_id, "templateId")

    # Validate workspace
    _get_workspace_or_404(session, request.clientId, auth.org_id)

    try:
        result = instantiate_template(
            session,
            template_id=template_id,
            org_id=auth.org_id,
            client_id=request.clientId,
            name=request.name,
            description=request.description,
            product_id=request.productId,
            design_system_id=request.designSystemId,
            primary_domain=request.primaryDomain,
            created_by_user_external_id=auth.user_id,
        )
        session.commit()
    except SiteTemplateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return SiteTemplateInstantiateResponse(
        siteId=result["siteId"],
        siteName=result["siteName"],
        pageCount=result["pageCount"],
        funnelCount=result["funnelCount"],
        entryPageId=result.get("entryPageId"),
        createdAt=result["createdAt"],
    )
