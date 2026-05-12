from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from app.services.animated_templates.media import (
    extract_animated_source_metadata,
    normalize_media_content_type,
)


_OUTPUT_CONTENT_TYPES = {
    "gif": "image/gif",
    "webp": "image/webp",
}


@dataclass(frozen=True)
class RenderedAnimatedTemplateArtifact:
    content: bytes
    content_type: str
    output_format: str
    sha256: str
    size_bytes: int
    metadata: dict[str, Any]


def _is_source_passthrough_manifest(manifest: dict[str, Any]) -> bool:
    layers = manifest.get("layers") or []
    if not layers:
        return False
    for layer in layers:
        if not isinstance(layer, dict):
            return False
        if layer.get("policy") != "locked_source":
            return False
        if layer.get("renderOwner") != "source_pixels":
            return False
    return True


def render_source_passthrough(
    *,
    source_content: bytes,
    source_content_type: str,
    manifest: dict[str, Any],
    output_format: str,
    expected_source_sha256: str | None = None,
) -> RenderedAnimatedTemplateArtifact:
    normalized_output_format = str(output_format or "").strip().lower()
    expected_content_type = _OUTPUT_CONTENT_TYPES.get(normalized_output_format)
    if expected_content_type is None:
        raise RuntimeError(
            "Source-passthrough renderer currently supports gif and webp outputs only. "
            f"output_format={output_format}"
        )

    normalized_source_content_type = normalize_media_content_type(source_content_type)
    if normalized_source_content_type != expected_content_type:
        raise RuntimeError(
            "Source-passthrough renderer does not transcode animated media. "
            f"source_content_type={normalized_source_content_type}, output_format={normalized_output_format}"
        )
    if not _is_source_passthrough_manifest(manifest):
        raise RuntimeError(
            "Source-passthrough renderer requires every layer to be locked_source/source_pixels."
        )

    source_sha256 = hashlib.sha256(source_content).hexdigest()
    if expected_source_sha256 and source_sha256 != expected_source_sha256:
        raise RuntimeError(
            "Source-passthrough renderer source hash mismatch. "
            f"expected={expected_source_sha256}, actual={source_sha256}"
        )

    metadata = extract_animated_source_metadata(
        content=source_content,
        content_type=normalized_source_content_type,
    )
    return RenderedAnimatedTemplateArtifact(
        content=source_content,
        content_type=normalized_source_content_type,
        output_format=normalized_output_format,
        sha256=source_sha256,
        size_bytes=len(source_content),
        metadata={
            "renderer": "source_passthrough",
            "source": metadata,
        },
    )
