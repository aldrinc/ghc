from __future__ import annotations

import hashlib
import io
import mimetypes
import os
from typing import Optional

from PIL import Image
from sqlalchemy.orm import Session

from app.db.enums import AssetSourceEnum, AssetStatusEnum
from app.db.models import Asset
from app.services.media_storage import MediaStorage


def create_product_upload_asset(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    product_id: str,
    content_bytes: bytes,
    filename: Optional[str],
    content_type: str,
    asset_kind: str,
    tags: Optional[list[str]] = None,
    alt: Optional[str] = None,
) -> Asset:
    if not content_bytes:
        raise ValueError("Uploaded file is empty.")

    ext: Optional[str] = None
    if content_type:
        ext = mimetypes.guess_extension(content_type)
    if not ext and filename:
        ext = os.path.splitext(filename)[1] or None
    if not ext:
        raise ValueError("Unable to determine file extension for upload.")
    ext = ext.lstrip(".")

    sha256 = hashlib.sha256(content_bytes).hexdigest()
    storage = MediaStorage()
    key = storage.build_key(sha256=sha256, ext=ext, kind="orig")
    if not storage.object_exists(bucket=storage.bucket, key=key):
        storage.upload_bytes(
            bucket=storage.bucket,
            key=key,
            data=content_bytes,
            content_type=content_type,
            cache_control="public, max-age=31536000, immutable",
        )

    width: Optional[int] = None
    height: Optional[int] = None
    if asset_kind == "image":
        try:
            with Image.open(io.BytesIO(content_bytes)) as img:
                width, height = img.size
        except Exception as exc:
            raise ValueError("Invalid image file.") from exc

    metadata: dict[str, str] = {}
    if filename:
        metadata["filename"] = filename

    asset = Asset(
        org_id=org_id,
        client_id=client_id,
        source_type=AssetSourceEnum.upload,
        status=AssetStatusEnum.approved,
        asset_kind=asset_kind,
        channel_id="product",
        format=asset_kind,
        content={},
        product_id=product_id,
        storage_key=key,
        content_type=content_type,
        size_bytes=len(content_bytes),
        width=width,
        height=height,
        alt=alt,
        file_source="upload",
        file_status="ready",
        ai_metadata=metadata or None,
        tags=tags or [],
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset
