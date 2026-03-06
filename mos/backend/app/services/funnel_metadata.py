from __future__ import annotations

import html
import re
from typing import Any, Optional, TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Funnel, FunnelPage, Product
from app.services.design_systems import resolve_design_system_tokens

_WHITESPACE_RE = re.compile(r"\s+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MARKDOWN_RE = re.compile(r"[*_`~#]")
_GENERIC_PAGE_LABELS = {"home", "index", "landing", "main", "page", "sales"}
_IGNORED_KEYS = {
    "id",
    "src",
    "href",
    "alt",
    "prompt",
    "imageSource",
    "assetPublicId",
    "referenceAssetPublicId",
    "publicId",
    "targetPageId",
    "linkType",
    "icon",
    "iconSrc",
    "iconAlt",
    "label",
    "ariaLabel",
}
_TITLE_KEYS = ("headline", "title", "heading")
_DESCRIPTION_KEYS = ("subtitle", "subheadline", "description", "body", "text")


class PublicPageMetadata(TypedDict):
    title: str
    description: str
    lang: str
    brandName: Optional[str]


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = html.unescape(value)
    text = _HTML_TAG_RE.sub(" ", text)
    text = _MARKDOWN_RE.sub("", text)
    text = text.replace("\u00a0", " ")
    text = _WHITESPACE_RE.sub(" ", text).strip()
    if not text:
        return None
    return text


def _normalize_page_label(page_name: str | None, page_slug: str | None) -> str | None:
    raw = _clean_text(page_name) or _clean_text(page_slug)
    if not raw:
        return None
    label = re.sub(r"[-_]+", " ", raw)
    label = _WHITESPACE_RE.sub(" ", label).strip()
    if not label:
        return None
    titled = label.title()
    if label.casefold() in _GENERIC_PAGE_LABELS:
        return None
    return titled


def _truncate(text: str | None, limit: int) -> str | None:
    cleaned = _clean_text(text)
    if not cleaned:
        return None
    if len(cleaned) <= limit:
        return cleaned
    clipped = cleaned[: limit - 1].rstrip()
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0].rstrip()
    return f"{clipped}..."


def _is_placeholder_title(title: str | None) -> bool:
    cleaned = _clean_text(title)
    if not cleaned:
        return True
    normalized = cleaned.casefold()
    if "template" not in normalized:
        return False
    return any(token in normalized for token in ("pdp", "listicle", "page", "landing"))


def _is_placeholder_description(description: str | None) -> bool:
    cleaned = _clean_text(description)
    if not cleaned:
        return True
    normalized = cleaned.casefold()
    if "template" not in normalized:
        return False
    return "react + vite" in normalized or "recreate" in normalized or "layout" in normalized


def _iter_components(node: object) -> list[dict[str, Any]]:
    if not isinstance(node, list):
        return []
    return [item for item in node if isinstance(item, dict)]


def _extract_sales_pdp_copy(page_component: dict[str, Any]) -> tuple[str | None, str | None]:
    page_props = page_component.get("props")
    if not isinstance(page_props, dict):
        return None, None
    for block in _iter_components(page_props.get("content")):
        if block.get("type") != "SalesPdpHero":
            continue
        block_props = block.get("props")
        if not isinstance(block_props, dict):
            continue
        config = block_props.get("config")
        if not isinstance(config, dict):
            continue
        purchase = config.get("purchase")
        if not isinstance(purchase, dict):
            continue
        title = _clean_text(purchase.get("title"))
        benefit_texts = []
        for item in purchase.get("benefits") or []:
            if not isinstance(item, dict):
                continue
            benefit = _clean_text(item.get("text"))
            if benefit:
                benefit_texts.append(benefit)
        description = None
        if benefit_texts:
            description = _truncate(". ".join(benefit_texts[:2]), 160)
        return title, description
    return None, None


def _extract_pre_sales_copy(page_component: dict[str, Any]) -> tuple[str | None, str | None]:
    page_props = page_component.get("props")
    if not isinstance(page_props, dict):
        return None, None
    for block in _iter_components(page_props.get("content")):
        if block.get("type") != "PreSalesHero":
            continue
        block_props = block.get("props")
        if not isinstance(block_props, dict):
            continue
        config = block_props.get("config")
        if not isinstance(config, dict):
            continue
        hero = config.get("hero")
        if not isinstance(hero, dict):
            continue
        return _clean_text(hero.get("title")), _truncate(hero.get("subtitle"), 160)
    return None, None


def _find_first_text(node: object, keys: tuple[str, ...], *, exclude: set[str] | None = None) -> str | None:
    excluded = exclude or set()
    if isinstance(node, dict):
        for key in keys:
            text = _clean_text(node.get(key))
            if text and text.casefold() not in excluded:
                return text
        for key, value in node.items():
            if key in keys or key in _IGNORED_KEYS or key.endswith("Json"):
                continue
            found = _find_first_text(value, keys, exclude=excluded)
            if found:
                return found
        return None
    if isinstance(node, list):
        for item in node:
            found = _find_first_text(item, keys, exclude=excluded)
            if found:
                return found
    return None


def _extract_primary_copy(puck_data: dict[str, Any]) -> tuple[str | None, str | None]:
    for page_component in _iter_components(puck_data.get("content")):
        component_type = page_component.get("type")
        if component_type == "SalesPdpPage":
            title, description = _extract_sales_pdp_copy(page_component)
            if title or description:
                return title, description
        if component_type == "PreSalesPage":
            title, description = _extract_pre_sales_copy(page_component)
            if title or description:
                return title, description

    content = puck_data.get("content")
    title = _find_first_text(content, _TITLE_KEYS)
    description = _find_first_text(content, _DESCRIPTION_KEYS, exclude={title.casefold()} if title else set())
    return title, _truncate(description, 160)


def _derive_title(
    *,
    primary_title: str | None,
    brand_name: str | None,
    product_title: str | None,
    page_label: str | None,
) -> str:
    short_primary = _truncate(primary_title, 60)
    short_product = _truncate(product_title, 60)
    cleaned_brand = _clean_text(brand_name)

    if short_product:
        if cleaned_brand and cleaned_brand.casefold() not in short_product.casefold():
            return _truncate(f"{short_product} | {cleaned_brand}", 70) or short_product
        return short_product

    if short_primary:
        if cleaned_brand and cleaned_brand.casefold() not in short_primary.casefold():
            return _truncate(f"{short_primary} | {cleaned_brand}", 70) or short_primary
        return short_primary

    if cleaned_brand and page_label:
        return _truncate(f"{cleaned_brand} | {page_label}", 70) or cleaned_brand
    if cleaned_brand:
        return cleaned_brand
    if short_primary:
        return short_primary
    if short_product:
        return short_product
    if page_label:
        return page_label
    return "Funnel Page"


def _derive_description(
    *,
    primary_title: str | None,
    primary_description: str | None,
    brand_name: str | None,
    page_label: str | None,
) -> str:
    cleaned_title = _clean_text(primary_title)
    cleaned_description = _truncate(primary_description, 160)
    cleaned_brand = _clean_text(brand_name)

    if cleaned_title and cleaned_description and cleaned_description.casefold() not in cleaned_title.casefold():
        combined = _truncate(f"{cleaned_title}. {cleaned_description}", 160)
        if combined:
            return combined
    if cleaned_description:
        return cleaned_description
    if cleaned_title:
        return _truncate(cleaned_title, 160) or ""
    if cleaned_brand and page_label:
        return _truncate(f"{page_label} for {cleaned_brand}.", 160) or ""
    if cleaned_brand:
        return cleaned_brand
    return ""


def build_public_page_metadata(
    *,
    puck_data: dict[str, Any],
    page_name: str | None,
    page_slug: str | None,
    brand_name: str | None,
    product_title: str | None,
) -> PublicPageMetadata:
    root = puck_data.get("root")
    root_props = root.get("props") if isinstance(root, dict) else None
    explicit_title = _clean_text(root_props.get("title")) if isinstance(root_props, dict) else None
    explicit_description = _clean_text(root_props.get("description")) if isinstance(root_props, dict) else None
    explicit_lang = _clean_text(root_props.get("lang")) if isinstance(root_props, dict) else None

    primary_title, primary_description = _extract_primary_copy(puck_data)
    page_label = _normalize_page_label(page_name, page_slug)

    title = (
        explicit_title
        if explicit_title and not _is_placeholder_title(explicit_title)
        else _derive_title(
            primary_title=primary_title,
            brand_name=brand_name,
            product_title=product_title,
            page_label=page_label,
        )
    )
    description = (
        explicit_description
        if explicit_description and not _is_placeholder_description(explicit_description)
        else _derive_description(
            primary_title=primary_title,
            primary_description=primary_description,
            brand_name=brand_name,
            page_label=page_label,
        )
    )

    return {
        "title": title,
        "description": description,
        "lang": explicit_lang or "en",
        "brandName": _clean_text(brand_name),
    }


def normalize_public_page_metadata(
    *,
    puck_data: dict[str, Any],
    page_name: str | None,
    page_slug: str | None,
    brand_name: str | None,
    product_title: str | None,
) -> PublicPageMetadata:
    metadata = build_public_page_metadata(
        puck_data=puck_data,
        page_name=page_name,
        page_slug=page_slug,
        brand_name=brand_name,
        product_title=product_title,
    )
    root = puck_data.setdefault("root", {})
    if not isinstance(root, dict):
        raise ValueError("puckData.root must be an object.")
    root_props = root.setdefault("props", {})
    if not isinstance(root_props, dict):
        raise ValueError("puckData.root.props must be an object.")
    root_props["title"] = metadata["title"]
    root_props["description"] = metadata["description"]
    return metadata


def _resolve_brand_name(
    *,
    session: Session,
    org_id: str,
    funnel: Funnel,
    page: FunnelPage | None,
) -> str | None:
    tokens = resolve_design_system_tokens(
        session=session,
        org_id=org_id,
        client_id=str(funnel.client_id),
        funnel=funnel,
        page=page,
    )
    if not isinstance(tokens, dict):
        return None
    brand = tokens.get("brand")
    if not isinstance(brand, dict):
        return None
    return _clean_text(brand.get("name"))


def _resolve_product_title(session: Session, funnel: Funnel) -> str | None:
    if not funnel.product_id:
        return None
    return session.scalars(select(Product.title).where(Product.id == funnel.product_id)).first()


def build_public_page_metadata_for_context(
    *,
    session: Session,
    org_id: str,
    funnel: Funnel,
    page: FunnelPage | None,
    puck_data: dict[str, Any],
) -> PublicPageMetadata:
    return build_public_page_metadata(
        puck_data=puck_data,
        page_name=getattr(page, "name", None),
        page_slug=getattr(page, "slug", None),
        brand_name=_resolve_brand_name(session=session, org_id=org_id, funnel=funnel, page=page),
        product_title=_resolve_product_title(session=session, funnel=funnel),
    )


def normalize_public_page_metadata_for_context(
    *,
    session: Session,
    org_id: str,
    funnel: Funnel,
    page: FunnelPage | None,
    puck_data: dict[str, Any],
) -> PublicPageMetadata:
    return normalize_public_page_metadata(
        puck_data=puck_data,
        page_name=getattr(page, "name", None),
        page_slug=getattr(page, "slug", None),
        brand_name=_resolve_brand_name(session=session, org_id=org_id, funnel=funnel, page=page),
        product_title=_resolve_product_title(session=session, funnel=funnel),
    )
