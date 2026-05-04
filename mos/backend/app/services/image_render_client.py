from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import urlparse
from uuid import UUID

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAIError, RateLimitError

from app.config import settings
from app.db.base import session_scope
from app.db.models import Asset
from app.observability import get_openai_client_class
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
from app.services.media_storage import IMMUTABLE_CACHE_CONTROL, MediaStorage

_PROVIDER_CREATIVE_SERVICE = "creative_service"
_PROVIDER_HIGGSFIELD = "higgsfield"
_PROVIDER_OPENAI = "openai"

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
_OPENAI_IMAGE_MODEL_PREFIX = "gpt-image-"
_OPENAI_DEFAULT_IMAGE_MODEL = "gpt-image-2"
_OPENAI_DEFAULT_OUTPUT_FORMAT = "png"
_OPENAI_OUTPUT_FORMAT_CONTENT_TYPES = {
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}
_OPENAI_QUALITY_VALUES = {"low", "medium", "high", "auto"}
_OPENAI_OUTPUT_FORMAT_VALUES = set(_OPENAI_OUTPUT_FORMAT_CONTENT_TYPES)


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
    if candidate.startswith("openai/"):
        candidate = candidate[len("openai/") :]
    if candidate.startswith("models/"):
        candidate = candidate[len("models/") :]
    if candidate.startswith("gemini-"):
        return _PROVIDER_CREATIVE_SERVICE
    if candidate.startswith(_HIGGS_NANO_BANANA_MODEL_PREFIX):
        return _PROVIDER_HIGGSFIELD
    if candidate.startswith(_OPENAI_IMAGE_MODEL_PREFIX):
        return _PROVIDER_OPENAI
    return None


def get_image_render_provider(*, model_id: str | None = None) -> str:
    inferred = _infer_image_render_provider_from_model(model_id)
    if inferred is None and model_id is None:
        inferred = _infer_image_render_provider_from_model(
            os.getenv("SWIPE_IMAGE_RENDER_MODEL")
            or os.getenv("IMAGE_RENDER_MODEL")
            or settings.SWIPE_IMAGE_RENDER_MODEL
        )
    if inferred is not None:
        return inferred
    provider = str(settings.IMAGE_RENDER_PROVIDER or "").strip().lower()
    if provider not in {_PROVIDER_CREATIVE_SERVICE, _PROVIDER_HIGGSFIELD, _PROVIDER_OPENAI}:
        expected = ", ".join(
            [_PROVIDER_CREATIVE_SERVICE, _PROVIDER_HIGGSFIELD, _PROVIDER_OPENAI]
        )
        raise ValueError(
            "Unsupported IMAGE_RENDER_PROVIDER. "
            f"Expected one of [{expected}] but got {provider!r}."
        )
    return provider


def build_image_render_client(
    *,
    model_id: str | None = None,
    org_id: str | None = None,
) -> ImageRenderClient:
    provider = get_image_render_provider(model_id=model_id)
    if provider == _PROVIDER_CREATIVE_SERVICE:
        return EmbeddedFreestyleImageRenderClient(org_id=org_id)
    if provider == _PROVIDER_HIGGSFIELD:
        return HiggsfieldImageRenderClient()
    if provider == _PROVIDER_OPENAI:
        return OpenAIImageRenderClient(org_id=org_id)
    raise ValueError(f"Unsupported image render provider: {provider!r}")


def _normalize_openai_model_id(model_id: str | None) -> str:
    cleaned = str(
        model_id or os.getenv("OPENAI_IMAGE_RENDER_MODEL") or _OPENAI_DEFAULT_IMAGE_MODEL
    ).strip()
    if cleaned.startswith("openai/"):
        cleaned = cleaned[len("openai/") :]
    if not cleaned:
        raise ValueError("model_id is required for OpenAI image rendering.")
    if not cleaned.lower().startswith(_OPENAI_IMAGE_MODEL_PREFIX):
        raise ValueError(
            "OpenAI image rendering requires a GPT Image model id "
            f"(for example {_OPENAI_DEFAULT_IMAGE_MODEL!r}); got {cleaned!r}."
        )
    return cleaned


