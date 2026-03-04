"""Merge 0051 Shopify theme drafts and 0052 strategy lineage heads.

Revision ID: 0053_merge_0051_0052_heads
Revises: 0051_shopify_theme_template_drafts, 0052_strategy_v2_launch_lineage
Create Date: 2026-03-03 18:30:00.000000
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "0053_merge_0051_0052_heads"
down_revision = ("0051_shopify_theme_template_drafts", "0052_strategy_v2_launch_lineage")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
