from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response as BinaryResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.deps import get_session
from app.db.enums import (
    FunnelAssetStatusEnum,
    FunnelEventTypeEnum,
    FunnelPageVersionStatusEnum,
    FunnelStatusEnum,
)
from app.db.models import Funnel, FunnelEvent, FunnelPage, FunnelPageVersion
from app.db.repositories.funnels import (
    FunnelPageVersionsRepository,
    FunnelPagesRepository,
    FunnelPublicRepository,
    FunnelsRepository,
)
from app.schemas.funnels import PublicEventsIngestRequest
from app.services.media_storage import MediaStorage

router = APIRouter(prefix="/public", tags=["public"])


def _get_funnel_or_404(*, session: Session, public_id: str) -> Funnel:
    funnels_repo = FunnelsRepository(session)
    funnel = funnels_repo.get_by_public_id(public_id=public_id)
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")
    if funnel.status == FunnelStatusEnum.disabled:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Funnel disabled")
    return funnel


def _publication_id_for_public_response(funnel: Funnel) -> str:
    """
    Public runtime expects a publicationId string. For unpublished funnels, we return the funnel id
    (a valid UUID) so public event ingestion won't crash on invalid UUID input.
    """

    return str(funnel.active_publication_id or funnel.id)


def _preview_page_map(*, session: Session, funnel_id: str) -> dict[str, str]:
    """
    For unpublished funnels, we treat "preview" pages as those with an approved version.
    """

    approved_page_ids = set(
        str(page_id)
        for page_id in session.scalars(
            select(FunnelPageVersion.page_id)
            .join(FunnelPage, FunnelPage.id == FunnelPageVersion.page_id)
            .where(
                FunnelPage.funnel_id == funnel_id,
                FunnelPageVersion.status == FunnelPageVersionStatusEnum.approved,
            )
            .distinct()
        ).all()
    )
    pages_repo = FunnelPagesRepository(session)
    pages = pages_repo.list(funnel_id=funnel_id)
    return {str(page.id): page.slug for page in pages if str(page.id) in approved_page_ids}


@router.get("/funnels/{public_id}/meta")
def public_funnel_meta(
    public_id: str,
    response: Response,
    session: Session = Depends(get_session),
):
    public_repo = FunnelPublicRepository(session)
    funnel = _get_funnel_or_404(session=session, public_id=public_id)

    publication_id = _publication_id_for_public_response(funnel)
    if funnel.active_publication_id:
        publication = public_repo.get_active_publication(
            funnel_id=str(funnel.id), publication_id=str(funnel.active_publication_id)
        )
        if not publication:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publication not found")
        pages = public_repo.list_publication_pages(publication_id=str(funnel.active_publication_id))
        entry_slug = None
        for pp in pages:
            if str(pp.page_id) == str(publication.entry_page_id):
                entry_slug = pp.slug_at_publish
                break
        if not entry_slug:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry page not found")

        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return {
            "publicId": str(funnel.public_id),
            "funnelId": str(funnel.id),
            "publicationId": publication_id,
            "entrySlug": entry_slug,
            "pages": [{"pageId": str(pp.page_id), "slug": pp.slug_at_publish} for pp in pages],
        }

    # Preview mode: allow viewing approved pages even if the funnel hasn't been published yet.
    page_map = _preview_page_map(session=session, funnel_id=str(funnel.id))
    if not funnel.entry_page_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry page not found")
    entry_slug = page_map.get(str(funnel.entry_page_id))
    if not entry_slug:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry page not approved")

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {
        "publicId": str(funnel.public_id),
        "funnelId": str(funnel.id),
        "publicationId": publication_id,
        "entrySlug": entry_slug,
        "pages": [{"pageId": page_id, "slug": slug} for page_id, slug in page_map.items()],
    }


