"""Add Strategy V2 workflow/artifact enum values and feature flags.

Revision ID: 0050_strategy_v2_enums_and_flags
Revises: 0049_merge_0048_heads
Create Date: 2026-02-22 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0050_strategy_v2_enums_and_flags"
down_revision = "0049_merge_0048_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE workflow_kind ADD VALUE IF NOT EXISTS 'strategy_v2';")

    op.execute("ALTER TYPE artifact_type ADD VALUE IF NOT EXISTS 'strategy_v2_step_payload';")
    op.execute("ALTER TYPE artifact_type ADD VALUE IF NOT EXISTS 'strategy_v2_stage0';")
    op.execute("ALTER TYPE artifact_type ADD VALUE IF NOT EXISTS 'strategy_v2_stage1';")
    op.execute("ALTER TYPE artifact_type ADD VALUE IF NOT EXISTS 'strategy_v2_stage2';")
    op.execute("ALTER TYPE artifact_type ADD VALUE IF NOT EXISTS 'strategy_v2_stage3';")
    op.execute("ALTER TYPE artifact_type ADD VALUE IF NOT EXISTS 'strategy_v2_awareness_angle_matrix';")
    op.execute("ALTER TYPE artifact_type ADD VALUE IF NOT EXISTS 'strategy_v2_offer';")
    op.execute("ALTER TYPE artifact_type ADD VALUE IF NOT EXISTS 'strategy_v2_copy';")
    op.execute("ALTER TYPE artifact_type ADD VALUE IF NOT EXISTS 'strategy_v2_copy_context';")

    op.add_column(
        "orgs",
        sa.Column(
            "strategy_v2_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "clients",
        sa.Column(
            "strategy_v2_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("clients", "strategy_v2_enabled")
    op.drop_column("orgs", "strategy_v2_enabled")
