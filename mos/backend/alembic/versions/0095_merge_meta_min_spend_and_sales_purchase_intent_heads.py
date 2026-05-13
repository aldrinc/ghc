"""merge meta min spend and sales purchase intent heads

Revision ID: 0095_merge_meta_min_spend_and_sales_purchase_intent_heads
Revises: 0093_merge_meta_min_spend_and_tracking_heads, 0094_add_sales_purchase_intent_event_types
Create Date: 2026-05-13 12:30:00.000000
"""

from __future__ import annotations


revision = "0095_merge_meta_min_spend_and_sales_purchase_intent_heads"
down_revision = (
    "0093_merge_meta_min_spend_and_tracking_heads",
    "0094_add_sales_purchase_intent_event_types",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
