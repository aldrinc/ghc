"""Add next_page_id to funnel_pages."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0036_funnel_page_next_page"
down_revision = "0035_product_brand_relationships"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "funnel_pages",
        sa.Column("next_page_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_funnel_pages_next_page_id",
        "funnel_pages",
        "funnel_pages",
        ["next_page_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_funnel_pages_next_page", "funnel_pages", ["next_page_id"])


def downgrade() -> None:
    op.drop_index("idx_funnel_pages_next_page", table_name="funnel_pages")
    op.drop_constraint("fk_funnel_pages_next_page_id", "funnel_pages", type_="foreignkey")
    op.drop_column("funnel_pages", "next_page_id")
