from app.temporal.activities.asset_activities import (
    _extract_requirement_swipe_source,
    _extract_requirement_swipe_requires_product_image,
    _extract_remote_reference_asset_id,
    _extract_swipe_requires_product_image_from_tags,
    _normalize_requirement_format,
    _split_requirement_asset_counts,
)


def test_split_requirement_asset_counts_even_distribution() -> None:
    requirements = [{"format": "image"}, {"format": "image"}, {"format": "video"}]
    allocations = _split_requirement_asset_counts(requirements, 6)

    counts = [count for _idx, _req, count in allocations]
    assert counts == [2, 2, 2]


def test_split_requirement_asset_counts_with_remainder() -> None:
    requirements = [{"format": "image"}, {"format": "video"}]
    allocations = _split_requirement_asset_counts(requirements, 6)

    counts = [count for _idx, _req, count in allocations]
    assert counts == [3, 3]


def test_split_requirement_asset_counts_errors_when_requirements_exceed_total() -> None:
    requirements = [{"idx": idx} for idx in range(7)]

    try:
        _split_requirement_asset_counts(requirements, 6)
    except ValueError as exc:
        assert "only 6 assets are allowed per brief" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError for requirements > total assets")


def test_extract_remote_reference_asset_id() -> None:
    assert _extract_remote_reference_asset_id(ai_metadata=None) is None
    assert _extract_remote_reference_asset_id(ai_metadata={"creativeServiceReferenceAssetId": "  "}) is None
    assert (
        _extract_remote_reference_asset_id(ai_metadata={"creativeServiceReferenceAssetId": "abc-123"})
        == "abc-123"
    )


def test_normalize_requirement_format_aliases() -> None:
    assert _normalize_requirement_format("image") == "image"
    assert _normalize_requirement_format("image_ad") == "image"
    assert _normalize_requirement_format("image-ad") == "image"
    assert _normalize_requirement_format("video") == "video"
    assert _normalize_requirement_format("video_ad") == "video"
    assert _normalize_requirement_format("video-ad") == "video"


def test_extract_requirement_swipe_source_prefers_explicit_keys() -> None:
    company_swipe_id, swipe_image_url = _extract_requirement_swipe_source(
        {
            "companySwipeId": " swipe-123 ",
            "swipeImageUrl": None,
        }
    )
    assert company_swipe_id == "swipe-123"
    assert swipe_image_url is None

    company_swipe_id, swipe_image_url = _extract_requirement_swipe_source(
        {
            "company_swipe_id": None,
            "swipe_image_url": " https://example.com/swipe.png ",
        }
    )
    assert company_swipe_id is None
    assert swipe_image_url == "https://example.com/swipe.png"


def test_extract_requirement_swipe_source_rejects_ambiguous_payload() -> None:
    try:
        _extract_requirement_swipe_source(
            {
                "companySwipeId": "swipe-123",
                "swipeImageUrl": "https://example.com/swipe.png",
            }
        )
    except ValueError as exc:
        assert "exactly one swipe source" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError when both company swipe id and swipe image url are provided.")


def test_extract_requirement_swipe_requires_product_image() -> None:
    assert _extract_requirement_swipe_requires_product_image({}) is None
    assert _extract_requirement_swipe_requires_product_image({"swipeRequiresProductImage": True}) is True
    assert _extract_requirement_swipe_requires_product_image({"swipe_requires_product_image": False}) is False

    try:
        _extract_requirement_swipe_requires_product_image({"swipeRequiresProductImage": "true"})
    except ValueError as exc:
        assert "must be a boolean" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError for non-boolean swipeRequiresProductImage")


def test_extract_swipe_requires_product_image_from_tags() -> None:
    assert _extract_swipe_requires_product_image_from_tags([]) is None
    assert _extract_swipe_requires_product_image_from_tags(["swipe:requires_product_image"]) is True
    assert _extract_swipe_requires_product_image_from_tags(["swipe:no_product_image"]) is False

    try:
        _extract_swipe_requires_product_image_from_tags(
            ["swipe:requires_product_image", "swipe:no_product_image"]
        )
    except ValueError as exc:
        assert "conflicting product image policy tags" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError for conflicting swipe product image tags")
