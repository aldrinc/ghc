"""merge current alembic heads

Revision ID: 0062_merge_meta_heads
Revises: 0059_meta_account_connections_and_configs, 0059_swipe_image_ad_workflow_kind, 0061_campaign_creative_context_artifacts
Create Date: 2026-03-18 16:45:00.000000
"""

from __future__ import annotations


revision = "0062_merge_meta_heads"
down_revision = (
    "0059_meta_account_connections_and_configs",
    "0059_swipe_image_ad_workflow_kind",
    "0061_campaign_creative_context_artifacts",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
