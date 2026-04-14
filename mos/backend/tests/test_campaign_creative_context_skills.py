from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.enums import ArtifactTypeEnum
from app.db.models import Artifact, Campaign
from app.services.campaign_creative_context import load_campaign_creative_context
from app.services.product_strategy_bundles import ProductStrategyBundlesService
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


def _seed_skills_handoff_bundle(
    db_session,
    *,
    client_id: str,
    product_id: str,
    include_sales_page: bool = True,
) -> dict[str, object]:
    service = ProductStrategyBundlesService(
        session=db_session,
        org_id=TEST_ORG_ID,
        client_id=client_id,
        product_id=product_id,
        created_by_user=None,
    )
    angle_library = service.create_document_artifact(
        artifact_type=ArtifactTypeEnum.skill_angle_library,
        title="Angle Library",
        role="angle_library",
        document_format="json",
        markdown=None,
        json_payload={
            "angles": [
                {
                    "angleId": "ember-angle-1",
                    "angleName": "Fuel deficit clarity",
                    "description": "Frame the fog as a hidden fuel deficit instead of decline.",
                    "mechanism": "Creatine-backed energy support",
                    "evidence": ["VOC shows fear of decline and doctor dismissal."],
                },
                {
                    "angleId": "ember-angle-2",
                    "angleName": "Mechanism before panic",
                    "description": "Explain the mechanism before emotional escalation.",
                    "mechanism": "Steadier ATP support",
                    "evidence": ["Research-aware buyers want mechanism-first framing."],
                },
            ]
        },
        metadata_json={},
    )
    angle_selection = service.create_document_artifact(
        artifact_type=ArtifactTypeEnum.skill_angle_selection,
        title="Angle Selection",
        role="angle_selection",
        document_format="json",
        markdown=None,
        json_payload={
            "selectedAngleId": "ember-angle-1",
            "rationale": "Best approved local angle.",
            "selectedAngle": {
                "angleId": "ember-angle-1",
                "angleName": "Fuel deficit clarity",
                "description": "Frame the fog as a hidden fuel deficit instead of decline.",
                "mechanism": "Creatine-backed energy support",
                "evidence": ["VOC shows fear of decline and doctor dismissal."],
            },
            "sourceArtifactId": str(angle_library.id),
        },
        metadata_json={},
    )
    signal_report = service.create_document_artifact(
        artifact_type=ArtifactTypeEnum.skill_signal_report,
        title="Signal Report",
        role="signal_report",
        document_format="markdown",
        markdown="# Signal Report\n\nWomen fear decline, dismissal, and identity loss.",
        json_payload=None,
        metadata_json={},
    )
    knowledge_base = service.create_document_artifact(
        artifact_type=ArtifactTypeEnum.skill_knowledge_base,
        title="Knowledge Base",
        role="knowledge_base",
        document_format="markdown",
        markdown="# Knowledge Base\n\nAudience state, mechanism, and product context.",
        json_payload=None,
        metadata_json={},
    )
    cso = service.create_document_artifact(
        artifact_type=ArtifactTypeEnum.skill_cso,
        title="CSO",
        role="cso",
        document_format="markdown",
        markdown="# CSO\n\nTarget state, proof strategy, objections, and copy constraints.",
        json_payload=None,
        metadata_json={},
    )
    offer_document = service.create_document_artifact(
        artifact_type=ArtifactTypeEnum.skill_offer_document,
        title="Offer Document",
        role="offer_document",
        document_format="json",
        markdown=None,
        json_payload={
            "ump": "Restore the fuel pathway perimenopause drains away.",
            "ums": "A daily creatine gummy protocol that supports clarity and consistency.",
            "corePromise": "Trust your own brain again with a steadier daily protocol.",
            "valueStackSummary": "Protocol guidance plus a simple daily clarity routine.",
            "guaranteeType": "30-day",
            "pricingRationale": "Priced against repeated symptom-chasing spend.",
            "selectedVariantId": "ember-30",
            "selectedVariantName": "30 Day Supply",
            "offerDetailsMarkdown": "# Offer Details\n\nProtocol and bundle details.",
        },
        metadata_json={},
    )
    headline_selection = service.create_document_artifact(
        artifact_type=ArtifactTypeEnum.skill_headline_selection,
        title="Headline Selection",
        role="headline_selection",
        document_format="json",
        markdown=None,
        json_payload={
            "selectedHeadlineId": "headline-1",
            "rationale": "Strongest approved headline.",
            "selectedHeadline": {
                "headlineId": "headline-1",
                "headline": "What if the fog isn’t decline, but a fuel problem nobody named?",
                "rationale": "Pairs wound with mechanism.",
            },
            "sourceArtifactId": "headline-pool-1",
        },
        metadata_json={},
    )
    presell_page = service.create_document_artifact(
        artifact_type=ArtifactTypeEnum.skill_presell_page,
        title="Presell Page",
        role="presell_page",
        document_format="markdown",
        markdown="# Presell Page\n\nLong-form presell copy.",
        json_payload=None,
        metadata_json={},
    )

    artifact_roles = {
        "signal_report": str(signal_report.id),
        "angle_library": str(angle_library.id),
        "angle_selection": str(angle_selection.id),
        "knowledge_base": str(knowledge_base.id),
        "cso": str(cso.id),
        "offer_document": str(offer_document.id),
        "headline_selection": str(headline_selection.id),
        "presell_page": str(presell_page.id),
    }
    if include_sales_page:
        sales_page = service.create_document_artifact(
            artifact_type=ArtifactTypeEnum.skill_sales_page,
            title="Sales Page",
            role="sales_page",
            document_format="markdown",
            markdown="# Sales Page\n\nLong-form sales copy.",
            json_payload=None,
            metadata_json={},
        )
        artifact_roles["sales_page"] = str(sales_page.id)

    bundle = service.create_bundle(
        bundle_type="skills_handoff",
        title="EMBER Skills Handoff",
        status="approved",
        is_active=True,
        artifact_roles=artifact_roles,
        metadata_json={"testSeed": True},
        approved_by_user=None,
    )
    db_session.commit()
    return bundle


