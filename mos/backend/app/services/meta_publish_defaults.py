from __future__ import annotations

from copy import deepcopy
from typing import Any

DEFAULT_META_PUBLISH_TEMPLATE_ID = "default-broad-int-cbo"
DEFAULT_META_PUBLISH_CAMPAIGN_DAILY_BUDGET_MINOR_UNITS = 10000
DEFAULT_META_PUBLISH_ADSET_DAILY_MIN_SPEND_TARGET_MINOR_UNITS = 1000
DEFAULT_META_PUBLISH_BUCKET_COUNT = 5
MAX_META_PUBLISH_BUCKET_COUNT = 8
DEFAULT_META_PUBLISH_BUCKET_STRATEGY = "deterministic_round_robin"
DEFAULT_META_PUBLISH_COUNTRIES = ("US", "CA", "GB", "AU")
DEFAULT_META_PUBLISH_TARGETING: dict[str, Any] = {
    "age_min": 18,
    "age_max": 65,
    "age_range": [18, 65],
    "geo_locations": {
        "countries": list(DEFAULT_META_PUBLISH_COUNTRIES),
        "location_types": ["home", "recent"],
    },
    "brand_safety_content_filter_levels": ["FACEBOOK_RELAXED"],
    "targeting_automation": {
        "advantage_audience": 1,
        "individual_setting": {
            "age": 1,
            "gender": 1,
        },
    },
}
DEFAULT_META_PUBLISH_ATTRIBUTION_SPEC: list[dict[str, Any]] = [
    {"event_type": "CLICK_THROUGH", "window_days": 7},
    {"event_type": "VIEW_THROUGH", "window_days": 1},
    {"event_type": "ENGAGED_VIDEO_VIEW", "window_days": 1},
]
DEFAULT_META_PUBLISH_OPTIMIZATION_GOAL = "OFFSITE_CONVERSIONS"
DEFAULT_META_PUBLISH_BILLING_EVENT = "IMPRESSIONS"


def default_meta_publish_targeting() -> dict[str, Any]:
    return deepcopy(DEFAULT_META_PUBLISH_TARGETING)


def default_meta_publish_attribution_spec() -> list[dict[str, Any]]:
    return deepcopy(DEFAULT_META_PUBLISH_ATTRIBUTION_SPEC)


def _coerce_bucket_index(value: Any) -> int | None:
    if isinstance(value, int):
        normalized = value
    elif isinstance(value, str) and value.strip().isdigit():
        normalized = int(value.strip())
    else:
        return None
    if normalized < 1 or normalized > MAX_META_PUBLISH_BUCKET_COUNT:
        return None
    return normalized


def read_default_meta_publish_bucket_index(metadata_json: Any) -> int | None:
    if not isinstance(metadata_json, dict):
        return None
    if metadata_json.get("templateId") != DEFAULT_META_PUBLISH_TEMPLATE_ID:
        return None
    bucket_count = metadata_json.get("bucketCount")
    if bucket_count is not None:
        if isinstance(bucket_count, str) and bucket_count.strip().isdigit():
            bucket_count = int(bucket_count.strip())
        if (
            not isinstance(bucket_count, int)
            or bucket_count < 1
            or bucket_count > MAX_META_PUBLISH_BUCKET_COUNT
        ):
            return None
    return _coerce_bucket_index(metadata_json.get("bucketIndex"))


def default_meta_publish_bucket_name(bucket_index: int) -> str:
    normalized = _coerce_bucket_index(bucket_index)
    if normalized is None:
        raise ValueError(f"bucket_index must be between 1 and {MAX_META_PUBLISH_BUCKET_COUNT}.")
    return f"CBO Bucket {normalized}"


def default_meta_publish_bucket_metadata(
    bucket_index: int,
    *,
    bucket_count: int = DEFAULT_META_PUBLISH_BUCKET_COUNT,
    base_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = _coerce_bucket_index(bucket_index)
    if normalized is None:
        raise ValueError(f"bucket_index must be between 1 and {MAX_META_PUBLISH_BUCKET_COUNT}.")
    if bucket_count < 1 or bucket_count > MAX_META_PUBLISH_BUCKET_COUNT:
        raise ValueError(f"bucket_count must be between 1 and {MAX_META_PUBLISH_BUCKET_COUNT}.")
    metadata = deepcopy(base_metadata) if isinstance(base_metadata, dict) else {}
    metadata["templateId"] = DEFAULT_META_PUBLISH_TEMPLATE_ID
    metadata["campaignDailyBudget"] = DEFAULT_META_PUBLISH_CAMPAIGN_DAILY_BUDGET_MINOR_UNITS
    metadata["bucketIndex"] = normalized
    metadata["bucketCount"] = bucket_count
    metadata["bucketStrategy"] = DEFAULT_META_PUBLISH_BUCKET_STRATEGY
    metadata.setdefault("attributionSpec", default_meta_publish_attribution_spec())
    return metadata
