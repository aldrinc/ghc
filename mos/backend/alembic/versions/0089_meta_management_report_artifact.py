"""add meta management report artifact enum value

Revision ID: 0089_meta_management_report_artifact
Revises: 0088_gethookd_sync_docs_alignment
Create Date: 2026-04-23 00:00:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "0089_meta_management_report_artifact"
down_revision = "0088_gethookd_sync_docs_alignment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE artifact_type ADD VALUE IF NOT EXISTS 'meta_management_report_markdown';"
    )


def downgrade() -> None:
    pass
