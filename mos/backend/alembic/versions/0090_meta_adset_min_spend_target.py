"""add meta ad set daily min spend target

Revision ID: 0090_meta_adset_min_spend_target
Revises: 0089_meta_management_report_artifact
Create Date: 2026-05-06 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0090_meta_adset_min_spend_target"
down_revision = "0089_meta_management_report_artifact"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "meta_adset_specs",
        sa.Column(
            "daily_min_spend_target",
            sa.Integer(),
            server_default="1000",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("meta_adset_specs", "daily_min_spend_target")
