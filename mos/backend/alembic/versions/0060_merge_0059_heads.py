"""Merge 0059 Meta account config and swipe workflow heads.

Revision ID: 0060_merge_0059_heads
Revises: 0059_meta_account_connections_and_configs, 0059_swipe_image_ad_workflow_kind
Create Date: 2026-03-18 12:05:00.000000
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "0060_merge_0059_heads"
down_revision = (
    "0059_meta_account_connections_and_configs",
    "0059_swipe_image_ad_workflow_kind",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
