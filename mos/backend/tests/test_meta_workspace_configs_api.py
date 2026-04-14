from sqlalchemy import select

from app.db.models import MetaAdAccountConnection, MetaWorkspaceAdConfig
from app.routers import meta_ads as meta_ads_router
from app.services.integration_secrets import encrypt_secret_json


def _create_workspace(api_client, *, name: str) -> str:
    response = api_client.post("/clients", json={"name": name, "industry": "Retail"})
    assert response.status_code == 201
    return response.json()["id"]


def _seed_connection(
    db_session,
    *,
    org_id: str,
    name: str = "Reusable Meta Connection",
    ad_account_id: str = "act_123456",
) -> MetaAdAccountConnection:
    connection = MetaAdAccountConnection(
        org_id=org_id,
        name=name,
        ad_account_id=ad_account_id,
        ad_account_name="Primary Ad Account",
        business_manager_id="bm_123",
        business_manager_name="Primary Business",
        graph_api_version="v24.0",
        graph_api_base_url="https://graph.facebook.com",
        credential_type="access_token",
        credentials_encrypted=encrypt_secret_json({"accessToken": "meta-token"}),
        status="active",
        validation_status="valid",
    )
    db_session.add(connection)
    db_session.commit()
    db_session.refresh(connection)
    return connection


def test_create_workspace_meta_config_auto_provisions_dedicated_pixel(api_client, db_session, auth_context, monkeypatch):
    workspace_id = _create_workspace(api_client, name="Workspace Pixel Brand")
    connection = _seed_connection(db_session, org_id=auth_context.org_id)

    class _FakeMetaClient:
        def create_ad_pixel(self, **kwargs):
            assert kwargs["ad_account_id"] == "act_123456"
            assert kwargs["name"] == "Workspace Pixel Brand"
            return {"id": "pixel_123", "name": kwargs["name"]}

    monkeypatch.setattr(meta_ads_router, "_get_meta_client", lambda **kwargs: _FakeMetaClient())

    response = api_client.post(
        f"/meta/clients/{workspace_id}/configs",
        json={
            "connectionId": str(connection.id),
            "name": "Workspace Pixel Config",
            "isDefault": True,
            "status": "active",
            "metadata": {},
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["pixelId"] == "pixel_123"
    assert payload["dataSetId"] == "pixel_123"
    assert payload["metadata"]["metaPixelName"] == "Workspace Pixel Brand"
    assert payload["metadata"]["pixelProvisioning"]["status"] == "created"
    assert payload["metadata"]["pixelProvisioning"]["source"] == "mos.workspace_config_create"

    saved = db_session.scalar(
        select(MetaWorkspaceAdConfig).where(MetaWorkspaceAdConfig.client_id == workspace_id)
    )
    assert saved is not None
    assert saved.pixel_id == "pixel_123"
    assert saved.data_set_id == "pixel_123"


def test_create_workspace_meta_config_preserves_explicit_pixel_id(api_client, db_session, auth_context, monkeypatch):
    workspace_id = _create_workspace(api_client, name="Existing Pixel Brand")
    connection = _seed_connection(db_session, org_id=auth_context.org_id, ad_account_id="act_999999")

    def _unexpected_meta_client(**kwargs):
        raise AssertionError(f"Meta pixel provisioning should not run when pixelId is provided: {kwargs}")

    monkeypatch.setattr(meta_ads_router, "_get_meta_client", _unexpected_meta_client)

    response = api_client.post(
        f"/meta/clients/{workspace_id}/configs",
        json={
            "connectionId": str(connection.id),
            "name": "Explicit Pixel Config",
            "isDefault": True,
            "status": "active",
            "pixelId": "pixel_existing_123",
            "dataSetId": "dataset_existing_123",
            "metadata": {},
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["pixelId"] == "pixel_existing_123"
    assert payload["dataSetId"] == "dataset_existing_123"
    assert "pixelProvisioning" not in payload["metadata"]
