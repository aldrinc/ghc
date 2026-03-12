from __future__ import annotations

import hashlib
import os
import re
import time
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import unquote, urlparse

import httpx
try:
    from google import genai
    from google.genai import types as genai_types
    _GENAI_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - environment-specific dependency issue
    genai = None
    genai_types = None
    _GENAI_IMPORT_ERROR = exc
from sqlalchemy import select
from temporalio import activity
from pydantic import ValidationError

from app.config import settings
from app.db.base import session_scope
from app.db.enums import ArtifactTypeEnum
from app.db.models import DesignSystem, Funnel, FunnelPage, ProductOffer, ProductVariant
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.clients import ClientsRepository
from app.db.repositories.products import ProductsRepository
from app.db.repositories.swipes import CompanySwipesRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.observability import LangfuseTraceContext, bind_langfuse_trace_context, start_langfuse_generation
from app.schemas.creative_generation import SwipeAdCopyPack
from app.schemas.creative_service import CreativeServiceImageAdsCreateIn
from app.services.creative_service_client import (
    CreativeServiceConfigError,
    CreativeServiceRequestError,
)
from app.services.image_render_client import (
    build_image_render_client,
    get_image_render_provider,
)
from app.services.gemini_file_search import (
    ensure_uploaded_to_gemini_file_search,
    is_gemini_file_search_enabled,
)
from app.services.swipe_prompt import (
    SwipePromptParseError,
    extract_new_image_prompt_from_markdown,
    inline_swipe_render_placeholders,
    load_swipe_to_image_ad_prompt,
)

# Reuse existing asset generation helpers to keep asset storage consistent.
from app.temporal.activities.asset_activities import (  # noqa: E402
    _create_generated_asset_from_url,
    _extract_brief,
    _retention_expires_at,
    _select_product_reference_assets,
    _stable_idempotency_key,
    _validate_brief_scope,
)


_GEMINI_CLIENT: Any | None = None
_SWIPE_PRODUCT_IMAGE_PROFILE_CACHE: Dict[str, bool] | None = None
_SWIPE_COPY_GEMINI_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_SWIPE_COPY_GEMINI_MAX_ATTEMPTS = max(1, int(os.getenv("SWIPE_COPY_GEMINI_MAX_ATTEMPTS", "5")))


def _resolve_swipe_gemini_timeout_seconds() -> int:
    return max(1, int(settings.SWIPE_GEMINI_TIMEOUT_SECONDS or 300))


def _build_swipe_gemini_http_timeout() -> httpx.Timeout:
    timeout_seconds = float(_resolve_swipe_gemini_timeout_seconds())
    connect_timeout_seconds = min(timeout_seconds, 30.0)
    return httpx.Timeout(
        timeout_seconds,
        connect=connect_timeout_seconds,
        read=timeout_seconds,
        write=timeout_seconds,
        pool=timeout_seconds,
    )


def _build_swipe_gemini_http_options() -> Any:
    timeout_seconds = _resolve_swipe_gemini_timeout_seconds()
    httpx_timeout = _build_swipe_gemini_http_timeout()
    return genai_types.HttpOptions(
        timeout=timeout_seconds * 1000,
        clientArgs={"timeout": httpx_timeout},
        asyncClientArgs={"timeout": httpx_timeout},
    )


def _load_swipe_product_image_profiles() -> Dict[str, bool]:
    global _SWIPE_PRODUCT_IMAGE_PROFILE_CACHE
    if _SWIPE_PRODUCT_IMAGE_PROFILE_CACHE is not None:
        return _SWIPE_PRODUCT_IMAGE_PROFILE_CACHE

    configured_path = (os.getenv("SWIPE_PRODUCT_IMAGE_PROFILES_PATH") or "").strip()
    if configured_path:
        profile_path = Path(configured_path).expanduser().resolve()
    else:
        profile_path = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "swipe_profiles"
            / "initial_swipe_product_image_profiles_v1.json"
        )

    if not profile_path.exists() or not profile_path.is_file():
        raise RuntimeError(f"Swipe product image profiles file not found: {profile_path}")

    try:
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to parse swipe product image profiles at {profile_path}: {exc}") from exc

    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise RuntimeError(
            "Swipe product image profiles must define an `entries` array "
            f"(path={profile_path})."
        )

    profiles: Dict[str, bool] = {}
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise RuntimeError(
                "Swipe product image profile entry must be an object "
                f"(path={profile_path}, index={idx})."
            )
        filename_raw = entry.get("filename")
        requires_raw = entry.get("requires_product_image")
        if not isinstance(filename_raw, str) or not filename_raw.strip():
            raise RuntimeError(
                "Swipe product image profile entry is missing filename "
                f"(path={profile_path}, index={idx})."
            )
        if not isinstance(requires_raw, bool):
            raise RuntimeError(
                "Swipe product image profile entry requires boolean requires_product_image "
                f"(path={profile_path}, index={idx}, filename={filename_raw!r})."
            )
        key = filename_raw.strip().lower()
        if key in profiles:
            raise RuntimeError(
                "Duplicate filename in swipe product image profiles "
                f"(path={profile_path}, filename={filename_raw!r})."
            )
        profiles[key] = requires_raw

    _SWIPE_PRODUCT_IMAGE_PROFILE_CACHE = profiles
    return profiles


def _resolve_swipe_copy_gemini_retry_delay_seconds(*, attempt: int, retry_after_raw: str | None = None) -> float:
    if isinstance(retry_after_raw, str) and retry_after_raw.strip():
        try:
            parsed_retry_after = float(retry_after_raw.strip())
            if parsed_retry_after > 0:
                return max(1.0, parsed_retry_after)
        except ValueError:
            pass
    return min(30.0, max(1.0, float(2**attempt)))


