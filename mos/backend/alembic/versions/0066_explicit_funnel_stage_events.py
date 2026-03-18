"""add explicit funnel stage event types

Revision ID: 0066_explicit_funnel_stage_events
Revises: 0065_merge_shopify_and_deploy_heads
Create Date: 2026-03-18 18:05:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "0066_explicit_funnel_stage_events"
down_revision = "0065_merge_shopify_and_deploy_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE funnel_event_type ADD VALUE IF NOT EXISTS 'pre_sales_page_view'")
        op.execute("ALTER TYPE funnel_event_type ADD VALUE IF NOT EXISTS 'sales_page_view'")
        op.execute("ALTER TYPE funnel_event_type ADD VALUE IF NOT EXISTS 'checkout_page_view'")
        op.execute("ALTER TYPE funnel_event_type ADD VALUE IF NOT EXISTS 'thank_you_page_view'")
        op.execute("ALTER TYPE funnel_event_type ADD VALUE IF NOT EXISTS 'custom_page_view'")
        op.execute("ALTER TYPE funnel_event_type ADD VALUE IF NOT EXISTS 'pre_sales_to_sales_click'")
        op.execute("ALTER TYPE funnel_event_type ADD VALUE IF NOT EXISTS 'sales_to_checkout_click'")
        op.execute("ALTER TYPE funnel_event_type ADD VALUE IF NOT EXISTS 'custom_page_click'")


def downgrade() -> None:
    pass
