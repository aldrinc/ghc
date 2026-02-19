"""Add route_slug to funnels for slug-based public routing.

Revision ID: 0046_funnel_route_slug
Revises: 0045_offer_bonuses_and_shopify_product_gid
Create Date: 2026-02-18 00:00:00.000000
"""

from __future__ import annotations

import re

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0046_funnel_route_slug"
down_revision = "0045_offer_bonuses_and_shopify_product_gid"
branch_labels = None
depends_on = None


def _slugify(value: str) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "funnel"


def upgrade() -> None:
    op.add_column("funnels", sa.Column("route_slug", sa.Text(), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, name
            FROM funnels
            ORDER BY created_at ASC, id ASC
            """
        )
    ).mappings().all()

    used_slugs: set[str] = set()
    for row in rows:
        base = _slugify(str(row.get("name") or ""))
        slug = base
        suffix = 2
        while slug in used_slugs:
            slug = f"{base}-{suffix}"
            suffix += 1
        used_slugs.add(slug)
        bind.execute(
            sa.text(
                """
                UPDATE funnels
                SET route_slug = :slug
                WHERE id = :funnel_id
                """
            ),
            {"slug": slug, "funnel_id": row["id"]},
        )

    unresolved = bind.execute(
        sa.text("SELECT COUNT(*) FROM funnels WHERE route_slug IS NULL OR btrim(route_slug) = ''")
    ).scalar_one()
    if int(unresolved or 0) > 0:
        raise RuntimeError("Failed to backfill funnels.route_slug for all rows.")

    op.alter_column("funnels", "route_slug", nullable=False)
    op.create_unique_constraint("uq_funnels_route_slug", "funnels", ["route_slug"])


def downgrade() -> None:
    op.drop_constraint("uq_funnels_route_slug", "funnels", type_="unique")
    op.drop_column("funnels", "route_slug")
