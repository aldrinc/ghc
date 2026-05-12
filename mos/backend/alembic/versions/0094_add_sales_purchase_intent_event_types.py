"""add sales purchase intent funnel event types

Revision ID: 0094_add_sales_purchase_intent_event_types
Revises: 0093_animated_template_manifests
Create Date: 2026-05-12 10:30:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "0094_add_sales_purchase_intent_event_types"
down_revision = "0093_animated_template_manifests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE funnel_event_type ADD VALUE IF NOT EXISTS 'add_to_cart';")
    op.execute("ALTER TYPE funnel_event_type ADD VALUE IF NOT EXISTS 'purchase_intent_click';")


def downgrade() -> None:
    pass
