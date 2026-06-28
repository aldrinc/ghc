from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.env_loader import load_backend_env_files

_backend_root = Path(__file__).resolve().parents[2]
load_backend_env_files(_backend_root)


class RagflowRetrievalConfigError(RuntimeError):
    pass


class RagflowRetrievalError(RuntimeError):
    pass


@dataclass(frozen=True)
class RagflowRetrievalConfig:
    enabled: bool
    base_url: str
    api_key: str | None
    default_dataset_ids: tuple[str, ...] = ()
    default_document_ids: tuple[str, ...] = ()
    default_rerank_id: str | None = None
    timeout_seconds: float = 60.0
    page_size: int = 8
    top_k: int = 1024
    similarity_threshold: float = 0.2
    vector_similarity_weight: float = 0.3
    keyword_enabled: bool = False
    highlight_enabled: bool = False
    generation_model: str = "deepseek:deepseek-v4-pro"


@dataclass(frozen=True)
class RagflowChunk:
    id: str
    content: str
    dataset_id: str | None = None
    document_id: str | None = None
    document_name: str | None = None
    highlight: str | None = None
    positions: list[Any] = field(default_factory=list)
    similarity: float | None = None
    vector_similarity: float | None = None
    term_similarity: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "dataset_id": self.dataset_id,
            "document_id": self.document_id,
            "document_name": self.document_name,
            "highlight": self.highlight,
            "positions": self.positions,
            "similarity": self.similarity,
            "vector_similarity": self.vector_similarity,
            "term_similarity": self.term_similarity,
        }


