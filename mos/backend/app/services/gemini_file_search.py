from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from app.db.base import session_scope
from app.db.enums import GeminiContextFileStatusEnum
from app.db.repositories.gemini_context_files import GeminiContextFilesRepository
from app.observability import start_langfuse_generation

try:
    from google import genai
    from google.genai import types as genai_types
    _GENAI_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - environment-specific dependency issue
    genai = None
    genai_types = None
    _GENAI_IMPORT_ERROR = exc


logger = logging.getLogger(__name__)

_INVALID_FILENAME_CHARS = re.compile(r"[\\/:*?\"<>|]+")
_DEFAULT_CHAT_MODEL = os.getenv("GEMINI_FILE_SEARCH_MODEL", "gemini-2.5-flash")
_POLL_INTERVAL_SECONDS = float(os.getenv("GEMINI_FILE_SEARCH_POLL_INTERVAL_SECONDS", "2.0"))
_POLL_TIMEOUT_SECONDS = float(os.getenv("GEMINI_FILE_SEARCH_POLL_TIMEOUT_SECONDS", "300.0"))


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def is_gemini_file_search_enabled() -> bool:
    return _parse_bool(os.getenv("GEMINI_FILE_SEARCH_ENABLED"), default=False)


class GeminiFileSearchConfigError(RuntimeError):
    pass


@dataclass
class GeminiContextFileUploadResult:
    store_name: str
    file_name: str | None
    document_name: str | None
    mime_type: str
    size_bytes: int | None


@dataclass
class GeminiCitation:
    title: str | None
    uri: str | None
    source_kind: str
    document_name: str | None = None
    start_index: int | None = None
    end_index: int | None = None


@dataclass
class GeminiChatResult:
    text: str
    stop_reason: str | None
    output_tokens: int | None
    citations: list[GeminiCitation]


def _sanitize_filename(filename: str) -> str:
    cleaned = _INVALID_FILENAME_CHARS.sub("_", (filename or "").strip())
    if not cleaned:
        cleaned = "upload.txt"
    return cleaned[:255]


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except Exception:
            return None
    return None


def _require_client():
    if not is_gemini_file_search_enabled():
        raise GeminiFileSearchConfigError(
            "Gemini File Search is disabled. Set GEMINI_FILE_SEARCH_ENABLED=true to use this flow."
        )
    if genai is None or genai_types is None:
        detail = str(_GENAI_IMPORT_ERROR) if _GENAI_IMPORT_ERROR else "unknown import error"
        raise GeminiFileSearchConfigError(
            "google-genai dependency is unavailable for Gemini File Search. "
            f"Original error: {detail}"
        )
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise GeminiFileSearchConfigError("GEMINI_API_KEY not configured for Gemini File Search.")
    return genai.Client(api_key=api_key)


def _build_store_display_name(*, doc_key: str, sha256: str) -> str:
    prefix = os.getenv("GEMINI_FILE_SEARCH_STORE_PREFIX", "mos")
    normalized_key = re.sub(r"[^A-Za-z0-9_-]+", "-", doc_key).strip("-").lower()
    if not normalized_key:
        normalized_key = "context"
    return f"{prefix}-{normalized_key}-{sha256[:12]}"


def _poll_operation(client, operation, *, timeout_seconds: float):
    started_at = time.time()
    latest = operation
    while not bool(getattr(latest, "done", False)):
        if (time.time() - started_at) > timeout_seconds:
            name = str(getattr(latest, "name", "") or "")
            raise RuntimeError(
                f"Timed out waiting for Gemini File Search operation to complete (operation={name})."
            )
        time.sleep(_POLL_INTERVAL_SECONDS)
        latest = client.operations.get(latest)
    error = getattr(latest, "error", None)
    if error:
        raise RuntimeError(f"Gemini File Search operation failed: {error}")
    return latest


def _poll_document_active(client, *, document_name: str, timeout_seconds: float):
    started_at = time.time()
    while True:
        doc = client.file_search_stores.documents.get(name=document_name)
        state = getattr(doc, "state", None)
        state_value = str(getattr(state, "value", state or ""))
        if state_value == "STATE_ACTIVE":
            return doc
        if state_value == "STATE_FAILED":
            raise RuntimeError(f"Gemini File Search document indexing failed for {document_name}.")
        if (time.time() - started_at) > timeout_seconds:
            raise RuntimeError(
                f"Timed out waiting for Gemini File Search document to become active (document={document_name})."
            )
        time.sleep(_POLL_INTERVAL_SECONDS)