@router.get("/funnels/{public_id}/pages/{slug}")
def public_funnel_page(
    public_id: str,
    slug: str,
    response: Response,
    session: Session = Depends(get_session),
):
    public_repo = FunnelPublicRepository(session)
    funnel = _get_funnel_or_404(session=session, public_id=public_id)

    publication_id = _publication_id_for_public_response(funnel)
    if funnel.active_publication_id:
        pp = public_repo.get_publication_page_by_slug(publication_id=str(funnel.active_publication_id), slug=slug)
        if not pp:
            redirect = public_repo.get_redirect(funnel_id=str(funnel.id), from_slug=slug)
            if redirect:
                response.headers["X-Robots-Tag"] = "noindex, nofollow"
                return {"redirectToSlug": redirect.to_slug}
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

        version = public_repo.get_page_version(version_id=str(pp.page_version_id))
        if not version:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page content not found")

        page_map = {
            str(item.page_id): item.slug_at_publish
            for item in public_repo.list_publication_pages(publication_id=str(funnel.active_publication_id))
        }
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return {
            "funnelId": str(funnel.id),
            "publicationId": publication_id,
            "pageId": str(pp.page_id),
            "slug": pp.slug_at_publish,
            "puckData": version.puck_data,
            "pageMap": page_map,
        }

    # Preview mode: allow viewing approved pages even if the funnel hasn't been published yet.
    page = session.scalars(
        select(FunnelPage).where(FunnelPage.funnel_id == funnel.id, FunnelPage.slug == slug)
    ).first()
    if not page:
        redirect = public_repo.get_redirect(funnel_id=str(funnel.id), from_slug=slug)
        if redirect:
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
            return {"redirectToSlug": redirect.to_slug}
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    versions_repo = FunnelPageVersionsRepository(session)
    approved = versions_repo.latest_for_page(page_id=str(page.id), status=FunnelPageVersionStatusEnum.approved)
    if not approved:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not approved")

    page_map = _preview_page_map(session=session, funnel_id=str(funnel.id))
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {
        "funnelId": str(funnel.id),
        "publicationId": publication_id,
        "pageId": str(page.id),
        "slug": page.slug,
        "puckData": approved.puck_data,
        "pageMap": page_map,
    }


@router.get("/funnels/{public_id}/graph")
def public_funnel_graph(
    public_id: str,
    response: Response,
    session: Session = Depends(get_session),
):
    funnel = _get_funnel_or_404(session=session, public_id=public_id)
    public_repo = FunnelPublicRepository(session)
    publication_id = _publication_id_for_public_response(funnel)
    if funnel.active_publication_id:
        publication = public_repo.get_active_publication(
            funnel_id=str(funnel.id), publication_id=str(funnel.active_publication_id)
        )
        if not publication:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publication not found")
        pages = public_repo.list_publication_pages(publication_id=str(funnel.active_publication_id))
        links = public_repo.list_publication_links(publication_id=str(funnel.active_publication_id))
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return {
            "publicId": str(funnel.public_id),
            "funnelId": str(funnel.id),
            "publicationId": publication_id,
            "entryPageId": str(publication.entry_page_id),
            "pages": [{"pageId": str(pp.page_id), "slug": pp.slug_at_publish} for pp in pages],
            "links": [jsonable_encoder(link) for link in links],
        }

    # Preview mode: only return approved pages for the graph.
    page_map = _preview_page_map(session=session, funnel_id=str(funnel.id))
    if not funnel.entry_page_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry page not found")
    if str(funnel.entry_page_id) not in page_map:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry page not approved")

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {
        "publicId": str(funnel.public_id),
        "funnelId": str(funnel.id),
        "publicationId": publication_id,
        "entryPageId": str(funnel.entry_page_id),
        "pages": [{"pageId": page_id, "slug": slug_value} for page_id, slug_value in page_map.items()],
        "links": [],
    }


@router.post("/events")
def ingest_public_events(
    payload: PublicEventsIngestRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    if not payload.events:
        return {"ingested": 0}

    publication_ids = {event.publicationId for event in payload.events}
    if len(publication_ids) != 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Batch must share publicationId")
    publication_id = next(iter(publication_ids))

    funnel = session.scalars(select(Funnel).where(Funnel.active_publication_id == publication_id)).first()
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publication not found")

    host = request.headers.get("host")
    ingested = 0
    for ev in payload.events:
        occurred_at = ev.occurredAt or datetime.now(timezone.utc)
        try:
            event_type = FunnelEventTypeEnum(ev.eventType)
        except Exception:
            continue

        session.add(
            FunnelEvent(
                occurred_at=occurred_at,
                org_id=funnel.org_id,
                client_id=funnel.client_id,
                campaign_id=funnel.campaign_id,
                funnel_id=funnel.id,
                publication_id=publication_id,
                page_id=ev.pageId,
                event_type=event_type,
                visitor_id=ev.visitorId,
                session_id=ev.sessionId,
                host=host,
                path=ev.path,
                referrer=ev.referrer,
                utm=ev.utm,
                props=ev.props,
            )
        )
        ingested += 1

    session.commit()
    return {"ingested": ingested}


@router.get("/assets/{public_id}")
def public_asset(
    public_id: str,
    session: Session = Depends(get_session),
):
    public_repo = FunnelPublicRepository(session)
    asset = public_repo.get_asset_by_public_id(public_id=public_id)
    if not asset or asset.status != FunnelAssetStatusEnum.ready:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    storage = MediaStorage()
    try:
        data, content_type = storage.download_bytes(key=asset.storage_key)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    headers = {"Cache-Control": "public, max-age=31536000, immutable"}
    return BinaryResponse(
        content=data,
        media_type=asset.content_type or content_type or "application/octet-stream",
        headers=headers,
    )