def test_skills_creative_context_readiness_requires_active_bundle(api_client, db_session) -> None:
    _, _, campaign_id = _create_campaign_with_product(api_client, suffix="skills-readiness-missing-bundle")

    provider_response = api_client.put(
        f"/campaigns/{campaign_id}/creative-context/provider",
        json={"provider": "skills"},
    )
    assert provider_response.status_code == 200, provider_response.text

    readiness_response = api_client.get(f"/campaigns/{campaign_id}/launch-context-readiness")
    assert readiness_response.status_code == 200, readiness_response.text
    payload = readiness_response.json()
    assert payload["provider"] == "skills"
    assert payload["ready"] is False
    assert payload["missingArtifacts"] == ["skills_handoff"]
    assert payload["creativeContextArtifactId"] == provider_response.json()["creativeContextArtifactId"]


def test_skills_creative_context_readiness_reports_missing_bundle_roles(api_client, db_session) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="skills-readiness-missing-role",
    )
    _seed_skills_handoff_bundle(
        db_session,
        client_id=client_id,
        product_id=product_id,
        include_sales_page=False,
    )

    provider_response = api_client.put(
        f"/campaigns/{campaign_id}/creative-context/provider",
        json={"provider": "skills"},
    )
    assert provider_response.status_code == 200, provider_response.text

    readiness_response = api_client.get(f"/campaigns/{campaign_id}/launch-context-readiness")
    assert readiness_response.status_code == 200, readiness_response.text
    payload = readiness_response.json()
    assert payload["provider"] == "skills"
    assert payload["ready"] is False
    assert "sales_page" in payload["missingArtifacts"]


