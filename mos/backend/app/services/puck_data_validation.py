"""Puck data validation for import-contract parity.

This module provides validation to ensure Puck data does not contain
legacy Section props that have been replaced by modern design-system tokens.

Legacy props (must be rejected):
- layout
- containerWidth
- padding
"""

from __future__ import annotations

from typing import Any


# Legacy Section props that are no longer supported
LEGACY_SECTION_PROPS = frozenset({"layout", "containerWidth", "padding"})


class LegacySectionPropError(ValueError):
    """Raised when legacy Section props are detected in Puck data.

    Attributes:
        prop_name: The legacy prop name found.
        path: The path to the block containing the legacy prop.
    """

    def __init__(self, prop_name: str, path: str):
        self.prop_name = prop_name
        self.path = path
        super().__init__(
            f"Legacy Section prop '{prop_name}' found at '{path}'. "
            f"These props are no longer supported. "
            f"Use design-system tokens instead."
        )


def _check_legacy_props_in_props(
    props: dict[str, Any],
    path: str,
) -> list[LegacySectionPropError]:
    """Check a single props dict for legacy Section props.

    Args:
        props: The props dict to check.
        path: The path to this props location (for error reporting).

    Returns:
        List of LegacySectionPropError found (empty if valid).
    """
    errors = []
    for prop_name in LEGACY_SECTION_PROPS:
        if prop_name in props:
            errors.append(LegacySectionPropError(prop_name, path))
    return errors


def _validate_puck_data_recursive(
    puck_data: dict[str, Any],
    path: str = "root",
) -> list[LegacySectionPropError]:
    """Recursively validate puck data for legacy Section props.

    Args:
        puck_data: The Puck data structure to validate.
        path: Current path in the structure (for error reporting).

    Returns:
        List of LegacySectionPropError found (empty if valid).
    """
    errors: list[LegacySectionPropError] = []

    # Check root block (stored at puck_data["root"])
    if "root" in puck_data and isinstance(puck_data["root"], dict):
        root_block = puck_data["root"]
        if "props" in root_block and isinstance(root_block["props"], dict):
            errors.extend(_check_legacy_props_in_props(root_block["props"], "root.props"))

    # Check content array for blocks
    content = puck_data.get("content")
    if isinstance(content, list):
        for idx, item in enumerate(content):
            if not isinstance(item, dict):
                continue

            item_path = f"{path}.content[{idx}]"

            # Check item props directly
            if "props" in item and isinstance(item["props"], dict):
                errors.extend(_check_legacy_props_in_props(item["props"], f"{item_path}.props"))

            # Recurse into item if it has a nested structure (e.g., slots)
            if "slots" in item and isinstance(item["slots"], dict):
                for slot_name, slot_content in item["slots"].items():
                    if isinstance(slot_content, list):
                        for slot_idx, slot_item in enumerate(slot_content):
                            if isinstance(slot_item, dict) and "props" in slot_item:
                                slot_path = f"{item_path}.slots.{slot_name}[{slot_idx}]"
                                if isinstance(slot_item["props"], dict):
                                    errors.extend(
                                        _check_legacy_props_in_props(
                                            slot_item["props"], f"{slot_path}.props"
                                        )
                                    )

            # Also check children recursively for complex block structures
            if "children" in item and isinstance(item["children"], list):
                for child_idx, child in enumerate(item["children"]):
                    if isinstance(child, dict):
                        child_path = f"{item_path}.children[{child_idx}]"
                        if "props" in child and isinstance(child["props"], dict):
                            errors.extend(
                                _check_legacy_props_in_props(child["props"], f"{child_path}.props")
                            )

    return errors


def validate_puck_data_no_legacy_section_props(puck_data: dict[str, Any]) -> None:
    """Validate that Puck data does not contain legacy Section props.

    Raises LegacySectionPropError if any legacy props are found.

    Args:
        puck_data: The Puck data structure to validate.

    Raises:
        LegacySectionPropError: If any legacy Section props are found.
    """
    if not isinstance(puck_data, dict):
        return

    errors = _validate_puck_data_recursive(puck_data)
    if errors:
        # Raise the first error (most actionable)
        raise errors[0]


def assert_no_legacy_section_props(puck_data: dict[str, Any]) -> None:
    """Backward-compatible assertion wrapper used by existing callers."""
    validate_puck_data_no_legacy_section_props(puck_data)
