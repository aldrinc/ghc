from app.services.shopify_theme_content_planner import _parse_and_validate_planner_output


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