def _extract_swipe_copy_gemini_status_code(exc: Exception) -> int | None:
    direct_status = getattr(exc, "status_code", None)
    if isinstance(direct_status, int):
        return direct_status
    direct_code = getattr(exc, "code", None)
    if isinstance(direct_code, int):
        return direct_code
    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    if isinstance(response_status, int):
        return response_status
    message = str(exc)
    match = re.search(r"\b(4\d{2}|5\d{2})\b", message)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def _extract_swipe_copy_gemini_retry_after(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    getter = getattr(headers, "get", None)
    if callable(getter):
        value = getter("Retry-After")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _is_retryable_swipe_copy_gemini_error(exc: Exception, *, error_text: str) -> bool:
    status_code = _extract_swipe_copy_gemini_status_code(exc)
    if status_code in _SWIPE_COPY_GEMINI_RETRYABLE_STATUS_CODES:
        return True
    normalized = error_text.lower()
    retryable_markers = (
        "resource_exhausted",
        "too many requests",
        "temporarily unavailable",
        "failed to embed content",
        "internal error",
        "service unavailable",
        "deadline exceeded",
        "timed out",
        "timeout",
    )
    return any(marker in normalized for marker in retryable_markers)


def _call_gemini_generate_content_with_retries(
    *,
    gemini_client: Any,
    model: str,
    contents: List[Any],
    config: Any,
    operation_name: str,
    file_search_model_error_message: str,
) -> Any:
    for attempt in range(1, _SWIPE_COPY_GEMINI_MAX_ATTEMPTS + 1):
        try:
            return gemini_client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as exc:  # noqa: BLE001
            error_text = str(exc)
            if "File search tool is not enabled for this model" in error_text:
                raise RuntimeError(file_search_model_error_message) from exc
            if attempt < _SWIPE_COPY_GEMINI_MAX_ATTEMPTS and _is_retryable_swipe_copy_gemini_error(
                exc,
                error_text=error_text,
            ):
                time.sleep(
                    _resolve_swipe_copy_gemini_retry_delay_seconds(
                        attempt=attempt,
                        retry_after_raw=_extract_swipe_copy_gemini_retry_after(exc),
                    )
                )
                continue
            raise RuntimeError(f"{operation_name} failed with Gemini: {error_text}") from exc
    raise RuntimeError(f"{operation_name} did not return a response.")


def _extract_source_filename(source_url: str | None) -> str | None:
    if not isinstance(source_url, str) or not source_url.strip():
        return None
    raw = source_url.strip()
    parsed = urlparse(raw)
    path = parsed.path or raw
    name = Path(unquote(path)).name.strip()
    if not name:
        return None
    return name


def _optional_clean_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _summarize_swipe_copy_validation_error(exc: ValidationError) -> str:
    missing_fields: list[str] = []
    other_messages: list[str] = []
    meta_required_prefix = "Meta swipe copy pack is missing required fields:"

    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc") or [])
        message = str(error.get("msg") or "").strip()
        if location in {"metaPrimaryText", "metaHeadline", "metaDescription", "metaCta"}:
            missing_fields.append(location)
            continue
        if meta_required_prefix in message:
            suffix = message.split(meta_required_prefix, 1)[1].strip()
            missing_fields.extend(part.strip() for part in suffix.split(",") if part.strip())
            continue
        if message:
            other_messages.append(message)

    if missing_fields:
        ordered = ", ".join(dict.fromkeys(missing_fields))
        return (
            "The JSON object is missing required Meta fields: "
            f"{ordered}. Return the complete JSON shape and populate every Meta field."
        )
    if other_messages:
        return other_messages[0]
    return "The JSON object did not satisfy the SwipeAdCopyPack schema. Return the complete required shape."


def _resolve_swipe_requires_product_image_policy(
    *,
    explicit_requires_product_image: bool | None,
    swipe_source_url: str | None,
) -> tuple[bool | None, str, str | None]:
    if explicit_requires_product_image is not None:
        return explicit_requires_product_image, "explicit_param", _extract_source_filename(swipe_source_url)

    source_filename = _extract_source_filename(swipe_source_url)
    if source_filename:
        profile_lookup = _load_swipe_product_image_profiles()
        matched = profile_lookup.get(source_filename.lower())
        if matched is not None:
            return matched, "catalog_filename", source_filename

    return None, "default_optional", source_filename


def _ensure_gemini_client():
    global _GEMINI_CLIENT
    if _GEMINI_CLIENT is not None:
        return _GEMINI_CLIENT
    if genai is None:
        detail = str(_GENAI_IMPORT_ERROR) if _GENAI_IMPORT_ERROR else "unknown import error"
        raise RuntimeError(
            "google-genai dependency is unavailable for swipe image activity. "
            f"Fix dependency compatibility and retry. Original error: {detail}"
        )
    if genai_types is None:
        detail = str(_GENAI_IMPORT_ERROR) if _GENAI_IMPORT_ERROR else "unknown import error"
        raise RuntimeError(f"google.genai.types is unavailable: {detail}")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")
    _GEMINI_CLIENT = genai.Client(
        api_key=api_key,
        http_options=_build_swipe_gemini_http_options(),
    )
    return _GEMINI_CLIENT


def _normalize_gemini_model_name(model: str) -> str:
    normalized = (model or "").strip()
    if not normalized:
        raise ValueError("model is required (provide params.model or set SWIPE_PROMPT_MODEL).")
    if normalized.startswith("models/"):
        return normalized.split("/", 1)[1]
    return normalized


def _is_image_render_model_name(model: str) -> bool:
    normalized = _normalize_gemini_model_name(model).lower()
    return (
        "image-preview" in normalized
        or "image-generation" in normalized
        or normalized.endswith("-image")
    )


def _normalize_render_model_id(model: str) -> str:
    normalized = (model or "").strip()
    if not normalized:
        raise ValueError("render_model_id must be a non-empty string when provided.")
    if normalized.startswith("models/"):
        return normalized
    if normalized.startswith("gemini-"):
        return f"models/{normalized}"
    return normalized


def _download_bytes(url: str, *, max_bytes: int, timeout_seconds: float) -> Tuple[bytes, str]:
    with httpx.Client(follow_redirects=True, timeout=timeout_seconds) as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
            if not content_type:
                raise RuntimeError(f"Swipe image response missing content-type header (url={url})")
            chunks: List[bytes] = []
            total = 0
            for chunk in resp.iter_bytes(8192):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise RuntimeError(f"swipe_image_too_large: {total} bytes (limit {max_bytes})")
                chunks.append(chunk)
            data = b"".join(chunks)
            if not data:
                raise RuntimeError(f"Swipe image download returned empty bytes (url={url})")
            return data, content_type


def _resolve_swipe_image(
    *,
    session,
    org_id: str,
    company_swipe_id: str | None,
    swipe_image_url: str | None,
) -> Tuple[bytes, str, str]:
    """
    Return (bytes, mime_type, source_url) for the competitor swipe image.
    """
    if bool(company_swipe_id) == bool(swipe_image_url):
        raise ValueError("Exactly one of company_swipe_id or swipe_image_url must be provided.")

    if swipe_image_url:
        data, mime_type = _download_bytes(
            swipe_image_url,
            max_bytes=int(os.getenv("SWIPE_IMAGE_MAX_BYTES", str(18 * 1024 * 1024))),
            timeout_seconds=float(os.getenv("SWIPE_IMAGE_DOWNLOAD_TIMEOUT", "30")),
        )
        return data, mime_type, swipe_image_url

    repo = CompanySwipesRepository(session)
    swipe = repo.get_asset(org_id=org_id, swipe_id=company_swipe_id or "")
    if not swipe:
        raise ValueError(f"Company swipe not found: {company_swipe_id}")
    media = repo.list_media(org_id=org_id, swipe_asset_id=str(swipe.id))
    if not media:
        raise ValueError(f"Company swipe has no media: {company_swipe_id}")

    # Prefer image media.
    selected = None
    for item in media:
        mt = (getattr(item, "mime_type", None) or "").lower()
        if mt.startswith("image/"):
            selected = item
            break
    if not selected:
        selected = media[0]

    url = (
        getattr(selected, "download_url", None)
        or getattr(selected, "url", None)
        or getattr(selected, "thumbnail_url", None)
    )
    if not url:
        raise ValueError(f"Swipe media is missing a usable url (company_swipe_id={company_swipe_id})")

    data, mime_type = _download_bytes(
        url,
        max_bytes=int(os.getenv("SWIPE_IMAGE_MAX_BYTES", str(18 * 1024 * 1024))),
        timeout_seconds=float(os.getenv("SWIPE_IMAGE_DOWNLOAD_TIMEOUT", "30")),
    )
    return data, mime_type, str(url)


def _extract_brand_context(
    *,
    session,
    org_id: str,
    client_id: str,
    product_id: str,
) -> Dict[str, Any]:
    clients_repo = ClientsRepository(session)
    client = clients_repo.get(org_id=org_id, client_id=client_id)
    if not client:
        raise ValueError(f"Client not found: {client_id}")

    product = ProductsRepository(session).get(org_id=org_id, product_id=product_id)
    if not product:
        raise ValueError(f"Product not found: {product_id}")
    if str(getattr(product, "client_id", "")) != str(client_id):
        raise ValueError("Product does not belong to the provided client_id.")

    artifacts_repo = ArtifactsRepository(session)
    canon_artifact = artifacts_repo.get_latest_by_type(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        artifact_type=ArtifactTypeEnum.client_canon,
    )
    if not canon_artifact or not isinstance(canon_artifact.data, dict):
        raise ValueError("Client canon (creative brief) is required but was not found for this client/product.")
    canon = canon_artifact.data

    design_system_tokens: Dict[str, Any] = {}
    design_system_id = getattr(client, "design_system_id", None)
    if design_system_id:
        ds = session.get(DesignSystem, design_system_id)
        if ds and isinstance(ds.tokens, dict):
            design_system_tokens = ds.tokens

    return {
        "client_name": getattr(client, "name", None),
        "product_title": getattr(product, "title", None),
        "canon": canon,
        "design_system_tokens": design_system_tokens,
    }


def _format_audience_from_canon(canon: Dict[str, Any]) -> str | None:
    icps = canon.get("icps")
    if not isinstance(icps, list) or not icps:
        return None
    first = icps[0] if isinstance(icps[0], dict) else None
    if not first:
        return None
    name = first.get("name") if isinstance(first.get("name"), str) else None
    pains = first.get("pains") if isinstance(first.get("pains"), list) else []
    gains = first.get("gains") if isinstance(first.get("gains"), list) else []
    jobs = first.get("jobsToBeDone") if isinstance(first.get("jobsToBeDone"), list) else []
    parts: List[str] = []
    if name and name.strip():
        parts.append(f"ICP: {name.strip()}")
    if pains:
        pains_str = "; ".join(str(p).strip() for p in pains if isinstance(p, str) and p.strip())
        if pains_str:
            parts.append(f"Pains: {pains_str}")
    if gains:
        gains_str = "; ".join(str(g).strip() for g in gains if isinstance(g, str) and g.strip())
        if gains_str:
            parts.append(f"Gains: {gains_str}")
    if jobs:
        jobs_str = "; ".join(str(j).strip() for j in jobs if isinstance(j, str) and j.strip())
        if jobs_str:
            parts.append(f"Jobs: {jobs_str}")
    return " | ".join(parts) if parts else None


def _brand_colors_fonts_from_design_tokens(tokens: Dict[str, Any]) -> str | None:
    if not isinstance(tokens, dict) or not tokens:
        return None
    css_vars = tokens.get("cssVars")
    if not isinstance(css_vars, dict):
        css_vars = {}

    font_heading = css_vars.get("--font-heading")
    font_body = css_vars.get("--font-sans") or css_vars.get("--font-body")
    color_brand = css_vars.get("--color-brand")
    color_page_bg = css_vars.get("--color-page-bg")
    color_bg = css_vars.get("--color-bg")

    parts: List[str] = []
    if isinstance(font_heading, str) and font_heading.strip():
        parts.append(f"Heading font: {font_heading.strip()}")
    if isinstance(font_body, str) and font_body.strip():
        parts.append(f"Body font: {font_body.strip()}")
    if isinstance(color_brand, str) and color_brand.strip():
        parts.append(f"Brand color: {color_brand.strip()}")
    if isinstance(color_page_bg, str) and color_page_bg.strip():
        parts.append(f"Page bg: {color_page_bg.strip()}")
    if isinstance(color_bg, str) and color_bg.strip():
        parts.append(f"Surface bg: {color_bg.strip()}")

    return " | ".join(parts) if parts else None


def _must_avoid_claims_from_canon(canon: Dict[str, Any]) -> List[str]:
    constraints = canon.get("constraints")
    if not isinstance(constraints, dict):
        return []
    out: List[str] = []
    for key in ("legal", "compliance", "bannedTopics", "bannedPhrases"):
        items = constraints.get(key)
        if isinstance(items, list):
            out.extend([str(x).strip() for x in items if isinstance(x, str) and x.strip()])
    return out


def _normalize_prompt_value(value: str | None) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "[UNKNOWN]"


def _has_logo_available(*, design_system_tokens: Dict[str, Any]) -> bool:
    if not isinstance(design_system_tokens, dict):
        return False
    brand = design_system_tokens.get("brand")
    if not isinstance(brand, dict):
        return False
    logo_public_id = brand.get("logoAssetPublicId")
    return isinstance(logo_public_id, str) and bool(logo_public_id.strip())


def _prompt_assets_value(*, product_reference_assets: List[Any], design_system_tokens: Dict[str, Any]) -> str:
    packshot_titles: List[str] = []
    for reference in product_reference_assets:
        title = getattr(reference, "title", None)
        if isinstance(title, str) and title.strip():
            packshot_titles.append(title.strip())

    has_logo = _has_logo_available(design_system_tokens=design_system_tokens)

    if not packshot_titles and not has_logo:
        return "[UNKNOWN]"

    packshot_part = ", ".join(packshot_titles) if packshot_titles else "[UNKNOWN]"
    logo_part = "available" if has_logo else "[UNKNOWN]"
    return f"PACKSHOT: {packshot_part}; LOGO: {logo_part}"


def _render_swipe_prompt_template(
    *,
    prompt_template: str,
    brand_name: str,
    product_name: str,
    audience: str | None,
    angle_from_docs: str | None,
    brand_colors_fonts: str | None,
    must_avoid_claims: List[str],
    assets_value: str,
    packshot_available: bool,
    logo_available: bool,
) -> str:
    if not isinstance(prompt_template, str) or not prompt_template.strip():
        raise ValueError("prompt_template is required and must be non-empty.")

    cleaned_brand_name = _normalize_prompt_value(brand_name)
    cleaned_product_name = _normalize_prompt_value(product_name)
    cleaned_audience = _normalize_prompt_value(audience)
    cleaned_angle_from_docs = _normalize_prompt_value(angle_from_docs)
    cleaned_brand_colors_fonts = _normalize_prompt_value(brand_colors_fonts)
    claims_value = (
        "; ".join(item.strip() for item in must_avoid_claims if isinstance(item, str) and item.strip())
        if must_avoid_claims
        else "[UNKNOWN]"
    )
    cleaned_assets = _normalize_prompt_value(assets_value)
    cleaned_packshot_available = "yes" if packshot_available else "no"
    cleaned_logo_available = "yes" if logo_available else "no"

    rendered = prompt_template
    rendered = re.sub(
        r"Brand name:\s*\[BRAND_NAME\]",
        lambda _m: f"Brand name: {cleaned_brand_name}",
        rendered,
    )
    rendered = re.sub(
        r"Product:\s*\[PRODUCT\]",
        lambda _m: f"Product: {cleaned_product_name}",
        rendered,
    )
    rendered = re.sub(
        r"Audience:\s*\[AUDIENCE\]\s*\(optional\)",
        lambda _m: f"Audience: {cleaned_audience} (optional)",
        rendered,
    )
    rendered = re.sub(
        r"Brand colors/fonts:\s*\[UNKNOWN if not given\]",
        lambda _m: f"Brand colors/fonts: {cleaned_brand_colors_fonts}",
        rendered,
    )
    rendered = re.sub(
        r"Must-avoid claims:\s*\[UNKNOWN if not given\]",
        lambda _m: f"Must-avoid claims: {claims_value}",
        rendered,
    )
    rendered = re.sub(
        r"Assets:\s*\[PACKSHOT\?\s*LOGO\?\]\s*\(optional\)",
        lambda _m: f"Assets: {cleaned_assets} (optional)",
        rendered,
    )
    rendered = re.sub(
        r"Packshot available:\s*\[PACKSHOT_AVAILABLE\]",
        lambda _m: f"Packshot available: {cleaned_packshot_available}",
        rendered,
    )
    rendered = re.sub(
        r"Logo available:\s*\[LOGO_AVAILABLE\]",
        lambda _m: f"Logo available: {cleaned_logo_available}",
        rendered,
    )

    rendered = rendered.replace(
        "[User uploads image]",
        "Competitor swipe image is attached below as image input.",
    )
    rendered = rendered.replace("[BRAND_NAME]", cleaned_brand_name)
    rendered = rendered.replace("[PRODUCT]", cleaned_product_name)
    rendered = rendered.replace("[AUDIENCE]", cleaned_audience)

    rendered = re.sub(
        r"\n*---\s*\n*\s*But with the items shown in brackets populated with our product/brand specific info\.\s*$",
        "",
        rendered,
        flags=re.IGNORECASE,
    )

    unresolved = [
        token
        for token in (
            "[BRAND_NAME]",
            "[PRODUCT]",
            "[AUDIENCE]",
            "[UNKNOWN if not given]",
            "[PACKSHOT? LOGO?]",
            "[PACKSHOT_AVAILABLE]",
            "[LOGO_AVAILABLE]",
            "[User uploads image]",
        )
        if token in rendered
    ]
    if unresolved:
        raise ValueError(
            "Swipe prompt template has unresolved runtime placeholders after rendering: "
            f"{', '.join(unresolved)}"
        )

    angle_line = f"Angle: {cleaned_angle_from_docs}"
    vocc_instruction = (
        "Use emotional, raw, visceral VOCC from research documents around the primary precision, "
        "safety, dosage angle and secondary angles. Should be a punch in the gut style."
    )
    rendered = rendered.rstrip()
    if re.search(r"(?im)^Angle:\s*", rendered):
        rendered = re.sub(r"(?im)^Angle:\s*.*$", angle_line, rendered, count=1)
    else:
        rendered = f"{rendered}\n\n{angle_line}"
    if vocc_instruction.lower() not in rendered.lower():
        rendered = f"{rendered}\n\n{vocc_instruction}"

    rendered = (
        f"{rendered}\n\n"
        "Hard constraints for NEW IMAGE PROMPT:\n"
        "- Do NOT output unresolved bracket placeholders such as [BRAND_LOGO], [PRODUCT_PACKSHOT], [HEADLINE], "
        "[SUBHEAD], [BODY], [EQUATION_LINE], [CTA], [DISCLAIMER], [UNKNOWN], [UNREADABLE].\n"
        f"- Packshot available: {cleaned_packshot_available}. If no, omit product-packshot references entirely.\n"
        f"- Logo available: {cleaned_logo_available}. If no, omit logo references entirely."
    )

    return rendered.strip()


def _format_price(amount_cents: int, currency: str) -> str:
    cleaned_currency = (currency or "").strip().upper()
    if cleaned_currency == "USD":
        if amount_cents % 100 == 0:
            return f"${amount_cents // 100}"
        return f"${amount_cents / 100:.2f}"
    # Default: show currency code explicitly to avoid guessing locale formatting.
    return f"{amount_cents / 100:.2f} {cleaned_currency or '[UNKNOWN]'}"


def _build_product_offer_context_block(
    *,
    session,
    org_id: str,
    client_id: str,
    product_id: str,
    funnel_id: str | None,
) -> tuple[str, str, dict[str, Any]]:
    """
    Build a deterministic block of offer/pricing context for Gemini so it can populate
    price lines without inventing.
    """

    funnel: Funnel | None = None
    selected_offer_id: str | None = None
    if funnel_id:
        funnel = session.get(Funnel, funnel_id)
        if not funnel:
            raise ValueError(f"Funnel not found: {funnel_id}")
        selected_offer_id = str(funnel.selected_offer_id) if funnel.selected_offer_id else None

    offers = list(
        session.scalars(
            select(ProductOffer)
            .where(
                ProductOffer.org_id == org_id,
                ProductOffer.client_id == client_id,
                ProductOffer.product_id == product_id,
            )
            .order_by(ProductOffer.created_at.desc())
        ).all()
    )

    selected_offer: ProductOffer | None = None
    if selected_offer_id:
        selected_offer = next((item for item in offers if str(item.id) == selected_offer_id), None)
        if not selected_offer:
            raise ValueError(
                "Selected offer does not exist for this product. "
                f"funnel_id={funnel_id} selected_offer_id={selected_offer_id} product_id={product_id}"
            )
    else:
        if not offers:
            raise ValueError(
                "No product offers found; cannot inject offer/pricing context. "
                "Create at least one product offer with price points (e.g., via Shopify sync). "
                f"product_id={product_id}"
            )
        if len(offers) > 1:
            raise ValueError(
                "Multiple product offers found but funnel.selected_offer_id is not set; cannot choose pricing context. "
                f"funnel_id={funnel_id} product_id={product_id} offer_ids={[str(o.id) for o in offers]}"
            )
        selected_offer = offers[0]

    price_points = list(
        session.scalars(
            select(ProductVariant).where(ProductVariant.offer_id == selected_offer.id).order_by(ProductVariant.price.asc())
        ).all()
    )
    if not price_points:
        raise ValueError(
            "Selected offer has no price points; cannot inject offer/pricing context. "
            f"offer_id={selected_offer.id} product_id={product_id}"
        )

    lines: list[str] = []
    lines.append("## PRODUCT / OFFER CONTEXT")
    lines.append(f"Offer name: {selected_offer.name}")
    lines.append("Price points (use exact values; do not invent pricing):")
    for point in price_points:
        price = _format_price(int(point.price), str(point.currency))
        compare_at = (
            _format_price(int(point.compare_at_price), str(point.currency))
            if point.compare_at_price is not None
            else None
        )
        suffix = f" (compare at {compare_at})" if compare_at else ""
        lines.append(f"- {point.title}: {price}{suffix}")
    lines.append(
        "If you include a price in the ad, choose ONE of the price points above (prefer the lowest unless the brief says otherwise)."
    )
    text = "\n".join(lines).strip()

    signature = _stable_idempotency_key(
        "swipe_offer_context_v1",
        str(selected_offer.id),
        *[
            f"{point.title}|{int(point.price)}|{str(point.currency)}|{int(point.compare_at_price) if point.compare_at_price is not None else ''}"
            for point in price_points
        ],
    )

    metadata: dict[str, Any] = {
        "offerId": str(selected_offer.id),
        "offerName": selected_offer.name,
        "pricePoints": [
            {
                "title": point.title,
                "amountCents": int(point.price),
                "currency": str(point.currency),
                "compareAtPriceCents": int(point.compare_at_price) if point.compare_at_price is not None else None,
            }
            for point in price_points
        ],
        "signature": signature,
    }
    return text, signature, metadata


def _json_payload_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str).encode("utf-8")


