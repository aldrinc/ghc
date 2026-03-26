"""Add site publication tables and active_publication ref on sites

Revision ID: 0080_site_publications
Revises: 0079_extend_site_system
Create Date: 2026-03-26 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision = "0080_site_publications"
down_revision = "0079_extend_site_system"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE artifact_type ADD VALUE IF NOT EXISTS 'site_runtime_bundle';")

    # -------------------------------------------------------------------------
    # Add active_site_publication_id helper column to sites
    # -------------------------------------------------------------------------
    op.add_column(
        "sites",
        sa.Column(
            "active_site_publication_id",
            UUID(as_uuid=True),
            nullable=True,
        ),
    )

    # -------------------------------------------------------------------------
    # site_publications table (immutable snapshots of site state at publish time)
    # -------------------------------------------------------------------------
    op.create_table(
        "site_publications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "site_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entry_page_id",
            UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "meta",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_site_publications_site", "site_publications", ["site_id"])
    op.create_unique_constraint(
        "uq_site_publications_site_created",
        "site_publications",
        ["site_id", "created_at"],
    )

    # Add FK for entry_page_id now that site_pages table exists
    op.create_foreign_key(
        "fk_site_publications_entry_page",
        "site_publications",
        "site_pages",
        ["entry_page_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Add FK for active_site_publication_id on sites
    op.create_foreign_key(
        "fk_sites_active_site_publication",
        "sites",
        "site_publications",
        ["active_site_publication_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # -------------------------------------------------------------------------
    # site_publication_pages table
    # -------------------------------------------------------------------------
    op.create_table(
        "site_publication_pages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "publication_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_publications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "page_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_pages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "page_version_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_page_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("slug_at_publish", sa.Text(), nullable=False),
        sa.Column("title_at_publish", sa.Text(), nullable=True),
        sa.Column("description_at_publish", sa.Text(), nullable=True),
        sa.Column("page_type_at_publish", sa.Text(), nullable=True),
        sa.Column("page_role_at_publish", sa.Text(), nullable=True),
        sa.Column("ordering_at_publish", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "og_image_asset_id",
            UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_site_publication_pages_pub", "site_publication_pages", ["publication_id"])
    op.create_index(
        "idx_site_publication_pages_pub_page",
        "site_publication_pages",
        ["publication_id", "page_id"],
    )
    op.create_unique_constraint(
        "uq_site_publication_pages_pub_slug",
        "site_publication_pages",
        ["publication_id", "slug_at_publish"],
    )

    # -------------------------------------------------------------------------
    # site_publication_links table
    # -------------------------------------------------------------------------
    op.create_table(
        "site_publication_links",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "publication_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_publications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "site_link_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_links.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_page_id_at_publish", UUID(as_uuid=True), nullable=True),
        sa.Column("to_page_id_at_publish", UUID(as_uuid=True), nullable=True),
        sa.Column("from_page_slug_at_publish", sa.Text(), nullable=True),
        sa.Column("to_page_slug_at_publish", sa.Text(), nullable=True),
        sa.Column("label_at_publish", sa.Text(), nullable=True),
        sa.Column(
            "link_kind_at_publish", sa.Text(), nullable=False, server_default=sa.text("'internal'")
        ),
        sa.Column(
            "meta_at_publish",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_site_publication_links_pub_from",
        "site_publication_links",
        ["publication_id", "from_page_id_at_publish"],
    )

    # -------------------------------------------------------------------------
    # site_publication_funnels table
    # -------------------------------------------------------------------------
    op.create_table(
        "site_publication_funnels",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "publication_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_publications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "site_funnel_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_funnels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name_at_publish", sa.Text(), nullable=False),
        sa.Column(
            "funnel_type_at_publish",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'checkout'"),
        ),
        sa.Column(
            "entry_page_id_at_publish",
            UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_site_publication_funnels_pub",
        "site_publication_funnels",
        ["publication_id"],
    )
    op.create_unique_constraint(
        "uq_site_publication_funnels_pub_funnel",
        "site_publication_funnels",
        ["publication_id", "site_funnel_id"],
    )

    # -------------------------------------------------------------------------
    # site_publication_funnel_steps table
    # -------------------------------------------------------------------------
    op.create_table(
        "site_publication_funnel_steps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "publication_funnel_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_publication_funnels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "site_funnel_step_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_funnel_steps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_id_at_publish", UUID(as_uuid=True), nullable=False),
        sa.Column("slug_at_publish", sa.Text(), nullable=False),
        sa.Column("ordering_at_publish", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("step_role_at_publish", sa.Text(), nullable=True),
        sa.Column("cta_label_at_publish", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_site_publication_funnel_steps_pub_funnel",
        "site_publication_funnel_steps",
        ["publication_funnel_id"],
    )
    op.create_unique_constraint(
        "uq_site_publication_funnel_steps_pub_funnel_ordering",
        "site_publication_funnel_steps",
        ["publication_funnel_id", "ordering_at_publish"],
    )

    # -------------------------------------------------------------------------
    # site_publication_product_bindings table
    # -------------------------------------------------------------------------
    op.create_table(
        "site_publication_product_bindings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "publication_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_publications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "site_product_binding_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_product_page_bindings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id_at_publish",
            UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("page_id_at_publish", UUID(as_uuid=True), nullable=True),
        sa.Column("page_role_at_publish", sa.Text(), nullable=False),
        sa.Column(
            "variant_ids_at_publish", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "binding_context_at_publish",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("priority_at_publish", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "active_at_publish", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_site_publication_product_bindings_pub",
        "site_publication_product_bindings",
        ["publication_id"],
    )
    op.create_unique_constraint(
        "uq_site_publication_product_bindings_pub_binding",
        "site_publication_product_bindings",
        ["publication_id", "site_product_binding_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_site_publication_product_bindings_pub_binding",
        "site_publication_product_bindings",
        type_="unique",
    )
    op.drop_index(
        "idx_site_publication_product_bindings_pub",
        table_name="site_publication_product_bindings",
    )
    op.drop_table("site_publication_product_bindings")

    op.drop_constraint(
        "uq_site_publication_funnel_steps_pub_funnel_ordering",
        "site_publication_funnel_steps",
        type_="unique",
    )
    op.drop_index(
        "idx_site_publication_funnel_steps_pub_funnel",
        table_name="site_publication_funnel_steps",
    )
    op.drop_table("site_publication_funnel_steps")

    op.drop_constraint(
        "uq_site_publication_funnels_pub_funnel",
        "site_publication_funnels",
        type_="unique",
    )
    op.drop_index(
        "idx_site_publication_funnels_pub",
        table_name="site_publication_funnels",
    )
    op.drop_table("site_publication_funnels")

    op.drop_index(
        "idx_site_publication_links_pub_from",
        table_name="site_publication_links",
    )
    op.drop_table("site_publication_links")

    op.drop_constraint(
        "uq_site_publication_pages_pub_slug",
        "site_publication_pages",
        type_="unique",
    )
    op.drop_index(
        "idx_site_publication_pages_pub_page",
        table_name="site_publication_pages",
    )
    op.drop_index(
        "idx_site_publication_pages_pub",
        table_name="site_publication_pages",
    )
    op.drop_table("site_publication_pages")

    # Remove FKs and column before dropping table
    op.drop_constraint(
        "fk_sites_active_site_publication",
        "sites",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_site_publications_entry_page",
        "site_publications",
        type_="foreignkey",
    )

    op.drop_index("idx_site_publications_site", table_name="site_publications")
    op.drop_constraint(
        "uq_site_publications_site_created",
        "site_publications",
        type_="unique",
    )
    op.drop_table("site_publications")

    op.drop_column("sites", "active_site_publication_id")
