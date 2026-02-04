from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from app.db.enums import AdChannelEnum, AdStatusEnum, MediaAssetTypeEnum
from app.db.models import Ad, Brand, MediaAsset


def _coerce_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _extract_codes(raw_sources: Iterable[dict[str, Any]], keys: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    for source in raw_sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            raw_value = source.get(key)
            for item in _coerce_list(raw_value):
                if not isinstance(item, str):
                    continue
                code = item.strip()
                if not code:
                    continue
                # Normalize locale-like strings (en_US -> en, es-ES -> es)
                code = code.replace("-", "_")
                if "_" in code:
                    code = code.split("_", 1)[0]
                seen.add(code.upper())
    return sorted(seen)


def _guess_display_format(media_assets: Sequence[MediaAsset]) -> str | None:
    if not media_assets:
        return None
    videos = sum(1 for asset in media_assets if asset.asset_type == MediaAssetTypeEnum.VIDEO)
    images = sum(
        1
        for asset in media_assets
        if asset.asset_type in (MediaAssetTypeEnum.IMAGE, MediaAssetTypeEnum.SCREENSHOT)
    )
    if videos:
        return "video"
    if images > 1:
        return "carousel"
    if images == 1:
        return "image"
    return str(media_assets[0].asset_type.value or media_assets[0].asset_type).lower()


def _video_length_seconds(media_assets: Sequence[MediaAsset]) -> int | None:
    longest_ms: int | None = None
    for asset in media_assets:
        if asset.asset_type != MediaAssetTypeEnum.VIDEO:
            continue
        meta = getattr(asset, "metadata_json", {}) or {}
        candidates = [
            ("duration_ms", asset.duration_ms),
            ("duration_ms", meta.get("duration_ms")),
            ("duration", meta.get("duration")),
            ("length_ms", meta.get("length_ms")),
            ("length_seconds", meta.get("length_seconds")),
        ]
        for key, val in candidates:
            if val is None or not isinstance(val, (int, float)):
                continue
            if ("second" in key or key == "duration") and val > 0:
                ms = int(val * 1000)
            else:
                ms = int(val)
            longest_ms = max(longest_ms or 0, ms)
    if longest_ms:
        return max(int(longest_ms // 1000), 1)
    return None


def _days_active(ad: Ad) -> int | None:
    start_dt = ad.started_running_at or ad.first_seen_at
    end_dt = ad.ended_running_at or ad.last_seen_at
    if start_dt is None:
        return None
    if end_dt is None and ad.ad_status == AdStatusEnum.active:
        end_dt = datetime.now(timezone.utc)
    if end_dt is None:
        return None
    delta_days = (end_dt.date() - start_dt.date()).days + 1
    return max(delta_days, 1)


def build_ad_facts_payload(
    *,
    ad: Ad,
    brand: Brand,
    media_assets: Sequence[MediaAsset],
) -> dict[str, Any]:
    raw = ad.raw_json if isinstance(ad.raw_json, dict) else {}
    snapshot = raw.get("snapshot") if isinstance(raw.get("snapshot"), dict) else {}
    media_types = sorted({(asset.asset_type.value or str(asset.asset_type)).upper() for asset in media_assets})

    start_dt = ad.started_running_at or ad.first_seen_at
    start_date = start_dt.date() if start_dt else None

    channel_value = getattr(ad.channel, "value", ad.channel)
    status_value = getattr(ad.ad_status, "value", ad.ad_status)

    return {
        "ad_id": ad.id,
        "org_id": brand.org_id,
        "brand_id": ad.brand_id,
        "channel": channel_value if isinstance(channel_value, AdChannelEnum) else AdChannelEnum(channel_value),
        "status": status_value if isinstance(status_value, AdStatusEnum) else AdStatusEnum(status_value),
        "display_format": _guess_display_format(media_assets),
        "media_types": media_types,
        "video_length_seconds": _video_length_seconds(media_assets),
        "language_codes": _extract_codes([raw, snapshot], ["languages", "language", "locale"]),
        "country_codes": _extract_codes([raw, snapshot], ["countries", "country", "country_codes", "publisher_country"]),
        "start_date": start_date,
        "days_active": _days_active(ad),
    }