def _extract_store_name_from_document_name(document_name: str) -> str:
    cleaned = (document_name or "").strip()
    match = re.match(r"^(fileSearchStores/[^/]+)/documents/[^/]+$", cleaned)
    if not match:
        raise RuntimeError(
            "Unexpected Gemini document name format while resolving swipe stage-1 context: "
            f"{cleaned!r}"
        )
    return match.group(1)


def _load_required_product_offer_pricing_snapshot(
    *,
    session,
    org_id: str,
    client_id: str,
    product_id: str,
    funnel_id: str | None,
) -> Dict[str, Any]:
    selected_offer: ProductOffer | None = None
    if funnel_id:
        funnel = session.get(Funnel, funnel_id)
        if funnel is None:
            raise ValueError(f"Funnel not found: {funnel_id}")
        if funnel.selected_offer_id:
            selected_offer = session.get(ProductOffer, funnel.selected_offer_id)
            if selected_offer is None:
                raise ValueError(
                    "Funnel selected_offer_id is set but the offer could not be found "
                    f"(funnel_id={funnel_id}, selected_offer_id={funnel.selected_offer_id})."
                )

    if selected_offer is None:
        offers = list(
            session.scalars(
                select(ProductOffer)
                .where(
                    ProductOffer.org_id == org_id,
                    ProductOffer.client_id == client_id,
                    ProductOffer.product_id == product_id,
                )
                .order_by(ProductOffer.created_at.desc())
            ).all()
        )
        if not offers:
            raise ValueError(
                "No product offers found for swipe stage-1 RAG context. "
                f"product_id={product_id}."
            )
        if len(offers) > 1:
            raise ValueError(
                "Multiple product offers found and no funnel.selected_offer_id is set; "
                "cannot deterministically choose offer_pricing snapshot for swipe stage-1 RAG context. "
                f"product_id={product_id}, funnel_id={funnel_id}, offer_ids={[str(item.id) for item in offers]}."
            )
        selected_offer = offers[0]

    variants = list(
        session.scalars(
            select(ProductVariant)
            .where(ProductVariant.offer_id == selected_offer.id)
            .order_by(ProductVariant.price.asc(), ProductVariant.id.asc())
        ).all()
    )
    if not variants:
        raise ValueError(
            "Selected product offer has no pricing variants; cannot build offer_pricing snapshot for swipe stage-1 "
            f"RAG context (offer_id={selected_offer.id})."
        )

    return {
        "offer": {
            "id": str(selected_offer.id),
            "org_id": str(selected_offer.org_id),
            "client_id": str(selected_offer.client_id),
            "product_id": str(selected_offer.product_id) if selected_offer.product_id else None,
            "name": selected_offer.name,
            "description": selected_offer.description,
            "business_model": selected_offer.business_model,
            "differentiation_bullets": list(selected_offer.differentiation_bullets or []),
            "guarantee_text": selected_offer.guarantee_text,
            "options_schema": selected_offer.options_schema,
            "created_at": selected_offer.created_at.isoformat() if selected_offer.created_at else None,
        },
        "variants": [
            {
                "id": str(variant.id),
                "offer_id": str(variant.offer_id) if variant.offer_id else None,
                "product_id": str(variant.product_id) if variant.product_id else None,
                "title": variant.title,
                "price": int(variant.price),
                "currency": str(variant.currency),
                "provider": variant.provider,
                "external_price_id": variant.external_price_id,
                "option_values": variant.option_values,
                "compare_at_price": int(variant.compare_at_price) if variant.compare_at_price is not None else None,
                "sku": variant.sku,
                "barcode": variant.barcode,
                "requires_shipping": bool(variant.requires_shipping),
                "taxable": bool(variant.taxable),
                "weight": float(variant.weight) if variant.weight is not None else None,
                "weight_unit": variant.weight_unit,
                "inventory_quantity": variant.inventory_quantity,
                "inventory_policy": variant.inventory_policy,
                "inventory_management": variant.inventory_management,
                "incoming": variant.incoming,
                "next_incoming_date": variant.next_incoming_date.isoformat() if variant.next_incoming_date else None,
                "unit_price": int(variant.unit_price) if variant.unit_price is not None else None,
                "unit_price_measurement": variant.unit_price_measurement,
                "quantity_rule": variant.quantity_rule,
                "quantity_price_breaks": variant.quantity_price_breaks,
                "shopify_last_synced_at": (
                    variant.shopify_last_synced_at.isoformat() if variant.shopify_last_synced_at else None
                ),
                "shopify_last_sync_error": variant.shopify_last_sync_error,
            }
            for variant in variants
        ],
    }


def _load_required_swipe_stage1_rag_docs(
    *,
    session,
    org_id: str,
    client_id: str,
    product_id: str,
    campaign_id: str | None,
    funnel_id: str | None,
    asset_brief_artifact_id: str,
) -> list[Dict[str, Any]]:
    artifacts_repo = ArtifactsRepository(session)

    def _require_latest_product_artifact(*, artifact_type: ArtifactTypeEnum, doc_key: str, title: str) -> Dict[str, Any]:
        artifact = artifacts_repo.get_latest_by_type(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            artifact_type=artifact_type,
        )
        if artifact is None:
            raise ValueError(
                "Required swipe stage-1 RAG artifact is missing. "
                f"artifact_type={artifact_type.value} client_id={client_id} product_id={product_id}."
            )
        payload = {
            "artifact": {
                "id": str(artifact.id),
                "type": artifact.type.value,
                "version": int(artifact.version),
                "org_id": str(artifact.org_id),
                "client_id": str(artifact.client_id),
                "product_id": str(artifact.product_id) if artifact.product_id else None,
                "campaign_id": str(artifact.campaign_id) if artifact.campaign_id else None,
                "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
            },
            "data": artifact.data,
        }
        return {
            "doc_key": doc_key,
            "doc_title": title,
            "source_kind": artifact_type.value,
            "filename": f"{doc_key}.json",
            "mime_type": "text/plain",
            "content_bytes": _json_payload_bytes(payload),
        }

    def _require_latest_campaign_artifact(*, artifact_type: ArtifactTypeEnum, doc_key: str, title: str) -> Dict[str, Any]:
        if not campaign_id:
            raise ValueError(
                f"campaign_id is required to resolve campaign artifact {artifact_type.value} for swipe stage-1 RAG."
            )
        artifact = artifacts_repo.get_latest_by_type_for_campaign(
            org_id=org_id,
            campaign_id=campaign_id,
            artifact_type=artifact_type,
        )
        if artifact is None:
            raise ValueError(
                "Required swipe stage-1 campaign RAG artifact is missing. "
                f"artifact_type={artifact_type.value} campaign_id={campaign_id}."
            )
        payload = {
            "artifact": {
                "id": str(artifact.id),
                "type": artifact.type.value,
                "version": int(artifact.version),
                "org_id": str(artifact.org_id),
                "client_id": str(artifact.client_id),
                "product_id": str(artifact.product_id) if artifact.product_id else None,
                "campaign_id": str(artifact.campaign_id) if artifact.campaign_id else None,
                "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
            },
            "data": artifact.data,
        }
        return {
            "doc_key": doc_key,
            "doc_title": title,
            "source_kind": artifact_type.value,
            "filename": f"{doc_key}.json",
            "mime_type": "text/plain",
            "content_bytes": _json_payload_bytes(payload),
        }

    client = ClientsRepository(session).get(org_id=org_id, client_id=client_id)
    if client is None:
        raise ValueError(f"Client not found for swipe stage-1 RAG: {client_id}")
    design_system_id = getattr(client, "design_system_id", None)
    if not design_system_id:
        raise ValueError(f"Client has no design_system_id for swipe stage-1 RAG: {client_id}")
    design_system = session.get(DesignSystem, design_system_id)
    if design_system is None:
        raise ValueError(
            "Client references a design system that was not found for swipe stage-1 RAG. "
            f"client_id={client_id}, design_system_id={design_system_id}."
        )
    if not isinstance(design_system.tokens, dict):
        raise ValueError(
            "Design system tokens must be a JSON object for swipe stage-1 RAG "
            f"(design_system_id={design_system_id})."
        )
    design_system_payload = {
        "design_system": {
            "id": str(design_system.id),
            "org_id": str(design_system.org_id),
            "client_id": str(design_system.client_id) if design_system.client_id else None,
            "name": design_system.name,
            "created_at": design_system.created_at.isoformat() if design_system.created_at else None,
            "updated_at": design_system.updated_at.isoformat() if design_system.updated_at else None,
        },
        "tokens": design_system.tokens,
    }

    product = ProductsRepository(session).get(org_id=org_id, product_id=product_id)
    if product is None:
        raise ValueError(f"Product not found for swipe stage-1 RAG: {product_id}")
    product_profile_payload = {
        "product": {
            "id": str(product.id),
            "org_id": str(product.org_id),
            "client_id": str(product.client_id),
            "title": product.title,
            "description": product.description,
            "product_type": product.product_type,
            "handle": product.handle,
            "vendor": product.vendor,
            "tags": list(product.tags or []),
            "template_suffix": product.template_suffix,
            "published_at": product.published_at.isoformat() if product.published_at else None,
            "shopify_product_gid": product.shopify_product_gid,
            "primary_benefits": list(product.primary_benefits or []),
            "feature_bullets": list(product.feature_bullets or []),
            "guarantee_text": product.guarantee_text,
            "disclaimers": list(product.disclaimers or []),
            "primary_asset_id": str(product.primary_asset_id) if product.primary_asset_id else None,
            "created_at": product.created_at.isoformat() if product.created_at else None,
        }
    }

    offer_pricing_payload = _load_required_product_offer_pricing_snapshot(
        session=session,
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        funnel_id=funnel_id,
    )

    asset_brief_artifact = artifacts_repo.get(org_id=org_id, artifact_id=asset_brief_artifact_id)
    if asset_brief_artifact is None:
        raise ValueError(
            "Asset brief artifact not found for swipe stage-1 RAG "
            f"(asset_brief_artifact_id={asset_brief_artifact_id})."
        )
    if asset_brief_artifact.type != ArtifactTypeEnum.asset_brief:
        raise ValueError(
            "Resolved asset brief artifact has an unexpected type for swipe stage-1 RAG "
            f"(artifact_id={asset_brief_artifact_id}, type={asset_brief_artifact.type.value})."
        )
    asset_brief_payload = {
        "artifact": {
            "id": str(asset_brief_artifact.id),
            "type": asset_brief_artifact.type.value,
            "version": int(asset_brief_artifact.version),
            "org_id": str(asset_brief_artifact.org_id),
            "client_id": str(asset_brief_artifact.client_id),
            "product_id": str(asset_brief_artifact.product_id) if asset_brief_artifact.product_id else None,
            "campaign_id": str(asset_brief_artifact.campaign_id) if asset_brief_artifact.campaign_id else None,
            "created_at": asset_brief_artifact.created_at.isoformat() if asset_brief_artifact.created_at else None,
        },
        "data": asset_brief_artifact.data,
    }

    return [
        _require_latest_product_artifact(
            artifact_type=ArtifactTypeEnum.client_canon,
            doc_key="swipe_stage1_client_canon",
            title="Swipe Stage1 Client Canon",
        ),
        {
            "doc_key": "swipe_stage1_design_system",
            "doc_title": "Swipe Stage1 Design System",
            "source_kind": "design_system_snapshot",
            "filename": "swipe_stage1_design_system.json",
            "mime_type": "text/plain",
            "content_bytes": _json_payload_bytes(design_system_payload),
        },
        _require_latest_product_artifact(
            artifact_type=ArtifactTypeEnum.strategy_v2_stage0,
            doc_key="swipe_stage1_strategy_v2_stage0",
            title="Swipe Stage1 Strategy V2 Stage0",
        ),
        _require_latest_product_artifact(
            artifact_type=ArtifactTypeEnum.strategy_v2_stage1,
            doc_key="swipe_stage1_strategy_v2_stage1",
            title="Swipe Stage1 Strategy V2 Stage1",
        ),
        _require_latest_product_artifact(
            artifact_type=ArtifactTypeEnum.strategy_v2_stage2,
            doc_key="swipe_stage1_strategy_v2_stage2",
            title="Swipe Stage1 Strategy V2 Stage2",
        ),
        _require_latest_product_artifact(
            artifact_type=ArtifactTypeEnum.strategy_v2_stage3,
            doc_key="swipe_stage1_strategy_v2_stage3",
            title="Swipe Stage1 Strategy V2 Stage3",
        ),
        _require_latest_product_artifact(
            artifact_type=ArtifactTypeEnum.strategy_v2_awareness_angle_matrix,
            doc_key="swipe_stage1_strategy_v2_awareness_angle_matrix",
            title="Swipe Stage1 Strategy V2 Awareness Angle Matrix",
        ),
        _require_latest_product_artifact(
            artifact_type=ArtifactTypeEnum.strategy_v2_offer,
            doc_key="swipe_stage1_strategy_v2_offer",
            title="Swipe Stage1 Strategy V2 Offer",
        ),
        _require_latest_product_artifact(
            artifact_type=ArtifactTypeEnum.strategy_v2_copy_context,
            doc_key="swipe_stage1_strategy_v2_copy_context",
            title="Swipe Stage1 Strategy V2 Copy Context",
        ),
        _require_latest_product_artifact(
            artifact_type=ArtifactTypeEnum.strategy_v2_copy,
            doc_key="swipe_stage1_strategy_v2_copy",
            title="Swipe Stage1 Strategy V2 Copy",
        ),
        {
            "doc_key": "swipe_stage1_product_profile",
            "doc_title": "Swipe Stage1 Product Profile",
            "source_kind": "product_profile_snapshot",
            "filename": "swipe_stage1_product_profile.json",
            "mime_type": "text/plain",
            "content_bytes": _json_payload_bytes(product_profile_payload),
        },
        {
            "doc_key": "swipe_stage1_offer_pricing",
            "doc_title": "Swipe Stage1 Offer Pricing",
            "source_kind": "offer_pricing_snapshot",
            "filename": "swipe_stage1_offer_pricing.json",
            "mime_type": "text/plain",
            "content_bytes": _json_payload_bytes(offer_pricing_payload),
        },
        _require_latest_campaign_artifact(
            artifact_type=ArtifactTypeEnum.strategy_sheet,
            doc_key="swipe_stage1_campaign_strategy_sheet",
            title="Swipe Stage1 Campaign Strategy Sheet",
        ),
        _require_latest_campaign_artifact(
            artifact_type=ArtifactTypeEnum.experiment_spec,
            doc_key="swipe_stage1_campaign_experiment_spec",
            title="Swipe Stage1 Campaign Experiment Spec",
        ),
        {
            "doc_key": "swipe_stage1_campaign_asset_brief",
            "doc_title": "Swipe Stage1 Campaign Asset Brief",
            "source_kind": ArtifactTypeEnum.asset_brief.value,
            "filename": "swipe_stage1_campaign_asset_brief.json",
            "mime_type": "text/plain",
            "content_bytes": _json_payload_bytes(asset_brief_payload),
        },
    ]


