"""Merge 0046 legacy and route-slug heads.

Revision ID: 0047_merge_0046_heads
Revises: 0046_client_shopify_default_shop, 0046_funnel_route_slug
Create Date: 2026-02-19 00:05:00.000000
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "0047_merge_0046_heads"
down_revision = ("0046_client_shopify_default_shop", "0046_funnel_route_slug")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
