from __future__ import annotations

import base64
import mimetypes
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx

from app.db.base import session_scope
from app.db.models import Asset
from app.schemas.creative_service import (
    CreativeServiceAssetRef,
    CreativeServiceImageAdsCreateIn,
    CreativeServiceImageAdsJob,
)
from app.services.creative_service_client import (
    CreativeServiceConfigError,
    CreativeServiceRequestError,
)
from app.services.media_storage import IMMUTABLE_CACHE_CONTROL, MediaStorage

_ASPECT_RATIO_RE = re.compile(r"^\s*(\d+)\s*:\s*(\d+)\s*$")
_DEFAULT_NANO_BANANA_MODEL = "models/gemini-2.5-flash-image"


@dataclass
class NanoBananaConfig:
    api_key: str
    base_url: str = "https://generativelanguage.googleapis.com"
    model: str = _DEFAULT_NANO_BANANA_MODEL
    request_timeout: float = 120.0

    @classmethod
    def from_env(cls) -> "NanoBananaConfig":
        return cls(api_key=os.environ.get("GEMINI_API_KEY", "").strip())


class NanoBananaClient:
    def __init__(self, config: NanoBananaConfig | None = None) -> None:
        self.config = config or NanoBananaConfig.from_env()
        if not self.config.api_key:
            raise CreativeServiceConfigError("GEMINI_API_KEY is required to generate images with embedded Freestyle")
        self.base_url = self.config.base_url.rstrip("/")

    def generate_image(
        self,
        *,
        prompt: str,
        reference_images: list[tuple[bytes, str]] | None = None,
        reference_text: str | None = None,
    ) -> tuple[bytes, str]:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Nano Banana prompt must be a non-empty string")
        if reference_text is not None and not isinstance(reference_text, str):
            raise ValueError("Nano Banana reference_text must be a string when provided")
        if reference_images is not None and not isinstance(reference_images, list):
            raise ValueError("Nano Banana reference_images must be a list when provided")

        url = f"{self.base_url}/v1beta/{self.config.model}:generateContent"
        parts: list[dict[str, Any]] = []
        combined_prompt = prompt.strip()
        if isinstance(reference_text, str) and reference_text.strip():
            combined_prompt = f"{combined_prompt}\n\nREFERENCE NOTES:\n{reference_text.strip()}"
        parts.append({"text": combined_prompt})

        if reference_images:
            for idx, (image_bytes, mime_type) in enumerate(reference_images):
                if not isinstance(image_bytes, (bytes, bytearray)) or not image_bytes:
                    raise ValueError(f"Nano Banana reference_images[{idx}] bytes must be non-empty")
                if not isinstance(mime_type, str) or not mime_type.strip():
                    raise ValueError(f"Nano Banana reference_images[{idx}] mime_type must be a non-empty string")
                parts.append(
                    {
                        "inlineData": {
                            "mimeType": mime_type.strip(),
                            "data": base64.b64encode(bytes(image_bytes)).decode("utf-8"),
                        }
                    }
                )
        payload = {"contents": [{"role": "user", "parts": parts}]}
        with httpx.Client(timeout=self.config.request_timeout) as client:
            response = client.post(url, params={"key": self.config.api_key}, json=payload)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text
                raise RuntimeError(
                    f"Nano Banana generateContent failed ({exc.response.status_code}): {detail}"
                ) from exc
        try:
            data: Any = response.json()
        except ValueError as exc:
            raise RuntimeError("Nano Banana response was not valid JSON") from exc
        if not isinstance(data, dict):
            raise RuntimeError("Nano Banana response must be a JSON object")
        return _extract_inline_image(data)


def _extract_inline_image(payload: dict[str, Any]) -> tuple[bytes, str]:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise RuntimeError("Nano Banana response missing candidates[]")
    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        content = cand.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            inline = part.get("inlineData")
            if not isinstance(inline, dict):
                continue
            mime = inline.get("mimeType")
            b64 = inline.get("data")
            if not isinstance(mime, str) or not mime:
                raise RuntimeError("Nano Banana inlineData.mimeType is required")
            if not isinstance(b64, str) or not b64:
                raise RuntimeError("Nano Banana inlineData.data is required")
            try:
                image_bytes = base64.b64decode(b64, validate=True)
            except Exception as exc:
                raise RuntimeError("Nano Banana inlineData.data was not valid base64") from exc
            if not image_bytes:
                raise RuntimeError("Nano Banana returned empty image bytes")
            return image_bytes, mime
    raise RuntimeError("Nano Banana response did not include an inline image (inlineData)")


