from __future__ import annotations

import hashlib
import io

import pytest
from PIL import Image

from app.schemas.animated_templates import AnimatedTemplateRenderRequest
from app.services.animated_templates.render_plan import build_render_plan
from app.services.animated_templates.renderer import render_source_passthrough


def _animated_gif_bytes() -> bytes:
    first = Image.new("RGB", (10, 10), "white")
    second = Image.new("RGB", (10, 10), "black")
    output = io.BytesIO()
    first.save(output, format="GIF", save_all=True, append_images=[second], duration=100, loop=0)
    return output.getvalue()


def _source_passthrough_manifest() -> dict:
    return {
        "schemaVersion": 1,
        "canvas": {"width": 10, "height": 10},
        "timeline": {"durationMs": 200, "frameCount": 2},
        "layers": [
            {
                "id": "locked_source_pixels",
                "type": "source_frames",
                "policy": "locked_source",
                "renderOwner": "source_pixels",
                "sourceFrameIndexes": [0, 1],
            }
        ],
        "productReplacement": {"hasCompetitorProductSlot": False},
    }


def test_render_plan_marks_all_source_layers_as_source_passthrough() -> None:
    render_request = AnimatedTemplateRenderRequest.model_validate(
        {"outputFormats": ["gif"], "renderMode": "deterministic"}
    )
    plan = build_render_plan(
        manifest=_source_passthrough_manifest(),
        render_request=render_request,
    )

    assert plan["rendererStrategy"] == "source_passthrough"
    assert plan["requiresAiModel"] is False


def test_source_passthrough_renderer_returns_original_verified_gif() -> None:
    source = _animated_gif_bytes()
    artifact = render_source_passthrough(
        source_content=source,
        source_content_type="image/gif",
        manifest=_source_passthrough_manifest(),
        output_format="gif",
        expected_source_sha256=hashlib.sha256(source).hexdigest(),
    )

    assert artifact.content == source
    assert artifact.content_type == "image/gif"
    assert artifact.output_format == "gif"
    assert artifact.size_bytes == len(source)
    assert artifact.metadata["renderer"] == "source_passthrough"
    assert artifact.metadata["source"]["frameCount"] == 2


def test_source_passthrough_renderer_rejects_transcoding() -> None:
    with pytest.raises(RuntimeError, match="does not transcode"):
        render_source_passthrough(
            source_content=_animated_gif_bytes(),
            source_content_type="image/gif",
            manifest=_source_passthrough_manifest(),
            output_format="webp",
        )


def test_source_passthrough_renderer_rejects_unlocked_layers() -> None:
    manifest = _source_passthrough_manifest()
    manifest["layers"][0]["policy"] = "deterministic_rebuild"

    with pytest.raises(RuntimeError, match="locked_source/source_pixels"):
        render_source_passthrough(
            source_content=_animated_gif_bytes(),
            source_content_type="image/gif",
            manifest=manifest,
            output_format="gif",
        )
