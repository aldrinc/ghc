from __future__ import annotations

from copy import deepcopy
from typing import Any

DEFAULT_META_PUBLISH_CAMPAIGN_DAILY_BUDGET_MINOR_UNITS = 10000
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
