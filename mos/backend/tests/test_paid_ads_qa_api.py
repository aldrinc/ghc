from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.db.enums import ArtifactTypeEnum, AssetSourceEnum, AssetStatusEnum
from app.db.models import Artifact, Asset, Campaign, ClientUserPreference, MetaAdSetSpec, MetaCreativeSpec
from app.routers import paid_ads_qa as paid_ads_qa_router
from app.services import paid_ads_qa as paid_ads_qa_service
from app.services.paid_ads_qa import LEGACY_RULESET_VERSION, RULESET_VERSION


def _create_client(api_client, *, name: str = "Paid Ads QA Client") -> str:
    response = api_client.post("/clients", json={"name": name, "industry": "Retail"})
    assert response.status_code == 201
    return response.json()["id"]


def _create_campaign_with_product(api_client, *, suffix: str) -> tuple[str, str, str]:
    client_id = _create_client(api_client, name=f"Paid Ads QA {suffix}")
    product_resp = api_client.post("/products", json={"clientId": client_id, "title": f"Product {suffix}"})
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


def _complete_meta_profile_payload() -> dict:
    return {
        "rulesetVersion": RULESET_VERSION,
        "businessManagerId": "bm-123",
        "businessManagerName": "Marks BM",
        "pageId": "123456",
        "pageName": "Marks Page",
        "adAccountId": "act_123456",
        "adAccountName": "Marks Account",
        "paymentMethodType": "credit_card",
        "paymentMethodStatus": "active",
        "pixelId": "pixel-123",
        "dataSetId": "dataset-123",
        "dataSetShopifyPartnerInstalled": True,
        "dataSetDataSharingLevel": "maximum",
        "dataSetAssignedToAdAccount": True,
        "verifiedDomain": "example.com",
        "verifiedDomainStatus": "verified",
        "attributionClickWindow": "7d",
        "attributionViewWindow": "1d",
        "viewThroughEnabled": False,
        "trackingProvider": "triple_whale",
        "trackingUrlParameters": "utm_source=meta&utm_medium=paid",
        "metadata": {},
    }


def _mock_passthrough_graph_refresh(monkeypatch) -> None:
    monkeypatch.setattr(
        paid_ads_qa_router,
        "refresh_meta_platform_profile_from_graph",
        lambda *, profile, ruleset_version: profile,
    )


def _mock_hydrated_graph_refresh(monkeypatch, *, overrides: dict | None = None) -> None:
    overrides = overrides or {}

    def _refresh(*, profile, ruleset_version):
        refreshed = {
            **profile,
            **_complete_meta_profile_payload(),
            "platform": "meta",
            "rulesetVersion": ruleset_version,
        }
        metadata = dict(profile.get("metadata") or {})
        metadata["metaGraphValidation"] = {
            "apiVersion": "v-test",
            "lastValidatedAt": "2026-03-10T21:45:00+00:00",
            "validatedFields": [
                "pageId",
                "pageName",
                "adAccountId",
                "adAccountName",
                "businessManagerId",
                "businessManagerName",
                "paymentMethodStatus",
                "paymentMethodType",
                "pixelId",
                "dataSetId",
                "dataSetAssignedToAdAccount",
            ],
        }
        refreshed["metadata"] = metadata
        refreshed.update(overrides)
        return refreshed

    monkeypatch.setattr(
        paid_ads_qa_router,
        "refresh_meta_platform_profile_from_graph",
        _refresh,
    )


def _create_funnel_scoped_brief(
    *,
    db_session,
    campaign: Campaign,
    client_id: str,
    brief_id: str,
    funnel_id: str,
) -> None:
    brief_artifact = Artifact(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=str(campaign.id),
        type=ArtifactTypeEnum.asset_brief,
        data={
            "asset_briefs": [
                {
                    "id": brief_id,
                    "campaignId": str(campaign.id),
                    "clientId": client_id,
                    "funnelId": funnel_id,
                    "experimentId": f"exp-{brief_id}",
                    "requirements": [{"channel": "facebook", "format": "image_ad"}],
                }
            ]
        },
    )
    db_session.add(brief_artifact)
    db_session.commit()


def _set_selected_storefront_domain(
    *,
    db_session,
    campaign: Campaign,
    client_id: str,
    user_external_id: str = "test-user",
    storefront_domain: str,
) -> None:
    preference = ClientUserPreference(
        org_id=campaign.org_id,
        client_id=client_id,
        user_external_id=user_external_id,
        selected_shop_storefront_domain=storefront_domain,
    )
    db_session.add(preference)
    db_session.commit()


