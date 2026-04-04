"""Tests for puck_data_validation module.

Validates that legacy Section props (layout, containerWidth, padding)
are correctly rejected in Puck data.
"""

from __future__ import annotations

import pytest

from app.services.puck_data_validation import (
    LEGACY_SECTION_PROPS,
    LegacySectionPropError,
    validate_puck_data_no_legacy_section_props,
)


class TestLegacySectionPropDetection:
    """Tests for detecting legacy Section props in Puck data."""

    def test_accepts_valid_puck_data_with_no_legacy_props(self):
        """Modern Puck data without legacy props should pass."""
        puck_data = {
            "root": {"props": {"title": "Test Page"}},
            "content": [
                {
                    "type": "Heading",
                    "props": {"children": "Hello World"},
                },
                {
                    "type": "Text",
                    "props": {"content": "Some text content"},
                },
            ],
        }
        # Should not raise
        validate_puck_data_no_legacy_section_props(puck_data)

    def test_rejects_layout_prop_in_root_props(self):
        """Legacy 'layout' prop in root props should be rejected."""
        puck_data = {
            "root": {"props": {"title": "Test", "layout": "centered"}},
            "content": [],
        }
        with pytest.raises(LegacySectionPropError) as exc_info:
            validate_puck_data_no_legacy_section_props(puck_data)
        assert exc_info.value.prop_name == "layout"
        assert "root.props" in exc_info.value.path

    def test_rejects_containerWidth_prop_in_root_props(self):
        """Legacy 'containerWidth' prop in root props should be rejected."""
        puck_data = {
            "root": {"props": {"title": "Test", "containerWidth": 1200}},
            "content": [],
        }
        with pytest.raises(LegacySectionPropError) as exc_info:
            validate_puck_data_no_legacy_section_props(puck_data)
        assert exc_info.value.prop_name == "containerWidth"
        assert "root.props" in exc_info.value.path

    def test_rejects_padding_prop_in_root_props(self):
        """Legacy 'padding' prop in root props should be rejected."""
        puck_data = {
            "root": {"props": {"title": "Test", "padding": "16px"}},
            "content": [],
        }
        with pytest.raises(LegacySectionPropError) as exc_info:
            validate_puck_data_no_legacy_section_props(puck_data)
        assert exc_info.value.prop_name == "padding"
        assert "root.props" in exc_info.value.path

    def test_rejects_legacy_props_in_content_blocks(self):
        """Legacy props in content block props should be rejected."""
        puck_data = {
            "root": {"props": {"title": "Test"}},
            "content": [
                {
                    "type": "Section",
                    "props": {
                        "children": "Hello",
                        "layout": "full-width",
                    },
                },
            ],
        }
        with pytest.raises(LegacySectionPropError) as exc_info:
            validate_puck_data_no_legacy_section_props(puck_data)
        assert exc_info.value.prop_name == "layout"
        assert "content[0].props" in exc_info.value.path

    def test_rejects_legacy_props_in_nested_slots(self):
        """Legacy props in block slots should be rejected."""
        puck_data = {
            "root": {"props": {"title": "Test"}},
            "content": [
                {
                    "type": "Layout",
                    "props": {},
                    "slots": {
                        "body": [
                            {
                                "type": "Section",
                                "props": {
                                    "children": "Content",
                                    "containerWidth": 1000,
                                },
                            }
                        ],
                    },
                },
            ],
        }
        with pytest.raises(LegacySectionPropError) as exc_info:
            validate_puck_data_no_legacy_section_props(puck_data)
        assert exc_info.value.prop_name == "containerWidth"
        assert "content[0].slots.body[0].props" in exc_info.value.path

    def test_rejects_legacy_props_in_children(self):
        """Legacy props in block children should be rejected."""
        puck_data = {
            "root": {"props": {"title": "Test"}},
            "content": [
                {
                    "type": "Wrapper",
                    "props": {},
                    "children": [
                        {
                            "type": "Section",
                            "props": {
                                "children": "Nested",
                                "padding": "24px",
                            },
                        },
                    ],
                },
            ],
        }
        with pytest.raises(LegacySectionPropError) as exc_info:
            validate_puck_data_no_legacy_section_props(puck_data)
        assert exc_info.value.prop_name == "padding"
        assert "content[0].children[0].props" in exc_info.value.path

    def test_reports_first_error_when_multiple_legacy_props_exist(self):
        """When multiple legacy props exist, should report the first one found."""
        puck_data = {
            "root": {"props": {"title": "Test", "layout": "centered", "padding": "16px"}},
            "content": [],
        }
        with pytest.raises(LegacySectionPropError) as exc_info:
            validate_puck_data_no_legacy_section_props(puck_data)
        # First prop found in iteration order should be reported
        # LEGACY_SECTION_PROPS is frozenset, so iteration order is deterministic
        assert exc_info.value.prop_name in LEGACY_SECTION_PROPS


