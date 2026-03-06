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

from app.config import settings
from app.db.base import session_scope
from app.db.enums import ArtifactTypeEnum
from app.db.models import DesignSystem, Funnel, ProductOffer, ProductVariant
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.clients import ClientsRepository
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
    inline_swipe_render_placeholders,
    load_swipe_to_image_ad_prompt,
)

# Reuse existing asset generation helpers to keep asset storage consistent.
from app.temporal.activities.asset_activities import (  # noqa: E402
    _create_generated_asset_from_url,
    _ensure_remote_reference_asset_ids,
    _extract_brief,
    _retention_expires_at,
    _select_product_reference_assets,
    _stable_idempotency_key,
    _validate_brief_scope,
)


_GEMINI_CLIENT: Any | None = None
_SWIPE_PRODUCT_IMAGE_PROFILE_CACHE: Dict[str, bool] | None = None


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
      1) Use Gemini (vision) with the stage-1 prompt template + runtime brand/angle + attached RAG docs + the
         competitor swipe image to produce a dense, generation-ready image prompt.
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
                "swipeProductReferenceRemoteAssetIds": product_reference_remote_ids,
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
            "stores_attached": len(gemini_store_names),
            "gemini_rag_doc_keys": gemini_rag_doc_keys,
            "gemini_rag_bundle_doc_keys": gemini_rag_bundle_doc_keys,
            "gemini_rag_document_names": gemini_rag_document_names,
            "prompt_template_sha256": prompt_sha,
        }
