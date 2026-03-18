from __future__ import annotations

from sqlalchemy import select

from app.db.enums import ArtifactTypeEnum
from app.db.models import Artifact, Campaign, Client, Product
from app.strategy_v2 import launches as strategy_v2_launches
from tests.helpers.manual_creative_context import manual_creative_context_payload
from tests.helpers.launch_context import seed_ready_launch_context_for_campaign
from tests.conftest import TEST_ORG_ID


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
            "channels": ["meta"],
            "asset_brief_types": ["image"],
        },
    )
    assert campaign_resp.status_code == 201
    return client_id, product_id, campaign_resp.json()["id"]


def _seed_ready_launch_context(db_session) -> Campaign:
    client = Client(org_id=TEST_ORG_ID, name="Launch Context Client", industry="Health")
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)

    product = Product(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        title="Launch Context Product",
        description="Launch-ready product description.",
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    campaign = Campaign(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        product_id=product.id,
        name="Launch Context Campaign",
        channels=["meta"],
        asset_brief_types=["image"],
    )
    db_session.add(campaign)
    db_session.commit()
    db_session.refresh(campaign)

    seed_ready_launch_context_for_campaign(
        db_session,
        client_id=str(client.id),
        product_id=str(product.id),
        campaign_id=str(campaign.id),
    )

    return campaign


def test_campaign_delivery_defaults_to_internal_funnel_on_create(api_client) -> None:
    _, _, campaign_id = _create_campaign_with_product(api_client, suffix="delivery-default")

    response = api_client.get(f"/campaigns/{campaign_id}/delivery")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["deliveryMode"] == "internal_funnel"
    assert payload["validationStatus"] == "not_applicable"
    assert payload["preSalesUrl"] is None
    assert payload["salesUrl"] is None


def test_campaign_delivery_put_external_urls_normalizes_and_invalidates_validation(api_client, db_session) -> None:
    _, _, campaign_id = _create_campaign_with_product(api_client, suffix="delivery-put")
    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None
    seed_ready_launch_context_for_campaign(
        db_session,
        client_id=str(campaign.client_id),
        product_id=str(campaign.product_id),
        campaign_id=str(campaign.id),
        launch_key=f"sv2-launch:test:{campaign.id}:delivery-put",
    )

    response = api_client.put(
        f"/campaigns/{campaign_id}/delivery",
        json={
            "deliveryMode": "external_urls",
            "preSalesUrl": " HTTPS://Example.COM/presell ",
            "salesUrl": "https://Example.com/offer",
            "checkoutUrl": "https://checkout.example.com/cart",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["deliveryMode"] == "external_urls"
    assert payload["preSalesUrl"] == "https://example.com/presell"
    assert payload["salesUrl"] == "https://example.com/offer"
    assert payload["checkoutUrl"] == "https://checkout.example.com/cart"
    assert payload["validationStatus"] == "not_validated"
    assert payload["validatedAt"] is None


def test_campaign_delivery_validate_marks_valid_and_returns_results(api_client, db_session, monkeypatch) -> None:
    _, _, campaign_id = _create_campaign_with_product(api_client, suffix="delivery-validate")
    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None
    seed_ready_launch_context_for_campaign(
        db_session,
        client_id=str(campaign.client_id),
        product_id=str(campaign.product_id),
        campaign_id=str(campaign.id),
        launch_key=f"sv2-launch:test:{campaign.id}:delivery-validate",
    )
    put_response = api_client.put(
        f"/campaigns/{campaign_id}/delivery",
        json={
            "deliveryMode": "external_urls",
            "preSalesUrl": "https://example.com/presell",
            "salesUrl": "https://example.com/offer",
        },
    )
    assert put_response.status_code == 200, put_response.text

    def _fake_fetch(url: str) -> tuple[int, str, str]:
        return 200, url, "<html>privacy contact support</html>"

    monkeypatch.setattr("app.services.campaign_delivery._fetch_url_validation_result", _fake_fetch)

    response = api_client.post(f"/campaigns/{campaign_id}/delivery/validate")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["validationStatus"] == "valid"
    assert len(payload["results"]) == 2
    assert all(result["passed"] is True for result in payload["results"])

    get_response = api_client.get(f"/campaigns/{campaign_id}/delivery")
    assert get_response.status_code == 200
    assert get_response.json()["validationStatus"] == "valid"
    assert get_response.json()["validatedAt"] is not None


def test_campaign_delivery_validate_marks_invalid_when_required_markers_missing(api_client, db_session, monkeypatch) -> None:
    _, _, campaign_id = _create_campaign_with_product(api_client, suffix="delivery-invalid")
    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None
    seed_ready_launch_context_for_campaign(
        db_session,
        client_id=str(campaign.client_id),
        product_id=str(campaign.product_id),
        campaign_id=str(campaign.id),
        launch_key=f"sv2-launch:test:{campaign.id}:delivery-invalid",
    )
    put_response = api_client.put(
        f"/campaigns/{campaign_id}/delivery",
        json={
            "deliveryMode": "external_urls",
            "preSalesUrl": "https://example.com/presell",
            "salesUrl": "https://example.com/offer",
        },
    )
    assert put_response.status_code == 200, put_response.text

    def _fake_fetch(url: str) -> tuple[int, str, str]:
        return 200, url, "<html>contact support only</html>"

    monkeypatch.setattr("app.services.campaign_delivery._fetch_url_validation_result", _fake_fetch)

    response = api_client.post(f"/campaigns/{campaign_id}/delivery/validate")
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["validationStatus"] == "invalid"
    assert any("privacy" in issue.lower() for result in detail["results"] for issue in result["issues"])

    get_response = api_client.get(f"/campaigns/{campaign_id}/delivery")
    assert get_response.status_code == 200
    assert get_response.json()["validationStatus"] == "invalid"


def test_campaign_launch_context_readiness_reports_missing_launch_lineage(api_client) -> None:
    _, _, campaign_id = _create_campaign_with_product(api_client, suffix="launch-context-missing")

    response = api_client.get(f"/campaigns/{campaign_id}/launch-context-readiness")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ready"] is False
    assert "no pinned Strategy V2 launch lineage".lower() in payload["reason"].lower()


def test_campaign_launch_context_readiness_pins_artifact_when_ready(api_client, db_session, monkeypatch) -> None:
    campaign = _seed_ready_launch_context(db_session)
    monkeypatch.setattr(
        strategy_v2_launches.ProductBriefStage1,
        "model_validate",
        classmethod(lambda cls, value: value),
    )

    first_response = api_client.get(f"/campaigns/{campaign.id}/launch-context-readiness")
    assert first_response.status_code == 200, first_response.text
    first_payload = first_response.json()
    assert first_payload["ready"] is True
    assert first_payload["refreshed"] is True
    artifact_id = first_payload["launchContextArtifactId"]
    assert artifact_id

    artifact = db_session.scalars(
        select(Artifact).where(
            Artifact.id == artifact_id,
            Artifact.type == ArtifactTypeEnum.strategy_v2_launch_context,
        )
    ).first()
    assert artifact is not None
    assert artifact.campaign_id == campaign.id

    second_response = api_client.get(f"/campaigns/{campaign.id}/launch-context-readiness")
    assert second_response.status_code == 200, second_response.text
    second_payload = second_response.json()
    assert second_payload["ready"] is True
    assert second_payload["refreshed"] is False
    assert second_payload["launchContextArtifactId"] == artifact_id


def test_campaign_manual_creative_context_ingest_sets_manual_readiness(api_client, db_session, monkeypatch) -> None:
    _, _, campaign_id = _create_campaign_with_product(api_client, suffix="manual-context")

    monkeypatch.setattr(
        "app.services.campaign_creative_context.ensure_uploaded_to_claude",
        lambda **_kwargs: "claude-file-1",
    )
    monkeypatch.setattr("app.services.campaign_creative_context.is_gemini_file_search_enabled", lambda: False)
    monkeypatch.setattr(
        "app.services.campaign_creative_context.ensure_uploaded_to_gemini_file_search",
        lambda **_kwargs: None,
    )

    response = api_client.post(
        f"/campaigns/{campaign_id}/creative-context/loaded",
        json=manual_creative_context_payload(campaign_id=campaign_id),
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["provider"] == "manual"
    assert "campaign_creative_context" in payload["artifactIds"]
    assert "campaign_loaded_copy" in payload["artifactIds"]
    assert f"experiment_specs:{campaign_id}" in payload["uploadedDocKeys"]

    readiness_response = api_client.get(f"/campaigns/{campaign_id}/launch-context-readiness")
    assert readiness_response.status_code == 200, readiness_response.text
    readiness_payload = readiness_response.json()
    assert readiness_payload["provider"] == "manual"
    assert readiness_payload["ready"] is True
    assert readiness_payload["manualCreativeContextArtifactId"] == payload["creativeContextArtifactId"]

    creative_context_artifact = db_session.scalars(
        select(Artifact).where(
            Artifact.campaign_id == campaign_id,
            Artifact.type == ArtifactTypeEnum.campaign_creative_context,
        )
    ).first()
    assert creative_context_artifact is not None
    assert creative_context_artifact.data["provider"] == "manual"


def test_creative_production_accepts_manual_creative_context_without_launch_lineage(
    api_client,
    db_session,
    monkeypatch,
) -> None:
    client_id, _, campaign_id = _create_campaign_with_product(api_client, suffix="manual-produce")

    monkeypatch.setattr(
        "app.services.campaign_creative_context.ensure_uploaded_to_claude",
        lambda **_kwargs: "claude-file-1",
    )
    monkeypatch.setattr("app.services.campaign_creative_context.is_gemini_file_search_enabled", lambda: False)
    monkeypatch.setattr(
        "app.services.campaign_creative_context.ensure_uploaded_to_gemini_file_search",
        lambda **_kwargs: None,
    )

    creative_context_response = api_client.post(
        f"/campaigns/{campaign_id}/creative-context/loaded",
        json=manual_creative_context_payload(campaign_id=campaign_id),
    )
    assert creative_context_response.status_code == 201, creative_context_response.text

    def _fake_fetch(url: str) -> tuple[int, str, str]:
        return 200, url, "<html>privacy contact support</html>"

    monkeypatch.setattr("app.services.campaign_delivery._fetch_url_validation_result", _fake_fetch)
    put_response = api_client.put(
        f"/campaigns/{campaign_id}/delivery",
        json={
            "deliveryMode": "external_urls",
            "preSalesUrl": "https://lp.example.com/manual-pre-sale",
            "salesUrl": "https://lp.example.com/manual-offer",
        },
    )
    assert put_response.status_code == 200, put_response.text
    validate_response = api_client.post(f"/campaigns/{campaign_id}/delivery/validate")
    assert validate_response.status_code == 200, validate_response.text

    brief_artifact = Artifact(
        org_id=TEST_ORG_ID,
        client_id=client_id,
        campaign_id=campaign_id,
        type=ArtifactTypeEnum.asset_brief,
        data={
            "asset_briefs": [
                {
                    "id": "brief-manual-produce",
                    "campaignId": campaign_id,
                    "clientId": client_id,
                    "deliveryMode": "external_urls",
                    "destinationType": "pre-sales",
                    "experimentId": "exp-manual-1",
                    "variantId": "var_angle",
                    "variantName": "Structured angle",
                    "creativeConcept": "Drive clicks with the structured angle.",
                    "requirements": [{"channel": "facebook", "format": "image_ad"}],
                }
            ]
        },
    )
    db_session.add(brief_artifact)
    db_session.commit()

    response = api_client.post(
        f"/campaigns/{campaign_id}/creative/produce",
        json={"asset_brief_ids": ["brief-manual-produce"]},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["workflow_run_id"]
    assert payload["temporal_workflow_id"]
