"""Add Shopify product identity to products and offer bonus links.

Revision ID: 0045_offer_bonuses_and_shopify_product_gid
Revises: 0044_shopify_product_variant_schema
Create Date: 2026-02-16 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0045_offer_bonuses_and_shopify_product_gid"
down_revision = "0044_shopify_product_variant_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    op.add_column("products", sa.Column("shopify_product_gid", sa.Text(), nullable=True))
    op.create_index("idx_products_shopify_product_gid", "products", ["shopify_product_gid"])

    op.create_table(
        "product_offer_bonuses",
        sa.Column("id", uuid, nullable=False),
        sa.Column("org_id", uuid, nullable=False),
        sa.Column("client_id", uuid, nullable=False),
        sa.Column("offer_id", uuid, nullable=False),
        sa.Column("bonus_product_id", uuid, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["offer_id"], ["product_offers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["bonus_product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("offer_id", "bonus_product_id", name="uq_product_offer_bonuses_offer_bonus_product"),
    )
    op.create_index("idx_product_offer_bonuses_offer", "product_offer_bonuses", ["offer_id"])
    op.create_index("idx_product_offer_bonuses_bonus_product", "product_offer_bonuses", ["bonus_product_id"])


def downgrade() -> None:
    op.drop_index("idx_product_offer_bonuses_bonus_product", table_name="product_offer_bonuses")
    op.drop_index("idx_product_offer_bonuses_offer", table_name="product_offer_bonuses")
    op.drop_table("product_offer_bonuses")

    op.drop_index("idx_products_shopify_product_gid", table_name="products")
    op.drop_column("products", "shopify_product_gid")
