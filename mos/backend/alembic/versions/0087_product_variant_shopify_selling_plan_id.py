"""Add Shopify selling plan ID to product variants

Revision ID: 0087_product_variant_shopify_selling_plan_id
Revises: 0086_web_vital_recorded_event_type
Create Date: 2026-04-21 16:20:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0087_product_variant_shopify_selling_plan_id"
down_revision = "0086_web_vital_recorded_event_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_offer_price_points",
        sa.Column("shopify_selling_plan_id", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("product_offer_price_points", "shopify_selling_plan_id")
