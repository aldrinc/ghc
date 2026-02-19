"""Add funnel runtime bundle artifact type.

Revision ID: 0048_funnel_runtime_bundle_artifact
Revises: 0047_merge_0046_heads
Create Date: 2026-02-19 00:30:00.000000
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0048_funnel_runtime_bundle_artifact"
down_revision = "0047_merge_0046_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE artifact_type ADD VALUE IF NOT EXISTS 'funnel_runtime_bundle';")


def downgrade() -> None:
    pass
