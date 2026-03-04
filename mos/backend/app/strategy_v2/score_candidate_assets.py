from __future__ import annotations

import math
import re
from typing import Any
from urllib.parse import urlparse


_CANDIDATE_REQUIRED_FIELDS = ("candidate_id", "source_ref", "competitor_name", "platform")

_DURABILITY_WEIGHT = 0.30
_DISTRIBUTION_WEIGHT = 0.20
_ENGAGEMENT_WEIGHT = 0.20
_PROOF_WEIGHT = 0.15
_EXECUTION_WEIGHT = 0.15

_RUNNING_DURATION_SCORE = {
    "UNDER_30D": 0.45,
    "30_TO_90D": 0.75,
    "OVER_90D": 1.0,
    "UNKNOWN": 0.30,
}

_ESTIMATED_SPEND_TIER_SCORE = {
    "LOW": 0.45,
    "MEDIUM": 0.70,
    "HIGH": 0.95,
    "UNKNOWN": 0.25,
}

_PROOF_TYPE_SCORE = {
    "NONE": 0.10,
    "TESTIMONIAL": 0.75,
    "STUDY": 0.90,
    "AUTHORITY": 0.80,
    "DEMONSTRATION": 0.85,
    "SOCIAL_PROOF": 0.70,
}

_EXECUTION_SCORE = {
    "VIDEO": 1.00,
    "IMAGE": 0.80,
    "PAGE": 0.90,
    "TEXT": 0.60,
}

_PLATFORM_FROM_DOMAIN = {
    "facebook.com": "META",
    "instagram.com": "INSTAGRAM",
    "tiktok.com": "TIKTOK",
    "youtube.com": "YOUTUBE",
    "youtu.be": "YOUTUBE",
    "reddit.com": "REDDIT",
}


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _as_upper(value: Any, default: str) -> str:
    text = str(value or "").strip().upper()
    return text or default


def _coerce_non_negative_float(value: Any) -> float:
    if isinstance(value, (int, float)):
        return max(float(value), 0.0)
    if isinstance(value, str) and value.strip():
        try:
            return max(float(value.strip()), 0.0)
        except Exception:
            return 0.0
    return 0.0


def _domain_from_ref(source_ref: str) -> str:
    parsed = urlparse(source_ref)
    host = parsed.netloc.strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def normalize_source_ref(raw_ref: Any) -> str:
    if not isinstance(raw_ref, str):
        return ""
    candidate = raw_ref.strip()
    if not candidate:
        return ""
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        return ""
    if not parsed.netloc:
        return ""
    return candidate.rstrip("/")


def derive_competitor_name_from_ref(source_ref: str) -> str:
    domain = _domain_from_ref(source_ref)
    if not domain:
        return "Unknown Competitor"
    labels = [part for part in domain.split(".") if part]
    if not labels:
        return "Unknown Competitor"
    base = labels[0]
    if base in {"offer", "shop", "get", "go", "buy", "app", "www"} and len(labels) > 1:
        base = labels[1]
    words = [word.capitalize() for word in re.split(r"[-_]", base) if word]
    return " ".join(words) if words else "Unknown Competitor"


def derive_platform_from_ref(source_ref: str) -> str:
    domain = _domain_from_ref(source_ref)
    for known_domain, platform in _PLATFORM_FROM_DOMAIN.items():
        if domain == known_domain or domain.endswith(f".{known_domain}"):
            return platform
    return "WEB"


