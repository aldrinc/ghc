from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterator

import httpx
from pydantic import ValidationError

from app.config import settings
from app.schemas.creative_service import (
    CreativeServiceAssetCreateFromUriIn,
    CreativeServiceAssetOut,
    CreativeServiceErrorEnvelope,
    CreativeServiceImageAdsCreateIn,
    CreativeServiceImageAdsJob,
    CreativeServiceVideoMessageCreateIn,
    CreativeServiceVideoMessageOut,
    CreativeServiceVideoResultOut,
    CreativeServiceVideoSessionCreateIn,
    CreativeServiceVideoSessionOut,
    CreativeServiceVideoTurnOut,
)


class CreativeServiceConfigError(RuntimeError):
    pass


@dataclass
class CreativeServiceRequestError(RuntimeError):
    message: str
    status_code: int | None = None
    error_code: str | None = None
    request_id: str | None = None
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        code = f" code={self.error_code}" if self.error_code else ""
        status = f" status={self.status_code}" if self.status_code is not None else ""
        req = f" request_id={self.request_id}" if self.request_id else ""
        return f"{self.message}{status}{code}{req}".strip()


class CreativeServiceClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        bearer_token: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        resolved_base = (base_url or settings.CREATIVE_SERVICE_BASE_URL or "").strip()
        resolved_token = (bearer_token or settings.CREATIVE_SERVICE_BEARER_TOKEN or "").strip()
        if not resolved_base:
            raise CreativeServiceConfigError("CREATIVE_SERVICE_BASE_URL is required")
        if not resolved_token:
            raise CreativeServiceConfigError("CREATIVE_SERVICE_BEARER_TOKEN is required")
        self.base_url = resolved_base.rstrip("/")
        self.bearer_token = resolved_token
        self.timeout_seconds = float(timeout_seconds or settings.CREATIVE_SERVICE_TIMEOUT_SECONDS or 30.0)

    def create_image_ads(
        self,
        *,
        payload: CreativeServiceImageAdsCreateIn,
        idempotency_key: str,
    ) -> CreativeServiceImageAdsJob:
        body = self._request_json(
            "POST",
            "/v1/marketing/image-ads",
            json_payload=payload.model_dump(mode="json"),
            idempotency_key=idempotency_key,
        )
        return self._parse_model(CreativeServiceImageAdsJob, body, context="create_image_ads")

    def create_asset_from_uri(
        self,
        *,
        payload: CreativeServiceAssetCreateFromUriIn,
    ) -> CreativeServiceAssetOut:
        body = self._request_json(
            "POST",
            "/assets/from_uri",
            json_payload=payload.model_dump(mode="json"),
        )
        return self._parse_model(CreativeServiceAssetOut, body, context="create_asset_from_uri")

    def upload_asset(
        self,
        *,
        kind: str,
        source: str,
        file_name: str,
        file_bytes: bytes,
        content_type: str,
        title: str | None = None,
        description: str | None = None,
        metadata_json: dict[str, Any] | None = None,
        generate_proxy: bool = True,
    ) -> CreativeServiceAssetOut:
        if not file_bytes:
            raise CreativeServiceRequestError("Cannot upload empty asset bytes")
        if not file_name.strip():
            raise CreativeServiceRequestError("Asset upload file_name cannot be empty")
        if not content_type.strip():
            raise CreativeServiceRequestError("Asset upload content_type cannot be empty")

        form_data: dict[str, Any] = {
            "kind": kind,
            "source": source,
            "generate_proxy": str(generate_proxy).lower(),
        }
        if title is not None:
            form_data["title"] = title
        if description is not None:
            form_data["description"] = description
        if metadata_json is not None:
            form_data["metadata_json"] = json.dumps(metadata_json)

        files = {"file": (file_name, file_bytes, content_type)}
        with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            resp = client.post(
                "/assets/upload",
                data=form_data,
                files=files,
                headers={
                    "Authorization": f"Bearer {self.bearer_token}",
                    "Accept": "application/json",
                },
            )

        if resp.status_code >= 400:
            self._raise_request_error(resp)

        try:
            data = resp.json()
        except ValueError as exc:
            raise CreativeServiceRequestError(
                "Creative service returned non-JSON payload for asset upload",
                status_code=resp.status_code,
            ) from exc
        if not isinstance(data, dict):
            raise CreativeServiceRequestError(
                "Creative service returned non-object JSON payload for asset upload",
                status_code=resp.status_code,
            )
        return self._parse_model(CreativeServiceAssetOut, data, context="upload_asset")

    def get_image_ads_job(self, *, job_id: str) -> CreativeServiceImageAdsJob:
        body = self._request_json("GET", f"/v1/marketing/image-ads/{job_id}")
        return self._parse_model(CreativeServiceImageAdsJob, body, context="get_image_ads_job")

    def iter_image_ads_events(self, *, job_id: str) -> Iterator[dict[str, Any]]:
        path = f"/v1/marketing/image-ads/{job_id}/events"
        with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            with client.stream("GET", path, headers=self._headers()) as resp:
                if resp.status_code >= 400:
                    self._raise_request_error(resp)
                for line in resp.iter_lines():
                    if not line:
                        continue
                    text = line.decode("utf-8") if isinstance(line, bytes) else str(line)
                    if text.startswith("data:"):
                        raw = text[5:].strip()
                        if not raw:
                            continue
                        try:
                            parsed = json.loads(raw)
                        except json.JSONDecodeError as exc:
                            raise CreativeServiceRequestError(
                                f"Invalid SSE event payload from creative service: {raw[:200]}"
                            ) from exc
                        if not isinstance(parsed, dict):
                            raise CreativeServiceRequestError("Creative service SSE event payload must be an object")
                        yield parsed

    def create_video_session(
        self,
        *,
        payload: CreativeServiceVideoSessionCreateIn,
        idempotency_key: str,
    ) -> CreativeServiceVideoSessionOut:
        body = self._request_json(
            "POST",
            "/v1/video-ads/sessions",
            json_payload=payload.model_dump(mode="json"),
            idempotency_key=idempotency_key,
        )
        return self._parse_model(CreativeServiceVideoSessionOut, body, context="create_video_session")

    def create_video_message(
        self,
        *,
        session_id: str,
        payload: CreativeServiceVideoMessageCreateIn,
        idempotency_key: str,
    ) -> CreativeServiceVideoMessageOut:
        body = self._request_json(
            "POST",
            f"/v1/video-ads/sessions/{session_id}/messages",
            json_payload=payload.model_dump(mode="json"),
            idempotency_key=idempotency_key,
        )
        return self._parse_model(CreativeServiceVideoMessageOut, body, context="create_video_message")

    def get_video_turn(self, *, session_id: str, turn_id: str) -> CreativeServiceVideoTurnOut:
        body = self._request_json("GET", f"/v1/video-ads/sessions/{session_id}/turns/{turn_id}")
        return self._parse_model(CreativeServiceVideoTurnOut, body, context="get_video_turn")

    def get_video_result(self, *, session_id: str) -> CreativeServiceVideoResultOut:
        body = self._request_json("GET", f"/v1/video-ads/sessions/{session_id}/result")
        return self._parse_model(CreativeServiceVideoResultOut, body, context="get_video_result")

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            resp = client.request(
                method=method,
                url=path,
                json=json_payload,
                headers=self._headers(idempotency_key=idempotency_key),
            )

        if resp.status_code >= 400:
            self._raise_request_error(resp)

        try:
            data = resp.json()
        except ValueError as exc:
            raise CreativeServiceRequestError(
                f"Creative service returned non-JSON payload for {method} {path}",
                status_code=resp.status_code,
            ) from exc

        if not isinstance(data, dict):
            raise CreativeServiceRequestError(
                f"Creative service returned non-object JSON payload for {method} {path}",
                status_code=resp.status_code,
            )
        return data

    def _headers(self, *, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            cleaned = idempotency_key.strip()
            if not cleaned:
                raise CreativeServiceRequestError("Idempotency key cannot be empty")
            headers["Idempotency-Key"] = cleaned
        return headers

    def _raise_request_error(self, resp: httpx.Response) -> None:
        details: dict[str, Any] | None = None
        message = f"Creative service request failed ({resp.status_code})"
        error_code: str | None = None
        request_id: str | None = None

        try:
            payload = resp.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            try:
                envelope = CreativeServiceErrorEnvelope.model_validate(payload)
            except ValidationError:
                envelope = None

            if envelope and envelope.error:
                if envelope.error.message:
                    message = envelope.error.message
                error_code = envelope.error.code
                request_id = envelope.error.request_id
                details = envelope.error.details
            else:
                details = payload

        raise CreativeServiceRequestError(
            message=message,
            status_code=resp.status_code,
            error_code=error_code,
            request_id=request_id,
            details=details,
        )

    def _parse_model(self, model_cls, payload: dict[str, Any], *, context: str):
        try:
            return model_cls.model_validate(payload)
        except ValidationError as exc:
            raise CreativeServiceRequestError(
                f"Creative service payload validation failed for {context}: {exc}",
                details={"payload": payload},
            ) from exc
