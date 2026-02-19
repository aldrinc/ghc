from __future__ import annotations

import re

from app.db.models import Product


_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def normalize_route_token(value: str) -> str:
    text = (value or "").strip().lower()
    text = _SLUG_PATTERN.sub("-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text


def require_product_route_slug(*, product: Product) -> str:
    handle = (product.handle or "").strip()
    if handle:
        handle_slug = normalize_route_token(handle)
        if handle_slug:
            return handle_slug

    product_id = str(product.id).strip() if product.id is not None else ""
    id_slug = normalize_route_token(product_id)
    if id_slug:
        return id_slug

    if handle:
        raise ValueError(
            f"Product '{product.id}' handle '{handle}' is invalid for routing and product id is unavailable."
        )
    raise ValueError(
        "Product route slug cannot be resolved because both product.handle and product.id are unavailable."
    )
