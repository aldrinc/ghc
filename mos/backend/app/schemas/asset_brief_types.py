from __future__ import annotations

from collections.abc import Sequence


SUPPORTED_ASSET_BRIEF_TYPES: tuple[str, ...] = ("image", "video")


def normalize_required_asset_brief_types(
    value: Sequence[str],
    *,
    field_name: str,
) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise ValueError(f"{field_name} must include at least one supported value.")

    normalized: list[str] = []
    seen: set[str] = set()
    invalid: list[str] = []

    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} must contain non-empty strings.")
        cleaned = " ".join(item.strip().lower().split())
        if cleaned not in SUPPORTED_ASSET_BRIEF_TYPES:
            invalid.append(item.strip())
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)

    if invalid:
        supported = ", ".join(SUPPORTED_ASSET_BRIEF_TYPES)
        invalid_list = ", ".join(invalid)
        raise ValueError(
            f"{field_name} contains unsupported values: {invalid_list}. Supported values: {supported}."
        )
    if not normalized:
        raise ValueError(f"{field_name} must include at least one supported value.")
    return normalized


def normalize_optional_asset_brief_types(
    value: Sequence[str] | None,
    *,
    field_name: str,
) -> list[str] | None:
    if value is None:
        return None
    return normalize_required_asset_brief_types(value, field_name=field_name)
