"""Canonical Site Imports API endpoints.

These are the canonical routes for site imports, separate from /storefront/templates/imports.
These routes write audit rows to site_import_applications for explicit apply actions.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4, UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.models import Client, SiteImport, SiteImportSnapshot, SiteImportApplication
from app.schemas.site_imports import (
    SiteImportSummary,
    SiteImportApplicationSummary,
    SiteImportApplyRequest,
    SiteImportApplyResponse,
    SiteImportCreateRequest,
    SiteImportCreateSiteRequest,
    SiteImportAddPagesRequest,
    SiteImportCreateSiteTemplateRequest,
    SiteImportCreatePageTemplateRequest,
    SiteImportCreateSiteResponse,
    SiteImportAddPagesResponse,
    SiteImportCreateSiteTemplateResponse,
    SiteImportCreatePageTemplateResponse,
    SiteImportSnapshotResponse,
)
from app.services.site_imports import (
    SiteImportError,
    create_import_record,
    create_import_as_site_template,
    get_import_detail,
    get_import_snapshot as get_import_snapshot_service,
    list_imports,
    process_import_job,
    save_import_as_site,
    add_import_pages_to_site,
    convert_import_to_variant,
    convert_import_to_variant_with_synthesis,
)
from app.services.site_blueprints import get_site_family

router = APIRouter(prefix="/site-imports", tags=["site-imports"])


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


def _write_application(
    session: Session,
    *,
    site_import_id: str,
    action: str,
    status: str,
    site_id: str | None = None,
    site_page_ids: list[str] | None = None,
    site_template_id: str | None = None,
    template_variant_id: str | None = None,
    error_detail: str | None = None,
    result_summary: dict[str, Any] | None = None,
    created_by_user_external_id: str | None = None,
) -> SiteImportApplication:
    """Write an audit row to site_import_applications."""
    now = datetime.now(timezone.utc)
    application = SiteImportApplication(
        id=str(uuid4()),
        site_import_id=site_import_id,
        action=action,
        status=status,
        site_id=site_id,
        site_page_ids=site_page_ids or [],
        site_template_id=site_template_id,
        template_variant_id=template_variant_id,
        error_detail=error_detail,
        result_summary=result_summary or {},
        created_by_user_external_id=created_by_user_external_id,
        created_at=now,
    )
    session.add(application)
    session.flush()
    return application


@router.get("", response_model=list[SiteImportSummary])
def list_site_imports(
    clientId: str,
    limit: int = 25,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[SiteImportSummary]:
    """List site imports for a workspace."""
    _get_workspace_or_404(session, clientId, auth.org_id)

    imports = list_imports(
        session,
        org_id=auth.org_id,
        client_id=clientId,
        limit=limit,
    )

    return [
        SiteImportSummary(
            id=str(imp.id),
            sourceUrl=imp.source_url,
            sourceHostname=imp.source_hostname,
            pageTypeHint=imp.page_type_hint,
            siteFamilyHint=imp.site_family_hint,
            status=imp.status,
            title=imp.title,
            suggestedTemplateFamily=imp.suggested_template_family,
            savedSiteId=str(imp.saved_site_id) if imp.saved_site_id else None,
            createdAt=imp.created_at,
            updatedAt=imp.updated_at,
        )
        for imp in imports
    ]


@router.post("", response_model=SiteImportSummary, status_code=status.HTTP_201_CREATED)
async def create_site_import(
    request: SiteImportCreateRequest,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteImportSummary:
    """Create a new site import job."""
    _get_workspace_or_404(session, clientId, auth.org_id)

    # Validate URL format
    try:
        from app.services.site_imports import _validate_url

        _validate_url(request.sourceUrl)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    import_job = create_import_record(
        session,
        org_id=auth.org_id,
        client_id=clientId,
        source_url=request.sourceUrl,
        page_type_hint=request.pageTypeHint,
        site_family_hint=request.siteFamilyHint,
        created_by_user_external_id=auth.user_id,
    )

    # Write application audit row for create action
    _write_application(
        session,
        site_import_id=str(import_job.id),
        action="create",
        status="pending",
        result_summary={"source_url": request.sourceUrl},
        created_by_user_external_id=auth.user_id,
    )
    session.commit()

    threading.Thread(
        target=lambda: asyncio.run(process_import_job(site_import_id=str(import_job.id))),
        daemon=True,
    ).start()

    return SiteImportSummary(
        id=str(import_job.id),
        sourceUrl=import_job.source_url,
        sourceHostname=import_job.source_hostname,
        pageTypeHint=import_job.page_type_hint,
        siteFamilyHint=import_job.site_family_hint,
        status=import_job.status,
        title=import_job.title,
        suggestedTemplateFamily=import_job.suggested_template_family,
        createdAt=import_job.created_at,
        updatedAt=import_job.updated_at,
    )


@router.get("/{import_id}", response_model=SiteImportSummary)
def get_site_import(
    import_id: str,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteImportSummary:
    """Get detailed information about a site import."""
    _get_workspace_or_404(session, clientId, auth.org_id)
    _parse_uuid_or_400(import_id, "importId")

    site_import = get_import_detail(
        session,
        org_id=auth.org_id,
        client_id=clientId,
        site_import_id=import_id,
    )
    if site_import is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import not found.")

    return SiteImportSummary(
        id=str(site_import.id),
        sourceUrl=site_import.source_url,
        sourceHostname=site_import.source_hostname,
        pageTypeHint=site_import.page_type_hint,
        siteFamilyHint=site_import.site_family_hint,
        status=site_import.status,
        title=site_import.title,
        suggestedTemplateFamily=site_import.suggested_template_family,
        savedSiteId=str(site_import.saved_site_id) if site_import.saved_site_id else None,
        createdAt=site_import.created_at,
        updatedAt=site_import.updated_at,
    )


@router.get("/{import_id}/snapshot", response_model=SiteImportSnapshotResponse)
def get_site_import_snapshot(
    import_id: str,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteImportSnapshotResponse:
    """Get the snapshot for an import."""
    _get_workspace_or_404(session, clientId, auth.org_id)
    _parse_uuid_or_400(import_id, "importId")

    snapshot = get_import_snapshot_service(session, site_import_id=import_id)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found.")

    return SiteImportSnapshotResponse(
        id=str(snapshot.id),
        htmlSnapshot=snapshot.html_snapshot,
        desktopScreenshotDataUrl=snapshot.desktop_screenshot_data_url,
        mobileScreenshotDataUrl=snapshot.mobile_screenshot_data_url,
        captureMetadata=dict(snapshot.capture_metadata or {}),
        createdAt=snapshot.created_at,
    )


@router.post("/{import_id}/create-site", response_model=SiteImportCreateSiteResponse)
def create_site_from_import(
    import_id: str,
    request: SiteImportCreateSiteRequest,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteImportCreateSiteResponse:
    """Create a site from a completed import."""
    _get_workspace_or_404(session, clientId, auth.org_id)
    _parse_uuid_or_400(import_id, "importId")

    try:
        result = save_import_as_site(
            session,
            org_id=auth.org_id,
            client_id=clientId,
            site_import_id=import_id,
            site_name=request.siteName,
            description=request.description,
            created_by_user_external_id=auth.user_id,
        )

        # Write application audit row
        _write_application(
            session,
            site_import_id=import_id,
            action="create-site",
            status="completed",
            site_id=result["siteId"],
            site_page_ids=[p["pageId"] for p in result.get("createdPages", [])],
            result_summary=result,
            created_by_user_external_id=auth.user_id,
        )
        session.commit()

        return SiteImportCreateSiteResponse(
            siteId=result["siteId"],
            siteName=result["siteName"],
            pageCount=result["pageCount"],
            entryPageType=result.get("entryPageType"),
            createdPages=result.get("createdPages", []),
            createdAt=result["createdAt"],
        )
    except SiteImportError as e:
        # Write failed application audit row
        _write_application(
            session,
            site_import_id=import_id,
            action="create-site",
            status="failed",
            error_detail=str(e),
            created_by_user_external_id=auth.user_id,
        )
        session.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{import_id}/add-pages", response_model=SiteImportAddPagesResponse)
def add_pages_from_import(
    import_id: str,
    request: SiteImportAddPagesRequest,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteImportAddPagesResponse:
    """Add pages from an import to an existing site."""
    _get_workspace_or_404(session, clientId, auth.org_id)
    _parse_uuid_or_400(import_id, "importId")

    try:
        result = add_import_pages_to_site(
            session,
            org_id=auth.org_id,
            client_id=clientId,
            site_import_id=import_id,
            site_id=request.siteId,
            created_by_user_external_id=auth.user_id,
        )
        application = _write_application(
            session,
            site_import_id=import_id,
            action="add-pages",
            status="completed",
            site_id=result["siteId"],
            site_page_ids=[p["pageId"] for p in result.get("createdPages", [])],
            result_summary=result,
            created_by_user_external_id=auth.user_id,
        )
        session.commit()
        return SiteImportAddPagesResponse(
            siteId=result["siteId"],
            pageCount=result["pageCount"],
            createdPages=result["createdPages"],
        )
    except SiteImportError as e:
        _write_application(
            session,
            site_import_id=import_id,
            action="add-pages",
            status="failed",
            error_detail=str(e),
            created_by_user_external_id=auth.user_id,
        )
        session.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{import_id}/create-site-template", response_model=SiteImportCreateSiteTemplateResponse
)
def create_site_template_from_import(
    import_id: str,
    request: SiteImportCreateSiteTemplateRequest,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteImportCreateSiteTemplateResponse:
    """Create a site template from a completed import."""
    _get_workspace_or_404(session, clientId, auth.org_id)
    _parse_uuid_or_400(import_id, "importId")

    try:
        result = create_import_as_site_template(
            session,
            org_id=auth.org_id,
            client_id=clientId,
            site_import_id=import_id,
            name=request.name,
            family=request.family,
            description=request.description,
            created_by_user_external_id=auth.user_id,
        )
        _write_application(
            session,
            site_import_id=import_id,
            action="create-site-template",
            status="completed",
            site_template_id=result["siteTemplateId"],
            result_summary=result,
            created_by_user_external_id=auth.user_id,
        )
        session.commit()
        return SiteImportCreateSiteTemplateResponse(**result)
    except SiteImportError as e:
        _write_application(
            session,
            site_import_id=import_id,
            action="create-site-template",
            status="failed",
            error_detail=str(e),
            created_by_user_external_id=auth.user_id,
        )
        session.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{import_id}/create-page-template", response_model=SiteImportCreatePageTemplateResponse
)
def create_page_template_from_import(
    import_id: str,
    request: SiteImportCreatePageTemplateRequest,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteImportCreatePageTemplateResponse:
    """Create a page template variant from a completed import."""
    _get_workspace_or_404(session, clientId, auth.org_id)
    _parse_uuid_or_400(import_id, "importId")

    accepted_section_ids = list(request.acceptedSectionIds)
    if not accepted_section_ids:
        site_import = get_import_detail(
            session,
            org_id=auth.org_id,
            client_id=clientId,
            site_import_id=import_id,
        )
        if not site_import:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import not found.")
        accepted_section_ids = [
            section.get("id")
            for section in (site_import.normalized_sections or [])
            if isinstance(section, dict) and section.get("id")
        ]
        if not accepted_section_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Import has no normalized sections available for page template creation.",
            )

    try:
        result = convert_import_to_variant_with_synthesis(
            session,
            org_id=auth.org_id,
            client_id=clientId,
            site_import_id=import_id,
            name=request.name,
            family=request.family,
            page_type=request.pageType,
            accepted_section_ids=accepted_section_ids,
            review_notes=request.reviewNotes,
            created_by_user_external_id=auth.user_id,
        )

        variant = result["variant"]
        style_preset = result.get("style_preset")

        # Write application audit row
        _write_application(
            session,
            site_import_id=import_id,
            action="create-page-template",
            status="completed",
            template_variant_id=str(variant.id),
            result_summary={
                "name": variant.name,
                "family": variant.family,
                "page_type": variant.page_type,
            },
            created_by_user_external_id=auth.user_id,
        )
        session.commit()

        return SiteImportCreatePageTemplateResponse(
            variantId=str(variant.id),
            stylePresetId=str(style_preset.id) if style_preset else None,
            name=variant.name,
            family=variant.family,
            pageType=variant.page_type,
            createdAt=variant.created_at,
        )
    except SiteImportError as e:
        # Write failed application audit row
        _write_application(
            session,
            site_import_id=import_id,
            action="create-page-template",
            status="failed",
            error_detail=str(e),
            created_by_user_external_id=auth.user_id,
        )
        session.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{import_id}/applications", response_model=list[SiteImportApplicationSummary])
def list_import_applications(
    import_id: str,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[SiteImportApplicationSummary]:
    """List all applications (audit rows) for an import."""
    _get_workspace_or_404(session, clientId, auth.org_id)
    _parse_uuid_or_400(import_id, "importId")

    stmt = (
        select(SiteImportApplication)
        .where(SiteImportApplication.site_import_id == import_id)
        .order_by(SiteImportApplication.created_at.desc())
    )
    applications = list(session.scalars(stmt).all())

    return [
        SiteImportApplicationSummary(
            id=str(app.id),
            siteImportId=str(app.site_import_id),
            action=app.action,
            status=app.status,
            siteId=str(app.site_id) if app.site_id else None,
            siteTemplateId=str(app.site_template_id) if app.site_template_id else None,
            templateVariantId=str(app.template_variant_id) if app.template_variant_id else None,
            errorDetail=app.error_detail,
            createdByUserExternalId=app.created_by_user_external_id,
            createdAt=app.created_at,
        )
        for app in applications
    ]


@router.post("/{import_id}/apply", response_model=SiteImportApplyResponse)
def apply_site_import(
    import_id: str,
    request: SiteImportApplyRequest,
    clientId: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SiteImportApplyResponse:
    """Generic apply endpoint for the site-first import workflow."""
    if request.action == "create-site":
        if not request.name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="name is required"
            )
        result = create_site_from_import(
            import_id=import_id,
            request=SiteImportCreateSiteRequest(
                siteName=request.name, description=request.description
            ),
            clientId=clientId,
            auth=auth,
            session=session,
        )
        latest = session.scalars(
            select(SiteImportApplication)
            .where(
                SiteImportApplication.site_import_id == import_id,
                SiteImportApplication.action == "create-site",
            )
            .order_by(SiteImportApplication.created_at.desc())
        ).first()
        return SiteImportApplyResponse(applicationId=str(latest.id), siteId=result.siteId)

    if request.action == "add-pages":
        if not request.targetSiteId:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="targetSiteId is required"
            )
        result = add_pages_from_import(
            import_id=import_id,
            request=SiteImportAddPagesRequest(siteId=request.targetSiteId),
            clientId=clientId,
            auth=auth,
            session=session,
        )
        latest = session.scalars(
            select(SiteImportApplication)
            .where(
                SiteImportApplication.site_import_id == import_id,
                SiteImportApplication.action == "add-pages",
            )
            .order_by(SiteImportApplication.created_at.desc())
        ).first()
        return SiteImportApplyResponse(applicationId=str(latest.id), siteId=result.siteId)

    if request.action == "create-site-template":
        if not request.name or not request.family:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="name and family are required",
            )
        result = create_site_template_from_import(
            import_id=import_id,
            request=SiteImportCreateSiteTemplateRequest(
                name=request.name, family=request.family, description=request.description
            ),
            clientId=clientId,
            auth=auth,
            session=session,
        )
        latest = session.scalars(
            select(SiteImportApplication)
            .where(
                SiteImportApplication.site_import_id == import_id,
                SiteImportApplication.action == "create-site-template",
            )
            .order_by(SiteImportApplication.created_at.desc())
        ).first()
        return SiteImportApplyResponse(
            applicationId=str(latest.id), siteTemplateId=result.siteTemplateId
        )

    if request.action == "create-page-template":
        if not request.name or not request.family or not request.pageType:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="name, family, and pageType are required",
            )
        result = create_page_template_from_import(
            import_id=import_id,
            request=SiteImportCreatePageTemplateRequest(
                name=request.name,
                family=request.family,
                pageType=request.pageType,
                acceptedSectionIds=request.acceptedSectionIds,
                reviewNotes=request.reviewNotes,
            ),
            clientId=clientId,
            auth=auth,
            session=session,
        )
        latest = session.scalars(
            select(SiteImportApplication)
            .where(
                SiteImportApplication.site_import_id == import_id,
                SiteImportApplication.action == "create-page-template",
            )
            .order_by(SiteImportApplication.created_at.desc())
        ).first()
        return SiteImportApplyResponse(
            applicationId=str(latest.id), pageTemplateId=result.variantId
        )

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"Unsupported action: {request.action}",
    )
