"""set default for site theme binding mode

Revision ID: 7c8d2e1f9b44
Revises: 4a9f6a7d3c21
Create Date: 2026-03-26 14:32:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "7c8d2e1f9b44"
down_revision = "4a9f6a7d3c21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE sites ALTER COLUMN theme_binding_mode SET DEFAULT 'standalone'::site_theme_binding_mode"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE sites ALTER COLUMN theme_binding_mode DROP DEFAULT")