@dataclass(frozen=True)
class RagflowRetrieveResult:
    chunks: list[RagflowChunk]
    doc_aggs: list[dict[str, Any]]
    total: int | None
    request: dict[str, Any]

    def citations(self) -> list[dict[str, Any]]:
        citations: list[dict[str, Any]] = []
        for index, chunk in enumerate(self.chunks, start=1):
            citations.append(
                {
                    "index": index,
                    "chunk_id": chunk.id,
                    "dataset_id": chunk.dataset_id,
                    "document_id": chunk.document_id,
                    "document_name": chunk.document_name,
                    "similarity": chunk.similarity,
                    "vector_similarity": chunk.vector_similarity,
                    "term_similarity": chunk.term_similarity,
                }
            )
        return citations


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_string_list(value: str | Iterable[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return ()
        return tuple(item.strip() for item in raw.split(",") if item.strip())
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def _parse_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw.strip())
    except ValueError as exc:
        raise RagflowRetrievalConfigError(f"{name} must be a number.") from exc


def _parse_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise RagflowRetrievalConfigError(f"{name} must be an integer.") from exc


def _clean_optional(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


def _validate_http_url(name: str, value: str) -> str:
    normalized = (value or "").strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RagflowRetrievalConfigError(
            f"{name} must be a fully qualified http(s) URL, e.g. 'http://127.0.0.1:9380'."
        )
    return normalized


def is_ragflow_retrieval_enabled() -> bool:
    return _parse_bool(os.getenv("RAGFLOW_RETRIEVAL_ENABLED"), default=False)


def get_ragflow_config() -> RagflowRetrievalConfig:
    return RagflowRetrievalConfig(
        enabled=is_ragflow_retrieval_enabled(),
        base_url=_validate_http_url(
            "RAGFLOW_BASE_URL",
            os.getenv("RAGFLOW_BASE_URL", "http://127.0.0.1:9380"),
        ),
        api_key=_clean_optional(os.getenv("RAGFLOW_API_KEY")),
        default_dataset_ids=_parse_string_list(os.getenv("RAGFLOW_DEFAULT_DATASET_IDS")),
        default_document_ids=_parse_string_list(os.getenv("RAGFLOW_DEFAULT_DOCUMENT_IDS")),
        default_rerank_id=_clean_optional(os.getenv("RAGFLOW_DEFAULT_RERANK_ID")),
        timeout_seconds=_parse_float_env("RAGFLOW_RETRIEVAL_TIMEOUT_SECONDS", 60.0),
        page_size=_parse_int_env("RAGFLOW_RETRIEVAL_PAGE_SIZE", 8),
        top_k=_parse_int_env("RAGFLOW_RETRIEVAL_TOP_K", 1024),
        similarity_threshold=_parse_float_env("RAGFLOW_RETRIEVAL_SIMILARITY_THRESHOLD", 0.2),
        vector_similarity_weight=_parse_float_env(
            "RAGFLOW_RETRIEVAL_VECTOR_SIMILARITY_WEIGHT",
            0.3,
        ),
        keyword_enabled=_parse_bool(os.getenv("RAGFLOW_RETRIEVAL_KEYWORD_ENABLED"), default=False),
        highlight_enabled=_parse_bool(
            os.getenv("RAGFLOW_RETRIEVAL_HIGHLIGHT_ENABLED"), default=False
        ),
        generation_model=os.getenv("RAGFLOW_GENERATION_MODEL", "deepseek:deepseek-v4-pro").strip()
        or "deepseek:deepseek-v4-pro",
    )


def _require_config(config: RagflowRetrievalConfig | None = None) -> RagflowRetrievalConfig:
    resolved = config or get_ragflow_config()
    if not resolved.enabled:
        raise RagflowRetrievalConfigError(
            "RAGFlow retrieval is disabled. Set RAGFLOW_RETRIEVAL_ENABLED=true to use this path."
        )
    if not resolved.api_key:
        raise RagflowRetrievalConfigError("RAGFLOW_API_KEY not configured.")
    if resolved.timeout_seconds <= 0:
        raise RagflowRetrievalConfigError(
            "RAGFLOW_RETRIEVAL_TIMEOUT_SECONDS must be greater than 0."
        )
    if resolved.page_size <= 0:
        raise RagflowRetrievalConfigError("RAGFLOW_RETRIEVAL_PAGE_SIZE must be greater than 0.")
    if resolved.top_k <= 0:
        raise RagflowRetrievalConfigError("RAGFLOW_RETRIEVAL_TOP_K must be greater than 0.")
    return resolved


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _normalize_chunk(raw: dict[str, Any]) -> RagflowChunk:
    chunk_id = str(raw.get("id") or "").strip()
    content = str(raw.get("content") or "").strip()
    if not chunk_id or not content:
        raise RagflowRetrievalError("RAGFlow returned a chunk without id or content.")
    document_name = raw.get("document_keyword") or raw.get("document_name") or raw.get("doc_name")
    dataset_id = raw.get("dataset_id") or raw.get("kb_id")
    positions = raw.get("positions")
    return RagflowChunk(
        id=chunk_id,
        content=content,
        dataset_id=str(dataset_id).strip() if dataset_id else None,
        document_id=str(raw.get("document_id")).strip() if raw.get("document_id") else None,
        document_name=str(document_name).strip() if document_name else None,
        highlight=str(raw.get("highlight")).strip() if raw.get("highlight") else None,
        positions=positions if isinstance(positions, list) else [],
        similarity=_safe_float(raw.get("similarity")),
        vector_similarity=_safe_float(raw.get("vector_similarity")),
        term_similarity=_safe_float(raw.get("term_similarity")),
    )


def build_retrieval_payload(
    *,
    question: str,
    config: RagflowRetrievalConfig,
    dataset_ids: list[str] | None = None,
    document_ids: list[str] | None = None,
    page: int | None = None,
    page_size: int | None = None,
    similarity_threshold: float | None = None,
    vector_similarity_weight: float | None = None,
    top_k: int | None = None,
    rerank_id: str | None = None,
    keyword: bool | None = None,
    highlight: bool | None = None,
    cross_languages: list[str] | None = None,
    metadata_condition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_question = question.strip()
    if not normalized_question:
        raise ValueError("RAGFlow retrieval question must be non-empty.")

    resolved_dataset_ids = _parse_string_list(dataset_ids) or config.default_dataset_ids
    resolved_document_ids = _parse_string_list(document_ids) or config.default_document_ids
    if not resolved_dataset_ids and not resolved_document_ids:
        raise RagflowRetrievalConfigError(
            "RAGFlow retrieval requires dataset IDs or document IDs. Set "
            "RAGFLOW_DEFAULT_DATASET_IDS or pass datasetIds/documentIds in the request."
        )

    payload: dict[str, Any] = {
        "question": normalized_question,
        "page": page if page is not None else 1,
        "page_size": page_size if page_size is not None else config.page_size,
        "similarity_threshold": (
            similarity_threshold
            if similarity_threshold is not None
            else config.similarity_threshold
        ),
        "vector_similarity_weight": (
            vector_similarity_weight
            if vector_similarity_weight is not None
            else config.vector_similarity_weight
        ),
        "top_k": top_k if top_k is not None else config.top_k,
        "keyword": keyword if keyword is not None else config.keyword_enabled,
        "highlight": highlight if highlight is not None else config.highlight_enabled,
    }
    if resolved_dataset_ids:
        payload["dataset_ids"] = list(resolved_dataset_ids)
    if resolved_document_ids:
        payload["document_ids"] = list(resolved_document_ids)
    resolved_rerank_id = _clean_optional(rerank_id) or config.default_rerank_id
    if resolved_rerank_id:
        payload["rerank_id"] = resolved_rerank_id
    resolved_cross_languages = _parse_string_list(cross_languages)
    if resolved_cross_languages:
        payload["cross_languages"] = list(resolved_cross_languages)
    if metadata_condition is not None:
        payload["metadata_condition"] = metadata_condition
    return payload


def retrieve_chunks(
    *,
    question: str,
    dataset_ids: list[str] | None = None,
    document_ids: list[str] | None = None,
    page: int | None = None,
    page_size: int | None = None,
    similarity_threshold: float | None = None,
    vector_similarity_weight: float | None = None,
    top_k: int | None = None,
    rerank_id: str | None = None,
    keyword: bool | None = None,
    highlight: bool | None = None,
    cross_languages: list[str] | None = None,
    metadata_condition: dict[str, Any] | None = None,
    config: RagflowRetrievalConfig | None = None,
) -> RagflowRetrieveResult:
    resolved_config = _require_config(config)
    payload = build_retrieval_payload(
        question=question,
        config=resolved_config,
        dataset_ids=dataset_ids,
        document_ids=document_ids,
        page=page,
        page_size=page_size,
        similarity_threshold=similarity_threshold,
        vector_similarity_weight=vector_similarity_weight,
        top_k=top_k,
        rerank_id=rerank_id,
        keyword=keyword,
        highlight=highlight,
        cross_languages=cross_languages,
        metadata_condition=metadata_condition,
    )
    url = f"{resolved_config.base_url}/api/v1/retrieval"
    headers = {
        "Authorization": f"Bearer {resolved_config.api_key}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=resolved_config.timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RagflowRetrievalError(f"RAGFlow retrieval request failed: {exc}") from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise RagflowRetrievalError("RAGFlow retrieval returned a non-JSON response.") from exc

    if not isinstance(body, dict):
        raise RagflowRetrievalError("RAGFlow retrieval returned an invalid response shape.")
    code = body.get("code")
    if code not in (0, "0", None):
        message = body.get("message") or body.get("msg") or "unknown RAGFlow error"
        raise RagflowRetrievalError(f"RAGFlow retrieval failed: {message}")

    data = body.get("data")
    if not isinstance(data, dict):
        raise RagflowRetrievalError("RAGFlow retrieval response missing data object.")
    raw_chunks = data.get("chunks")
    if not isinstance(raw_chunks, list):
        raise RagflowRetrievalError("RAGFlow retrieval response missing chunks list.")

    chunks = [_normalize_chunk(item) for item in raw_chunks if isinstance(item, dict)]
    doc_aggs = data.get("doc_aggs")
    return RagflowRetrieveResult(
        chunks=chunks,
        doc_aggs=doc_aggs if isinstance(doc_aggs, list) else [],
        total=_safe_int(data.get("total")),
        request=payload,
    )


def build_grounded_prompt(
    *, user_prompt: str, chunks: list[RagflowChunk], system_prompt: str
) -> str:
    if not chunks:
        return (
            f"{system_prompt}\n\n"
            "RAGFlow returned no chunks. State that no relevant indexed context was found, "
            "then answer "
            "only if the user explicitly asked for a general, non-grounded answer.\n\n"
            f"User request:\n{user_prompt.strip()}"
        )

    context_blocks: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        label_parts = [f"source={index}", f"chunk_id={chunk.id}"]
        if chunk.document_name:
            label_parts.append(f"document={chunk.document_name}")
        if chunk.similarity is not None:
            label_parts.append(f"similarity={chunk.similarity:.4f}")
        context_blocks.append(f"[{'; '.join(label_parts)}]\n{chunk.content}")

    context = "\n\n".join(context_blocks)
    return (
        f"{system_prompt}\n\n"
        "Use only the RAGFlow context below for factual claims. Cite sources inline as [source=N]. "
        "If the context is insufficient, say so explicitly and do not invent missing details.\n\n"
        f"RAGFlow context:\n{context}\n\n"
        f"User request:\n{user_prompt.strip()}"
    )
