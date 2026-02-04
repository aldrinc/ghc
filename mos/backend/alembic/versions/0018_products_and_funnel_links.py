"""Add products and link offers/funnels"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0018_products_and_funnel_links"
down_revision = "0017_design_systems"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    op.create_table(
        "products",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column(
            "primary_benefits",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column(
            "feature_bullets",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("guarantee_text", sa.Text(), nullable=True),
        sa.Column(
            "disclaimers",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_products_org_client", "products", ["org_id", "client_id"])

    op.add_column(
        "product_offers",
        sa.Column("product_id", uuid, sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("idx_product_offers_product", "product_offers", ["product_id"])

    op.add_column(
        "funnels",
        sa.Column("product_id", uuid, sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "funnels",
        sa.Column(
            "selected_offer_id",
            uuid,
            sa.ForeignKey("product_offers.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("idx_funnels_product", "funnels", ["product_id"])
    op.create_index("idx_funnels_selected_offer", "funnels", ["selected_offer_id"])


def downgrade() -> None:
    op.drop_index("idx_funnels_selected_offer", table_name="funnels")
    op.drop_index("idx_funnels_product", table_name="funnels")
    op.drop_column("funnels", "selected_offer_id")
    op.drop_column("funnels", "product_id")

    op.drop_index("idx_product_offers_product", table_name="product_offers")
    op.drop_column("product_offers", "product_id")

    op.drop_index("idx_products_org_client", table_name="products")
    op.drop_table("products")