def _normalize_openai_output_format(value: str | None) -> str:
    cleaned = str(value or _OPENAI_DEFAULT_OUTPUT_FORMAT).strip().lower()
    if cleaned == "jpg":
        cleaned = "jpeg"
    if cleaned not in _OPENAI_OUTPUT_FORMAT_VALUES:
        raise ValueError(
            "OPENAI_IMAGE_RENDER_OUTPUT_FORMAT must be one of "
            f"{sorted(_OPENAI_OUTPUT_FORMAT_VALUES)}; got {cleaned!r}."
        )
    return cleaned


def _normalize_openai_quality(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    cleaned = str(value).strip().lower()
    if cleaned not in _OPENAI_QUALITY_VALUES:
        raise ValueError(
            "OPENAI_IMAGE_RENDER_QUALITY must be one of "
            f"{sorted(_OPENAI_QUALITY_VALUES)}; got {cleaned!r}."
        )
    return cleaned


def _normalize_openai_output_compression(value: str | None) -> int | None:
    if value is None or not str(value).strip():
        return None
    try:
        parsed = int(str(value).strip())
    except ValueError as exc:
        raise ValueError(
            "OPENAI_IMAGE_RENDER_OUTPUT_COMPRESSION must be an integer from 0 to 100."
        ) from exc
    if parsed < 0 or parsed > 100:
        raise ValueError("OPENAI_IMAGE_RENDER_OUTPUT_COMPRESSION must be an integer from 0 to 100.")
    return parsed


def _normalize_openai_aspect_ratio_size(aspect_ratio: str | None) -> str:
    if aspect_ratio is None or not str(aspect_ratio).strip():
        return "auto"
    cleaned = str(aspect_ratio).strip().lower()
    if cleaned == "auto":
        return "auto"

    parts = cleaned.split(":")
    if len(parts) != 2:
        raise ValueError("aspect_ratio must be in the form 'W:H' for OpenAI image rendering.")
    try:
        width_ratio = int(parts[0].strip())
        height_ratio = int(parts[1].strip())
    except ValueError as exc:
        raise ValueError(
            "aspect_ratio must contain integer W:H values for OpenAI image rendering."
        ) from exc
    if width_ratio <= 0 or height_ratio <= 0:
        raise ValueError("aspect_ratio values must be positive for OpenAI image rendering.")
    if max(width_ratio, height_ratio) / min(width_ratio, height_ratio) > 3:
        raise ValueError(
            "GPT Image 2 size constraints require aspect ratios no wider than 3:1 or 1:3."
        )

    short_edge = 1024
    if width_ratio >= height_ratio:
        height = short_edge
        width = _round_to_multiple_of_16(short_edge * width_ratio / height_ratio)
    else:
        width = short_edge
        height = _round_to_multiple_of_16(short_edge * height_ratio / width_ratio)

    if width > 3840 or height > 3840:
        raise ValueError(
            f"OpenAI image size exceeds GPT Image 2 max edge constraint: {width}x{height}."
        )
    total_pixels = width * height
    if total_pixels < 655_360 or total_pixels > 8_294_400:
        raise ValueError(
            f"OpenAI image size violates GPT Image 2 pixel constraints: {width}x{height}."
        )
    return f"{width}x{height}"


def _round_to_multiple_of_16(value: float) -> int:
    rounded = int(round(value / 16.0) * 16)
    return max(16, rounded)


def _image_b64_from_openai_item(item: Any, *, output_index: int) -> str:
    if isinstance(item, dict):
        b64_json = item.get("b64_json")
    else:
        b64_json = getattr(item, "b64_json", None)
    if not isinstance(b64_json, str) or not b64_json.strip():
        raise RuntimeError(
            f"OpenAI image response missing b64_json at output_index={output_index}."
        )
    return b64_json.strip()


def _detect_image_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:6] in {b"GIF87a", b"GIF89a"}:
        return "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def _openai_content_type_for_format(output_format: str) -> str:
    content_type = _OPENAI_OUTPUT_FORMAT_CONTENT_TYPES.get(output_format)
    if not content_type:
        raise RuntimeError(f"Unsupported OpenAI output format: {output_format!r}")
    return content_type


def _openai_extension_for_format(output_format: str) -> str:
    if output_format == "jpeg":
        return ".jpg"
    return f".{output_format}"


def _openai_job_id_from_idempotency(idempotency_key: str) -> str:
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    return f"{_PROVIDER_OPENAI}:{digest}"


