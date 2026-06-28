from app.services.skills_runtime_registry import SkillsRuntimeRegistryService


def _create_client(api_client, *, name: str = "Connected Social Test") -> str:
    resp = api_client.post("/clients", json={"name": name, "industry": "SaaS"})
    assert resp.status_code == 201
    return resp.json()["id"]


def test_connected_social_asset_snapshot_and_action_proposal_flow(api_client):
    client_id = _create_client(api_client)

    asset_resp = api_client.post(
        f"/clients/{client_id}/connected-social/provider-assets",
        json={
            "provider": "meta",
            "providerAssetId": "act_123",
            "assetType": "ad_account",
            "displayName": "Demo Meta Ads",
            "capabilityFlags": ["ads_read", "ads_management"],
            "rawPayload": {"accountId": "act_123"},
            "metadata": {"source": "test"},
        },
    )
    assert asset_resp.status_code == 201
    asset = asset_resp.json()
    assert asset["providerAssetId"] == "act_123"
    assert asset["capabilityFlags"] == ["ads_read", "ads_management"]

    list_resp = api_client.get(f"/clients/{client_id}/connected-social/provider-assets?provider=meta")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    snapshot_resp = api_client.post(
        f"/clients/{client_id}/connected-social/snapshots",
        json={
            "providerAssetId": asset["id"],
            "provider": "meta",
            "snapshotType": "ad_account_insights",
            "metrics": {"views": 123},
            "rawPayload": {"items": []},
            "provenance": "concrete",
        },
    )
    assert snapshot_resp.status_code == 201
    assert snapshot_resp.json()["metrics"]["views"] == 123

    proposal_resp = api_client.post(
        f"/clients/{client_id}/connected-social/action-proposals",
        json={
            "actionType": "submit_tiktok_carousel_draft",
            "targetProvider": "postiz",
            "targetAssetId": "postiz-channel-123",
            "targetAssetType": "postiz_channel",
            "beforeSnapshot": {"status": "draft"},
            "proposedAfter": {"status": "submitted"},
            "rationale": "Approved rendered carousel is ready for Postiz draft submission.",
            "riskLabel": "medium",
            "requiredCapability": "postiz.compose",
        },
    )
    assert proposal_resp.status_code == 201
    proposal = proposal_resp.json()
    assert proposal["status"] == "pending"

    approve_resp = api_client.post(
        f"/clients/{client_id}/connected-social/action-proposals/{proposal['id']}/approve",
        json={"notes": "Looks good"},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"
    assert approve_resp.json()["metadata"]["approvalNotes"] == "Looks good"

    reapprove_resp = api_client.post(
        f"/clients/{client_id}/connected-social/action-proposals/{proposal['id']}/approve",
        json={},
    )
    assert reapprove_resp.status_code == 409


def test_connected_social_runtime_profiles_are_registered():
    profiles = SkillsRuntimeRegistryService._default_runtime_profiles()
    keys = {profile["key"] for profile in profiles}
    assert {"meta-ads-manager", "social-media-manager", "tiktok-carousel-growth-manager"} <= keys

    tiktok_profile = next(
        profile for profile in profiles if profile["key"] == "tiktok-carousel-growth-manager"
    )
    rules = tiktok_profile["profile_json"]["runtimeRules"]
    assert any("Postiz owns compose" in rule for rule in rules)
    assert "mos.growth_programs.variants" in tiktok_profile["profile_json"]["toolsets"]
    assert "mos.postiz.handoff" in tiktok_profile["profile_json"]["toolsets"]
