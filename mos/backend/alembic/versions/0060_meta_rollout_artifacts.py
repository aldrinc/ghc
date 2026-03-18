"""add meta rollout artifact enum values

Revision ID: 0060_meta_rollout_artifacts
Revises: 0059_campaign_delivery_configs
Create Date: 2026-03-16 16:30:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "0060_meta_rollout_artifacts"
down_revision = "0059_campaign_delivery_configs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for value in (
        "meta_launch_plan",
        "meta_management_metrics_snapshot",
        "meta_management_recommended_actions",
        "meta_management_approval_decision",
        "meta_management_applied_action",
    ):
        op.execute(f"ALTER TYPE artifact_type ADD VALUE IF NOT EXISTS '{value}';")


def downgrade() -> None:
    pass
