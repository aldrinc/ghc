from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger("meta.ads")

_META_RATE_LIMIT_STATUS_CODES = {429}
_META_RATE_LIMIT_ERROR_CODES = {4, 17, 32, 613, 80004}


def _new_condition() -> threading.Condition:
    return threading.Condition(threading.Lock())


@dataclass
class _MetaAdAccountReadPressureState:
    condition: threading.Condition = field(default_factory=_new_condition)
    active_read_requests: int = 0
    cooldown_until_monotonic: float = 0.0


_META_AD_ACCOUNT_READ_PRESSURE_STATES: dict[str, _MetaAdAccountReadPressureState] = {}
_META_AD_ACCOUNT_READ_PRESSURE_STATES_LOCK = threading.Lock()


class MetaAdsConfigError(RuntimeError):
    pass


class MetaAdsError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None, error_payload: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_payload = error_payload


class MetaAdsRateLimitError(MetaAdsError):
    def __init__(
        self,
        message: str,
        *,
        ad_account_id: str | None,
        retry_after_seconds: float | None,
        deferred: bool,
        error_payload: Any = None,
    ) -> None:
        payload: dict[str, Any] = {
            "kind": "ad_account_pressure",
            "adAccountId": ad_account_id,
            "retryAfterSeconds": retry_after_seconds,
            "deferred": deferred,
        }
        if error_payload is not None:
            payload["metaGraphError"] = error_payload
        super().__init__(message, status_code=429, error_payload=payload)
        self.ad_account_id = ad_account_id
        self.retry_after_seconds = retry_after_seconds
        self.deferred = deferred


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


def _normalize_throttle_scope(throttle_scope: str | None) -> str | None:
    if not isinstance(throttle_scope, str):
        return None
    raw = throttle_scope.strip()
    if not raw:
        return None
    if raw.startswith("act_") or raw.isdigit():
        return _normalize_ad_account_id(raw)
    return raw


def _infer_throttle_scope(path: str) -> str | None:
    root_segment = path.lstrip("/").split("/", 1)[0].strip()
    if root_segment.startswith("act_") or root_segment.isdigit():
        return _normalize_ad_account_id(root_segment)
    return None


def _meta_graph_error_details(error_payload: Any) -> dict[str, Any] | None:
    if not isinstance(error_payload, dict):
        return None
    payload_error = error_payload.get("error")
    if not isinstance(payload_error, dict):
        return None
    return payload_error


def _is_meta_rate_limited(*, status_code: int | None, error_payload: Any) -> bool:
    if status_code in _META_RATE_LIMIT_STATUS_CODES:
        return True
    error_details = _meta_graph_error_details(error_payload)
    if not error_details:
        return False
    raw_code = error_details.get("code")
    try:
        error_code = int(str(raw_code)) if raw_code is not None else None
    except (TypeError, ValueError):
        error_code = None
    if error_code in _META_RATE_LIMIT_ERROR_CODES:
        return True
    message = error_details.get("message")
    if not isinstance(message, str):
        return False
    lowered = message.lower()
    return "rate limit" in lowered or "too many api calls" in lowered


def _resolve_retry_after_seconds(*, attempt_number: int, retry_after_raw: str | None) -> float:
    if retry_after_raw:
        stripped = retry_after_raw.strip()
        if stripped:
            try:
                return max(float(stripped), 1.0)
            except ValueError:
                try:
                    parsed = parsedate_to_datetime(stripped)
                except (TypeError, ValueError, IndexError, OverflowError):
                    parsed = None
                if parsed is not None:
                    return max((parsed.timestamp() - time.time()), 1.0)
    base_delay = settings.META_GRAPH_RATE_LIMIT_BASE_DELAY_SECONDS
    retry_power = max(0, attempt_number - 1)
    delay_seconds = base_delay * (2**retry_power)
    return max(1.0, min(delay_seconds, settings.META_GRAPH_RATE_LIMIT_MAX_DELAY_SECONDS))


def _read_pressure_state_for(scope: str) -> _MetaAdAccountReadPressureState:
    with _META_AD_ACCOUNT_READ_PRESSURE_STATES_LOCK:
        state = _META_AD_ACCOUNT_READ_PRESSURE_STATES.get(scope)
        if state is None:
            state = _MetaAdAccountReadPressureState()
            _META_AD_ACCOUNT_READ_PRESSURE_STATES[scope] = state
        return state


def _mark_read_cooldown(scope: str, *, cooldown_seconds: float) -> None:
    if cooldown_seconds <= 0:
        return
    state = _read_pressure_state_for(scope)
    with state.condition:
        state.cooldown_until_monotonic = max(
            state.cooldown_until_monotonic,
            time.monotonic() + cooldown_seconds,
        )
        state.condition.notify_all()


