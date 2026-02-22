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
