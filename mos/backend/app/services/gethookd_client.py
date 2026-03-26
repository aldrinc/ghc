"""
GetHookd API client service.

Provides methods for authenticating and fetching ads from GetHookd Explore API.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

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
    """Filters for GetHookd Explore API."""

    query: str = ""
    platforms: str = "facebook,instagram"
    niche: Optional[str] = None
    ad_format: Optional[str] = None
    location: Optional[str] = None
    language: Optional[str] = None
    performance_scores: str = "winning,optimized"
    status: str = "active"
    sort_column: str = "days_active"
    sort_direction: str = "desc"
    ads_per_brand_limit: int = 3
    active_ads_count: Optional[int] = None


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
    ) -> list[GetHookdAdResult]:
        """
        Fetch ads from GetHookd Explore API.
        """
        params: dict[str, Any] = {
            "page": page,
            "per_page": per_page,
        }

        if filters.query:
            params["query"] = filters.query
        if filters.platforms:
            params["platform"] = filters.platforms
        if filters.niche:
            params["niche"] = filters.niche
        if filters.ad_format:
            params["ad-format"] = filters.ad_format
        if filters.location:
            params["location"] = filters.location
        if filters.language:
            params["language"] = filters.language
        if filters.performance_scores:
            params["performance_scores"] = filters.performance_scores
        if filters.status:
            params["status"] = filters.status
        if filters.sort_column:
            params["sort_column"] = filters.sort_column
        if filters.sort_direction:
            params["sort_direction"] = filters.sort_direction
        if filters.ads_per_brand_limit:
            params["ads_per_brand_limit"] = filters.ads_per_brand_limit
        if filters.active_ads_count:
            params["active_ads_count"] = filters.active_ads_count

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
                    return []
                if not isinstance(results, list):
                    raise GetHookdClientError(
                        "GetHookd explore response returned an invalid data payload"
                    )
                parsed = self._parse_results(results)
                return parsed[: max(int(per_page or 0), 0)]
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
