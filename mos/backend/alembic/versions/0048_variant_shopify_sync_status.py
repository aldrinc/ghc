"""Add Shopify variant sync status columns.

Tracks the most recent successful sync timestamp and the most recent sync error
for product variants mapped to Shopify.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0048_variant_shopify_sync_status"
down_revision = "0047_client_compliance_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_offer_price_points",
        sa.Column("shopify_last_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "product_offer_price_points",
        sa.Column("shopify_last_sync_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("product_offer_price_points", "shopify_last_sync_error")
    op.drop_column("product_offer_price_points", "shopify_last_synced_at")
