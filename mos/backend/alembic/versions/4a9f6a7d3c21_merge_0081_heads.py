"""merge 0081 heads

Revision ID: 4a9f6a7d3c21
Revises: 0081_site_theme_binding_mode, 0081_stripe_account_profiles
Create Date: 2026-03-26 14:20:00.000000
"""

from __future__ import annotations


# revision identifiers, used by Alembic.
revision = "4a9f6a7d3c21"
down_revision = ("0081_site_theme_binding_mode", "0081_stripe_account_profiles")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
