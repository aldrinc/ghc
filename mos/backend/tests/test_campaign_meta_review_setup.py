from app.db.enums import ArtifactTypeEnum, AssetSourceEnum, AssetStatusEnum
from app.db.models import Artifact, Asset, Campaign, Funnel, FunnelPage


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
            "asset_brief_types": ["image_ad"],
        },
    )
    assert campaign_resp.status_code == 201
    return client_id, product_id, campaign_resp.json()["id"]


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
        ai_metadata={"assetBriefId": brief_id, "requirementIndex": 0},
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    setup_resp = api_client.post(
        f"/campaigns/{campaign_id}/meta/review-setup",
        json={"assetBriefIds": [brief_id]},
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
    assert row["creative_spec"]["headline"] == "A clearer way to check interactions before you start."
    assert row["creative_spec"]["metadata_json"]["assetBriefId"] == brief_id
    assert row["creative_spec"]["metadata_json"]["reviewPaths"]["pre-sales"].endswith("/pre-sales")
    assert row["creative_spec"]["metadata_json"]["reviewPaths"]["sales"].endswith("/sales")
    assert row["experiment"]["id"] == "exp-A02-Interaction Triage Workflow"
    assert row["adset_specs"][0]["metadata_json"]["experimentSpecId"] == "exp-A02-Interaction Triage Workflow"
