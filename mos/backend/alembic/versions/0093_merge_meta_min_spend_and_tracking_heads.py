"""merge meta min spend and funnel tracking heads

Revision ID: 0093_merge_meta_min_spend_and_tracking_heads
Revises: 0090_meta_adset_min_spend_target, 0092_merge_meta_management_and_funnel_tracking_heads
Create Date: 2026-05-07 14:05:00.000000
"""

from __future__ import annotations


revision = "0093_merge_meta_min_spend_and_tracking_heads"
down_revision = (
    "0090_meta_adset_min_spend_target",
    "0092_merge_meta_management_and_funnel_tracking_heads",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
