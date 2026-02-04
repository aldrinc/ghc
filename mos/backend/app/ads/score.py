from __future__ import annotations

from datetime import datetime, timezone
from math import exp, log1p
from typing import Any, Optional

from app.db.enums import AdStatusEnum
from app.db.models import Ad


def _safe_days_between(start: Optional[datetime], end: Optional[datetime]) -> Optional[int]:
    if not start or not end:
        return None
    return max((end.date() - start.date()).days + 1, 1)


def _normalize(val: float, cap: float) -> float:
    if cap <= 0:
        return 0.0
    return max(min(val / cap, 1.0), 0.0)


def compute_ad_score(
    *,
    ad: Ad,
    facts: dict[str, Any] | None,
    media_count: int,
    version: str = "v1",
) -> dict[str, Any]:
    facts = facts or {}
    now = datetime.now(timezone.utc)
    days_active = facts.get("days_active")
    if days_active is None:
        days_active = _safe_days_between(ad.started_running_at or ad.first_seen_at, ad.last_seen_at or now)

    days_since_last_seen = None
    if ad.last_seen_at:
        days_since_last_seen = max((now.date() - ad.last_seen_at.date()).days, 0)

    components: dict[str, dict[str, Any]] = {}
    weights = {
        "longevity": 0.35,
        "recency": 0.25,
        "media": 0.15,
        "status": 0.25,
    }

    longevity_val = _normalize(log1p(days_active or 0), log1p(90))
    components["longevity"] = {"value": longevity_val, "weight": weights["longevity"], "raw": {"days_active": days_active}}

    recency_val = 0.0
    if days_since_last_seen is not None:
        recency_val = exp(-days_since_last_seen / 21)
    components["recency"] = {
        "value": recency_val,
        "weight": weights["recency"],
        "raw": {"days_since_last_seen": days_since_last_seen},
    }

    media_val = 1.0 if media_count > 0 else 0.0
    components["media"] = {"value": media_val, "weight": weights["media"], "raw": {"media_count": media_count}}

    status = ad.ad_status if isinstance(ad.ad_status, AdStatusEnum) else AdStatusEnum(str(ad.ad_status))
    status_val = 1.0 if status == AdStatusEnum.active else 0.5 if status == AdStatusEnum.unknown else 0.25
    components["status"] = {"value": status_val, "weight": weights["status"], "raw": {"status": status.value}}

    weighted_sum = sum(c["value"] * c["weight"] for c in components.values())
    total_weight = sum(weights.values())
    score_0_1 = weighted_sum / total_weight if total_weight else 0.0

    performance_score = round(score_0_1 * 100)
    performance_stars = min(max(round(score_0_1 * 5), 1), 5)
    winning_score = round(score_0_1 * 5000)

    present = [c for c in components.values() if c["raw"].get("days_active") is not None or c["raw"].get("days_since_last_seen") is not None or c["raw"].get("media_count") is not None or c["raw"].get("status")]
    confidence = _normalize(len(present), len(components))

    return {
        "score_version": version,
        "performance_score": performance_score,
        "performance_stars": performance_stars,
        "winning_score": winning_score,
        "confidence": confidence,
        "score_breakdown": {"components": components},
    }
