from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import httpx

from app.db.base import session_scope
from app.db.enums import ClaudeContextFileStatusEnum
from app.db.repositories.claude_context_files import ClaudeContextFilesRepository


logger = logging.getLogger(__name__)
CLAUDE_API_BASE_URL = os.getenv("ANTHROPIC_API_BASE_URL") or os.getenv("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"
CLAUDE_HTTP_TIMEOUT = int(os.getenv("ANTHROPIC_HTTP_TIMEOUT", "300"))
CLAUDE_DEFAULT_MODEL = os.getenv("CLAUDE_DEFAULT_MODEL", "claude-3-5-sonnet-20241022")


@dataclass
class ClaudeFileUploadResult:
    file_id: str
    filename: str
    mime_type: str
    size_bytes: Optional[int]


_INVALID_FILENAME_CHARS = re.compile(r"[\\/:*?\"<>|]+")


def _sanitize_filename(filename: str) -> str:
    """
    Anthropic rejects certain characters (e.g., colons) in filenames.
    Replace invalid characters with underscores and trim length.
    """
    name_only = os.path.basename(filename)
    cleaned = _INVALID_FILENAME_CHARS.sub("_", name_only).strip()
    if not cleaned:
        cleaned = "upload"
    # Keep filenames reasonable for the API.
    return cleaned[:255]


def _upload_claude_file(*, filename: str, mime_type: str, content_bytes: bytes) -> ClaudeFileUploadResult:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured for Claude file upload")

    safe_filename = _sanitize_filename(filename)
    if safe_filename != filename:
        logger.debug(
            "claude_upload_filename_sanitized",
            extra={"original_filename": filename, "sanitized_filename": safe_filename},
        )

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "files-api-2025-04-14",
    }
    url = f"{CLAUDE_API_BASE_URL.rstrip('/')}/v1/files"
    files = {"file": (safe_filename, content_bytes, mime_type)}
    data = {"purpose": "message"}
    try:
        with httpx.Client(timeout=CLAUDE_HTTP_TIMEOUT) as client:
            response = client.post(url, headers=headers, files=files, data=data)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text if exc.response else ""
        status = exc.response.status_code if exc.response else "unknown"
        raise RuntimeError(f"Failed to upload file to Claude (status={status}): {body}") from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to upload file to Claude: {exc}") from exc

    file_id = payload.get("id")
    if not file_id:
        raise RuntimeError("Claude file upload returned no id")
    return ClaudeFileUploadResult(
        file_id=file_id,
        filename=payload.get("filename") or safe_filename,
        mime_type=payload.get("mime_type") or mime_type,
        size_bytes=payload.get("size_bytes"),
    )


def ensure_uploaded_to_claude(
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
    allow_stub: bool = False,
) -> str:
    """
    Upload a document to Claude Files API once per workspace/doc_key/hash and return the file_id.
    """
    sha256 = hashlib.sha256(content_bytes).hexdigest()
    sanitized_filename = _sanitize_filename(filename)
    with session_scope() as session:
        repo = ClaudeContextFilesRepository(session)
        existing = repo.get_by_doc_key_hash(
            org_id=org_id,
            idea_workspace_id=idea_workspace_id,
            doc_key=doc_key,
            sha256=sha256,
            product_id=product_id,
        )
        if (
            existing
            and existing.status == ClaudeContextFileStatusEnum.ready
            and existing.claude_file_id
        ):
            return existing.claude_file_id

    try:
        uploaded = _upload_claude_file(filename=sanitized_filename, mime_type=mime_type, content_bytes=content_bytes)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "claude_upload_failed",
            extra={
                "doc_key": doc_key,
                "idea_workspace_id": idea_workspace_id,
                "error": str(exc),
            },
        )
        with session_scope() as session:
            repo = ClaudeContextFilesRepository(session)
            repo.upsert_failed(
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
                filename=sanitized_filename,
                mime_type=mime_type,
                error=str(exc),
                drive_doc_id=drive_doc_id,
                drive_url=drive_url,
            )
        if allow_stub:
            return ""
        raise

    with session_scope() as session:
        repo = ClaudeContextFilesRepository(session)
        repo.upsert_ready(
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
            claude_file_id=uploaded.file_id,
            filename=uploaded.filename,
            mime_type=uploaded.mime_type,
            size_bytes=uploaded.size_bytes,
            drive_doc_id=drive_doc_id,
            drive_url=drive_url,
        )
    return uploaded.file_id


