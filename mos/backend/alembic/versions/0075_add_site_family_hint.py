"""add site_family_hint to site_imports

Revision ID: 0075_add_site_family_hint
Revises: 0074_site_import_screenshot_to_code_runtime
Create Date: 2026-03-25 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0075_add_site_family_hint"
down_revision = "0074_site_import_screenshot_to_code_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("site_imports", sa.Column("site_family_hint", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("site_imports", "site_family_hint")
