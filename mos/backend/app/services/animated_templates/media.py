from __future__ import annotations

import hashlib
import io
from typing import Any

from PIL import Image, UnidentifiedImageError


_DEFAULT_MAX_ANALYSIS_FRAMES = 360
_DEFAULT_SAMPLE_FRAME_COUNT = 12


def normalize_media_content_type(value: str | None) -> str:
    normalized = str(value or "").split(";", 1)[0].strip().lower()
    if not normalized:
        raise RuntimeError("Animated template source media is missing a content type.")
    return normalized


def sample_frame_indexes(frame_count: int, sample_count: int = _DEFAULT_SAMPLE_FRAME_COUNT) -> list[int]:
    if frame_count <= 0:
        raise RuntimeError("Animated template source frame count must be positive.")
    if sample_count <= 0:
        raise RuntimeError("Animated template sample count must be positive.")
    if frame_count <= sample_count:
        return list(range(frame_count))
    last_index = frame_count - 1
    return sorted({round(index * last_index / (sample_count - 1)) for index in range(sample_count)})


def _frame_png_evidence(image: Image.Image, frame_index: int) -> dict[str, Any]:
    image.seek(frame_index)
    frame = image.convert("RGBA")
    buffer = io.BytesIO()
    frame.save(buffer, format="PNG")
    png_bytes = buffer.getvalue()
    return {
        "frameIndex": frame_index,
        "sha256": hashlib.sha256(png_bytes).hexdigest(),
        "contentType": "image/png",
        "width": frame.width,
        "height": frame.height,
    }


def extract_animated_source_metadata(
    *,
    content: bytes,
    content_type: str,
    max_frames: int = _DEFAULT_MAX_ANALYSIS_FRAMES,
) -> dict[str, Any]:
    normalized_content_type = normalize_media_content_type(content_type)
    if not normalized_content_type.startswith("image/"):
        raise RuntimeError(
            "Animated template source analysis currently supports image media only. "
            f"content_type={normalized_content_type}"
        )
    if not content:
        raise RuntimeError("Animated template source media is empty.")

    source_sha256 = hashlib.sha256(content).hexdigest()
    try:
        with Image.open(io.BytesIO(content)) as image:
            width, height = image.size
            frame_count = int(getattr(image, "n_frames", 1) or 1)
            if frame_count > max_frames:
                raise RuntimeError(
                    "Animated template source has too many frames for the current analysis limit. "
                    f"frame_count={frame_count}, max_frames={max_frames}"
                )

            frame_durations_ms: list[int | None] = []
            for frame_index in range(frame_count):
                image.seek(frame_index)
                duration = image.info.get("duration")
                if isinstance(duration, (int, float)):
                    frame_durations_ms.append(max(0, int(duration)))
                else:
                    frame_durations_ms.append(None)

            duration_ms = (
                sum(duration for duration in frame_durations_ms if duration is not None)
                if all(duration is not None for duration in frame_durations_ms)
                else None
            )
            loop_count = image.info.get("loop")

            sampled_indexes = sample_frame_indexes(frame_count)
            return {
                "sourceSha256": source_sha256,
                "contentType": normalized_content_type,
                "sizeBytes": len(content),
                "format": str(image.format or "").lower() or None,
                "width": width,
                "height": height,
                "frameCount": frame_count,
                "isAnimated": bool(getattr(image, "is_animated", False) and frame_count > 1),
                "durationMs": duration_ms,
                "frameDurationsMs": frame_durations_ms,
                "loopCount": loop_count if isinstance(loop_count, int) else None,
                "sampleFrameIndexes": sampled_indexes,
                "sampleFrames": [
                    _frame_png_evidence(image, frame_index) for frame_index in sampled_indexes
                ],
            }
    except UnidentifiedImageError as exc:
        raise RuntimeError(
            "Animated template source media could not be decoded as an image. "
            f"content_type={normalized_content_type}"
        ) from exc
