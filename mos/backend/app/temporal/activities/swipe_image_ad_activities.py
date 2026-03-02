from __future__ import annotations

import hashlib
import os
import re
import time
import json
from typing import Any, Dict, List, Tuple

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

from app.config import settings
from app.db.base import session_scope
from app.db.enums import ArtifactTypeEnum
from app.db.models import DesignSystem, Funnel, ProductOffer, ProductVariant
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.clients import ClientsRepository
from app.db.repositories.gemini_context_files import GeminiContextFilesRepository
from app.db.repositories.products import ProductsRepository
from app.db.repositories.swipes import CompanySwipesRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.observability import (
    LangfuseTraceContext,
    bind_langfuse_trace_context,
    start_langfuse_generation,
)
from app.schemas.creative_service import CreativeServiceImageAdsCreateIn
from app.services.creative_service_client import (
    CreativeServiceClient,
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
    load_swipe_to_image_ad_prompt,
)

# Reuse existing asset generation helpers to keep asset storage consistent.
from app.temporal.activities.asset_activities import (  # noqa: E402
    _build_image_reference_text,
    _create_generated_asset_from_url,
    _ensure_remote_reference_asset_ids,
    _extract_brief,
    _retention_expires_at,
    _select_product_reference_assets,
    _stable_idempotency_key,
    _validate_brief_scope,
)


_GEMINI_CLIENT: Any | None = None


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
    _GEMINI_CLIENT = genai.Client(api_key=api_key)
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


def _prompt_assets_value(*, product_reference_assets: List[Any], design_system_tokens: Dict[str, Any]) -> str:
    packshot_titles: List[str] = []
    for reference in product_reference_assets:
        title = getattr(reference, "title", None)
        if isinstance(title, str) and title.strip():
            packshot_titles.append(title.strip())

    has_logo = False
    if isinstance(design_system_tokens, dict):
        brand = design_system_tokens.get("brand")
        if isinstance(brand, dict):
            logo_public_id = brand.get("logoAssetPublicId")
            has_logo = isinstance(logo_public_id, str) and bool(logo_public_id.strip())

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


def _build_swipe_foundation_seed_doc(
    *,
    client_name: str,
    product_title: str,
    canon: dict[str, Any],
    design_system_tokens: dict[str, Any],
    swipe_context_block: str,
    offer_context_block: str,
) -> str:
    return "\n".join(
        [
            "# SWIPE FOUNDATION CONTEXT",
            f"Brand name: {client_name}",
            f"Product: {product_title}",
            "",
            "## CLIENT_CANON_JSON",
            "```json",
            json.dumps(canon, ensure_ascii=True, sort_keys=True),
            "```",
            "",
            "## DESIGN_SYSTEM_TOKENS_JSON",
            "```json",
            json.dumps(design_system_tokens, ensure_ascii=True, sort_keys=True),
            "```",
            "",
            "## SWIPE_CONTEXT_BLOCK",
            swipe_context_block,
            "",
            "## OFFER_CONTEXT_BLOCK",
            offer_context_block,
        ]
    ).strip()


def _resolve_gemini_file_search_store_names(
    *,
    session,
    org_id: str,
    idea_workspace_id: str,
    client_id: str,
    product_id: str,
    campaign_id: str | None,
    client_name: str,
    product_title: str,
    canon: dict[str, Any],
    design_system_tokens: dict[str, Any],
    swipe_context_block: str,
    offer_context_block: str,
) -> list[str]:
    if not is_gemini_file_search_enabled():
        raise RuntimeError(
            "Gemini File Search must be enabled for swipe image ad generation. "
            "Set GEMINI_FILE_SEARCH_ENABLED=true."
        )

    repo = GeminiContextFilesRepository(session)
    records = repo.list_for_workspace_or_client(
        org_id=org_id,
        idea_workspace_id=idea_workspace_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
    )
    store_names = sorted(
        {
            str(getattr(record, "gemini_store_name", "") or "").strip()
            for record in records
            if str(getattr(record, "gemini_store_name", "") or "").strip()
        }
    )
    if store_names:
        return store_names

    foundation_text = _build_swipe_foundation_seed_doc(
        client_name=client_name,
        product_title=product_title,
        canon=canon,
        design_system_tokens=design_system_tokens,
        swipe_context_block=swipe_context_block,
        offer_context_block=offer_context_block,
    )
    ensure_uploaded_to_gemini_file_search(
        org_id=org_id,
        idea_workspace_id=idea_workspace_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        doc_key="swipe_foundation_context",
        doc_title="Swipe Foundation Context",
        source_kind="swipe_foundation_context",
        step_key="swipe_image_ad",
        filename="swipe_foundation_context.md",
        mime_type="text/plain",
        content_bytes=foundation_text.encode("utf-8"),
        drive_doc_id=None,
        drive_url=None,
    )

    session.expire_all()
    seeded_records = repo.list_for_workspace_or_client(
        org_id=org_id,
        idea_workspace_id=idea_workspace_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
    )
    seeded_store_names = sorted(
        {
            str(getattr(record, "gemini_store_name", "") or "").strip()
            for record in seeded_records
            if str(getattr(record, "gemini_store_name", "") or "").strip()
        }
    )
    if seeded_store_names:
        return seeded_store_names

    raise RuntimeError(
        "No Gemini File Search stores are available for this workspace after seeding foundation context."
    )