def _resolve_swipe_stage1_gemini_file_search_context(
    *,
    session,
    org_id: str,
    idea_workspace_id: str,
    client_id: str,
    product_id: str,
    campaign_id: str | None,
    funnel_id: str | None,
    asset_brief_artifact_id: str,
) -> tuple[list[str], list[str], list[str], list[str]]:
    if not is_gemini_file_search_enabled():
        raise RuntimeError(
            "Gemini File Search must be enabled for swipe image ad generation. "
            "Set GEMINI_FILE_SEARCH_ENABLED=true."
        )

    rag_docs = _load_required_swipe_stage1_rag_docs(
        session=session,
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        funnel_id=funnel_id,
        asset_brief_artifact_id=asset_brief_artifact_id,
    )

    docs_by_key: Dict[str, Dict[str, Any]] = {}
    for doc in rag_docs:
        doc_key = str(doc["doc_key"])
        if doc_key in docs_by_key:
            raise RuntimeError(f"Duplicate swipe stage-1 RAG doc key encountered: {doc_key}")
        docs_by_key[doc_key] = doc

    bundle_specs: list[tuple[str, str, list[str]]] = [
        (
            "swipe_stage1_bundle_brand_foundation",
            "Swipe Stage1 Bundle: Brand Foundation",
            [
                "swipe_stage1_client_canon",
                "swipe_stage1_design_system",
                "swipe_stage1_product_profile",
            ],
        ),
        (
            "swipe_stage1_bundle_offer_and_pricing",
            "Swipe Stage1 Bundle: Offer And Pricing",
            [
                "swipe_stage1_offer_pricing",
                "swipe_stage1_strategy_v2_offer",
            ],
        ),
        (
            "swipe_stage1_bundle_strategy_stages",
            "Swipe Stage1 Bundle: Strategy Stages",
            [
                "swipe_stage1_strategy_v2_stage0",
                "swipe_stage1_strategy_v2_stage1",
                "swipe_stage1_strategy_v2_stage2",
                "swipe_stage1_strategy_v2_stage3",
                "swipe_stage1_strategy_v2_awareness_angle_matrix",
            ],
        ),
        (
            "swipe_stage1_bundle_strategy_copy",
            "Swipe Stage1 Bundle: Strategy Copy",
            [
                "swipe_stage1_strategy_v2_copy_context",
                "swipe_stage1_strategy_v2_copy",
            ],
        ),
        (
            "swipe_stage1_bundle_campaign_context",
            "Swipe Stage1 Bundle: Campaign Context",
            [
                "swipe_stage1_campaign_strategy_sheet",
                "swipe_stage1_campaign_experiment_spec",
                "swipe_stage1_campaign_asset_brief",
            ],
        ),
    ]

    consumed_keys: set[str] = set()
    bundle_docs: list[Dict[str, Any]] = []
    for bundle_key, bundle_title, bundle_keys in bundle_specs:
        entries: list[Dict[str, Any]] = []
        for key in bundle_keys:
            doc = docs_by_key.get(key)
            if doc is None:
                raise RuntimeError(
                    f"Missing required swipe stage-1 source doc while building bundle {bundle_key}: {key}"
                )
            consumed_keys.add(key)
            entries.append(
                {
                    "doc_key": key,
                    "doc_title": str(doc["doc_title"]),
                    "source_kind": str(doc["source_kind"]),
                    "mime_type": str(doc["mime_type"]),
                    "content_sha256": hashlib.sha256(doc["content_bytes"]).hexdigest(),
                    "content_text": doc["content_bytes"].decode("utf-8"),
                }
            )
        payload = {
            "bundle_key": bundle_key,
            "bundle_title": bundle_title,
            "documents": entries,
        }
        bundle_docs.append(
            {
                "doc_key": bundle_key,
                "doc_title": bundle_title,
                "source_kind": "swipe_stage1_bundle",
                "filename": f"{bundle_key}.json",
                "mime_type": "text/plain",
                "content_bytes": _json_payload_bytes(payload),
            }
        )

    source_doc_keys = sorted(docs_by_key.keys())
    missing_from_bundles = sorted(set(source_doc_keys) - consumed_keys)
    if missing_from_bundles:
        raise RuntimeError(
            "Some swipe stage-1 source docs were not included in any Gemini bundle: "
            f"{missing_from_bundles}"
        )

    document_names: list[str] = []
    bundle_doc_keys: list[str] = []
    store_names: set[str] = set()
    for doc in bundle_docs:
        doc_key = str(doc["doc_key"])
        document_name = ensure_uploaded_to_gemini_file_search(
            org_id=org_id,
            idea_workspace_id=idea_workspace_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            doc_key=doc_key,
            doc_title=str(doc["doc_title"]),
            source_kind=str(doc["source_kind"]),
            step_key="swipe_image_ad_stage1",
            filename=str(doc["filename"]),
            mime_type=str(doc["mime_type"]),
            content_bytes=doc["content_bytes"],
            drive_doc_id=None,
            drive_url=None,
        )
        bundle_doc_keys.append(doc_key)
        document_names.append(document_name)
        store_names.add(_extract_store_name_from_document_name(document_name))

    sorted_store_names = sorted(store_names)
    if not sorted_store_names:
        raise RuntimeError(
            "No Gemini File Search stores were resolved for swipe stage-1 context uploads."
        )
    return sorted_store_names, source_doc_keys, bundle_doc_keys, document_names


def _build_swipe_stage1_prompt_input(
    *,
    prompt_template: str,
    brand_name: str,
    angle: str | None,
) -> str:
    if not isinstance(prompt_template, str) or not prompt_template.strip():
        raise ValueError("swipe stage-1 prompt template is required and must be non-empty.")
    clean_brand = _normalize_prompt_value(brand_name)
    clean_angle = _normalize_prompt_value(angle)
    return (
        f"{prompt_template.strip()}\n\n"
        "RUNTIME INPUTS (INJECTED)\n"
        f"Brand: {clean_brand}\n"
        f"Angle: {clean_angle}\n"
        "Competitor swipe image is attached as image input."
    )


def _resolve_swipe_copy_platform(*, channel_id: str) -> str:
    normalized = (channel_id or "").strip().lower()
    if normalized in {"facebook", "instagram", "meta", "facebook_ads", "instagram_ads"}:
        return "Meta"
    if normalized in {"tiktok", "tik_tok", "tik-tok"}:
        return "TikTok"
    raise ValueError(
        "Swipe Stage 1 copy generation only supports Meta and TikTok channels. "
        f"Received channel={channel_id!r}."
    )


def _resolve_destination_type(
    *,
    session,
    funnel_id: str | None,
    funnel_stage: str | None,
) -> str:
    normalized_stage = (funnel_stage or "").strip().lower()
    if not isinstance(funnel_id, str) or not funnel_id.strip():
        if normalized_stage in {"top-of-funnel", "top", "tof", "middle-of-funnel", "middle", "mid", "mof"}:
            return "Presales Listicle Page"
        if normalized_stage in {"bottom-of-funnel", "bottom", "bof"}:
            return "Sales Page"
        raise ValueError(
            "funnel_id is required to resolve swipe copy destination type when funnelStage is missing or unsupported."
        )

    pages = session.scalars(
        select(FunnelPage).where(FunnelPage.funnel_id == funnel_id.strip())
    ).all()
    template_ids = {
        str(page.template_id).strip()
        for page in pages
        if isinstance(page.template_id, str) and page.template_id.strip()
    }
    if not template_ids:
        raise ValueError(
            "No funnel page template ids were available to resolve swipe copy destination type "
            f"(funnel_id={funnel_id})."
        )

    if normalized_stage in {"bottom-of-funnel", "bottom", "bof"}:
        if "sales-pdp" in template_ids:
            return "Sales Page"
        if len(template_ids) == 1 and "pre-sales-listicle" in template_ids:
            return "Presales Listicle Page"
        raise ValueError(
            "Bottom-of-funnel requirement could not be mapped to a supported destination page type. "
            f"funnel_id={funnel_id} template_ids={sorted(template_ids)}"
        )

    if "pre-sales-listicle" in template_ids:
        return "Presales Listicle Page"
    if "sales-pdp" in template_ids:
        return "Sales Page"

    raise ValueError(
        "Swipe Stage 1 copy destination type is unsupported for the funnel pages attached to this brief. "
        f"funnel_id={funnel_id} template_ids={sorted(template_ids)}"
    )


def _resolve_swipe_copy_asset_type(*, mime_type: str) -> str:
    normalized = (mime_type or "").strip().lower()
    if normalized.startswith("image/"):
        return "image"
    if normalized.startswith("video/"):
        return "video"
    raise ValueError(
        "Swipe Stage 1 copy generation only supports image or video creatives. "
        f"Received mime_type={mime_type!r}."
    )


_BLIND_ANGLE_MECHANISM_TERMS = {
    "check",
    "checks",
    "checklist",
    "checklists",
    "compound",
    "compounds",
    "dose",
    "doses",
    "dosage",
    "dosages",
    "dosing",
    "drug",
    "drugs",
    "enzyme",
    "enzymes",
    "formula",
    "formulas",
    "guide",
    "guides",
    "ingredient",
    "ingredients",
    "interaction",
    "interactions",
    "mechanism",
    "mechanisms",
    "method",
    "methods",
    "mg",
    "milligram",
    "milligrams",
    "pathway",
    "pathways",
    "precision",
    "process",
    "processes",
    "protocol",
    "protocols",
    "requirement",
    "requirements",
    "rule",
    "rules",
    "safety",
    "screen",
    "screening",
    "step",
    "steps",
    "triage",
    "workflow",
    "workflows",
}

_GLOBAL_BLIND_ANGLE_REVEAL_TERMS = {
    "bring to your pharmacist",
    "check",
    "checks",
    "checklist",
    "checklists",
    "focused question list",
    "guide",
    "guides",
    "handbook",
    "how it works",
    "method",
    "methods",
    "process",
    "processes",
    "protocol",
    "protocols",
    "question list",
    "question lists",
    "run it yourself",
    "screen",
    "screening",
    "self directed",
    "step by step",
    "step",
    "steps",
    "walks you through",
    "way to check",
    "workflow",
    "workflows",
}


