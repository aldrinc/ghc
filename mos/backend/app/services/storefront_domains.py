from __future__ import annotations

from urllib.parse import urlparse


LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}

MULTI_PART_PUBLIC_SUFFIXES = {
    "ac.uk",
    "co.jp",
    "co.nz",
    "co.uk",
    "com.au",
    "com.br",
    "com.mx",
    "gov.uk",
    "net.au",
    "org.au",
    "org.uk",
}


def _clean_optional_text(value: str | None) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def is_apex_hostname(hostname: str) -> bool:
    labels = [label for label in hostname.split(".") if label]
    if len(labels) < 2:
        return False
    if len(labels) == 2:
        return True
    return ".".join(labels[-2:]) in MULTI_PART_PUBLIC_SUFFIXES and len(labels) == 3


def resolve_shop_hosted_hostname(hostname: str | None) -> str | None:
    cleaned = _clean_optional_text(hostname)
    if not cleaned:
        return None

    normalized = cleaned.lower()
    if normalized.startswith("www."):
        normalized = normalized[4:]
    if normalized in LOCAL_HOSTNAMES or normalized.startswith("shop."):
        return normalized
    if not is_apex_hostname(normalized):
        return normalized
    return f"shop.{normalized}"


def resolve_shop_hosted_origin(value: str | None) -> str | None:
    cleaned = _clean_optional_text(value)
    if not cleaned:
        return None

    candidate = cleaned if "://" in cleaned else f"https://{cleaned}"
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None

    hostname = resolve_shop_hosted_hostname(parsed.hostname)
    if not hostname:
        return None
    return f"{parsed.scheme}://{hostname}"


def normalize_absolute_origin(value: str | None) -> str | None:
    cleaned = _clean_optional_text(value)
    if not cleaned:
        return None

    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"
