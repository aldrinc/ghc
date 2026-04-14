from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.enums import ArtifactTypeEnum
from app.db.models import Artifact, Campaign
from app.routers import funnels as funnels_router
from app.routers import swipes as swipes_router
from app.services import funnel_testimonials
from app.services.template_image_workspace import TEMPLATE_IMAGE_ASSETS_DIR


def _create_campaign_with_product(api_client: TestClient, *, suffix: str) -> tuple[str, str, str]:
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


def test_sales_pdp_examples_endpoint_returns_five_examples(api_client: TestClient, monkeypatch) -> None:
    version = SimpleNamespace(id="draft-123")
    generated = [
        {"kind": "core_product_image", "variantId": "core", "assetId": "core-asset", "publicId": "core-public"},
        {"kind": "generated_pdp_carousel", "variantId": "dorm_selfie", "assetId": "a5", "publicId": "p5"},
        {"kind": "generated_pdp_carousel", "variantId": "bold_claim", "assetId": "a3", "publicId": "p3"},
        {"kind": "generated_pdp_carousel", "variantId": "standard_ugc", "assetId": "a1", "publicId": "p1"},
        {"kind": "generated_pdp_carousel", "variantId": "qa_ugc", "assetId": "a2", "publicId": "p2"},
        {"kind": "generated_pdp_carousel", "variantId": "personal_highlight", "assetId": "a4", "publicId": "p4"},
    ]

    def _fake_generate_sales_pdp_carousel_images(**_kwargs):
        return version, {"content": []}, generated

    monkeypatch.setattr(
        funnels_router,
        "generate_sales_pdp_carousel_images",
        _fake_generate_sales_pdp_carousel_images,
    )

    response = api_client.post("/funnels/funnel-1/pages/page-1/ai/sales-pdp-examples", json={})

    assert response.status_code == 201
    body = response.json()
    assert body["draftVersionId"] == "draft-123"
    assert [item["variantId"] for item in body["generatedPdpExamples"]] == [
        "standard_ugc",
        "qa_ugc",
        "bold_claim",
        "personal_highlight",
        "dorm_selfie",
    ]


def test_sales_pdp_examples_endpoint_errors_when_variant_missing(api_client: TestClient, monkeypatch) -> None:
    version = SimpleNamespace(id="draft-123")
    generated = [
        {"kind": "generated_pdp_carousel", "variantId": "standard_ugc", "assetId": "a1", "publicId": "p1"},
        {"kind": "generated_pdp_carousel", "variantId": "qa_ugc", "assetId": "a2", "publicId": "p2"},
        {"kind": "generated_pdp_carousel", "variantId": "bold_claim", "assetId": "a3", "publicId": "p3"},
        {"kind": "generated_pdp_carousel", "variantId": "personal_highlight", "assetId": "a4", "publicId": "p4"},
    ]

    def _fake_generate_sales_pdp_carousel_images(**_kwargs):
        return version, {"content": []}, generated

    monkeypatch.setattr(
        funnels_router,
        "generate_sales_pdp_carousel_images",
        _fake_generate_sales_pdp_carousel_images,
    )

    response = api_client.post("/funnels/funnel-1/pages/page-1/ai/sales-pdp-examples", json={})

    assert response.status_code == 400
    assert "Missing: dorm_selfie." in response.json()["detail"]


def test_swipe_and_testimonial_template_paths_share_workspace_assets_dir() -> None:
    assert swipes_router._TEMPLATE_IMAGES_DIR == TEMPLATE_IMAGE_ASSETS_DIR
    assert funnel_testimonials._PRE_SALES_TESTIMONIAL_TEMPLATE_DIR == TEMPLATE_IMAGE_ASSETS_DIR


