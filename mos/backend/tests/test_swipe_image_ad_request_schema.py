from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.swipe_image_ads import SwipeImageAdGenerateRequest


def _base_payload() -> dict[str, object]:
    return {
        "clientId": "00000000-0000-0000-0000-000000000011",
        "productId": "00000000-0000-0000-0000-000000000022",
        "campaignId": "00000000-0000-0000-0000-000000000033",
        "assetBriefId": "asset-brief-1",
        "requirementIndex": 0,
        "companySwipeId": "swipe-1",
        "count": 1,
        "aspectRatio": "1:1",
    }


def test_swipe_request_rejects_image_model_for_stage_one() -> None:
    payload = _base_payload()
    payload["model"] = "gemini-3-pro-image-preview"

    with pytest.raises(ValidationError) as exc:
        SwipeImageAdGenerateRequest.model_validate(payload)

    assert "Use renderModelId for final image rendering models" in str(exc.value)


def test_swipe_request_accepts_render_model_id_override() -> None:
    payload = _base_payload()
    payload["model"] = "gemini-2.5-flash"
    payload["renderModelId"] = "gemini-3-pro-image-preview"

    parsed = SwipeImageAdGenerateRequest.model_validate(payload)
    assert parsed.model == "gemini-2.5-flash"
    assert parsed.render_model_id == "gemini-3-pro-image-preview"
