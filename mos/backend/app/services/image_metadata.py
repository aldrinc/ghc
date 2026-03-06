from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Optional

from PIL import Image, ImageOps, JpegImagePlugin, UnidentifiedImageError

_SUPPORTED_IMAGE_FORMATS = ("JPEG", "PNG", "WEBP")
_FORMAT_TO_CONTENT_TYPE = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
_CONTENT_TYPE_TO_FORMAT = {value: key for key, value in _FORMAT_TO_CONTENT_TYPE.items()}
_BLOCKED_METADATA_TOKENS = ("exif", "xmp", "iptc", "gps")
_BLOCKED_JPEG_APP_MARKERS = {"APP1", "APP13"}


class ImageMetadataSanitizationError(ValueError):
    pass


@dataclass(frozen=True)
class SanitizedImage:
    content: bytes
    content_type: str


def strip_and_validate_image_metadata(*, content: bytes, content_type: Optional[str]) -> SanitizedImage:
    if not content:
        raise ImageMetadataSanitizationError("Image content is empty.")

    normalized_content_type = _normalize_content_type(content_type)

    try:
        with Image.open(io.BytesIO(content)) as source:
            source.load()
            output_format = _resolve_output_format(
                source_format=source.format,
                normalized_content_type=normalized_content_type,
            )
            if output_format not in _SUPPORTED_IMAGE_FORMATS:
                supported = ", ".join(fmt.lower() for fmt in _SUPPORTED_IMAGE_FORMATS)
                raise ImageMetadataSanitizationError(
                    f"Unsupported image format for metadata stripping: {output_format.lower()}. "
                    f"Supported formats: {supported}."
                )

            sanitized_image = ImageOps.exif_transpose(source)
            if output_format == "JPEG" and sanitized_image.mode not in {"RGB", "L", "CMYK"}:
                sanitized_image = sanitized_image.convert("RGB")

            save_kwargs = _build_save_kwargs(source=source, output_format=output_format)
            output_buffer = io.BytesIO()
            sanitized_image.save(output_buffer, format=output_format, **save_kwargs)
            sanitized_content = output_buffer.getvalue()
    except UnidentifiedImageError as exc:
        raise ImageMetadataSanitizationError("Image bytes are invalid or unreadable.") from exc
    except OSError as exc:
        raise ImageMetadataSanitizationError(f"Failed to sanitize image metadata: {exc}") from exc

    if not sanitized_content:
        raise ImageMetadataSanitizationError("Image metadata stripping produced empty output.")

    _validate_sanitized_image(content=sanitized_content, output_format=output_format)

    return SanitizedImage(
        content=sanitized_content,
        content_type=_FORMAT_TO_CONTENT_TYPE[output_format],
    )


def _normalize_content_type(content_type: Optional[str]) -> Optional[str]:
    if not isinstance(content_type, str):
        return None
    normalized = content_type.split(";", 1)[0].strip().lower()
    return normalized or None


def _resolve_output_format(*, source_format: Optional[str], normalized_content_type: Optional[str]) -> str:
    if isinstance(source_format, str) and source_format.strip():
        normalized_format = source_format.strip().upper()
        if normalized_format == "JPG":
            return "JPEG"
        return normalized_format
    if normalized_content_type and normalized_content_type in _CONTENT_TYPE_TO_FORMAT:
        return _CONTENT_TYPE_TO_FORMAT[normalized_content_type]
    raise ImageMetadataSanitizationError("Unable to determine image format for metadata stripping.")


def _build_save_kwargs(*, source: Image.Image, output_format: str) -> dict[str, object]:
    save_kwargs: dict[str, object] = {}

    icc_profile = source.info.get("icc_profile")
    if isinstance(icc_profile, (bytes, bytearray)) and icc_profile:
        save_kwargs["icc_profile"] = bytes(icc_profile)

    if output_format == "JPEG":
        quantization = getattr(source, "quantization", None)
        if isinstance(quantization, dict) and quantization:
            save_kwargs["qtables"] = quantization
            sampling = JpegImagePlugin.get_sampling(source)
            if isinstance(sampling, int) and sampling >= 0:
                save_kwargs["subsampling"] = sampling
        else:
            save_kwargs["quality"] = 95
        return save_kwargs

    if output_format == "WEBP":
        save_kwargs["quality"] = 95
        save_kwargs["method"] = 6
        if bool(source.info.get("lossless")):
            save_kwargs["lossless"] = True

    return save_kwargs


def _validate_sanitized_image(*, content: bytes, output_format: str) -> None:
    try:
        with Image.open(io.BytesIO(content)) as sanitized:
            sanitized.load()

            if len(sanitized.getexif()) > 0:
                raise ImageMetadataSanitizationError("EXIF metadata is still present after stripping.")

            blocked_info_keys = []
            for raw_key in sanitized.info.keys():
                key = str(raw_key).strip().lower()
                if key == "icc_profile":
                    continue
                if _is_blocked_metadata_key(key):
                    blocked_info_keys.append(str(raw_key))
            if blocked_info_keys:
                keys = ", ".join(sorted(blocked_info_keys))
                raise ImageMetadataSanitizationError(
                    f"Blocked metadata keys remain after stripping: {keys}."
                )

            if output_format == "JPEG":
                app_markers = getattr(sanitized, "applist", [])
                blocked_markers = [
                    marker
                    for marker, _payload in app_markers
                    if marker in _BLOCKED_JPEG_APP_MARKERS
                ]
                if blocked_markers:
                    markers = ", ".join(sorted(set(blocked_markers)))
                    raise ImageMetadataSanitizationError(
                        f"Blocked JPEG metadata segments remain after stripping: {markers}."
                    )
    except UnidentifiedImageError as exc:
        raise ImageMetadataSanitizationError("Sanitized image output is unreadable.") from exc
    except OSError as exc:
        raise ImageMetadataSanitizationError(
            f"Failed to validate sanitized image metadata: {exc}"
        ) from exc


def _is_blocked_metadata_key(key: str) -> bool:
    return any(token in key for token in _BLOCKED_METADATA_TOKENS)
