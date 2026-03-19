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


def require_short_uuid_route_token(*, value: str | UUID | None, label: str) -> str:
    normalized_value = str(value).strip() if value is not None else ""
    if not normalized_value:
        raise ValueError(f"{label} route token cannot be resolved because {label.lower()} id is unavailable.")

    try:
        normalized_id = str(UUID(normalized_value))
    except ValueError as exc:
        raise ValueError(f"{label} '{normalized_value}' id is not a valid UUID.") from exc

    short_slug = normalized_id.split("-", 1)[0][:_SHORT_ID_LENGTH]
    if len(short_slug) != _SHORT_ID_LENGTH:
        raise ValueError(
            f"{label} '{normalized_id}' id cannot be converted to an {_SHORT_ID_LENGTH}-character route token."
        )
    return short_slug


def require_product_route_slug(*, product: Product) -> str:
    return require_short_uuid_route_token(value=product.id, label="Product")
