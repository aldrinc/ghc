import pytest
from pydantic import ValidationError

from app.schemas.campaign_funnels import CampaignFunnelGenerationRequest


def test_campaign_funnel_generation_request_defaults_async_media_enrichment_true() -> None:
    payload = CampaignFunnelGenerationRequest.model_validate({"experimentIds": ["exp_001"]})

    assert payload.async_media_enrichment is True
    dumped = payload.model_dump(by_alias=True)
    assert dumped["asyncMediaEnrichment"] is True


def test_campaign_funnel_generation_request_parses_async_media_enrichment_false() -> None:
    payload = CampaignFunnelGenerationRequest.model_validate(
        {
            "experimentIds": ["exp_001"],
            "asyncMediaEnrichment": False,
        }
    )

    assert payload.async_media_enrichment is False


def test_campaign_funnel_generation_request_accepts_custom_pages() -> None:
    payload = CampaignFunnelGenerationRequest.model_validate(
        {
            "experimentIds": ["exp_001"],
            "pages": [
                {
                    "templateId": "presales",
                    "name": "Presell A",
                    "slug": "presell-a",
                    "nextPageSlug": "sales-a",
                },
                {
                    "templateId": "sales-pdp",
                    "name": "Sales A",
                    "slug": "sales-a",
                },
            ],
        }
    )

    assert payload.pages is not None
    assert payload.pages[0].template_id == "presales"
    assert payload.pages[0].next_page_slug == "sales-a"
    assert payload.model_dump(by_alias=True)["pages"][0]["nextPageSlug"] == "sales-a"


def test_campaign_funnel_generation_request_rejects_missing_next_page_slug() -> None:
    with pytest.raises(ValidationError, match="nextPageSlug values that do not match"):
        CampaignFunnelGenerationRequest.model_validate(
            {
                "experimentIds": ["exp_001"],
                "pages": [
                    {
                        "templateId": "presales",
                        "name": "Presell A",
                        "slug": "presell-a",
                        "nextPageSlug": "missing-sales",
                    }
                ],
            }
        )
