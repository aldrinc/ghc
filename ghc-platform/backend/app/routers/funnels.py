from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.enums import FunnelPageVersionSourceEnum, FunnelPageVersionStatusEnum, FunnelStatusEnum
from app.db.models import Campaign, FunnelPageSlugRedirect, FunnelPageVersion
from app.db.repositories.funnels import FunnelPageVersionsRepository, FunnelPagesRepository, FunnelsRepository
from app.schemas.funnels import (
    FunnelCreateRequest,
    FunnelDuplicateRequest,
    FunnelPageCreateRequest,
    FunnelPageAIGenerateRequest,
    FunnelPageSaveDraftRequest,
    FunnelPageUpdateRequest,
    FunnelUpdateRequest,
)
from app.services.funnel_ai import generate_funnel_page_draft, stream_funnel_page_draft
from app.services.funnels import (
    default_puck_data,
    duplicate_funnel,
    generate_unique_slug,
    publish_funnel,
)

router = APIRouter(prefix="/funnels", tags=["funnels"])


@router.get("")
def list_funnels(
    clientId: str | None = None,
    campaignId: str | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list:
    repo = FunnelsRepository(session)
    campaign_is_null = campaignId == "null"
    campaign_id_value = None if campaign_is_null else campaignId
    return jsonable_encoder(
        repo.list(
            org_id=auth.org_id,
            client_id=clientId,
            campaign_id=campaign_id_value,
            campaign_is_null=campaign_is_null if campaignId is not None else None,
        )
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_funnel(
    payload: FunnelCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    campaign_id = payload.campaignId or None
    if campaign_id:
        campaign = session.scalars(
            select(Campaign).where(Campaign.org_id == auth.org_id, Campaign.id == campaign_id)
        ).first()
        if not campaign:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
        if str(campaign.client_id) != str(payload.clientId):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Campaign must belong to the same client",
            )

    repo = FunnelsRepository(session)
    funnel = repo.create(
        org_id=auth.org_id,
        client_id=payload.clientId,
        campaign_id=campaign_id,
        name=payload.name,
        description=payload.description,
        status=FunnelStatusEnum.draft,
    )
    return jsonable_encoder(funnel)


@router.get("/{funnel_id}")
def get_funnel(
    funnel_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    funnels_repo = FunnelsRepository(session)
    pages_repo = FunnelPagesRepository(session)
    versions_repo = FunnelPageVersionsRepository(session)

    funnel = funnels_repo.get(org_id=auth.org_id, funnel_id=funnel_id)
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")

    pages = pages_repo.list(funnel_id=funnel_id)
    page_summaries = []
    all_approved = True
    for page in pages:
        draft = versions_repo.latest_for_page(page_id=str(page.id), status=FunnelPageVersionStatusEnum.draft)
        approved = versions_repo.latest_for_page(page_id=str(page.id), status=FunnelPageVersionStatusEnum.approved)
        if not approved:
            all_approved = False
        page_summaries.append(
            {
                **jsonable_encoder(page),
                "latestDraftVersionId": str(draft.id) if draft else None,
                "latestApprovedVersionId": str(approved.id) if approved else None,
            }
        )

    can_publish = bool(funnel.entry_page_id) and bool(pages) and all_approved
    return {
        **jsonable_encoder(funnel),
        "pages": page_summaries,
        "canPublish": can_publish,
    }


@router.patch("/{funnel_id}")
def update_funnel(
    funnel_id: str,
    payload: FunnelUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    funnels_repo = FunnelsRepository(session)
    funnel = funnels_repo.get(org_id=auth.org_id, funnel_id=funnel_id)
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")

    fields = {}
    if payload.name is not None:
        fields["name"] = payload.name
    if payload.description is not None:
        fields["description"] = payload.description
    if payload.campaignId is not None:
        campaign_id = payload.campaignId or None
        if campaign_id:
            campaign = session.scalars(
                select(Campaign).where(Campaign.org_id == auth.org_id, Campaign.id == campaign_id)
            ).first()
            if not campaign:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
            if str(campaign.client_id) != str(funnel.client_id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Campaign must belong to the same client",
                )
        fields["campaign_id"] = campaign_id
    if payload.entryPageId is not None:
        entry_page_id = payload.entryPageId or None
        if entry_page_id:
            pages_repo = FunnelPagesRepository(session)
            page = pages_repo.get(funnel_id=funnel_id, page_id=entry_page_id)
            if not page:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Entry page must belong to the funnel",
                )
        fields["entry_page_id"] = entry_page_id

    updated = funnels_repo.update(org_id=auth.org_id, funnel_id=funnel_id, **fields)
    return jsonable_encoder(updated)


@router.post("/{funnel_id}/disable")
def disable_funnel(
    funnel_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = FunnelsRepository(session)
    funnel = repo.update(org_id=auth.org_id, funnel_id=funnel_id, status=FunnelStatusEnum.disabled)
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")
    return jsonable_encoder(funnel)


@router.post("/{funnel_id}/enable")
def enable_funnel(
    funnel_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = FunnelsRepository(session)
    funnel = repo.get(org_id=auth.org_id, funnel_id=funnel_id)
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")
    next_status = FunnelStatusEnum.published if funnel.active_publication_id else FunnelStatusEnum.draft
    funnel = repo.update(org_id=auth.org_id, funnel_id=funnel_id, status=next_status)
    return jsonable_encoder(funnel)


@router.post("/{funnel_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_funnel_route(
    funnel_id: str,
    payload: FunnelDuplicateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    try:
        new_funnel = duplicate_funnel(
            session=session,
            org_id=auth.org_id,
            source_funnel_id=funnel_id,
            target_campaign_id=payload.targetCampaignId,
            name=payload.name,
            copy_mode=payload.copyMode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return jsonable_encoder(new_funnel)


@router.post("/{funnel_id}/pages", status_code=status.HTTP_201_CREATED)
def create_page(
    funnel_id: str,
    payload: FunnelPageCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    funnels_repo = FunnelsRepository(session)
    funnel = funnels_repo.get(org_id=auth.org_id, funnel_id=funnel_id)
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")

    pages_repo = FunnelPagesRepository(session)
    pages = pages_repo.list(funnel_id=funnel_id)
    ordering = len(pages)
    desired = payload.slug or payload.name
    unique_slug = generate_unique_slug(session, funnel_id=funnel_id, desired_slug=desired)

    page = pages_repo.create(funnel_id=funnel_id, name=payload.name, slug=unique_slug, ordering=ordering)

    version = FunnelPageVersion(
        page_id=page.id,
        status=FunnelPageVersionStatusEnum.draft,
        puck_data=default_puck_data(),
        source=FunnelPageVersionSourceEnum.human,
        created_at=datetime.now(timezone.utc),
    )
    session.add(version)
    session.commit()
    session.refresh(page)
    session.refresh(version)

    return {"page": jsonable_encoder(page), "draftVersion": jsonable_encoder(version)}


@router.get("/{funnel_id}/pages/{page_id}")
def get_page(
    funnel_id: str,
    page_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    funnels_repo = FunnelsRepository(session)
    funnel = funnels_repo.get(org_id=auth.org_id, funnel_id=funnel_id)
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")

    pages_repo = FunnelPagesRepository(session)
    page = pages_repo.get(funnel_id=funnel_id, page_id=page_id)
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    versions_repo = FunnelPageVersionsRepository(session)
    draft = versions_repo.latest_for_page(page_id=str(page.id), status=FunnelPageVersionStatusEnum.draft)
    approved = versions_repo.latest_for_page(page_id=str(page.id), status=FunnelPageVersionStatusEnum.approved)

    return {
        "page": jsonable_encoder(page),
        "latestDraft": jsonable_encoder(draft) if draft else None,
        "latestApproved": jsonable_encoder(approved) if approved else None,
    }


@router.put("/{funnel_id}/pages/{page_id}")
def save_draft(
    funnel_id: str,
    page_id: str,
    payload: FunnelPageSaveDraftRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    funnels_repo = FunnelsRepository(session)
    if not funnels_repo.get(org_id=auth.org_id, funnel_id=funnel_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")

    pages_repo = FunnelPagesRepository(session)
    page = pages_repo.get(funnel_id=funnel_id, page_id=page_id)
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    version = FunnelPageVersion(
        page_id=page.id,
        status=FunnelPageVersionStatusEnum.draft,
        puck_data=payload.puckData,
        source=FunnelPageVersionSourceEnum.human,
        created_at=datetime.now(timezone.utc),
    )
    session.add(version)
    session.commit()
    session.refresh(version)
    return jsonable_encoder(version)


@router.patch("/{funnel_id}/pages/{page_id}")
def update_page(
    funnel_id: str,
    page_id: str,
    payload: FunnelPageUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    funnels_repo = FunnelsRepository(session)
    if not funnels_repo.get(org_id=auth.org_id, funnel_id=funnel_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")

    pages_repo = FunnelPagesRepository(session)
    page = pages_repo.get(funnel_id=funnel_id, page_id=page_id)
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    update_fields = {}
    if payload.name is not None:
        update_fields["name"] = payload.name
    if payload.ordering is not None:
        update_fields["ordering"] = payload.ordering
    if payload.slug is not None:
        new_slug = generate_unique_slug(
            session,
            funnel_id=funnel_id,
            desired_slug=payload.slug,
            exclude_page_id=str(page.id),
        )
        if page.slug != new_slug:
            session.add(
                FunnelPageSlugRedirect(
                    funnel_id=funnel_id,
                    page_id=page.id,
                    from_slug=page.slug,
                    to_slug=new_slug,
                )
            )
        update_fields["slug"] = new_slug

    updated = pages_repo.update(page_id=page_id, **update_fields)
    return jsonable_encoder(updated)


@router.post("/{funnel_id}/pages/{page_id}/approve", status_code=status.HTTP_201_CREATED)
def approve_page(
    funnel_id: str,
    page_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    funnels_repo = FunnelsRepository(session)
    if not funnels_repo.get(org_id=auth.org_id, funnel_id=funnel_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")

    pages_repo = FunnelPagesRepository(session)
    page = pages_repo.get(funnel_id=funnel_id, page_id=page_id)
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    versions_repo = FunnelPageVersionsRepository(session)
    draft = versions_repo.latest_for_page(page_id=str(page.id), status=FunnelPageVersionStatusEnum.draft)
    if not draft:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No draft version to approve")

    approved = FunnelPageVersion(
        page_id=page.id,
        status=FunnelPageVersionStatusEnum.approved,
        puck_data=draft.puck_data,
        source=draft.source,
        ai_metadata=draft.ai_metadata,
        created_at=datetime.now(timezone.utc),
    )
    session.add(approved)
    session.commit()
    session.refresh(approved)
    return jsonable_encoder(approved)


@router.post("/{funnel_id}/publish", status_code=status.HTTP_201_CREATED)
def publish_funnel_route(
    funnel_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    try:
        publication = publish_funnel(
            session=session,
            org_id=auth.org_id,
            user_id=auth.user_id,
            funnel_id=funnel_id,
        )
    except ValueError as exc:
        message = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not found" in message.lower() else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=message) from exc
    return {"publicationId": str(publication.id)}


@router.post("/{funnel_id}/pages/{page_id}/ai/generate", status_code=status.HTTP_201_CREATED)
def ai_generate_page_draft(
    funnel_id: str,
    page_id: str,
    payload: FunnelPageAIGenerateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    try:
        assistant_message, version, puck_data, generated_images = generate_funnel_page_draft(
            session=session,
            org_id=auth.org_id,
            user_id=auth.user_id,
            funnel_id=funnel_id,
            page_id=page_id,
            prompt=payload.prompt,
            messages=[m.model_dump() for m in payload.messages] if payload.messages else None,
            current_puck_data=payload.currentPuckData,
            model=payload.model,
            temperature=payload.temperature,
            max_tokens=payload.maxTokens,
            generate_images=payload.generateImages,
            max_images=payload.maxImages,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return {
        "assistantMessage": assistant_message,
        "puckData": puck_data,
        "draftVersionId": str(version.id),
        "generatedImages": generated_images,
    }


@router.post("/{funnel_id}/pages/{page_id}/ai/generate/stream")
def ai_generate_page_draft_stream(
    funnel_id: str,
    page_id: str,
    payload: FunnelPageAIGenerateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    def _sse(data: dict) -> bytes:
        return f"data: {json.dumps(data, separators=(',', ':'))}\n\n".encode("utf-8")

    def event_stream():
        for event in stream_funnel_page_draft(
            session=session,
            org_id=auth.org_id,
            user_id=auth.user_id,
            funnel_id=funnel_id,
            page_id=page_id,
            prompt=payload.prompt,
            messages=[m.model_dump() for m in payload.messages] if payload.messages else None,
            current_puck_data=payload.currentPuckData,
            model=payload.model,
            temperature=payload.temperature,
            max_tokens=payload.maxTokens,
            generate_images=payload.generateImages,
            max_images=payload.maxImages,
        ):
            yield _sse(event)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