def _creative_request_error_from_openai_exception(
    exc: Exception,
    *,
    model_id: str,
) -> CreativeServiceRequestError:
    status_code = getattr(exc, "status_code", None)
    request_id = getattr(exc, "request_id", None)
    error_code: str | None = None
    details: dict[str, Any] = {"model_id": model_id}

    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        details["body"] = body
        raw_error = body.get("error")
        if isinstance(raw_error, dict):
            raw_code = raw_error.get("code") or raw_error.get("type")
            if isinstance(raw_code, str) and raw_code.strip():
                error_code = raw_code.strip()

    if isinstance(exc, APITimeoutError):
        message = f"OpenAI image rendering timed out: {exc}"
    elif isinstance(exc, APIConnectionError):
        message = f"OpenAI image rendering network error: {exc}"
    elif isinstance(exc, RateLimitError):
        message = f"OpenAI image rendering rate limit: {exc}"
        status_code = status_code or 429
    elif isinstance(exc, APIStatusError):
        message = f"OpenAI image rendering API error: {exc}"
    elif isinstance(exc, OpenAIError):
        message = f"OpenAI image rendering SDK error: {exc}"
    else:
        message = f"OpenAI image rendering request failed: {exc}"

    return CreativeServiceRequestError(
        message=message,
        status_code=status_code if isinstance(status_code, int) else None,
        error_code=error_code,
        request_id=request_id if isinstance(request_id, str) and request_id.strip() else None,
        details=details,
    )