class _MetaReadThrottleLease:
    def __init__(self, state: _MetaAdAccountReadPressureState | None) -> None:
        self._state = state
        self._released = state is None

    def release(self) -> None:
        if self._released or self._state is None:
            return
        with self._state.condition:
            self._state.active_read_requests = max(0, self._state.active_read_requests - 1)
            self._state.condition.notify_all()
        self._released = True


def _acquire_read_slot(*, scope: str, wait_timeout_seconds: float) -> _MetaReadThrottleLease:
    max_concurrent_reads = settings.META_GRAPH_MAX_CONCURRENT_READS_PER_ACCOUNT
    if max_concurrent_reads <= 0:
        return _MetaReadThrottleLease(None)

    state = _read_pressure_state_for(scope)
    deadline = time.monotonic() + max(wait_timeout_seconds, 0.0)
    with state.condition:
        while True:
            now = time.monotonic()
            cooldown_remaining = max(0.0, state.cooldown_until_monotonic - now)
            if cooldown_remaining <= 0 and state.active_read_requests < max_concurrent_reads:
                state.active_read_requests += 1
                return _MetaReadThrottleLease(state)

            remaining_budget = deadline - now
            if remaining_budget <= 0:
                retry_after_seconds = cooldown_remaining if cooldown_remaining > 0 else None
                raise MetaAdsRateLimitError(
                    "Meta Graph API request deferred due to ad account pressure.",
                    ad_account_id=scope,
                    retry_after_seconds=retry_after_seconds,
                    deferred=True,
                )

            wait_seconds = cooldown_remaining if cooldown_remaining > 0 else 0.25
            state.condition.wait(min(wait_seconds, remaining_budget))


