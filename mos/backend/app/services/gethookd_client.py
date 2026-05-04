"""
GetHookd API client service.

Provides methods for authenticating and fetching ads from GetHookd Explore API.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GETHOOKD_API_BASE_URL = "https://app.gethookd.ai/api/v1"


class GetHookdClientError(RuntimeError):
    """Base exception for GetHookd client errors."""

    pass


class GetHookdAuthenticationError(GetHookdClientError):
    """Raised when authentication fails."""

    pass


class GetHookdRateLimitError(GetHookdClientError):
    """Raised when rate limit is hit."""

    pass


class GetHookdInsufficientCreditsError(GetHookdClientError):
    """Raised when there are insufficient credits."""

    pass


@dataclass
class GetHookdAdResult:
    """Normalized GetHookd ad result."""

    id: str
    external_id: Optional[str]
    platform: str
    display_format: Optional[str]
    ad_unit_format: Optional[str]
    title: Optional[str]
    body: Optional[str]
    cta_type: Optional[str]
    cta_text: Optional[str]
    landing_page: Optional[str]
    start_date: Optional[str]
    end_date: Optional[str]
    days_active: Optional[int]
    active_in_library: Optional[bool]
    used_count: Optional[int]
    performance_score: Optional[int]
    performance_score_title: Optional[str]
    share_url: Optional[str]
    ad_library_link: Optional[str]
    brand_id: Optional[str]
    brand_name: Optional[str]
    brand_logo_url: Optional[str]
    media: list[dict[str, Any]]
    raw_json: dict[str, Any]


@dataclass
class GetHookdExploreFilters:
    """Pass-through filters for GetHookd Explore API."""

    query: str = ""
    sort_column: Optional[str] = None
    sort_direction: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[str] = None
    ad_format: Optional[str] = None
    run_time: Optional[int] = None
    language: Optional[str] = None
    platform: Optional[str] = None
    niche: Optional[str] = None
    performance_scores: Optional[str] = None
    used_count: Optional[int] = None
    video_lengths: Optional[str] = None
    eu_transparency: Optional[int] = None
    eu_total_reach: Optional[int] = None
    gender_audience: Optional[str] = None
    age_audience: Optional[str] = None
    location: Optional[str] = None
    ad_spend_range: Optional[str] = None
    excluded_brands: Optional[str] = None
    creative_categories: Optional[str] = None
    cta_types: Optional[str] = None
    active_ads_count: Optional[int] = None
    ads_per_brand_limit: Optional[int] = None

    @classmethod
    def from_filter_dict(cls, filters: Mapping[str, Any] | None) -> "GetHookdExploreFilters":
        source = dict(filters or {})

        def read_text(primary: str, *aliases: str) -> Optional[str]:
            for key in (primary, *aliases):
                if key in source:
                    raw = source.get(key)
                    if raw is None:
                        return None
                    cleaned = str(raw).strip()
                    return cleaned or None
            return None

        def read_int(primary: str, *aliases: str) -> Optional[int]:
            raw_text = read_text(primary, *aliases)
            if raw_text is None:
                return None
            try:
                return int(raw_text)
            except ValueError as exc:
                raise GetHookdClientError(
                    f"Invalid GetHookd filter '{primary}': expected integer, got {raw_text!r}"
                ) from exc

        return cls(
            query=read_text("query") or "",
            sort_column=read_text("sort_column"),
            sort_direction=read_text("sort_direction"),
            start_date=read_text("start_date", "start-date"),
            end_date=read_text("end_date", "end-date"),
            status=read_text("status"),
            ad_format=read_text("ad_format", "ad-format"),
            run_time=read_int("run_time", "run-time"),
            language=read_text("language"),
            platform=read_text("platform", "platforms"),
            niche=read_text("niche"),
            performance_scores=read_text("performance_scores"),
            used_count=read_int("used_count"),
            video_lengths=read_text("video_lengths"),
            eu_transparency=read_int("eu_transparency"),
            eu_total_reach=read_int("eu_total_reach"),
            gender_audience=read_text("gender_audience"),
            age_audience=read_text("age_audience"),
            location=read_text("location"),
            ad_spend_range=read_text("ad_spend_range"),
            excluded_brands=read_text("excluded_brands"),
            creative_categories=read_text("creative_categories"),
            cta_types=read_text("cta_types"),
            active_ads_count=read_int("active_ads_count"),
            ads_per_brand_limit=read_int("ads_per_brand_limit"),
        )

    def to_query_params(self, *, page: int, per_page: int) -> dict[str, Any]:
        params: dict[str, Any] = {
            "page": page,
            "per_page": per_page,
        }

        text_fields = {
            "query": self.query,
            "sort_column": self.sort_column,
            "sort_direction": self.sort_direction,
            "start-date": self.start_date,
            "end-date": self.end_date,
            "status": self.status,
            "ad-format": self.ad_format,
            "language": self.language,
            "platform": self.platform,
            "niche": self.niche,
            "performance_scores": self.performance_scores,
            "video_lengths": self.video_lengths,
            "gender_audience": self.gender_audience,
            "age_audience": self.age_audience,
            "location": self.location,
            "ad_spend_range": self.ad_spend_range,
            "excluded_brands": self.excluded_brands,
            "creative_categories": self.creative_categories,
            "cta_types": self.cta_types,
        }
        for key, value in text_fields.items():
            if value is None:
                continue
            cleaned = str(value).strip()
            if cleaned:
                params[key] = cleaned

        int_fields = {
            "run-time": self.run_time,
            "used_count": self.used_count,
            "eu_transparency": self.eu_transparency,
            "eu_total_reach": self.eu_total_reach,
            "active_ads_count": self.active_ads_count,
            "ads_per_brand_limit": self.ads_per_brand_limit,
        }
        for key, value in int_fields.items():
            if value is not None:
                params[key] = int(value)

        return params


@dataclass
class GetHookdExplorePage:
    """A single GetHookd Explore page response."""

    items: list[GetHookdAdResult]
    raw_items_count: int
    current_page: Optional[int]
    last_page: Optional[int]
    total: Optional[int]
    next_url: Optional[str]
    previous_url: Optional[str]
    used_credits: float
    remaining_credits: Optional[float]
    sorting: dict[str, Any]
    filters: dict[str, Any]
    raw_payload: dict[str, Any]

    @property
    def has_next_page(self) -> bool:
        return bool(self.next_url) or (
            self.current_page is not None
            and self.last_page is not None
            and self.current_page < self.last_page
        )


class GetHookdClient:
    """Client for GetHookd Explore API."""

    def __init__(
        self,
        api_token: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.api_token = api_token or settings.GETHOOKD_API_KEY
        if not self.api_token:
            raise GetHookdClientError("API token is required")
        self.base_url = (
            base_url or settings.GETHOOKD_API_BASE_URL or GETHOOKD_API_BASE_URL
        ).rstrip("/")
        self.timeout_seconds = float(timeout_seconds or settings.GETHOOKD_TIMEOUT_SECONDS or 30.0)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    def validate_credentials(self) -> tuple[bool, Optional[str]]:
        """
        Validate credentials by making a test request.
        Returns (is_valid, error_message).
        """
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    f"{self.base_url}/authcheck",
                    headers=self._headers(),
                )
                if response.status_code == 401:
                    return False, "Invalid API token"
                elif response.status_code == 403:
                    return False, "Insufficient permissions (missing explore:read scope)"
                response.raise_for_status()
                payload = response.json()
                data = payload.get("data") if isinstance(payload, dict) else None
                if isinstance(data, dict) and data.get("authenticated") is True:
                    return True, None
                message = payload.get("message") if isinstance(payload, dict) else None
                if isinstance(message, str) and message.strip():
                    return False, message.strip()
                return False, "Credential validation failed"
        except httpx.TimeoutException:
            return False, "Request timed out"
        except httpx.HTTPError as exc:
            return False, f"HTTP error: {exc}"

    def explore(
        self,
        *,
        filters: GetHookdExploreFilters,
        page: int = 1,
        per_page: int = settings.GETHOOKD_EXPLORE_PAGE_SIZE,
    ) -> GetHookdExplorePage:
        """
        Fetch ads from GetHookd Explore API.
        """
        params = filters.to_query_params(page=page, per_page=per_page)

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(
                    f"{self.base_url}/explore",
                    headers=self._headers(),
                    params=params,
                )

                if response.status_code == 401:
                    raise GetHookdAuthenticationError("Invalid API token")
                elif response.status_code == 429:
                    raise GetHookdRateLimitError("Rate limit exceeded")
                elif response.status_code == 402:
                    raise GetHookdInsufficientCreditsError("Insufficient credits")

                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict) and payload.get("errors") is True:
                    message = payload.get("message")
                    raise GetHookdClientError(
                        str(message).strip()
                        if isinstance(message, str) and message.strip()
                        else "GetHookd returned an error"
                    )
                results = payload.get("data") if isinstance(payload, dict) else None
                if results is None:
                    return GetHookdExplorePage(
                        items=[],
                        raw_items_count=0,
                        current_page=None,
                        last_page=None,
                        total=None,
                        next_url=None,
                        previous_url=None,
                        used_credits=0.0,
                        remaining_credits=None,
                        sorting={},
                        filters={},
                        raw_payload=payload if isinstance(payload, dict) else {},
                    )
                if not isinstance(results, list):
                    raise GetHookdClientError(
                        "GetHookd explore response returned an invalid data payload"
                    )
                parsed = self._parse_results(results)
                meta = payload.get("meta") if isinstance(payload, dict) else None
                links = payload.get("links") if isinstance(payload, dict) else None
                sorting = payload.get("sorting") if isinstance(payload, dict) else None
                response_filters = payload.get("filters") if isinstance(payload, dict) else None
                return GetHookdExplorePage(
                    items=parsed,
                    raw_items_count=len(results),
                    current_page=_coerce_optional_int(meta.get("current_page"))
                    if isinstance(meta, dict)
                    else None,
                    last_page=_coerce_optional_int(meta.get("last_page"))
                    if isinstance(meta, dict)
                    else None,
                    total=_coerce_optional_int(meta.get("total")) if isinstance(meta, dict) else None,
                    next_url=str(links.get("next")).strip()
                    if isinstance(links, dict) and links.get("next")
                    else None,
                    previous_url=str(links.get("prev")).strip()
                    if isinstance(links, dict) and links.get("prev")
                    else None,
                    used_credits=_coerce_optional_float(
                        payload.get("used_credits") if isinstance(payload, dict) else None
                    )
                    or 0.0,
                    remaining_credits=_coerce_optional_float(
                        payload.get("remaining_credits") if isinstance(payload, dict) else None
                    ),
                    sorting=sorting if isinstance(sorting, dict) else {},
                    filters=response_filters if isinstance(response_filters, dict) else {},
                    raw_payload=payload if isinstance(payload, dict) else {},
                )
        except httpx.HTTPError as exc:
            raise GetHookdClientError(f"Failed to fetch ads: {exc}") from exc

    def _parse_results(self, results: list[dict]) -> list[GetHookdAdResult]:
        """Parse API results into normalized GetHookdAdResult objects."""
        parsed = []
        for item in results:
            brand = item.get("brand", {}) or {}

            # Determine ad unit format from media
            media = item.get("media", []) or []
            ad_unit_format = None
            if media:
                if len(media) > 1:
                    ad_unit_format = "carousel"
                elif media:
                    first_media = media[0]
                    if first_media.get("type") == "video":
                        ad_unit_format = "video"
                    else:
                        ad_unit_format = "image"

            parsed.append(
                GetHookdAdResult(
                    id=str(item.get("id", "")),
                    external_id=item.get("external_id"),
                    platform=item.get("platform", ""),
                    display_format=item.get("display_format"),
                    ad_unit_format=ad_unit_format,
                    title=item.get("title"),
                    body=item.get("body"),
                    cta_type=item.get("cta_type"),
                    cta_text=item.get("cta_text"),
                    landing_page=item.get("landing_page"),
                    start_date=item.get("start_date"),
                    end_date=item.get("end_date"),
                    days_active=item.get("days_active"),
                    active_in_library=item.get("active_in_library"),
                    used_count=item.get("used_count"),
                    performance_score=item.get("performance_score"),
                    performance_score_title=item.get("performance_score_title"),
                    share_url=item.get("share_url"),
                    ad_library_link=item.get("ad_library_link") or item.get("ad_library_url"),
                    brand_id=brand.get("external_id") or brand.get("id"),
                    brand_name=brand.get("name"),
                    brand_logo_url=brand.get("logo_url"),
                    media=media,
                    raw_json=item,
                )
            )
        return parsed


def create_gethookd_client(
    api_token: str | None = None,
    base_url: str | None = None,
    timeout_seconds: float | None = None,
) -> GetHookdClient:
    """Factory function to create GetHookd client with optional settings."""
    return GetHookdClient(
        api_token=api_token,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )


def _coerce_optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_optional_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