def test_swipe_template_testimonials_endpoint_starts_one_workflow_per_template(
    api_client: TestClient,
    db_session,
    monkeypatch,
    tmp_path,
) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(api_client, suffix="SwipeTemplates")
    campaign = db_session.scalars(select(Campaign).where(Campaign.id == campaign_id)).first()
    assert campaign is not None
    db_session.add(
        Artifact(
            org_id=campaign.org_id,
            client_id=campaign.client_id,
            campaign_id=campaign.id,
            type=ArtifactTypeEnum.asset_brief,
            data={
                "asset_briefs": [
                    {
                        "id": "brief-1",
                        "funnelId": "funnel-123",
                        "requirements": [
                            {
                                "format": "image",
                                "channel": "meta",
                            }
                        ],
                    }
                ]
            },
        )
    )
    db_session.commit()

    template_dir = tmp_path / "template-images"
    template_dir.mkdir()
    (template_dir / "alpha.png").write_bytes(b"alpha")
    (template_dir / "beta.webp").write_bytes(b"beta")

    staged_assets: list[dict[str, object]] = []
    started_payloads = []

    def _fake_create_funnel_upload_asset(**kwargs):
        index = len(staged_assets) + 1
        asset = SimpleNamespace(id=f"staged-{index}", public_id=f"public-{index}")
        staged_assets.append({"kwargs": kwargs, "asset": asset})
        return asset

    async def _fake_start_swipe_image_ad_run(*, payload, auth, session, temporal=None):
        index = len(started_payloads) + 1
        started_payloads.append(payload)
        return {"workflow_run_id": f"wf-{index}", "temporal_workflow_id": f"twf-{index}"}

    async def _fake_get_temporal_client():
        return object()

    monkeypatch.setattr(swipes_router, "_TEMPLATE_IMAGES_DIR", template_dir)
    monkeypatch.setattr(swipes_router.settings, "PUBLIC_ASSET_BASE_URL", "https://assets.example.com")
    monkeypatch.setattr(swipes_router, "create_funnel_upload_asset", _fake_create_funnel_upload_asset)
    monkeypatch.setattr(swipes_router, "_start_swipe_image_ad_run", _fake_start_swipe_image_ad_run)
    monkeypatch.setattr(swipes_router, "get_temporal_client", _fake_get_temporal_client)

    response = api_client.post(
        "/swipes/generate-template-testimonials",
        json={"campaignId": campaign_id, "assetBriefId": "brief-1"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["campaignId"] == campaign_id
    assert body["clientId"] == client_id
    assert body["productId"] == product_id
    assert body["requirementIndex"] == 0
    assert [row["templateFile"] for row in body["templateRuns"]] == ["alpha.png", "beta.webp"]
    assert [row["workflowRunId"] for row in body["templateRuns"]] == ["wf-1", "wf-2"]

    assert len(staged_assets) == 2
    assert len(started_payloads) == 2
    assert [payload.asset_brief_id for payload in started_payloads] == ["brief-1", "brief-1"]
    assert [payload.requirement_index for payload in started_payloads] == [0, 0]
    assert [payload.swipe_image_url for payload in started_payloads] == [
        "https://assets.example.com/public/assets/public-1",
        "https://assets.example.com/public/assets/public-2",
    ]
    assert all(payload.count == 1 for payload in started_payloads)


def test_swipe_template_testimonials_endpoint_rejects_multiple_image_requirements(
    api_client: TestClient,
    db_session,
) -> None:
    _client_id, _product_id, campaign_id = _create_campaign_with_product(api_client, suffix="SwipeTemplatesMulti")
    campaign = db_session.scalars(select(Campaign).where(Campaign.id == campaign_id)).first()
    assert campaign is not None
    db_session.add(
        Artifact(
            org_id=campaign.org_id,
            client_id=campaign.client_id,
            campaign_id=campaign.id,
            type=ArtifactTypeEnum.asset_brief,
            data={
                "asset_briefs": [
                    {
                        "id": "brief-multi",
                        "requirements": [
                            {"format": "image"},
                            {"format": "image_ad"},
                        ],
                    }
                ]
            },
        )
    )
    db_session.commit()

    response = api_client.post(
        "/swipes/generate-template-testimonials",
        json={"campaignId": campaign_id, "assetBriefId": "brief-multi"},
    )

    assert response.status_code == 409
    assert "Found indexes: [0, 1]." in response.json()["detail"]


def test_swipe_generate_image_ad_endpoint_starts_workflow(api_client: TestClient, fake_temporal) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(api_client, suffix="SwipeDirect")

    response = api_client.post(
        "/swipes/generate-image-ad",
        json={
            "clientId": client_id,
            "productId": product_id,
            "campaignId": campaign_id,
            "assetBriefId": "brief-1",
            "requirementIndex": 0,
            "swipeImageUrl": "https://example.com/swipe.png",
            "aspectRatio": "1:1",
            "count": 1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body.get("workflow_run_id"), str)
    assert isinstance(body.get("temporal_workflow_id"), str)
    assert fake_temporal.started
