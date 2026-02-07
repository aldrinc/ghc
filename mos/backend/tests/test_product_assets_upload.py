from app.config import settings
from app.db.models import Product


def test_upload_product_assets_returns_clear_error_when_media_storage_not_configured(
    api_client, db_session, seed_data, monkeypatch
):
    product = Product(
        org_id=seed_data["client"].org_id,
        client_id=seed_data["client"].id,
        name="Test Product",
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