class MetaAdsClient:
    def __init__(
        self,
        *,
        access_token: str,
        api_version: str,
        base_url: str | None = None,
        request_timeout_seconds: float | None = None,
        connect_timeout_seconds: float | None = None,
    ) -> None:
        self.access_token = access_token
        self.api_version = api_version
        self.base_url = (base_url or "https://graph.facebook.com").rstrip("/")
        self.timeout = httpx.Timeout(
            request_timeout_seconds
            if request_timeout_seconds is not None
            else settings.META_GRAPH_REQUEST_TIMEOUT_SECONDS,
            connect=connect_timeout_seconds
            if connect_timeout_seconds is not None
            else settings.META_GRAPH_CONNECT_TIMEOUT_SECONDS,
        )

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
        throttle_scope: str | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/{self.api_version}/{path.lstrip('/')}"
        merged_params = {**(params or {}), "access_token": self.access_token}
        method_upper = method.upper()
        normalized_scope = _normalize_throttle_scope(throttle_scope) or _infer_throttle_scope(path)
        lease: _MetaReadThrottleLease | None = None
        if method_upper == "GET" and normalized_scope is not None:
            lease = _acquire_read_slot(
                scope=normalized_scope,
                wait_timeout_seconds=settings.META_GRAPH_READ_SLOT_WAIT_TIMEOUT_SECONDS,
            )

        max_attempts = max(1, settings.META_GRAPH_RATE_LIMIT_MAX_RETRIES + 1)
        try:
            for attempt in range(1, max_attempts + 1):
                try:
                    response = httpx.request(
                        method,
                        url,
                        params=merged_params,
                        data=data,
                        files=files,
                        timeout=self.timeout,
                    )
                except httpx.RequestError as exc:
                    message = f"Meta Graph API request failed: {exc}"
                    raise MetaAdsError(message) from exc

                if response.is_error:
                    error_payload: Any = None
                    try:
                        error_payload = response.json()
                    except Exception:
                        error_payload = {"text": response.text}

                    if _is_meta_rate_limited(
                        status_code=response.status_code,
                        error_payload=error_payload,
                    ):
                        retry_after_seconds = _resolve_retry_after_seconds(
                            attempt_number=attempt,
                            retry_after_raw=response.headers.get("Retry-After"),
                        )
                        if normalized_scope is not None and method_upper == "GET":
                            _mark_read_cooldown(
                                normalized_scope,
                                cooldown_seconds=retry_after_seconds,
                            )
                        if attempt < max_attempts:
                            logger.warning(
                                "Meta Graph API request hit ad account pressure; backing off.",
                                extra={
                                    "path": path,
                                    "method": method_upper,
                                    "ad_account_id": normalized_scope,
                                    "attempt": attempt,
                                    "retry_after_seconds": retry_after_seconds,
                                },
                            )
                            time.sleep(retry_after_seconds)
                            continue
                        raise MetaAdsRateLimitError(
                            "Meta Graph API request deferred due to ad account pressure.",
                            ad_account_id=normalized_scope,
                            retry_after_seconds=retry_after_seconds,
                            deferred=method_upper == "GET" and normalized_scope is not None,
                            error_payload=error_payload,
                        )

                    message = f"Meta Graph API error ({response.status_code})."
                    raise MetaAdsError(
                        message,
                        status_code=response.status_code,
                        error_payload=error_payload,
                    )

                try:
                    return response.json()
                except Exception as exc:
                    message = "Meta Graph API returned a non-JSON response."
                    raise MetaAdsError(message) from exc
        finally:
            if lease is not None:
                lease.release()

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
        return self._request("POST", path, data=data, files=files, throttle_scope=ad_account_id)

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
        return self._request("POST", path, data=data, files=files, throttle_scope=ad_account_id)

    def create_adcreative(self, *, ad_account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        path = f"{_normalize_ad_account_id(ad_account_id)}/adcreatives"
        return self._request("POST", path, data=_encode_payload(payload), throttle_scope=ad_account_id)

    def create_campaign(self, *, ad_account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        path = f"{_normalize_ad_account_id(ad_account_id)}/campaigns"
        return self._request("POST", path, data=_encode_payload(payload), throttle_scope=ad_account_id)

    def create_ad_pixel(self, *, ad_account_id: str, name: str) -> dict[str, Any]:
        path = f"{_normalize_ad_account_id(ad_account_id)}/adspixels"
        return self._request("POST", path, data=_encode_payload({"name": name}), throttle_scope=ad_account_id)

    def create_adset(self, *, ad_account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        path = f"{_normalize_ad_account_id(ad_account_id)}/adsets"
        return self._request("POST", path, data=_encode_payload(payload), throttle_scope=ad_account_id)

    def create_ad(self, *, ad_account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        path = f"{_normalize_ad_account_id(ad_account_id)}/ads"
        return self._request("POST", path, data=_encode_payload(payload), throttle_scope=ad_account_id)

    def update_campaign(
        self,
        *,
        campaign_id: str,
        payload: dict[str, Any],
        throttle_scope: str | None = None,
    ) -> dict[str, Any]:
        return self._request("POST", campaign_id, data=_encode_payload(payload), throttle_scope=throttle_scope)

    def update_adset(
        self,
        *,
        adset_id: str,
        payload: dict[str, Any],
        throttle_scope: str | None = None,
    ) -> dict[str, Any]:
        return self._request("POST", adset_id, data=_encode_payload(payload), throttle_scope=throttle_scope)

    def update_ad(
        self,
        *,
        ad_id: str,
        payload: dict[str, Any],
        throttle_scope: str | None = None,
    ) -> dict[str, Any]:
        return self._request("POST", ad_id, data=_encode_payload(payload), throttle_scope=throttle_scope)

    def get_creative_previews(
        self,
        *,
        creative_id: str,
        ad_format: str,
        render_type: Optional[str] = None,
        throttle_scope: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"ad_format": ad_format}
        if render_type:
            params["render_type"] = render_type
        return self._request("GET", f"{creative_id}/previews", params=params, throttle_scope=throttle_scope)

    def get_object(
        self,
        *,
        object_id: str,
        fields: str,
        throttle_scope: str | None = None,
    ) -> dict[str, Any]:
        return self._request("GET", object_id, params={"fields": fields}, throttle_scope=throttle_scope)

    def list_user_pages(
        self,
        *,
        fields: str,
        limit: Optional[int] = None,
        after: Optional[str] = None,
    ) -> dict[str, Any]:
        return self._list_edge(path="me/accounts", fields=fields, limit=limit, after=after)

    def list_user_adaccounts(
        self,
        *,
        fields: str,
        limit: Optional[int] = None,
        after: Optional[str] = None,
    ) -> dict[str, Any]:
        return self._list_edge(path="me/adaccounts", fields=fields, limit=limit, after=after)

    def list_user_businesses(
        self,
        *,
        fields: str,
        limit: Optional[int] = None,
        after: Optional[str] = None,
    ) -> dict[str, Any]:
        return self._list_edge(path="me/businesses", fields=fields, limit=limit, after=after)

    def get_ad_account(self, *, ad_account_id: str, fields: str) -> dict[str, Any]:
        return self.get_object(
            object_id=_normalize_ad_account_id(ad_account_id),
            fields=fields,
            throttle_scope=ad_account_id,
        )

    def list_ad_pixels(
        self,
        *,
        ad_account_id: str,
        fields: str,
        limit: Optional[int] = None,
        after: Optional[str] = None,
    ) -> dict[str, Any]:
        return self._list_ad_account_edge(
            ad_account_id=ad_account_id,
            edge="adspixels",
            fields=fields,
            limit=limit,
            after=after,
        )

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

    def send_pixel_events(
        self,
        *,
        pixel_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request("POST", f"{pixel_id}/events", data=_encode_payload(payload))

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
        path = f"{_normalize_ad_account_id(ad_account_id)}/{edge}"
        return self._list_edge(path=path, fields=fields, limit=limit, after=after)

    def _list_edge(
        self,
        *,
        path: str,
        fields: str,
        limit: Optional[int],
        after: Optional[str],
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"fields": fields}
        if limit is not None:
            params["limit"] = limit
        if after:
            params["after"] = after
        return self._request("GET", path, params=params)
