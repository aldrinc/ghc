from __future__ import annotations

import base64
import json
import mimetypes
import os
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.schemas.creative_service import (
    CreativeServiceAssetRef,
    CreativeServiceImageAdsCreateIn,
    CreativeServiceImageAdsJob,
)
from app.services.creative_service_client import (
    CreativeServiceConfigError,
    CreativeServiceRequestError,
)
from app.services.embedded_freestyle_image_client import EmbeddedFreestyleImageRenderClient

_PROVIDER_CREATIVE_SERVICE = "creative_service"
_PROVIDER_HIGGSFIELD = "higgsfield"

_HIGGS_STATUS_QUEUED = "queued"
_HIGGS_STATUS_IN_PROGRESS = "in_progress"
_HIGGS_STATUS_COMPLETED = "completed"
_HIGGS_STATUS_FAILED = "failed"
_HIGGS_STATUS_NSFW = "nsfw"
_HIGGS_STATUS_CANCELED = "canceled"
_HIGGS_IMAGE_REFERENCE_ARGUMENT_KEY = "image_url"
_HIGGS_NANO_BANANA_MODEL_PREFIX = "nano-banana"
_HIGGS_TYPED_IMAGE_REFERENCE_KEY = "input_images"
_HIGGS_TYPED_IMAGE_REFERENCE_TYPE = "image_url"


class ImageRenderClient(Protocol):
    def create_image_ads(
        self,
        *,
        payload: CreativeServiceImageAdsCreateIn,
        idempotency_key: str,
    ) -> CreativeServiceImageAdsJob:
        ...

    def get_image_ads_job(self, *, job_id: str) -> CreativeServiceImageAdsJob:
        ...


def _infer_image_render_provider_from_model(model_id: str | None) -> str | None:
    candidate = str(model_id or "").strip().lower().lstrip("/")
    if not candidate:
        return None
    if candidate.startswith("models/"):
        candidate = candidate[len("models/") :]
    if candidate.startswith("gemini-"):
        return _PROVIDER_CREATIVE_SERVICE
    if candidate.startswith(_HIGGS_NANO_BANANA_MODEL_PREFIX):
        return _PROVIDER_HIGGSFIELD
    return None


def get_image_render_provider(*, model_id: str | None = None) -> str:
    inferred = _infer_image_render_provider_from_model(model_id)
    if inferred is None and model_id is None:
        inferred = _infer_image_render_provider_from_model(
            os.getenv("SWIPE_IMAGE_RENDER_MODEL") or os.getenv("IMAGE_RENDER_MODEL")
        )
    if inferred is not None:
        return inferred
    provider = str(settings.IMAGE_RENDER_PROVIDER or "").strip().lower()
    if provider not in {_PROVIDER_CREATIVE_SERVICE, _PROVIDER_HIGGSFIELD}:
        raise ValueError(
            "Unsupported IMAGE_RENDER_PROVIDER. "
            f"Expected one of [{_PROVIDER_CREATIVE_SERVICE}, {_PROVIDER_HIGGSFIELD}] "
            f"but got {provider!r}."
        )
    return provider


def build_image_render_client(*, model_id: str | None = None, org_id: str | None = None) -> ImageRenderClient:
    provider = get_image_render_provider(model_id=model_id)
    if provider == _PROVIDER_CREATIVE_SERVICE:
        return EmbeddedFreestyleImageRenderClient(org_id=org_id)
    if provider == _PROVIDER_HIGGSFIELD:
        return HiggsfieldImageRenderClient()
    raise ValueError(f"Unsupported image render provider: {provider!r}")


