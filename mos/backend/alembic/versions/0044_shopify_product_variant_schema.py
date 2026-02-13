"""Add Shopify-aligned product fields and variant fields.

This migration keeps existing tables but extends them so our API/schema can align
to Shopify Liquid product/variant objects.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0044_shopify_product_variant_schema"
down_revision = "0043_creative_service_orchestration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    # Products: add Shopify-ish identity fields.
    op.add_column("products", sa.Column("handle", sa.Text(), nullable=True))
    op.add_column("products", sa.Column("vendor", sa.Text(), nullable=True))
    op.add_column(
        "products",
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
    )
    op.add_column("products", sa.Column("template_suffix", sa.Text(), nullable=True))
    op.add_column("products", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("idx_products_handle", "products", ["handle"])

    # Variants: extend existing price point rows (we'll treat these as variants).
    op.add_column(
        "product_offer_price_points",
        sa.Column("product_id", uuid, sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=True),
    )
    op.add_column("product_offer_price_points", sa.Column("compare_at_price_cents", sa.Integer(), nullable=True))
    op.add_column("product_offer_price_points", sa.Column("sku", sa.Text(), nullable=True))
    op.add_column("product_offer_price_points", sa.Column("barcode", sa.Text(), nullable=True))
    op.add_column(
        "product_offer_price_points",
        sa.Column("requires_shipping", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "product_offer_price_points",
        sa.Column("taxable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column("product_offer_price_points", sa.Column("weight", sa.Numeric(), nullable=True))
    op.add_column("product_offer_price_points", sa.Column("weight_unit", sa.Text(), nullable=True))
    op.add_column("product_offer_price_points", sa.Column("inventory_quantity", sa.Integer(), nullable=True))
    op.add_column("product_offer_price_points", sa.Column("inventory_policy", sa.Text(), nullable=True))
    op.add_column("product_offer_price_points", sa.Column("inventory_management", sa.Text(), nullable=True))
    op.add_column(
        "product_offer_price_points",
        sa.Column("incoming", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "product_offer_price_points",
        sa.Column("next_incoming_date", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("product_offer_price_points", sa.Column("unit_price_cents", sa.Integer(), nullable=True))
    op.add_column(
        "product_offer_price_points",
        sa.Column("unit_price_measurement", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "product_offer_price_points",
        sa.Column("quantity_rule", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "product_offer_price_points",
        sa.Column("quantity_price_breaks", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # Allow variants to exist without offers going forward.
    op.alter_column("product_offer_price_points", "offer_id", nullable=True)

    # Backfill product_id from offer -> product_id where possible.
    op.execute(
        """
        UPDATE product_offer_price_points AS pp
        SET product_id = po.product_id
        FROM product_offers AS po
        WHERE pp.offer_id = po.id AND pp.product_id IS NULL
        """
    )

    op.create_index("idx_price_points_product_id", "product_offer_price_points", ["product_id"])


def downgrade() -> None:
    op.drop_index("idx_price_points_product_id", table_name="product_offer_price_points")

    # Restore offer_id to non-null. This may fail if rows were created with NULL offer_id.
    op.alter_column("product_offer_price_points", "offer_id", nullable=False)

    op.drop_column("product_offer_price_points", "quantity_price_breaks")
    op.drop_column("product_offer_price_points", "quantity_rule")
    op.drop_column("product_offer_price_points", "unit_price_measurement")
    op.drop_column("product_offer_price_points", "unit_price_cents")
    op.drop_column("product_offer_price_points", "next_incoming_date")
    op.drop_column("product_offer_price_points", "incoming")
    op.drop_column("product_offer_price_points", "inventory_management")
    op.drop_column("product_offer_price_points", "inventory_policy")
    op.drop_column("product_offer_price_points", "inventory_quantity")
    op.drop_column("product_offer_price_points", "weight_unit")
    op.drop_column("product_offer_price_points", "weight")
    op.drop_column("product_offer_price_points", "taxable")
    op.drop_column("product_offer_price_points", "requires_shipping")
    op.drop_column("product_offer_price_points", "barcode")
    op.drop_column("product_offer_price_points", "sku")
    op.drop_column("product_offer_price_points", "compare_at_price_cents")
    op.drop_column("product_offer_price_points", "product_id")

    op.drop_index("idx_products_handle", table_name="products")
    op.drop_column("products", "published_at")
    op.drop_column("products", "template_suffix")
    op.drop_column("products", "tags")
    op.drop_column("products", "vendor")
    op.drop_column("products", "handle")

