import pytest
from fastapi import HTTPException, status

from app.routers.clients import _normalize_theme_template_slot_path_filter


def test_normalize_theme_template_slot_path_filter_accepts_none() -> None:
    assert _normalize_theme_template_slot_path_filter(None) == []


def test_normalize_theme_template_slot_path_filter_trims_and_preserves_order() -> None:
    assert _normalize_theme_template_slot_path_filter(
        [
            " templates/index.json.sections.hero.settings.image ",
            "templates/index.json.sections.gallery.settings.image",
        ]
    ) == [
        "templates/index.json.sections.hero.settings.image",
        "templates/index.json.sections.gallery.settings.image",
    ]


@pytest.mark.parametrize(
    "raw_slot_paths, expected_fragment",
    [
        ("not-a-list", "slotPaths must be an array"),
        ([""], "must be a non-empty string"),
        (["path.one", "path.one"], "contains a duplicate path"),
    ],
)
def test_normalize_theme_template_slot_path_filter_rejects_invalid_values(
    raw_slot_paths: object,
    expected_fragment: str,
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        _normalize_theme_template_slot_path_filter(raw_slot_paths)

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert expected_fragment in str(exc_info.value.detail)
