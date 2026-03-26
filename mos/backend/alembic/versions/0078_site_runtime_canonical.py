"""Add site runtime canonical tables and fields

Revision ID: 0078_site_runtime_canonical
Revises: 0076_gethookd_sync_backend
Create Date: 2026-03-25 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "0078_site_runtime_canonical"
down_revision = "0076_gethookd_sync_backend"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create site_templates table (minimal placeholder for slice 1)
    op.create_table(
        "site_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("family", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("site_type", sa.Text(), nullable=False),
        sa.Column("commerce_provider", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_site_templates_family", "site_templates", ["family"])

    # Create site_funnels table (minimal placeholder for slice 1)
    op.create_table(
        "site_funnels",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "site_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column(
            "entry_page_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_pages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "product_id",
            UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "selected_offer_id",
            UUID(as_uuid=True),
            sa.ForeignKey("product_offers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_site_funnels_site", "site_funnels", ["site_id"])
    op.create_index(
        "idx_site_funnels_site_entry_page", "site_funnels", ["site_id", "entry_page_id"]
    )

    # Create site_funnel_steps table (minimal placeholder for slice 1)
    op.create_table(
        "site_funnel_steps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "site_funnel_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_funnels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "site_page_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_pages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordering", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("step_role", sa.Text(), nullable=True),
        sa.Column("cta_label", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_site_funnel_steps_funnel", "site_funnel_steps", ["site_funnel_id"])
    op.create_unique_constraint(
        "uq_site_funnel_steps_funnel_ordering",
        "site_funnel_steps",
        ["site_funnel_id", "ordering"],
    )

    # Add columns to sites table
    op.add_column(
        "sites",
        sa.Column(
            "design_system_id",
            UUID(as_uuid=True),
            sa.ForeignKey("design_systems.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "sites",
        sa.Column(
            "route_slug",
            sa.Text(),
            nullable=True,
        ),
    )
    op.add_column(
        "sites",
        sa.Column(
            "entry_page_id",
            UUID(as_uuid=True),
            nullable=True,
        ),
    )

    op.create_unique_constraint("uq_sites_route_slug", "sites", ["route_slug"])

    # Add design_system_id to site_pages
    op.add_column(
        "site_pages",
        sa.Column(
            "design_system_id",
            UUID(as_uuid=True),
            sa.ForeignKey("design_systems.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # Drop old unique constraint on site_pages (site_id, page_type)
    op.drop_constraint("uq_site_pages_site_page_type", "site_pages", type_="unique")

    # Add new unique constraint on site_pages (site_id, slug)
    op.create_unique_constraint("uq_site_pages_site_slug", "site_pages", ["site_id", "slug"])

    # Add FK for entry_page_id now that site_pages table exists
    op.create_foreign_key(
        "fk_sites_entry_page_id",
        "sites",
        "site_pages",
        ["entry_page_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Remove FK for entry_page_id
    op.drop_constraint("fk_sites_entry_page_id", "sites", type_="foreignkey")

    # Remove unique constraint on site_pages (site_id, slug)
    op.drop_constraint("uq_site_pages_site_slug", "site_pages", type_="unique")

    # Add back old unique constraint on site_pages (site_id, page_type)
    op.create_unique_constraint(
        "uq_site_pages_site_page_type", "site_pages", ["site_id", "page_type"]
    )

    # Remove design_system_id from site_pages
    op.drop_column("site_pages", "design_system_id")

    # Drop route_slug unique constraint
    op.drop_constraint("uq_sites_route_slug", "sites", type_="unique")

    # Remove columns from sites table
    op.drop_column("sites", "entry_page_id")
    op.drop_column("sites", "route_slug")
    op.drop_column("sites", "design_system_id")

    # Drop site_funnel_steps table
    op.drop_constraint("uq_site_funnel_steps_funnel_ordering", "site_funnel_steps", type_="unique")
    op.drop_index("idx_site_funnel_steps_funnel", table_name="site_funnel_steps")
    op.drop_table("site_funnel_steps")

    # Drop site_funnels table
    op.drop_index("idx_site_funnels_site_entry_page", table_name="site_funnels")
    op.drop_index("idx_site_funnels_site", table_name="site_funnels")
    op.drop_table("site_funnels")

    # Drop site_templates table
    op.drop_index("idx_site_templates_family", table_name="site_templates")
    op.drop_table("site_templates")
