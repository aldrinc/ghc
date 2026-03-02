import pytest

from app.services.shopify_theme_copy_agent import _parse_and_validate_copy_output


def test_parse_and_validate_copy_output_clips_text_to_slot_max_length():
    path = "templates/index.json.sections.hero.settings.heading"
    parsed = {
        "textAssignments": [
            {
                "path": path,
                "value": "x" * 121,
            }
        ]
    }
    text_slots = [
        {
            "path": path,
            "maxLength": 120,
        }
    ]

    result = _parse_and_validate_copy_output(parsed=parsed, text_slots=text_slots)

    assert result[path] == "x" * 120


def test_parse_and_validate_copy_output_requires_all_slot_assignments():
    path = "templates/index.json.sections.hero.settings.heading"
    parsed = {"textAssignments": []}
    text_slots = [{"path": path, "maxLength": 120}]

    with pytest.raises(ValueError, match="did not assign all text slots"):
        _parse_and_validate_copy_output(parsed=parsed, text_slots=text_slots)