def _encode_higgs_job_state(
    *,
    model_id: str,
    prompt: str,
    count: int,
    aspect_ratio: str | None,
    request_ids: list[str],
    request_arguments: dict[str, Any] | None = None,
    uploaded_reference_urls: list[str] | None = None,
) -> str:
    state = {
        "provider": _PROVIDER_HIGGSFIELD,
        "model_id": model_id,
        "prompt": prompt,
        "count": count,
        "aspect_ratio": aspect_ratio,
        "request_ids": request_ids,
    }
    if request_arguments is not None:
        state["request_arguments"] = request_arguments
    if uploaded_reference_urls:
        state["uploaded_reference_urls"] = uploaded_reference_urls
    raw = json.dumps(state, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{_PROVIDER_HIGGSFIELD}:{encoded}"


def _decode_higgs_job_state(job_id: str) -> dict[str, Any]:
    prefix = f"{_PROVIDER_HIGGSFIELD}:"
    if not isinstance(job_id, str) or not job_id.startswith(prefix):
        raise ValueError(f"Invalid Higgsfield job id format: {job_id!r}")
    encoded = job_id[len(prefix) :]
    if not encoded:
        raise ValueError("Invalid Higgsfield job id: missing payload.")
    padded = encoded + ("=" * (-len(encoded) % 4))
    try:
        payload = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        parsed = json.loads(payload)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Invalid Higgsfield job id payload: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Invalid Higgsfield job id payload: expected JSON object.")
    request_ids = parsed.get("request_ids")
    if not isinstance(request_ids, list) or not request_ids:
        raise ValueError("Invalid Higgsfield job id payload: request_ids is required.")
    return parsed


def _extract_error_detail(data: dict[str, Any]) -> str | None:
    detail = data.get("detail")
    if isinstance(detail, str) and detail.strip():
        return detail.strip()

    error = data.get("error")
    if isinstance(error, str) and error.strip():
        return error.strip()
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()

    message = data.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()

    return None


def _extract_image_urls_from_higgs_result(data: dict[str, Any]) -> list[str]:
    images = data.get("images")
    if not isinstance(images, list) or not images:
        raise RuntimeError("Higgsfield completed response is missing images.")

    urls: list[str] = []
    for idx, image in enumerate(images):
        if not isinstance(image, dict):
            raise RuntimeError(f"Higgsfield image entry at index {idx} must be an object.")
        url = image.get("url")
        if not isinstance(url, str) or not url.strip():
            raise RuntimeError(f"Higgsfield image entry at index {idx} is missing a non-empty url.")
        urls.append(url.strip())
    return urls


class HiggsfieldImageRenderClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        hf_key: str | None = None,
        hf_api_key: str | None = None,
        hf_api_secret: str | None = None,
        default_model: str | None = None,
        default_resolution: str | None = None,
    ) -> None:
        self.base_url = (base_url or settings.HIGGSFIELD_BASE_URL or "").strip().rstrip("/")
        if not self.base_url:
            raise CreativeServiceConfigError("HIGGSFIELD_BASE_URL is required")

        key = (hf_key or settings.HF_KEY or "").strip()
        if key:
            self._auth_key = key
        else:
            api_key = (hf_api_key or settings.HF_API_KEY or "").strip()
            api_secret = (hf_api_secret or settings.HF_API_SECRET or "").strip()
            if not api_key or not api_secret:
                raise CreativeServiceConfigError(
                    "Higgsfield credentials are required. Configure HF_KEY or HF_API_KEY + HF_API_SECRET."
                )
            self._auth_key = f"{api_key}:{api_secret}"

        self.timeout_seconds = float(timeout_seconds or settings.CREATIVE_SERVICE_TIMEOUT_SECONDS or 30.0)
        self.default_model = (default_model or settings.HIGGSFIELD_DEFAULT_MODEL or "").strip()
        if not self.default_model:
            raise CreativeServiceConfigError("HIGGSFIELD_DEFAULT_MODEL is required for Higgsfield render provider.")
        self.default_resolution = (default_resolution or settings.HIGGSFIELD_DEFAULT_RESOLUTION or "").strip()

    def _download_reference_image(self, *, reference_image_url: str) -> tuple[bytes, str]:
        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
                response = client.get(reference_image_url)
        except httpx.HTTPError as exc:
            raise CreativeServiceRequestError(
                "Failed to download reference image for Higgsfield request.",
                details={"reference_image_url": reference_image_url, "error": str(exc)},
            ) from None

        if response.status_code >= 400:
            raise CreativeServiceRequestError(
                "Failed to download reference image for Higgsfield request.",
                status_code=response.status_code,
                details={"reference_image_url": reference_image_url},
            )

        content = response.content
        if not content:
            raise CreativeServiceRequestError(
                "Reference image URL returned empty content.",
                details={"reference_image_url": reference_image_url},
            )

        content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
        if not content_type:
            guess, _ = mimetypes.guess_type(urlparse(reference_image_url).path)
            content_type = (guess or "").strip().lower()
        if not content_type:
            raise CreativeServiceRequestError(
                "Reference image content type is missing and could not be inferred.",
                details={"reference_image_url": reference_image_url},
            )
        if not content_type.startswith("image/"):
            raise CreativeServiceRequestError(
                "Reference image URL must resolve to an image/* content type.",
                details={"reference_image_url": reference_image_url, "content_type": content_type},
            )

        return content, content_type

    def _create_upload_url(self, *, content_type: str) -> tuple[str, str]:
        response = self._request_json(
            "POST",
            "/files/generate-upload-url",
            json_payload={"content_type": content_type},
        )
        public_url = str(response.get("public_url") or "").strip()
        upload_url = str(response.get("upload_url") or "").strip()
        if not public_url or not upload_url:
            raise CreativeServiceRequestError(
                "Higgsfield upload URL response is missing public_url or upload_url.",
                details=response,
            )
        return public_url, upload_url

    def _upload_reference_bytes(
        self,
        *,
        upload_url: str,
        content: bytes,
        content_type: str,
    ) -> None:
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.put(
                    upload_url,
                    content=content,
                    headers={"Content-Type": content_type},
                )
        except httpx.HTTPError as exc:
            raise CreativeServiceRequestError(
                "Failed to upload reference image bytes to Higgsfield upload URL.",
                details={"upload_url": upload_url, "error": str(exc)},
            ) from None

        if response.status_code >= 400:
            raise CreativeServiceRequestError(
                "Failed to upload reference image bytes to Higgsfield upload URL.",
                status_code=response.status_code,
                details={"upload_url": upload_url},
            )

    def _prepare_reference_image_urls(self, *, reference_image_urls: list[str]) -> list[str]:
        cleaned_urls = [str(item).strip() for item in reference_image_urls if str(item).strip()]
        if not cleaned_urls:
            return []
        if len(cleaned_urls) > 1:
            raise ValueError(
                "Higgsfield render currently supports at most one reference image URL per request in MOS integration."
            )

        downloaded_bytes, content_type = self._download_reference_image(reference_image_url=cleaned_urls[0])
        public_url, upload_url = self._create_upload_url(content_type=content_type)
        self._upload_reference_bytes(upload_url=upload_url, content=downloaded_bytes, content_type=content_type)
        return [public_url]

    def _build_reference_arguments(
        self,
        *,
        model_id: str,
        uploaded_reference_urls: list[str],
    ) -> dict[str, Any]:
        if not uploaded_reference_urls:
            return {}

        reference_url = uploaded_reference_urls[0]
        normalized_model_id = model_id.strip().lower()
        if normalized_model_id.startswith(_HIGGS_NANO_BANANA_MODEL_PREFIX):
            return {
                _HIGGS_TYPED_IMAGE_REFERENCE_KEY: [
                    {
                        "type": _HIGGS_TYPED_IMAGE_REFERENCE_TYPE,
                        "image_url": reference_url,
                    }
                ]
            }

        return {_HIGGS_IMAGE_REFERENCE_ARGUMENT_KEY: reference_url}

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Key {self._auth_key}",
            "Accept": "application/json",
        }
        if json_payload is not None:
            headers["Content-Type"] = "application/json"

        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
                response = client.request(
                    method=method,
                    url=path,
                    headers=headers,
                    json=json_payload,
                )
        except httpx.HTTPError as exc:
            raise CreativeServiceRequestError(
                "Higgsfield network error",
                details={
                    "method": method,
                    "path": path,
                    "base_url": self.base_url,
                    "error": str(exc),
                },
            ) from None

        body: dict[str, Any] | None = None
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                body = parsed
        except ValueError:
            body = None

        if response.status_code >= 400:
            message = _extract_error_detail(body or {}) or f"Higgsfield request failed with HTTP {response.status_code}"
            raise CreativeServiceRequestError(
                message=message,
                status_code=response.status_code,
                details=body,
            )

        if body is None:
            raise CreativeServiceRequestError(
                "Higgsfield API returned a non-object JSON response.",
                status_code=response.status_code,
            )
        return body

    def create_image_ads(
        self,
        *,
        payload: CreativeServiceImageAdsCreateIn,
        idempotency_key: str,
    ) -> CreativeServiceImageAdsJob:
        del idempotency_key
        if payload.count < 1:
            raise ValueError("count must be greater than zero for Higgsfield image rendering.")

        model_id = (payload.model_id or self.default_model).strip().lstrip("/")
        if not model_id:
            raise ValueError("model_id is required for Higgsfield image rendering.")

        prompt = (payload.prompt or "").strip()
        if not prompt:
            raise ValueError("prompt is required for Higgsfield image rendering.")

        uploaded_reference_urls = self._prepare_reference_image_urls(
            reference_image_urls=payload.reference_image_urls
        )

        args: dict[str, Any] = {"prompt": prompt}
        args.update(
            self._build_reference_arguments(
                model_id=model_id,
                uploaded_reference_urls=uploaded_reference_urls,
            )
        )
        if payload.aspect_ratio:
            args["aspect_ratio"] = payload.aspect_ratio
        if self.default_resolution:
            args["resolution"] = self.default_resolution

        request_ids: list[str] = []
        for _ in range(payload.count):
            response = self._request_json("POST", f"/{model_id}", json_payload=args)
            request_id = response.get("request_id")
            if not isinstance(request_id, str) or not request_id.strip():
                raise CreativeServiceRequestError(
                    "Higgsfield response is missing request_id.",
                    details=response,
                )
            request_ids.append(request_id.strip())

        job_id = _encode_higgs_job_state(
            model_id=model_id,
            prompt=prompt,
            count=payload.count,
            aspect_ratio=payload.aspect_ratio,
            request_ids=request_ids,
            request_arguments=args,
            uploaded_reference_urls=uploaded_reference_urls,
        )
        reference_assets = [
            CreativeServiceAssetRef(
                asset_id=f"higgsfield:reference:{idx}",
                output_index=idx,
                primary_url=url,
            )
            for idx, url in enumerate(uploaded_reference_urls)
        ]
        return CreativeServiceImageAdsJob(
            id=job_id,
            status="queued",
            prompt=prompt,
            count=payload.count,
            aspect_ratio=payload.aspect_ratio,
            model_id=model_id,
            error_detail=None,
            references=reference_assets,
            outputs=[],
        )

    def get_image_ads_job(self, *, job_id: str) -> CreativeServiceImageAdsJob:
        state = _decode_higgs_job_state(job_id)
        request_ids = [str(item).strip() for item in state["request_ids"] if str(item).strip()]
        if not request_ids:
            raise RuntimeError("Higgsfield job has no request_ids.")

        model_id = str(state.get("model_id") or "").strip() or None
        prompt = str(state.get("prompt") or "").strip() or None
        count = int(state.get("count") or len(request_ids))
        aspect_ratio_raw = state.get("aspect_ratio")
        aspect_ratio = str(aspect_ratio_raw).strip() if isinstance(aspect_ratio_raw, str) else None
        uploaded_reference_urls_raw = state.get("uploaded_reference_urls")
        uploaded_reference_urls = (
            [str(item).strip() for item in uploaded_reference_urls_raw if str(item).strip()]
            if isinstance(uploaded_reference_urls_raw, list)
            else []
        )

        raw_statuses: list[str] = []
        failure_details: list[str] = []
        outputs: list[CreativeServiceAssetRef] = []
        output_index = 0

        for request_id in request_ids:
            status_data = self._request_json("GET", f"/requests/{request_id}/status")
            status_raw = str(status_data.get("status") or "").strip().lower()
            if not status_raw:
                raise RuntimeError(f"Higgsfield status response is missing status for request_id={request_id}.")

            raw_statuses.append(status_raw)
            if status_raw == _HIGGS_STATUS_COMPLETED:
                urls = _extract_image_urls_from_higgs_result(status_data)
                for image_idx, url in enumerate(urls):
                    outputs.append(
                        CreativeServiceAssetRef(
                            asset_id=f"higgsfield:{request_id}:{image_idx}",
                            output_index=output_index,
                            primary_url=url,
                            prompt_used=prompt,
                        )
                    )
                    output_index += 1
                continue

            if status_raw in {_HIGGS_STATUS_FAILED, _HIGGS_STATUS_NSFW, _HIGGS_STATUS_CANCELED}:
                detail = _extract_error_detail(status_data) or f"request_id={request_id} status={status_raw}"
                failure_details.append(detail)
                continue

            if status_raw in {_HIGGS_STATUS_QUEUED, _HIGGS_STATUS_IN_PROGRESS}:
                continue

            raise RuntimeError(f"Unknown Higgsfield request status: {status_raw!r} (request_id={request_id}).")

        if failure_details:
            status = "failed"
            error_detail = "; ".join(failure_details)
        elif raw_statuses and all(item == _HIGGS_STATUS_COMPLETED for item in raw_statuses):
            status = "succeeded"
            error_detail = None
        elif raw_statuses and all(item == _HIGGS_STATUS_QUEUED for item in raw_statuses):
            status = "queued"
            error_detail = None
        else:
            status = "processing"
            error_detail = None

        reference_assets = [
            CreativeServiceAssetRef(
                asset_id=f"higgsfield:reference:{idx}",
                output_index=idx,
                primary_url=url,
            )
            for idx, url in enumerate(uploaded_reference_urls)
        ]
        return CreativeServiceImageAdsJob(
            id=job_id,
            status=status,
            prompt=prompt,
            count=count,
            aspect_ratio=aspect_ratio,
            model_id=model_id,
            error_detail=error_detail,
            references=reference_assets,
            outputs=outputs,
        )