def ensure_uploaded_to_gemini_file_search(
    *,
    org_id: str,
    idea_workspace_id: str,
    client_id: Optional[str],
    product_id: Optional[str],
    campaign_id: Optional[str],
    doc_key: str,
    doc_title: Optional[str],
    source_kind: str,
    step_key: Optional[str],
    filename: str,
    mime_type: str,
    content_bytes: bytes,
    drive_doc_id: Optional[str],
    drive_url: Optional[str],
) -> str:
    client = _require_client()
    sha256 = hashlib.sha256(content_bytes).hexdigest()
    safe_filename = _sanitize_filename(filename)
    normalized_mime = (mime_type or "text/plain").strip() or "text/plain"

    with session_scope() as session:
        repo = GeminiContextFilesRepository(session)
        existing = repo.get_by_doc_key_hash(
            org_id=org_id,
            idea_workspace_id=idea_workspace_id,
            doc_key=doc_key,
            sha256=sha256,
            product_id=product_id,
        )
        if (
            existing
            and existing.status == GeminiContextFileStatusEnum.ready
            and getattr(existing, "gemini_document_name", None)
        ):
            return str(existing.gemini_document_name)

    store_name = str(getattr(existing, "gemini_store_name", "") or "").strip() if existing else ""
    if not store_name:
        store = client.file_search_stores.create(
            config=genai_types.CreateFileSearchStoreConfig(
                display_name=_build_store_display_name(doc_key=doc_key, sha256=sha256),
            )
        )
        store_name = str(getattr(store, "name", "") or "").strip()
        if not store_name:
            raise RuntimeError("Gemini File Search store creation returned no store name.")

    uploaded_file_name: str | None = None
    document_name: str | None = None
    size_bytes: int | None = None
    try:
        file_buffer = io.BytesIO(content_bytes)
        file_buffer.name = safe_filename  # type: ignore[attr-defined]

        with start_langfuse_generation(
            name="llm.gemini.file_search.upload",
            model="gemini-file-search",
            input=f"{doc_key}:{sha256[:12]}",
            metadata={
                "org_id": org_id,
                "idea_workspace_id": idea_workspace_id,
                "product_id": product_id,
                "campaign_id": campaign_id,
                "doc_key": doc_key,
                "source_kind": source_kind,
                "step_key": step_key,
                "store_name": store_name,
                "mime_type": normalized_mime,
                "size_bytes": len(content_bytes),
            },
            tags=["gemini", "file_search", "upload"],
            trace_name="gemini.file_search.upload",
        ) as generation:
            operation = client.file_search_stores.upload_to_file_search_store(
                file_search_store_name=store_name,
                file=file_buffer,
                config=genai_types.UploadToFileSearchStoreConfig(
                    mime_type=normalized_mime,
                    display_name=safe_filename,
                    custom_metadata=[
                        genai_types.CustomMetadata(key="doc_key", string_value=doc_key),
                        genai_types.CustomMetadata(key="source_kind", string_value=source_kind),
                    ],
                ),
            )
            completed = _poll_operation(client, operation, timeout_seconds=_POLL_TIMEOUT_SECONDS)
            response = getattr(completed, "response", None)
            uploaded_file_name = str(getattr(response, "file_name", "") or "").strip() or None
            document_name = str(getattr(response, "document_name", "") or "").strip() or None
            if not document_name:
                raise RuntimeError(
                    "Gemini File Search upload operation completed without a document_name."
                )
            document = _poll_document_active(
                client,
                document_name=document_name,
                timeout_seconds=_POLL_TIMEOUT_SECONDS,
            )
            size_bytes = _safe_int(getattr(document, "size_bytes", None))
            if generation is not None:
                generation.update(
                    output=document_name,
                    usage_details={"input": len(content_bytes)},
                )
    except Exception as exc:
        logger.error(
            "gemini_file_search_upload_failed",
            extra={
                "org_id": org_id,
                "idea_workspace_id": idea_workspace_id,
                "product_id": product_id,
                "doc_key": doc_key,
                "error": str(exc),
            },
        )
        with session_scope() as session:
            GeminiContextFilesRepository(session).upsert_failed(
                org_id=org_id,
                idea_workspace_id=idea_workspace_id,
                client_id=client_id,
                product_id=product_id,
                campaign_id=campaign_id,
                doc_key=doc_key,
                doc_title=doc_title,
                source_kind=source_kind,
                step_key=step_key,
                sha256=sha256,
                gemini_store_name=store_name,
                gemini_file_name=uploaded_file_name,
                gemini_document_name=document_name,
                filename=safe_filename,
                mime_type=normalized_mime,
                error=str(exc),
                drive_doc_id=drive_doc_id,
                drive_url=drive_url,
            )
        raise

    with session_scope() as session:
        GeminiContextFilesRepository(session).upsert_ready(
            org_id=org_id,
            idea_workspace_id=idea_workspace_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            doc_key=doc_key,
            doc_title=doc_title,
            source_kind=source_kind,
            step_key=step_key,
            sha256=sha256,
            gemini_store_name=store_name,
            gemini_file_name=uploaded_file_name,
            gemini_document_name=document_name,
            filename=safe_filename,
            mime_type=normalized_mime,
            size_bytes=size_bytes,
            drive_doc_id=drive_doc_id,
            drive_url=drive_url,
        )
    return str(document_name)


