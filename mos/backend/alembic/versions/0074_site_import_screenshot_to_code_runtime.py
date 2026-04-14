"""add screenshot-to-code import persistence and site runtime

Revision ID: 0074_site_import_screenshot_to_code_runtime
Revises: 0073_site_foundation
Create Date: 2026-03-25 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0074_site_import_screenshot_to_code_runtime"
down_revision = "0073_site_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    op.create_table(
        "sites",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "site_import_id",
            uuid,
            sa.ForeignKey("site_imports.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "product_id", uuid, sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("site_type", sa.Text(), nullable=True),
        sa.Column("site_family", sa.Text(), nullable=True),
        sa.Column("commerce_provider", sa.Text(), nullable=True),
        sa.Column("source_hostname", sa.Text(), nullable=True),
        sa.Column("entry_page_type", sa.Text(), nullable=True),
        sa.Column("imported_page_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "completeness_state",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'partial'"),
        ),
        sa.Column("created_by_user_external_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("idx_sites_org_client", "sites", ["org_id", "client_id"], unique=False)
    op.create_index("idx_sites_family", "sites", ["site_family"], unique=False)

    op.create_table(
        "site_pages",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("site_id", uuid, sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("page_type", sa.Text(), nullable=True),
        sa.Column("template_id", sa.Text(), nullable=True),
        sa.Column("ordering", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column(
            "source_screenshot_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("generated_code", sa.Text(), nullable=True),
        sa.Column(
            "adapted_puck_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "outbound_links",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("site_id", "page_type", name="uq_site_pages_site_page_type"),
    )
    op.create_index("idx_site_pages_site", "site_pages", ["site_id"], unique=False)

    op.create_table(
        "site_page_versions",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "page_id", uuid, sa.ForeignKey("site_pages.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
        sa.Column(
            "puck_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "provenance",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("idx_site_page_versions_page", "site_page_versions", ["page_id"], unique=False)

    op.create_table(
        "site_links",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("site_id", uuid, sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "from_page_id", uuid, sa.ForeignKey("site_pages.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column(
            "to_page_id", uuid, sa.ForeignKey("site_pages.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("from_page_type", sa.Text(), nullable=True),
        sa.Column("to_page_type", sa.Text(), nullable=True),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("link_kind", sa.Text(), nullable=False, server_default=sa.text("'internal'")),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("idx_site_links_site", "site_links", ["site_id"], unique=False)

    op.add_column(
        "site_imports",
        sa.Column("input_mode", sa.Text(), nullable=False, server_default=sa.text("'image'")),
    )
    op.add_column("site_imports", sa.Column("generator_error", sa.Text(), nullable=True))
    op.add_column("site_imports", sa.Column("resolved_site_family", sa.Text(), nullable=True))
    op.add_column("site_imports", sa.Column("resolved_page_type", sa.Text(), nullable=True))
    op.add_column("site_imports", sa.Column("resolved_template_id", sa.Text(), nullable=True))
    op.add_column(
        "site_imports",
        sa.Column(
            "model_slots",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "site_imports",
        sa.Column(
            "upstream_request_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "site_imports",
        sa.Column(
            "upstream_transcript",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "site_imports",
        sa.Column(
            "upstream_variants",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "site_imports",
        sa.Column(
            "upstream_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "site_imports",
        sa.Column(
            "adapted_site",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "site_imports",
        sa.Column(
            "adapted_pages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "site_imports",
        sa.Column(
            "adapted_puck_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "site_imports",
        sa.Column(
            "saved_site_id",
            uuid,
            sa.ForeignKey("sites.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("site_imports", "saved_site_id")
    op.drop_column("site_imports", "adapted_puck_data")
    op.drop_column("site_imports", "adapted_pages")
    op.drop_column("site_imports", "adapted_site")
    op.drop_column("site_imports", "upstream_metadata")
    op.drop_column("site_imports", "upstream_variants")
    op.drop_column("site_imports", "upstream_transcript")
    op.drop_column("site_imports", "upstream_request_payload")
    op.drop_column("site_imports", "model_slots")
    op.drop_column("site_imports", "resolved_template_id")
    op.drop_column("site_imports", "resolved_page_type")
    op.drop_column("site_imports", "resolved_site_family")
    op.drop_column("site_imports", "generator_error")
    op.drop_column("site_imports", "input_mode")

    op.drop_index("idx_site_links_site", table_name="site_links")
    op.drop_table("site_links")

    op.drop_index("idx_site_page_versions_page", table_name="site_page_versions")
    op.drop_table("site_page_versions")

    op.drop_index("idx_site_pages_site", table_name="site_pages")
    op.drop_table("site_pages")

    op.drop_index("idx_sites_family", table_name="sites")
    op.drop_index("idx_sites_org_client", table_name="sites")
    op.drop_table("sites")