class OpenAIImageRenderClient:
    def __init__(
        self,
        *,
        org_id: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        default_model: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.org_id = str(org_id).strip() if isinstance(org_id, str) and org_id.strip() else None
        self.default_model = _normalize_openai_model_id(default_model)
        self.output_format = _normalize_openai_output_format(
            os.getenv("OPENAI_IMAGE_RENDER_OUTPUT_FORMAT")
        )
        self.quality = _normalize_openai_quality(os.getenv("OPENAI_IMAGE_RENDER_QUALITY"))
        self.output_compression = _normalize_openai_output_compression(
            os.getenv("OPENAI_IMAGE_RENDER_OUTPUT_COMPRESSION")
        )
        self.timeout_seconds = float(
            timeout_seconds or settings.CREATIVE_SERVICE_TIMEOUT_SECONDS or 30.0
        )
        self._jobs: dict[str, CreativeServiceImageAdsJob] = {}

        if client is not None:
            self.client = client
            return

        resolved_api_key = (
            api_key or settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY") or ""
        ).strip()
        if not resolved_api_key:
            raise CreativeServiceConfigError(
                "OPENAI_API_KEY is required for OpenAI image rendering."
            )

        resolved_base_url = (
            base_url if base_url is not None else os.getenv("OPENAI_BASE_URL") or ""
        ).strip()
        client_kwargs: dict[str, Any] = {
            "api_key": resolved_api_key,
            "timeout": self.timeout_seconds,
        }
        if resolved_base_url:
            client_kwargs["base_url"] = resolved_base_url
        self.client = get_openai_client_class()(**client_kwargs)

    def create_image_ads(
        self,
        *,
        payload: CreativeServiceImageAdsCreateIn,
        idempotency_key: str,
    ) -> CreativeServiceImageAdsJob:
        cleaned_idempotency_key = str(idempotency_key or "").strip()
        if not cleaned_idempotency_key:
            raise CreativeServiceRequestError(
                "OpenAI image rendering requires a non-empty idempotency key."
            )
        if payload.count < 1:
            raise ValueError("count must be greater than zero for OpenAI image rendering.")
        if payload.reference_image_urls:
            raise CreativeServiceRequestError(
                "OpenAI image rendering does not accept reference_image_urls in MOS. "
                "Pass local reference_asset_ids instead."
            )

        model_id = _normalize_openai_model_id(payload.model_id or self.default_model)
        prompt = (payload.prompt or "").strip()
        if not prompt:
            raise ValueError("prompt is required for OpenAI image rendering.")
        if isinstance(payload.reference_text, str) and payload.reference_text.strip():
            prompt = f"{prompt}\n\nREFERENCE NOTES:\n{payload.reference_text.strip()}"

        size = _normalize_openai_aspect_ratio_size(payload.aspect_ratio)
        storage = MediaStorage()
        references, image_files = self._load_reference_images(
            storage=storage,
            reference_asset_ids=payload.reference_asset_ids,
        )

        request_kwargs: dict[str, Any] = {
            "model": model_id,
            "prompt": prompt,
            "n": int(payload.count),
            "size": size,
            "output_format": self.output_format,
            "extra_headers": {"Idempotency-Key": cleaned_idempotency_key},
        }
        if self.quality is not None:
            request_kwargs["quality"] = self.quality
        if self.output_compression is not None and self.output_format in {"jpeg", "webp"}:
            request_kwargs["output_compression"] = self.output_compression

        try:
            if image_files:
                response = self.client.images.edit(image=image_files, **request_kwargs)
            else:
                response = self.client.images.generate(**request_kwargs)
        except OpenAIError as exc:
            raise _creative_request_error_from_openai_exception(exc, model_id=model_id) from None
        except Exception as exc:  # noqa: BLE001
            raise CreativeServiceRequestError(
                "OpenAI image rendering request failed.",
                details={"model_id": model_id, "error": str(exc)},
            ) from None

        outputs = self._store_openai_outputs(
            storage=storage,
            response=response,
            output_format=self.output_format,
            prompt_used=prompt,
        )
        job_id = _openai_job_id_from_idempotency(cleaned_idempotency_key)
        job = CreativeServiceImageAdsJob(
            id=job_id,
            status="succeeded",
            prompt=prompt,
            count=int(payload.count),
            aspect_ratio=payload.aspect_ratio,
            model_id=model_id,
            error_detail=None,
            references=references,
            outputs=outputs,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self._jobs[job_id] = job
        return job

    def get_image_ads_job(self, *, job_id: str) -> CreativeServiceImageAdsJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise CreativeServiceRequestError(f"OpenAI image job not found: {job_id}")
        return job

    def _load_reference_images(
        self,
        *,
        storage: MediaStorage,
        reference_asset_ids: list[str],
    ) -> tuple[list[CreativeServiceAssetRef], list[tuple[str, bytes, str]]]:
        references: list[CreativeServiceAssetRef] = []
        image_files: list[tuple[str, bytes, str]] = []
        if not reference_asset_ids:
            return references, image_files

        with session_scope() as session:
            for position, raw_asset_id in enumerate(reference_asset_ids):
                asset_id = str(raw_asset_id or "").strip()
                if not asset_id:
                    raise CreativeServiceRequestError(
                        "reference_asset_ids must contain non-empty asset ids"
                    )
                try:
                    asset_uuid = UUID(asset_id)
                except ValueError as exc:
                    raise CreativeServiceRequestError(
                        "reference_asset_ids must contain UUID strings. "
                        f"Invalid asset_id={asset_id!r}"
                    ) from exc
                asset = session.get(Asset, asset_uuid)
                if asset is None:
                    raise CreativeServiceRequestError(f"Reference asset not found: {asset_id}")
                if self.org_id and str(asset.org_id) != self.org_id:
                    raise CreativeServiceRequestError(f"Reference asset org mismatch: {asset_id}")
                if asset.asset_kind != "image":
                    raise CreativeServiceRequestError(
                        f"Reference asset must be an image: {asset_id}"
                    )
                if not asset.storage_key:
                    raise CreativeServiceRequestError(
                        f"Reference asset is missing storage_key: {asset_id}"
                    )
                if asset.file_status and asset.file_status != "ready":
                    raise CreativeServiceRequestError(
                        "Reference asset is not ready "
                        f"(asset_id={asset_id}, file_status={asset.file_status})"
                    )
                if asset.expires_at and asset.expires_at <= datetime.now(timezone.utc):
                    raise CreativeServiceRequestError(
                        "Reference asset is expired "
                        f"(asset_id={asset_id}, expires_at={asset.expires_at})"
                    )

                data, downloaded_content_type = storage.download_bytes(key=asset.storage_key)
                if not data:
                    raise CreativeServiceRequestError(
                        f"Reference asset returned empty bytes: {asset_id}"
                    )
                content_type = (
                    str(asset.content_type).strip().lower()
                    if isinstance(asset.content_type, str) and asset.content_type.strip()
                    else None
                )
                if not content_type:
                    content_type = (
                        str(downloaded_content_type).split(";", 1)[0].strip().lower()
                        if isinstance(downloaded_content_type, str)
                        and downloaded_content_type.strip()
                        else None
                    )
                if not content_type:
                    content_type = _detect_image_mime(data)
                if not content_type.startswith("image/"):
                    raise CreativeServiceRequestError(
                        "Reference asset must resolve to image/* bytes "
                        f"(asset_id={asset_id}, content_type={content_type})"
                    )

                primary_uri = f"s3://{storage.bucket}/{asset.storage_key}"
                primary_url = storage.presign_get(bucket=storage.bucket, key=asset.storage_key)
                references.append(
                    CreativeServiceAssetRef(
                        asset_id=asset_id,
                        position=position,
                        primary_uri=primary_uri,
                        primary_url=primary_url,
                    )
                )
                suffix = mimetypes.guess_extension(content_type) or _openai_extension_for_format(
                    "png"
                )
                if suffix == ".jpe":
                    suffix = ".jpg"
                image_files.append((f"reference-{position + 1}{suffix}", data, content_type))
        return references, image_files

    def _store_openai_outputs(
        self,
        *,
        storage: MediaStorage,
        response: Any,
        output_format: str,
        prompt_used: str,
    ) -> list[CreativeServiceAssetRef]:
        response_data = getattr(response, "data", None)
        if not isinstance(response_data, list) or not response_data:
            raise RuntimeError("OpenAI image response did not include data[].")

        content_type = _openai_content_type_for_format(output_format)
        ext = _openai_extension_for_format(output_format)
        outputs: list[CreativeServiceAssetRef] = []
        for output_index, item in enumerate(response_data):
            b64_json = _image_b64_from_openai_item(item, output_index=output_index)
            try:
                image_bytes = base64.b64decode(b64_json, validate=True)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    f"OpenAI image output was not valid base64 at output_index={output_index}."
                ) from exc
            if not image_bytes:
                raise RuntimeError(f"OpenAI image output was empty at output_index={output_index}.")

            sha256 = hashlib.sha256(image_bytes).hexdigest()
            key = storage.build_key(sha256=sha256, ext=ext, kind="orig")
            if not storage.object_exists(bucket=storage.bucket, key=key):
                storage.upload_bytes(
                    bucket=storage.bucket,
                    key=key,
                    data=image_bytes,
                    content_type=content_type,
                    cache_control=IMMUTABLE_CACHE_CONTROL,
                )
            outputs.append(
                CreativeServiceAssetRef(
                    asset_id=f"openai:{sha256}",
                    output_index=output_index,
                    primary_uri=f"s3://{storage.bucket}/{key}",
                    primary_url=storage.presign_get(bucket=storage.bucket, key=key),
                    prompt_used=prompt_used,
                )
            )
        return outputs


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
                    "Higgsfield credentials are required. "
                    "Configure HF_KEY or HF_API_KEY + HF_API_SECRET."
                )
            self._auth_key = f"{api_key}:{api_secret}"

        self.timeout_seconds = float(
            timeout_seconds or settings.CREATIVE_SERVICE_TIMEOUT_SECONDS or 30.0
        )
        self.default_model = (default_model or settings.HIGGSFIELD_DEFAULT_MODEL or "").strip()
        if not self.default_model:
            raise CreativeServiceConfigError(
                "HIGGSFIELD_DEFAULT_MODEL is required for Higgsfield render provider."
            )
        self.default_resolution = (
            default_resolution or settings.HIGGSFIELD_DEFAULT_RESOLUTION or ""
        ).strip()

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
                "Higgsfield render currently supports at most one reference image URL "
                "per request in MOS integration."
            )

        downloaded_bytes, content_type = self._download_reference_image(
            reference_image_url=cleaned_urls[0]
        )
        public_url, upload_url = self._create_upload_url(content_type=content_type)
        self._upload_reference_bytes(
            upload_url=upload_url,
            content=downloaded_bytes,
            content_type=content_type,
        )
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
            message = _extract_error_detail(body or {}) or (
                f"Higgsfield request failed with HTTP {response.status_code}"
            )
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
                raise RuntimeError(
                    f"Higgsfield status response is missing status for request_id={request_id}."
                )

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
                detail = _extract_error_detail(status_data) or (
                    f"request_id={request_id} status={status_raw}"
                )
                failure_details.append(detail)
                continue

            if status_raw in {_HIGGS_STATUS_QUEUED, _HIGGS_STATUS_IN_PROGRESS}:
                continue

            raise RuntimeError(
                f"Unknown Higgsfield request status: {status_raw!r} "
                f"(request_id={request_id})."
            )

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