def build_url_candidates(source_refs: list[str]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_refs: set[str] = set()
    for raw_ref in source_refs:
        source_ref = normalize_source_ref(raw_ref)
        if not source_ref or source_ref in seen_refs:
            continue
        seen_refs.add(source_ref)
        platform = derive_platform_from_ref(source_ref)
        asset_kind = "VIDEO" if platform in {"TIKTOK", "YOUTUBE", "INSTAGRAM"} else "PAGE"
        candidates.append(
            {
                "candidate_id": source_ref,
                "source_ref": source_ref,
                "source_type": "SOCIAL_VIDEO" if asset_kind == "VIDEO" else "LANDING_PAGE",
                "competitor_name": derive_competitor_name_from_ref(source_ref),
                "platform": platform,
                "asset_kind": asset_kind,
                "headline_or_caption": "",
                "metrics": {},
                "running_duration": "UNKNOWN",
                "estimated_spend_tier": "UNKNOWN",
                "proof_type": "NONE",
                "compliance_risk": "YELLOW",
            }
        )
    return candidates


def _durability_signal(candidate: dict[str, Any]) -> float:
    metrics = candidate.get("metrics")
    days_active = 0.0
    if isinstance(metrics, dict):
        days_active = _coerce_non_negative_float(metrics.get("days_active") or metrics.get("days_running"))
    if days_active > 0:
        return _clamp01(days_active / 120.0)
    running_duration = _as_upper(candidate.get("running_duration"), "UNKNOWN")
    return _RUNNING_DURATION_SCORE.get(running_duration, _RUNNING_DURATION_SCORE["UNKNOWN"])


def _distribution_signal(candidate: dict[str, Any]) -> float:
    spend_tier = _as_upper(candidate.get("estimated_spend_tier"), "UNKNOWN")
    base = _ESTIMATED_SPEND_TIER_SCORE.get(spend_tier, _ESTIMATED_SPEND_TIER_SCORE["UNKNOWN"])
    platform = _as_upper(candidate.get("platform"), "WEB")
    placement_bonus = 0.05 if platform in {"META", "TIKTOK", "INSTAGRAM", "YOUTUBE"} else 0.0
    return _clamp01(base + placement_bonus)


def _engagement_signal(candidate: dict[str, Any]) -> float:
    metrics = candidate.get("metrics")
    if not isinstance(metrics, dict):
        return 0.0

    views = _coerce_non_negative_float(metrics.get("views") or metrics.get("view_count"))
    followers = _coerce_non_negative_float(metrics.get("followers") or metrics.get("account_followers"))
    likes = _coerce_non_negative_float(metrics.get("likes") or metrics.get("like_count"))
    comments = _coerce_non_negative_float(metrics.get("comments") or metrics.get("comment_count"))
    shares = _coerce_non_negative_float(metrics.get("shares") or metrics.get("share_count"))

    if views <= 0 and followers <= 0 and likes <= 0 and comments <= 0 and shares <= 0:
        return 0.0

    weighted_interactions = likes + (2.0 * comments) + (3.0 * shares)
    denominator = max(views, 1.0)
    interaction_ratio = _clamp01((weighted_interactions / denominator) * 10.0)
    reach_signal = _clamp01(math.log10(1.0 + max(views, followers)) / 6.0)
    return _clamp01((0.6 * interaction_ratio) + (0.4 * reach_signal))


def _proof_signal(candidate: dict[str, Any]) -> float:
    proof_type = _as_upper(candidate.get("proof_type"), "NONE")
    return _PROOF_TYPE_SCORE.get(proof_type, _PROOF_TYPE_SCORE["NONE"])


def _execution_signal(candidate: dict[str, Any]) -> float:
    asset_kind = _as_upper(candidate.get("asset_kind"), "TEXT")
    return _EXECUTION_SCORE.get(asset_kind, 0.50)


def score_candidate_assets(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for candidate in candidates:
        hard_gate_flags: list[str] = []
        for field_name in _CANDIDATE_REQUIRED_FIELDS:
            value = candidate.get(field_name)
            if not isinstance(value, str) or not value.strip():
                hard_gate_flags.append(f"missing_{field_name}")

        compliance_risk = _as_upper(candidate.get("compliance_risk"), "YELLOW")
        if compliance_risk == "RED":
            hard_gate_flags.append("compliance_red")

        durability = _durability_signal(candidate)
        distribution = _distribution_signal(candidate)
        engagement = _engagement_signal(candidate)
        proof = _proof_signal(candidate)
        execution = _execution_signal(candidate)

        composite = (
            (_DURABILITY_WEIGHT * durability)
            + (_DISTRIBUTION_WEIGHT * distribution)
            + (_ENGAGEMENT_WEIGHT * engagement)
            + (_PROOF_WEIGHT * proof)
            + (_EXECUTION_WEIGHT * execution)
        )

        scored.append(
            {
                **candidate,
                "candidate_asset_score": round(_clamp01(composite) * 100.0, 2),
                "score_components": {
                    "durability_signal": round(durability, 4),
                    "distribution_signal": round(distribution, 4),
                    "engagement_signal": round(engagement, 4),
                    "proof_signal": round(proof, 4),
                    "execution_signal": round(execution, 4),
                },
                "hard_gate_flags": hard_gate_flags,
                "eligible": not hard_gate_flags,
            }
        )
    return scored


def select_top_candidates(
    scored_candidates: list[dict[str, Any]],
    *,
    max_candidates: int,
    max_per_competitor: int,
    max_per_platform: int,
) -> list[dict[str, Any]]:
    if max_candidates <= 0:
        raise ValueError(f"max_candidates must be > 0, got {max_candidates}")
    if max_per_competitor <= 0:
        raise ValueError(f"max_per_competitor must be > 0, got {max_per_competitor}")
    if max_per_platform <= 0:
        raise ValueError(f"max_per_platform must be > 0, got {max_per_platform}")

    eligible_rows = [row for row in scored_candidates if bool(row.get("eligible"))]
    sorted_rows = sorted(
        eligible_rows,
        key=lambda row: (
            -float(row.get("candidate_asset_score") or 0.0),
            str(row.get("candidate_id") or ""),
        ),
    )

    selected: list[dict[str, Any]] = []
    per_competitor: dict[str, int] = {}
    per_platform: dict[str, int] = {}

    for row in sorted_rows:
        competitor = str(row.get("competitor_name") or "unknown")
        platform = str(row.get("platform") or "unknown")
        if per_competitor.get(competitor, 0) >= max_per_competitor:
            continue
        if per_platform.get(platform, 0) >= max_per_platform:
            continue
        selected.append(row)
        per_competitor[competitor] = per_competitor.get(competitor, 0) + 1
        per_platform[platform] = per_platform.get(platform, 0) + 1
        if len(selected) >= max_candidates:
            break

    return selected
