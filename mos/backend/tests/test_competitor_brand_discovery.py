from app.temporal.activities.competitor_brand_discovery_activities import (
    build_competitor_brand_discovery_activity,
)


def test_brand_discovery_does_not_fail_when_all_missing_facebook() -> None:
    result = build_competitor_brand_discovery_activity(
        {
            "competitors": [
                {"name": "Brand A", "website": "https://example.com", "facebook_page_url": None},
                {"name": "Brand B", "website": "https://example.org", "facebook_page_url": None},
            ]
        }
    )

    assert result["brand_discovery"] is not None
    assert result["facebook_urls"] == []
    assert len(result["brand_discovery"]["brands"]) == 2

