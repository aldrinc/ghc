"""Add web_vital_recorded funnel event type

Revision ID: 0086_web_vital_recorded_event_type
Revises: 0085_prepared_funnel_checkouts
Create Date: 2026-04-19 00:30:00.000000

"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "0086_web_vital_recorded_event_type"
down_revision = "0085_prepared_funnel_checkouts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE funnel_event_type ADD VALUE IF NOT EXISTS 'web_vital_recorded'")


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely in-place.
    pass