def _poll_image_job(
    *,
    creative_client: Any,
    job_id: str,
) -> Any:
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
      1) Use Gemini (vision) with the swipe prompt template + brand/brief context + the competitor swipe image to
         produce a dense, generation-ready image prompt.
      2) Extract ONLY the prompt from the Gemini markdown output (```text fenced block).
      3) Send ONLY that extracted prompt to the creative service (Freestyle) to render the final image(s).
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
    requested_render_model_id = params.get("render_model_id") or os.getenv("SWIPE_IMAGE_RENDER_MODEL")
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

    render_provider = get_image_render_provider()
    log_activity(
        "swipe_image_ad",
        "started",
        payload_in={
            "asset_brief_id": asset_brief_id,
            "campaign_id": campaign_id,
            "company_swipe_id": company_swipe_id,
            "swipe_image_url": swipe_image_url,
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
        render_client = build_image_render_client()
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

        creative_concept_raw = brief.get("creativeConcept")
        if not isinstance(creative_concept_raw, str) or not creative_concept_raw.strip():
            raise ValueError("Asset brief is missing creativeConcept.")
        creative_concept = creative_concept_raw.strip()

        channel_id = (requirement.get("channel") or "meta").strip()
        fmt = (requirement.get("format") or "image").strip()
        angle = requirement.get("angle") if isinstance(requirement.get("angle"), str) else None
        hook = requirement.get("hook") if isinstance(requirement.get("hook"), str) else None
        constraints = [item for item in (brief.get("constraints") or []) if isinstance(item, str) and item.strip()]
        tone_guidelines = [
            item for item in (brief.get("toneGuidelines") or []) if isinstance(item, str) and item.strip()
        ]
        visual_guidelines = [
            item for item in (brief.get("visualGuidelines") or []) if isinstance(item, str) and item.strip()
        ]

        # Creative brief / brand context.
        brand_ctx = _extract_brand_context(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
        )
        client_name = brand_ctx.get("client_name") or ""
        product_title = brand_ctx.get("product_title") or ""
        canon = brand_ctx.get("canon") if isinstance(brand_ctx.get("canon"), dict) else {}
        tokens = (
            brand_ctx.get("design_system_tokens") if isinstance(brand_ctx.get("design_system_tokens"), dict) else {}
        )

        audience = _format_audience_from_canon(canon)
        brand_colors_fonts = _brand_colors_fonts_from_design_tokens(tokens)
        must_avoid_claims = _must_avoid_claims_from_canon(canon)

        offer_context_metadata = {
            "offerId": None,
            "offerName": None,
            "pricePoints": [],
        }

        # Product references are optional for this flow. If no product image exists, continue as text-to-image.
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
        product_reference_remote_ids: list[str] = []
        if render_provider == "creative_service" and product_reference_assets:
            try:
                reference_client = CreativeServiceClient()
            except CreativeServiceConfigError as exc:
                raise RuntimeError(str(exc)) from exc
            product_reference_remote_ids = _ensure_remote_reference_asset_ids(
                session=session,
                org_id=org_id,
                creative_client=reference_client,
                references=product_reference_assets,
            )
        image_reference_text = _build_image_reference_text(product_reference_assets) if product_reference_assets else ""
        all_product_reference_image_urls = [
            reference.primary_url
            for reference in product_reference_assets
            if isinstance(reference.primary_url, str) and reference.primary_url.strip()
        ]
        product_reference_image_urls = (
            all_product_reference_image_urls[:1] if render_provider == "higgsfield" else all_product_reference_image_urls
        )
        reference_signature_parts = (
            product_reference_remote_ids
            if product_reference_remote_ids
            else [reference.local_asset_id for reference in product_reference_assets]
        )
        if not reference_signature_parts:
            reference_signature_parts = ["no_product_reference_assets"]
        product_reference_signature = _stable_idempotency_key(
            "swipe_product_references_v1",
            *reference_signature_parts,
        )
        prompt_assets_value = _prompt_assets_value(
            product_reference_assets=product_reference_assets,
            design_system_tokens=tokens if isinstance(tokens, dict) else {},
        )
        rendered_prompt_template = _render_swipe_prompt_template(
            prompt_template=prompt_template,
            brand_name=str(client_name),
            product_name=str(product_title),
            audience=audience,
            angle_from_docs=angle,
            brand_colors_fonts=brand_colors_fonts,
            must_avoid_claims=must_avoid_claims,
            assets_value=prompt_assets_value,
        )
        if product_reference_image_urls:
            rendered_prompt_template = (
                f"{rendered_prompt_template}\n\n"
                "<product_packshot_image>\n"
                "Product packshot image is attached below as image input. Use it as the source of truth for "
                "product silhouette, proportions, and visible hardware details.\n"
                "</product_packshot_image>"
            )
        rendered_prompt_signature = _stable_idempotency_key(
            "swipe_prompt_input_v1",
            rendered_prompt_template,
        )

        # Swipe image bytes.
        swipe_bytes, swipe_mime_type, swipe_source_url = _resolve_swipe_image(
            session=session,
            org_id=org_id,
            company_swipe_id=company_swipe_id,
            swipe_image_url=swipe_image_url,
        )
        swipe_image_sha256 = hashlib.sha256(swipe_bytes).hexdigest()
        swipe_image_size_bytes = len(swipe_bytes)
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
        # File Search still attaches foundational stores as an external tool context.
        swipe_context_block = ""
        offer_context_block = ""
        gemini_store_names = _resolve_gemini_file_search_store_names(
            session=session,
            org_id=org_id,
            idea_workspace_id=idea_workspace_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            client_name=str(client_name),
            product_title=str(product_title),
            canon=canon if isinstance(canon, dict) else {},
            design_system_tokens=tokens if isinstance(tokens, dict) else {},
            swipe_context_block=swipe_context_block,
            offer_context_block=offer_context_block,
        )

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
                    result = gemini_client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=generate_config,
                    )
                    raw_output = _extract_gemini_text(result)
                    if not raw_output:
                        raise RuntimeError("Gemini returned no text for swipe prompt generation")
                except Exception as exc:  # noqa: BLE001
                    error_text = str(exc)
                    if "File search tool is not enabled for this model" in error_text:
                        raise RuntimeError(
                            "Swipe prompt generation model does not support Gemini File Search. "
                            f"model={model_name}. Choose a Gemini model with File Search support for this workflow."
                        ) from exc
                    raise RuntimeError(
                        "Swipe prompt generation failed with Gemini File Search context: "
                        f"{error_text}"
                    ) from exc
                if generation is not None:
                    generation.update(
                        output=raw_output,
                        usage_details=_extract_gemini_usage_details(result),
                    )

        try:
            image_prompt = extract_new_image_prompt_from_markdown(raw_output)
        except SwipePromptParseError as exc:
            raise RuntimeError(f"Failed to parse swipe prompt output: {exc}") from exc
        if re.search(r"\[PRODUCT(?::[^\]]*)?\]", image_prompt):
            raise RuntimeError(
                "Swipe prompt generation produced an unresolved [PRODUCT] placeholder. "
                "Expected the exact product name from context."
            )

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
                reference_text=image_reference_text,
                reference_asset_ids=product_reference_remote_ids,
                reference_image_urls=product_reference_image_urls,
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

            completed_job = _poll_image_job(creative_client=render_client, job_id=created_job.id)
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
                "swipeGeminiStoreNames": gemini_store_names,
                "swipePromptTemplateKey": "prompts/swipe/swipe_to_image_ad.md",
                "swipePromptTemplateSha256": prompt_sha,
                "swipePromptInputText": rendered_prompt_template,
                "swipePromptImageAttached": True,
                "swipePromptImageSourceUrl": swipe_source_url,
                "swipePromptImageMimeType": swipe_mime_type,
                "swipePromptImageSizeBytes": swipe_image_size_bytes,
                "swipePromptImageSha256": swipe_image_sha256,
                "swipePromptProductImageAttached": product_prompt_image_bytes is not None,
                "swipePromptProductImageSourceUrl": product_prompt_image_source_url,
                "swipePromptProductImageMimeType": product_prompt_image_mime_type,
                "swipePromptProductImageSizeBytes": product_prompt_image_size_bytes,
                "swipePromptProductImageSha256": product_prompt_image_sha256,
                "swipeOfferId": offer_context_metadata.get("offerId"),
                "swipeOfferName": offer_context_metadata.get("offerName"),
                "swipeOfferPricePoints": offer_context_metadata.get("pricePoints"),
                "swipePromptMarkdownSha256": hashlib.sha256(raw_output.encode("utf-8")).hexdigest(),
                "swipePromptMarkdown": raw_output,
                "swipePromptMarkdownPreview": raw_output[:4000],
                "swipeProductReferenceRemoteAssetIds": product_reference_remote_ids,
                "swipeProductReferenceLocalAssetIds": [
                    reference.local_asset_id for reference in product_reference_assets
                ],
                "swipeProductReferenceTitles": [
                    reference.title for reference in product_reference_assets if isinstance(reference.title, str)
                ],
                "swipeProductReferenceText": image_reference_text,
                "swipeProductReferenceImageUrlsSelected": product_reference_image_urls,
                "swipeProductReferenceImageUrlsAvailable": all_product_reference_image_urls,
                "swipeRenderReferenceImageUrlsUsed": [
                    ref.primary_url
                    for ref in (getattr(completed_job, "references", []) or [])
                    if isinstance(ref.primary_url, str) and ref.primary_url.strip()
                ],
            }

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
            "stores_attached": len(gemini_store_names),
            "prompt_template_sha256": prompt_sha,
        }
