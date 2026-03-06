from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"\s+")

_PRODUCT_TYPE_ALIASES: dict[str, set[str]] = {
    "book": {
        "book",
        "books",
        "guidebook",
        "handbook",
        "physical book",
        "physical books",
        "print book",
        "printed book",
    },
    "digital": {
        "digital",
        "digital access",
        "digital download",
        "digital product",
        "download",
        "downloadable",
        "e book",
        "ebook",
        "e books",
        "ebooks",
        "pdf",
    },
    "supplement": {
        "herbal supplement",
        "herbal supplements",
        "supplement",
        "supplements",
        "vitamin",
        "vitamins",
    },
    "service": {
        "consulting",
        "coaching",
        "done for you",
        "service",
        "services",
    },
    "software": {
        "app",
        "application",
        "saas",
        "software",
        "tool",
        "tools",
    },
    "course": {
        "course",
        "courses",
        "training",
        "workshop",
    },
    "physical_product": {
        "consumer good",
        "consumer goods",
        "device",
        "devices",
        "hardware",
        "physical product",
        "physical products",
    },
    "other": {"other"},
}


def normalize_product_type_value(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()
    if not cleaned:
        return None
    cleaned = cleaned.replace("_", " ").replace("-", " ")
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned or None


def canonical_product_type(value: str | None) -> str | None:
    normalized = normalize_product_type_value(value)
    if not normalized:
        return None
    for canonical, aliases in _PRODUCT_TYPE_ALIASES.items():
        if normalized in aliases:
            return canonical
    return normalized


def product_type_matches(left: str | None, right: str | None) -> bool:
    left_canonical = canonical_product_type(left)
    right_canonical = canonical_product_type(right)
    if not left_canonical or not right_canonical:
        return False
    return left_canonical == right_canonical


def is_book_product_type(value: str | None) -> bool:
    return canonical_product_type(value) == "book"
