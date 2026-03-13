from __future__ import annotations

import io

from PIL import Image

from app.db.enums import AssetSourceEnum, AssetStatusEnum
from app.db.models import Asset, MetaAdSetSpec, MetaCreativeSpec
from app.routers import meta_ads as meta_ads_router
from app.services.paid_ads_qa import RULESET_VERSION


TEST_ORG_ID = "00000000-0000-0000-0000-000000000001"


def _jpeg_bytes() -> bytes:
    image = Image.new("RGB", (16, 16), color=(120, 180, 40))
    output = io.BytesIO()
    image.save(output, format="JPEG")
    return output.getvalue()


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
    client_id: str,
    product_id: str,
    campaign_id: str,
    batch_id: str,
    suffix: str,
) -> Asset:
    content = _jpeg_bytes()
    asset = Asset(
        org_id=TEST_ORG_ID,
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
        size_bytes=len(content),
        width=16,
        height=16,
        file_source="ai",
        file_status="ready",
        ai_metadata={"creativeGenerationBatchId": batch_id},
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


def _create_meta_publish_inputs(
    db_session,
    *,
    asset: Asset,
    campaign_id: str,
    experiment_key: str,
    with_targeting: bool = True,
) -> tuple[MetaCreativeSpec, MetaAdSetSpec]:
    creative_spec = MetaCreativeSpec(
        org_id=TEST_ORG_ID,
        asset_id=asset.id,
        campaign_id=campaign_id,
        name="Publish Creative",
        primary_text="Primary text",
        headline="Headline",
        description="Description",
        call_to_action_type="LEARN_MORE",
        destination_url="/presales",
        page_id="page_123",
        instagram_actor_id=None,
        status="draft",
        metadata_json={"experimentSpecId": experiment_key},
    )
    adset_spec = MetaAdSetSpec(
        org_id=TEST_ORG_ID,
        campaign_id=campaign_id,
        name="Launch Ad Set",
        status="draft",
        optimization_goal="OFFSITE_CONVERSIONS",
        billing_event="IMPRESSIONS",
        targeting={"geo_locations": {"countries": ["US"]}} if with_targeting else None,
        placements={"publisher_platforms": ["facebook"]},
        daily_budget=5000,
        lifetime_budget=None,
        bid_amount=None,
        start_time=None,
        end_time=None,
        promoted_object={"pixel_id": "pixel_123", "custom_event_type": "PURCHASE"},
        conversion_domain="shop.thehonestherbalist.com",
        metadata_json={"experimentSpecId": experiment_key},
    )
    db_session.add(creative_spec)
    db_session.add(adset_spec)
    db_session.commit()
    db_session.refresh(creative_spec)
    db_session.refresh(adset_spec)
    return creative_spec, adset_spec


def _upsert_meta_profile(api_client, *, client_id: str) -> None:
    response = api_client.put(
        f"/clients/{client_id}/paid-ads-qa/platforms/meta/profile",
        json={
            "rulesetVersion": RULESET_VERSION,
            "adAccountId": "act_123456",
            "pageId": "page_123",
            "pixelId": "pixel_123",
            "verifiedDomain": "shop.thehonestherbalist.com",
            "verifiedDomainStatus": "verified",
        },
    )
    assert response.status_code == 200


def _exclude_asset_from_publish(api_client, *, campaign_id: str, generation_key: str, asset_id: str) -> None:
    response = api_client.put(
        f"/meta/campaigns/{campaign_id}/publish-selections",
        json={
            "generationKey": generation_key,
            "decisions": [{"assetId": asset_id, "decision": "excluded"}],
        },
    )
    assert response.status_code == 200


def test_validate_meta_publish_plan_reports_blockers(api_client, db_session) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(api_client, suffix="publish-validate")
    asset = _create_asset(
        db_session,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        batch_id="latest-run",
        suffix="publish-validate",
    )
    _create_meta_publish_inputs(
        db_session,
        asset=asset,
        campaign_id=campaign_id,
        experiment_key="exp-validate",
        with_targeting=False,
    )
    _upsert_meta_profile(api_client, client_id=client_id)

    response = api_client.post(
        f"/meta/campaigns/{campaign_id}/publish-plan/validate",
        json={
            "generationKey": "batch:latest-run",
            "publishBaseUrl": "https://shop.thehonestherbalist.com",
            "campaignName": "Honest Herbalist Launch",
            "campaignObjective": "OUTCOME_SALES",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["items"][0]["status"] == "blocked"
    assert "missing targeting" in payload["items"][0]["blockers"][0].lower()


def test_validate_meta_publish_plan_blocks_when_all_assets_are_excluded(api_client, db_session) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(api_client, suffix="publish-all-excluded")
    asset = _create_asset(
        db_session,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        batch_id="latest-run",
        suffix="publish-all-excluded",
    )
    _create_meta_publish_inputs(
        db_session,
        asset=asset,
        campaign_id=campaign_id,
        experiment_key="exp-all-excluded",
        with_targeting=True,
    )
    _upsert_meta_profile(api_client, client_id=client_id)
    _exclude_asset_from_publish(
        api_client,
        campaign_id=campaign_id,
        generation_key="batch:latest-run",
        asset_id=str(asset.id),
    )

    response = api_client.post(
        f"/meta/campaigns/{campaign_id}/publish-plan/validate",
        json={
            "generationKey": "batch:latest-run",
            "publishBaseUrl": "https://shop.thehonestherbalist.com",
            "campaignName": "Honest Herbalist Launch",
            "campaignObjective": "OUTCOME_SALES",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["blockers"] == ["All creatives are excluded from the final Meta package for this generation."]
    assert payload["includedCount"] == 0
    assert payload["items"] == []


def test_publish_meta_run_creates_paused_entities_and_history(api_client, db_session, monkeypatch) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(api_client, suffix="publish-run")
    asset = _create_asset(
        db_session,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        batch_id="latest-run",
        suffix="publish-run",
    )
    _create_meta_publish_inputs(
        db_session,
        asset=asset,
        campaign_id=campaign_id,
        experiment_key="exp-publish",
        with_targeting=True,
    )
    _upsert_meta_profile(api_client, client_id=client_id)

    content = _jpeg_bytes()

    class _FakeStorage:
        def download_bytes(self, *, key: str, bucket: str | None = None) -> tuple[bytes, str]:
            _ = bucket
            assert key == "creative/publish-run.jpg"
            return content, "image/jpeg"

    class _FakeMetaClient:
        def upload_image(self, **kwargs):
            assert kwargs["ad_account_id"] == "act_123456"
            return {"images": {kwargs["filename"]: {"hash": "hash_123"}}}

        def create_campaign(self, **kwargs):
            assert kwargs["ad_account_id"] == "act_123456"
            assert kwargs["payload"]["status"] == "PAUSED"
            return {"id": "meta_campaign_123", "status": "PAUSED"}

        def create_adset(self, **kwargs):
            assert kwargs["payload"]["status"] == "PAUSED"
            return {"id": "meta_adset_123", "status": "PAUSED"}

        def create_adcreative(self, **kwargs):
            assert kwargs["payload"]["object_story_spec"]["page_id"] == "page_123"
            assert kwargs["payload"]["object_story_spec"]["link_data"]["link"] == "https://shop.thehonestherbalist.com/presales"
            return {"id": "meta_creative_123"}

        def create_ad(self, **kwargs):
            assert kwargs["payload"]["status"] == "PAUSED"
            return {"id": "meta_ad_123", "status": "PAUSED"}

    monkeypatch.setattr(meta_ads_router, "MediaStorage", _FakeStorage)
    monkeypatch.setattr(meta_ads_router, "_get_meta_client", lambda: _FakeMetaClient())

    publish_response = api_client.post(
        f"/meta/campaigns/{campaign_id}/publish-runs",
        json={
            "generationKey": "batch:latest-run",
            "publishBaseUrl": "https://shop.thehonestherbalist.com",
            "campaignName": "Honest Herbalist Launch",
            "campaignObjective": "OUTCOME_SALES",
            "buyingType": "AUCTION",
        },
    )

    assert publish_response.status_code == 200
    publish_payload = publish_response.json()
    assert publish_payload["status"] == "published"
    assert publish_payload["metaCampaignId"] == "meta_campaign_123"
    assert publish_payload["publishDomain"] == "shop.thehonestherbalist.com"
    assert len(publish_payload["items"]) == 1
    assert publish_payload["items"][0]["status"] == "published"
    assert publish_payload["items"][0]["metaCreativeId"] == "meta_creative_123"
    assert publish_payload["items"][0]["metaAdSetId"] == "meta_adset_123"
    assert publish_payload["items"][0]["metaAdId"] == "meta_ad_123"

    history_response = api_client.get(f"/meta/campaigns/{campaign_id}/publish-runs")
    assert history_response.status_code == 200
    history_payload = history_response.json()
    assert len(history_payload) == 1
    assert history_payload[0]["id"] == publish_payload["id"]
    assert history_payload[0]["items"][0]["metaAdId"] == "meta_ad_123"
