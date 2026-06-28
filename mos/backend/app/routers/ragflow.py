from __future__ import annotations

import asyncio
import json
import queue
import threading
from collections.abc import AsyncIterator, Sequence
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.auth.dependencies import AuthContext, get_current_user
from app.llm.client import LLMClient, LLMGenerationParams
from app.observability import (
    LangfuseTraceContext,
    bind_langfuse_trace_context,
    start_langfuse_generation,
)
from app.services.ragflow_retrieval import (
    RagflowRetrievalConfigError,
    RagflowRetrievalError,
    build_grounded_prompt,
    get_ragflow_config,
    is_ragflow_retrieval_enabled,
    retrieve_chunks,
)

router = APIRouter(prefix="/ragflow", tags=["ragflow"])


class RagflowRetrieveRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    dataset_ids: list[str] | None = Field(None, alias="datasetIds")
    document_ids: list[str] | None = Field(None, alias="documentIds")
    page: int | None = Field(None, ge=1)
    page_size: int | None = Field(None, alias="pageSize", ge=1, le=100)
    similarity_threshold: float | None = Field(
        None,
        alias="similarityThreshold",
        ge=0.0,
        le=1.0,
    )
    vector_similarity_weight: float | None = Field(
        None,
        alias="vectorSimilarityWeight",
        ge=0.0,
        le=1.0,
    )
    top_k: int | None = Field(None, alias="topK", ge=1, le=4096)
    rerank_id: str | None = Field(None, alias="rerankId")
    keyword: bool | None = None
    highlight: bool | None = None
    cross_languages: list[str] | None = Field(None, alias="crossLanguages")
    metadata_condition: dict[str, Any] | None = Field(None, alias="metadataCondition")

    model_config = ConfigDict(populate_by_name=True)


class RagflowChatRequest(RagflowRetrieveRequest):
    model: str | None = None
    max_tokens: int = Field(2048, alias="maxTokens", ge=128, le=8000)
    temperature: float = Field(0.2, ge=0.0, le=1.0)
    system: str | None = Field(
        None,
        description="Optional system prompt. Defaults to a grounded marketing copilot prompt.",
    )