def _seed_campaign_ready_meta_objects(
    *,
    db_session,
    client_id: str,
    product_id: str,
    campaign_id: str,
    brief_id: str = "brief-campaign-history",
    funnel_id: str | None = None,
) -> None:
    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None
    resolved_funnel_id = funnel_id or str(uuid4())
    brief_artifact = Artifact(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        type=ArtifactTypeEnum.asset_brief,
        data={
            "asset_briefs": [
                {
                    "id": brief_id,
                    "campaignId": campaign_id,
                    "clientId": client_id,
                    "funnelId": resolved_funnel_id,
                    "experimentId": "exp-campaign-history",
                    "requirements": [{"channel": "facebook", "format": "image_ad"}],
                }
            ]
        },
    )
    db_session.add(brief_artifact)
    db_session.commit()

    asset = Asset(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.qa_passed,
        asset_kind="image",
        channel_id="facebook",
        format="image_ad",
        content={"kind": "creative"},
        storage_key="creative/campaign-history.jpg",
        content_type="image/jpeg",
        size_bytes=1234,
        width=1080,
        height=1080,
        file_source="ai",
        file_status="ready",
        ai_metadata={"assetBriefId": brief_id},
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    creative_spec = MetaCreativeSpec(
        org_id=campaign.org_id,
        campaign_id=campaign.id,
        asset_id=asset.id,
        name="Campaign QA History Creative",
        primary_text="Compliant primary text.",
        headline="Compliant headline",
        description="Privacy Policy. Contact support@example.com",
        call_to_action_type="Learn More",
        destination_url="https://example.com/offer",
        status="draft",
        metadata_json={},
    )
    adset_spec = MetaAdSetSpec(
        org_id=campaign.org_id,
        campaign_id=campaign.id,
        name="Campaign QA History Ad Set",
        status="draft",
        metadata_json={},
    )
    db_session.add_all([creative_spec, adset_spec])
    db_session.commit()


def test_paid_ads_ruleset_api_exposes_structured_rules(api_client) -> None:
    summary_resp = api_client.get("/paid-ads-qa/rulesets")
    assert summary_resp.status_code == 200
    summary_payload = summary_resp.json()
    summary_versions = {entry["version"] for entry in summary_payload}
    assert LEGACY_RULESET_VERSION in summary_versions
    assert RULESET_VERSION in summary_versions
    assert all(entry["ruleCount"] >= 10 for entry in summary_payload)

    ruleset_resp = api_client.get(f"/paid-ads-qa/rulesets/{RULESET_VERSION}")
    assert ruleset_resp.status_code == 200
    ruleset = ruleset_resp.json()
    rule_ids = {rule["ruleId"] for rule in ruleset["rules"]}
    assert "META-ACCOUNT-001" in rule_ids
    assert "META-COPY-002" in rule_ids
    assert "TTK-ACCOUNT-001" in rule_ids


def test_meta_platform_profile_v2_accepts_mos_runtime_tracking_for_account_008() -> None:
    profile = _complete_meta_profile_payload()
    profile["dataSetShopifyPartnerInstalled"] = False
    profile["dataSetDataSharingLevel"] = "standard"
    profile["trackingProvider"] = "mos"
    profile["metadata"] = {
        "mosMetaTracking": {
            "status": "active",
            "channel": "meta",
            "mode": "public_funnel_runtime",
            "pixelId": "pixel-123",
            "browserEvents": ["PageView", "InitiateCheckout"],
            "internalEvents": ["page_view", "cta_click"],
        }
    }

    result = paid_ads_qa_service.evaluate_platform_profile(
        platform="meta",
        profile=profile,
        ruleset_version=RULESET_VERSION,
    )

    failing_rule_ids = {finding["ruleId"] for finding in result["findings"]}
    assert "META-ACCOUNT-008" not in failing_rule_ids


def test_meta_platform_profile_assessment_returns_blockers(api_client, monkeypatch, tmp_path) -> None:
    client_id = _create_client(api_client, name="Meta Profile Assessment")
    _mock_passthrough_graph_refresh(monkeypatch)

    report_path = tmp_path / "meta-profile-report.md"
    monkeypatch.setattr(
        paid_ads_qa_router,
        "write_report_file",
        lambda **_kwargs: str(report_path),
    )

    profile_payload = {
        "rulesetVersion": RULESET_VERSION,
        "pageId": "123456",
        "adAccountId": "act_123456",
        "paymentMethodType": "paypal",
        "paymentMethodStatus": "inactive",
        "metadata": {},
    }
    put_resp = api_client.put(
        f"/clients/{client_id}/paid-ads-qa/platforms/meta/profile",
        json=profile_payload,
    )
    assert put_resp.status_code == 200

    assessment_resp = api_client.post(f"/clients/{client_id}/paid-ads-qa/platforms/meta/assessment")
    assert assessment_resp.status_code == 200
    assessment = assessment_resp.json()
    assert assessment["status"] == "failed"
    assert assessment["reportFilePath"] == str(report_path)
    rule_ids = {finding["ruleId"] for finding in assessment["findings"]}
    assert "META-ACCOUNT-001" in rule_ids
    assert "META-ACCOUNT-004" in rule_ids
    assert "META-ACCOUNT-005" in rule_ids
    assert "META-ACCOUNT-006" in rule_ids


def test_meta_platform_profile_assessment_refreshes_live_profile_and_persists_validation(
    api_client,
    monkeypatch,
    tmp_path,
) -> None:
    client_id = _create_client(api_client, name="Meta Profile Live Refresh")
    _mock_hydrated_graph_refresh(monkeypatch)

    report_path = tmp_path / "meta-profile-live-report.md"
    monkeypatch.setattr(
        paid_ads_qa_router,
        "write_report_file",
        lambda **_kwargs: str(report_path),
    )

    assessment_resp = api_client.post(f"/clients/{client_id}/paid-ads-qa/platforms/meta/assessment")
    assert assessment_resp.status_code == 200
    assessment = assessment_resp.json()
    assert assessment["status"] == "passed"
    assert assessment["reportFilePath"] == str(report_path)
    assert assessment["metadata"]["profileValidation"]["lastValidatedAt"] == "2026-03-10T21:45:00+00:00"

    profile_resp = api_client.get(f"/clients/{client_id}/paid-ads-qa/platforms/meta/profile")
    assert profile_resp.status_code == 200
    profile = profile_resp.json()
    assert profile["businessManagerId"] == "bm-123"
    assert profile["pageId"] == "123456"
    assert profile["adAccountId"] == "act_123456"
    assert profile["metadata"]["metaGraphValidation"]["lastValidatedAt"] == "2026-03-10T21:45:00+00:00"


def test_meta_campaign_paid_ads_qa_evaluates_copy_and_landing_page(
    api_client,
    db_session,
    monkeypatch,
    tmp_path,
) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(api_client, suffix="campaign-qa")
    _mock_passthrough_graph_refresh(monkeypatch)

    profile_resp = api_client.put(
        f"/clients/{client_id}/paid-ads-qa/platforms/meta/profile",
        json=_complete_meta_profile_payload(),
    )
    assert profile_resp.status_code == 200

    report_path = tmp_path / "campaign-report.md"
    monkeypatch.setattr(
        paid_ads_qa_router,
        "write_report_file",
        lambda **_kwargs: str(report_path),
    )
    monkeypatch.setattr(
        paid_ads_qa_service,
        "_landing_page_snapshot",
        lambda url: {
            "requestedUrl": url,
            "finalUrl": url,
            "statusCode": 200,
            "bodyText": "Under construction. Privacy Policy. Contact support@example.com",
        },
    )

    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None
    funnel_id = str(uuid4())
    brief_id = "brief-campaign-qa"
    _create_funnel_scoped_brief(
        db_session=db_session,
        campaign=campaign,
        client_id=client_id,
        brief_id=brief_id,
        funnel_id=funnel_id,
    )

    asset = Asset(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.qa_passed,
        asset_kind="image",
        channel_id="facebook",
        format="image_ad",
        content={"kind": "creative"},
        storage_key="creative/campaign-qa.jpg",
        content_type="image/jpeg",
        size_bytes=1234,
        width=1080,
        height=1080,
        file_source="ai",
        file_status="ready",
        ai_metadata={"assetBriefId": brief_id},
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    creative_spec = MetaCreativeSpec(
        org_id=campaign.org_id,
        campaign_id=campaign.id,
        asset_id=asset.id,
        name="Campaign QA Creative",
        primary_text="We know you have diabetes. Vote now.",
        headline="Are you ugly?",
        description="This page explains the offer.",
        call_to_action_type="Learn More",
        destination_url="https://example.com/offer",
        status="draft",
        metadata_json={},
    )
    adset_spec = MetaAdSetSpec(
        org_id=campaign.org_id,
        campaign_id=campaign.id,
        name="Campaign QA Ad Set",
        status="draft",
        metadata_json={},
    )
    db_session.add_all([creative_spec, adset_spec])
    db_session.commit()

    run_resp = api_client.post(
        f"/campaigns/{campaign_id}/paid-ads-qa/runs",
        json={"platform": "meta", "rulesetVersion": RULESET_VERSION, "funnelId": funnel_id},
    )
    assert run_resp.status_code == 200
    run_payload = run_resp.json()
    assert run_payload["status"] == "failed"
    assert run_payload["reportFilePath"] == str(report_path)
    rule_ids = {finding["ruleId"] for finding in run_payload["findings"]}
    assert "META-COPY-002" in rule_ids
    assert "META-COPY-004" in rule_ids
    assert "META-COPY-005" in rule_ids
    assert "META-LP-004" in rule_ids

    report_resp = api_client.get(f"/campaigns/{campaign_id}/paid-ads-qa/runs/{run_payload['id']}/report.md")
    assert report_resp.status_code == 200
    assert "Paid Ads QA Report" in report_resp.text
    assert "META-COPY-002" in report_resp.text


def test_meta_campaign_paid_ads_qa_lists_previous_runs(
    api_client,
    db_session,
    monkeypatch,
    tmp_path,
) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(api_client, suffix="campaign-qa-history")
    _mock_passthrough_graph_refresh(monkeypatch)

    profile_resp = api_client.put(
        f"/clients/{client_id}/paid-ads-qa/platforms/meta/profile",
        json=_complete_meta_profile_payload(),
    )
    assert profile_resp.status_code == 200

    report_path = tmp_path / "campaign-history-report.md"
    monkeypatch.setattr(
        paid_ads_qa_router,
        "write_report_file",
        lambda **_kwargs: str(report_path),
    )
    monkeypatch.setattr(
        paid_ads_qa_service,
        "_landing_page_snapshot",
        lambda url: {
            "requestedUrl": url,
            "finalUrl": url,
            "statusCode": 200,
            "bodyText": "Privacy Policy. Contact support@example.com",
        },
    )

    funnel_id = str(uuid4())
    _seed_campaign_ready_meta_objects(
        db_session=db_session,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        funnel_id=funnel_id,
    )

    first_run_resp = api_client.post(
        f"/campaigns/{campaign_id}/paid-ads-qa/runs",
        json={"platform": "meta", "rulesetVersion": RULESET_VERSION, "funnelId": funnel_id},
    )
    assert first_run_resp.status_code == 200
    first_run = first_run_resp.json()

    second_run_resp = api_client.post(
        f"/campaigns/{campaign_id}/paid-ads-qa/runs",
        json={
            "platform": "meta",
            "rulesetVersion": RULESET_VERSION,
            "reviewBaseUrl": "http://localhost:5275",
            "funnelId": funnel_id,
        },
    )
    assert second_run_resp.status_code == 200
    second_run = second_run_resp.json()

    list_resp = api_client.get(f"/campaigns/{campaign_id}/paid-ads-qa/runs")
    assert list_resp.status_code == 200
    runs = list_resp.json()

    assert [run["id"] for run in runs] == [second_run["id"], first_run["id"]]
    assert runs[0]["findings"] == []
    assert runs[1]["findings"] == []
    assert runs[0]["metadata"]["reviewBaseUrl"] == "http://localhost:5275"
    assert runs[1]["metadata"]["reviewBaseUrl"] is None


def test_meta_campaign_paid_ads_qa_defaults_to_latest_generation_scope(
    api_client,
    db_session,
    monkeypatch,
    tmp_path,
) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(api_client, suffix="campaign-qa-generation-scope")
    _mock_passthrough_graph_refresh(monkeypatch)

    profile_resp = api_client.put(
        f"/clients/{client_id}/paid-ads-qa/platforms/meta/profile",
        json=_complete_meta_profile_payload(),
    )
    assert profile_resp.status_code == 200

    report_path = tmp_path / "campaign-generation-scope-report.md"
    monkeypatch.setattr(
        paid_ads_qa_router,
        "write_report_file",
        lambda **_kwargs: str(report_path),
    )
    monkeypatch.setattr(
        paid_ads_qa_service,
        "_landing_page_snapshot",
        lambda url: {
            "requestedUrl": url,
            "finalUrl": url,
            "statusCode": 200,
            "bodyText": "Privacy Policy. Contact support@example.com",
        },
    )

    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None
    funnel_id = str(uuid4())
    older_brief_id = "brief-campaign-qa-generation-older"
    latest_brief_id = "brief-campaign-qa-generation-latest"
    _create_funnel_scoped_brief(
        db_session=db_session,
        campaign=campaign,
        client_id=client_id,
        brief_id=older_brief_id,
        funnel_id=funnel_id,
    )
    _create_funnel_scoped_brief(
        db_session=db_session,
        campaign=campaign,
        client_id=client_id,
        brief_id=latest_brief_id,
        funnel_id=funnel_id,
    )

    older_asset = Asset(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.qa_passed,
        asset_kind="image",
        channel_id="facebook",
        format="image_ad",
        content={"kind": "creative"},
        storage_key="creative/campaign-qa-generation-older.jpg",
        content_type="image/jpeg",
        size_bytes=1234,
        width=1080,
        height=1080,
        file_source="ai",
        file_status="ready",
        ai_metadata={"creativeGenerationBatchId": "batch-older", "assetBriefId": older_brief_id},
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    latest_asset = Asset(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.qa_passed,
        asset_kind="image",
        channel_id="facebook",
        format="image_ad",
        content={"kind": "creative"},
        storage_key="creative/campaign-qa-generation-latest.jpg",
        content_type="image/jpeg",
        size_bytes=1234,
        width=1080,
        height=1080,
        file_source="ai",
        file_status="ready",
        ai_metadata={"creativeGenerationBatchId": "batch-latest", "assetBriefId": latest_brief_id},
        created_at=datetime.now(timezone.utc),
    )
    db_session.add_all([older_asset, latest_asset])
    db_session.commit()
    db_session.refresh(latest_asset)

    creative_spec = MetaCreativeSpec(
        org_id=campaign.org_id,
        campaign_id=campaign.id,
        asset_id=latest_asset.id,
        name="Latest Generation Creative",
        primary_text="Compliant latest-generation copy.",
        headline="Latest generation headline",
        description="Compliant latest-generation description.",
        call_to_action_type="Learn More",
        destination_url="https://example.com/offer",
        status="draft",
        metadata_json={},
    )
    adset_spec = MetaAdSetSpec(
        org_id=campaign.org_id,
        campaign_id=campaign.id,
        name="Latest Generation Ad Set",
        status="draft",
        metadata_json={},
    )
    db_session.add_all([creative_spec, adset_spec])
    db_session.commit()

    run_resp = api_client.post(
        f"/campaigns/{campaign_id}/paid-ads-qa/runs",
        json={
            "platform": "meta",
            "rulesetVersion": RULESET_VERSION,
            "reviewBaseUrl": "http://localhost:5275",
            "funnelId": funnel_id,
        },
    )
    assert run_resp.status_code == 200
    run_payload = run_resp.json()
    assert run_payload["status"] == "passed"
    assert run_payload["metadata"]["generationKey"] == "batch:batch-latest"
    assert run_payload["metadata"]["readyAssetCount"] == 1
    assert run_payload["findings"] == []


def test_meta_campaign_paid_ads_qa_scopes_generation_to_requested_funnel(
    api_client,
    db_session,
    monkeypatch,
    tmp_path,
) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(api_client, suffix="campaign-qa-funnel-scope")
    _mock_passthrough_graph_refresh(monkeypatch)

    profile_resp = api_client.put(
        f"/clients/{client_id}/paid-ads-qa/platforms/meta/profile",
        json=_complete_meta_profile_payload(),
    )
    assert profile_resp.status_code == 200

    report_path = tmp_path / "campaign-funnel-scope-report.md"
    monkeypatch.setattr(
        paid_ads_qa_router,
        "write_report_file",
        lambda **_kwargs: str(report_path),
    )
    monkeypatch.setattr(
        paid_ads_qa_service,
        "_landing_page_snapshot",
        lambda url: {
            "requestedUrl": url,
            "finalUrl": url,
            "statusCode": 200,
            "bodyText": "Privacy Policy. Contact support@example.com",
        },
    )

    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None
    funnel_id = str(uuid4())
    other_funnel_id = str(uuid4())
    brief_id = "brief-campaign-qa-funnel-scope"
    other_brief_id = "brief-campaign-qa-funnel-scope-other"
    _create_funnel_scoped_brief(
        db_session=db_session,
        campaign=campaign,
        client_id=client_id,
        brief_id=brief_id,
        funnel_id=funnel_id,
    )
    _create_funnel_scoped_brief(
        db_session=db_session,
        campaign=campaign,
        client_id=client_id,
        brief_id=other_brief_id,
        funnel_id=other_funnel_id,
    )

    scoped_asset = Asset(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.qa_passed,
        asset_kind="image",
        channel_id="facebook",
        format="image_ad",
        content={"kind": "creative"},
        storage_key="creative/campaign-qa-funnel-scope.jpg",
        content_type="image/jpeg",
        size_bytes=1234,
        width=1080,
        height=1080,
        file_source="ai",
        file_status="ready",
        ai_metadata={"creativeGenerationBatchId": "batch-funnel-scope", "assetBriefId": brief_id},
        created_at=datetime.now(timezone.utc),
    )
    other_funnel_asset = Asset(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.qa_passed,
        asset_kind="image",
        channel_id="facebook",
        format="image_ad",
        content={"kind": "creative"},
        storage_key="creative/campaign-qa-funnel-scope-other.jpg",
        content_type="image/jpeg",
        size_bytes=1234,
        width=1080,
        height=1080,
        file_source="ai",
        file_status="ready",
        ai_metadata={"creativeGenerationBatchId": "batch-funnel-scope", "assetBriefId": other_brief_id},
        created_at=datetime.now(timezone.utc),
    )
    db_session.add_all([scoped_asset, other_funnel_asset])
    db_session.commit()
    db_session.refresh(scoped_asset)

    creative_spec = MetaCreativeSpec(
        org_id=campaign.org_id,
        campaign_id=campaign.id,
        asset_id=scoped_asset.id,
        name="Scoped Funnel Creative",
        primary_text="Compliant scoped-funnel copy.",
        headline="Scoped funnel headline",
        description="Compliant scoped-funnel description.",
        call_to_action_type="Learn More",
        destination_url="https://example.com/offer",
        status="draft",
        metadata_json={},
    )
    adset_spec = MetaAdSetSpec(
        org_id=campaign.org_id,
        campaign_id=campaign.id,
        name="Scoped Funnel Ad Set",
        status="draft",
        metadata_json={},
    )
    db_session.add_all([creative_spec, adset_spec])
    db_session.commit()

    run_resp = api_client.post(
        f"/campaigns/{campaign_id}/paid-ads-qa/runs",
        json={
            "platform": "meta",
            "rulesetVersion": RULESET_VERSION,
            "reviewBaseUrl": "http://localhost:5275",
            "generationKey": "batch:batch-funnel-scope",
            "funnelId": funnel_id,
        },
    )
    assert run_resp.status_code == 200
    run_payload = run_resp.json()
    assert run_payload["status"] == "passed"
    assert run_payload["metadata"]["readyAssetCount"] == 1
    assert run_payload["metadata"]["funnelId"] == funnel_id
    assert run_payload["findings"] == []


def test_meta_campaign_paid_ads_qa_resolves_relative_review_paths_with_explicit_base_url(
    api_client,
    db_session,
    monkeypatch,
    tmp_path,
) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(api_client, suffix="campaign-qa-relative")
    _mock_passthrough_graph_refresh(monkeypatch)

    profile_resp = api_client.put(
        f"/clients/{client_id}/paid-ads-qa/platforms/meta/profile",
        json=_complete_meta_profile_payload(),
    )
    assert profile_resp.status_code == 200

    report_path = tmp_path / "campaign-relative-report.md"
    monkeypatch.setattr(
        paid_ads_qa_router,
        "write_report_file",
        lambda **_kwargs: str(report_path),
    )
    monkeypatch.setattr(
        paid_ads_qa_service,
        "_landing_page_snapshot",
        lambda url: {
            "requestedUrl": url,
            "finalUrl": url,
            "statusCode": 200,
            "bodyText": "Privacy Policy. Contact support@example.com",
        },
    )

    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None
    funnel_id = str(uuid4())
    brief_id = "brief-campaign-qa-relative"
    _create_funnel_scoped_brief(
        db_session=db_session,
        campaign=campaign,
        client_id=client_id,
        brief_id=brief_id,
        funnel_id=funnel_id,
    )

    asset = Asset(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.qa_passed,
        asset_kind="image",
        channel_id="facebook",
        format="image_ad",
        content={"kind": "creative"},
        storage_key="creative/campaign-qa-relative.jpg",
        content_type="image/jpeg",
        size_bytes=1234,
        width=1080,
        height=1080,
        file_source="ai",
        file_status="ready",
        ai_metadata={"assetBriefId": brief_id},
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    creative_spec = MetaCreativeSpec(
        org_id=campaign.org_id,
        campaign_id=campaign.id,
        asset_id=asset.id,
        name="Campaign QA Relative Creative",
        primary_text="Plain compliant copy.",
        headline="Plain compliant headline",
        description="Plain compliant description.",
        call_to_action_type="Learn More",
        destination_url=None,
        status="draft",
        metadata_json={
            "destinationPage": "pre-sales",
            "reviewPaths": {"pre-sales": "/f/example/funnel/pre-sales"},
        },
    )
    adset_spec = MetaAdSetSpec(
        org_id=campaign.org_id,
        campaign_id=campaign.id,
        name="Campaign QA Relative Ad Set",
        status="draft",
        metadata_json={},
    )
    db_session.add_all([creative_spec, adset_spec])
    db_session.commit()

    run_resp = api_client.post(
        f"/campaigns/{campaign_id}/paid-ads-qa/runs",
        json={
            "platform": "meta",
            "rulesetVersion": RULESET_VERSION,
            "reviewBaseUrl": "http://localhost:5275",
            "funnelId": funnel_id,
        },
    )
    assert run_resp.status_code == 200
    run_payload = run_resp.json()
    assert run_payload["status"] == "passed"
    assert run_payload["reportFilePath"] == str(report_path)
    assert run_payload["metadata"]["reviewBaseUrl"] == "http://localhost:5275"
    assert run_payload["findings"] == []


def test_meta_campaign_paid_ads_qa_defaults_review_base_url_from_selected_storefront_domain(
    api_client,
    db_session,
    monkeypatch,
    tmp_path,
) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(api_client, suffix="campaign-qa-storefront-default")
    _mock_passthrough_graph_refresh(monkeypatch)

    profile_resp = api_client.put(
        f"/clients/{client_id}/paid-ads-qa/platforms/meta/profile",
        json=_complete_meta_profile_payload(),
    )
    assert profile_resp.status_code == 200

    report_path = tmp_path / "campaign-storefront-default-report.md"
    monkeypatch.setattr(
        paid_ads_qa_router,
        "write_report_file",
        lambda **_kwargs: str(report_path),
    )
    captured_urls: list[str] = []

    def _capture_snapshot(url: str):
        captured_urls.append(url)
        return {
            "requestedUrl": url,
            "finalUrl": url,
            "statusCode": 200,
            "bodyText": "Privacy Policy. Contact support@example.com",
        }

    monkeypatch.setattr(paid_ads_qa_service, "_landing_page_snapshot", _capture_snapshot)

    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None
    funnel_id = str(uuid4())
    brief_id = "brief-campaign-qa-storefront-default"
    _create_funnel_scoped_brief(
        db_session=db_session,
        campaign=campaign,
        client_id=client_id,
        brief_id=brief_id,
        funnel_id=funnel_id,
    )
    _set_selected_storefront_domain(
        db_session=db_session,
        campaign=campaign,
        client_id=client_id,
        storefront_domain="thehonestherbalist.com",
    )

    asset = Asset(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.qa_passed,
        asset_kind="image",
        channel_id="facebook",
        format="image_ad",
        content={"kind": "creative"},
        storage_key="creative/campaign-qa-storefront-default.jpg",
        content_type="image/jpeg",
        size_bytes=1234,
        width=1080,
        height=1080,
        file_source="ai",
        file_status="ready",
        ai_metadata={"assetBriefId": brief_id},
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    creative_spec = MetaCreativeSpec(
        org_id=campaign.org_id,
        campaign_id=campaign.id,
        asset_id=asset.id,
        name="Campaign QA Storefront Default Creative",
        primary_text="Plain compliant copy.",
        headline="Plain compliant headline",
        description="Plain compliant description.",
        call_to_action_type="Learn More",
        destination_url=None,
        status="draft",
        metadata_json={
            "destinationPage": "pre-sales",
            "reviewPaths": {"pre-sales": "/f/example/funnel/pre-sales"},
        },
    )
    adset_spec = MetaAdSetSpec(
        org_id=campaign.org_id,
        campaign_id=campaign.id,
        name="Campaign QA Storefront Default Ad Set",
        status="draft",
        metadata_json={},
    )
    db_session.add_all([creative_spec, adset_spec])
    db_session.commit()

    run_resp = api_client.post(
        f"/campaigns/{campaign_id}/paid-ads-qa/runs",
        json={
            "platform": "meta",
            "rulesetVersion": RULESET_VERSION,
            "funnelId": funnel_id,
        },
    )
    assert run_resp.status_code == 200
    run_payload = run_resp.json()
    assert run_payload["status"] == "passed"
    assert run_payload["metadata"]["reviewBaseUrl"] == "https://shop.thehonestherbalist.com"
    assert captured_urls == ["https://shop.thehonestherbalist.com/f/example/funnel/pre-sales"]


def test_meta_campaign_paid_ads_qa_reads_public_funnel_payload_for_privacy_markers(
    api_client,
    db_session,
    monkeypatch,
    tmp_path,
) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(api_client, suffix="campaign-qa-public-funnel")
    _mock_passthrough_graph_refresh(monkeypatch)

    profile_resp = api_client.put(
        f"/clients/{client_id}/paid-ads-qa/platforms/meta/profile",
        json=_complete_meta_profile_payload(),
    )
    assert profile_resp.status_code == 200

    report_path = tmp_path / "campaign-public-funnel-report.md"
    monkeypatch.setattr(
        paid_ads_qa_router,
        "write_report_file",
        lambda **_kwargs: str(report_path),
    )
    monkeypatch.setattr(paid_ads_qa_service.settings, "DEPLOY_PUBLIC_API_BASE_URL", "https://api.moshq.test")

    requested_urls: list[str] = []

    class _FakeResponse:
        def __init__(self, *, url: str, payload: dict) -> None:
            self.url = url
            self.status_code = 200
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    class _FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def get(self, url: str):
            requested_urls.append(url)
            if url == "https://api.moshq.test/public/funnels/example-product/example-funnel/pages/pre-sales":
                return _FakeResponse(
                    url=url,
                    payload={
                        "metadata": {
                            "title": "The Honest Herbalist Handbook",
                            "description": "Landing page description.",
                            "brandName": "The Honest Herbalist",
                        },
                        "puckData": {
                            "content": [
                                {
                                    "type": "PreSalesHero",
                                    "props": {
                                        "config": {
                                            "badges": [
                                                {"label": "Customer Support", "value": "24/7"},
                                            ]
                                        }
                                    },
                                },
                                {
                                    "type": "PreSalesFooter",
                                    "props": {
                                        "config": {
                                            "links": [
                                                {"label": "Privacy", "href": "https://example.myshopify.com/pages/privacy-policy"},
                                                {"label": "Contact Support", "href": "https://example.myshopify.com/pages/contact"},
                                            ]
                                        }
                                    },
                                },
                            ]
                        },
                    },
                )
            raise AssertionError(f"Unexpected URL requested during public funnel snapshot test: {url}")

    monkeypatch.setattr(paid_ads_qa_service.httpx, "Client", _FakeClient)

    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None
    funnel_id = str(uuid4())
    brief_id = "brief-campaign-qa-public-funnel"
    _create_funnel_scoped_brief(
        db_session=db_session,
        campaign=campaign,
        client_id=client_id,
        brief_id=brief_id,
        funnel_id=funnel_id,
    )

    asset = Asset(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.qa_passed,
        asset_kind="image",
        channel_id="facebook",
        format="image_ad",
        content={"kind": "creative"},
        storage_key="creative/campaign-qa-public-funnel.jpg",
        content_type="image/jpeg",
        size_bytes=1234,
        width=1080,
        height=1080,
        file_source="ai",
        file_status="ready",
        ai_metadata={"assetBriefId": brief_id},
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    creative_spec = MetaCreativeSpec(
        org_id=campaign.org_id,
        campaign_id=campaign.id,
        asset_id=asset.id,
        name="Campaign QA Public Funnel Creative",
        primary_text="Plain compliant copy.",
        headline="Plain compliant headline",
        description="Plain compliant description.",
        call_to_action_type="Learn More",
        destination_url="https://shop.thehonestherbalist.com/f/example-product/example-funnel/pre-sales",
        status="draft",
        metadata_json={},
    )
    adset_spec = MetaAdSetSpec(
        org_id=campaign.org_id,
        campaign_id=campaign.id,
        name="Campaign QA Public Funnel Ad Set",
        status="draft",
        metadata_json={},
    )
    db_session.add_all([creative_spec, adset_spec])
    db_session.commit()

    run_resp = api_client.post(
        f"/campaigns/{campaign_id}/paid-ads-qa/runs",
        json={
            "platform": "meta",
            "rulesetVersion": RULESET_VERSION,
            "funnelId": funnel_id,
        },
    )
    assert run_resp.status_code == 200
    run_payload = run_resp.json()

    assert run_payload["status"] == "passed"
    assert run_payload["findings"] == []
    assert requested_urls == ["https://api.moshq.test/public/funnels/example-product/example-funnel/pages/pre-sales"]


def test_meta_campaign_paid_ads_qa_rejects_mismatched_explicit_review_base_url(
    api_client,
    db_session,
    monkeypatch,
) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(api_client, suffix="campaign-qa-storefront-mismatch")
    _mock_passthrough_graph_refresh(monkeypatch)

    profile_resp = api_client.put(
        f"/clients/{client_id}/paid-ads-qa/platforms/meta/profile",
        json=_complete_meta_profile_payload(),
    )
    assert profile_resp.status_code == 200

    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None
    funnel_id = str(uuid4())
    brief_id = "brief-campaign-qa-storefront-mismatch"
    _create_funnel_scoped_brief(
        db_session=db_session,
        campaign=campaign,
        client_id=client_id,
        brief_id=brief_id,
        funnel_id=funnel_id,
    )
    _set_selected_storefront_domain(
        db_session=db_session,
        campaign=campaign,
        client_id=client_id,
        storefront_domain="thehonestherbalist.com",
    )

    asset = Asset(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.qa_passed,
        asset_kind="image",
        channel_id="facebook",
        format="image_ad",
        content={"kind": "creative"},
        storage_key="creative/campaign-qa-storefront-mismatch.jpg",
        content_type="image/jpeg",
        size_bytes=1234,
        width=1080,
        height=1080,
        file_source="ai",
        file_status="ready",
        ai_metadata={"assetBriefId": brief_id},
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    creative_spec = MetaCreativeSpec(
        org_id=campaign.org_id,
        campaign_id=campaign.id,
        asset_id=asset.id,
        name="Campaign QA Storefront Mismatch Creative",
        primary_text="Plain compliant copy.",
        headline="Plain compliant headline",
        description="Plain compliant description.",
        call_to_action_type="Learn More",
        destination_url="https://shop.thehonestherbalist.com/f/example/funnel/pre-sales",
        status="draft",
        metadata_json={},
    )
    adset_spec = MetaAdSetSpec(
        org_id=campaign.org_id,
        campaign_id=campaign.id,
        name="Campaign QA Storefront Mismatch Ad Set",
        status="draft",
        metadata_json={},
    )
    db_session.add_all([creative_spec, adset_spec])
    db_session.commit()

    run_resp = api_client.post(
        f"/campaigns/{campaign_id}/paid-ads-qa/runs",
        json={
            "platform": "meta",
            "rulesetVersion": RULESET_VERSION,
            "reviewBaseUrl": "https://shop.moshq.app",
            "funnelId": funnel_id,
        },
    )
    assert run_resp.status_code == 409
    payload = run_resp.json()["detail"]
    assert payload["reviewBaseUrl"] == "https://shop.moshq.app"
    assert payload["expectedReviewBaseUrl"] == "https://shop.thehonestherbalist.com"


def test_meta_campaign_paid_ads_qa_refreshes_live_profile_before_scoring(
    api_client,
    db_session,
    monkeypatch,
    tmp_path,
) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(api_client, suffix="campaign-qa-live-refresh")
    _mock_hydrated_graph_refresh(monkeypatch)

    report_path = tmp_path / "campaign-live-refresh-report.md"
    monkeypatch.setattr(
        paid_ads_qa_router,
        "write_report_file",
        lambda **_kwargs: str(report_path),
    )
    monkeypatch.setattr(
        paid_ads_qa_service,
        "_landing_page_snapshot",
        lambda url: {
            "requestedUrl": url,
            "finalUrl": url,
            "statusCode": 200,
            "bodyText": "Privacy Policy. Contact support@example.com",
        },
    )

    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None
    funnel_id = str(uuid4())
    brief_id = "brief-campaign-qa-live-refresh"
    _create_funnel_scoped_brief(
        db_session=db_session,
        campaign=campaign,
        client_id=client_id,
        brief_id=brief_id,
        funnel_id=funnel_id,
    )

    asset = Asset(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.qa_passed,
        asset_kind="image",
        channel_id="facebook",
        format="image_ad",
        content={"kind": "creative"},
        storage_key="creative/campaign-qa-live-refresh.jpg",
        content_type="image/jpeg",
        size_bytes=1234,
        width=1080,
        height=1080,
        file_source="ai",
        file_status="ready",
        ai_metadata={"assetBriefId": brief_id},
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    creative_spec = MetaCreativeSpec(
        org_id=campaign.org_id,
        campaign_id=campaign.id,
        asset_id=asset.id,
        name="Campaign QA Live Refresh Creative",
        primary_text="Compliant copy.",
        headline="Compliant headline",
        description="Compliant description.",
        call_to_action_type="Learn More",
        destination_url="https://example.com/offer",
        status="draft",
        metadata_json={},
    )
    adset_spec = MetaAdSetSpec(
        org_id=campaign.org_id,
        campaign_id=campaign.id,
        name="Campaign QA Live Refresh Ad Set",
        status="draft",
        metadata_json={},
    )
    db_session.add_all([creative_spec, adset_spec])
    db_session.commit()

    run_resp = api_client.post(
        f"/campaigns/{campaign_id}/paid-ads-qa/runs",
        json={"platform": "meta", "rulesetVersion": RULESET_VERSION, "funnelId": funnel_id},
    )
    assert run_resp.status_code == 200
    run_payload = run_resp.json()
    assert run_payload["status"] == "passed"
    assert run_payload["reportFilePath"] == str(report_path)
    rule_ids = {finding["ruleId"] for finding in run_payload["findings"]}
    assert "META-ACCOUNT-001" not in rule_ids
    assert "META-ACCOUNT-002" not in rule_ids
    assert "META-ACCOUNT-003" not in rule_ids
    assert run_payload["metadata"]["profileValidation"]["lastValidatedAt"] == "2026-03-10T21:45:00+00:00"
