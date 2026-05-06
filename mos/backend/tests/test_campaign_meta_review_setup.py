from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.enums import ArtifactTypeEnum, AssetSourceEnum, AssetStatusEnum
from app.db.models import Artifact, Asset, Campaign, Funnel, FunnelPage, MetaAdSetSpec, MetaCreativeSpec
from app.services.meta_publish_defaults import (
    DEFAULT_META_PUBLISH_ADSET_DAILY_MIN_SPEND_TARGET_MINOR_UNITS,
    DEFAULT_META_PUBLISH_ATTRIBUTION_SPEC,
    DEFAULT_META_PUBLISH_BUCKET_COUNT,
    DEFAULT_META_PUBLISH_CAMPAIGN_DAILY_BUDGET_MINOR_UNITS,
    DEFAULT_META_PUBLISH_TARGETING,
    MAX_META_PUBLISH_BUCKET_COUNT,
)
from app.services.paid_ads_qa import RULESET_VERSION
from tests.helpers.manual_creative_context import manual_creative_context_payload
from tests.helpers.launch_context import seed_ready_launch_context_for_campaign


def _create_campaign_with_product(api_client, *, suffix: str, db_session=None) -> tuple[str, str, str]:
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

    profile_resp = api_client.put(
        f"/clients/{client_id}/paid-ads-qa/platforms/meta/profile",
        json={
            "rulesetVersion": RULESET_VERSION,
            "pageId": "123456",
            "adAccountId": "act_123456",
            "metadata": {},
        },
    )
    assert profile_resp.status_code == 200
    campaign_id = campaign_resp.json()["id"]
    if db_session is not None:
        seed_ready_launch_context_for_campaign(
            db_session,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            launch_key=f"sv2-launch:test:{campaign_id}:{suffix}",
        )
    return client_id, product_id, campaign_id


def _build_swipe_copy_pack(
    *,
    requirement_index: int,
    angle: str,
    hook: str,
    primary_text: str,
    headline: str,
    description: str,
    cta: str = "Learn More",
    destination_type: str = "pre-sales",
) -> dict[str, object]:
    return {
        "platform": "Meta",
        "requirementIndex": requirement_index,
        "channel": "facebook",
        "format": "image_ad",
        "funnelStage": "top-of-funnel",
        "angle": angle,
        "hook": hook,
        "destinationType": destination_type,
        "selectedVariation": "Variation 1",
        "formattedVariationsMarkdown": (
            "```markdown\n"
            f"Primary Text: {primary_text}\n"
            f"Headline: {headline}\n"
            f"Description: {description}\n"
            f"CTA: {cta}\n"
            "```"
        ),
        "metaPrimaryText": primary_text,
        "metaHeadline": headline,
        "metaDescription": description,
        "metaCta": cta,
        "claimsGuardrails": ["Do not invent unsupported claims."],
    }


def _build_swipe_copy_inputs(
    *,
    source_label: str,
    source_url: str,
    angle_used: str,
    destination_page: str = "pre-sales",
    source_swipe_label: str | None = None,
    source_swipe_url: str | None = None,
) -> dict[str, object]:
    return {
        "platform": "Meta",
        "adImageOrVideo": {
            "sourceKind": "rendered_output",
            "sourceLabel": source_label,
            "sourceUrl": source_url,
            "assetType": "image",
            "mimeType": "image/png",
        },
        "angleUsed": angle_used,
        "destinationPage": destination_page,
        "sourceSwipe": {
            "sourceLabel": source_swipe_label or source_label,
            "sourceUrl": source_swipe_url or source_url,
            "mimeType": "image/png",
        },
    }


