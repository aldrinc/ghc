from app.db.enums import AssetSourceEnum, AssetStatusEnum
from app.db.models import Asset, Campaign, MetaAdSetSpec, MetaCreativeSpec
from app.routers import paid_ads_qa as paid_ads_qa_router
from app.services import paid_ads_qa as paid_ads_qa_service
from app.services.paid_ads_qa import RULESET_VERSION


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


def _seed_campaign_ready_meta_objects(
    *,
    db_session,
    client_id: str,
    product_id: str,
    campaign_id: str,
) -> None:
    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None

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
        ai_metadata={},
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
    assert summary_payload[0]["version"] == RULESET_VERSION
    assert summary_payload[0]["ruleCount"] >= 10

    ruleset_resp = api_client.get(f"/paid-ads-qa/rulesets/{RULESET_VERSION}")
    assert ruleset_resp.status_code == 200
    ruleset = ruleset_resp.json()
    rule_ids = {rule["ruleId"] for rule in ruleset["rules"]}
    assert "META-ACCOUNT-001" in rule_ids
    assert "META-COPY-002" in rule_ids
    assert "TTK-ACCOUNT-001" in rule_ids


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
        ai_metadata={},
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
        json={"platform": "meta", "rulesetVersion": RULESET_VERSION},
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

    _seed_campaign_ready_meta_objects(
        db_session=db_session,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
    )

    first_run_resp = api_client.post(
        f"/campaigns/{campaign_id}/paid-ads-qa/runs",
        json={"platform": "meta", "rulesetVersion": RULESET_VERSION},
    )
    assert first_run_resp.status_code == 200
    first_run = first_run_resp.json()

    second_run_resp = api_client.post(
        f"/campaigns/{campaign_id}/paid-ads-qa/runs",
        json={"platform": "meta", "rulesetVersion": RULESET_VERSION, "reviewBaseUrl": "http://localhost:5275"},
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
        ai_metadata={},
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
        },
    )
    assert run_resp.status_code == 200
    run_payload = run_resp.json()
    assert run_payload["status"] == "passed"
    assert run_payload["reportFilePath"] == str(report_path)
    assert run_payload["metadata"]["reviewBaseUrl"] == "http://localhost:5275"
    assert run_payload["findings"] == []


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
        ai_metadata={},
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
        json={"platform": "meta", "rulesetVersion": RULESET_VERSION},
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
