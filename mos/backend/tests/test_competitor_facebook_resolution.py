from app.temporal.activities.competitor_facebook_activities import (
    _extract_facebook_page_candidates,
    _normalize_extracted_url,
    _score_candidate_for_brand,
)


def test_extract_candidates_filters_to_page_roots() -> None:
    html = """
    <a href="https://www.facebook.com/FOREO/">Facebook</a>
    <a href="https://www.facebook.com/FOREO/videos/576387576399178/">Video</a>
    <a href="https://www.facebook.com/sharer/sharer.php?u=https://example.com">Share</a>
    """
    candidates = _extract_facebook_page_candidates(html)
    assert "https://www.facebook.com/FOREO" in candidates
    assert all("/videos/" not in c.lower() for c in candidates)
    assert all("/sharer/" not in c.lower() for c in candidates)


def test_normalize_extracted_url_unescapes_slashes() -> None:
    assert (
        _normalize_extracted_url("https:\\/\\/www.facebook.com\\/OmniluxLED\\/")
        == "https://www.facebook.com/OmniluxLED/"
    )


def test_scoring_prefers_slug_matching_brand_tokens() -> None:
    shark = "https://www.facebook.com/SharkNinja"
    ninja_kitchen = "https://www.facebook.com/ninjakitchen"
    assert _score_candidate_for_brand(shark, "SharkNinja (CryoGlow)") > _score_candidate_for_brand(
        ninja_kitchen, "SharkNinja (CryoGlow)"
    )

