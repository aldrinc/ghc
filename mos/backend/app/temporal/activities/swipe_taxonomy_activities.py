from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from temporalio import activity

from app.config import settings
from app.db.base import session_scope
from app.db.repositories.swipes import CompanySwipesRepository
from app.schemas.swipe_assets import SwipeTaxonomyGeminiOutput
from app.services.media_storage import MediaStorage

try:
    from google import genai
    from google.genai import types as genai_types
    _GENAI_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - dependency/runtime specific
    genai = None
    genai_types = None
    _GENAI_IMPORT_ERROR = exc


_GEMINI_CLIENT: Any | None = None
_SWIPE_TAXONOMY_MAX_BYTES = 20 * 1024 * 1024


def _ensure_gemini_client():
    global _GEMINI_CLIENT
    if _GEMINI_CLIENT is not None:
        return _GEMINI_CLIENT
    if genai is None or genai_types is None:
        detail = str(_GENAI_IMPORT_ERROR) if _GENAI_IMPORT_ERROR else "unknown import error"
        raise RuntimeError(
            "google-genai dependency is unavailable for swipe taxonomy analysis. "
            f"Original error: {detail}"
        )
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required for swipe taxonomy analysis.")
    _GEMINI_CLIENT = genai.Client(api_key=api_key)
    return _GEMINI_CLIENT


def _normalize_model_name(model: str | None) -> str:
    normalized = str(model or settings.SWIPE_TAXONOMY_MODEL or "").strip()
    if not normalized:
        raise RuntimeError("SWIPE_TAXONOMY_MODEL must be configured for swipe taxonomy analysis.")
    if normalized.startswith("models/"):
        return normalized.split("/", 1)[1]
    return normalized


def _extract_response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        texts: list[str] = []
        for part in parts:
            value = getattr(part, "text", None)
            if isinstance(value, str) and value.strip():
                texts.append(value.strip())
        if texts:
            return "\n".join(texts)
    return ""


def _download_http_bytes(url: str) -> tuple[bytes, str | None]:
    with httpx.Client(follow_redirects=True, timeout=float(settings.SWIPE_GEMINI_TIMEOUT_SECONDS or 300)) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type")
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes(8192):
                if not chunk:
                    continue
                total += len(chunk)
                if total > _SWIPE_TAXONOMY_MAX_BYTES:
                    raise RuntimeError(
                        f"Swipe taxonomy source media exceeds {_SWIPE_TAXONOMY_MAX_BYTES} bytes."
                    )
                chunks.append(chunk)
            return b"".join(chunks), content_type


def _load_media_bytes(media: Any) -> tuple[bytes, str]:
    mime_type = str(getattr(media, "mime_type", "") or "").strip() or None
    path_value = str(getattr(media, "path", "") or "").strip() or None
    for candidate in (
        str(getattr(media, "download_url", "") or "").strip() or None,
        str(getattr(media, "url", "") or "").strip() or None,
        path_value if path_value and urlparse(path_value).scheme in {"http", "https"} else None,
    ):
        if not candidate:
            continue
        data, downloaded_mime_type = _download_http_bytes(candidate)
        resolved_mime_type = mime_type or downloaded_mime_type or "application/octet-stream"
        return data, resolved_mime_type

    if not path_value:
        raise RuntimeError("Swipe media is missing a readable path or URL.")

    storage = MediaStorage()
    data, stored_mime_type = storage.download_bytes(key=path_value)
    if not data:
        raise RuntimeError("Swipe media bytes are empty.")
    resolved_mime_type = mime_type or stored_mime_type or "application/octet-stream"
    return data, resolved_mime_type


