"""remove legacy section props from funnel page versions

Revision ID: 0077_remove_legacy_section_props
Revises: 0076_gethookd_sync_backend
Create Date: 2026-03-25 18:30:00.000000
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0077_remove_legacy_section_props"
down_revision = "0076_gethookd_sync_backend"
branch_labels = None
depends_on = None


_LEGACY_SECTION_PROP_KEYS = ("layout", "containerWidth", "padding")
_CONTAINER_WIDTH_MAP = {
    "sm": "sm",
    "md": "md",
    "lg": "lg",
    "xl": "xl",
}
_SURFACE_MAP = {
    "full": "none",
    "contained": "subtle",
    "card": "card",
}
_PAD_MAP = {
    "none": "none",
    "sm": "sm",
    "md": "md",
    "lg": "lg",
}
_SHELL_COMPONENT_TYPES = {
    "CommerceCart",
    "CommerceCatalogHero",
    "CommerceCheckout",
    "CommerceProductDetail",
    "CommerceStoreFooter",
    "CommerceStoreHeader",
    "CommerceStoreTemplate",
    "StarterCollectionRails",
    "StarterHomeHero",
    "StarterPromoBar",
    "StarterStoreFooter",
    "StarterStoreHeader",
}


def _section_owns_its_inner_container(props: dict[str, Any]) -> bool:
    content = props.get("content")
    if not isinstance(content, list) or len(content) != 1:
        return False
    child = content[0]
    return isinstance(child, dict) and child.get("type") in _SHELL_COMPONENT_TYPES


def _migrate_value(value: Any) -> tuple[Any, bool]:
    if isinstance(value, list):
        next_items: list[Any] = []
        changed = False
        for item in value:
            next_item, item_changed = _migrate_value(item)
            next_items.append(next_item)
            changed = changed or item_changed
        return next_items, changed

    if not isinstance(value, dict):
        return value, False

    next_obj = deepcopy(value)
    changed = False

    props = next_obj.get("props")
    if next_obj.get("type") == "Section" and isinstance(props, dict):
        legacy_keys = [key for key in _LEGACY_SECTION_PROP_KEYS if key in props]
        if legacy_keys:
            shell_section = _section_owns_its_inner_container(props)

            props.setdefault("bandWidth", "bleed")
            props.setdefault("contentAlign", "center")

            if shell_section:
                props.setdefault("contentWidth", "none")
                props.setdefault("surface", "none")
                props.setdefault("padY", "none")
                props.setdefault("padX", "none")
            else:
                legacy_width = props.get("containerWidth")
                legacy_layout = props.get("layout")
                legacy_padding = props.get("padding")
                props.setdefault("contentWidth", _CONTAINER_WIDTH_MAP.get(str(legacy_width), "xl"))
                props.setdefault("surface", _SURFACE_MAP.get(str(legacy_layout), "none"))
                props.setdefault("padY", _PAD_MAP.get(str(legacy_padding), "md"))
                props.setdefault("padX", "md")

            for key in legacy_keys:
                props.pop(key, None)
            changed = True

    for key, child in list(next_obj.items()):
        next_child, child_changed = _migrate_value(child)
        next_obj[key] = next_child
        changed = changed or child_changed

    return next_obj, changed


def _has_legacy_section_props(value: Any) -> bool:
    if isinstance(value, list):
        return any(_has_legacy_section_props(item) for item in value)
    if not isinstance(value, dict):
        return False
    if value.get("type") == "Section":
        props = value.get("props")
        if isinstance(props, dict) and any(key in props for key in _LEGACY_SECTION_PROP_KEYS):
            return True
    return any(_has_legacy_section_props(child) for child in value.values())


def upgrade() -> None:
    bind = op.get_bind()
    page_versions = sa.table(
        "funnel_page_versions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("puck_data", postgresql.JSONB(astext_type=sa.Text())),
    )

    rows = bind.execute(sa.select(page_versions.c.id, page_versions.c.puck_data)).mappings().all()
    updated = 0
    for row in rows:
        migrated, changed = _migrate_value(row["puck_data"])
        if not changed:
            continue
        bind.execute(
            page_versions.update()
            .where(page_versions.c.id == row["id"])
            .values(puck_data=migrated)
        )
        updated += 1

    remaining = 0
    for row in bind.execute(sa.select(page_versions.c.puck_data)).scalars():
        if _has_legacy_section_props(row):
            remaining += 1

    if remaining:
        raise RuntimeError(
            f"Legacy Section props remain in funnel_page_versions after migration: {remaining} rows."
        )

    if updated:
        print(f"Migrated legacy Section props in {updated} funnel_page_versions rows.")


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade is not supported for 0077_remove_legacy_section_props because the legacy "
        "Section prop shape was intentionally removed."
    )
