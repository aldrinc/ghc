"""add medusa_product_id to products

Revision ID: 0072_product_medusa_id
Revises: 0071_client_medusa_configs
Create Date: 2026-03-23 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0072_product_medusa_id"
down_revision = "0071_client_medusa_configs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("medusa_product_id", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("products", "medusa_product_id")