def _normalize_blind_angle_text(value: str) -> str:
    normalized = value.lower()
    normalized = (
        normalized.replace("–", " ")
        .replace("—", " ")
        .replace("-", " ")
        .replace("/", " ")
        .replace("'", " ")
        .replace('"', " ")
    )
    normalized = re.sub(r"[^a-z0-9\s-]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _collect_blind_angle_forbidden_terms(*values: str | None) -> list[str]:
    phrases: set[str] = set()
    for raw_value in values:
        if not isinstance(raw_value, str) or not raw_value.strip():
            continue
        normalized_value = _normalize_blind_angle_text(raw_value)
        if not normalized_value:
            continue
        tokens = normalized_value.split()
        for idx, token in enumerate(tokens):
            if token not in _BLIND_ANGLE_MECHANISM_TERMS:
                continue
            phrases.add(token)
            start = max(0, idx - 2)
            end = min(len(tokens), idx + 3)
            phrase = " ".join(tokens[start:end]).strip()
            if phrase and phrase != token:
                phrases.add(phrase)
        for match in re.finditer(r"['\"]([^'\"]{2,120})['\"]", raw_value):
            candidate = _normalize_blind_angle_text(match.group(1))
            if not candidate:
                continue
            candidate_tokens = candidate.split()
            if any(token in _BLIND_ANGLE_MECHANISM_TERMS for token in candidate_tokens):
                phrases.add(candidate)
    return sorted((phrase for phrase in phrases if phrase), key=lambda item: (-len(item), item))


def _validate_swipe_copy_blind_angle_blackout(
    *,
    copy_pack: SwipeAdCopyPack,
    forbidden_terms: list[str],
) -> None:
    if not forbidden_terms:
        return
    candidate_text = "\n".join(
        value
        for value in (
            copy_pack.formatted_variations_markdown,
            copy_pack.meta_primary_text,
            copy_pack.meta_headline,
            copy_pack.meta_description,
            copy_pack.tiktok_caption,
            copy_pack.tiktok_on_screen_text,
        )
        if isinstance(value, str) and value.strip()
    )
    normalized_candidate = f" {_normalize_blind_angle_text(candidate_text)} "
    matches: list[str] = []
    for term in forbidden_terms:
        normalized_term = _normalize_blind_angle_text(term)
        if normalized_term and f" {normalized_term} " in normalized_candidate:
            matches.append(term)
    if matches:
        preview = ", ".join(repr(term) for term in matches[:8])
        if len(matches) > 8:
            preview += ", ..."
        raise ValueError(
            "Swipe Stage 1 copy leaked forbidden blind-angle terms into feed copy: "
            f"{preview}. Regenerate with a stronger curiosity gap."
        )


def _build_swipe_copy_stage1_prompt(
    *,
    brief: Dict[str, Any],
    requirement_index: int,
    requirement: Dict[str, Any],
    platform: str,
    destination_type: str,
    swipe_asset_type: str,
    swipe_mime_type: str,
    swipe_source_label: str | None,
    swipe_source_url: str,
    forbidden_terms: list[str],
    retry_feedback: str | None = None,
) -> str:
    input_payload = {
        "Platform": platform,
        "Ad Image or Video": {
            "assetType": swipe_asset_type,
            "sourceLabel": swipe_source_label,
            "sourceUrl": swipe_source_url,
            "mimeType": swipe_mime_type,
            "attachedInlineToGemini": True,
        },
        "Angle Used": requirement.get("angle"),
        "Destination Page": destination_type,
        "Project Docs": {
            "assetBriefId": brief.get("id"),
            "campaignId": brief.get("campaignId"),
            "funnelId": brief.get("funnelId"),
            "variantId": brief.get("variantId"),
            "variantName": brief.get("variantName"),
            "creativeConcept": brief.get("creativeConcept"),
            "constraints": brief.get("constraints") or [],
            "toneGuidelines": brief.get("toneGuidelines") or [],
            "visualGuidelines": brief.get("visualGuidelines") or [],
        },
        "Requirement Context": {
            "requirementIndex": requirement_index,
            "channel": requirement.get("channel"),
            "format": requirement.get("format"),
            "funnelStage": requirement.get("funnelStage"),
            "hook": requirement.get("hook"),
        },
        "Blind Angle Forbidden Terms": forbidden_terms,
    }

    prompt = (
        "ROLE:\n"
        "You are an elite, top-tier Direct Response Copywriter and Media Buying Strategist specializing strictly "
        "in Meta (Facebook/Instagram) and TikTok in-feed ads. Your expertise lies in analyzing visual ad creatives, "
        "extracting their core psychological angles, and writing visceral ad copy designed with one singular goal: "
        "maximizing Link Click-Through Rate (CTR).\n\n"
        "OBJECTIVE:\n"
        "Take the attached ad creative, the declared destination page, the attached project documentation, the "
        "specified Angle Used, and the target platform. Silently analyze everything, then build three copy "
        "variations that stay locked to the exact same angle.\n\n"
        "INPUTS YOU WILL RECEIVE:\n"
        f"- Platform: {platform}\n"
        f"- Ad Image or Video: attached {swipe_asset_type} asset ({swipe_source_label or 'unlabeled asset'}, {swipe_mime_type})\n"
        f"- Angle Used: {requirement.get('angle')}\n"
        f"- Destination Page: {destination_type}\n"
        "- Project Docs: attached through Gemini File Search context.\n\n"
        "THE SINGLE ANGLE CONSTRAINT:\n"
        "All 3 variations must focus exclusively on the supplied Angle Used. Do not invent a new angle. "
        "Variation 1, Variation 2, and Variation 3 must be different emotional or structural approaches to the "
        "same angle.\n\n"
        "THE BLIND ANGLE AND INFORMATION BLACKOUT RULE:\n"
        "Never explain how the product works, what the exact solution is, or list specific requirements for success. "
        "If the Angle Used names a mechanism, dosage, interaction, ingredient, or other specific lever, you must "
        "not use that exact mechanism language in the feed copy. Translate it into a blind curiosity gap using vague, "
        "ominous references such as 'this', 'that one hidden detail', 'the fatal flaw', or 'the one thing'. Sell the "
        "click, not the lesson.\n\n"
        "BLACKOUT ENFORCEMENT:\n"
        "The following words and phrases are banned from the ad copy because they reveal the angle. Do not use them in "
        "variation titles, primary text, headlines, descriptions, captions, or on-screen text:\n"
        f"{json.dumps(forbidden_terms, ensure_ascii=False)}\n\n"
        "If you need to refer to the promised thing, use only blind nouns like 'this', 'the missing piece', "
        "'the one detail', 'what they left out', or 'the thing nobody warns you about'. Never call it a guide, "
        "check, checklist, process, workflow, method, step, screen, handbook, or question list.\n\n"
        "THE SLIPPERY SLOPE RULE:\n"
        "Never write block paragraphs. Each sentence in the primary text must be separated by a hard line break, "
        "but the copy must still read as one cohesive escalation from hook to agitation to bridge to CTA.\n\n"
        "PLATFORM RULES:\n"
        "- Meta: Primary Text must stay short, narrative, and broken into 3-5 punchy lines. Headline must be "
        "40-60 characters. Description must be a short urgency trigger. CTA must be one of Learn More, Shop Now, "
        "Watch More, or Sign Up.\n"
        "- TikTok: Caption must feel native and stay under 150 characters. Include 1-3 relevant hashtags. "
        "On-screen text must be a visceral 1-2 sentence hook for the first 3 seconds. CTA must be Learn More or Shop Now.\n\n"
        "GENERAL RULES:\n"
        "- If the Destination Page is a listicle, do not use specific numbers in the copy or headline.\n"
        "- Use plain, bar-stool language. Ban fluffy corporate words.\n"
        "- Match the destination scent. If the Destination Page is a presell page, the copy should feel like "
        "a warning, a leak, a breaking discovery, or a shocking reveal.\n"
        "- Respect attached project constraints and compliance rules. If a project constraint conflicts with the "
        "aggressive copy style, obey the constraint and stay as direct-response as the source materials allow.\n\n"
        "STRUCTURED OUTPUT RULE:\n"
        "Return valid JSON only. Do not wrap the JSON in prose. If you use a markdown fence, use a single ```json fence "
        "that contains only the JSON object. Escape every newline inside string values as \\n. Put the exact requested "
        "three-variation output inside `formattedVariationsMarkdown` as one markdown code block string. The code block "
        "must contain exactly 3 variations and use the requested field labels. "
        "Do not use literal double-quote characters inside any string value unless they are escaped. Prefer paraphrasing "
        "quoted speech instead of quoting it.\n"
        "Then populate the platform-specific selected variation fields in JSON:\n"
        "- For Meta, fill `metaPrimaryText`, `metaHeadline`, `metaDescription`, and `metaCta` from the best single variation.\n"
        "- For TikTok, fill `tiktokCaption`, `tiktokOnScreenText`, and `tiktokCta` from the best single variation.\n"
        "- `selectedVariation` must name the winning variation exactly.\n"
        "- `claimsGuardrails` must contain short, concrete publishing guardrails grounded in the attached docs.\n"
        "- Do not output strategy notes or creative breakdown outside the JSON fields.\n\n"
        "JSON SHAPE:\n"
        "{\n"
        '  "selectedVariation": "Variation 1: ...",\n'
        '  "formattedVariationsMarkdown": "```text\\\\n**Variation 1: ...",\n'
        '  "metaPrimaryText": "Sentence 1\\\\n\\\\nSentence 2...",\n'
        '  "metaHeadline": "Headline here",\n'
        '  "metaDescription": "Description here",\n'
        '  "metaCta": "Learn More",\n'
        '  "tiktokCaption": null,\n'
        '  "tiktokOnScreenText": null,\n'
        '  "tiktokCta": null,\n'
        '  "claimsGuardrails": ["Guardrail 1", "Guardrail 2"]\n'
        "}\n\n"
        "OUTPUT LAYOUT TO MIRROR INSIDE formattedVariationsMarkdown:\n"
        "```text\n"
        "**Variation 1: [Target Angle - Approach]**\n\n"
        "**Primary Text:** [Sentence 1]\n\n"
        "[Sentence 2]\n\n"
        "[Sentence 3]\n\n"
        "[Sentence 4 if needed]\n\n"
        "**Headline:** [Headline]\n"
        "**Description:** [Description]\n"
        "**CTA:** [Button]\n\n"
        "---\n\n"
        "**Variation 2: [Target Angle - Approach]**\n"
        "...\n\n"
        "---\n\n"
        "**Variation 3: [Target Angle - Approach]**\n"
        "...\n"
        "```\n\n"
    )
    if isinstance(retry_feedback, str) and retry_feedback.strip():
        prompt += f"RETRY CORRECTION:\n{retry_feedback}\n\n"
    prompt += f"INPUT JSON:\n{json.dumps(input_payload, ensure_ascii=False, indent=2)}"
    return prompt


def _extract_first_json_object_from_text(text: str) -> Dict[str, Any]:
    start = text.find("{")
    if start < 0:
        raise RuntimeError("Swipe Stage 1 copy response did not contain a JSON object.")

    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        char = text[idx]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : idx + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError as exc:
                    raise RuntimeError("Swipe Stage 1 copy response contained malformed JSON.") from exc

    raise RuntimeError("Swipe Stage 1 copy response contained malformed JSON.")


def _repair_truncated_json(text: str) -> str | None:
    stripped = text.rstrip()
    if not stripped.startswith("{"):
        return None

    closing_stack: list[str] = []
    in_string = False
    escape = False
    for char in stripped:
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            closing_stack.append("}")
            continue
        if char == "[":
            closing_stack.append("]")
            continue
        if char in {"}", "]"}:
            if not closing_stack or char != closing_stack[-1]:
                return None
            closing_stack.pop()

    if not closing_stack:
        return None

    repaired = stripped
    if in_string:
        # Gemini sometimes truncates inside a JSON string. Close the open escape
        # sequence/string, then close any remaining containers.
        if escape:
            repaired += "\\"
        repaired += '"'

    return repaired + "".join(reversed(closing_stack))


def _strip_trailing_commas(text: str) -> str:
    out: list[str] = []
    in_string = False
    escape = False
    for ch in text:
        if in_string:
            out.append(ch)
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
            out.append(ch)
            continue

        if ch in ("}", "]"):
            j = len(out) - 1
            while j >= 0 and out[j].isspace():
                j -= 1
            if j >= 0 and out[j] == ",":
                out.pop(j)
        out.append(ch)

    return "".join(out)


def _escape_unescaped_control_chars(text: str) -> str:
    out: list[str] = []
    in_string = False
    escape = False
    for ch in text:
        if in_string:
            if escape:
                if ch not in {'"', "\\", "/", "b", "f", "n", "r", "t", "u"} and out and out[-1] == "\\":
                    out.pop()
                out.append(ch)
                escape = False
                continue
            if ch == "\\":
                out.append(ch)
                escape = True
                continue
            if ch == '"':
                in_string = False
                out.append(ch)
                continue
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                out.append("\\r")
                continue
            if ch == "\t":
                out.append("\\t")
                continue
            if ch == "\b":
                out.append("\\b")
                continue
            if ch == "\f":
                out.append("\\f")
                continue
            if ord(ch) < 0x20:
                out.append(f"\\u{ord(ch):04x}")
                continue
            out.append(ch)
            continue

        if ch == '"':
            in_string = True
        out.append(ch)

    return "".join(out)


def _repair_json_text(text: str) -> str:
    if not text:
        return text
    repaired = _strip_trailing_commas(text)
    return _escape_unescaped_control_chars(repaired)


def _parse_swipe_copy_json_object(text: str) -> Dict[str, Any]:
    candidates: list[str] = []
    seen: set[str] = set()

    def _add(candidate: str | None) -> None:
        if not isinstance(candidate, str):
            return
        stripped = candidate.strip()
        if not stripped or stripped in seen:
            return
        seen.add(stripped)
        candidates.append(stripped)

    raw = _strip_json_fence(text)
    repaired = _repair_json_text(raw)
    repaired_truncated = _repair_truncated_json(raw)
    repaired_truncated_sanitized = _repair_truncated_json(repaired)

    _add(raw)
    _add(repaired)
    _add(repaired_truncated)
    _add(repaired_truncated_sanitized)

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed

        try:
            parsed = _extract_first_json_object_from_text(candidate)
        except RuntimeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed

    raise RuntimeError("Swipe Stage 1 copy response did not contain a valid JSON object.")


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    first_newline = stripped.find("\n")
    if first_newline > 0:
        fence_header = stripped[:first_newline].strip().lower()
        if fence_header in {"```", "```json"}:
            return stripped[first_newline + 1 :].lstrip()
    return stripped


def _extract_gemini_finish_reason(response: Any) -> str | None:
    candidates = getattr(response, "candidates", None)
    if not isinstance(candidates, list) or not candidates:
        return None
    reason = getattr(candidates[0], "finish_reason", None)
    if reason is None:
        return None
    return str(getattr(reason, "value", reason))


def _call_swipe_copy_gemini_json_message(
    *,
    model: str,
    system_instruction: str,
    contents: List[Any],
    store_names: list[str] | None,
    max_tokens: int,
    temperature: float,
    response_schema: Any | None = None,
) -> Dict[str, Any]:
    gemini_client = _ensure_gemini_client()
    unique_store_names = sorted(
        {name.strip() for name in (store_names or []) if isinstance(name, str) and name.strip()}
    )
    config_kwargs: Dict[str, Any] = {
        "temperature": temperature,
        "max_output_tokens": max_tokens,
        "system_instruction": system_instruction,
    }
    if unique_store_names:
        config_kwargs["tools"] = [
            genai_types.Tool(
                file_search=genai_types.FileSearch(file_search_store_names=unique_store_names)
            )
        ]
    if response_schema is not None and not unique_store_names:
        config_kwargs["response_mime_type"] = "application/json"
        if hasattr(response_schema, "model_json_schema"):
            config_kwargs["response_json_schema"] = response_schema.model_json_schema()
        else:
            config_kwargs["response_json_schema"] = response_schema
    response = _call_gemini_generate_content_with_retries(
        gemini_client=gemini_client,
        model=model,
        contents=contents,
        config=genai_types.GenerateContentConfig(**config_kwargs),
        operation_name="Swipe Stage 1 copy generation",
        file_search_model_error_message=(
            "Swipe Stage 1 copy generation model does not support Gemini File Search. "
            f"model={model}. Choose a Gemini model with File Search support for this workflow."
        ),
    )

    parsed = getattr(response, "parsed", None)
    if parsed is not None and hasattr(parsed, "model_dump"):
        parsed = parsed.model_dump(mode="json", by_alias=True, exclude_none=False)

    text = _extract_gemini_text(response) or ""
    if parsed is None:
        try:
            parsed = _parse_swipe_copy_json_object(text)
        except RuntimeError as exc:
            preview = _strip_json_fence(text).strip()[:1200]
            raise RuntimeError(
                "Swipe Stage 1 copy response was not valid JSON. "
                f"Raw response preview: {preview!r}"
            ) from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Swipe Stage 1 copy generation returned a non-object JSON payload.")
    return {
        "parsed": parsed,
        "text": _strip_json_fence(text),
        "stop_reason": _extract_gemini_finish_reason(response),
        "output_tokens": (_extract_gemini_usage_details(response) or {}).get("output"),
    }


def _audit_swipe_copy_blind_angle_blackout(
    *,
    copy_pack: SwipeAdCopyPack,
    angle: str | None,
    hook: str | None,
    forbidden_terms: list[str],
    destination_type: str,
    model: str,
) -> tuple[bool, str | None]:
    audit_payload = {
        "platform": copy_pack.platform,
        "destinationPage": destination_type,
        "angleUsed": angle,
        "hook": hook,
        "forbiddenTerms": forbidden_terms,
        "selectedVariation": copy_pack.selected_variation,
        "formattedVariationsMarkdown": copy_pack.formatted_variations_markdown,
        "metaPrimaryText": copy_pack.meta_primary_text,
        "metaHeadline": copy_pack.meta_headline,
        "metaDescription": copy_pack.meta_description,
        "metaCta": copy_pack.meta_cta,
        "tiktokCaption": copy_pack.tiktok_caption,
        "tiktokOnScreenText": copy_pack.tiktok_on_screen_text,
        "tiktokCta": copy_pack.tiktok_cta,
    }
    audit_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "passes": {"type": "boolean"},
            "violations": {"type": "array", "items": {"type": "string"}},
            "retryFeedback": {"type": ["string", "null"]},
        },
        "required": ["passes", "violations", "retryFeedback"],
    }
    response = _call_swipe_copy_gemini_json_message(
        model=model,
        system_instruction=(
            "You are a strict direct-response copy QA auditor. Your job is to reject ad copy that violates the blind "
            "angle or information blackout rule. Return JSON only."
        ),
        contents=[
            (
                "Audit the candidate ad copy below.\n\n"
                "FAIL the copy if ANY of the following are true:\n"
                "- It repeats or closely reveals the mechanism, requirement, workflow, checklist, guide, screening, "
                "process, step, protocol, interaction, dosage, ingredient, or other lesson named in the angle/hook.\n"
                "- It explains what the solution is, how it works, how to do it, or what exact tool/process the user "
                "will see after clicking.\n"
                "- It names a concrete self-service process such as a check, checklist, guide, workflow, question list, "
                "screening step, or run-it-yourself method.\n"
                "- It uses the forbidden terms list directly.\n"
                "- If the destination page is a listicle, it uses specific numbers in copy or headline.\n\n"
                "PASS only if the copy stays blind, curiosity-driven, and sells the click without teaching the lesson.\n\n"
                "Return valid JSON with exactly this shape:\n"
                "{\n"
                '  "passes": true,\n'
                '  "violations": [],\n'
                '  "retryFeedback": null\n'
                "}\n\n"
                "If it fails, set `passes` to false, list concise violations, and provide a short `retryFeedback` that tells "
                "the generator what to remove.\n\n"
                f"CANDIDATE JSON:\n{json.dumps(audit_payload, ensure_ascii=False, indent=2)}"
            )
        ],
        store_names=[],
        max_tokens=1200,
        temperature=0.0,
        response_schema=audit_schema,
    )
    parsed = response.get("parsed")
    if not isinstance(parsed, dict):
        raise RuntimeError("Swipe Stage 1 copy blackout audit returned a non-dict parsed payload.")
    passes = bool(parsed.get("passes"))
    if passes:
        return True, None
    retry_feedback = parsed.get("retryFeedback")
    if isinstance(retry_feedback, str) and retry_feedback.strip():
        return False, retry_feedback.strip()
    violations = parsed.get("violations")
    if isinstance(violations, list):
        flattened = "; ".join(str(item).strip() for item in violations if str(item).strip())
        if flattened:
            return False, flattened
    return False, "Copy failed the blind-angle blackout audit. Remove all solution and mechanism reveals."