def _extract_response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    candidates = getattr(response, "candidates", None)
    if not isinstance(candidates, list):
        raise RuntimeError("Gemini File Search response had no candidates.")
    parts: list[str] = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        content_parts = getattr(content, "parts", None) if content is not None else None
        if not isinstance(content_parts, list):
            continue
        for part in content_parts:
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str) and part_text:
                parts.append(part_text)
    joined = "".join(parts).strip()
    if joined:
        return joined
    raise RuntimeError("Gemini File Search response had no text content.")


def _extract_usage_output_tokens(response: Any) -> int | None:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return None
    return _safe_int(getattr(usage, "candidates_token_count", None))


def _extract_stop_reason(response: Any) -> str | None:
    candidates = getattr(response, "candidates", None)
    if not isinstance(candidates, list) or not candidates:
        return None
    reason = getattr(candidates[0], "finish_reason", None)
    if reason is None:
        return None
    return str(getattr(reason, "value", reason))


def _extract_citations(response: Any) -> list[GeminiCitation]:
    citations: list[GeminiCitation] = []
    seen: set[tuple[str, str, str, str, int | None, int | None]] = set()
    candidates = getattr(response, "candidates", None)
    if not isinstance(candidates, list):
        return citations
    for candidate in candidates:
        citation_meta = getattr(candidate, "citation_metadata", None)
        citation_rows = getattr(citation_meta, "citations", None) if citation_meta else None
        if isinstance(citation_rows, list):
            for row in citation_rows:
                citation = GeminiCitation(
                    title=getattr(row, "title", None),
                    uri=getattr(row, "uri", None),
                    source_kind="citation",
                    start_index=_safe_int(getattr(row, "start_index", None)),
                    end_index=_safe_int(getattr(row, "end_index", None)),
                )
                dedupe_key = (
                    citation.title or "",
                    citation.uri or "",
                    citation.source_kind,
                    citation.document_name or "",
                    citation.start_index,
                    citation.end_index,
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                citations.append(citation)

        grounding = getattr(candidate, "grounding_metadata", None)
        chunks = getattr(grounding, "grounding_chunks", None) if grounding else None
        if isinstance(chunks, list):
            for chunk in chunks:
                retrieved = getattr(chunk, "retrieved_context", None)
                if retrieved is not None:
                    citation = GeminiCitation(
                        title=getattr(retrieved, "title", None),
                        uri=getattr(retrieved, "uri", None),
                        source_kind="retrieved_context",
                        document_name=getattr(retrieved, "document_name", None),
                    )
                else:
                    web = getattr(chunk, "web", None)
                    if web is None:
                        continue
                    citation = GeminiCitation(
                        title=getattr(web, "title", None),
                        uri=getattr(web, "uri", None),
                        source_kind="web",
                    )
                dedupe_key = (
                    citation.title or "",
                    citation.uri or "",
                    citation.source_kind,
                    citation.document_name or "",
                    citation.start_index,
                    citation.end_index,
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                citations.append(citation)
    return citations


def generate_with_gemini_file_search(
    *,
    prompt: str,
    store_names: Sequence[str],
    model: str | None = None,
    max_tokens: int = 2048,
    temperature: float = 0.2,
    system_instruction: str | None = None,
) -> GeminiChatResult:
    if not prompt.strip():
        raise ValueError("prompt is required for Gemini File Search chat.")
    client = _require_client()
    unique_store_names = sorted({name.strip() for name in store_names if isinstance(name, str) and name.strip()})
    if not unique_store_names:
        raise RuntimeError("No Gemini File Search stores were provided for retrieval.")

    chat_model = model or _DEFAULT_CHAT_MODEL
    response = client.models.generate_content(
        model=chat_model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system_instruction,
            tools=[
                genai_types.Tool(
                    file_search=genai_types.FileSearch(
                        file_search_store_names=unique_store_names,
                    )
                )
            ],
        ),
    )
    return GeminiChatResult(
        text=_extract_response_text(response),
        stop_reason=_extract_stop_reason(response),
        output_tokens=_extract_usage_output_tokens(response),
        citations=_extract_citations(response),
    )