def test_campaign_meta_review_setup_creates_internal_specs_and_pipeline_payload(
    api_client,
    db_session,
) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="meta-review",
        db_session=db_session,
    )

    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None

    funnel = Funnel(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        name="Meta Review Funnel",
        route_slug="meta-review-funnel",
    )
    db_session.add(funnel)
    db_session.commit()
    db_session.refresh(funnel)

    pre_sales_page = FunnelPage(
        funnel_id=funnel.id,
        name="Pre-sales",
        slug="pre-sales",
        template_id="pre_sales_listicle",
    )
    sales_page = FunnelPage(
        funnel_id=funnel.id,
        name="Sales",
        slug="sales",
        template_id="sales_pdp",
    )
    db_session.add_all([pre_sales_page, sales_page])
    db_session.commit()

    brief_id = "brief-exp-a02-001"
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
                    "funnelId": str(funnel.id),
                    "experimentId": "exp-A02-Interaction Triage Workflow",
                    "variantId": "variant_a",
                    "variantName": "Interaction Triage Workflow",
                    "creativeConcept": "Explain the workflow and reduce confusion.",
                    "requirements": [
                        {
                            "channel": "facebook",
                            "format": "image_ad",
                            "funnelStage": "top-of-funnel",
                            "hook": "A clearer way to check interactions before you start.",
                            "angle": "Structure over guesswork.",
                        }
                    ],
                }
            ]
        },
    )
    db_session.add(brief_artifact)
    db_session.commit()
    db_session.refresh(brief_artifact)

    ad_copy_pack_artifact = Artifact(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        type=ArtifactTypeEnum.ad_copy_pack,
        data={
            "schemaVersion": 2,
            "assetBriefId": brief_id,
            "sourceBriefArtifactId": str(brief_artifact.id),
            "sourceBriefSha256": "brief-sha-123",
            "sourceFunnelId": str(funnel.id),
            "copyPacks": [
                {
                    "id": "copy-pack-001",
                    "requirementIndex": 0,
                    "channel": "facebook",
                    "format": "image_ad",
                    "funnelStage": "top-of-funnel",
                    "angle": "Structure over guesswork.",
                    "hook": "A clearer way to check interactions before you start.",
                    "creativeConcept": "Use a structured workflow instead of guessing.",
                    "metaPrimaryText": "Parents need a repeatable herb-drug interaction workflow before they try anything.",
                    "metaHeadline": "A safer way to screen interactions",
                    "metaDescription": "Built from the Honest Herbalist workflow.",
                    "claimsGuardrails": ["Do not promise medical outcomes."],
                }
            ],
        },
    )
    db_session.add(ad_copy_pack_artifact)
    db_session.commit()
    db_session.refresh(ad_copy_pack_artifact)

    asset = Asset(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        funnel_id=funnel.id,
        asset_brief_artifact_id=brief_artifact.id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.draft,
        asset_kind="image",
        channel_id="facebook",
        format="image_ad",
        content={"assetBriefId": brief_id},
        storage_key="creative/test-meta-review.jpg",
        content_type="image/jpeg",
        size_bytes=1234,
        width=1080,
        height=1080,
        file_source="ai",
        file_status="ready",
        ai_metadata={
            "assetBriefId": brief_id,
            "requirementIndex": 0,
            "adCopyPackArtifactId": str(ad_copy_pack_artifact.id),
            "adCopyPackId": "copy-pack-001",
            "creativeGenerationBatchId": "batch-xyz",
            "swipeCopyPack": _build_swipe_copy_pack(
                requirement_index=0,
                angle="Structure over guesswork.",
                hook="A clearer way to check interactions before you start.",
                primary_text="Parents need a repeatable herb-drug interaction workflow before they try anything.",
                headline="A safer way to screen interactions",
                description="Built from the Honest Herbalist workflow.",
            ),
            "swipeCopyInputs": _build_swipe_copy_inputs(
                source_label="10.png",
                source_url="https://example.com/swipes/10.png",
                angle_used="Structure over guesswork.",
                destination_page="pre-sales",
            ),
        },
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    setup_resp = api_client.post(
        f"/campaigns/{campaign_id}/meta/review-setup",
        json={"assetBriefIds": [brief_id], "funnelId": str(funnel.id)},
    )
    assert setup_resp.status_code == 200
    setup_payload = setup_resp.json()
    assert setup_payload["assetCount"] == 1
    assert len(setup_payload["createdCreativeSpecIds"]) == 1
    assert len(setup_payload["createdAdSetSpecIds"]) == DEFAULT_META_PUBLISH_BUCKET_COUNT

    pipeline_resp = api_client.get(
        f"/meta/pipeline/assets?clientId={client_id}&productId={product_id}&campaignId={campaign_id}&statuses=draft"
    )
    assert pipeline_resp.status_code == 200
    pipeline = pipeline_resp.json()
    assert len(pipeline) == 1
    row = pipeline[0]
    assert row["asset"]["ai_metadata"]["creativeGenerationBatchId"] == "batch-xyz"
    assert row["creative_spec"]["primary_text"] == (
        "Parents need a repeatable herb-drug interaction workflow before they try anything."
    )
    assert row["creative_spec"]["headline"] == "A safer way to screen interactions"
    assert row["creative_spec"]["description"] == "Built from the Honest Herbalist workflow."
    assert row["creative_spec"]["call_to_action_type"] == "Learn More"
    assert row["creative_spec"]["destination_url"].endswith("/pre-sales")
    assert row["creative_spec"]["metadata_json"]["assetBriefId"] == brief_id
    assert row["creative_spec"]["metadata_json"]["generationBatchId"] == "batch-xyz"
    assert row["creative_spec"]["metadata_json"]["swipeSourceLabel"] == "10.png"
    assert row["creative_spec"]["metadata_json"]["swipeSourceMediaUrl"] == "https://example.com/swipes/10.png"
    assert row["creative_spec"]["metadata_json"]["swipeCopyPack"]["metaPrimaryText"] == (
        "Parents need a repeatable herb-drug interaction workflow before they try anything."
    )
    assert row["creative_spec"]["metadata_json"]["swipeCopyInputs"]["destinationPage"] == "pre-sales"
    assert row["creative_spec"]["metadata_json"]["reviewPaths"]["pre-sales"].endswith("/pre-sales")
    assert row["creative_spec"]["metadata_json"]["reviewPaths"]["sales"].endswith("/sales")
    assert row["experiment"]["id"] == "exp-A02-Interaction Triage Workflow"
    assert len(row["adset_specs"]) == DEFAULT_META_PUBLISH_BUCKET_COUNT
    assert row["adset_specs"][0]["optimization_goal"] == "OFFSITE_CONVERSIONS"
    assert row["adset_specs"][0]["billing_event"] == "IMPRESSIONS"
    assert row["adset_specs"][0]["daily_budget"] is None
    assert row["adset_specs"][0]["lifetime_budget"] is None
    assert row["adset_specs"][0]["daily_min_spend_target"] == (
        DEFAULT_META_PUBLISH_ADSET_DAILY_MIN_SPEND_TARGET_MINOR_UNITS
    )
    assert row["adset_specs"][0]["placements"] is None
    assert row["adset_specs"][0]["targeting"] == DEFAULT_META_PUBLISH_TARGETING
    assert row["adset_specs"][0]["metadata_json"]["templateId"] == "default-broad-int-cbo"
    assert row["adset_specs"][0]["metadata_json"]["bucketIndex"] == 1
    assert row["adset_specs"][0]["metadata_json"]["bucketCount"] == DEFAULT_META_PUBLISH_BUCKET_COUNT
    assert row["adset_specs"][0]["metadata_json"]["campaignDailyBudget"] == (
        DEFAULT_META_PUBLISH_CAMPAIGN_DAILY_BUDGET_MINOR_UNITS
    )
    assert row["adset_specs"][0]["metadata_json"]["attributionSpec"] == DEFAULT_META_PUBLISH_ATTRIBUTION_SPEC

    library_pipeline_resp = api_client.get(f"/meta/pipeline/assets?clientId={client_id}&productId={product_id}&statuses=draft")
    assert library_pipeline_resp.status_code == 200
    library_pipeline = library_pipeline_resp.json()
    assert len(library_pipeline) == 1
    assert len(library_pipeline[0]["adset_specs"]) == DEFAULT_META_PUBLISH_BUCKET_COUNT
    assert library_pipeline[0]["adset_specs"][0]["metadata_json"]["bucketIndex"] == 1

    custom_bucket_setup_resp = api_client.post(
        f"/campaigns/{campaign_id}/meta/review-setup",
        json={
            "assetBriefIds": [brief_id],
            "funnelId": str(funnel.id),
            "bucketCount": MAX_META_PUBLISH_BUCKET_COUNT,
        },
    )
    assert custom_bucket_setup_resp.status_code == 200
    custom_bucket_setup_payload = custom_bucket_setup_resp.json()
    assert len(custom_bucket_setup_payload["createdAdSetSpecIds"]) == (
        MAX_META_PUBLISH_BUCKET_COUNT - DEFAULT_META_PUBLISH_BUCKET_COUNT
    )

    custom_bucket_specs = db_session.scalars(
        select(MetaAdSetSpec).where(
            MetaAdSetSpec.campaign_id == campaign_id,
            MetaAdSetSpec.org_id == campaign.org_id,
        )
    ).all()
    custom_bucket_indices = sorted(
        spec.metadata_json.get("bucketIndex") for spec in custom_bucket_specs
    )
    assert custom_bucket_indices == list(range(1, MAX_META_PUBLISH_BUCKET_COUNT + 1))
    custom_bucket_eight = next(
        spec for spec in custom_bucket_specs if spec.metadata_json.get("bucketIndex") == 8
    )
    assert custom_bucket_eight.metadata_json["bucketCount"] == MAX_META_PUBLISH_BUCKET_COUNT


def test_campaign_meta_review_setup_uses_external_campaign_delivery_urls(
    api_client,
    db_session,
    monkeypatch,
) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="meta-review-external",
        db_session=db_session,
    )

    def _fake_fetch(url: str) -> tuple[int, str, str]:
        return 200, url, "<html>privacy contact support</html>"

    monkeypatch.setattr("app.services.campaign_delivery._fetch_url_validation_result", _fake_fetch)

    put_response = api_client.put(
        f"/campaigns/{campaign_id}/delivery",
        json={
            "deliveryMode": "external_urls",
            "preSalesUrl": "https://lp.example.com/pre-sale",
            "salesUrl": "https://lp.example.com/offer",
        },
    )
    assert put_response.status_code == 200, put_response.text
    validate_response = api_client.post(f"/campaigns/{campaign_id}/delivery/validate")
    assert validate_response.status_code == 200, validate_response.text

    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None

    brief_id = "brief-exp-a02-external"
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
                    "deliveryMode": "external_urls",
                    "destinationType": "pre-sales",
                    "destinationLabel": "Pre-Sales Landing Page",
                    "experimentId": "exp-A02-External",
                    "variantId": "variant_a",
                    "variantName": "External Landing Page Variant",
                    "creativeConcept": "Drive qualified clicks to the external pre-sales page.",
                    "requirements": [
                        {
                            "channel": "facebook",
                            "format": "image_ad",
                            "funnelStage": "top-of-funnel",
                            "hook": "Why operators click through the external page.",
                            "angle": "External delivery without funnel coupling.",
                            "destinationType": "pre-sales",
                            "destinationLabel": "Pre-Sales Landing Page",
                        }
                    ],
                }
            ]
        },
    )
    db_session.add(brief_artifact)
    db_session.commit()
    db_session.refresh(brief_artifact)

    asset = Asset(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        funnel_id=None,
        asset_brief_artifact_id=brief_artifact.id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.draft,
        asset_kind="image",
        channel_id="facebook",
        format="image_ad",
        content={"assetBriefId": brief_id},
        storage_key="creative/test-meta-review-external.jpg",
        content_type="image/jpeg",
        size_bytes=1234,
        width=1080,
        height=1080,
        file_source="ai",
        file_status="ready",
        ai_metadata={
            "assetBriefId": brief_id,
            "requirementIndex": 0,
            "creativeGenerationBatchId": "batch-external",
            "deliveryMode": "external_urls",
            "destinationType": "pre-sales",
            "resolvedDestinationUrl": "https://lp.example.com/pre-sale",
            "swipeCopyPack": _build_swipe_copy_pack(
                requirement_index=0,
                angle="External delivery without funnel coupling.",
                hook="Why operators click through the external page.",
                primary_text="Use the validated external landing page for paid traffic.",
                headline="External destinations are launch-ready",
                description="Creative spec should point at the canonical pre-sales URL.",
            ),
            "swipeCopyInputs": _build_swipe_copy_inputs(
                source_label="14.png",
                source_url="https://example.com/swipes/14.png",
                angle_used="External delivery without funnel coupling.",
                destination_page="pre-sales",
            ),
        },
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    setup_resp = api_client.post(
        f"/campaigns/{campaign_id}/meta/review-setup",
        json={"assetBriefIds": [brief_id]},
    )
    assert setup_resp.status_code == 200, setup_resp.text

    creative_spec = db_session.scalar(
        select(MetaCreativeSpec).where(
            MetaCreativeSpec.campaign_id == campaign_id,
            MetaCreativeSpec.asset_id == asset.id,
        )
    )
    assert creative_spec is not None
    assert creative_spec.destination_url == "https://lp.example.com/pre-sale"
    assert creative_spec.metadata_json["destinationSource"] == "campaign_delivery_config"
    assert creative_spec.metadata_json["campaignDelivery"]["deliveryMode"] == "external_urls"


def test_campaign_meta_review_setup_supports_manual_creative_context_without_launch_lineage(
    api_client,
    db_session,
    monkeypatch,
) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="meta-review-manual",
        db_session=None,
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

    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None

    brief_id = "brief-exp-manual-external"
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
                    "deliveryMode": "external_urls",
                    "destinationType": "pre-sales",
                    "destinationLabel": "Pre-Sales Landing Page",
                    "experimentId": "exp-manual-1",
                    "variantId": "var_angle",
                    "variantName": "Structured angle",
                    "creativeConcept": "Drive clicks with the manually loaded structured angle.",
                    "requirements": [
                        {
                            "channel": "facebook",
                            "format": "image_ad",
                            "funnelStage": "top-of-funnel",
                            "hook": "Show the decision path before the click.",
                            "angle": "Structured relief path",
                            "destinationType": "pre-sales",
                            "destinationLabel": "Pre-Sales Landing Page",
                        }
                    ],
                }
            ]
        },
    )
    db_session.add(brief_artifact)
    db_session.commit()
    db_session.refresh(brief_artifact)

    asset = Asset(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        funnel_id=None,
        asset_brief_artifact_id=brief_artifact.id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.draft,
        asset_kind="image",
        channel_id="facebook",
        format="image_ad",
        content={"assetBriefId": brief_id},
        storage_key="creative/test-meta-review-manual.jpg",
        content_type="image/jpeg",
        size_bytes=1234,
        width=1080,
        height=1080,
        file_source="ai",
        file_status="ready",
        ai_metadata={
            "assetBriefId": brief_id,
            "requirementIndex": 0,
            "creativeGenerationBatchId": "batch-manual",
            "deliveryMode": "external_urls",
            "destinationType": "pre-sales",
            "resolvedDestinationUrl": "https://lp.example.com/manual-pre-sale",
            "swipeCopyPack": _build_swipe_copy_pack(
                requirement_index=0,
                angle="Structured relief path",
                hook="Show the decision path before the click.",
                primary_text="Walk buyers through the offer before they commit.",
                headline="A clearer external decision path",
                description="Manual creative context drives the published copy.",
            ),
            "swipeCopyInputs": _build_swipe_copy_inputs(
                source_label="21.png",
                source_url="https://example.com/swipes/21.png",
                angle_used="Structured relief path",
                destination_page="pre-sales",
            ),
        },
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    setup_resp = api_client.post(
        f"/campaigns/{campaign_id}/meta/review-setup",
        json={"assetBriefIds": [brief_id]},
    )
    assert setup_resp.status_code == 200, setup_resp.text

    creative_spec = db_session.scalar(
        select(MetaCreativeSpec).where(
            MetaCreativeSpec.campaign_id == campaign_id,
            MetaCreativeSpec.asset_id == asset.id,
        )
    )
    assert creative_spec is not None
    assert creative_spec.destination_url == "https://lp.example.com/manual-pre-sale"
    assert creative_spec.metadata_json["destinationSource"] == "campaign_delivery_config"


def test_campaign_meta_review_setup_ignores_legacy_assets_when_latest_batch_exists(
    api_client,
    db_session,
) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="meta-review-latest-batch",
        db_session=db_session,
    )

    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None

    funnel = Funnel(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        name="Meta Review Funnel",
        route_slug="meta-review-latest-batch-funnel",
    )
    db_session.add(funnel)
    db_session.commit()
    db_session.refresh(funnel)

    db_session.add_all(
        [
            FunnelPage(funnel_id=funnel.id, name="Pre-sales", slug="pre-sales", template_id="pre_sales_listicle"),
            FunnelPage(funnel_id=funnel.id, name="Sales", slug="sales", template_id="sales_pdp"),
        ]
    )
    db_session.commit()

    brief_id = "brief-exp-a02-latest-batch"
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
                    "funnelId": str(funnel.id),
                    "experimentId": "exp-A02-Latest-Batch",
                    "variantId": "variant_a",
                    "variantName": "Latest Batch Variant",
                    "creativeConcept": "Use latest batch only.",
                    "requirements": [
                        {
                            "channel": "facebook",
                            "format": "image_ad",
                            "funnelStage": "top-of-funnel",
                            "hook": "Use the latest assets only.",
                            "angle": "Batch-aware review setup.",
                        }
                    ],
                }
            ]
        },
    )
    db_session.add(brief_artifact)
    db_session.commit()
    db_session.refresh(brief_artifact)

    ad_copy_pack_artifact = Artifact(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        type=ArtifactTypeEnum.ad_copy_pack,
        data={
            "schemaVersion": 2,
            "assetBriefId": brief_id,
            "sourceBriefArtifactId": str(brief_artifact.id),
            "sourceBriefSha256": "brief-sha-latest",
            "sourceFunnelId": str(funnel.id),
            "copyPacks": [
                {
                    "id": "copy-pack-latest",
                    "requirementIndex": 0,
                    "channel": "facebook",
                    "format": "image_ad",
                    "funnelStage": "top-of-funnel",
                    "angle": "Batch-aware review setup.",
                    "hook": "Use the latest assets only.",
                    "creativeConcept": "Latest batch creative",
                    "metaPrimaryText": "Primary text from the latest batch.",
                    "metaHeadline": "Latest batch headline",
                    "metaDescription": "Latest batch description",
                    "claimsGuardrails": ["Do not invent unsupported claims."],
                }
            ],
        },
    )
    db_session.add(ad_copy_pack_artifact)
    db_session.commit()
    db_session.refresh(ad_copy_pack_artifact)

    legacy_asset = Asset(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        funnel_id=funnel.id,
        asset_brief_artifact_id=brief_artifact.id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.draft,
        asset_kind="image",
        channel_id="facebook",
        format="image_ad",
        content={"assetBriefId": brief_id},
        storage_key="creative/legacy-meta-review.jpg",
        content_type="image/jpeg",
        size_bytes=1111,
        width=1080,
        height=1080,
        file_source="ai",
        file_status="ready",
        ai_metadata={
            "assetBriefId": brief_id,
            "requirementIndex": 0,
        },
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    latest_asset = Asset(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        funnel_id=funnel.id,
        asset_brief_artifact_id=brief_artifact.id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.draft,
        asset_kind="image",
        channel_id="facebook",
        format="image_ad",
        content={"assetBriefId": brief_id},
        storage_key="creative/latest-meta-review.jpg",
        content_type="image/jpeg",
        size_bytes=2222,
        width=1080,
        height=1080,
        file_source="ai",
        file_status="ready",
        ai_metadata={
            "assetBriefId": brief_id,
            "requirementIndex": 0,
            "adCopyPackArtifactId": str(ad_copy_pack_artifact.id),
            "adCopyPackId": "copy-pack-latest",
            "creativeGenerationBatchId": "batch-latest",
            "swipeCopyPack": _build_swipe_copy_pack(
                requirement_index=0,
                angle="Batch-aware review setup.",
                hook="Use the latest assets only.",
                primary_text="Primary text from the latest batch.",
                headline="Latest batch headline",
                description="Latest batch description",
            ),
            "swipeCopyInputs": _build_swipe_copy_inputs(
                source_label="10.png",
                source_url="https://example.com/swipes/10.png",
                angle_used="Batch-aware review setup.",
                destination_page="pre-sales",
            ),
        },
        created_at=datetime.now(timezone.utc),
    )
    db_session.add_all([legacy_asset, latest_asset])
    db_session.commit()

    setup_resp = api_client.post(
        f"/campaigns/{campaign_id}/meta/review-setup",
        json={"assetBriefIds": [brief_id], "funnelId": str(funnel.id)},
    )
    assert setup_resp.status_code == 200
    setup_payload = setup_resp.json()
    assert setup_payload["assetCount"] == 1

    pipeline_resp = api_client.get(
        f"/meta/pipeline/assets?clientId={client_id}&productId={product_id}&campaignId={campaign_id}&statuses=draft"
    )
    assert pipeline_resp.status_code == 200
    pipeline = pipeline_resp.json()
    latest_row = next(row for row in pipeline if row["asset"]["id"] == str(latest_asset.id))
    legacy_row = next(row for row in pipeline if row["asset"]["id"] == str(legacy_asset.id))
    assert latest_row["creative_spec"] is not None
    assert legacy_row["creative_spec"] is None


def test_campaign_meta_review_setup_can_scope_to_explicit_generation_batch(
    api_client,
    db_session,
) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="meta-review-batch-scope",
        db_session=db_session,
    )

    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None

    funnel = Funnel(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        name="Meta Review Batch Scope Funnel",
        route_slug="meta-review-batch-scope-funnel",
    )
    db_session.add(funnel)
    db_session.commit()
    db_session.refresh(funnel)

    db_session.add_all(
        [
            FunnelPage(funnel_id=funnel.id, name="Pre-sales", slug="pre-sales", template_id="pre_sales_listicle"),
            FunnelPage(funnel_id=funnel.id, name="Sales", slug="sales", template_id="sales_pdp"),
        ]
    )
    db_session.commit()

    brief_id = "brief-exp-a02-batch-scope"
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
                    "funnelId": str(funnel.id),
                    "experimentId": "exp-A02-Batch-Scope",
                    "variantId": "variant_a",
                    "variantName": "Batch Scope Variant",
                    "creativeConcept": "Use only the requested batch.",
                    "requirements": [
                        {
                            "channel": "facebook",
                            "format": "image_ad",
                            "funnelStage": "top-of-funnel",
                            "hook": "Respect the selected creative batch.",
                            "angle": "Batch-scoped review setup.",
                        }
                    ],
                }
            ]
        },
    )
    db_session.add(brief_artifact)
    db_session.commit()
    db_session.refresh(brief_artifact)

    ad_copy_pack_artifact = Artifact(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        type=ArtifactTypeEnum.ad_copy_pack,
        data={
            "schemaVersion": 2,
            "assetBriefId": brief_id,
            "sourceBriefArtifactId": str(brief_artifact.id),
            "sourceBriefSha256": "brief-sha-batch-scope",
            "sourceFunnelId": str(funnel.id),
            "copyPacks": [
                {
                    "id": "copy-pack-batch-scope",
                    "requirementIndex": 0,
                    "channel": "facebook",
                    "format": "image_ad",
                    "funnelStage": "top-of-funnel",
                    "angle": "Batch-scoped review setup.",
                    "hook": "Respect the selected creative batch.",
                    "creativeConcept": "Scoped creative concept.",
                    "metaPrimaryText": "Primary text from the selected batch.",
                    "metaHeadline": "Selected batch headline",
                    "metaDescription": "Selected batch description",
                    "claimsGuardrails": ["Do not invent unsupported claims."],
                }
            ],
        },
    )
    db_session.add(ad_copy_pack_artifact)
    db_session.commit()
    db_session.refresh(ad_copy_pack_artifact)

    older_batch_asset = Asset(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        funnel_id=funnel.id,
        asset_brief_artifact_id=brief_artifact.id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.draft,
        asset_kind="image",
        channel_id="facebook",
        format="image_ad",
        content={"assetBriefId": brief_id},
        storage_key="creative/batch-scope-older.jpg",
        content_type="image/jpeg",
        size_bytes=1111,
        width=1080,
        height=1080,
        file_source="ai",
        file_status="ready",
        ai_metadata={
            "assetBriefId": brief_id,
            "requirementIndex": 0,
            "adCopyPackArtifactId": str(ad_copy_pack_artifact.id),
            "adCopyPackId": "copy-pack-batch-scope",
            "creativeGenerationBatchId": "batch-older",
            "swipeCopyPack": _build_swipe_copy_pack(
                requirement_index=0,
                angle="Batch-scoped review setup.",
                hook="Respect the selected creative batch.",
                primary_text="Primary text from the older batch.",
                headline="Older batch headline",
                description="Older batch description",
            ),
            "swipeCopyInputs": _build_swipe_copy_inputs(
                source_label="10.png",
                source_url="https://example.com/swipes/10.png",
                angle_used="Batch-scoped review setup.",
                destination_page="pre-sales",
            ),
        },
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    selected_batch_asset = Asset(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        funnel_id=funnel.id,
        asset_brief_artifact_id=brief_artifact.id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.draft,
        asset_kind="image",
        channel_id="facebook",
        format="image_ad",
        content={"assetBriefId": brief_id},
        storage_key="creative/batch-scope-selected.jpg",
        content_type="image/jpeg",
        size_bytes=2222,
        width=1080,
        height=1080,
        file_source="ai",
        file_status="ready",
        ai_metadata={
            "assetBriefId": brief_id,
            "requirementIndex": 0,
            "adCopyPackArtifactId": str(ad_copy_pack_artifact.id),
            "adCopyPackId": "copy-pack-batch-scope",
            "creativeGenerationBatchId": "batch-selected",
            "swipeCopyPack": _build_swipe_copy_pack(
                requirement_index=0,
                angle="Batch-scoped review setup.",
                hook="Respect the selected creative batch.",
                primary_text="Primary text from the selected batch.",
                headline="Selected batch headline",
                description="Selected batch description",
            ),
            "swipeCopyInputs": _build_swipe_copy_inputs(
                source_label="11.png",
                source_url="https://example.com/swipes/11.png",
                angle_used="Batch-scoped review setup.",
                destination_page="pre-sales",
            ),
        },
        created_at=datetime.now(timezone.utc),
    )
    db_session.add_all([older_batch_asset, selected_batch_asset])
    db_session.commit()

    setup_resp = api_client.post(
        f"/campaigns/{campaign_id}/meta/review-setup",
        json={"assetBriefIds": [brief_id], "generationBatchId": "batch-selected", "funnelId": str(funnel.id)},
    )
    assert setup_resp.status_code == 200
    setup_payload = setup_resp.json()
    assert setup_payload["assetCount"] == 1

    pipeline_resp = api_client.get(
        f"/meta/pipeline/assets?clientId={client_id}&productId={product_id}&campaignId={campaign_id}&statuses=draft"
    )
    assert pipeline_resp.status_code == 200
    pipeline = pipeline_resp.json()
    selected_row = next(row for row in pipeline if row["asset"]["id"] == str(selected_batch_asset.id))
    older_row = next(row for row in pipeline if row["asset"]["id"] == str(older_batch_asset.id))
    assert selected_row["creative_spec"] is not None
    assert selected_row["creative_spec"]["metadata_json"]["generationBatchId"] == "batch-selected"
    assert older_row["creative_spec"] is None


def test_campaign_meta_review_setup_normalizes_human_destination_labels(
    api_client,
    db_session,
) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="meta-review-human-destination",
        db_session=db_session,
    )

    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None

    funnel = Funnel(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        name="Meta Review Human Destination Funnel",
        route_slug="meta-review-human-destination-funnel",
    )
    db_session.add(funnel)
    db_session.commit()
    db_session.refresh(funnel)

    db_session.add_all(
        [
            FunnelPage(funnel_id=funnel.id, name="Pre-sales", slug="pre-sales", template_id="pre_sales_listicle"),
            FunnelPage(funnel_id=funnel.id, name="Sales", slug="sales", template_id="sales_pdp"),
        ]
    )
    db_session.commit()

    brief_id = "brief-human-destination"
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
                    "funnelId": str(funnel.id),
                    "experimentId": "exp-human-destination",
                    "variantId": "variant_human_destination",
                    "variantName": "Human Destination Variant",
                    "creativeConcept": "Resolve human-readable destination labels.",
                    "requirements": [
                        {
                            "channel": "facebook",
                            "format": "image_ad",
                            "funnelStage": "top-of-funnel",
                            "hook": "Map the destination label correctly.",
                            "angle": "Human-readable destination labels.",
                        }
                    ],
                }
            ]
        },
    )
    db_session.add(brief_artifact)
    db_session.commit()
    db_session.refresh(brief_artifact)

    asset = Asset(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        funnel_id=funnel.id,
        asset_brief_artifact_id=brief_artifact.id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.draft,
        asset_kind="image",
        channel_id="facebook",
        format="image_ad",
        content={"assetBriefId": brief_id},
        storage_key="creative/meta-review-human-destination.jpg",
        content_type="image/jpeg",
        size_bytes=1234,
        width=1080,
        height=1080,
        file_source="ai",
        file_status="ready",
        ai_metadata={
            "assetBriefId": brief_id,
            "requirementIndex": 0,
            "creativeGenerationBatchId": "batch-human-destination",
            "swipeCopyPack": _build_swipe_copy_pack(
                requirement_index=0,
                angle="Human-readable destination labels.",
                hook="Map the destination label correctly.",
                primary_text="Use the category label and still resolve the right page.",
                headline="Destination labels should normalize",
                description="Review setup should map the destination cleanly.",
            ),
            "swipeCopyInputs": _build_swipe_copy_inputs(
                source_label="12.png",
                source_url="https://example.com/swipes/12.png",
                angle_used="Human-readable destination labels.",
                destination_page="Presales Listicle Page",
            ),
        },
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    setup_resp = api_client.post(
        f"/campaigns/{campaign_id}/meta/review-setup",
        json={"assetBriefIds": [brief_id], "funnelId": str(funnel.id)},
    )
    assert setup_resp.status_code == 200

    creative_spec = db_session.scalar(
        select(MetaCreativeSpec).where(
            MetaCreativeSpec.campaign_id == campaign_id,
            MetaCreativeSpec.asset_id == asset.id,
        )
    )
    assert creative_spec is not None
    assert creative_spec.destination_url.endswith("/pre-sales")
    assert creative_spec.metadata_json["destinationPage"] == "pre-sales"


def test_campaign_meta_review_setup_requires_explicit_funnel_for_multi_funnel_selection(
    api_client,
    db_session,
) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="meta-review-multi-funnel",
        db_session=db_session,
    )

    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None

    first_funnel = Funnel(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        name="First Meta Funnel",
        route_slug="first-meta-funnel",
    )
    second_funnel = Funnel(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        name="Second Meta Funnel",
        route_slug="second-meta-funnel",
    )
    db_session.add_all([first_funnel, second_funnel])
    db_session.commit()
    db_session.refresh(first_funnel)
    db_session.refresh(second_funnel)

    db_session.add_all(
        [
            FunnelPage(funnel_id=first_funnel.id, name="Pre-sales", slug="pre-sales", template_id="pre_sales_listicle"),
            FunnelPage(funnel_id=second_funnel.id, name="Pre-sales", slug="pre-sales", template_id="pre_sales_listicle"),
        ]
    )
    db_session.commit()

    first_brief_id = "brief-multi-funnel-first"
    second_brief_id = "brief-multi-funnel-second"
    brief_artifact = Artifact(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        type=ArtifactTypeEnum.asset_brief,
        data={
            "asset_briefs": [
                {
                    "id": first_brief_id,
                    "campaignId": campaign_id,
                    "clientId": client_id,
                    "funnelId": str(first_funnel.id),
                    "experimentId": "exp-multi-funnel-first",
                    "variantId": "variant_multi_funnel_first",
                    "variantName": "First Funnel Variant",
                    "requirements": [{"channel": "facebook", "format": "image_ad", "funnelStage": "top-of-funnel"}],
                },
                {
                    "id": second_brief_id,
                    "campaignId": campaign_id,
                    "clientId": client_id,
                    "funnelId": str(second_funnel.id),
                    "experimentId": "exp-multi-funnel-second",
                    "variantId": "variant_multi_funnel_second",
                    "variantName": "Second Funnel Variant",
                    "requirements": [{"channel": "facebook", "format": "image_ad", "funnelStage": "top-of-funnel"}],
                },
            ]
        },
    )
    db_session.add(brief_artifact)
    db_session.commit()

    first_asset = Asset(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        funnel_id=first_funnel.id,
        asset_brief_artifact_id=brief_artifact.id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.draft,
        asset_kind="image",
        channel_id="facebook",
        format="image_ad",
        content={"assetBriefId": first_brief_id},
        storage_key="creative/meta-review-multi-funnel-first.jpg",
        content_type="image/jpeg",
        size_bytes=1234,
        width=1080,
        height=1080,
        file_source="ai",
        file_status="ready",
        ai_metadata={
            "assetBriefId": first_brief_id,
            "requirementIndex": 0,
            "creativeGenerationBatchId": "batch-multi-funnel",
            "swipeCopyPack": _build_swipe_copy_pack(
                requirement_index=0,
                angle="First funnel angle.",
                hook="First funnel hook.",
                primary_text="First funnel primary text.",
                headline="First funnel headline",
                description="First funnel description",
            ),
            "swipeCopyInputs": _build_swipe_copy_inputs(
                source_label="first.png",
                source_url="https://example.com/swipes/first.png",
                angle_used="First funnel angle.",
                destination_page="pre-sales",
            ),
        },
    )
    second_asset = Asset(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        funnel_id=second_funnel.id,
        asset_brief_artifact_id=brief_artifact.id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.draft,
        asset_kind="image",
        channel_id="facebook",
        format="image_ad",
        content={"assetBriefId": second_brief_id},
        storage_key="creative/meta-review-multi-funnel-second.jpg",
        content_type="image/jpeg",
        size_bytes=1234,
        width=1080,
        height=1080,
        file_source="ai",
        file_status="ready",
        ai_metadata={
            "assetBriefId": second_brief_id,
            "requirementIndex": 0,
            "creativeGenerationBatchId": "batch-multi-funnel",
            "swipeCopyPack": _build_swipe_copy_pack(
                requirement_index=0,
                angle="Second funnel angle.",
                hook="Second funnel hook.",
                primary_text="Second funnel primary text.",
                headline="Second funnel headline",
                description="Second funnel description",
            ),
            "swipeCopyInputs": _build_swipe_copy_inputs(
                source_label="second.png",
                source_url="https://example.com/swipes/second.png",
                angle_used="Second funnel angle.",
                destination_page="pre-sales",
            ),
        },
    )
    db_session.add_all([first_asset, second_asset])
    db_session.commit()

    setup_resp = api_client.post(
        f"/campaigns/{campaign_id}/meta/review-setup",
        json={"assetBriefIds": [first_brief_id, second_brief_id]},
    )
    assert setup_resp.status_code == 409
    assert setup_resp.json()["detail"] == {
        "message": "Selected asset briefs span multiple funnels. Pick one funnel in the Meta ads tab before preparing review.",
        "selectedAssetBriefIds": [first_brief_id, second_brief_id],
        "availableFunnelIds": sorted([str(first_funnel.id), str(second_funnel.id)]),
    }


