"""add checkout_started funnel event type

Revision ID: 0063_checkout_started_event_type
Revises: 0062_merge_meta_heads
Create Date: 2026-03-18 16:30:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "0063_checkout_started_event_type"
down_revision = "0062_merge_meta_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE funnel_event_type ADD VALUE IF NOT EXISTS 'checkout_started'")


def downgrade() -> None:
    pass
