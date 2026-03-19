"""add DSA beneficiary/payor to meta adset specs

Revision ID: 0068_meta_adset_spec_dsa_fields
Revises: 0067_rename_funnel_enter_event
Create Date: 2026-03-18 17:35:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0068_meta_adset_spec_dsa_fields"
down_revision = "0067_rename_funnel_enter_event"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("meta_adset_specs", sa.Column("dsa_beneficiary", sa.Text(), nullable=True))
    op.add_column("meta_adset_specs", sa.Column("dsa_payor", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("meta_adset_specs", "dsa_payor")
    op.drop_column("meta_adset_specs", "dsa_beneficiary")
