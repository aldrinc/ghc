from app.services.shopify_theme_content_planner import (
    _parse_and_validate_planner_output,
    _rebalance_image_assignments,
)


def test_parse_and_validate_planner_output_clips_text_to_slot_max_length():
    over_limit = "x" * 121
    parsed = {
        "imageAssignments": [],
        "textAssignments": [
            {
                "path": "sections/footer-group.json.sections.ss_footer_4_9rJacA.settings.second_text",
                "value": over_limit,
            }
        ],
    }

    result = _parse_and_validate_planner_output(
        parsed=parsed,
        image_slots=[],
        text_slots=[
            {
                "path": "sections/footer-group.json.sections.ss_footer_4_9rJacA.settings.second_text",
                "maxLength": 120,
            }
        ],
        asset_public_ids=set(),
    )

    assert (
        result["componentTextValues"][
            "sections/footer-group.json.sections.ss_footer_4_9rJacA.settings.second_text"
        ]
        == "x" * 120
    )


def test_rebalance_image_assignments_distributes_assets_across_slots():
    image_slots = [
        {
            "path": "templates/index.json.sections.hero.settings.image",
            "role": "hero",
            "recommendedAspect": "landscape",
        },
        {
            "path": "templates/index.json.sections.gallery.settings.image",
            "role": "gallery",
            "recommendedAspect": "square",
        },
        {
            "path": "templates/index.json.sections.benefits.blocks.item-1.settings.image",
            "role": "supporting",
            "recommendedAspect": "portrait",
        },
    ]
    image_assets = [
        {"publicId": "asset-landscape", "orientation": "landscape"},
        {"publicId": "asset-square", "orientation": "square"},
        {"publicId": "asset-portrait", "orientation": "portrait"},
    ]
    repeated_assignment = {slot["path"]: "asset-landscape" for slot in image_slots}

    rebalanced = _rebalance_image_assignments(
        component_image_asset_map=repeated_assignment,
        image_slots=image_slots,
        image_assets=image_assets,
    )

    assert len(set(rebalanced.values())) == 3
    assert rebalanced["templates/index.json.sections.hero.settings.image"] == "asset-landscape"


def test_rebalance_image_assignments_keeps_single_asset_mapping_when_only_one_asset_exists():
    image_slots = [
        {
            "path": "templates/index.json.sections.hero.settings.image",
            "role": "hero",
            "recommendedAspect": "landscape",
        },
        {
            "path": "templates/index.json.sections.gallery.settings.image",
            "role": "gallery",
            "recommendedAspect": "square",
        },
    ]
    image_assets = [{"publicId": "asset-only", "orientation": "landscape"}]
    repeated_assignment = {slot["path"]: "asset-only" for slot in image_slots}

    rebalanced = _rebalance_image_assignments(
        component_image_asset_map=repeated_assignment,
        image_slots=image_slots,
        image_assets=image_assets,
    )

    assert rebalanced == repeated_assignment
