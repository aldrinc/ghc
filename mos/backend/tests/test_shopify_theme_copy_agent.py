import pytest

from app.services.shopify_theme_copy_agent import (
    _copy_output_schema,
    _parse_and_validate_copy_output,
)


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


def test_copy_output_schema_restricts_assignment_paths_to_known_slots():
    slot_paths = [
        "templates/index.json.sections.hero.settings.heading",
        "templates/index.json.sections.hero.settings.subheading",
    ]

    schema = _copy_output_schema(text_slot_paths=slot_paths)

    assert (
        schema["properties"]["textAssignments"]["items"]["properties"]["path"]["enum"]
        == slot_paths
    )
    assert schema["properties"]["textAssignments"]["minItems"] == len(slot_paths)
    assert schema["properties"]["textAssignments"]["maxItems"] == len(slot_paths)
