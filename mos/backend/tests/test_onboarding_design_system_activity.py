from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from uuid import UUID

from sqlalchemy import select

from app.db.enums import AssetSourceEnum
from app.db.models import Asset, Client, DesignSystem, OnboardingPayload, Product
from app.services.design_system_generation import load_base_tokens_template
from app.temporal.activities import client_onboarding_activities as coa


TEST_ORG_ID = UUID("00000000-0000-0000-0000-000000000001")


def test_build_design_system_activity_creates_new_ds_each_run_and_sets_logo(monkeypatch, db_session):
    client = Client(org_id=TEST_ORG_ID, name="Onboard Brand", industry="DTC skincare")
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)

    product = Product(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        name="Glow Serum",
        description="A vitamin C serum for brighter skin.",
        category="Skincare",
        primary_benefits=["Brighter skin", "Even tone"],
        feature_bullets=["15% vitamin C", "Fragrance-free"],
        disclaimers=["For external use only."],
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    payload = OnboardingPayload(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        product_id=product.id,
        data={
            "brand_story": "We make science-backed skincare for busy people.",
            "goals": ["Increase conversions", "Build trust"],
            "competitor_urls": ["https://example.com/competitor-a", "https://example.com/competitor-b"],
            "funnel_notes": "Lean into clinical proof and before/after credibility.",
        },
    )
    db_session.add(payload)
    db_session.commit()
    db_session.refresh(payload)

    @contextmanager
    def _session_scope_override():
        yield db_session

    monkeypatch.setattr(coa, "session_scope", _session_scope_override)

    seen_ctx = []

    def _fake_generate_design_system_tokens(*, ctx, model=None, max_output_tokens=9000):
        seen_ctx.append(ctx)
        return deepcopy(load_base_tokens_template())

    monkeypatch.setattr(coa, "generate_design_system_tokens", _fake_generate_design_system_tokens)

    image_asset_calls: list[str] = []

    def _fake_create_funnel_image_asset(
        *,
        session,
        org_id: str,
        client_id: str,
        prompt: str,
        aspect_ratio=None,
        usage_context=None,
        reference_image_bytes=None,
        reference_image_mime_type=None,
        reference_asset_public_id=None,
        reference_asset_id=None,
        funnel_id=None,
        product_id=None,
        tags=None,
    ):
        image_asset_calls.append(prompt)
        asset = Asset(
            org_id=org_id,
            client_id=client_id,
            source_type=AssetSourceEnum.ai,
            channel_id="funnel",
            format="image",
            product_id=product_id,
            content={"prompt": prompt, "aspectRatio": aspect_ratio, "usageContext": usage_context or {}},
            tags=tags or [],
        )
        session.add(asset)
        session.flush()  # ensure public_id is available for the activity
        return asset

    monkeypatch.setattr(coa, "create_funnel_image_asset", _fake_create_funnel_image_asset)

    params = {
        "org_id": str(TEST_ORG_ID),
        "client_id": str(client.id),
        "product_id": str(product.id),
        "onboarding_payload_id": str(payload.id),
        "precanon_research": {"step_summaries": {"04": "Deep research notes."}},
        "canon": {"brand": {"story": "Canonical brand story from research."}},
    }

    first = coa.build_design_system_activity(params)
    assert isinstance(first.get("design_system_id"), str) and first["design_system_id"]
    assert first.get("client_id") == str(client.id)
    assert isinstance(first.get("logoAssetPublicId"), str) and first["logoAssetPublicId"]
    assert len(image_asset_calls) == 1

    client_after_first = db_session.scalars(
        select(Client).where(Client.org_id == str(TEST_ORG_ID), Client.id == str(client.id))
    ).first()
    assert client_after_first is not None
    assert str(client_after_first.design_system_id) == first["design_system_id"]

    first_ds = db_session.scalars(
        select(DesignSystem).where(DesignSystem.org_id == str(TEST_ORG_ID), DesignSystem.id == first["design_system_id"])
    ).first()
    assert first_ds is not None
    assert first_ds.tokens["brand"]["name"] == client.name
    assert first_ds.tokens["brand"]["logoAssetPublicId"] == first["logoAssetPublicId"]
    assert first_ds.tokens["brand"]["logoAlt"] == client.name

    second = coa.build_design_system_activity(params)
    assert isinstance(second.get("design_system_id"), str) and second["design_system_id"]
    assert second["design_system_id"] != first["design_system_id"]
    assert len(image_asset_calls) == 1  # reuse existing logo

    client_after_second = db_session.scalars(
        select(Client).where(Client.org_id == str(TEST_ORG_ID), Client.id == str(client.id))
    ).first()
    assert client_after_second is not None
    assert str(client_after_second.design_system_id) == second["design_system_id"]

    ds_count = db_session.scalars(
        select(DesignSystem.id).where(DesignSystem.org_id == str(TEST_ORG_ID), DesignSystem.client_id == str(client.id))
    ).all()
    assert len(ds_count) == 2

    assert len(seen_ctx) == 2
    assert seen_ctx[0].client_name == client.name
    assert seen_ctx[0].client_industry == client.industry
    assert seen_ctx[0].product_name == product.name
    assert seen_ctx[0].competitor_urls == payload.data["competitor_urls"]
    assert seen_ctx[0].precanon_step_summaries == {"04": "Deep research notes."}

