from app.temporal.activities.asset_activities import (
    _ProductReferenceAsset,
    _build_image_reference_text,
    _extract_remote_reference_asset_id,
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


def test_build_image_reference_text_includes_urls() -> None:
    text = _build_image_reference_text(
        [
            _ProductReferenceAsset(
                local_asset_id="asset-1",
                primary_url="https://example.com/asset-1.png",
                title="Hero Product",
                remote_asset_id="remote-1",
            )
        ]
    )
    assert "Hero Product" in text
    assert "https://example.com/asset-1.png" in text
