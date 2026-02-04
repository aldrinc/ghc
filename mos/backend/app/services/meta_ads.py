from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger("meta.ads")


class MetaAdsConfigError(RuntimeError):
    pass


class MetaAdsError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None, error_payload: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_payload = error_payload


def _normalize_ad_account_id(ad_account_id: str) -> str:
    if ad_account_id.startswith("act_"):
        return ad_account_id
    return f"act_{ad_account_id}"


def _encode_payload(payload: dict[str, Any]) -> dict[str, Any]:
    encoded: dict[str, Any] = {}
    for key, value in payload.items():
        if value is None:
            continue
        if isinstance(value, bool):
            encoded[key] = "true" if value else "false"
            continue
        if isinstance(value, (dict, list)):
            encoded[key] = json.dumps(value)
            continue
        encoded[key] = value
    return encoded


class MetaAdsClient:
    def __init__(self, *, access_token: str, api_version: str, base_url: str | None = None) -> None:
        self.access_token = access_token
        self.api_version = api_version
        self.base_url = (base_url or "https://graph.facebook.com").rstrip("/")
        self.timeout = httpx.Timeout(30.0)

    @classmethod
    def from_settings(cls) -> "MetaAdsClient":
        if not settings.META_ACCESS_TOKEN:
            raise MetaAdsConfigError("META_ACCESS_TOKEN is required to use Meta Ads integration.")
        if not settings.META_GRAPH_API_VERSION:
            raise MetaAdsConfigError("META_GRAPH_API_VERSION is required to use Meta Ads integration.")
        return cls(
            access_token=settings.META_ACCESS_TOKEN,
            api_version=settings.META_GRAPH_API_VERSION,
            base_url=settings.META_GRAPH_API_BASE_URL,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        data: Optional[dict[str, Any]] = None,
        files: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/{self.api_version}/{path.lstrip('/')}"
        merged_params = {**(params or {}), "access_token": self.access_token}
        try:
            response = httpx.request(
                method,
                url,
                params=merged_params,
                data=data,
                files=files,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            error_payload: Any = None
            try:
                error_payload = response.json()
            except Exception:
                error_payload = {"text": response.text}
            message = f"Meta Graph API error ({response.status_code})."
            raise MetaAdsError(message, status_code=response.status_code, error_payload=error_payload) from exc
        except httpx.RequestError as exc:
            message = f"Meta Graph API request failed: {exc}"
            raise MetaAdsError(message) from exc

        try:
            return response.json()
        except Exception as exc:
            message = "Meta Graph API returned a non-JSON response."
            raise MetaAdsError(message) from exc

    def upload_image(
        self,
        *,
        ad_account_id: str,
        filename: str,
        content: bytes,
        content_type: Optional[str] = None,
        name: Optional[str] = None,
    ) -> dict[str, Any]:
        path = f"{_normalize_ad_account_id(ad_account_id)}/adimages"
        data = _encode_payload({"name": name}) if name else None
        files = {
            "filename": (
                filename,
                content,
                content_type or "application/octet-stream",
            )
        }
        return self._request("POST", path, data=data, files=files)

    def upload_video(
        self,
        *,
        ad_account_id: str,
        filename: str,
        content: bytes,
        content_type: Optional[str] = None,
        name: Optional[str] = None,
    ) -> dict[str, Any]:
        path = f"{_normalize_ad_account_id(ad_account_id)}/advideos"
        data = _encode_payload({"name": name}) if name else None
        files = {
            "source": (
                filename,
                content,
                content_type or "application/octet-stream",
            )
        }
        return self._request("POST", path, data=data, files=files)

    def create_adcreative(self, *, ad_account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        path = f"{_normalize_ad_account_id(ad_account_id)}/adcreatives"
        return self._request("POST", path, data=_encode_payload(payload))

    def create_campaign(self, *, ad_account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        path = f"{_normalize_ad_account_id(ad_account_id)}/campaigns"
        return self._request("POST", path, data=_encode_payload(payload))

    def create_adset(self, *, ad_account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        path = f"{_normalize_ad_account_id(ad_account_id)}/adsets"
        return self._request("POST", path, data=_encode_payload(payload))

    def create_ad(self, *, ad_account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        path = f"{_normalize_ad_account_id(ad_account_id)}/ads"
        return self._request("POST", path, data=_encode_payload(payload))

    def get_creative_previews(
        self,
        *,
        creative_id: str,
        ad_format: str,
        render_type: Optional[str] = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"ad_format": ad_format}
        if render_type:
            params["render_type"] = render_type
        return self._request("GET", f"{creative_id}/previews", params=params)

    def list_ad_images(
        self,
        *,
        ad_account_id: str,
        fields: str,
        limit: Optional[int] = None,
        after: Optional[str] = None,
    ) -> dict[str, Any]:
        return self._list_ad_account_edge(
            ad_account_id=ad_account_id,
            edge="adimages",
            fields=fields,
            limit=limit,
            after=after,
        )

    def list_ad_videos(
        self,
        *,
        ad_account_id: str,
        fields: str,
        limit: Optional[int] = None,
        after: Optional[str] = None,
    ) -> dict[str, Any]:
        return self._list_ad_account_edge(
            ad_account_id=ad_account_id,
            edge="advideos",
            fields=fields,
            limit=limit,
            after=after,
        )

    def list_ad_creatives(
        self,
        *,
        ad_account_id: str,
        fields: str,
        limit: Optional[int] = None,
        after: Optional[str] = None,
    ) -> dict[str, Any]:
        return self._list_ad_account_edge(
            ad_account_id=ad_account_id,
            edge="adcreatives",
            fields=fields,
            limit=limit,
            after=after,
        )

    def list_campaigns(
        self,
        *,
        ad_account_id: str,
        fields: str,
        limit: Optional[int] = None,
        after: Optional[str] = None,
    ) -> dict[str, Any]:
        return self._list_ad_account_edge(
            ad_account_id=ad_account_id,
            edge="campaigns",
            fields=fields,
            limit=limit,
            after=after,
        )

    def list_adsets(
        self,
        *,
        ad_account_id: str,
        fields: str,
        limit: Optional[int] = None,
        after: Optional[str] = None,
    ) -> dict[str, Any]:
        return self._list_ad_account_edge(
            ad_account_id=ad_account_id,
            edge="adsets",
            fields=fields,
            limit=limit,
            after=after,
        )

    def list_ads(
        self,
        *,
        ad_account_id: str,
        fields: str,
        limit: Optional[int] = None,
        after: Optional[str] = None,
    ) -> dict[str, Any]:
        return self._list_ad_account_edge(
            ad_account_id=ad_account_id,
            edge="ads",
            fields=fields,
            limit=limit,
            after=after,
        )

    def _list_ad_account_edge(
        self,
        *,
        ad_account_id: str,
        edge: str,
        fields: str,
        limit: Optional[int],
        after: Optional[str],
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"fields": fields}
        if limit is not None:
            params["limit"] = limit
        if after:
            params["after"] = after
        path = f"{_normalize_ad_account_id(ad_account_id)}/{edge}"
        return self._request("GET", path, params=params)
