"""Add Strategy V2 launch workflow kinds and launch lineage table.

Revision ID: 0052_strategy_v2_launch_lineage
Revises: 0051_gemini_context_files
Create Date: 2026-03-01 09:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0052_strategy_v2_launch_lineage"
down_revision = "0051_gemini_context_files"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE workflow_kind ADD VALUE IF NOT EXISTS 'strategy_v2_angle_launch';")
    op.execute("ALTER TYPE workflow_kind ADD VALUE IF NOT EXISTS 'strategy_v2_angle_iteration';")

    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "strategy_v2_launches",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "source_strategy_v2_workflow_run_id",
            uuid,
            sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_strategy_v2_temporal_workflow_id", sa.Text(), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", uuid, sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", uuid, sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("funnel_id", uuid, sa.ForeignKey("funnels.id", ondelete="SET NULL"), nullable=True),
        sa.Column("angle_id", sa.Text(), nullable=False),
        sa.Column("angle_run_id", sa.Text(), nullable=False),
        sa.Column("selected_ums_id", sa.Text(), nullable=True),
        sa.Column("selected_variant_id", sa.Text(), nullable=True),
        sa.Column("source_stage3_artifact_id", uuid, sa.ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_offer_artifact_id", uuid, sa.ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_copy_artifact_id", uuid, sa.ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "source_copy_context_artifact_id",
            uuid,
            sa.ForeignKey("artifacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("launch_type", sa.Text(), nullable=False),
        sa.Column("launch_key", sa.Text(), nullable=False),
        sa.Column("launch_index", sa.Integer(), nullable=True),
        sa.Column("launch_workflow_run_id", uuid, sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("launch_temporal_workflow_id", sa.Text(), nullable=True),
        sa.Column("created_by_user", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("org_id", "launch_key", name="uq_strategy_v2_launches_org_launch_key"),
        sa.UniqueConstraint(
            "org_id",
            "angle_run_id",
            "selected_ums_id",
            name="uq_strategy_v2_launches_org_angle_run_ums",
        ),
    )
    op.create_index(
        "idx_strategy_v2_launches_source_run",
        "strategy_v2_launches",
        ["org_id", "source_strategy_v2_workflow_run_id"],
    )
    op.create_index(
        "idx_strategy_v2_launches_campaign",
        "strategy_v2_launches",
        ["org_id", "campaign_id"],
    )
    op.create_index(
        "idx_strategy_v2_launches_angle",
        "strategy_v2_launches",
        ["org_id", "client_id", "product_id", "angle_id"],
    )
    op.create_index(
        "idx_strategy_v2_launches_created_at",
        "strategy_v2_launches",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_strategy_v2_launches_created_at", table_name="strategy_v2_launches")
    op.drop_index("idx_strategy_v2_launches_angle", table_name="strategy_v2_launches")
    op.drop_index("idx_strategy_v2_launches_campaign", table_name="strategy_v2_launches")
    op.drop_index("idx_strategy_v2_launches_source_run", table_name="strategy_v2_launches")
    op.drop_table("strategy_v2_launches")