class EmbeddedFreestyleImageRenderClient:
    """
    MOS-embedded port of Freestyle's image-ad service.

    This keeps the Freestyle image-ad behavior in-process for MOS so swipe-image
    generation no longer depends on the downstream Freestyle API server.
    """

    def __init__(self, *, org_id: str | None = None) -> None:
        self.org_id = str(org_id).strip() if isinstance(org_id, str) and org_id.strip() else None
        self._jobs: dict[str, CreativeServiceImageAdsJob] = {}
        self._jobs_by_idempotency: dict[str, str] = {}

    def create_image_ads(
        self,
        *,
        payload: CreativeServiceImageAdsCreateIn,
        idempotency_key: str,
    ) -> CreativeServiceImageAdsJob:
        cleaned_idempotency_key = str(idempotency_key or "").strip()
        if not cleaned_idempotency_key:
            raise CreativeServiceRequestError("Embedded Freestyle image rendering requires a non-empty idempotency key")
        existing_job_id = self._jobs_by_idempotency.get(cleaned_idempotency_key)
        if existing_job_id is not None:
            return self.get_image_ads_job(job_id=existing_job_id)

        if payload.reference_image_urls:
            raise CreativeServiceRequestError(
                "Embedded Freestyle image rendering does not accept reference_image_urls. "
                "Pass local reference_asset_ids instead."
            )

        cleaned_prompt = str(payload.prompt or "").strip()
        if not cleaned_prompt:
            raise CreativeServiceRequestError("prompt must be a non-empty string")

        if int(payload.count) < 1:
            raise CreativeServiceRequestError("count must be at least 1")

        cleaned_aspect_ratio = _normalize_aspect_ratio(payload.aspect_ratio)
        resolved_model_id = _resolve_model_id(payload.model_id)
        storage = MediaStorage()
        job_id = f"embedded-freestyle:{cleaned_idempotency_key}"
        created_at = datetime.now(timezone.utc)

        references, reference_images = self._load_reference_images(
            storage=storage,
            reference_asset_ids=payload.reference_asset_ids,
        )

        output_refs: list[CreativeServiceAssetRef] = []
        renderer = NanoBananaClient(NanoBananaConfig.from_env())
        renderer.config.model = resolved_model_id

        try:
            for idx in range(int(payload.count)):
                prompt_used = _build_variation_prompt(
                    base_prompt=cleaned_prompt,
                    index=idx,
                    aspect_ratio=cleaned_aspect_ratio,
                    total_count=int(payload.count),
                )
                image_bytes, content_type = renderer.generate_image(
                    prompt=prompt_used,
                    reference_images=reference_images or None,
                    reference_text=payload.reference_text,
                )
                output_refs.append(
                    self._store_generated_output(
                        storage=storage,
                        image_bytes=image_bytes,
                        content_type=content_type,
                        output_index=idx,
                        prompt_used=prompt_used,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            failed_job = CreativeServiceImageAdsJob(
                id=job_id,
                status="failed",
                prompt=cleaned_prompt,
                count=int(payload.count),
                aspect_ratio=cleaned_aspect_ratio,
                model_id=resolved_model_id,
                error_detail=str(exc),
                references=references,
                outputs=output_refs,
                created_at=created_at,
                updated_at=datetime.now(timezone.utc),
            )
            self._jobs[job_id] = failed_job
            self._jobs_by_idempotency[cleaned_idempotency_key] = job_id
            return failed_job

        succeeded_job = CreativeServiceImageAdsJob(
            id=job_id,
            status="succeeded",
            prompt=cleaned_prompt,
            count=int(payload.count),
            aspect_ratio=cleaned_aspect_ratio,
            model_id=resolved_model_id,
            error_detail=None,
            references=references,
            outputs=output_refs,
            created_at=created_at,
            updated_at=datetime.now(timezone.utc),
        )
        self._jobs[job_id] = succeeded_job
        self._jobs_by_idempotency[cleaned_idempotency_key] = job_id
        return succeeded_job

    def get_image_ads_job(self, *, job_id: str) -> CreativeServiceImageAdsJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise CreativeServiceRequestError(f"Embedded Freestyle image job not found: {job_id}")
        return job

    def _load_reference_images(
        self,
        *,
        storage: MediaStorage,
        reference_asset_ids: list[str],
    ) -> tuple[list[CreativeServiceAssetRef], list[tuple[bytes, str]]]:
        references: list[CreativeServiceAssetRef] = []
        reference_images: list[tuple[bytes, str]] = []
        if not reference_asset_ids:
            return references, reference_images

        with session_scope() as session:
            for position, raw_asset_id in enumerate(reference_asset_ids):
                asset_id = str(raw_asset_id or "").strip()
                if not asset_id:
                    raise CreativeServiceRequestError("reference_asset_ids must contain non-empty asset ids")
                try:
                    asset_uuid = UUID(asset_id)
                except ValueError as exc:
                    raise CreativeServiceRequestError(
                        f"reference_asset_ids must contain UUID strings. Invalid asset_id={asset_id!r}"
                    ) from exc
                asset = session.get(Asset, asset_uuid)
                if asset is None:
                    raise CreativeServiceRequestError(f"Reference asset not found: {asset_id}")
                if self.org_id and str(asset.org_id) != self.org_id:
                    raise CreativeServiceRequestError(f"Reference asset org mismatch: {asset_id}")
                if asset.asset_kind != "image":
                    raise CreativeServiceRequestError(f"Reference asset must be an image: {asset_id}")
                if not asset.storage_key:
                    raise CreativeServiceRequestError(f"Reference asset is missing storage_key: {asset_id}")
                if asset.file_status and asset.file_status != "ready":
                    raise CreativeServiceRequestError(
                        f"Reference asset is not ready (asset_id={asset_id}, file_status={asset.file_status})"
                    )
                if asset.expires_at and asset.expires_at <= datetime.now(timezone.utc):
                    raise CreativeServiceRequestError(
                        f"Reference asset is expired (asset_id={asset_id}, expires_at={asset.expires_at})"
                    )
                data, downloaded_content_type = storage.download_bytes(key=asset.storage_key)
                if not data:
                    raise CreativeServiceRequestError(f"Reference asset returned empty bytes: {asset_id}")
                content_type = (
                    str(asset.content_type).strip().lower()
                    if isinstance(asset.content_type, str) and asset.content_type.strip()
                    else None
                )
                if not content_type:
                    content_type = (
                        str(downloaded_content_type).split(";", 1)[0].strip().lower()
                        if isinstance(downloaded_content_type, str) and downloaded_content_type.strip()
                        else None
                    )
                if not content_type:
                    content_type = _detect_image_mime(data)
                if not content_type.startswith("image/"):
                    raise CreativeServiceRequestError(
                        f"Reference asset must resolve to image/* bytes (asset_id={asset_id}, content_type={content_type})"
                    )

                references.append(
                    CreativeServiceAssetRef(
                        asset_id=asset_id,
                        position=position,
                        primary_uri=f"s3://{storage.bucket}/{asset.storage_key}",
                        primary_url=storage.presign_get(bucket=storage.bucket, key=asset.storage_key),
                    )
                )
                reference_images.append((data, content_type))
        return references, reference_images

    def _store_generated_output(
        self,
        *,
        storage: MediaStorage,
        image_bytes: bytes,
        content_type: str,
        output_index: int,
        prompt_used: str,
    ) -> CreativeServiceAssetRef:
        ext = mimetypes.guess_extension(content_type) or ""
        if ext == ".jpe":
            ext = ".jpg"
        if not ext:
            raise RuntimeError(f"Unsupported Nano Banana content_type: {content_type!r}")

        sha256 = _sha256_hex(image_bytes)
        key = storage.build_key(sha256=sha256, ext=ext, kind="orig")
        if not storage.object_exists(bucket=storage.bucket, key=key):
            storage.upload_bytes(
                bucket=storage.bucket,
                key=key,
                data=image_bytes,
                content_type=content_type,
                cache_control=IMMUTABLE_CACHE_CONTROL,
            )
        return CreativeServiceAssetRef(
            asset_id=f"embedded-freestyle:{sha256}",
            output_index=output_index,
            primary_uri=f"s3://{storage.bucket}/{key}",
            primary_url=storage.presign_get(bucket=storage.bucket, key=key),
            prompt_used=prompt_used,
        )


def _resolve_model_id(model_id: str | None) -> str:
    cleaned = str(model_id or "").strip().lstrip("/")
    if not cleaned:
        return _DEFAULT_NANO_BANANA_MODEL
    if cleaned.startswith("models/"):
        return cleaned
    if cleaned.startswith("gemini-"):
        return f"models/{cleaned}"
    return cleaned


def _normalize_aspect_ratio(aspect_ratio: str | None) -> str | None:
    if aspect_ratio is None:
        return None
    cleaned = str(aspect_ratio).strip()
    if not cleaned:
        raise CreativeServiceRequestError("aspect_ratio must be a non-empty string when provided")
    match = _ASPECT_RATIO_RE.match(cleaned)
    if not match:
        raise CreativeServiceRequestError("aspect_ratio must be in the form 'W:H' (for example '9:16')")
    width = int(match.group(1))
    height = int(match.group(2))
    if width <= 0 or height <= 0:
        raise CreativeServiceRequestError("aspect_ratio values must be positive")
    return f"{width}:{height}"


def _build_variation_prompt(*, base_prompt: str, index: int, aspect_ratio: str | None, total_count: int) -> str:
    if int(total_count) <= 1:
        lines = [base_prompt.strip()]
        if aspect_ratio:
            lines.extend(["", f"Aspect ratio: {aspect_ratio}."])
        return "\n".join(lines).strip()

    directive = _variation_directive(index)
    lines = [base_prompt.strip(), "", directive]
    if aspect_ratio:
        lines.extend(["", f"Aspect ratio: {aspect_ratio}."])
    lines.append("")
    lines.append("Make this distinct from other variations while keeping the same core concept and brand cues.")
    return "\n".join(lines).strip()


def _variation_directive(index: int) -> str:
    compositions = [
        "Hero product shot",
        "Lifestyle scene with a person using the product",
        "Minimalist studio composition",
        "Flat lay arrangement",
        "Macro detail focus",
        "Dynamic action moment",
        "Before/after concept (no text, visual-only contrast)",
        "Premium editorial look",
        "Bold, high-energy composition",
        "Soft, cozy composition",
    ]
    camera_angles = [
        "Straight-on framing",
        "3/4 angle framing",
        "Top-down framing",
        "Low-angle framing",
        "Wide shot framing",
        "Tight close-up framing",
    ]
    lighting = [
        "Soft diffused lighting",
        "High-contrast dramatic lighting",
        "Bright daylight lighting",
        "Warm golden-hour lighting",
        "Cool neon accent lighting",
        "Clean studio lighting",
    ]
    palettes = [
        "Warm palette",
        "Cool palette",
        "Neutral palette",
        "Pastel palette",
        "High-saturation palette",
        "Monochrome palette with one accent color",
    ]
    backgrounds = [
        "Simple gradient background",
        "Textured background",
        "Outdoor setting background",
        "Indoor lifestyle background",
        "Abstract geometric background",
        "Clean white seamless background",
    ]

    composition = compositions[index % len(compositions)]
    camera_angle = camera_angles[(index * 3) % len(camera_angles)]
    lighting_setup = lighting[(index * 5) % len(lighting)]
    palette = palettes[(index * 7) % len(palettes)]
    background = backgrounds[(index * 11) % len(backgrounds)]
    return (
        f"Variation {index + 1}: {composition}. {camera_angle}. {lighting_setup}. "
        f"{palette}. {background}."
    )


def _detect_image_mime(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    raise CreativeServiceRequestError("Unsupported reference image type; expected jpeg/png/gif/webp")


def _sha256_hex(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()
