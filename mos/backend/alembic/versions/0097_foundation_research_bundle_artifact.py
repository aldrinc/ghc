"""Add foundation onboarding artifact types.

Revision ID: 0097_foundation_research_bundle_artifact
Revises: 0096_site_funnel_variants
Create Date: 2026-05-20
"""

from alembic import op


revision = "0097_foundation_research_bundle_artifact"
down_revision = "0096_site_funnel_variants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE artifact_type ADD VALUE IF NOT EXISTS 'context_dev_extraction';")
    op.execute("ALTER TYPE artifact_type ADD VALUE IF NOT EXISTS 'foundation_research_bundle';")


def downgrade() -> None:
    pass
