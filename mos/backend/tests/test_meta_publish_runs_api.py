from __future__ import annotations

import io
from datetime import datetime, timezone
from uuid import uuid4

from PIL import Image
from sqlalchemy import select

from app.db.enums import (
    ArtifactTypeEnum,
    AssetSourceEnum,
    AssetStatusEnum,
    FunnelEventTypeEnum,
    FunnelPageVersionStatusEnum,
    FunnelStatusEnum,
)
from app.db.models import (
    Artifact,
    Asset,
    Campaign,
    ClientUserPreference,
    Funnel,
    FunnelEvent,
    FunnelPage,
    FunnelPageVersion,
    FunnelPublication,
    FunnelPublicationPage,
    MetaAdAccountConnection,
    MetaAdSetSpec,
    MetaCampaign,
    MetaCreativeSpec,
    MetaWorkspaceAdConfig,
    ProductOffer,
    ProductVariant,
)
from app.routers import meta_ads as meta_ads_router
from app.services.integration_secrets import encrypt_secret_json
from app.services.meta_publish_defaults import (
    DEFAULT_META_PUBLISH_ATTRIBUTION_SPEC,
    DEFAULT_META_PUBLISH_CAMPAIGN_DAILY_BUDGET_MINOR_UNITS,
    DEFAULT_META_PUBLISH_TARGETING,
)
from app.services.paid_ads_qa import RULESET_VERSION
from tests.helpers.manual_creative_context import manual_creative_context_payload
from tests.helpers.launch_context import seed_ready_launch_context_for_campaign


TEST_ORG_ID = "00000000-0000-0000-0000-000000000001"


def _jpeg_bytes() -> bytes:
    image = Image.new("RGB", (16, 16), color=(120, 180, 40))
    output = io.BytesIO()
    image.save(output, format="JPEG")
    return output.getvalue()


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