def build_document_blocks(records: Sequence[Any]) -> List[Dict[str, Any]]:
    """
    Convert ClaudeContextFile records into message document blocks.
    """
    blocks: List[Dict[str, Any]] = []
    for record in records:
        file_id = getattr(record, "claude_file_id", None)
        if not file_id:
            continue
        title = getattr(record, "doc_title", None) or getattr(record, "doc_key", None) or "Context"
        blocks.append(
            {
                "type": "document",
                "source": {"type": "file", "file_id": file_id},
                "title": title,
            }
    )
    return blocks


def _enforce_no_additional_properties(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Anthropic structured outputs require explicit additionalProperties: false on objects
    and reject some JSON Schema keywords (e.g., maxItems on arrays). Normalize the schema
    to avoid 400 errors.
    """

    def _walk(node: Any) -> Any:
        if not isinstance(node, dict):
            return node
        updated = dict(node)
        node_type = updated.get("type")
        is_object = node_type == "object" or (isinstance(node_type, list) and "object" in node_type)
        is_array = node_type == "array" or (isinstance(node_type, list) and "array" in node_type)
        is_number = node_type in {"number", "integer"} or (
            isinstance(node_type, list) and any(t in {"number", "integer"} for t in node_type)
        )

        if is_object and "additionalProperties" not in updated:
            updated["additionalProperties"] = False
        if is_array:
            # Anthropic structured outputs do not support maxItems/minItems today.
            updated.pop("maxItems", None)
            updated.pop("minItems", None)
        if is_number:
            # Anthropic structured outputs reject numeric bounds today (e.g. minimum/maximum).
            # We enforce constraints in application-level validation instead.
            for key in ("maximum", "minimum", "exclusiveMaximum", "exclusiveMinimum", "multipleOf"):
                updated.pop(key, None)

        props = updated.get("properties")
        if isinstance(props, dict):
            updated["properties"] = {k: _walk(v) for k, v in props.items()}

        items = updated.get("items")
        if isinstance(items, dict):
            updated["items"] = _walk(items)
        elif isinstance(items, list):
            updated["items"] = [_walk(i) for i in items]

        for key in ("anyOf", "oneOf", "allOf"):
            if key in updated and isinstance(updated[key], list):
                updated[key] = [_walk(v) for v in updated[key]]

        return updated

    return _walk(schema)


def _is_model_not_found(exc: httpx.HTTPStatusError) -> bool:
    resp = exc.response
    if not resp or resp.status_code != 404:
        return False
    try:
        payload = resp.json()
        err = payload.get("error") or {}
        return (err.get("type") == "not_found_error") and ("model" in (err.get("message") or "").lower())
    except Exception:
        return False


def _is_output_format_unsupported(exc: httpx.HTTPStatusError) -> bool:
    resp = exc.response
    if not resp or resp.status_code != 400:
        return False
    try:
        payload = resp.json()
        err = payload.get("error") or {}
        msg = (err.get("message") or "").lower()
        return "does not support output format" in msg
    except Exception:
        return False


def _extract_first_json_object(text: str) -> Dict[str, Any]:
    """
    Extract and parse the first top-level JSON object from an arbitrary text blob.

    Claude sometimes returns JSON with minor preambles/suffixes even when structured
    outputs are requested. This helper avoids failing the entire generation run when
    the content still includes a valid JSON object.
    """

    if not isinstance(text, str):
        raise ValueError("Input text must be a string")
    raw = text.strip()
    if not raw:
        raise ValueError("Input text is empty")

    start: int | None = None
    depth = 0
    in_string = False
    escape = False

    for i, ch in enumerate(raw):
        if start is None:
            if ch == "{":
                start = i
                depth = 1
                in_string = False
                escape = False
            continue

        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                candidate = raw[start : i + 1].strip()
                parsed = json.loads(candidate)
                if not isinstance(parsed, dict):
                    raise ValueError("Extracted JSON was not an object")
                return parsed

    raise ValueError("Unable to locate a complete JSON object in response text")


def _summarize_claude_structured_payload(payload: Any) -> str:
    if not isinstance(payload, dict):
        return f"type={type(payload).__name__}"

    model = payload.get("model")
    stop_reason = payload.get("stop_reason")
    content = payload.get("content")
    block_types: list[str] = []
    text_len = 0
    if isinstance(content, list):
        for block in content[:12]:
            if isinstance(block, dict):
                block_type = block.get("type")
                block_types.append(str(block_type) if block_type is not None else "unknown")
                if block_type == "text":
                    text_len += len(block.get("text") or "")
            else:
                block_types.append(type(block).__name__)

    return f"model={model!r} stop_reason={stop_reason!r} content_types={block_types} text_len={text_len}"


def call_claude_structured_message(
    *,
    model: str,
    system: Optional[str],
    user_content: List[Dict[str, Any]],
    output_schema: Dict[str, Any],
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> Dict[str, Any]:
    """
    Call Claude Messages API with structured outputs enabled and return parsed JSON + raw response.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured for Claude structured message call")

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "structured-outputs-2025-11-13,files-api-2025-04-14",
    }
    safe_schema = _enforce_no_additional_properties(output_schema)
    candidate_model = model or CLAUDE_DEFAULT_MODEL
    if not candidate_model:
        raise RuntimeError("Claude model is required for structured message call")

    body = {
        "model": candidate_model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": user_content}],
        "output_format": {"type": "json_schema", "schema": safe_schema},
    }
    if system:
        body["system"] = system

    url = f"{CLAUDE_API_BASE_URL.rstrip('/')}/v1/messages"
    try:
        with httpx.Client(timeout=CLAUDE_HTTP_TIMEOUT) as client:
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        if _is_model_not_found(exc):
            raise RuntimeError(f"Claude model not found: {candidate_model}") from exc
        if _is_output_format_unsupported(exc):
            raise RuntimeError(
                f"Claude model does not support structured outputs (output_format=json_schema): {candidate_model}"
            ) from exc
        body_text = exc.response.text if exc.response else ""
        status = exc.response.status_code if exc.response else "unknown"
        raise RuntimeError(f"Claude structured message failed (status={status}): {body_text}") from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Claude structured message failed: {exc}") from exc

    parsed = None
    output_block = payload.get("output")
    if isinstance(output_block, dict):
        parsed = output_block.get("parsed") or output_block.get("data") or output_block.get("content")

    text_content = ""
    stop_reason = payload.get("stop_reason") if isinstance(payload, dict) else None
    if parsed is None:
        content_blocks = payload.get("content") or []
        text_parts: List[str] = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text") or "")
        text_content = "".join(text_parts).strip()
        if text_content:
            try:
                parsed = json.loads(text_content)
            except Exception:
                try:
                    parsed = _extract_first_json_object(text_content)
                except Exception:
                    parsed = None

    if parsed is None:
        summary = _summarize_claude_structured_payload(payload)
        if stop_reason == "max_tokens":
            # This is very often truncated JSON. Surface a clear error so callers can increase max_tokens.
            raise RuntimeError(
                "Claude structured message returned non-JSON output (stop_reason=max_tokens). "
                f"Increase max_tokens. {summary}"
            )

        head = text_content[:400].replace("\n", "\\n") if text_content else ""
        raise RuntimeError(
            "Claude structured message returned no parsable output. "
            f"{summary} text_head={head!r}"
        )

    return {"parsed": parsed, "raw": payload, "text": text_content}
