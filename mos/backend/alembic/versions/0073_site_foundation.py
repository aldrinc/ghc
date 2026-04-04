"""Add site foundation fields to funnels and funnel_pages

Revision ID: 0073_site_foundation
Revises: 0072_product_medusa_id
Create Date: 2024-01-15 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0073_site_foundation"
down_revision = "0072_product_medusa_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add experience_kind column to funnels
    op.add_column(
        "funnels",
        sa.Column(
            "experience_kind",
            sa.Text(),
            nullable=True,
            server_default="funnel",
        ),
    )

    # Add site_type column to funnels
    op.add_column(
        "funnels",
        sa.Column(
            "site_type",
            sa.Text(),
            nullable=True,
        ),
    )

    # Add site_family column to funnels
    op.add_column(
        "funnels",
        sa.Column(
            "site_family",
            sa.Text(),
            nullable=True,
        ),
    )

    # Add commerce_provider column to funnels
    op.add_column(
        "funnels",
        sa.Column(
            "commerce_provider",
            sa.Text(),
            nullable=True,
        ),
    )

    # Add page_type column to funnel_pages
    op.add_column(
        "funnel_pages",
        sa.Column(
            "page_type",
            sa.Text(),
            nullable=True,
        ),
    )

    # Create indexes for efficient querying
    op.create_index(
        "idx_funnels_experience_kind",
        "funnels",
        ["experience_kind"],
        postgresql_where=sa.text("experience_kind IS NOT NULL"),
    )

    op.create_index(
        "idx_funnels_site_family",
        "funnels",
        ["site_family"],
        postgresql_where=sa.text("site_family IS NOT NULL"),
    )

    op.create_index(
        "idx_funnel_pages_page_type",
        "funnel_pages",
        ["page_type"],
        postgresql_where=sa.text("page_type IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_funnel_pages_page_type", table_name="funnel_pages")
    op.drop_index("idx_funnels_site_family", table_name="funnels")
    op.drop_index("idx_funnels_experience_kind", table_name="funnels")

    op.drop_column("funnel_pages", "page_type")
    op.drop_column("funnels", "commerce_provider")
    op.drop_column("funnels", "site_family")
    op.drop_column("funnels", "site_type")
    op.drop_column("funnels", "experience_kind")