def _create_asset(
    db_session,
    *,
    client_id: str,
    product_id: str,
    campaign_id: str,
    batch_id: str,
    suffix: str,
    asset_brief_id: str,
) -> Asset:
    content = _jpeg_bytes()
    asset = Asset(
        org_id=TEST_ORG_ID,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.approved,
        asset_kind="image",
        channel_id="facebook",
        format="image_ad",
        content={},
        storage_key=f"creative/{suffix}.jpg",
        content_type="image/jpeg",
        size_bytes=len(content),
        width=16,
        height=16,
        file_source="ai",
        file_status="ready",
        ai_metadata={"creativeGenerationBatchId": batch_id, "assetBriefId": asset_brief_id},
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


def _create_funnel_scoped_brief(
    db_session,
    *,
    client_id: str,
    campaign_id: str,
    brief_id: str,
    funnel_id: str,
) -> None:
    brief_artifact = Artifact(
        org_id=TEST_ORG_ID,
        client_id=client_id,
        campaign_id=campaign_id,
        type=ArtifactTypeEnum.asset_brief,
        data={
            "asset_briefs": [
                {
                    "id": brief_id,
                    "campaignId": campaign_id,
                    "clientId": client_id,
                    "funnelId": funnel_id,
                    "experimentId": f"exp-{brief_id}",
                    "requirements": [
                        {
                            "channel": "facebook",
                            "format": "image_ad",
                        }
                    ],
                }
            ]
        },
    )
    db_session.add(brief_artifact)
    db_session.commit()


def _set_selected_storefront_domain(
    db_session,
    *,
    client_id: str,
    storefront_domain: str,
    user_external_id: str = "test-user",
) -> None:
    preference = ClientUserPreference(
        org_id=TEST_ORG_ID,
        client_id=client_id,
        user_external_id=user_external_id,
        selected_shop_storefront_domain=storefront_domain,
    )
    db_session.add(preference)
    db_session.commit()


def _create_meta_publish_inputs(
    db_session,
    *,
    asset: Asset,
    campaign_id: str,
    experiment_key: str,
    with_targeting: bool = True,
) -> tuple[MetaCreativeSpec, MetaAdSetSpec]:
    creative_spec = MetaCreativeSpec(
        org_id=TEST_ORG_ID,
        asset_id=asset.id,
        campaign_id=campaign_id,
        name="Publish Creative",
        primary_text="Primary text",
        headline="Headline",
        description="Description",
        call_to_action_type="LEARN_MORE",
        destination_url="/presales",
        page_id="page_123",
        instagram_actor_id=None,
        status="draft",
        metadata_json={"experimentSpecId": experiment_key},
    )
    adset_spec = MetaAdSetSpec(
        org_id=TEST_ORG_ID,
        campaign_id=campaign_id,
        name="Launch Ad Set",
        status="draft",
        optimization_goal="OFFSITE_CONVERSIONS",
        billing_event="IMPRESSIONS",
        targeting=dict(DEFAULT_META_PUBLISH_TARGETING) if with_targeting else None,
        placements=None,
        daily_budget=None,
        lifetime_budget=None,
        bid_amount=None,
        start_time=None,
        end_time=None,
        promoted_object={"pixel_id": "pixel_123", "custom_event_type": "PURCHASE"},
        conversion_domain="shop.thehonestherbalist.com",
        metadata_json={
            "experimentSpecId": experiment_key,
            "attributionSpec": DEFAULT_META_PUBLISH_ATTRIBUTION_SPEC,
        },
    )
    db_session.add(creative_spec)
    db_session.add(adset_spec)
    db_session.commit()
    db_session.refresh(creative_spec)
    db_session.refresh(adset_spec)
    return creative_spec, adset_spec


def _seed_meta_workspace_config(db_session, *, client_id: str) -> MetaWorkspaceAdConfig:
    connection = MetaAdAccountConnection(
        org_id=TEST_ORG_ID,
        name="Primary Meta Connection",
        ad_account_id="act_123456",
        ad_account_name="Test Ad Account",
        business_manager_id="bm_123",
        business_manager_name="Test Business",
        graph_api_version="v23.0",
        graph_api_base_url="https://graph.facebook.com",
        credentials_encrypted=encrypt_secret_json({"accessToken": "meta-token"}),
        status="active",
        validation_status="passed",
    )
    db_session.add(connection)
    db_session.commit()
    db_session.refresh(connection)

    workspace_config = MetaWorkspaceAdConfig(
        org_id=TEST_ORG_ID,
        client_id=client_id,
        meta_connection_id=connection.id,
        name="Primary Meta Workspace Config",
        is_default=True,
        status="active",
        page_id="page_123",
        page_name="Test Page",
        pixel_id="pixel_123",
        verified_domain="shop.thehonestherbalist.com",
        validation_status="passed",
    )
    db_session.add(workspace_config)
    db_session.commit()
    db_session.refresh(workspace_config)
    return workspace_config


def _meta_management_benchmark_metadata() -> dict[str, object]:
    return {
        "metaManagementBenchmarks": {
            "version": 1,
            "adLinkCtrPct": {"minimum": 1.5, "good": 2.5},
            "presellCtrPct": {"target": 30.0},
            "salesPdpPurchaseCvrPct": {"minimum": 3.0, "good": 5.0},
            "checkoutCvrPct": {"target": 30.0},
            "salesPdpAtcPctPriceBands": [
                {"id": "entry_30", "label": "$30 and below", "maxPrice": 30.0, "target": 15.0},
                {"id": "core_97_126", "label": "$97-$126.99", "minPrice": 97.0, "maxPrice": 126.99, "target": 10.0},
                {"id": "premium_127_plus", "label": "$127+", "minPrice": 127.0, "target": 7.0},
            ],
        }
    }


def _upsert_meta_profile(
    api_client,
    *,
    client_id: str,
    metadata: dict[str, object] | None = None,
    page_name: str | None = "Test Page",
) -> None:
    response = api_client.put(
        f"/clients/{client_id}/paid-ads-qa/platforms/meta/profile",
        json={
            "rulesetVersion": RULESET_VERSION,
            "adAccountId": "act_123456",
            "pageId": "page_123",
            "pageName": page_name,
            "pixelId": "pixel_123",
            "verifiedDomain": "shop.thehonestherbalist.com",
            "verifiedDomainStatus": "verified",
            "metadata": metadata or {},
        },
    )
    assert response.status_code == 200


def _seed_management_funnel(
    db_session,
    *,
    client_id: str,
    product_id: str,
    campaign_id: str,
    price_cents: int = 10000,
) -> dict[str, object]:
    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None

    offer = ProductOffer(
        org_id=TEST_ORG_ID,
        client_id=client_id,
        product_id=product_id,
        name="Primary Offer",
        business_model="one_time",
    )
    db_session.add(offer)
    db_session.commit()
    db_session.refresh(offer)

    variant = ProductVariant(
        product_id=product_id,
        offer_id=offer.id,
        title="Default",
        price=price_cents,
        currency="USD",
        provider="shopify",
        external_price_id="gid://shopify/ProductVariant/123456789",
        option_values=None,
    )
    db_session.add(variant)
    db_session.commit()
    db_session.refresh(variant)

    funnel = Funnel(
        org_id=TEST_ORG_ID,
        client_id=client_id,
        campaign_id=campaign.id,
        product_id=product_id,
        selected_offer_id=offer.id,
        name="Management Funnel",
        route_slug=f"management-funnel-{uuid4().hex[:8]}",
        status=FunnelStatusEnum.published,
    )
    db_session.add(funnel)
    db_session.commit()
    db_session.refresh(funnel)

    presell_page = FunnelPage(
        funnel_id=funnel.id,
        name="Pre-Sell",
        slug="story",
        template_id="pre-sales-listicle",
        ordering=1,
    )
    sales_page = FunnelPage(
        funnel_id=funnel.id,
        name="Sales",
        slug="offer",
        template_id="sales-pdp",
        ordering=2,
    )
    db_session.add(presell_page)
    db_session.add(sales_page)
    db_session.commit()
    db_session.refresh(presell_page)
    db_session.refresh(sales_page)

    presell_page.next_page_id = sales_page.id
    db_session.add(presell_page)

    presell_version = FunnelPageVersion(
        page_id=presell_page.id,
        status=FunnelPageVersionStatusEnum.approved,
        puck_data={"root": {}},
    )
    sales_version = FunnelPageVersion(
        page_id=sales_page.id,
        status=FunnelPageVersionStatusEnum.approved,
        puck_data={"root": {}},
    )
    db_session.add(presell_version)
    db_session.add(sales_version)
    db_session.commit()
    db_session.refresh(presell_version)
    db_session.refresh(sales_version)

    publication = FunnelPublication(
        funnel_id=funnel.id,
        entry_page_id=presell_page.id,
        created_by="test-user",
    )
    db_session.add(publication)
    db_session.commit()
    db_session.refresh(publication)

    db_session.add(
        FunnelPublicationPage(
            publication_id=publication.id,
            page_id=presell_page.id,
            page_version_id=presell_version.id,
            slug_at_publish=presell_page.slug,
            title_at_publish=presell_page.name,
        )
    )
    db_session.add(
        FunnelPublicationPage(
            publication_id=publication.id,
            page_id=sales_page.id,
            page_version_id=sales_version.id,
            slug_at_publish=sales_page.slug,
            title_at_publish=sales_page.name,
        )
    )
    funnel.entry_page_id = presell_page.id
    funnel.active_publication_id = publication.id
    db_session.add(funnel)
    db_session.commit()
    db_session.refresh(funnel)

    return {
        "offer": offer,
        "variant": variant,
        "funnel": funnel,
        "publication": publication,
        "presellPage": presell_page,
        "salesPage": sales_page,
    }


def _seed_management_funnel_events(
    db_session,
    *,
    funnel: Funnel,
    publication: FunnelPublication,
    presell_page: FunnelPage,
    sales_page: FunnelPage,
) -> None:
    now = datetime.now(timezone.utc)
    events: list[FunnelEvent] = []
    for idx in range(10):
        session_id = f"session_{idx}"
        visitor_id = f"visitor_{idx}"
        events.append(
            FunnelEvent(
                occurred_at=now,
                org_id=funnel.org_id,
                client_id=funnel.client_id,
                campaign_id=funnel.campaign_id,
                funnel_id=funnel.id,
                publication_id=publication.id,
                page_id=presell_page.id,
                event_type=FunnelEventTypeEnum.pre_sales_page_view,
                visitor_id=visitor_id,
                session_id=session_id,
                host="funnel.example",
                path="/story",
                referrer=None,
                utm={"source": "meta"},
                props={},
            )
        )
        events.append(
            FunnelEvent(
                occurred_at=now,
                org_id=funnel.org_id,
                client_id=funnel.client_id,
                campaign_id=funnel.campaign_id,
                funnel_id=funnel.id,
                publication_id=publication.id,
                page_id=sales_page.id,
                event_type=FunnelEventTypeEnum.sales_page_view,
                visitor_id=visitor_id,
                session_id=session_id,
                host="funnel.example",
                path="/offer",
                referrer=None,
                utm={"source": "meta"},
                props={},
            )
        )
    for idx in range(3):
        events.append(
            FunnelEvent(
                occurred_at=now,
                org_id=funnel.org_id,
                client_id=funnel.client_id,
                campaign_id=funnel.campaign_id,
                funnel_id=funnel.id,
                publication_id=publication.id,
                page_id=presell_page.id,
                event_type=FunnelEventTypeEnum.pre_sales_to_sales_click,
                visitor_id=f"visitor_{idx}",
                session_id=f"session_{idx}",
                host="funnel.example",
                path="/story",
                referrer=None,
                utm={"source": "meta"},
                props={},
            )
        )
    for event_type in (FunnelEventTypeEnum.checkout_started, FunnelEventTypeEnum.order_completed):
        events.append(
            FunnelEvent(
                occurred_at=now,
                org_id=funnel.org_id,
                client_id=funnel.client_id,
                campaign_id=funnel.campaign_id,
                funnel_id=funnel.id,
                publication_id=publication.id,
                page_id=sales_page.id,
                event_type=event_type,
                visitor_id="visitor_0",
                session_id="session_0",
                host="funnel.example",
                path="/offer",
                referrer=None,
                utm={"source": "meta"},
                props={},
            )
        )

    db_session.add_all(events)
    db_session.commit()


def _exclude_asset_from_publish(api_client, *, campaign_id: str, generation_key: str, asset_id: str) -> None:
    response = api_client.put(
        f"/meta/campaigns/{campaign_id}/publish-selections",
        json={
            "generationKey": generation_key,
            "decisions": [{"assetId": asset_id, "decision": "excluded"}],
        },
    )
    assert response.status_code == 200


def test_validate_meta_publish_plan_reports_blockers(api_client, db_session) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="publish-validate",
        db_session=db_session,
    )
    funnel_id = str(uuid4())
    brief_id = "brief-publish-validate"
    _create_funnel_scoped_brief(
        db_session,
        client_id=client_id,
        campaign_id=campaign_id,
        brief_id=brief_id,
        funnel_id=funnel_id,
    )
    asset = _create_asset(
        db_session,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        batch_id="latest-run",
        suffix="publish-validate",
        asset_brief_id=brief_id,
    )
    _create_meta_publish_inputs(
        db_session,
        asset=asset,
        campaign_id=campaign_id,
        experiment_key="exp-validate",
        with_targeting=False,
    )
    _upsert_meta_profile(api_client, client_id=client_id)

    response = api_client.post(
        f"/meta/campaigns/{campaign_id}/publish-plan/validate",
        json={
            "generationKey": "batch:latest-run",
            "funnelId": funnel_id,
            "publishBaseUrl": "https://shop.thehonestherbalist.com",
            "campaignName": "Honest Herbalist Launch",
            "campaignObjective": "OUTCOME_SALES",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["items"][0]["status"] == "blocked"
    assert "missing targeting" in payload["items"][0]["blockers"][0].lower()


def test_validate_meta_publish_plan_blocks_when_all_assets_are_excluded(api_client, db_session) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="publish-all-excluded",
        db_session=db_session,
    )
    funnel_id = str(uuid4())
    brief_id = "brief-publish-all-excluded"
    _create_funnel_scoped_brief(
        db_session,
        client_id=client_id,
        campaign_id=campaign_id,
        brief_id=brief_id,
        funnel_id=funnel_id,
    )
    asset = _create_asset(
        db_session,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        batch_id="latest-run",
        suffix="publish-all-excluded",
        asset_brief_id=brief_id,
    )
    _create_meta_publish_inputs(
        db_session,
        asset=asset,
        campaign_id=campaign_id,
        experiment_key="exp-all-excluded",
        with_targeting=True,
    )
    _upsert_meta_profile(api_client, client_id=client_id)
    _exclude_asset_from_publish(
        api_client,
        campaign_id=campaign_id,
        generation_key="batch:latest-run",
        asset_id=str(asset.id),
    )

    response = api_client.post(
        f"/meta/campaigns/{campaign_id}/publish-plan/validate",
        json={
            "generationKey": "batch:latest-run",
            "funnelId": funnel_id,
            "publishBaseUrl": "https://shop.thehonestherbalist.com",
            "campaignName": "Honest Herbalist Launch",
            "campaignObjective": "OUTCOME_SALES",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["blockers"] == ["All creatives are excluded from the final Meta package for this generation."]
    assert payload["includedCount"] == 0
    assert payload["items"] == []


def test_validate_meta_publish_plan_rejects_mismatched_storefront_host(api_client, db_session) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="publish-storefront-mismatch",
        db_session=db_session,
    )
    funnel_id = str(uuid4())
    brief_id = "brief-publish-storefront-mismatch"
    _create_funnel_scoped_brief(
        db_session,
        client_id=client_id,
        campaign_id=campaign_id,
        brief_id=brief_id,
        funnel_id=funnel_id,
    )
    _set_selected_storefront_domain(
        db_session,
        client_id=client_id,
        storefront_domain="thehonestherbalist.com",
    )
    asset = _create_asset(
        db_session,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        batch_id="latest-run",
        suffix="publish-storefront-mismatch",
        asset_brief_id=brief_id,
    )
    _create_meta_publish_inputs(
        db_session,
        asset=asset,
        campaign_id=campaign_id,
        experiment_key="exp-storefront-mismatch",
        with_targeting=True,
    )
    _upsert_meta_profile(api_client, client_id=client_id)

    response = api_client.post(
        f"/meta/campaigns/{campaign_id}/publish-plan/validate",
        json={
            "generationKey": "batch:latest-run",
            "funnelId": funnel_id,
            "publishBaseUrl": "https://shop.moshq.app",
            "campaignName": "Honest Herbalist Launch",
            "campaignObjective": "OUTCOME_SALES",
        },
    )

    assert response.status_code == 409
    payload = response.json()["detail"]
    assert payload["publishBaseUrl"] == "https://shop.moshq.app"
    assert payload["expectedPublishBaseUrl"] == "https://shop.thehonestherbalist.com"


def test_validate_meta_publish_plan_scopes_to_requested_funnel(api_client, db_session) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="publish-funnel-scope",
        db_session=db_session,
    )
    funnel_id = str(uuid4())
    other_funnel_id = str(uuid4())
    brief_id = "brief-publish-funnel-scope"
    other_brief_id = "brief-publish-funnel-scope-other"
    _create_funnel_scoped_brief(
        db_session,
        client_id=client_id,
        campaign_id=campaign_id,
        brief_id=brief_id,
        funnel_id=funnel_id,
    )
    _create_funnel_scoped_brief(
        db_session,
        client_id=client_id,
        campaign_id=campaign_id,
        brief_id=other_brief_id,
        funnel_id=other_funnel_id,
    )
    asset = _create_asset(
        db_session,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        batch_id="latest-run",
        suffix="publish-funnel-scope",
        asset_brief_id=brief_id,
    )
    _create_asset(
        db_session,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        batch_id="latest-run",
        suffix="publish-funnel-scope-other",
        asset_brief_id=other_brief_id,
    )
    _create_meta_publish_inputs(
        db_session,
        asset=asset,
        campaign_id=campaign_id,
        experiment_key="exp-funnel-scope",
        with_targeting=True,
    )
    _upsert_meta_profile(api_client, client_id=client_id)

    response = api_client.post(
        f"/meta/campaigns/{campaign_id}/publish-plan/validate",
        json={
            "generationKey": "batch:latest-run",
            "funnelId": funnel_id,
            "publishBaseUrl": "https://shop.thehonestherbalist.com",
            "campaignName": "Honest Herbalist Launch",
            "campaignObjective": "OUTCOME_SALES",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["includedCount"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["assetId"] == str(asset.id)
    assert payload["budgetScope"] == "campaign"
    assert payload["campaignDailyBudget"] == DEFAULT_META_PUBLISH_CAMPAIGN_DAILY_BUDGET_MINOR_UNITS


def test_validate_meta_publish_plan_respects_requested_campaign_daily_budget(api_client, db_session) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="publish-custom-cbo-budget",
        db_session=db_session,
    )
    funnel_id = str(uuid4())
    brief_id = "brief-publish-custom-cbo-budget"
    _create_funnel_scoped_brief(
        db_session,
        client_id=client_id,
        campaign_id=campaign_id,
        brief_id=brief_id,
        funnel_id=funnel_id,
    )
    asset = _create_asset(
        db_session,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        batch_id="latest-run",
        suffix="publish-custom-cbo-budget",
        asset_brief_id=brief_id,
    )
    _create_meta_publish_inputs(
        db_session,
        asset=asset,
        campaign_id=campaign_id,
        experiment_key="exp-custom-cbo-budget",
        with_targeting=True,
    )
    _upsert_meta_profile(api_client, client_id=client_id)

    response = api_client.post(
        f"/meta/campaigns/{campaign_id}/publish-plan/validate",
        json={
            "generationKey": "batch:latest-run",
            "funnelId": funnel_id,
            "publishBaseUrl": "https://shop.thehonestherbalist.com",
            "campaignName": "Honest Herbalist Launch",
            "campaignObjective": "OUTCOME_SALES",
            "campaignDailyBudget": 25000,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["budgetScope"] == "campaign"
    assert payload["campaignDailyBudget"] == 25000


def test_publish_meta_run_creates_paused_entities_and_history(api_client, db_session, monkeypatch) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="publish-run",
        db_session=db_session,
    )
    funnel_id = str(uuid4())
    brief_id = "brief-publish-run"
    _create_funnel_scoped_brief(
        db_session,
        client_id=client_id,
        campaign_id=campaign_id,
        brief_id=brief_id,
        funnel_id=funnel_id,
    )
    asset = _create_asset(
        db_session,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        batch_id="latest-run",
        suffix="publish-run",
        asset_brief_id=brief_id,
    )
    creative_spec, _adset_spec = _create_meta_publish_inputs(
        db_session,
        asset=asset,
        campaign_id=campaign_id,
        experiment_key="exp-publish",
        with_targeting=True,
    )
    creative_spec.call_to_action_type = "Learn More"
    db_session.add(creative_spec)
    db_session.commit()
    _upsert_meta_profile(api_client, client_id=client_id)

    content = _jpeg_bytes()

    class _FakeStorage:
        def download_bytes(self, *, key: str, bucket: str | None = None) -> tuple[bytes, str]:
            _ = bucket
            assert key == "creative/publish-run.jpg"
            return content, "image/jpeg"

    class _FakeMetaClient:
        def upload_image(self, **kwargs):
            assert kwargs["ad_account_id"] == "act_123456"
            return {"images": {kwargs["filename"]: {"hash": "hash_123"}}}

        def create_campaign(self, **kwargs):
            assert kwargs["ad_account_id"] == "act_123456"
            assert kwargs["payload"]["name"] == "Honest Herbalist Launch"
            assert kwargs["payload"]["status"] == "PAUSED"
            assert kwargs["payload"]["daily_budget"] == DEFAULT_META_PUBLISH_CAMPAIGN_DAILY_BUDGET_MINOR_UNITS
            assert "is_adset_budget_sharing_enabled" not in kwargs["payload"]
            return {"id": "meta_campaign_123", "status": "PAUSED"}

        def create_adset(self, **kwargs):
            assert kwargs["payload"]["status"] == "PAUSED"
            assert kwargs["payload"]["dsa_beneficiary"] == "Test Page"
            assert kwargs["payload"]["dsa_payor"] == "Test Page"
            assert kwargs["payload"]["targeting"]["geo_locations"]["countries"] == list(DEFAULT_META_PUBLISH_TARGETING["geo_locations"]["countries"])
            assert kwargs["payload"]["targeting"]["brand_safety_content_filter_levels"] == ["FACEBOOK_RELAXED"]
            assert kwargs["payload"]["targeting"]["targeting_automation"]["advantage_audience"] == 1
            assert "daily_budget" not in kwargs["payload"]
            assert "lifetime_budget" not in kwargs["payload"]
            assert kwargs["payload"]["attribution_spec"] == DEFAULT_META_PUBLISH_ATTRIBUTION_SPEC
            return {"id": "meta_adset_123", "status": "PAUSED"}

        def create_adcreative(self, **kwargs):
            assert kwargs["payload"]["object_story_spec"]["page_id"] == "page_123"
            assert kwargs["payload"]["object_story_spec"]["link_data"]["link"] == "https://shop.thehonestherbalist.com/presales"
            assert kwargs["payload"]["object_story_spec"]["link_data"]["call_to_action"]["type"] == "LEARN_MORE"
            return {"id": "meta_creative_123"}

        def create_ad(self, **kwargs):
            assert kwargs["payload"]["status"] == "PAUSED"
            return {"id": "meta_ad_123", "status": "PAUSED"}

    monkeypatch.setattr(meta_ads_router, "MediaStorage", _FakeStorage)
    monkeypatch.setattr(meta_ads_router, "_get_meta_client", lambda **kwargs: _FakeMetaClient())

    publish_response = api_client.post(
        f"/meta/campaigns/{campaign_id}/publish-runs",
        json={
            "generationKey": "batch:latest-run",
            "funnelId": funnel_id,
            "publishBaseUrl": "https://shop.thehonestherbalist.com",
            "campaignName": "Honest Herbalist Launch",
            "campaignObjective": "OUTCOME_SALES",
            "buyingType": "AUCTION",
        },
    )

    assert publish_response.status_code == 200
    publish_payload = publish_response.json()
    assert publish_payload["status"] == "published"
    assert publish_payload["metaCampaignId"] == "meta_campaign_123"
    assert publish_payload["publishDomain"] == "shop.thehonestherbalist.com"
    assert len(publish_payload["items"]) == 1
    assert publish_payload["items"][0]["status"] == "published"
    assert publish_payload["items"][0]["metaCreativeId"] == "meta_creative_123"
    assert publish_payload["items"][0]["metaAdSetId"] == "meta_adset_123"
    assert publish_payload["items"][0]["metaAdId"] == "meta_ad_123"

    history_response = api_client.get(f"/meta/campaigns/{campaign_id}/publish-runs")
    assert history_response.status_code == 200
    history_payload = history_response.json()
    assert len(history_payload) == 1
    assert history_payload[0]["id"] == publish_payload["id"]
    assert history_payload[0]["items"][0]["metaAdId"] == "meta_ad_123"


def test_publish_meta_run_uses_requested_campaign_daily_budget(api_client, db_session, monkeypatch) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="publish-run-custom-budget",
        db_session=db_session,
    )
    funnel_id = str(uuid4())
    brief_id = "brief-publish-run-custom-budget"
    _create_funnel_scoped_brief(
        db_session,
        client_id=client_id,
        campaign_id=campaign_id,
        brief_id=brief_id,
        funnel_id=funnel_id,
    )
    asset = _create_asset(
        db_session,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        batch_id="latest-run",
        suffix="publish-run-custom-budget",
        asset_brief_id=brief_id,
    )
    _create_meta_publish_inputs(
        db_session,
        asset=asset,
        campaign_id=campaign_id,
        experiment_key="exp-publish-run-custom-budget",
        with_targeting=True,
    )
    _upsert_meta_profile(api_client, client_id=client_id)

    content = _jpeg_bytes()

    class _FakeStorage:
        def download_bytes(self, *, key: str, bucket: str | None = None) -> tuple[bytes, str]:
            _ = bucket
            assert key == "creative/publish-run-custom-budget.jpg"
            return content, "image/jpeg"

    class _FakeMetaClient:
        def upload_image(self, **kwargs):
            assert kwargs["ad_account_id"] == "act_123456"
            return {"images": {kwargs["filename"]: {"hash": "hash_987"}}}

        def create_campaign(self, **kwargs):
            assert kwargs["payload"]["daily_budget"] == 25000
            return {"id": "meta_campaign_custom_budget", "status": "PAUSED"}

        def create_adset(self, **kwargs):
            return {"id": "meta_adset_custom_budget", "status": "PAUSED"}

        def create_adcreative(self, **kwargs):
            return {"id": "meta_creative_custom_budget"}

        def create_ad(self, **kwargs):
            return {"id": "meta_ad_custom_budget", "status": "PAUSED"}

    monkeypatch.setattr(meta_ads_router, "MediaStorage", _FakeStorage)
    monkeypatch.setattr(meta_ads_router, "_get_meta_client", lambda **kwargs: _FakeMetaClient())

    publish_response = api_client.post(
        f"/meta/campaigns/{campaign_id}/publish-runs",
        json={
            "generationKey": "batch:latest-run",
            "funnelId": funnel_id,
            "publishBaseUrl": "https://shop.thehonestherbalist.com",
            "campaignName": "Honest Herbalist Launch",
            "campaignObjective": "OUTCOME_SALES",
            "campaignDailyBudget": 25000,
        },
    )

    assert publish_response.status_code == 200
    publish_payload = publish_response.json()
    assert publish_payload["metadata"]["budgetScope"] == "campaign"
    assert publish_payload["metadata"]["campaignDailyBudget"] == 25000


def test_publish_meta_run_reuses_existing_asset_upload_when_launch_plan_changes(
    api_client,
    db_session,
    monkeypatch,
) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="publish-rerun-upload-reuse",
        db_session=db_session,
    )
    funnel_id = str(uuid4())
    brief_id = "brief-publish-rerun-upload-reuse"
    _create_funnel_scoped_brief(
        db_session,
        client_id=client_id,
        campaign_id=campaign_id,
        brief_id=brief_id,
        funnel_id=funnel_id,
    )
    asset = _create_asset(
        db_session,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        batch_id="latest-run",
        suffix="publish-rerun-upload-reuse",
        asset_brief_id=brief_id,
    )
    _creative_spec, adset_spec = _create_meta_publish_inputs(
        db_session,
        asset=asset,
        campaign_id=campaign_id,
        experiment_key="exp-publish-rerun-upload-reuse",
        with_targeting=True,
    )
    adset_spec.dsa_payor = "Initial Payor"
    db_session.add(adset_spec)
    db_session.commit()
    _upsert_meta_profile(api_client, client_id=client_id)

    content = _jpeg_bytes()
    counters = {
        "upload_image": 0,
        "create_campaign": 0,
        "create_adset": 0,
        "create_adcreative": 0,
        "create_ad": 0,
    }

    class _FakeStorage:
        def download_bytes(self, *, key: str, bucket: str | None = None) -> tuple[bytes, str]:
            _ = bucket
            assert key == "creative/publish-rerun-upload-reuse.jpg"
            return content, "image/jpeg"

    class _FakeMetaClient:
        def upload_image(self, **kwargs):
            counters["upload_image"] += 1
            assert kwargs["ad_account_id"] == "act_123456"
            return {"images": {kwargs["filename"]: {"hash": "hash_reuse_123"}}}

        def create_campaign(self, **kwargs):
            counters["create_campaign"] += 1
            assert kwargs["ad_account_id"] == "act_123456"
            assert kwargs["payload"]["daily_budget"] == DEFAULT_META_PUBLISH_CAMPAIGN_DAILY_BUDGET_MINOR_UNITS
            return {"id": f"meta_campaign_{counters['create_campaign']}", "status": "PAUSED"}

        def create_adset(self, **kwargs):
            counters["create_adset"] += 1
            assert kwargs["payload"]["status"] == "PAUSED"
            return {"id": f"meta_adset_{counters['create_adset']}", "status": "PAUSED"}

        def create_adcreative(self, **kwargs):
            counters["create_adcreative"] += 1
            return {"id": f"meta_creative_{counters['create_adcreative']}"}

        def create_ad(self, **kwargs):
            counters["create_ad"] += 1
            assert kwargs["payload"]["status"] == "PAUSED"
            return {"id": f"meta_ad_{counters['create_ad']}", "status": "PAUSED"}

    monkeypatch.setattr(meta_ads_router, "MediaStorage", _FakeStorage)
    monkeypatch.setattr(meta_ads_router, "_get_meta_client", lambda **kwargs: _FakeMetaClient())

    first_response = api_client.post(
        f"/meta/campaigns/{campaign_id}/publish-runs",
        json={
            "generationKey": "batch:latest-run",
            "funnelId": funnel_id,
            "publishBaseUrl": "https://shop.thehonestherbalist.com",
            "campaignName": "Honest Herbalist V2",
            "campaignObjective": "OUTCOME_SALES",
            "buyingType": "AUCTION",
        },
    )

    assert first_response.status_code == 200
    first_payload = first_response.json()
    assert first_payload["status"] == "published"
    first_upload_id = first_payload["items"][0]["metaAssetUploadId"]
    assert first_upload_id

    adset_spec.dsa_payor = "Updated Payor"
    db_session.add(adset_spec)
    db_session.commit()

    second_response = api_client.post(
        f"/meta/campaigns/{campaign_id}/publish-runs",
        json={
            "generationKey": "batch:latest-run",
            "funnelId": funnel_id,
            "publishBaseUrl": "https://shop.thehonestherbalist.com",
            "campaignName": "Honest Herbalist V2",
            "campaignObjective": "OUTCOME_SALES",
            "buyingType": "AUCTION",
        },
    )

    assert second_response.status_code == 200
    second_payload = second_response.json()
    assert second_payload["status"] == "published"
    assert second_payload["items"][0]["metaAssetUploadId"] == first_upload_id
    assert counters["upload_image"] == 1
    assert counters["create_campaign"] == 2
    assert counters["create_adset"] == 2
    assert counters["create_adcreative"] == 2
    assert counters["create_ad"] == 2


def test_validate_meta_publish_plan_blocks_eu_targeting_without_dsa_defaults(api_client, db_session) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="publish-eu-dsa",
        db_session=db_session,
    )
    funnel_id = str(uuid4())
    brief_id = "brief-publish-eu-dsa"
    _create_funnel_scoped_brief(
        db_session,
        client_id=client_id,
        campaign_id=campaign_id,
        brief_id=brief_id,
        funnel_id=funnel_id,
    )
    asset = _create_asset(
        db_session,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        batch_id="latest-run",
        suffix="publish-eu-dsa",
        asset_brief_id=brief_id,
    )
    _creative_spec, adset_spec = _create_meta_publish_inputs(
        db_session,
        asset=asset,
        campaign_id=campaign_id,
        experiment_key="exp-eu-dsa",
        with_targeting=True,
    )
    adset_spec.targeting = {"geo_locations": {"countries": ["DE"]}}
    db_session.commit()
    db_session.refresh(adset_spec)
    _upsert_meta_profile(api_client, client_id=client_id, page_name=None)

    response = api_client.post(
        f"/meta/campaigns/{campaign_id}/publish-plan/validate",
        json={
            "generationKey": "batch:latest-run",
            "funnelId": funnel_id,
            "publishBaseUrl": "https://shop.thehonestherbalist.com",
            "campaignName": "Honest Herbalist Launch",
            "campaignObjective": "OUTCOME_SALES",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["items"][0]["status"] == "blocked"
    assert meta_ads_router._missing_dsa_party_message("dsaBeneficiary") in payload["items"][0]["blockers"]
    assert meta_ads_router._missing_dsa_party_message("dsaPayor") in payload["items"][0]["blockers"]


def test_validate_meta_publish_plan_blocks_invalid_cta_type(api_client, db_session) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="publish-invalid-cta",
        db_session=db_session,
    )
    funnel_id = str(uuid4())
    brief_id = "brief-publish-invalid-cta"
    _create_funnel_scoped_brief(
        db_session,
        client_id=client_id,
        campaign_id=campaign_id,
        brief_id=brief_id,
        funnel_id=funnel_id,
    )
    asset = _create_asset(
        db_session,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        batch_id="latest-run",
        suffix="publish-invalid-cta",
        asset_brief_id=brief_id,
    )
    creative_spec, _adset_spec = _create_meta_publish_inputs(
        db_session,
        asset=asset,
        campaign_id=campaign_id,
        experiment_key="exp-invalid-cta",
        with_targeting=True,
    )
    creative_spec.call_to_action_type = "Click Here"
    db_session.add(creative_spec)
    db_session.commit()
    _upsert_meta_profile(api_client, client_id=client_id)

    response = api_client.post(
        f"/meta/campaigns/{campaign_id}/publish-plan/validate",
        json={
            "generationKey": "batch:latest-run",
            "funnelId": funnel_id,
            "publishBaseUrl": "https://shop.thehonestherbalist.com",
            "campaignName": "Honest Herbalist Launch",
            "campaignObjective": "OUTCOME_SALES",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["items"][0]["status"] == "blocked"
    assert any(
        "Unsupported Meta callToActionType 'Click Here'." in blocker
        for blocker in payload["items"][0]["blockers"]
    )


def test_validate_meta_publish_plan_blocks_daily_budget_under_meta_minimum(api_client, db_session) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="publish-low-budget",
        db_session=db_session,
    )
    funnel_id = str(uuid4())
    brief_id = "brief-publish-low-budget"
    _create_funnel_scoped_brief(
        db_session,
        client_id=client_id,
        campaign_id=campaign_id,
        brief_id=brief_id,
        funnel_id=funnel_id,
    )
    asset = _create_asset(
        db_session,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        batch_id="latest-run",
        suffix="publish-low-budget",
        asset_brief_id=brief_id,
    )
    _creative_spec, adset_spec = _create_meta_publish_inputs(
        db_session,
        asset=asset,
        campaign_id=campaign_id,
        experiment_key="exp-low-budget",
        with_targeting=True,
    )
    adset_spec.daily_budget = 100
    db_session.add(adset_spec)
    db_session.commit()
    _upsert_meta_profile(api_client, client_id=client_id)

    response = api_client.post(
        f"/meta/campaigns/{campaign_id}/publish-plan/validate",
        json={
            "generationKey": "batch:latest-run",
            "funnelId": funnel_id,
            "publishBaseUrl": "https://shop.thehonestherbalist.com",
            "campaignName": "Honest Herbalist Launch",
            "campaignObjective": "OUTCOME_SALES",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["items"][0]["status"] == "blocked"
    assert meta_ads_router._meta_daily_budget_too_low_message("Linked Meta ad set spec") in payload["items"][0]["blockers"]


def test_validate_meta_publish_plan_blocks_duplicate_placement_keys(api_client, db_session) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="publish-placement-dup",
        db_session=db_session,
    )
    funnel_id = str(uuid4())
    brief_id = "brief-publish-placement-dup"
    _create_funnel_scoped_brief(
        db_session,
        client_id=client_id,
        campaign_id=campaign_id,
        brief_id=brief_id,
        funnel_id=funnel_id,
    )
    asset = _create_asset(
        db_session,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        batch_id="latest-run",
        suffix="publish-placement-dup",
        asset_brief_id=brief_id,
    )
    _creative_spec, adset_spec = _create_meta_publish_inputs(
        db_session,
        asset=asset,
        campaign_id=campaign_id,
        experiment_key="exp-placement-dup",
        with_targeting=True,
    )
    adset_spec.targeting = {
        "geo_locations": {"countries": ["US"]},
        "publisher_platforms": ["instagram"],
    }
    adset_spec.placements = {"publisher_platforms": ["facebook"]}
    db_session.commit()
    db_session.refresh(adset_spec)
    _upsert_meta_profile(api_client, client_id=client_id)

    response = api_client.post(
        f"/meta/campaigns/{campaign_id}/publish-plan/validate",
        json={
            "generationKey": "batch:latest-run",
            "funnelId": funnel_id,
            "publishBaseUrl": "https://shop.thehonestherbalist.com",
            "campaignName": "Honest Herbalist Launch",
            "campaignObjective": "OUTCOME_SALES",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["items"][0]["status"] == "blocked"
    assert any(
        "Linked Meta ad set spec duplicates placement keys in targeting and placements: publisher_platforms."
        in blocker
        for blocker in payload["items"][0]["blockers"]
    )


def test_validate_meta_publish_plan_supports_external_delivery_without_funnel(
    api_client,
    db_session,
    monkeypatch,
) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="publish-external",
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
    validate_delivery = api_client.post(f"/campaigns/{campaign_id}/delivery/validate")
    assert validate_delivery.status_code == 200, validate_delivery.text

    brief_id = "brief-publish-external"
    brief_artifact = Artifact(
        org_id=TEST_ORG_ID,
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
                    "experimentId": "exp-publish-external",
                    "requirements": [{"channel": "facebook", "format": "image_ad"}],
                }
            ]
        },
    )
    db_session.add(brief_artifact)
    db_session.commit()

    asset = _create_asset(
        db_session,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        batch_id="latest-run",
        suffix="publish-external",
        asset_brief_id=brief_id,
    )
    creative_spec = MetaCreativeSpec(
        org_id=TEST_ORG_ID,
        asset_id=asset.id,
        campaign_id=campaign_id,
        name="External Publish Creative",
        primary_text="Primary text",
        headline="Headline",
        description="Description",
        call_to_action_type="LEARN_MORE",
        destination_url="https://lp.example.com/pre-sale",
        page_id="page_123",
        instagram_actor_id=None,
        status="draft",
        metadata_json={
            "experimentSpecId": "exp-publish-external",
            "destinationSource": "campaign_delivery_config",
            "resolvedDestinationUrl": "https://lp.example.com/pre-sale",
        },
    )
    adset_spec = MetaAdSetSpec(
        org_id=TEST_ORG_ID,
        campaign_id=campaign_id,
        name="External Launch Ad Set",
        status="draft",
        optimization_goal="OFFSITE_CONVERSIONS",
        billing_event="IMPRESSIONS",
        targeting={"geo_locations": {"countries": ["US"]}},
        placements={"publisher_platforms": ["facebook"]},
        daily_budget=5000,
        lifetime_budget=None,
        bid_amount=None,
        start_time=None,
        end_time=None,
        promoted_object={"pixel_id": "pixel_123", "custom_event_type": "PURCHASE"},
        conversion_domain="lp.example.com",
        metadata_json={"experimentSpecId": "exp-publish-external"},
    )
    db_session.add(creative_spec)
    db_session.add(adset_spec)
    db_session.commit()

    _upsert_meta_profile(api_client, client_id=client_id)

    response = api_client.post(
        f"/meta/campaigns/{campaign_id}/publish-plan/validate",
        json={
            "generationKey": "batch:latest-run",
            "publishBaseUrl": "https://shop.thehonestherbalist.com",
            "campaignName": "External Launch",
            "campaignObjective": "OUTCOME_SALES",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["includedCount"] == 1
    assert payload["items"][0]["resolvedDestinationUrl"] == "https://lp.example.com/pre-sale"
    assert payload["publishDomain"] == "lp.example.com"


def test_validate_meta_publish_plan_supports_manual_creative_context_without_launch_lineage(
    api_client,
    db_session,
    monkeypatch,
) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="publish-manual",
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
    validate_delivery = api_client.post(f"/campaigns/{campaign_id}/delivery/validate")
    assert validate_delivery.status_code == 200, validate_delivery.text

    brief_id = "brief-publish-manual"
    brief_artifact = Artifact(
        org_id=TEST_ORG_ID,
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
                    "experimentId": "exp-manual-1",
                    "requirements": [{"channel": "facebook", "format": "image_ad"}],
                }
            ]
        },
    )
    db_session.add(brief_artifact)
    db_session.commit()

    asset = _create_asset(
        db_session,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        batch_id="latest-run",
        suffix="publish-manual",
        asset_brief_id=brief_id,
    )
    creative_spec = MetaCreativeSpec(
        org_id=TEST_ORG_ID,
        asset_id=asset.id,
        campaign_id=campaign_id,
        name="Manual Publish Creative",
        primary_text="Primary text",
        headline="Headline",
        description="Description",
        call_to_action_type="LEARN_MORE",
        destination_url="https://lp.example.com/manual-pre-sale",
        page_id="page_123",
        instagram_actor_id=None,
        status="draft",
        metadata_json={
            "experimentSpecId": "exp-manual-1",
            "destinationSource": "campaign_delivery_config",
            "resolvedDestinationUrl": "https://lp.example.com/manual-pre-sale",
        },
    )
    adset_spec = MetaAdSetSpec(
        org_id=TEST_ORG_ID,
        campaign_id=campaign_id,
        name="Manual Launch Ad Set",
        status="draft",
        optimization_goal="OFFSITE_CONVERSIONS",
        billing_event="IMPRESSIONS",
        targeting={"geo_locations": {"countries": ["US"]}},
        placements={"publisher_platforms": ["facebook"]},
        daily_budget=5000,
        lifetime_budget=None,
        bid_amount=None,
        start_time=None,
        end_time=None,
        promoted_object={"pixel_id": "pixel_123", "custom_event_type": "PURCHASE"},
        conversion_domain="lp.example.com",
        metadata_json={"experimentSpecId": "exp-manual-1"},
    )
    db_session.add(creative_spec)
    db_session.add(adset_spec)
    db_session.commit()

    _upsert_meta_profile(api_client, client_id=client_id)

    response = api_client.post(
        f"/meta/campaigns/{campaign_id}/publish-plan/validate",
        json={
            "generationKey": "batch:latest-run",
            "publishBaseUrl": "https://shop.thehonestherbalist.com",
            "campaignName": "Manual External Launch",
            "campaignObjective": "OUTCOME_SALES",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["includedCount"] == 1
    assert payload["items"][0]["resolvedDestinationUrl"] == "https://lp.example.com/manual-pre-sale"


def test_meta_management_apply_mode_persists_artifacts(api_client, db_session, monkeypatch) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="management-apply",
        db_session=db_session,
    )
    _ = product_id
    _seed_meta_workspace_config(db_session, client_id=client_id)
    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None

    local_meta_campaign = MetaCampaign(
        org_id=TEST_ORG_ID,
        campaign_id=campaign.id,
        ad_account_id="act_123456",
        request_id="meta-launch-plan:test:campaign",
        meta_campaign_id="meta_campaign_apply_123",
        name="Managed Campaign",
        objective="OUTCOME_SALES",
        status="ACTIVE",
        metadata_json={},
    )
    db_session.add(local_meta_campaign)
    db_session.commit()

    class _FakeManagementClient:
        def get_object(self, *, object_id: str, fields: str):
            _ = fields
            if object_id == "meta_campaign_apply_123":
                return {"id": object_id, "status": "ACTIVE", "daily_budget": "10000"}
            return {"id": object_id, "status": "ACTIVE", "effective_status": "ACTIVE"}

        def update_ad(self, *, ad_id: str, payload: dict[str, object]):
            return {"id": ad_id, "status": payload["status"]}

    monkeypatch.setattr(
        "app.routers.meta_ads._get_meta_client",
        lambda **_kwargs: _FakeManagementClient(),
    )
    monkeypatch.setattr(
        "app.services.meta_media_buying.fetch_meta_campaign_snapshot",
        lambda **_kwargs: (
            {"id": "meta_campaign_apply_123", "name": "Managed Campaign", "status": "ACTIVE"},
            [{"id": "meta_adset_123", "name": "Managed Ad Set", "status": "ACTIVE"}],
        ),
    )
    monkeypatch.setattr(
        "app.services.meta_media_buying.fetch_ad_level_insights",
        lambda **_kwargs: [
            {
                "ad_id": "meta_ad_123",
                "ad_name": "Ad One",
                "adset_id": "meta_adset_123",
                "campaign_id": "meta_campaign_apply_123",
                "impressions": "1000",
                "spend": "65.00",
                "cpm": "65.00",
                "inline_link_clicks": "2",
                "inline_link_click_ctr": "0.2",
                "cost_per_inline_link_click": "32.50",
                "actions": [],
                "action_values": [],
            }
        ],
    )

    response = api_client.post(
        "/meta/management/plan",
        json={
            "metaCampaignId": "meta_campaign_apply_123",
            "clientId": client_id,
            "mode": "apply",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["mode"] == "apply"
    assert payload["actions"][0]["kind"] == "pause_ad"
    assert payload["appliedActions"][0]["status"] == "applied"
    assert payload["artifacts"]["metricsSnapshotArtifactId"]
    assert payload["artifacts"]["recommendedActionsArtifactId"]
    assert payload["artifacts"]["approvalDecisionArtifactId"]


def test_meta_management_plan_evaluates_benchmarks_and_persists_snapshot(api_client, db_session, monkeypatch) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="management-benchmarks",
        db_session=db_session,
    )
    _seed_meta_workspace_config(db_session, client_id=client_id)
    _upsert_meta_profile(
        api_client,
        client_id=client_id,
        metadata=_meta_management_benchmark_metadata(),
    )
    funnel_data = _seed_management_funnel(
        db_session,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        price_cents=10000,
    )
    _seed_management_funnel_events(
        db_session,
        funnel=funnel_data["funnel"],
        publication=funnel_data["publication"],
        presell_page=funnel_data["presellPage"],
        sales_page=funnel_data["salesPage"],
    )

    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None
    local_meta_campaign = MetaCampaign(
        org_id=TEST_ORG_ID,
        campaign_id=campaign.id,
        ad_account_id="act_123456",
        request_id="meta-launch-plan:test:benchmark-campaign",
        meta_campaign_id="meta_campaign_benchmark_123",
        name="Benchmark Campaign",
        objective="OUTCOME_SALES",
        status="ACTIVE",
        metadata_json={},
    )
    db_session.add(local_meta_campaign)
    db_session.commit()

    class _FakeManagementClient:
        pass

    monkeypatch.setattr(
        "app.routers.meta_ads._get_meta_client",
        lambda **_kwargs: _FakeManagementClient(),
    )
    monkeypatch.setattr(
        "app.services.meta_media_buying.fetch_meta_campaign_snapshot",
        lambda **_kwargs: (
            {"id": "meta_campaign_benchmark_123", "name": "Benchmark Campaign", "status": "ACTIVE"},
            [{"id": "meta_adset_123", "name": "Managed Ad Set", "status": "ACTIVE"}],
        ),
    )
    monkeypatch.setattr(
        "app.services.meta_media_buying.fetch_ad_level_insights",
        lambda **_kwargs: [
            {
                "ad_id": "meta_ad_123",
                "ad_name": "Ad One",
                "adset_id": "meta_adset_123",
                "campaign_id": "meta_campaign_benchmark_123",
                "impressions": "1000",
                "spend": "65.00",
                "cpm": "65.00",
                "inline_link_clicks": "30",
                "inline_link_click_ctr": "3.0",
                "cost_per_inline_link_click": "2.17",
                "actions": [],
                "action_values": [],
            }
        ],
    )

    response = api_client.post(
        "/meta/management/plan",
        json={
            "metaCampaignId": "meta_campaign_benchmark_123",
            "clientId": client_id,
            "evaluateBenchmarks": True,
            "datePreset": "last_3d",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["benchmarkContext"]["funnelId"] == str(funnel_data["funnel"].id)
    assert payload["benchmarkContext"]["atcPriceBandId"] == "core_97_126"
    assert payload["funnelSnapshot"]["presellPageViewSessions"] == 10
    assert payload["funnelSnapshot"]["presellCtaClickSessions"] == 3
    assert payload["funnelSnapshot"]["salesPageViewSessions"] == 10
    assert payload["funnelSnapshot"]["checkoutStartedSessions"] == 1
    assert payload["funnelSnapshot"]["orderCompletedSessions"] == 1

    evaluations = {entry["metricId"]: entry for entry in payload["benchmarkEvaluations"]}
    assert evaluations["ad_link_ctr_pct"]["status"] == "good"
    assert evaluations["presell_ctr_pct"]["status"] == "on_target"
    assert evaluations["sales_pdp_atc_pct"]["status"] == "on_target"
    assert evaluations["sales_pdp_purchase_cvr_pct"]["status"] == "good"
    assert evaluations["checkout_cvr_pct"]["status"] == "on_target"
    assert payload["artifacts"]["metricsSnapshotArtifactId"]

    metrics_artifact = db_session.scalars(
        select(Artifact).where(Artifact.id == payload["artifacts"]["metricsSnapshotArtifactId"])
    ).first()
    assert metrics_artifact is not None
    assert metrics_artifact.data["benchmarkContext"]["funnelId"] == str(funnel_data["funnel"].id)
    assert metrics_artifact.data["funnelSnapshot"]["checkoutStartedSessions"] == 1
    assert len(metrics_artifact.data["benchmarkEvaluations"]) == 5


def test_meta_management_plan_errors_when_benchmark_profile_is_missing(api_client, db_session, monkeypatch) -> None:
    client_id, product_id, campaign_id = _create_campaign_with_product(
        api_client,
        suffix="management-benchmarks-missing-profile",
        db_session=db_session,
    )
    _ = product_id
    _seed_meta_workspace_config(db_session, client_id=client_id)
    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None

    local_meta_campaign = MetaCampaign(
        org_id=TEST_ORG_ID,
        campaign_id=campaign.id,
        ad_account_id="act_123456",
        request_id="meta-launch-plan:test:benchmark-missing-profile",
        meta_campaign_id="meta_campaign_missing_profile_123",
        name="Benchmark Campaign",
        objective="OUTCOME_SALES",
        status="ACTIVE",
        metadata_json={},
    )
    db_session.add(local_meta_campaign)
    db_session.commit()

    class _FakeManagementClient:
        pass

    monkeypatch.setattr(
        "app.routers.meta_ads._get_meta_client",
        lambda **_kwargs: _FakeManagementClient(),
    )
    monkeypatch.setattr(
        "app.services.meta_media_buying.fetch_meta_campaign_snapshot",
        lambda **_kwargs: (
            {"id": "meta_campaign_missing_profile_123", "name": "Benchmark Campaign", "status": "ACTIVE"},
            [],
        ),
    )
    monkeypatch.setattr(
        "app.services.meta_media_buying.fetch_ad_level_insights",
        lambda **_kwargs: [],
    )

    response = api_client.post(
        "/meta/management/plan",
        json={
            "metaCampaignId": "meta_campaign_missing_profile_123",
            "clientId": client_id,
            "evaluateBenchmarks": True,
        },
    )

    assert response.status_code == 409, response.text
    assert "Meta paid ads profile is required" in response.json()["detail"]
