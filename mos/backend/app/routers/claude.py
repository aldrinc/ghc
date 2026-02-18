from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Iterable, List, Sequence

from anthropic import Anthropic
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.repositories.claude_context_files import ClaudeContextFilesRepository
from app.observability import (
    LangfuseTraceContext,
    bind_langfuse_trace_context,
    start_langfuse_generation,
)
from app.services.claude_files import (
    CLAUDE_API_BASE_URL,
    CLAUDE_DEFAULT_MODEL,
    CLAUDE_HTTP_TIMEOUT,
    build_document_blocks,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/claude", tags=["claude"])


class ClaudeChatRequest(BaseModel):
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
        description="Optional system prompt. Defaults to a marketing copilot persona grounded in attached docs.",
    )

    model_config = ConfigDict(populate_by_name=True)


def _sse(data: Dict[str, Any]) -> bytes:
    return f"data: {json.dumps(data, separators=(',', ':'))}\n\n".encode("utf-8")


def _serialize_context_files(records: Sequence[Any]) -> List[Dict[str, Any]]:
    files: List[Dict[str, Any]] = []
    for record in records:
        file_id = getattr(record, "claude_file_id", None)
        if not file_id:
            continue
        created_at = getattr(record, "created_at", None)
        files.append(
            {
                "id": str(getattr(record, "id", "")),
                "doc_key": getattr(record, "doc_key", None),
                "doc_title": getattr(record, "doc_title", None),
                "source_kind": getattr(record, "source_kind", None),
                "step_key": getattr(record, "step_key", None),
                "claude_file_id": file_id,
                "filename": getattr(record, "filename", None),
                "mime_type": getattr(record, "mime_type", None),
                "size_bytes": getattr(record, "size_bytes", None),
                "drive_url": getattr(record, "drive_url", None),
                "created_at": created_at.isoformat() if created_at else None,
            }
        )
    return files


def _anthropic_usage_details(usage: Any) -> Dict[str, int] | None:
    if usage is None:
        return None
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    if isinstance(usage, dict):
        input_tokens = usage.get("input_tokens", input_tokens)
        output_tokens = usage.get("output_tokens", output_tokens)

    usage_details: Dict[str, int] = {}
    if isinstance(input_tokens, int):
        usage_details["input"] = input_tokens
    if isinstance(output_tokens, int):
        usage_details["output"] = output_tokens
    return usage_details or None


@router.get("/context")
def list_claude_context(
    ideaWorkspaceId: str,
    clientId: str | None = None,
    productId: str | None = None,
    campaignId: str | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    if not ideaWorkspaceId:
        raise HTTPException(status_code=400, detail="ideaWorkspaceId is required")
    if (clientId and not productId) or (productId and not clientId):
        raise HTTPException(status_code=400, detail="clientId and productId are required together")

    repo = ClaudeContextFilesRepository(session)
    records = repo.list_for_workspace_or_client(
        org_id=auth.org_id,
        idea_workspace_id=ideaWorkspaceId,
        client_id=clientId,
        product_id=productId,
        campaign_id=campaignId,
    )
    return {"files": _serialize_context_files(records)}


@router.post("/chat/stream")
def stream_claude_chat(
    request: ClaudeChatRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    if not request.idea_workspace_id:
        raise HTTPException(status_code=400, detail="ideaWorkspaceId is required")
    if (request.client_id and not request.product_id) or (request.product_id and not request.client_id):
        raise HTTPException(status_code=400, detail="clientId and productId are required together")

    repo = ClaudeContextFilesRepository(session)
    records = repo.list_for_workspace_or_client(
        org_id=auth.org_id,
        idea_workspace_id=request.idea_workspace_id,
        client_id=request.client_id,
        product_id=request.product_id,
        campaign_id=request.campaign_id,
    )
    if request.file_ids:
        allowed = set(request.file_ids)
        records = [rec for rec in records if getattr(rec, "claude_file_id", None) in allowed]

    doc_blocks = build_document_blocks(records)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    model = request.model or CLAUDE_DEFAULT_MODEL
    system_prompt = request.system or (
        "You are a marketing copilot. Use the attached documents to ground answers and call out "
        "assumptions when the context is thin. Keep outputs concise and production-ready."
    )

    def event_stream() -> Iterable[bytes]:
        user_content = [{"type": "text", "text": request.prompt}]
        if doc_blocks:
            user_content.extend(doc_blocks)

        trace_context = LangfuseTraceContext(
            name="assistant.claude_chat",
            session_id=request.idea_workspace_id,
            user_id=auth.user_id,
            metadata={
                "orgId": auth.org_id,
                "ideaWorkspaceId": request.idea_workspace_id,
                "clientId": request.client_id,
                "productId": request.product_id,
                "campaignId": request.campaign_id,
                "docsAttached": len(doc_blocks),
                "maxTokens": request.max_tokens,
                "temperature": request.temperature,
                "model": model,
            },
            tags=["assistant", "claude", "stream"],
        )
        try:
            with bind_langfuse_trace_context(trace_context):
                with start_langfuse_generation(
                    name="llm.anthropic.chat_stream",
                    model=model,
                    input=request.prompt,
                    metadata={
                        "route": "/claude/chat/stream",
                        "docsAttached": len(doc_blocks),
                        "systemPromptChars": len(system_prompt),
                    },
                    model_parameters={
                        "temperature": request.temperature,
                        "max_tokens": request.max_tokens,
                    },
                    tags=["assistant", "claude", "stream"],
                    trace_name="assistant.claude_chat",
                ) as generation:
                    client = Anthropic(
                        api_key=api_key,
                        base_url=CLAUDE_API_BASE_URL,
                        default_headers={
                            "anthropic-version": "2023-06-01",
                            "anthropic-beta": "files-api-2025-04-14",
                        },
                        timeout=CLAUDE_HTTP_TIMEOUT,
                    )
                    yield _sse({"type": "start", "model": model, "docsAttached": len(doc_blocks)})

                    output_parts: list[str] = []
                    with client.messages.stream(
                        model=model,
                        max_tokens=request.max_tokens,
                        temperature=request.temperature,
                        system=system_prompt,
                        messages=[{"role": "user", "content": user_content}],
                    ) as stream:
                        for event in stream:
                            if event.type == "content_block_delta":
                                delta = getattr(event, "delta", None)
                                text = getattr(delta, "text", None) if delta else None
                                if text:
                                    output_parts.append(text)
                                    yield _sse({"type": "text", "text": text})
                        final = stream.get_final_message()
                        stop_reason = getattr(final, "stop_reason", None) if final else None
                        usage = getattr(final, "usage", None)
                        output_tokens = None
                        if usage:
                            output_tokens = getattr(usage, "output_tokens", None) or (
                                usage.get("output_tokens") if isinstance(usage, dict) else None
                            )
                        if generation is not None:
                            generation.update(
                                output="".join(output_parts) if output_parts else None,
                                usage_details=_anthropic_usage_details(usage),
                            )
                        yield _sse(
                            {"type": "done", "stop_reason": stop_reason, "output_tokens": output_tokens}
                        )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "claude_chat_stream_failed",
                extra={"idea_workspace_id": request.idea_workspace_id, "client_id": request.client_id},
            )
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
