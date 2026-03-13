from app.db.enums import AssetSourceEnum, AssetStatusEnum
from app.db.models import Asset

TEST_ORG_ID = "00000000-0000-0000-0000-000000000001"


def _create_campaign_with_product(api_client, *, suffix: str) -> tuple[str, str, str]:
    client_resp = api_client.post("/clients", json={"name": f"Client {suffix}", "industry": "SaaS"})
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    product_resp = api_client.post(
        "/products",
        json={"clientId": client_id, "title": f"Product {suffix}"},
    )
    assert product_resp.status_code == 201
    product_id = product_resp.json()["id"]

    campaign_resp = api_client.post(
        "/campaigns",
        json={
            "client_id": client_id,
            "product_id": product_id,
            "name": f"Campaign {suffix}",
            "channels": ["facebook"],
            "asset_brief_types": ["image"],
        },
    )
    assert campaign_resp.status_code == 201
    return client_id, product_id, campaign_resp.json()["id"]


def _create_asset(
    db_session,
    *,
    org_id,
    client_id: str,
    product_id: str,
    campaign_id: str,
    batch_id: str,
    suffix: str,
) -> Asset:
    asset = Asset(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.approved,
        asset_kind="image",
        channel_id="facebook",
        format="image_ad",
        content={},
        storage_key=f"creative/{suffix}.jpg",
        content_type="image/jpeg",
        size_bytes=1234,
        width=1080,
        height=1080,
        file_source="ai",
        file_status="ready",
        ai_metadata={"creativeGenerationBatchId": batch_id},
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


def test_meta_publish_selection_lifecycle_is_generation_scoped(api_client, db_session) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(api_client, suffix="publish-selection")
    batch_key = "batch:latest-run"
    older_batch_key = "batch:older-run"

    campaign_asset = _create_asset(
        db_session,
        org_id=TEST_ORG_ID,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        batch_id="latest-run",
        suffix="latest",
    )
    second_campaign_asset = _create_asset(
        db_session,
        org_id=TEST_ORG_ID,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        batch_id="latest-run",
        suffix="latest-2",
    )

    save_resp = api_client.put(
        f"/meta/campaigns/{campaign_id}/publish-selections",
        json={
            "generationKey": batch_key,
            "decisions": [
                {"assetId": str(campaign_asset.id), "decision": "included"},
                {"assetId": str(second_campaign_asset.id), "decision": "excluded"},
            ],
        },
    )
    assert save_resp.status_code == 200
    save_payload = save_resp.json()
    assert {entry["assetId"]: entry["decision"] for entry in save_payload} == {
        str(campaign_asset.id): "included",
        str(second_campaign_asset.id): "excluded",
    }
    assert {entry["decidedByUserId"] for entry in save_payload} == {"test-user"}

    list_resp = api_client.get(f"/meta/campaigns/{campaign_id}/publish-selections?generationKey={batch_key}")
    assert list_resp.status_code == 200
    assert {entry["assetId"]: entry["decision"] for entry in list_resp.json()} == {
        str(campaign_asset.id): "included",
        str(second_campaign_asset.id): "excluded",
    }

    older_save_resp = api_client.put(
        f"/meta/campaigns/{campaign_id}/publish-selections",
        json={
            "generationKey": older_batch_key,
            "decisions": [{"assetId": str(campaign_asset.id), "decision": "excluded"}],
        },
    )
    assert older_save_resp.status_code == 200
    assert older_save_resp.json()[0]["generationKey"] == older_batch_key
    assert older_save_resp.json()[0]["decision"] == "excluded"

    list_latest_resp = api_client.get(f"/meta/campaigns/{campaign_id}/publish-selections?generationKey={batch_key}")
    assert list_latest_resp.status_code == 200
    assert {entry["assetId"]: entry["decision"] for entry in list_latest_resp.json()} == {
        str(campaign_asset.id): "included",
        str(second_campaign_asset.id): "excluded",
    }

    clear_resp = api_client.put(
        f"/meta/campaigns/{campaign_id}/publish-selections",
        json={
            "generationKey": batch_key,
            "decisions": [{"assetId": str(second_campaign_asset.id), "decision": None}],
        },
    )
    assert clear_resp.status_code == 200
    clear_payload = clear_resp.json()
    assert len(clear_payload) == 1
    assert clear_payload[0]["campaignId"] == campaign_id
    assert clear_payload[0]["assetId"] == str(campaign_asset.id)
    assert clear_payload[0]["generationKey"] == batch_key
    assert clear_payload[0]["decision"] == "included"
    assert clear_payload[0]["decidedByUserId"] == "test-user"
    assert clear_payload[0]["id"]
    assert clear_payload[0]["createdAt"]
    assert clear_payload[0]["updatedAt"]


def test_meta_publish_selection_rejects_assets_outside_campaign(api_client, db_session) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(api_client, suffix="publish-selection-owner")
    other_client_id, other_product_id, other_campaign_id = _create_campaign_with_product(
        api_client,
        suffix="publish-selection-other",
    )

    wrong_campaign_asset = _create_asset(
        db_session,
        org_id=TEST_ORG_ID,
        client_id=other_client_id,
        product_id=other_product_id,
        campaign_id=other_campaign_id,
        batch_id="other-run",
        suffix="other",
    )

    response = api_client.put(
        f"/meta/campaigns/{campaign_id}/publish-selections",
        json={
            "generationKey": "batch:latest-run",
            "decisions": [{"assetId": str(wrong_campaign_asset.id), "decision": "included"}],
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == {
        "message": "Some campaign assets were not found for publish selection.",
        "missingAssetIds": [str(wrong_campaign_asset.id)],
    }