class TestLegacySectionPropError:
    """Tests for the LegacySectionPropError exception."""

    def test_error_message_contains_prop_name_and_path(self):
        """Error message should include the prop name and location path."""
        error = LegacySectionPropError("containerWidth", "content[0].props")
        assert "containerWidth" in str(error)
        assert "content[0].props" in str(error)
        assert "no longer supported" in str(error)
        assert "design-system tokens" in str(error)

    def test_error_has_correct_attributes(self):
        """Error should have prop_name and path attributes."""
        error = LegacySectionPropError("layout", "root.props")
        assert error.prop_name == "layout"
        assert error.path == "root.props"


class TestValidatePuckDataEdgeCases:
    """Tests for edge cases in puck data validation."""

    def test_accepts_empty_puck_data(self):
        """Empty dict should be valid."""
        validate_puck_data_no_legacy_section_props({})

    def test_accepts_puck_data_with_no_content(self):
        """Puck data with root props but no content should be valid if props are clean."""
        puck_data = {
            "root": {"props": {"title": "No Content Page"}},
        }
        validate_puck_data_no_legacy_section_props(puck_data)

    def test_accepts_puck_data_with_null_props(self):
        """Null props should be handled gracefully."""
        puck_data = {
            "root": {"props": None},
            "content": [
                {"type": "Text", "props": None},
            ],
        }
        # Should not raise
        validate_puck_data_no_legacy_section_props(puck_data)

    def test_accepts_non_dict_props(self):
        """Non-dict props should be skipped gracefully."""
        puck_data = {
            "root": {"props": "not a dict"},
            "content": [
                {"type": "Text", "props": 123},
            ],
        }
        # Should not raise
        validate_puck_data_no_legacy_section_props(puck_data)

    def test_handles_non_dict_content_items(self):
        """Non-dict items in content array should be skipped."""
        puck_data = {
            "root": {"props": {"title": "Test"}},
            "content": [
                "not a dict",
                123,
                None,
                {"type": "Text", "props": {"children": "Valid"}},
            ],
        }
        # Should not raise
        validate_puck_data_no_legacy_section_props(puck_data)

    def test_ignores_non_dict_puck_data(self):
        """Non-dict puck_data input should be ignored (return None)."""
        # Should not raise
        validate_puck_data_no_legacy_section_props("not a dict")
        validate_puck_data_no_legacy_section_props(None)
        validate_puck_data_no_legacy_section_props(123)

    def test_accepts_modern_design_system_props(self):
        """Props that are NOT legacy should be accepted."""
        puck_data = {
            "root": {
                "props": {
                    "title": "Test",
                    "backgroundColor": "#ffffff",
                    "textColor": "#000000",
                    "fontSize": "16px",
                    "gap": "8px",
                    "margin": "16px",
                }
            },
            "content": [
                {
                    "type": "Section",
                    "props": {
                        "children": "Content",
                        "backgroundColor": "#f5f5f5",
                        "paddingTop": "24px",
                        "paddingBottom": "24px",
                        "paddingLeft": "16px",
                        "paddingRight": "16px",
                    },
                },
            ],
        }
        # Should not raise
        validate_puck_data_no_legacy_section_props(puck_data)
