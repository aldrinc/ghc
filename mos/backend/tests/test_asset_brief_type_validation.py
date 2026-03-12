from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.asset_brief_types import normalize_required_asset_brief_types
from app.schemas.common import CampaignCreate
from app.schemas.intent import CampaignIntentRequest
from app.schemas.workflow_launches import StrategyV2LaunchAngleCampaignRequest


def test_normalize_required_asset_brief_types_accepts_supported_values() -> None:
    assert normalize_required_asset_brief_types([" image ", "video", "image"], field_name="assetBriefTypes") == [
        "image",
        "video",
    ]


def test_normalize_required_asset_brief_types_rejects_unsupported_values() -> None:
    with pytest.raises(ValueError, match="Supported values: image, video."):
        normalize_required_asset_brief_types(["static-image"], field_name="assetBriefTypes")


def test_campaign_create_rejects_unsupported_asset_brief_types() -> None:
    with pytest.raises(ValidationError, match="Supported values: image, video."):
        CampaignCreate(
            client_id="client-1",
            product_id="product-1",
            name="Campaign",
            channels=["facebook"],
            asset_brief_types=["static-image"],
        )


def test_campaign_intent_request_rejects_unsupported_asset_brief_types() -> None:
    with pytest.raises(ValidationError, match="Supported values: image, video."):
        CampaignIntentRequest(
            campaignName="Campaign",
            productId="product-1",
            channels=["facebook"],
            assetBriefTypes=["static-image"],
        )


def test_strategy_v2_launch_request_rejects_unsupported_asset_brief_types() -> None:
    with pytest.raises(ValidationError, match="Supported values: image, video."):
        StrategyV2LaunchAngleCampaignRequest(
            channels=["meta"],
            assetBriefTypes=["static-image"],
            experimentVariantPolicy="angle_launch_standard_v1",
        )
