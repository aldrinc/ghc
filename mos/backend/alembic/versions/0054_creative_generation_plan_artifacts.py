"""Add creative generation plan artifact enum values.

Revision ID: 0054_creative_generation_plan_artifacts
Revises: 0053_merge_0051_0052_heads
Create Date: 2026-03-06 09:00:00.000000
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "0054_creative_generation_plan_artifacts"
down_revision = "0053_merge_0051_0052_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE artifact_type ADD VALUE IF NOT EXISTS 'ad_copy_pack';")
    op.execute("ALTER TYPE artifact_type ADD VALUE IF NOT EXISTS 'creative_generation_plan';")


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely in-place.
    pass
