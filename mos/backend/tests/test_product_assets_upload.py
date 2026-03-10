from app.config import settings
from app.db.models import Product


def test_upload_product_assets_returns_clear_error_when_media_storage_not_configured(
    api_client, db_session, seed_data, monkeypatch
):
    product = Product(
        org_id=seed_data["client"].org_id,
        client_id=seed_data["client"].id,
        title="Test Product",
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    monkeypatch.setattr(settings, "MEDIA_STORAGE_BUCKET", None)

    resp = api_client.post(
        f"/products/{product.id}/assets",
        files=[("files", ("test.png", b"not-a-real-png", "image/png"))],
    )
    assert resp.status_code == 500
    assert resp.json() == {"detail": "MEDIA_STORAGE_BUCKET is required"}


def test_upload_product_assets_rejects_unsupported_image_mime_type(api_client, db_session, seed_data):
    product = Product(
        org_id=seed_data["client"].org_id,
        client_id=seed_data["client"].id,
        title="Test Product",
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    resp = api_client.post(
        f"/products/{product.id}/assets",
        files=[("files", ("test.heic", b"fake-heic-bytes", "image/heic"))],
    )

    assert resp.status_code == 400
    assert resp.json() == {
        "detail": (
            "Unsupported file type for test.heic (image/heic). "
            "Allowed: Images (png, jpeg, webp, gif), videos (mp4, webm, mov), documents (pdf, doc, docx)."
        )
    }
