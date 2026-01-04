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
