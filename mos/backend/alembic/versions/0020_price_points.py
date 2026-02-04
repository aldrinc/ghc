"""Add Stripe price ids and option values for price points."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0020_price_points"
down_revision = "0019_unify_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_offers",
        sa.Column("options_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.add_column(
        "product_offer_price_points",
        sa.Column("provider", sa.Text(), nullable=True),
    )
    op.add_column(
        "product_offer_price_points",
        sa.Column("external_price_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "product_offer_price_points",
        sa.Column("option_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.create_index(
        "idx_price_points_provider",
        "product_offer_price_points",
        ["provider"],
    )
    op.create_index(
        "idx_price_points_external_price_id",
        "product_offer_price_points",
        ["external_price_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_price_points_external_price_id", table_name="product_offer_price_points")
    op.drop_index("idx_price_points_provider", table_name="product_offer_price_points")
    op.drop_column("product_offer_price_points", "option_values")
    op.drop_column("product_offer_price_points", "external_price_id")
    op.drop_column("product_offer_price_points", "provider")
    op.drop_column("product_offers", "options_schema")
