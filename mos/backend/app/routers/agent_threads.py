from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.schemas.agent_threads import (
    AgentThreadCreateRequest,
    AgentThreadDetailResponse,
    AgentThreadMessageRequest,
    AgentThreadPageSessionRequest,
    AgentThreadValidationResponse,
    ApprovalResolveRequest,
)
from app.services.agent_threads import AgentThreadsService, AgentThreadsServiceError


router = APIRouter(prefix="/agent-threads", tags=["agent-threads"])


def _sse(data: dict[str, object]) -> bytes:
    return f"data: {json.dumps(data, separators=(',', ':'))}\n\n".encode("utf-8")


@router.post("", response_model=AgentThreadDetailResponse, status_code=status.HTTP_201_CREATED)
def create_agent_thread(
    payload: AgentThreadCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    service = AgentThreadsService(session=session, org_id=auth.org_id, user_id=auth.user_id)
    try:
        return service.create_thread(
            client_id=payload.clientId,
            product_id=payload.productId,
            agent_profile=payload.agentProfile,
            objective_type=payload.objectiveType,
            bundle_key=payload.bundleKey,
            runtime_profile_key=payload.runtimeProfileKey,
            strategy_bundle_id=payload.strategyBundleId,
            title=payload.title,
            metadata_json=payload.metadata,
            site_id=payload.siteId,
            page_id=payload.pageId,
        )
    except AgentThreadsServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/page-session", response_model=AgentThreadDetailResponse)
def get_or_create_page_agent_thread(
    payload: AgentThreadPageSessionRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    service = AgentThreadsService(session=session, org_id=auth.org_id, user_id=auth.user_id)
    try:
        return service.get_or_create_page_thread(
            client_id=payload.clientId,
            product_id=payload.productId,
            site_id=payload.siteId,
            page_id=payload.pageId,
            agent_profile=payload.agentProfile,
            objective_type=payload.objectiveType,
            title=payload.title,
            bundle_key=payload.bundleKey,
            metadata_json=payload.metadata,
            force_new=payload.forceNew,
        )
    except AgentThreadsServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{thread_id}", response_model=AgentThreadDetailResponse)
def get_agent_thread(
    thread_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    service = AgentThreadsService(session=session, org_id=auth.org_id, user_id=auth.user_id)
    try:
        return service.get_thread_detail(thread_id=thread_id)
    except AgentThreadsServiceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{thread_id}/validation", response_model=AgentThreadValidationResponse)
def get_agent_thread_validation(
    thread_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    service = AgentThreadsService(session=session, org_id=auth.org_id, user_id=auth.user_id)
    try:
        return service.get_thread_validation(thread_id=thread_id)
    except AgentThreadsServiceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{thread_id}/messages", response_model=AgentThreadDetailResponse)
def post_agent_thread_message(
    thread_id: str,
    payload: AgentThreadMessageRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    service = AgentThreadsService(session=session, org_id=auth.org_id, user_id=auth.user_id)
    try:
        return service.post_message(thread_id=thread_id, content=payload.content)
    except AgentThreadsServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{thread_id}/messages/stream")
def post_agent_thread_message_stream(
    thread_id: str,
    payload: AgentThreadMessageRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    service = AgentThreadsService(session=session, org_id=auth.org_id, user_id=auth.user_id)

    def event_stream():
        try:
            for event in service.stream_message(thread_id=thread_id, content=payload.content):
                yield _sse(event)
        except AgentThreadsServiceError as exc:
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{thread_id}/approve", response_model=AgentThreadDetailResponse)
def resolve_agent_thread_approval(
    thread_id: str,
    payload: ApprovalResolveRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    service = AgentThreadsService(session=session, org_id=auth.org_id, user_id=auth.user_id)
    try:
        return service.resolve_approval(
            thread_id=thread_id,
            target_kind=payload.targetKind,
            target_id=payload.targetId,
            decision=payload.decision,
            notes=payload.notes,
        )
    except AgentThreadsServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{thread_id}/reset-session", response_model=AgentThreadDetailResponse)
def reset_agent_thread_session(
    thread_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    service = AgentThreadsService(session=session, org_id=auth.org_id, user_id=auth.user_id)
    try:
        return service.reset_runtime_session(thread_id=thread_id)
    except AgentThreadsServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
