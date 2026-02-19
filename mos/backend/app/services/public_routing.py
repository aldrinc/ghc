from __future__ import annotations

import re
from uuid import UUID

from app.db.models import Product


_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
_SHORT_ID_LENGTH = 8


def normalize_route_token(value: str) -> str:
    text = (value or "").strip().lower()
    text = _SLUG_PATTERN.sub("-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text


def require_product_route_slug(*, product: Product) -> str:
    product_id = str(product.id).strip() if product.id is not None else ""
    if not product_id:
        raise ValueError("Product route slug cannot be resolved because product.id is unavailable.")

    try:
        normalized_id = str(UUID(product_id))
    except ValueError as exc:
        raise ValueError(f"Product '{product_id}' id is not a valid UUID.") from exc

    short_slug = normalized_id.split("-", 1)[0][:_SHORT_ID_LENGTH]
    if len(short_slug) != _SHORT_ID_LENGTH:
        raise ValueError(
            f"Product '{normalized_id}' id cannot be converted to an {_SHORT_ID_LENGTH}-character route slug."
        )
    return short_slug