def _call_gemini_taxonomy(
    *,
    model: str,
    media_bytes: bytes,
    mime_type: str,
    context_payload: dict[str, Any],
) -> SwipeTaxonomyGeminiOutput:
    gemini_client = _ensure_gemini_client()
    prompt = (
        "Classify the attached marketing swipe image.\n"
        "Use only the image and the provided metadata.\n"
        "Return JSON only.\n"
        "If a field is unclear, return null.\n\n"
        f"Metadata:\n{json.dumps(context_payload, ensure_ascii=False, sort_keys=True)}"
    )
    response = gemini_client.models.generate_content(
        model=_normalize_model_name(model),
        contents=[
            prompt,
            genai_types.Part.from_bytes(data=media_bytes, mime_type=mime_type),
        ],
        config=genai_types.GenerateContentConfig(
            system_instruction=(
                "You classify direct-response swipe images for creative generation. "
                "Return exactly one JSON object that matches the provided schema. "
                "Do not include prose, markdown, or extra keys."
            ),
            temperature=0,
            max_output_tokens=1024,
            response_mime_type="application/json",
            response_json_schema=SwipeTaxonomyGeminiOutput.model_json_schema(),
        ),
    )

    parsed = getattr(response, "parsed", None)
    if parsed is not None and hasattr(parsed, "model_dump"):
        parsed = parsed.model_dump(mode="json", by_alias=True, exclude_none=False)
    if parsed is None:
        raw_text = _extract_response_text(response)
        if not raw_text:
            raise RuntimeError("Gemini returned no swipe taxonomy payload.")
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Gemini returned invalid swipe taxonomy JSON: {raw_text[:500]!r}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Gemini returned a non-object swipe taxonomy payload.")
    return SwipeTaxonomyGeminiOutput.model_validate(parsed)


def _set_analysis_status(*, org_id: str, swipe_asset_id: str, status_value: str, error: str | None = None) -> None:
    with session_scope() as session:
        repo = CompanySwipesRepository(session)
        asset = repo.get_asset(org_id=org_id, swipe_id=swipe_asset_id)
        if asset is None:
            return
        asset.analysis_status = status_value
        asset.analysis_error = error
        asset.analysis_updated_at = datetime.now(timezone.utc)
        session.commit()


@activity.defn(name="swipes.analyze_swipe_asset")
def analyze_swipe_asset_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params.get("org_id") or "").strip()
    swipe_asset_id = str(params.get("swipe_asset_id") or "").strip()
    model = str(params.get("model") or settings.SWIPE_TAXONOMY_MODEL or "").strip() or None

    if not org_id:
        raise ValueError("org_id is required for swipe taxonomy analysis.")
    if not swipe_asset_id:
        raise ValueError("swipe_asset_id is required for swipe taxonomy analysis.")

    _set_analysis_status(org_id=org_id, swipe_asset_id=swipe_asset_id, status_value="analyzing")

    try:
        with session_scope() as session:
            repo = CompanySwipesRepository(session)
            asset = repo.get_asset(org_id=org_id, swipe_id=swipe_asset_id)
            if asset is None:
                raise RuntimeError(f"Swipe asset not found: {swipe_asset_id}")
            media_items = repo.list_media(org_id=org_id, swipe_asset_id=swipe_asset_id)
            if not media_items:
                raise RuntimeError(f"Swipe asset has no media: {swipe_asset_id}")

            media = media_items[0]
            media_bytes, mime_type = _load_media_bytes(media)
            if not mime_type.startswith("image/"):
                raise RuntimeError(
                    f"Swipe taxonomy analysis currently supports images only. mime_type={mime_type}"
                )

            context_payload = {
                "source_kind": asset.source_kind,
                "origin_system": asset.origin_system,
                "title": asset.title,
                "body": asset.body,
                "cta_text": asset.cta_text,
                "display_format": asset.display_format,
                "landing_page": asset.landing_page,
                "mime_type": mime_type,
                "existing_channel": asset.channel,
                "existing_destination_type": asset.destination_type,
            }
            parsed = _call_gemini_taxonomy(
                model=model,
                media_bytes=media_bytes,
                mime_type=mime_type,
                context_payload=context_payload,
            )

            asset.channel = parsed.channel
            asset.destination_type = parsed.destination_type
            asset.funnel_stage = parsed.funnel_stage
            asset.angle_family = parsed.angle_family
            asset.hook_type = parsed.hook_type
            asset.visual_archetype = parsed.visual_archetype
            asset.product_presence = parsed.product_presence
            asset.proof_type = parsed.proof_type
            asset.claim_risk = parsed.claim_risk
            asset.product_image_policy = parsed.product_image_policy
            asset.analysis_status = "ready"
            asset.analysis_error = None
            asset.analysis_model = _normalize_model_name(model)
            asset.analysis_updated_at = datetime.now(timezone.utc)
            session.commit()
            return {
                "swipe_asset_id": swipe_asset_id,
                "analysis_status": "ready",
                "taxonomy": parsed.model_dump(mode="json"),
            }
    except Exception as exc:  # noqa: BLE001
        _set_analysis_status(
            org_id=org_id,
            swipe_asset_id=swipe_asset_id,
            status_value="failed",
            error=str(exc),
        )
        raise
