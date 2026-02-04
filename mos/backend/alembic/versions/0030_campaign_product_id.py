"""Add product_id to campaigns."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0030_campaign_product_id"
down_revision = "0029_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.add_column(
        "campaigns",
        sa.Column("product_id", uuid, sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("idx_campaigns_product", "campaigns", ["product_id"])


def downgrade() -> None:
    op.drop_index("idx_campaigns_product", table_name="campaigns")
    op.drop_column("campaigns", "product_id")
