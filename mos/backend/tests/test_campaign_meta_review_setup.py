from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.enums import ArtifactTypeEnum, AssetSourceEnum, AssetStatusEnum
from app.db.models import Artifact, Asset, Campaign, Funnel, FunnelPage, MetaAdSetSpec, MetaCreativeSpec


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
) -> dict[str, object]:
    return {
        "adImageOrVideo": {
            "sourceLabel": source_label,
            "sourceUrl": source_url,
            "assetType": "image",
        },
        "angleUsed": angle_used,
        "destinationPage": destination_page,
    }


def test_campaign_meta_review_setup_creates_internal_specs_and_pipeline_payload(
    api_client,
    db_session,
) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(api_client, suffix="meta-review")

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
    assert len(setup_payload["createdAdSetSpecIds"]) == 1

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
    assert row["adset_specs"][0]["metadata_json"]["experimentSpecId"] == "exp-A02-Interaction Triage Workflow"

    library_pipeline_resp = api_client.get(f"/meta/pipeline/assets?clientId={client_id}&productId={product_id}&statuses=draft")
    assert library_pipeline_resp.status_code == 200
    library_pipeline = library_pipeline_resp.json()
    assert len(library_pipeline) == 1
    assert library_pipeline[0]["adset_specs"][0]["metadata_json"]["experimentSpecId"] == (
        "exp-A02-Interaction Triage Workflow"
    )


def test_campaign_meta_review_setup_ignores_legacy_assets_when_latest_batch_exists(
    api_client,
    db_session,
) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(api_client, suffix="meta-review-latest-batch")

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
    client_id, product_id, campaign_id = _create_campaign_with_product(api_client, suffix="meta-review-batch-scope")

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
    client_id, product_id, campaign_id = _create_campaign_with_product(api_client, suffix="meta-review-human-destination")

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
    client_id, product_id, campaign_id = _create_campaign_with_product(api_client, suffix="meta-review-multi-funnel")

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
    client_id, product_id, campaign_id = _create_campaign_with_product(api_client, suffix="meta-review-preflight")

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
