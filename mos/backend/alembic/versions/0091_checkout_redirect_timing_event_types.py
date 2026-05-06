"""add checkout redirect timing event types

Revision ID: 0091_checkout_redirect_timing_event_types
Revises: 0090_quiz_funnel_event_types
Create Date: 2026-05-05 15:30:00.000000

"""

from alembic import op


revision = "0091_checkout_redirect_timing_event_types"
down_revision = "0090_quiz_funnel_event_types"
branch_labels = None
depends_on = None


EVENT_TYPES = (
    "checkout_click",
    "checkout_redirect_started",
    "checkout_pagehide",
    "checkout_visibility_hidden",
)


def upgrade() -> None:
    for event_type in EVENT_TYPES:
        op.execute(f"ALTER TYPE funnel_event_type ADD VALUE IF NOT EXISTS '{event_type}'")


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely without recreating the type.
    pass
