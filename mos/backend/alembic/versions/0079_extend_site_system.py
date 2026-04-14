"""Extend site system data model for canonical site-first objects

Revision ID: 0079_extend_site_system
Revises: 0078_site_runtime_canonical
Create Date: 2026-03-25 12:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision = "0079_extend_site_system"
down_revision = "0078_site_runtime_canonical"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "site_templates",
        sa.Column(
            "is_system_template", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "site_templates",
        sa.Column(
            "provenance_notes",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    op.add_column(
        "site_funnels",
        sa.Column("funnel_type", sa.Text(), nullable=False, server_default=sa.text("'checkout'")),
    )
    op.add_column(
        "site_funnels",
        sa.Column("tracking_config", JSONB(), nullable=True),
    )

    # -------------------------------------------------------------------------
    # Extend sites table: primary_domain, site_template_id
    # -------------------------------------------------------------------------
    op.add_column(
        "sites",
        sa.Column(
            "primary_domain",
            sa.Text(),
            nullable=True,
        ),
    )
    op.add_column(
        "sites",
        sa.Column(
            "site_template_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # -------------------------------------------------------------------------
    # Extend site_pages table: page_role, status, is_system_page, page_template_id
    # -------------------------------------------------------------------------
    op.add_column(
        "site_pages",
        sa.Column(
            "page_role",
            sa.Text(),
            nullable=True,
        ),
    )
    op.add_column(
        "site_pages",
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
    )
    op.add_column(
        "site_pages",
        sa.Column(
            "is_system_page",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "site_pages",
        sa.Column(
            "page_template_id",
            sa.Text(),
            nullable=True,
        ),
    )

    # Add index on status for filtering
    op.create_index("idx_site_pages_status", "site_pages", ["status"])

    # -------------------------------------------------------------------------
    # Extend site_page_versions table: source_type, source_id, ai_metadata,
    # diff_summary, allow published status
    # -------------------------------------------------------------------------
    op.add_column(
        "site_page_versions",
        sa.Column(
            "source_type",
            sa.Text(),
            nullable=True,
        ),
    )
    op.add_column(
        "site_page_versions",
        sa.Column(
            "source_id",
            sa.Text(),
            nullable=True,
        ),
    )
    op.add_column(
        "site_page_versions",
        sa.Column(
            "ai_metadata",
            JSONB(),
            nullable=True,
        ),
    )
    op.add_column(
        "site_page_versions",
        sa.Column(
            "diff_summary",
            sa.Text(),
            nullable=True,
        ),
    )

    # Drop the old server_default and replace with one that allows 'published'
    op.alter_column(
        "site_page_versions",
        "status",
        existing_server_default="draft",
        server_default=None,
    )
    # Now update existing rows to 'draft' if they somehow have wrong values
    # and ensure the column is nullable=False with valid values
    op.execute(
        "UPDATE site_page_versions SET status = 'draft' WHERE status NOT IN ('draft', 'approved', 'published')"
    )
    op.create_check_constraint(
        "ck_site_page_versions_status_valid",
        "site_page_versions",
        "status IN ('draft', 'approved', 'published')",
    )

    # -------------------------------------------------------------------------
    # site_template_pages table (canonical template page definitions)
    # -------------------------------------------------------------------------
    op.create_table(
        "site_template_pages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "site_template_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_type", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("page_template_id", sa.Text(), nullable=True),  # References funnel template
        sa.Column("ordering", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_entry", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "provenance_notes", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_site_template_pages_template", "site_template_pages", ["site_template_id"])
    op.create_unique_constraint(
        "uq_site_template_pages_template_type",
        "site_template_pages",
        ["site_template_id", "page_type"],
    )
    op.create_unique_constraint(
        "uq_site_template_pages_template_ordering",
        "site_template_pages",
        ["site_template_id", "ordering"],
    )

    # -------------------------------------------------------------------------
    # site_template_links table (canonical template link definitions)
    # -------------------------------------------------------------------------
    op.create_table(
        "site_template_links",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "site_template_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_page_type", sa.Text(), nullable=True),
        sa.Column("to_page_type", sa.Text(), nullable=True),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("link_kind", sa.Text(), nullable=False, server_default=sa.text("'internal'")),
        sa.Column("meta", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_site_template_links_template", "site_template_links", ["site_template_id"])

    # -------------------------------------------------------------------------
    # site_template_funnels table (canonical template funnel definitions)
    # -------------------------------------------------------------------------
    op.create_table(
        "site_template_funnels",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "site_template_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("funnel_type", sa.Text(), nullable=False, server_default=sa.text("'checkout'")),
        sa.Column("entry_page_type", sa.Text(), nullable=True),
        sa.Column(
            "provenance_notes", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_site_template_funnels_template", "site_template_funnels", ["site_template_id"]
    )

    # -------------------------------------------------------------------------
    # site_template_funnel_steps table (canonical template funnel step definitions)
    # -------------------------------------------------------------------------
    op.create_table(
        "site_template_funnel_steps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "site_template_funnel_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_template_funnels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_type", sa.Text(), nullable=False),
        sa.Column("ordering", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("step_role", sa.Text(), nullable=True),
        sa.Column("cta_label", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_site_template_funnel_steps_funnel",
        "site_template_funnel_steps",
        ["site_template_funnel_id"],
    )
    op.create_unique_constraint(
        "uq_site_template_funnel_steps_funnel_ordering",
        "site_template_funnel_steps",
        ["site_template_funnel_id", "ordering"],
    )

    # -------------------------------------------------------------------------
    # site_product_page_bindings table
    # -------------------------------------------------------------------------
    op.create_table(
        "site_product_page_bindings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "site_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "site_page_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_pages.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "site_funnel_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_funnels.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("page_role", sa.Text(), nullable=False),  # e.g., 'pdp', 'cart', 'checkout'
        sa.Column("variant_ids", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column(
            "binding_context", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
    op.create_index("idx_site_product_bindings_site", "site_product_page_bindings", ["site_id"])
    op.create_index(
        "idx_site_product_bindings_product", "site_product_page_bindings", ["product_id"]
    )
    op.create_index(
        "idx_site_product_bindings_site_page", "site_product_page_bindings", ["site_page_id"]
    )
    op.create_index(
        "idx_site_product_bindings_site_funnel", "site_product_page_bindings", ["site_funnel_id"]
    )
    op.create_unique_constraint(
        "uq_site_product_bindings_site_product_role_funnel",
        "site_product_page_bindings",
        ["site_id", "product_id", "page_role", "site_funnel_id"],
    )

    # -------------------------------------------------------------------------
    # site_import_applications table (audit trail for import apply actions)
    # -------------------------------------------------------------------------
    op.create_table(
        "site_import_applications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "site_import_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_imports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "action", sa.Text(), nullable=False
        ),  # 'create-site', 'add-pages', 'create-site-template', 'create-page-template'
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("site_id", UUID(as_uuid=True), nullable=True),
        sa.Column("site_page_ids", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("site_template_id", UUID(as_uuid=True), nullable=True),
        sa.Column("template_variant_id", UUID(as_uuid=True), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("result_summary", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by_user_external_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_site_import_applications_import", "site_import_applications", ["site_import_id"]
    )
    op.create_index("idx_site_import_applications_action", "site_import_applications", ["action"])
    op.create_index(
        "idx_site_import_applications_created_at", "site_import_applications", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_site_import_applications_created_at", table_name="site_import_applications")
    op.drop_index("idx_site_import_applications_action", table_name="site_import_applications")
    op.drop_index("idx_site_import_applications_import", table_name="site_import_applications")
    op.drop_table("site_import_applications")

    # Drop site_import_applications
    op.drop_constraint(
        "uq_site_product_bindings_site_product_role_funnel",
        "site_product_page_bindings",
        type_="unique",
    )
    op.drop_index("idx_site_product_bindings_site_funnel", table_name="site_product_page_bindings")
    op.drop_index("idx_site_product_bindings_site_page", table_name="site_product_page_bindings")
    op.drop_index("idx_site_product_bindings_product", table_name="site_product_page_bindings")
    op.drop_index("idx_site_product_bindings_site", table_name="site_product_page_bindings")
    op.drop_table("site_product_page_bindings")

    # Drop site_template_funnel_steps
    op.drop_constraint(
        "uq_site_template_funnel_steps_funnel_ordering",
        "site_template_funnel_steps",
        type_="unique",
    )
    op.drop_index("idx_site_template_funnel_steps_funnel", table_name="site_template_funnel_steps")
    op.drop_table("site_template_funnel_steps")

    # Drop site_template_funnels
    op.drop_index("idx_site_template_funnels_template", table_name="site_template_funnels")
    op.drop_table("site_template_funnels")

    # Drop site_template_links
    op.drop_index("idx_site_template_links_template", table_name="site_template_links")
    op.drop_table("site_template_links")

    # Drop site_template_pages
    op.drop_unique_constraint(
        "uq_site_template_pages_template_ordering", "site_template_pages", type_="unique"
    )
    op.drop_unique_constraint(
        "uq_site_template_pages_template_type", "site_template_pages", type_="unique"
    )
    op.drop_index("idx_site_template_pages_template", table_name="site_template_pages")
    op.drop_table("site_template_pages")

    # Restore site_page_versions status
    op.drop_check_constraint("ck_site_page_versions_status_valid", "site_page_versions")
    op.alter_column(
        "site_page_versions",
        "status",
        existing_server_default=None,
        server_default="draft",
    )

    # Remove site_page_versions columns
    op.drop_column("site_page_versions", "diff_summary")
    op.drop_column("site_page_versions", "ai_metadata")
    op.drop_column("site_page_versions", "source_id")
    op.drop_column("site_page_versions", "source_type")

    # Remove site_pages columns
    op.drop_index("idx_site_pages_status", table_name="site_pages")
    op.drop_column("site_pages", "page_template_id")
    op.drop_column("site_pages", "is_system_page")
    op.drop_column("site_pages", "status")
    op.drop_column("site_pages", "page_role")

    # Remove sites columns
    op.drop_column("sites", "site_template_id")
    op.drop_column("sites", "primary_domain")

    op.drop_column("site_funnels", "tracking_config")
    op.drop_column("site_funnels", "funnel_type")
    op.drop_column("site_templates", "provenance_notes")
    op.drop_column("site_templates", "is_system_template")
