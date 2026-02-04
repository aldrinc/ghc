from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse, urlunparse

_CORPORATE_SUFFIXES = {
    "inc",
    "inc.",
    "llc",
    "ltd",
    "ltd.",
    "co",
    "co.",
    "company",
    "corp",
    "corp.",
    "corporation",
    "gmbh",
    "plc",
    "sa",
    "bv",
}

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def normalize_brand_name(name: str) -> str:
    """Deterministic brand name normalization for matching/deduping."""
    value = (name or "").strip().lower()
    value = re.sub(r"[^\w\s]", " ", value).replace("_", " ")
    value = re.sub(r"\s+", " ", value).strip()
    parts = value.split(" ") if value else []
    if len(parts) > 1 and parts[-1] in _CORPORATE_SUFFIXES:
        parts = parts[:-1]
    return " ".join(parts)


def normalize_url(url: Optional[str]) -> Optional[str]:
    """Canonicalize URLs for deterministic comparison."""
    if not url:
        return None
    candidate = url.strip()
    if not candidate:
        return None
    if not _SCHEME_RE.match(candidate):
        candidate = f"https://{candidate}"

    try:
        parsed = urlparse(candidate)
    except Exception:
        return None

    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = re.sub(r"/{2,}", "/", path)
    if not path.startswith("/"):
        path = f"/{path}"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def derive_primary_domain(url: Optional[str]) -> Optional[str]:
    """Extract the primary domain (hostname without scheme or port)."""
    normalized = normalize_url(url)
    if not normalized:
        return None
    parsed = urlparse(normalized)
    hostname = parsed.hostname
    if not hostname:
        return None
    hostname = hostname.lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname


def normalize_facebook_page_url(url: Optional[str]) -> Optional[str]:
    """
    Canonicalize Facebook Page URLs for ingestion.

    Rules:
    - Require https and host facebook.com; normalize host to www.facebook.com.
    - Strip query params/fragments and collapse duplicate slashes.
    - Remove trailing slash.
    - Reject obvious non-page paths (ads library, groups, events, watch, reels, photos).
    """
    if not url:
        return None
    candidate = url.strip()
    if not candidate:
        return None
    if not _SCHEME_RE.match(candidate):
        candidate = f"https://{candidate}"
    try:
        parsed = urlparse(candidate)
    except Exception:
        return None

    host = (parsed.hostname or "").lower()
    if not host.endswith("facebook.com"):
        return None
    host = "www.facebook.com"

    path = parsed.path or ""
    path = re.sub(r"/{2,}", "/", path)
    invalid_tokens = (
        "/ads/library",
        "/groups/",
        "/events/",
        "/watch/",
        "/reel",
        "/reels",
        "/photo",
        "/photos",
    )
    path_lower = path.lower()
    for token in invalid_tokens:
        if token in path_lower:
            return None

    if path and not path.startswith("/"):
        path = f"/{path}"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    if not path or path == "/":
        return None

    return urlunparse(("https", host, path, "", "", ""))
