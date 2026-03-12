from types import SimpleNamespace

from app.temporal.activities.asset_activities import (
    _DefaultSwipeSource,
    _build_creative_generation_batch_id,
    _build_creative_generation_plan_items,
    _existing_creative_generation_assets_by_plan_item,
    _extract_source_filename,
    _extract_requirement_swipe_source,
    _extract_requirement_swipe_requires_product_image,
    _extract_remote_reference_asset_id,
    _extract_swipe_requires_product_image_from_tags,
    _normalize_requirement_format,
    _split_requirement_asset_counts,
    _summarize_exception_message,
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


def test_extract_source_filename_decodes_percent_encoded_swipe_labels() -> None:
    assert _extract_source_filename("http://127.0.0.1:8099/Static%20%231.png") == "Static #1.png"


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


def test_build_creative_generation_plan_items_expands_all_default_swipes_deterministically() -> None:
    requirements = [
        {
            "channel": "facebook",
            "format": "image_ad",
            "funnelStage": "top-of-funnel",
            "angle": "Structured triage",
            "hook": "A better way to screen interactions",
        },
        {
            "channel": "facebook",
            "format": "video_ad",
            "funnelStage": "top-of-funnel",
        },
        {
            "channel": "facebook",
            "format": "image_ad",
            "funnelStage": "middle-of-funnel",
            "angle": "Workflow clarity",
            "hook": "Stop guessing",
        },
    ]
    default_swipes = [
        _DefaultSwipeSource(
            company_swipe_id="swipe-a",
            source_label="10.png",
            source_media_url="https://example.com/10.png",
            product_image_policy=False,
        ),
        _DefaultSwipeSource(
            company_swipe_id="swipe-b",
            source_label="11.png",
            source_media_url="https://example.com/11.png",
            product_image_policy=True,
        ),
    ]

    first = _build_creative_generation_plan_items(
        asset_brief_id="brief-123",
        batch_id="batch-1",
        requirements=requirements,
        default_swipes=default_swipes,
        copy_pack_ids_by_requirement={0: "copy-0", 2: "copy-2"},
    )
    second = _build_creative_generation_plan_items(
        asset_brief_id="brief-123",
        batch_id="batch-1",
        requirements=requirements,
        default_swipes=default_swipes,
        copy_pack_ids_by_requirement={0: "copy-0", 2: "copy-2"},
    )

    assert [item.id for item in first] == [item.id for item in second]
    assert len(first) == 4
    assert [item.requirement_index for item in first] == [0, 0, 2, 2]
    assert [item.source_label for item in first] == ["10.png", "11.png", "10.png", "11.png"]
    assert [item.copy_pack_id for item in first] == ["copy-0", "copy-0", "copy-2", "copy-2"]


def test_build_creative_generation_plan_items_errors_when_image_requirement_has_no_copy_pack() -> None:
    try:
        _build_creative_generation_plan_items(
            asset_brief_id="brief-123",
            batch_id="batch-1",
            requirements=[{"channel": "facebook", "format": "image_ad"}],
            default_swipes=[],
            copy_pack_ids_by_requirement={},
        )
    except ValueError as exc:
        assert "missing_requirement_index=0" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError when an image requirement has no copy pack id.")


def test_build_creative_generation_batch_id_is_stable_for_one_execution() -> None:
    first = _build_creative_generation_batch_id(
        execution_key="workflow-run-1",
        asset_brief_id="brief-123",
    )
    second = _build_creative_generation_batch_id(
        execution_key="workflow-run-1",
        asset_brief_id="brief-123",
    )
    different = _build_creative_generation_batch_id(
        execution_key="workflow-run-2",
        asset_brief_id="brief-123",
    )

    assert first == second
    assert first != different


def test_existing_creative_generation_assets_by_plan_item_filters_by_batch_and_brief() -> None:
    assets = [
        SimpleNamespace(
            id="asset-1",
            ai_metadata={
                "creativeGenerationBatchId": "batch-1",
                "creativeGenerationPlanItemId": "plan-item-1",
                "assetBriefId": "brief-1",
            },
            content={},
        ),
        SimpleNamespace(
            id="asset-2",
            ai_metadata={
                "creativeGenerationBatchId": "batch-2",
                "creativeGenerationPlanItemId": "plan-item-2",
                "assetBriefId": "brief-1",
            },
            content={},
        ),
        SimpleNamespace(
            id="asset-3",
            ai_metadata={
                "creativeGenerationBatchId": "batch-1",
                "creativeGenerationPlanItemId": "plan-item-3",
                "assetBriefId": "brief-2",
            },
            content={},
        ),
    ]

    result = _existing_creative_generation_assets_by_plan_item(
        assets=assets,
        batch_id="batch-1",
        asset_brief_id="brief-1",
    )

    assert result == {"plan-item-1": "asset-1"}


def test_existing_creative_generation_assets_by_plan_item_errors_on_duplicates() -> None:
    assets = [
        SimpleNamespace(
            id="asset-1",
            ai_metadata={
                "creativeGenerationBatchId": "batch-1",
                "creativeGenerationPlanItemId": "plan-item-1",
                "assetBriefId": "brief-1",
            },
            content={},
        ),
        SimpleNamespace(
            id="asset-2",
            ai_metadata={
                "creativeGenerationBatchId": "batch-1",
                "creativeGenerationPlanItemId": "plan-item-1",
                "assetBriefId": "brief-1",
            },
            content={},
        ),
    ]

    try:
        _existing_creative_generation_assets_by_plan_item(
            assets=assets,
            batch_id="batch-1",
            asset_brief_id="brief-1",
        )
    except RuntimeError as exc:
        assert "Multiple generated assets found for the same creative generation plan item" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected RuntimeError for duplicate plan item assets")


def test_summarize_exception_message_compacts_and_truncates() -> None:
    summary = _summarize_exception_message(
        RuntimeError("line one\nline two " + ("x" * 500)),
        max_chars=80,
    )

    assert summary.startswith("RuntimeError: line one line two")
    assert len(summary) <= 80
    assert summary.endswith("...")
