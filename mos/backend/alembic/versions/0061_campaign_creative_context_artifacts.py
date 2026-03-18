"""add campaign creative context artifact enum values

Revision ID: 0061_campaign_creative_context_artifacts
Revises: 0060_meta_rollout_artifacts
Create Date: 2026-03-18 15:30:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "0061_campaign_creative_context_artifacts"
down_revision = "0060_meta_rollout_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for value in (
        "campaign_loaded_angles",
        "campaign_loaded_offer",
        "campaign_loaded_copy",
        "campaign_loaded_copy_context",
        "campaign_creative_context",
    ):
        op.execute(f"ALTER TYPE artifact_type ADD VALUE IF NOT EXISTS '{value}';")


def downgrade() -> None:
    pass
