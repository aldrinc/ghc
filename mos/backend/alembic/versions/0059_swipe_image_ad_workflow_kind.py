"""Add swipe_image_ad to workflow_kind enum.

Revision ID: 0059_swipe_image_ad_workflow_kind
Revises: 0058_meta_publish_runs
Create Date: 2026-03-17 17:10:00.000000
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0059_swipe_image_ad_workflow_kind"
down_revision = "0058_meta_publish_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE workflow_kind ADD VALUE IF NOT EXISTS 'swipe_image_ad';")


def downgrade() -> None:
    # Enum value removal is not straightforward in Postgres.
    # Leave as a no-op to avoid destructive changes.
    pass
