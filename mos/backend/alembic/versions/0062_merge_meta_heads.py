"""merge current alembic heads

Revision ID: 0062_merge_meta_heads
Revises: 0060_merge_0059_heads, 0061_campaign_creative_context_artifacts
Create Date: 2026-03-18 16:45:00.000000
"""

from __future__ import annotations


revision = "0062_merge_meta_heads"
down_revision = (
    "0060_merge_0059_heads",
    "0061_campaign_creative_context_artifacts",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
