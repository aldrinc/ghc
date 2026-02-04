"""Add primary asset to products."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0033_product_primary_asset"
down_revision = "0032_set_default_design_systems"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("primary_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_products_primary_asset",
        "products",
        "assets",
        ["primary_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_products_primary_asset", "products", ["primary_asset_id"])


def downgrade() -> None:
    op.drop_index("idx_products_primary_asset", table_name="products")
    op.drop_constraint("fk_products_primary_asset", "products", type_="foreignkey")
    op.drop_column("products", "primary_asset_id")