def test_skills_creative_context_requires_materialization_and_reuses_existing_snapshot(
    api_client,
    db_session,
    monkeypatch,
) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="skills-load-success",
    )
    bundle = _seed_skills_handoff_bundle(
        db_session,
        client_id=client_id,
        product_id=product_id,
        include_sales_page=True,
    )

    provider_response = api_client.put(
        f"/campaigns/{campaign_id}/creative-context/provider",
        json={"provider": "skills"},
    )
    assert provider_response.status_code == 200, provider_response.text

    readiness_response = api_client.get(f"/campaigns/{campaign_id}/launch-context-readiness")
    assert readiness_response.status_code == 200, readiness_response.text
    readiness_payload = readiness_response.json()
    assert readiness_payload["provider"] == "skills"
    assert readiness_payload["ready"] is False
    assert readiness_payload["strategyBundleId"] == bundle["id"]
    assert readiness_payload["missingArtifacts"] == ["materialized_creative_context"]
    assert readiness_payload["materializedCreativeContextArtifactId"] is None

    campaign = db_session.scalars(select(Campaign).where(Campaign.id == campaign_id)).first()
    assert campaign is not None

    with pytest.raises(ValueError, match="has not been materialized"):
        load_campaign_creative_context(
            session=db_session,
            org_id=TEST_ORG_ID,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
        )

    monkeypatch.setattr(
        "app.services.campaign_creative_context.ensure_uploaded_to_claude",
        lambda **_kwargs: "claude-file-1",
    )
    monkeypatch.setattr("app.services.campaign_creative_context.is_gemini_file_search_enabled", lambda: False)
    monkeypatch.setattr(
        "app.services.campaign_creative_context.ensure_uploaded_to_gemini_file_search",
        lambda **_kwargs: None,
    )

    materialize_response = api_client.post(f"/campaigns/{campaign_id}/creative-context/materialize")
    assert materialize_response.status_code == 200, materialize_response.text
    materialize_payload = materialize_response.json()
    assert materialize_payload["provider"] == "skills"
    assert materialize_payload["refreshed"] is True
    assert materialize_payload["strategyBundleId"] == bundle["id"]
    assert "campaign_creative_context" in materialize_payload["artifactIds"]
    assert "campaign_loaded_copy_context" in materialize_payload["artifactIds"]
    assert materialize_payload["sourceArtifactIds"]["offer_document"] is not None

    second_materialize_response = api_client.post(f"/campaigns/{campaign_id}/creative-context/materialize")
    assert second_materialize_response.status_code == 200, second_materialize_response.text
    second_materialize_payload = second_materialize_response.json()
    assert second_materialize_payload["refreshed"] is False
    assert second_materialize_payload["creativeContextArtifactId"] == materialize_payload["creativeContextArtifactId"]

    readiness_response = api_client.get(f"/campaigns/{campaign_id}/launch-context-readiness")
    assert readiness_response.status_code == 200, readiness_response.text
    readiness_payload = readiness_response.json()
    assert readiness_payload["provider"] == "skills"
    assert readiness_payload["ready"] is True
    assert readiness_payload["materializedCreativeContextArtifactId"] == materialize_payload["creativeContextArtifactId"]
    assert readiness_payload["materializedArtifactIds"]["campaign_loaded_offer"] == materialize_payload["artifactIds"]["campaign_loaded_offer"]

    creative_context = load_campaign_creative_context(
        session=db_session,
        org_id=TEST_ORG_ID,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
    )
    provider = creative_context["provider"]
    assert getattr(provider, "value", provider) == "skills"
    assert creative_context["downstream_packet"]["selected_angle"]["angle_name"] == "Fuel deficit clarity"
    assert creative_context["downstream_packet"]["offer"]["selected_variant"]["id"] == "ember-30"
    assert creative_context["copy"]["headline"] == "What if the fog isn’t decline, but a fuel problem nobody named?"
    assert creative_context["copy_context"]["audienceProductMarkdown"].startswith("# Audience + Product")

    creative_context_artifact = db_session.scalars(
        select(Artifact).where(
            Artifact.id == materialize_payload["creativeContextArtifactId"],
            Artifact.type == ArtifactTypeEnum.campaign_creative_context,
        )
    ).first()
    assert creative_context_artifact is not None
    assert creative_context_artifact.data["provider"] == "skills"
    assert creative_context_artifact.data["artifactIds"]["campaign_loaded_angles"] == materialize_payload["artifactIds"]["campaign_loaded_angles"]
