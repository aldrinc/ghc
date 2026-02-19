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
    raw = (product.handle or "").strip()
    if not raw:
        raise ValueError(
            f"Product '{product.id}' is missing handle. Set product.handle before publishing funnels."
        )
    slug = normalize_route_token(raw)
    if not slug:
        raise ValueError(
            f"Product '{product.id}' handle '{raw}' is invalid for routing. Use lowercase letters, numbers, and dashes."
        )
    return slug