def test_campaign_meta_review_setup_rejects_invalid_assets_before_writing_specs(
    api_client,
    db_session,
) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="meta-review-preflight",
        db_session=db_session,
    )

    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None

    funnel = Funnel(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        name="Meta Review Preflight Funnel",
        route_slug="meta-review-preflight-funnel",
    )
    db_session.add(funnel)
    db_session.commit()
    db_session.refresh(funnel)

    db_session.add_all(
        [
            FunnelPage(funnel_id=funnel.id, name="Pre-sales", slug="pre-sales", template_id="pre_sales_listicle"),
            FunnelPage(funnel_id=funnel.id, name="Sales", slug="sales", template_id="sales_pdp"),
        ]
    )
    db_session.commit()

    brief_id = "brief-preflight"
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
                    "funnelId": str(funnel.id),
                    "experimentId": "exp-preflight",
                    "variantId": "variant_preflight",
                    "variantName": "Preflight Variant",
                    "creativeConcept": "Reject invalid assets before writing specs.",
                    "requirements": [
                        {
                            "channel": "facebook",
                            "format": "image_ad",
                            "funnelStage": "top-of-funnel",
                            "hook": "Reject invalid destination and copy.",
                            "angle": "Preflight validation.",
                        }
                    ],
                }
            ]
        },
    )
    db_session.add(brief_artifact)
    db_session.commit()
    db_session.refresh(brief_artifact)

    asset = Asset(
        org_id=campaign.org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        product_id=product_id,
        funnel_id=funnel.id,
        asset_brief_artifact_id=brief_artifact.id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.draft,
        asset_kind="image",
        channel_id="facebook",
        format="image_ad",
        content={"assetBriefId": brief_id},
        storage_key="creative/meta-review-preflight.jpg",
        content_type="image/jpeg",
        size_bytes=1234,
        width=1080,
        height=1080,
        file_source="ai",
        file_status="ready",
        ai_metadata={
            "assetBriefId": brief_id,
            "requirementIndex": 0,
            "creativeGenerationBatchId": "batch-preflight",
            "swipeCopyPack": _build_swipe_copy_pack(
                requirement_index=0,
                angle="Preflight validation.",
                hook="Reject invalid destination and copy.",
                primary_text="We know you have diabetes before you click.",
                headline="Private-info framing should block prep",
                description="Preflight should stop this before QA.",
            ),
            "swipeCopyInputs": _build_swipe_copy_inputs(
                source_label="13.png",
                source_url="https://example.com/swipes/13.png",
                angle_used="Preflight validation.",
                destination_page="Mystery Funnel Page",
            ),
        },
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    setup_resp = api_client.post(
        f"/campaigns/{campaign_id}/meta/review-setup",
        json={"assetBriefIds": [brief_id], "funnelId": str(funnel.id)},
    )
    assert setup_resp.status_code == 409
    payload = setup_resp.json()["detail"]
    assert payload["message"] == (
        "Some generated assets cannot be prepared for Meta review until destination mapping or copy issues are fixed."
    )
    assert len(payload["invalidAssets"]) == 1
    invalid_asset = payload["invalidAssets"][0]
    assert invalid_asset["assetId"] == str(asset.id)
    rule_ids = {issue["ruleId"] for issue in invalid_asset["issues"]}
    assert "META-LP-001" in rule_ids
    assert "META-COPY-002" in rule_ids

    creative_specs = db_session.scalars(
        select(MetaCreativeSpec).where(MetaCreativeSpec.campaign_id == campaign_id)
    ).all()
    adset_specs = db_session.scalars(
        select(MetaAdSetSpec).where(MetaAdSetSpec.campaign_id == campaign_id)
    ).all()
    assert creative_specs == []
    assert adset_specs == []
