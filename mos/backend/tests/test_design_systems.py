from copy import deepcopy
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.enums import AssetSourceEnum, AssetStatusEnum
from app.db.models import Asset
from app.routers import design_systems as design_systems_router
from app.services.design_system_generation import load_base_tokens_template


def _base_tokens() -> dict:
    return deepcopy(load_base_tokens_template())


def test_first_design_system_sets_client_default(api_client: TestClient):
    client_resp = api_client.post(
        "/clients", json={"name": "Design System Client", "industry": "SaaS"}
    )
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    first_resp = api_client.post(
        "/design-systems",
        json={"name": "First DS", "tokens": _base_tokens(), "clientId": client_id},
    )
    assert first_resp.status_code == 201
    first_id = first_resp.json()["id"]

    client_after_first = api_client.get(f"/clients/{client_id}")
    assert client_after_first.status_code == 200
    assert client_after_first.json()["design_system_id"] == first_id

    second_tokens = _base_tokens()
    second_tokens["brand"]["name"] = "Second DS Brand"
    second_resp = api_client.post(
        "/design-systems",
        json={"name": "Second DS", "tokens": second_tokens, "clientId": client_id},
    )
    assert second_resp.status_code == 201

    client_after_second = api_client.get(f"/clients/{client_id}")
    assert client_after_second.status_code == 200
    assert client_after_second.json()["design_system_id"] == first_id


def test_create_design_system_allows_text_tokens_coupled_to_brand(api_client: TestClient):
    client_resp = api_client.post(
        "/clients", json={"name": "Design System Client", "industry": "SaaS"}
    )
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    tokens = _base_tokens()
    tokens["cssVars"]["--color-text"] = "var(--color-brand)"

    resp = api_client.post(
        "/design-systems",
        json={"name": "Brand Ink DS", "tokens": tokens, "clientId": client_id},
    )
    assert resp.status_code == 201


def test_update_design_system_allows_low_contrast_muted_text(api_client: TestClient):
    client_resp = api_client.post(
        "/clients", json={"name": "Design System Client", "industry": "SaaS"}
    )
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    create_resp = api_client.post(
        "/design-systems",
        json={"name": "Valid DS", "tokens": _base_tokens(), "clientId": client_id},
    )
    assert create_resp.status_code == 201
    design_system_id = create_resp.json()["id"]

    invalid_tokens = _base_tokens()
    invalid_tokens["cssVars"]["--color-muted"] = "#cbd5e1"

    update_resp = api_client.patch(
        f"/design-systems/{design_system_id}",
        json={"tokens": invalid_tokens},
    )
    assert update_resp.status_code == 200


def test_create_design_system_allows_layout_token_updates(api_client: TestClient):
    client_resp = api_client.post(
        "/clients", json={"name": "Design System Client", "industry": "SaaS"}
    )
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    tokens = _base_tokens()
    tokens["cssVars"]["--reviews-height"] = "auto"

    resp = api_client.post(
        "/design-systems",
        json={"name": "Invalid DS", "tokens": tokens, "clientId": client_id},
    )
    assert resp.status_code == 201


def test_update_design_system_allows_layout_token_updates(api_client: TestClient):
    client_resp = api_client.post(
        "/clients", json={"name": "Design System Client", "industry": "SaaS"}
    )
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    create_resp = api_client.post(
        "/design-systems",
        json={"name": "Valid DS", "tokens": _base_tokens(), "clientId": client_id},
    )
    assert create_resp.status_code == 201
    design_system_id = create_resp.json()["id"]

    invalid_tokens = _base_tokens()
    invalid_tokens["cssVars"]["--cta-height-lg"] = "72px"

    update_resp = api_client.patch(
        f"/design-systems/{design_system_id}",
        json={"tokens": invalid_tokens},
    )
    assert update_resp.status_code == 200


def test_upload_design_system_logo_updates_brand_logo_token(api_client: TestClient, monkeypatch):
    client_resp = api_client.post(
        "/clients", json={"name": "Design System Client", "industry": "SaaS"}
    )
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    create_resp = api_client.post(
        "/design-systems",
        json={"name": "Valid DS", "tokens": _base_tokens(), "clientId": client_id},
    )
    assert create_resp.status_code == 201
    design_system_id = create_resp.json()["id"]

    fake_public_id = uuid4()

    def _fake_upload(
        *,
        session,
        org_id: str,
        client_id: str,
        content_bytes: bytes,
        filename: str | None,
        content_type: str,
        tags: list[str] | None = None,
        alt: str | None = None,
    ):
        _ = content_bytes
        _ = filename
        asset = Asset(
            org_id=org_id,
            client_id=client_id,
            source_type=AssetSourceEnum.upload,
            status=AssetStatusEnum.approved,
            asset_kind="image",
            channel_id="brand",
            format="image",
            content={},
            public_id=fake_public_id,
            storage_key="assets/fake-logo.png",
            content_type=content_type,
            size_bytes=123,
            width=128,
            height=48,
            alt=alt,
            file_source="upload",
            file_status="ready",
            tags=tags or [],
        )
        session.add(asset)
        session.commit()
        session.refresh(asset)
        return asset

    monkeypatch.setattr(design_systems_router, "create_client_logo_upload_asset", _fake_upload)

    upload_resp = api_client.post(
        f"/design-systems/{design_system_id}/logo",
        files=[("file", ("logo.png", b"fake-image-bytes", "image/png"))],
    )
    assert upload_resp.status_code == 201
    body = upload_resp.json()
    assert body["publicId"] == str(fake_public_id)
    assert body["url"] == f"/public/assets/{fake_public_id}"
    assert body["designSystem"]["tokens"]["brand"]["logoAssetPublicId"] == str(fake_public_id)


def test_upload_design_system_logo_rejects_unsupported_file_type(api_client: TestClient):
    client_resp = api_client.post(
        "/clients", json={"name": "Design System Client", "industry": "SaaS"}
    )
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    create_resp = api_client.post(
        "/design-systems",
        json={"name": "Valid DS", "tokens": _base_tokens(), "clientId": client_id},
    )
    assert create_resp.status_code == 201
    design_system_id = create_resp.json()["id"]

    upload_resp = api_client.post(
        f"/design-systems/{design_system_id}/logo",
        files=[("file", ("logo.txt", b"not-image", "text/plain"))],
    )
    assert upload_resp.status_code == 400
    assert "Unsupported logo file type" in (upload_resp.json().get("detail") or "")
