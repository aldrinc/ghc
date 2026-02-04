from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.db.enums import MediaAssetTypeEnum

FINGERPRINT_ALGO = "adcopy+media-sha256-set-v1"
_TRACKING_PARAMS = {"fbclid", "gclid", "ttclid"}
_TRACKING_PREFIXES = ("utm_",)


@dataclass
class MediaAssetInput:
    id: Optional[str]
    asset_type: MediaAssetTypeEnum
    role: Optional[str] = None
    sha256: Optional[str] = None
    storage_key: Optional[str] = None
    preview_storage_key: Optional[str] = None
    stored_url: Optional[str] = None
    source_url: Optional[str] = None
    size_bytes: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None


@dataclass
class CreativeFingerprintResult:
    creative_fingerprint: str
    media_fingerprint: Optional[str]
    copy_fingerprint: Optional[str]
    media_tokens: list[str]
    copy_tokens: list[str]
    primary_media_asset_id: Optional[str]
    fingerprint_algo: str = FINGERPRINT_ALGO


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonicalize_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value)).strip()
    text = re.sub(r"\s+", " ", text)
    text = text.lower()
    return text or None


def canonicalize_url_for_copy(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    candidate = url.strip()
    if not candidate:
        return None
    parsed = urlparse(candidate if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", candidate) else f"https://{candidate}")

    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    path = parsed.path or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    query_pairs = []
    for key, val in parse_qsl(parsed.query, keep_blank_values=False):
        key_lower = key.lower()
        if key_lower in _TRACKING_PARAMS or any(key_lower.startswith(prefix) for prefix in _TRACKING_PREFIXES):
            continue
        query_pairs.append((key, val))
    query = urlencode(query_pairs, doseq=True)
    return urlunparse((scheme, netloc, path, "", query, ""))


def _build_media_tokens(assets: Sequence[MediaAssetInput]) -> tuple[list[str], Optional[str], Optional[str]]:
    tokens: set[str] = set()
    primary_media_id: Optional[str] = None
    best_image_score: int = -1

    for asset in assets:
        stable_id = (
            asset.sha256
            or asset.storage_key
            or asset.preview_storage_key
            or asset.stored_url
            or asset.source_url
        )
        if not stable_id:
            continue
        role = asset.role or "UNKNOWN"
        asset_type = asset.asset_type.value if isinstance(asset.asset_type, MediaAssetTypeEnum) else str(asset.asset_type)
        token = f"{role}:{asset_type}:{stable_id}"
        tokens.add(token)

        if primary_media_id:
            continue
        if asset_type == MediaAssetTypeEnum.VIDEO.value:
            primary_media_id = asset.id
            continue
        if asset_type == MediaAssetTypeEnum.IMAGE.value:
            score = 0
            if asset.width and asset.height:
                score = asset.width * asset.height
            elif asset.size_bytes:
                score = asset.size_bytes
            if score > best_image_score:
                best_image_score = score
                primary_media_id = asset.id

    media_tokens = sorted(tokens)
    media_fingerprint = _sha256("|".join(media_tokens)) if media_tokens else None
    return media_tokens, media_fingerprint, primary_media_id


def _build_copy_tokens(copy_fields: dict[str, Optional[str]]) -> tuple[list[str], Optional[str]]:
    tokens: set[str] = set()

    field_map = {
        "primary_text": copy_fields.get("primary_text"),
        "headline": copy_fields.get("headline"),
        "description": copy_fields.get("description"),
    }
    for key, raw in field_map.items():
        norm = canonicalize_text(raw)
        if norm:
            tokens.add(f"copy:{key}:{_sha256(norm)}")

    cta = canonicalize_text(copy_fields.get("cta_label") or copy_fields.get("cta_type"))
    if cta:
        tokens.add(f"cta:{cta}")

    dest_url = canonicalize_url_for_copy(copy_fields.get("destination_url"))
    if dest_url:
        tokens.add(f"dest:{_sha256(dest_url)}")

    if not tokens:
        tokens.add("copy:none")

    copy_tokens = sorted(tokens)
    copy_fingerprint = _sha256("|".join(copy_tokens)) if copy_tokens else None
    return copy_tokens, copy_fingerprint


def compute_creative_fingerprint(
    *,
    copy_fields: dict[str, Optional[str]],
    assets: Sequence[MediaAssetInput],
) -> CreativeFingerprintResult:
    media_tokens, media_fingerprint, primary_media_asset_id = _build_media_tokens(assets)
    copy_tokens, copy_fingerprint = _build_copy_tokens(copy_fields)

    token_union = sorted(set(media_tokens).union(copy_tokens))
    creative_fingerprint = _sha256("|".join(token_union)) if token_union else _sha256("empty")

    return CreativeFingerprintResult(
        creative_fingerprint=creative_fingerprint,
        media_fingerprint=media_fingerprint,
        copy_fingerprint=copy_fingerprint,
        media_tokens=media_tokens,
        copy_tokens=copy_tokens,
        primary_media_asset_id=primary_media_asset_id,
        fingerprint_algo=FINGERPRINT_ALGO,
    )
