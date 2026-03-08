from __future__ import annotations

import io

from PIL import Image

from app.db.enums import AssetSourceEnum, AssetStatusEnum
from app.db.models import Asset
from app.routers import meta_ads as meta_ads_router


def _jpeg_with_exif() -> bytes:
    image = Image.new("RGB", (16, 16), color=(120, 180, 40))
    exif = Image.Exif()
    exif[0x010E] = "private-description"
    output = io.BytesIO()
    image.save(output, format="JPEG", exif=exif)
    return output.getvalue()


def test_upload_meta_asset_strips_metadata_before_meta_upload(
    api_client,
    db_session,
    seed_data,
    monkeypatch,
) -> None:
    source_bytes = _jpeg_with_exif()
    with Image.open(io.BytesIO(source_bytes)) as image_before:
        assert len(image_before.getexif()) > 0

    asset = Asset(
        org_id=seed_data["client"].org_id,
        client_id=seed_data["client"].id,
        campaign_id=seed_data["campaign"].id,
        experiment_id=seed_data["experiment"].id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.approved,
        asset_kind="image",
        channel_id="meta",
        format="image",
        content={},
        storage_key="creative/test-image.jpg",
        content_type="image/jpeg",
        size_bytes=len(source_bytes),
        width=16,
        height=16,
        file_source="ai",
        file_status="ready",
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    class _FakeStorage:
        def download_bytes(self, *, key: str, bucket: str | None = None) -> tuple[bytes, str]:
            assert key == "creative/test-image.jpg"
            _ = bucket
            return source_bytes, "image/jpeg"

    captured: dict[str, object] = {}

    class _FakeMetaClient:
        def upload_image(
            self,
            *,
            ad_account_id: str,
            filename: str,
            content: bytes,
            content_type: str | None = None,
            name: str | None = None,
        ) -> dict[str, object]:
            captured["ad_account_id"] = ad_account_id
            captured["filename"] = filename
            captured["content"] = content
            captured["content_type"] = content_type
            captured["name"] = name
            return {"images": {filename: {"hash": "meta-hash-123"}}}

    monkeypatch.setattr(meta_ads_router, "MediaStorage", _FakeStorage)
    monkeypatch.setattr(meta_ads_router, "_get_meta_client", lambda: _FakeMetaClient())

    response = api_client.post(
        f"/meta/assets/{asset.id}/upload",
        json={"requestId": "req-meta-upload-1", "adAccountId": "123456"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["meta_image_hash"] == "meta-hash-123"
    assert captured["content_type"] == "image/jpeg"
    assert captured["ad_account_id"] == "123456"

    uploaded = captured["content"]
    assert isinstance(uploaded, bytes)
    with Image.open(io.BytesIO(uploaded)) as image_after:
        assert len(image_after.getexif()) == 0
        lowered_keys = {str(key).strip().lower() for key in image_after.info.keys()}
        assert "exif" not in lowered_keys


def test_upload_meta_asset_fails_when_image_bytes_are_invalid(
    api_client,
    db_session,
    seed_data,
    monkeypatch,
) -> None:
    invalid_bytes = b"not-a-valid-image"

    asset = Asset(
        org_id=seed_data["client"].org_id,
        client_id=seed_data["client"].id,
        campaign_id=seed_data["campaign"].id,
        experiment_id=seed_data["experiment"].id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.approved,
        asset_kind="image",
        channel_id="meta",
        format="image",
        content={},
        storage_key="creative/invalid-image.jpg",
        content_type="image/jpeg",
        size_bytes=len(invalid_bytes),
        width=None,
        height=None,
        file_source="ai",
        file_status="ready",
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    class _FakeStorage:
        def download_bytes(self, *, key: str, bucket: str | None = None) -> tuple[bytes, str]:
            assert key == "creative/invalid-image.jpg"
            _ = bucket
            return invalid_bytes, "image/jpeg"

    class _FakeMetaClient:
        def upload_image(self, **kwargs):  # pragma: no cover - this must never run for invalid input.
            raise AssertionError(f"Meta upload should not run for invalid image bytes: {kwargs}")

    monkeypatch.setattr(meta_ads_router, "MediaStorage", _FakeStorage)
    monkeypatch.setattr(meta_ads_router, "_get_meta_client", lambda: _FakeMetaClient())

    response = api_client.post(
        f"/meta/assets/{asset.id}/upload",
        json={"requestId": "req-meta-upload-invalid", "adAccountId": "123456"},
    )

    assert response.status_code == 400
    assert "metadata sanitization failed" in response.json()["detail"].lower()
