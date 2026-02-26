from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Sequence

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.repositories.gemini_context_files import GeminiContextFilesRepository
from app.observability import (
    LangfuseTraceContext,
    bind_langfuse_trace_context,
    start_langfuse_generation,
)
from app.services.gemini_file_search import (
    GeminiCitation,
    generate_with_gemini_file_search,
    is_gemini_file_search_enabled,
)


router = APIRouter(prefix="/gemini", tags=["gemini"])


class GeminiChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    idea_workspace_id: str = Field(..., alias="ideaWorkspaceId")
    client_id: str | None = Field(None, alias="clientId")
    product_id: str | None = Field(None, alias="productId")
    campaign_id: str | None = Field(None, alias="campaignId")
    file_ids: List[str] | None = Field(None, alias="fileIds")
    model: str | None = None
    max_tokens: int = Field(2048, alias="maxTokens", ge=128, le=8000)
    temperature: float = Field(0.2, ge=0.0, le=1.0)
    system: str | None = Field(
        None,
        description="Optional system instruction. Defaults to a grounded marketing copilot prompt.",
    )

    model_config = ConfigDict(populate_by_name=True)


def _sse(data: Dict[str, Any]) -> bytes:
    return f"data: {json.dumps(data, separators=(',', ':'))}\n\n".encode("utf-8")


def _serialize_context_files(records: Sequence[Any]) -> List[Dict[str, Any]]:
    files: List[Dict[str, Any]] = []
    for record in records:
        document_name = getattr(record, "gemini_document_name", None)
        if not document_name:
            continue
        created_at = getattr(record, "created_at", None)
        files.append(
            {
                "id": str(getattr(record, "id", "")),
                "doc_key": getattr(record, "doc_key", None),
                "doc_title": getattr(record, "doc_title", None),
                "source_kind": getattr(record, "source_kind", None),
                "step_key": getattr(record, "step_key", None),
                "gemini_store_name": getattr(record, "gemini_store_name", None),
                "gemini_file_name": getattr(record, "gemini_file_name", None),
                "gemini_document_name": document_name,
                "filename": getattr(record, "filename", None),
                "mime_type": getattr(record, "mime_type", None),
                "size_bytes": getattr(record, "size_bytes", None),
                "drive_url": getattr(record, "drive_url", None),
                "created_at": created_at.isoformat() if created_at else None,
            }
        )
    return files


def _serialize_citations(citations: Sequence[GeminiCitation]) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    for citation in citations:
        payload.append(
            {
                "title": citation.title,
                "uri": citation.uri,
                "source_kind": citation.source_kind,
                "document_name": citation.document_name,
                "start_index": citation.start_index,
                "end_index": citation.end_index,
            }
        )
    return payload


@router.get("/context")
def list_gemini_context(
    ideaWorkspaceId: str,
    clientId: str | None = None,
    productId: str | None = None,
    campaignId: str | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    if not is_gemini_file_search_enabled():
        raise HTTPException(status_code=409, detail="Gemini File Search is disabled.")
    if not ideaWorkspaceId:
        raise HTTPException(status_code=400, detail="ideaWorkspaceId is required")
    if (clientId and not productId) or (productId and not clientId):
        raise HTTPException(status_code=400, detail="clientId and productId are required together")

    repo = GeminiContextFilesRepository(session)
    records = repo.list_for_workspace_or_client(
        org_id=auth.org_id,
        idea_workspace_id=ideaWorkspaceId,
        client_id=clientId,
        product_id=productId,
        campaign_id=campaignId,
    )
    return {"files": _serialize_context_files(records)}


@router.post("/chat/stream")
def stream_gemini_chat(
    request: GeminiChatRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    if not is_gemini_file_search_enabled():
        raise HTTPException(status_code=409, detail="Gemini File Search is disabled.")
    if not request.idea_workspace_id:
        raise HTTPException(status_code=400, detail="ideaWorkspaceId is required")
    if (request.client_id and not request.product_id) or (request.product_id and not request.client_id):
        raise HTTPException(status_code=400, detail="clientId and productId are required together")

    repo = GeminiContextFilesRepository(session)
    records = repo.list_for_workspace_or_client(
        org_id=auth.org_id,
        idea_workspace_id=request.idea_workspace_id,
        client_id=request.client_id,
        product_id=request.product_id,
        campaign_id=request.campaign_id,
    )
    if request.file_ids:
        allowed = set(request.file_ids)
        records = [
            rec for rec in records if str(getattr(rec, "gemini_document_name", "") or "").strip() in allowed
        ]

    store_names = sorted(
        {
            str(getattr(rec, "gemini_store_name", "") or "").strip()
            for rec in records
            if str(getattr(rec, "gemini_store_name", "") or "").strip()
        }
    )
    if not store_names:
        raise HTTPException(
            status_code=409,
            detail="No Gemini File Search documents are available for this scope and selection.",
        )

    model = request.model
    system_prompt = request.system or (
        "You are a marketing copilot. Use file-search evidence to ground every claim. "
        "If context is weak, say so explicitly and avoid speculation."
    )

    def event_stream() -> Iterable[bytes]:
        trace_context = LangfuseTraceContext(
            name="assistant.gemini_file_search_chat",
            session_id=request.idea_workspace_id,
            user_id=auth.user_id,
            metadata={
                "orgId": auth.org_id,
                "ideaWorkspaceId": request.idea_workspace_id,
                "clientId": request.client_id,
                "productId": request.product_id,
                "campaignId": request.campaign_id,
                "storesAttached": len(store_names),
                "maxTokens": request.max_tokens,
                "temperature": request.temperature,
                "model": model,
            },
            tags=["assistant", "gemini", "file_search", "stream"],
        )
        try:
            with bind_langfuse_trace_context(trace_context):
                with start_langfuse_generation(
                    name="llm.gemini.file_search_chat",
                    model=model or "gemini-file-search-default",
                    input=request.prompt,
                    metadata={
                        "route": "/gemini/chat/stream",
                        "storesAttached": len(store_names),
                        "systemPromptChars": len(system_prompt),
                    },
                    model_parameters={
                        "temperature": request.temperature,
                        "max_tokens": request.max_tokens,
                    },
                    tags=["assistant", "gemini", "file_search", "stream"],
                    trace_name="assistant.gemini_file_search_chat",
                ) as generation:
                    yield _sse(
                        {
                            "type": "start",
                            "model": model,
                            "docsAttached": len(records),
                            "storesAttached": len(store_names),
                        }
                    )
                    result = generate_with_gemini_file_search(
                        prompt=request.prompt,
                        store_names=store_names,
                        model=model,
                        max_tokens=request.max_tokens,
                        temperature=request.temperature,
                        system_instruction=system_prompt,
                    )
                    if result.text:
                        yield _sse({"type": "text", "text": result.text})
                    if generation is not None:
                        usage = {}
                        if isinstance(result.output_tokens, int):
                            usage["output"] = result.output_tokens
                        generation.update(
                            output=result.text,
                            usage_details=usage or None,
                            metadata={"citationCount": len(result.citations)},
                        )
                    yield _sse(
                        {
                            "type": "done",
                            "stop_reason": result.stop_reason,
                            "output_tokens": result.output_tokens,
                            "citations": _serialize_citations(result.citations),
                        }
                    )
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")