def _generate_swipe_stage1_copy_pack(
    *,
    session,
    brief: Dict[str, Any],
    requirement_index: int,
    requirement: Dict[str, Any],
    copy_model: str,
    gemini_store_names: list[str],
    swipe_bytes: bytes,
    swipe_mime_type: str,
    swipe_source_url: str,
    swipe_source_label: str | None,
    product_prompt_image_bytes: bytes | None,
    product_prompt_image_mime_type: str | None,
) -> tuple[SwipeAdCopyPack, Dict[str, Any], str]:
    channel_id = str(requirement.get("channel") or "").strip()
    if not channel_id:
        raise ValueError("Swipe Stage 1 copy generation requires a non-empty requirement channel.")
    platform = _resolve_swipe_copy_platform(channel_id=channel_id)
    swipe_asset_type = _resolve_swipe_copy_asset_type(mime_type=swipe_mime_type)
    forbidden_terms = sorted(
        {
            *_GLOBAL_BLIND_ANGLE_REVEAL_TERMS,
            *_collect_blind_angle_forbidden_terms(
                requirement.get("angle") if isinstance(requirement.get("angle"), str) else None,
                requirement.get("hook") if isinstance(requirement.get("hook"), str) else None,
            ),
        },
        key=lambda item: (-len(item), item),
    )
    destination_type = _resolve_destination_type(
        session=session,
        funnel_id=str(brief.get("funnelId") or "").strip() or None,
        funnel_stage=(
            str(requirement.get("funnelStage")).strip()
            if isinstance(requirement.get("funnelStage"), str) and requirement.get("funnelStage").strip()
            else None
        ),
    )
    retry_feedback: str | None = None
    last_response: Dict[str, Any] | None = None
    for attempt in range(1, 6):
        prompt = _build_swipe_copy_stage1_prompt(
            brief=brief,
            requirement_index=requirement_index,
            requirement=requirement,
            platform=platform,
            destination_type=destination_type,
            swipe_asset_type=swipe_asset_type,
            swipe_mime_type=swipe_mime_type,
            swipe_source_label=swipe_source_label,
            swipe_source_url=swipe_source_url,
            forbidden_terms=forbidden_terms,
            retry_feedback=retry_feedback,
        )
        contents: List[Any] = [
            prompt,
            "Ad Image or Video asset:",
            genai_types.Part.from_bytes(data=swipe_bytes, mime_type=swipe_mime_type),
        ]
        if product_prompt_image_bytes is not None and product_prompt_image_mime_type is not None:
            contents.extend(
                [
                    "Product reference image asset:",
                    genai_types.Part.from_bytes(
                        data=product_prompt_image_bytes,
                        mime_type=product_prompt_image_mime_type,
                    ),
                ]
            )
        response = _call_swipe_copy_gemini_json_message(
            model=copy_model,
            system_instruction=(
                "Generate swipe-specific direct response ad copy. Use the attached project documents as the source of truth. "
                "Do not invent unsupported claims, product facts, pricing, guarantees, or scientific proof. "
                "Return JSON only."
            ),
            contents=contents,
            store_names=gemini_store_names,
            max_tokens=6000,
            temperature=0.2,
            response_schema=SwipeAdCopyPack,
        )
        last_response = response
        parsed = response.get("parsed")
        if not isinstance(parsed, dict):
            raise RuntimeError("Swipe Stage 1 copy generation returned a non-dict parsed payload.")

        merged_payload = dict(parsed)
        merged_payload.update(
            {
                "platform": platform,
                "requirementIndex": requirement_index,
                "channel": str(requirement.get("channel") or ""),
                "format": str(requirement.get("format") or ""),
                "funnelStage": requirement.get("funnelStage"),
                "angle": requirement.get("angle"),
                "hook": requirement.get("hook"),
                "destinationType": destination_type,
            }
        )
        try:
            validated = SwipeAdCopyPack.model_validate(merged_payload)
        except ValidationError as exc:
            if attempt >= 5:
                raise RuntimeError(_summarize_swipe_copy_validation_error(exc)) from exc
            retry_feedback = (
                _summarize_swipe_copy_validation_error(exc)
                + " Preserve the same angle, but return the full valid JSON object."
            )
            continue
        try:
            _validate_swipe_copy_blind_angle_blackout(
                copy_pack=validated,
                forbidden_terms=forbidden_terms,
            )
        except ValueError as exc:
            if attempt >= 5:
                raise RuntimeError(str(exc)) from exc
            retry_feedback = (
                f"{exc} Remove the banned terms entirely and rebuild all 3 variations around a blind curiosity gap."
            )
            continue
        passes_audit, audit_feedback = _audit_swipe_copy_blind_angle_blackout(
            copy_pack=validated,
            angle=requirement.get("angle") if isinstance(requirement.get("angle"), str) else None,
            hook=requirement.get("hook") if isinstance(requirement.get("hook"), str) else None,
            forbidden_terms=forbidden_terms,
            destination_type=destination_type,
            model=copy_model,
        )
        if not passes_audit:
            if attempt >= 5:
                raise RuntimeError(audit_feedback or "Swipe Stage 1 copy failed the blackout audit.")
            retry_feedback = audit_feedback or (
                "The copy still reveals the solution or the angle mechanics. Remove those reveals and make the click "
                "curiosity-driven."
            )
            continue
        return validated, response, copy_model
    raise RuntimeError(
        "Swipe Stage 1 copy generation exhausted retry attempts without producing a valid blind-angle-compliant output."
        if last_response is not None
        else "Swipe Stage 1 copy generation did not produce a response."
    )


def _poll_image_job(
    *,
    creative_client: Any,
    job_id: str,
    initial_job: Any | None = None,
) -> Any:
    if initial_job is not None and getattr(initial_job, "status", None) in ("succeeded", "failed"):
        return initial_job

    poll_interval = float(settings.CREATIVE_SERVICE_POLL_INTERVAL_SECONDS or 2.0)
    poll_timeout = float(settings.CREATIVE_SERVICE_POLL_TIMEOUT_SECONDS or 300.0)
    if poll_interval <= 0:
        raise ValueError("CREATIVE_SERVICE_POLL_INTERVAL_SECONDS must be greater than zero.")
    if poll_timeout <= 0:
        raise ValueError("CREATIVE_SERVICE_POLL_TIMEOUT_SECONDS must be greater than zero.")

    started = time.monotonic()
    while True:
        job = creative_client.get_image_ads_job(job_id=job_id)
        if job.status in ("succeeded", "failed"):
            return job
        if (time.monotonic() - started) > poll_timeout:
            raise RuntimeError(
                f"Timed out waiting for image ads job completion (job_id={job_id}, timeout_seconds={poll_timeout})"
            )
        time.sleep(poll_interval)


def _extract_gemini_text(result: Any) -> str | None:
    """
    Extract text from a google.genai generation result.

    Note: In some library versions, `result.text` raises instead of returning a string.
    """
    try:
        text = getattr(result, "text", None)
    except Exception:
        text = None
    if isinstance(text, str) and text.strip():
        return text

    candidates = getattr(result, "candidates", None)
    if not candidates:
        return None
    first = candidates[0]
    if not first:
        return None
    content = getattr(first, "content", None)
    parts = getattr(content, "parts", None) if content else None
    if not parts:
        return None

    texts: List[str] = []
    for part in parts:
        part_text = getattr(part, "text", None)
        if isinstance(part_text, str) and part_text:
            texts.append(part_text)
    joined = "\n".join(texts).strip()
    return joined or None