def _sse(data: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(data, separators=(',', ':'))}\n\n".encode()


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, RagflowRetrievalConfigError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, RagflowRetrievalError):
        return HTTPException(status_code=502, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def _retrieve(request: RagflowRetrieveRequest):
    try:
        return retrieve_chunks(
            question=request.prompt,
            dataset_ids=request.dataset_ids,
            document_ids=request.document_ids,
            page=request.page,
            page_size=request.page_size,
            similarity_threshold=request.similarity_threshold,
            vector_similarity_weight=request.vector_similarity_weight,
            top_k=request.top_k,
            rerank_id=request.rerank_id,
            keyword=request.keyword,
            highlight=request.highlight,
            cross_languages=request.cross_languages,
            metadata_condition=request.metadata_condition,
        )
    except (RagflowRetrievalConfigError, RagflowRetrievalError) as exc:
        raise _http_error(exc) from exc


def _serialize_chunks(chunks: Sequence[Any]) -> list[dict[str, Any]]:
    return [chunk.to_dict() for chunk in chunks]


@router.get("/config")
def ragflow_config(_auth: AuthContext = Depends(get_current_user)) -> dict[str, Any]:
    config = get_ragflow_config()
    return {
        "enabled": is_ragflow_retrieval_enabled(),
        "base_url": config.base_url,
        "api_key_configured": bool(config.api_key),
        "default_dataset_ids": list(config.default_dataset_ids),
        "default_document_ids": list(config.default_document_ids),
        "default_rerank_id_configured": bool(config.default_rerank_id),
        "page_size": config.page_size,
        "top_k": config.top_k,
        "similarity_threshold": config.similarity_threshold,
        "vector_similarity_weight": config.vector_similarity_weight,
        "keyword_enabled": config.keyword_enabled,
        "highlight_enabled": config.highlight_enabled,
        "generation_model": config.generation_model,
    }


@router.post("/retrieve")
def retrieve_ragflow_context(
    request: RagflowRetrieveRequest,
    _auth: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    result = _retrieve(request)
    return {
        "chunks": _serialize_chunks(result.chunks),
        "citations": result.citations(),
        "doc_aggs": result.doc_aggs,
        "total": result.total,
        "request": result.request,
    }


@router.post("/chat/stream")
def stream_ragflow_chat(
    request: RagflowChatRequest,
    auth: AuthContext = Depends(get_current_user),
) -> StreamingResponse:
    config = get_ragflow_config()
    model = request.model or config.generation_model
    system_prompt = request.system or (
        "You are a marketing copilot. Use retrieved RAGFlow context to ground every claim. "
        "If context is weak, say so explicitly and avoid speculation."
    )

    async def event_stream() -> AsyncIterator[bytes]:
        trace_context = LangfuseTraceContext(
            name="assistant.ragflow_chat",
            session_id="ragflow",
            user_id=auth.user_id,
            metadata={
                "orgId": auth.org_id,
                "model": model,
                "maxTokens": request.max_tokens,
                "temperature": request.temperature,
            },
            tags=["assistant", "ragflow", "deepseek", "stream"],
        )
        try:
            result = _retrieve(request)
            yield _sse(
                {
                    "type": "retrieval",
                    "chunks": _serialize_chunks(result.chunks),
                    "citations": result.citations(),
                    "total": result.total,
                }
            )
            grounded_prompt = build_grounded_prompt(
                user_prompt=request.prompt,
                chunks=result.chunks,
                system_prompt=system_prompt,
            )
            yield _sse({"type": "start", "model": model, "docsAttached": len(result.chunks)})

            # Keep observability context managers away from StreamingResponse yield points.
            # Starlette can resume sync stream iterators in a different context; if a
            # ContextVar/OpenTelemetry token crosses that boundary, cleanup can become
            # a user-visible SSE error after a successful answer. The worker owns
            # DeepSeek streaming and tracing; the async generator only emits queued SSE.
            event_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()

            def run_generation() -> None:
                output_parts: list[str] = []
                params = LLMGenerationParams(
                    model=model,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                )
                try:
                    with bind_langfuse_trace_context(trace_context):
                        with start_langfuse_generation(
                            name="llm.ragflow.deepseek_chat_stream",
                            model=model,
                            input={"prompt": request.prompt, "chunkCount": len(result.chunks)},
                            metadata={
                                "route": "/ragflow/chat/stream",
                                "retrievalRequest": result.request,
                                "citationCount": len(result.chunks),
                            },
                            model_parameters={
                                "temperature": request.temperature,
                                "max_tokens": request.max_tokens,
                            },
                            tags=["assistant", "ragflow", "deepseek", "stream"],
                            trace_name="assistant.ragflow_chat",
                        ) as generation:
                            for text in LLMClient(default_model=model).stream_text(
                                grounded_prompt, params=params
                            ):
                                output_parts.append(text)
                                event_queue.put({"type": "text", "text": text})
                            output_text = "".join(output_parts)
                            if generation is not None:
                                generation.update(
                                    output=output_text,
                                    metadata={"citationCount": len(result.chunks)},
                                )
                    event_queue.put(
                        {
                            "type": "done",
                            "citations": result.citations(),
                            "output_tokens": None,
                            "stop_reason": None,
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    event_queue.put({"type": "error", "message": str(exc)})
                finally:
                    event_queue.put(None)

            thread = threading.Thread(target=run_generation, daemon=True)
            thread.start()
            while True:
                event = await asyncio.to_thread(event_queue.get)
                if event is None:
                    break
                yield _sse(event)
        except HTTPException as exc:
            yield _sse({"type": "error", "message": str(exc.detail)})
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
