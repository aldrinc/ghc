from __future__ import annotations

import io

import pytest
from PIL import Image, PngImagePlugin

from app.services.image_metadata import (
    ImageMetadataSanitizationError,
    strip_and_validate_image_metadata,
)


def _jpeg_with_exif() -> bytes:
    image = Image.new("RGB", (16, 16), color=(200, 120, 40))
    exif = Image.Exif()
    exif[0x010E] = "private-description"
    output = io.BytesIO()
    image.save(output, format="JPEG", exif=exif)
    return output.getvalue()


def _png_with_metadata() -> bytes:
    image = Image.new("RGBA", (16, 16), color=(20, 80, 220, 255))
    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_text("Comment", "sensitive note")
    pnginfo.add_text("XML:com.adobe.xmp", "<xmpmeta>private</xmpmeta>")
    output = io.BytesIO()
    image.save(output, format="PNG", pnginfo=pnginfo)
    return output.getvalue()


def test_strip_and_validate_image_metadata_removes_jpeg_exif() -> None:
    source = _jpeg_with_exif()
    with Image.open(io.BytesIO(source)) as before:
        assert len(before.getexif()) > 0

    sanitized = strip_and_validate_image_metadata(content=source, content_type="image/jpeg")

    assert sanitized.content_type == "image/jpeg"
    with Image.open(io.BytesIO(sanitized.content)) as after:
        assert len(after.getexif()) == 0
        lowered_keys = {str(key).strip().lower() for key in after.info.keys()}
        assert "exif" not in lowered_keys


def test_strip_and_validate_image_metadata_removes_png_text_chunks() -> None:
    source = _png_with_metadata()
    with Image.open(io.BytesIO(source)) as before:
        lowered_keys = {str(key).strip().lower() for key in before.info.keys()}
        assert "comment" in lowered_keys
        assert any("xmp" in key for key in lowered_keys)

    sanitized = strip_and_validate_image_metadata(content=source, content_type="image/png")

    assert sanitized.content_type == "image/png"
    with Image.open(io.BytesIO(sanitized.content)) as after:
        lowered_keys = {str(key).strip().lower() for key in after.info.keys()}
        assert "comment" not in lowered_keys
        assert not any("xmp" in key for key in lowered_keys)


def test_strip_and_validate_image_metadata_rejects_unsupported_format() -> None:
    image = Image.new("RGB", (8, 8), color=(255, 0, 0))
    output = io.BytesIO()
    image.save(output, format="GIF")

    with pytest.raises(ImageMetadataSanitizationError, match="Unsupported image format"):
        strip_and_validate_image_metadata(content=output.getvalue(), content_type="image/gif")
