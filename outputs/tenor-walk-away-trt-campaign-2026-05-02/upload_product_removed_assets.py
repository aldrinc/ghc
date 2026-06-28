from __future__ import annotations

import hashlib
import io
import json
import mimetypes
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image
from sqlalchemy import select

from app.db.base import session_scope
from app.db.enums import AssetSourceEnum, AssetStatusEnum
from app.db.models import Asset, Campaign
from app.services.media_storage import IMMUTABLE_CACHE_CONTROL, MediaStorage

BATCH_ID = "tenor-walk-away-trt-product-removed-edit-20260503"
ASSET_BRIEF_ID = "brief_editorial_wound_scene"
CAMPAIGN_ID = "3ff5811c-741b-4dc2-8050-46506dea14bc"
CLIENT_ID = "70124684-505f-48af-a25c-5f7a79601fa0"
PRODUCT_ID = "8b89a76d-069c-41a6-be38-b7e4f4483460"


def image_size(image_bytes: bytes) -> tuple[int | None, int | None]:
    with Image.open(io.BytesIO(image_bytes)) as image:
        return image.size


def upload_image_asset(
    *,
    session,
    storage: MediaStorage,
    campaign: Campaign,
    output: dict[str, Any],
    image_path: Path,
) -> Asset:
    image_bytes = image_path.read_bytes()
    if not image_bytes:
        raise RuntimeError(f"Image file is empty: {image_path}")
    content_type = mimetypes.guess_type(str(image_path))[0] or "image/jpeg"
    ext = (mimetypes.guess_extension(content_type) or image_path.suffix or ".jpg").lstrip(".")
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
    width, height = image_size(image_bytes)

    old_asset_id = (((output.get("oldResult") or {}).get("assetId")) or "").strip() or None
    old_asset = session.get(Asset, old_asset_id) if old_asset_id else None
    source = output.get("source") if isinstance(output.get("source"), dict) else {}
    edit = output.get("edit") if isinstance(output.get("edit"), dict) else {}

    metadata = {
        "creativeGenerationBatchId": BATCH_ID,
        "assetBriefId": ASSET_BRIEF_ID,
        "productRemovedOnly": True,
        "productRemovalEdited": bool(edit.get("edited")),
        "productRemovalInstruction": edit.get("instruction"),
        "productRemovalModel": edit.get("model"),
        "sourceBatchAssetId": old_asset_id,
        "sourceSwipeTitle": source.get("sourceSwipeTitle"),
        "sourceCompanySwipeId": source.get("companySwipeId"),
        "createdBy": "manual_product_removal_edit_pass",
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    asset = Asset(
        org_id=campaign.org_id,
        client_id=CLIENT_ID,
        campaign_id=CAMPAIGN_ID,
        product_id=PRODUCT_ID,
        asset_brief_artifact_id=getattr(old_asset, "asset_brief_artifact_id", None),
        source_type=AssetSourceEnum.generated,
        status=AssetStatusEnum.approved,
        asset_kind="image",
        channel_id="meta",
        format="image",
        content={
            "source": "manual_product_removal_edit_pass",
            "sourceBatchAssetId": old_asset_id,
            "sourceSwipeTitle": source.get("sourceSwipeTitle"),
        },
        storage_key=key,
        content_type=content_type,
        size_bytes=len(image_bytes),
        width=width,
        height=height,
        alt=f"{output.get('key')} product removed edit",
        file_source="generated",
        file_status="ready",
        ai_metadata=metadata,
        tags=["campaign-creative", "meta", "product-removed-only"],
    )
    session.add(asset)
    session.flush()
    return asset


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: upload_product_removed_assets.py /path/to/manifest.json")
    manifest_path = Path(sys.argv[1])
    manifest = json.loads(manifest_path.read_text())
    outputs = manifest.get("outputs")
    if not isinstance(outputs, list) or len(outputs) != 30:
        raise RuntimeError(f"Expected 30 outputs in {manifest_path}")

    storage = MediaStorage()
    with session_scope() as session:
        campaign = session.scalars(select(Campaign).where(Campaign.id == CAMPAIGN_ID)).first()
        if campaign is None:
            raise RuntimeError(f"Campaign not found: {CAMPAIGN_ID}")
        rows = []
        for output in outputs:
            local_path = Path(((output.get("result") or {}).get("localPath") or ""))
            image_path = manifest_path.parent / "generated" / local_path.name
            if not image_path.exists():
                raise RuntimeError(f"Missing image for {output.get('key')}: {image_path}")
            asset = upload_image_asset(
                session=session,
                storage=storage,
                campaign=campaign,
                output=output,
                image_path=image_path,
            )
            rows.append(
                {
                    "key": output.get("key"),
                    "oldAssetId": ((output.get("oldResult") or {}).get("assetId")),
                    "assetId": str(asset.id),
                    "publicId": str(asset.public_id),
                    "storageKey": asset.storage_key,
                    "edited": bool((output.get("edit") or {}).get("edited")),
                }
            )
        session.commit()
    print(json.dumps({"batchId": BATCH_ID, "assetCount": len(rows), "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
