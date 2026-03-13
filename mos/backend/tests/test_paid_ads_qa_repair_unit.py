from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import HTTPException

from app.auth.dependencies import AuthContext
from app.routers import paid_ads_qa as paid_ads_qa_router


def _profile_record(**overrides):
    now = datetime.now(timezone.utc)
    base = {
        "id": "profile-1",
        "org_id": "org-1",
        "client_id": "client-1",
        "platform": "meta",
        "ruleset_version": paid_ads_qa_router.RULESET_VERSION,
        "business_manager_id": "bm-123",
        "business_manager_name": "Meta Business",
        "page_id": "123456",
        "page_name": "Meta Page",
        "ad_account_id": "act_123456",
        "ad_account_name": "Meta Account",
        "payment_method_type": "credit_card",
        "payment_method_status": "active",
        "pixel_id": "pixel-123",
        "data_set_id": "dataset-123",
        "data_set_shopify_partner_installed": False,
        "data_set_data_sharing_level": "standard",
        "data_set_assigned_to_ad_account": True,
        "verified_domain": None,
        "verified_domain_status": None,
        "attribution_click_window": None,
        "attribution_view_window": None,
        "view_through_enabled": None,
        "tracking_provider": "mos",
        "tracking_url_parameters": "utm_source=meta&utm_medium=paid",
        "metadata_json": {},
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class _FakeSession:
    def __init__(self, *, funnel, campaign):
        self._funnel = funnel
        self._campaign = campaign
        self._scalar_calls = 0

    def scalar(self, _stmt):
        self._scalar_calls += 1
        if self._scalar_calls == 1:
            return self._funnel
        if self._scalar_calls == 2:
            return self._campaign
        raise AssertionError("Unexpected scalar call")


class _FakeRepo:
    saved_profile = None

    def __init__(self, _session):
        self._session = _session

    def get_platform_profile(self, *, org_id: str, client_id: str, platform: str):
        assert org_id == "org-1"
        assert client_id == "client-1"
        assert platform == "meta"
        return None

    def upsert_platform_profile(self, **fields):
        _FakeRepo.saved_profile = _profile_record(
            org_id=fields["org_id"],
            client_id=fields["client_id"],
            platform=fields["platform"],
            ruleset_version=fields["ruleset_version"],
            business_manager_id=fields.get("business_manager_id"),
            business_manager_name=fields.get("business_manager_name"),
            page_id=fields.get("page_id"),
            page_name=fields.get("page_name"),
            ad_account_id=fields.get("ad_account_id"),
            ad_account_name=fields.get("ad_account_name"),
            payment_method_type=fields.get("payment_method_type"),
            payment_method_status=fields.get("payment_method_status"),
            pixel_id=fields.get("pixel_id"),
            data_set_id=fields.get("data_set_id"),
            data_set_shopify_partner_installed=fields.get("data_set_shopify_partner_installed"),
            data_set_data_sharing_level=fields.get("data_set_data_sharing_level"),
            data_set_assigned_to_ad_account=fields.get("data_set_assigned_to_ad_account"),
            verified_domain=fields.get("verified_domain"),
            verified_domain_status=fields.get("verified_domain_status"),
            attribution_click_window=fields.get("attribution_click_window"),
            attribution_view_window=fields.get("attribution_view_window"),
            view_through_enabled=fields.get("view_through_enabled"),
            tracking_provider=fields.get("tracking_provider"),
            tracking_url_parameters=fields.get("tracking_url_parameters"),
            metadata_json=fields.get("metadata_json") or {},
        )
        return _FakeRepo.saved_profile


def test_repair_funnel_meta_tracking_updates_profile(monkeypatch) -> None:
    funnel = SimpleNamespace(
        id="funnel-1",
        org_id="org-1",
        client_id="client-1",
        campaign_id="campaign-1",
    )
    campaign = SimpleNamespace(
        id="campaign-1",
        org_id="org-1",
        client_id="client-1",
        channels=["facebook"],
    )
    fake_session = _FakeSession(funnel=funnel, campaign=campaign)

    def _activate(*, profile, funnel_ids, ruleset_version):
        assert profile["clientId"] == "client-1"
        assert funnel_ids == ["funnel-1"]
        assert ruleset_version == paid_ads_qa_router.RULESET_VERSION
        return {
            "clientId": "client-1",
            "platform": "meta",
            "rulesetVersion": paid_ads_qa_router.RULESET_VERSION,
            "businessManagerId": "bm-123",
            "businessManagerName": "Meta Business",
            "pageId": "123456",
            "pageName": "Meta Page",
            "adAccountId": "act_123456",
            "adAccountName": "Meta Account",
            "paymentMethodType": "credit_card",
            "paymentMethodStatus": "active",
            "pixelId": "pixel-123",
            "dataSetId": "dataset-123",
            "dataSetShopifyPartnerInstalled": False,
            "dataSetDataSharingLevel": "standard",
            "dataSetAssignedToAdAccount": True,
            "trackingProvider": "mos",
            "trackingUrlParameters": "utm_source=meta&utm_medium=paid",
            "metadata": {
                "mosMetaTracking": {
                    "status": "active",
                    "channel": "meta",
                    "mode": "public_funnel_runtime",
                    "pixelId": "pixel-123",
                    "browserEvents": ["PageView", "InitiateCheckout"],
                    "funnelIds": ["funnel-1"],
                }
            },
        }

    monkeypatch.setattr(paid_ads_qa_router, "PaidAdsQaRepository", _FakeRepo)
    monkeypatch.setattr(paid_ads_qa_router, "activate_mos_meta_funnel_tracking_profile", _activate)

    response = paid_ads_qa_router.repair_funnel_meta_tracking(
        funnel_id="funnel-1",
        auth=AuthContext(user_id="user-1", org_id="org-1"),
        session=fake_session,
    )

    assert response.funnelId == "funnel-1"
    assert response.campaignId == "campaign-1"
    assert response.clientId == "client-1"
    assert response.profile.rulesetVersion == paid_ads_qa_router.RULESET_VERSION
    assert response.profile.trackingProvider == "mos"
    assert response.profile.metadata["mosMetaTracking"]["funnelIds"] == ["funnel-1"]


def test_repair_funnel_meta_tracking_rejects_non_meta_campaign() -> None:
    funnel = SimpleNamespace(
        id="funnel-1",
        org_id="org-1",
        client_id="client-1",
        campaign_id="campaign-1",
    )
    campaign = SimpleNamespace(
        id="campaign-1",
        org_id="org-1",
        client_id="client-1",
        channels=["tiktok"],
    )
    fake_session = _FakeSession(funnel=funnel, campaign=campaign)

    try:
        paid_ads_qa_router.repair_funnel_meta_tracking(
            funnel_id="funnel-1",
            auth=AuthContext(user_id="user-1", org_id="org-1"),
            session=fake_session,
        )
    except HTTPException as exc:
        assert exc.status_code == 409
        assert exc.detail == "Meta tracking repair requires the funnel's campaign to target a Meta channel."
    else:
        raise AssertionError("Expected Meta tracking repair to reject non-Meta campaigns")


def test_provision_meta_domain_verification_dns_updates_profile(monkeypatch) -> None:
    funnel = SimpleNamespace(
        id="funnel-1",
        org_id="org-1",
        client_id="client-1",
        campaign_id="campaign-1",
    )
    campaign = SimpleNamespace(
        id="campaign-1",
        org_id="org-1",
        client_id="client-1",
        channels=["facebook"],
    )
    fake_session = _FakeSession(funnel=funnel, campaign=campaign)

    def _upsert_txt_record(*, hostname: str, value: str, ttl: int = 300):
        assert hostname == "shop.example.com"
        assert value == "facebook-domain-verification=xyz789"
        assert ttl == 300
        return {
            "provider": "namecheap",
            "recordType": "TXT",
            "host": "shop",
            "domain": "example.com",
            "fqdn": "shop.example.com",
            "value": "facebook-domain-verification=xyz789",
            "ttl": 300,
            "status": "dns_record_written",
        }

    monkeypatch.setattr(paid_ads_qa_router, "PaidAdsQaRepository", _FakeRepo)
    monkeypatch.setattr(
        paid_ads_qa_router.namecheap_dns_service,
        "upsert_txt_record",
        _upsert_txt_record,
    )

    response = paid_ads_qa_router.provision_meta_domain_verification_dns(
        funnel_id="funnel-1",
        payload=paid_ads_qa_router.PaidAdsMetaDomainVerificationProvisionRequest(
            txtValue="facebook-domain-verification=xyz789",
            verifiedDomain="shop.example.com",
        ),
        auth=AuthContext(user_id="user-1", org_id="org-1"),
        session=fake_session,
    )

    assert response.funnelId == "funnel-1"
    assert response.campaignId == "campaign-1"
    assert response.clientId == "client-1"
    assert response.verifiedDomain == "shop.example.com"
    assert response.verifiedDomainStatus == "pending"
    assert response.dnsRecord.status == "dns_record_written"
    assert response.dnsRecord.fqdn == "shop.example.com"
    assert response.profile.verifiedDomain == "shop.example.com"
    assert response.profile.verifiedDomainStatus == "pending"
    assert response.profile.metadata["metaDomainVerification"]["value"] == "facebook-domain-verification=xyz789"
    assert response.profile.metadata["metaDomainVerification"]["funnelIds"] == ["funnel-1"]


def test_provision_meta_domain_verification_dns_rejects_non_meta_campaign(monkeypatch) -> None:
    funnel = SimpleNamespace(
        id="funnel-1",
        org_id="org-1",
        client_id="client-1",
        campaign_id="campaign-1",
    )
    campaign = SimpleNamespace(
        id="campaign-1",
        org_id="org-1",
        client_id="client-1",
        channels=["tiktok"],
    )
    fake_session = _FakeSession(funnel=funnel, campaign=campaign)

    monkeypatch.setattr(paid_ads_qa_router, "PaidAdsQaRepository", _FakeRepo)

    try:
        paid_ads_qa_router.provision_meta_domain_verification_dns(
            funnel_id="funnel-1",
            payload=paid_ads_qa_router.PaidAdsMetaDomainVerificationProvisionRequest(
                txtValue="facebook-domain-verification=xyz789",
                verifiedDomain="shop.example.com",
            ),
            auth=AuthContext(user_id="user-1", org_id="org-1"),
            session=fake_session,
        )
    except HTTPException as exc:
        assert exc.status_code == 409
        assert exc.detail == "Meta domain verification requires the funnel's campaign to target a Meta channel."
    else:
        raise AssertionError("Expected Meta domain verification provisioning to reject non-Meta campaigns")