def _extract_gemini_usage_details(result: Any) -> Dict[str, int] | None:
    usage = getattr(result, "usage_metadata", None)
    if usage is None:
        return None

    input_tokens = getattr(usage, "prompt_token_count", None)
    output_tokens = getattr(usage, "candidates_token_count", None)
    if isinstance(usage, dict):
        input_tokens = usage.get("prompt_token_count", input_tokens)
        output_tokens = usage.get("candidates_token_count", output_tokens)

    usage_details: Dict[str, int] = {}
    if isinstance(input_tokens, int):
        usage_details["input"] = input_tokens
    if isinstance(output_tokens, int):
        usage_details["output"] = output_tokens
    return usage_details or None


def _is_retryable_render_failure(error_text: str | None) -> bool:
    if not isinstance(error_text, str) or not error_text.strip():
        return False
    normalized = error_text.lower()
    retryable_markers = (
        "inline image",
        "internal error",
        "status\": \"internal\"",
        "failed (500)",
        "timed out",
        "network error",
    )
    return any(marker in normalized for marker in retryable_markers)


@activity.defn(name="swipes.generate_swipe_image_ad")
def generate_swipe_image_ad_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate ONE (or N) image ad(s) by adapting a competitor swipe image.

    Flow:
      1) Use Gemini (vision) with the stage-1 prompt template + runtime brand/angle + attached RAG docs + the
         competitor swipe image to produce a dense, generation-ready image prompt.
      2) Extract ONLY the prompt from the Gemini markdown output (```text fenced block).
      3) Send ONLY that extracted prompt to the MOS-embedded Freestyle renderer to render the final image(s).
      4) Persist generated assets attached to the provided asset brief.
    """

    org_id = params["org_id"]
    client_id = params["client_id"]
    product_id = params["product_id"]
    campaign_id = params.get("campaign_id")
    asset_brief_id = params["asset_brief_id"]
    requirement_index = int(params.get("requirement_index") or 0)
    workflow_run_id = params.get("workflow_run_id")
    idea_workspace_id = (
        params.get("idea_workspace_id")
        or params.get("workflow_id")
        or params.get("campaign_id")
        or params.get("client_id")
    )
    if not isinstance(idea_workspace_id, str) or not idea_workspace_id.strip():
        raise ValueError("idea_workspace_id resolution failed; expected campaign_id or client_id in params.")
    idea_workspace_id = idea_workspace_id.strip()

    company_swipe_id: str | None = params.get("company_swipe_id")
    swipe_image_url: str | None = params.get("swipe_image_url")
    creative_generation_batch_id = _optional_clean_string(params.get("creative_generation_batch_id"))
    creative_generation_plan_artifact_id = _optional_clean_string(params.get("creative_generation_plan_artifact_id"))
    creative_generation_plan_item_id = _optional_clean_string(params.get("creative_generation_plan_item_id"))
    ad_copy_pack_artifact_id = _optional_clean_string(params.get("ad_copy_pack_artifact_id"))
    ad_copy_pack_id = _optional_clean_string(params.get("ad_copy_pack_id"))
    swipe_requires_product_image_raw = params.get("swipe_requires_product_image")
    if swipe_requires_product_image_raw is None:
        swipe_requires_product_image: bool | None = None
    elif isinstance(swipe_requires_product_image_raw, bool):
        swipe_requires_product_image = swipe_requires_product_image_raw
    else:
        raise ValueError("swipe_requires_product_image must be a boolean when provided.")

    model = (
        params.get("model")
        or os.getenv("SWIPE_PROMPT_MODEL")
        or os.getenv("GEMINI_FILE_SEARCH_MODEL")
        or settings.GEMINI_FILE_SEARCH_MODEL
    )
    model_name = _normalize_gemini_model_name(str(model or ""))
    if _is_image_render_model_name(model_name):
        raise ValueError(
            "model is used for stage-1 swipe prompt generation only and cannot be an image rendering model. "
            "Set model/SWIPE_PROMPT_MODEL to a Gemini File Search-capable text model, and set "
            "render_model_id/SWIPE_IMAGE_RENDER_MODEL for the final image rendering step."
        )
    requested_render_model_id = (
        params.get("render_model_id")
        or os.getenv("SWIPE_IMAGE_RENDER_MODEL")
        or settings.SWIPE_IMAGE_RENDER_MODEL
    )
    render_model_id: str | None = None
    if requested_render_model_id is not None:
        if not isinstance(requested_render_model_id, str) or not requested_render_model_id.strip():
            raise ValueError("render_model_id must be a non-empty string when provided.")
        requested_render_model_id = requested_render_model_id.strip()
        render_model_id = _normalize_render_model_id(requested_render_model_id)
    else:
        requested_render_model_id = None

    max_output_tokens = int(params.get("max_output_tokens") or os.getenv("SWIPE_PROMPT_MAX_OUTPUT_TOKENS") or "6000")
    aspect_ratio = (params.get("aspect_ratio") or "1:1").strip()
    count = int(params.get("count") or 1)
    if count <= 0:
        raise ValueError("count must be >= 1 for swipe image ad generation.")
    if creative_generation_plan_item_id and not creative_generation_batch_id:
        raise ValueError(
            "creative_generation_batch_id is required when creative_generation_plan_item_id is provided."
        )
    if creative_generation_plan_item_id and count != 1:
        raise ValueError(
            "creative_generation_plan_item_id requires count=1 for deterministic checkpointing."
        )
    render_count = count
    render_max_attempts = int(os.getenv("SWIPE_IMAGE_RENDER_MAX_ATTEMPTS", "3"))
    if render_max_attempts <= 0:
        raise ValueError("SWIPE_IMAGE_RENDER_MAX_ATTEMPTS must be greater than zero.")

    def log_activity(step: str, status: str, *, payload_in=None, payload_out=None, error: str | None = None) -> None:
        if not workflow_run_id:
            return
        with session_scope() as log_session:
            WorkflowsRepository(log_session).log_activity(
                workflow_run_id=str(workflow_run_id),
                step=step,
                status=status,
                payload_in=payload_in,
                payload_out=payload_out,
                error=error,
            )

    render_provider = get_image_render_provider(model_id=render_model_id)
    log_activity(
        "swipe_image_ad",
        "started",
        payload_in={
            "asset_brief_id": asset_brief_id,
            "campaign_id": campaign_id,
            "company_swipe_id": company_swipe_id,
            "swipe_image_url": swipe_image_url,
            "swipe_requires_product_image": swipe_requires_product_image,
            "model": model_name,
            "render_model_id_requested": requested_render_model_id,
            "render_model_id_used": render_model_id,
            "render_provider": render_provider,
            "count": count,
            "render_count": render_count,
            "aspect_ratio": aspect_ratio,
            "requirement_index": requirement_index,
        },
    )

    try:
        render_client = build_image_render_client(model_id=render_model_id, org_id=org_id)
    except CreativeServiceConfigError as exc:
        raise RuntimeError(str(exc)) from exc

    prompt_template, prompt_sha = load_swipe_to_image_ad_prompt()

    with session_scope() as session:
        artifacts_repo = ArtifactsRepository(session)
        brief, brief_artifact_id = _extract_brief(
            artifacts_repo=artifacts_repo,
            org_id=org_id,
            client_id=client_id,
            campaign_id=campaign_id,
            asset_brief_id=asset_brief_id,
        )
        funnel_id = _validate_brief_scope(
            session=session,
            org_id=org_id,
            client_id=client_id,
            campaign_id=campaign_id,
            asset_brief_id=asset_brief_id,
            brief=brief,
        )

        requirements_raw = brief.get("requirements") or []
        if not isinstance(requirements_raw, list) or not requirements_raw:
            raise ValueError("Asset brief has no requirements.")
        if requirement_index < 0 or requirement_index >= len(requirements_raw):
            raise ValueError(
                f"requirement_index out of range for asset brief {asset_brief_id}. "
                f"expected 0..{len(requirements_raw) - 1} got {requirement_index}"
            )
        requirement = requirements_raw[requirement_index]
        if not isinstance(requirement, dict):
            raise ValueError("Asset brief requirement must be an object.")

        channel_id = (requirement.get("channel") or "meta").strip()
        fmt = (requirement.get("format") or "image").strip()
        angle = requirement.get("angle") if isinstance(requirement.get("angle"), str) else None

        # Creative brief / brand context.
        brand_ctx = _extract_brand_context(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
        )
        client_name = brand_ctx.get("client_name") or ""

        # Swipe image bytes.
        swipe_bytes, swipe_mime_type, swipe_source_url = _resolve_swipe_image(
            session=session,
            org_id=org_id,
            company_swipe_id=company_swipe_id,
            swipe_image_url=swipe_image_url,
        )
        swipe_image_sha256 = hashlib.sha256(swipe_bytes).hexdigest()
        swipe_image_size_bytes = len(swipe_bytes)
        resolved_swipe_requires_product_image, swipe_product_image_policy_source, swipe_source_filename = (
            _resolve_swipe_requires_product_image_policy(
                explicit_requires_product_image=swipe_requires_product_image,
                swipe_source_url=swipe_source_url,
            )
        )
        swipe_source_label = (
            str(params.get("swipe_source_label")).strip()
            if isinstance(params.get("swipe_source_label"), str) and str(params.get("swipe_source_label")).strip()
            else swipe_source_filename
        )

        if resolved_swipe_requires_product_image is False:
            product_reference_assets = []
        elif resolved_swipe_requires_product_image is True:
            try:
                product_reference_assets = _select_product_reference_assets(
                    session=session,
                    org_id=org_id,
                    product_id=product_id,
                )
            except ValueError as exc:
                if "No active source product images are available" in str(exc):
                    raise ValueError(
                        "Swipe requires product image references, but no active source product images are available "
                        f"(product_id={product_id}, swipe_source={swipe_source_url})."
                    ) from exc
                raise
            if not product_reference_assets:
                raise ValueError(
                    "Swipe requires product image references, but product reference selection returned empty "
                    f"(product_id={product_id}, swipe_source={swipe_source_url})."
                )
        else:
            # Product references remain optional when no explicit or catalog policy is available.
            try:
                product_reference_assets = _select_product_reference_assets(
                    session=session,
                    org_id=org_id,
                    product_id=product_id,
                )
            except ValueError as exc:
                if "No active source product images are available" in str(exc):
                    product_reference_assets = []
                else:
                    raise

        product_reference_render_ids: list[str] = []
        if render_provider == "creative_service":
            product_reference_render_ids = [
                reference.local_asset_id
                for reference in product_reference_assets
                if isinstance(reference.local_asset_id, str) and reference.local_asset_id.strip()
            ]
        all_product_reference_image_urls = [
            reference.primary_url
            for reference in product_reference_assets
            if isinstance(reference.primary_url, str) and reference.primary_url.strip()
        ]
        product_reference_image_urls = (
            all_product_reference_image_urls[:1] if render_provider == "higgsfield" else all_product_reference_image_urls
        )
        reference_signature_parts = (
            product_reference_render_ids
            if product_reference_render_ids
            else [reference.local_asset_id for reference in product_reference_assets]
        )
        if not reference_signature_parts:
            reference_signature_parts = ["no_product_reference_assets"]
        product_reference_signature = _stable_idempotency_key(
            "swipe_product_references_v1",
            *reference_signature_parts,
        )
        rendered_prompt_template = _build_swipe_stage1_prompt_input(
            prompt_template=prompt_template,
            brand_name=str(client_name),
            angle=angle,
        )
        rendered_prompt_signature = _stable_idempotency_key(
            "swipe_prompt_input_v1",
            rendered_prompt_template,
        )

        product_prompt_image_bytes: bytes | None = None
        product_prompt_image_mime_type: str | None = None
        product_prompt_image_source_url: str | None = None
        product_prompt_image_sha256: str | None = None
        product_prompt_image_size_bytes: int | None = None
        if product_reference_image_urls:
            product_prompt_image_source_url = product_reference_image_urls[0]
            product_prompt_image_bytes, product_prompt_image_mime_type = _download_bytes(
                product_prompt_image_source_url,
                max_bytes=int(os.getenv("SWIPE_IMAGE_MAX_BYTES", str(18 * 1024 * 1024))),
                timeout_seconds=float(os.getenv("SWIPE_IMAGE_DOWNLOAD_TIMEOUT", "30")),
            )
            product_prompt_image_sha256 = hashlib.sha256(product_prompt_image_bytes).hexdigest()
            product_prompt_image_size_bytes = len(product_prompt_image_bytes)

        # The Gemini input must be only the rendered swipe prompt template plus the competitor image.
        # File Search attaches foundational documents as external context.
        (
            gemini_store_names,
            gemini_rag_doc_keys,
            gemini_rag_bundle_doc_keys,
            gemini_rag_document_names,
        ) = _resolve_swipe_stage1_gemini_file_search_context(
            session=session,
            org_id=org_id,
            idea_workspace_id=idea_workspace_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            funnel_id=funnel_id,
            asset_brief_artifact_id=brief_artifact_id,
        )
        swipe_copy_pack, swipe_copy_response, swipe_copy_model = _generate_swipe_stage1_copy_pack(
            session=session,
            brief=brief,
            requirement_index=requirement_index,
            requirement=requirement,
            copy_model=model_name,
            gemini_store_names=gemini_store_names,
            swipe_bytes=swipe_bytes,
            swipe_mime_type=swipe_mime_type,
            swipe_source_url=swipe_source_url,
            swipe_source_label=swipe_source_label,
            product_prompt_image_bytes=product_prompt_image_bytes,
            product_prompt_image_mime_type=product_prompt_image_mime_type,
        )
        swipe_copy_pack_payload = swipe_copy_pack.model_dump(mode="json", by_alias=True)
        swipe_copy_prompt_sha256 = hashlib.sha256(
            _build_swipe_copy_stage1_prompt(
                brief=brief,
                requirement_index=requirement_index,
                requirement=requirement,
                platform=swipe_copy_pack.platform,
                destination_type=swipe_copy_pack.destination_type,
                swipe_asset_type=_resolve_swipe_copy_asset_type(mime_type=swipe_mime_type),
                swipe_mime_type=swipe_mime_type,
                swipe_source_label=swipe_source_label,
                swipe_source_url=swipe_source_url,
                forbidden_terms=sorted(
                    {
                        *_GLOBAL_BLIND_ANGLE_REVEAL_TERMS,
                        *_collect_blind_angle_forbidden_terms(
                            requirement.get("angle") if isinstance(requirement.get("angle"), str) else None,
                            requirement.get("hook") if isinstance(requirement.get("hook"), str) else None,
                        ),
                    },
                    key=lambda item: (-len(item), item),
                ),
            ).encode("utf-8")
        ).hexdigest()
        swipe_copy_inputs = {
            "platform": swipe_copy_pack.platform,
            "adImageOrVideo": {
                "assetType": _resolve_swipe_copy_asset_type(mime_type=swipe_mime_type),
                "sourceLabel": swipe_source_label,
                "sourceUrl": swipe_source_url,
                "mimeType": swipe_mime_type,
            },
            "angleUsed": requirement.get("angle"),
            "destinationPage": swipe_copy_pack.destination_type,
        }

        # Run Gemini vision with File Search context to generate the generation-ready image prompt.
        gemini_client = _ensure_gemini_client()
        generation_config = {
            "temperature": 0.2,
            "max_output_tokens": max_output_tokens,
            "stores_attached": len(gemini_store_names),
            "product_reference_images_attached": 1 if product_prompt_image_bytes is not None else 0,
        }
        contents: List[Any] = [
            rendered_prompt_template,
            genai_types.Part.from_bytes(data=swipe_bytes, mime_type=swipe_mime_type),
        ]
        if product_prompt_image_bytes is not None and product_prompt_image_mime_type is not None:
            contents.append(
                genai_types.Part.from_bytes(data=product_prompt_image_bytes, mime_type=product_prompt_image_mime_type)
            )
        generate_config = genai_types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=max_output_tokens,
            tools=[
                genai_types.Tool(
                    file_search=genai_types.FileSearch(file_search_store_names=gemini_store_names)
                )
            ],
        )

        trace_context = LangfuseTraceContext(
            name="workflow.swipe_image_ad",
            session_id=workflow_run_id or asset_brief_id,
            metadata={
                "orgId": org_id,
                "clientId": client_id,
                "campaignId": campaign_id,
                "productId": product_id,
                "ideaWorkspaceId": idea_workspace_id,
                "assetBriefId": asset_brief_id,
                "workflowRunId": workflow_run_id,
                "model": model_name,
                "storesAttached": len(gemini_store_names),
                "requirementIndex": requirement_index,
            },
            tags=["workflow", "swipe_image_ad", "gemini", "file_search"],
        )
        with bind_langfuse_trace_context(trace_context):
            with start_langfuse_generation(
                name="llm.gemini.swipe_prompt",
                model=model_name,
                input={"asset_brief_id": asset_brief_id, "prompt_sha256": prompt_sha},
                metadata={
                    "channel": channel_id,
                    "format": fmt,
                    "companySwipeId": company_swipe_id,
                    "swipeSourceUrl": swipe_source_url,
                    "storesAttached": len(gemini_store_names),
                },
                model_parameters=generation_config,
                tags=["workflow", "swipe_image_ad", "gemini", "file_search"],
                trace_name="workflow.swipe_image_ad",
            ) as generation:
                try:
                    result = _call_gemini_generate_content_with_retries(
                        gemini_client=gemini_client,
                        model=model_name,
                        contents=contents,
                        config=generate_config,
                        operation_name="Swipe prompt generation",
                        file_search_model_error_message=(
                            "Swipe prompt generation model does not support Gemini File Search. "
                            f"model={model_name}. Choose a Gemini model with File Search support for this workflow."
                        ),
                    )
                    raw_output = _extract_gemini_text(result)
                    if not raw_output:
                        raise RuntimeError("Gemini returned no text for swipe prompt generation")
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(
                        "Swipe prompt generation failed with Gemini File Search context: "
                        f"{exc}"
                    ) from exc
                if generation is not None:
                    generation.update(
                        output=raw_output,
                        usage_details=_extract_gemini_usage_details(result),
                    )

        extracted_image_prompt_raw: str | None = None
        inlined_placeholder_map: Dict[str, str] = {}
        try:
            extracted_image_prompt_raw = extract_new_image_prompt_from_markdown(raw_output)
            image_prompt, inlined_placeholder_map = inline_swipe_render_placeholders(extracted_image_prompt_raw)
        except SwipePromptParseError as exc:
            raise RuntimeError(f"Failed to parse swipe prompt output: {exc}") from exc

        idempotency_key = _stable_idempotency_key(
            org_id,
            client_id,
            str(campaign_id or ""),
            asset_brief_id,
            "swipe_image_ad_v2",
            str(requirement_index),
            str(company_swipe_id or swipe_source_url or ""),
            aspect_ratio,
            str(render_count),
            render_provider,
            model_name,
            str(render_model_id or ""),
            prompt_sha,
            rendered_prompt_signature,
            product_reference_signature,
        )

        completed_job: Any | None = None
        last_render_error: str | None = None
        for attempt in range(1, render_max_attempts + 1):
            attempt_idempotency_key = (
                idempotency_key if attempt == 1 else _stable_idempotency_key(idempotency_key, f"attempt:{attempt}")
            )
            image_payload = CreativeServiceImageAdsCreateIn(
                prompt=image_prompt,
                reference_asset_ids=product_reference_render_ids,
                reference_image_urls=(
                    product_reference_image_urls if render_provider == "higgsfield" else []
                ),
                count=render_count,
                aspect_ratio=aspect_ratio,
                model_id=render_model_id,
                client_request_id=attempt_idempotency_key,
            )

            try:
                created_job = render_client.create_image_ads(
                    payload=image_payload,
                    idempotency_key=attempt_idempotency_key,
                )
            except (CreativeServiceRequestError, RuntimeError) as exc:
                last_render_error = f"Image ad generation request failed: {exc}"
                if attempt < render_max_attempts and _is_retryable_render_failure(last_render_error):
                    continue
                raise RuntimeError(last_render_error) from exc

            completed_job = _poll_image_job(
                creative_client=render_client,
                job_id=created_job.id,
                initial_job=created_job,
            )
            if completed_job.status == "succeeded":
                break

            last_render_error = completed_job.error_detail or "unknown error"
            if attempt < render_max_attempts and _is_retryable_render_failure(last_render_error):
                continue
            raise RuntimeError(f"Image generation failed (job_id={completed_job.id}): {last_render_error}")

        if completed_job is None or completed_job.status != "succeeded":
            raise RuntimeError(
                "Image generation failed after retry attempts. "
                f"attempts={render_max_attempts} error={last_render_error or 'unknown error'}"
            )

        if len(completed_job.outputs) < count:
            raise RuntimeError(
                "Image generation returned fewer outputs than requested. "
                f"requested={count} returned={len(completed_job.outputs)}"
            )

        retention_expires_at = _retention_expires_at()
        created_asset_ids: List[str] = []

        for local_index, output in enumerate(completed_job.outputs[:count]):
            if not output.primary_url:
                raise RuntimeError(
                    f"Image generation output missing primary_url (job_id={completed_job.id}, output_index={local_index})"
                )

            extra_ai_metadata: Dict[str, Any] = {
                "remoteJobId": completed_job.id,
                "remoteOutputIndex": output.output_index,
                "remoteAssetId": output.asset_id,
                "promptUsed": output.prompt_used,
                "swipeCompanyId": company_swipe_id,
                "swipeSourceUrl": swipe_source_url,
                "swipePromptModel": model_name,
                "swipeRenderModelIdRequested": requested_render_model_id,
                "swipeRenderModelIdUsed": getattr(completed_job, "model_id", None) or render_model_id,
                "swipeRenderProvider": render_provider,
                "swipeCopyPack": swipe_copy_pack_payload,
                "swipeCopyModel": swipe_copy_model,
                "swipeCopyRequestId": swipe_copy_response.get("request_id"),
                "swipeCopyStopReason": swipe_copy_response.get("stop_reason"),
                "swipeCopyOutputTokens": swipe_copy_response.get("output_tokens"),
                "swipeCopyPromptSha256": swipe_copy_prompt_sha256,
                "swipeCopyInputs": swipe_copy_inputs,
                "swipeCopyGeminiStoreNames": gemini_store_names,
                "swipeGeminiStoreNames": gemini_store_names,
                "swipeGeminiRagDocKeys": gemini_rag_doc_keys,
                "swipeGeminiRagBundleDocKeys": gemini_rag_bundle_doc_keys,
                "swipeGeminiRagDocumentNames": gemini_rag_document_names,
                "swipePromptTemplateKey": "prompts/swipe/swipe_to_image_ad.md",
                "swipePromptTemplateSha256": prompt_sha,
                "swipePromptInputText": rendered_prompt_template,
                "swipePromptImageAttached": True,
                "swipePromptImageSourceUrl": swipe_source_url,
                "swipeSourceFilename": swipe_source_filename,
                "swipePromptImageMimeType": swipe_mime_type,
                "swipePromptImageSizeBytes": swipe_image_size_bytes,
                "swipePromptImageSha256": swipe_image_sha256,
                "swipeRequiresProductImage": resolved_swipe_requires_product_image,
                "swipeRequiresProductImagePolicySource": swipe_product_image_policy_source,
                "swipePromptProductImageAttached": product_prompt_image_bytes is not None,
                "swipePromptProductImageSourceUrl": product_prompt_image_source_url,
                "swipePromptProductImageMimeType": product_prompt_image_mime_type,
                "swipePromptProductImageSizeBytes": product_prompt_image_size_bytes,
                "swipePromptProductImageSha256": product_prompt_image_sha256,
                "swipePromptMarkdownSha256": hashlib.sha256(raw_output.encode("utf-8")).hexdigest(),
                "swipePromptMarkdown": raw_output,
                "swipePromptMarkdownPreview": raw_output[:4000],
                "swipePromptExtractedRaw": extracted_image_prompt_raw,
                "swipePromptInlinedPlaceholderMap": inlined_placeholder_map,
                "swipeProductReferenceRenderAssetIds": product_reference_render_ids,
                "swipeProductReferenceLocalAssetIds": [
                    reference.local_asset_id for reference in product_reference_assets
                ],
                "swipeProductReferenceTitles": [
                    reference.title for reference in product_reference_assets if isinstance(reference.title, str)
                ],
                "swipeProductReferenceImageUrlsSelected": product_reference_image_urls,
                "swipeProductReferenceImageUrlsAvailable": all_product_reference_image_urls,
                "swipeRenderReferenceImageUrlsUsed": [
                    ref.primary_url
                    for ref in (getattr(completed_job, "references", []) or [])
                    if isinstance(ref.primary_url, str) and ref.primary_url.strip()
                ],
            }
            if creative_generation_batch_id:
                extra_ai_metadata["creativeGenerationBatchId"] = creative_generation_batch_id
            if creative_generation_plan_artifact_id:
                extra_ai_metadata["creativeGenerationPlanArtifactId"] = creative_generation_plan_artifact_id
            if creative_generation_plan_item_id:
                extra_ai_metadata["creativeGenerationPlanItemId"] = creative_generation_plan_item_id
            if ad_copy_pack_artifact_id:
                extra_ai_metadata["adCopyPackArtifactId"] = ad_copy_pack_artifact_id
            if ad_copy_pack_id:
                extra_ai_metadata["adCopyPackId"] = ad_copy_pack_id

            local_asset_id = _create_generated_asset_from_url(
                session=session,
                org_id=org_id,
                client_id=client_id,
                campaign_id=campaign_id,
                product_id=product_id,
                funnel_id=funnel_id,
                brief_artifact_id=brief_artifact_id,
                asset_brief_id=asset_brief_id,
                variant_id=brief.get("variantId") or brief.get("variant_id"),
                variant_index=None,
                channel_id=channel_id,
                fmt=fmt,
                requirement_index=requirement_index,
                requirement=requirement,
                primary_url=output.primary_url,
                prompt=image_prompt,
                source_kind="swipe_adaptation",
                expected_asset_kind="image",
                retention_expires_at=retention_expires_at,
                extra_ai_metadata=extra_ai_metadata,
                attach_to_product=True,
            )
            created_asset_ids.append(local_asset_id)

        log_activity(
            "swipe_image_ad",
            "succeeded",
            payload_out={
                "asset_ids": created_asset_ids,
                "job_id": completed_job.id,
                "swipe_prompt_model": model_name,
                "swipe_render_model_id": getattr(completed_job, "model_id", None) or render_model_id,
                "swipe_render_provider": render_provider,
                "prompt_template_sha256": prompt_sha,
                "stores_attached": len(gemini_store_names),
                "gemini_rag_doc_keys": gemini_rag_doc_keys,
                "gemini_rag_bundle_doc_keys": gemini_rag_bundle_doc_keys,
            },
        )

        return {
            "asset_ids": created_asset_ids,
            "job_id": completed_job.id,
            "image_prompt": image_prompt,
            "swipe_prompt_markdown": raw_output,
            "swipe_prompt_model": model_name,
            "swipe_render_model_id": getattr(completed_job, "model_id", None) or render_model_id,
            "swipe_render_provider": render_provider,
            "swipe_copy_pack": swipe_copy_pack_payload,
            "swipe_copy_model": swipe_copy_model,
            "stores_attached": len(gemini_store_names),
            "gemini_rag_doc_keys": gemini_rag_doc_keys,
            "gemini_rag_bundle_doc_keys": gemini_rag_bundle_doc_keys,
            "gemini_rag_document_names": gemini_rag_document_names,
            "prompt_template_sha256": prompt_sha,
        }
