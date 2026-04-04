"""add storefront site imports and variant drafts

Revision ID: 0070_storefront_site_imports
Revises: 0069_swipe_collections_and_taxonomy
Create Date: 2026-03-22 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0070_storefront_site_imports"
down_revision = "0069_swipe_collections_and_taxonomy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    op.create_table(
        "site_imports",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_hostname", sa.Text(), nullable=True),
        sa.Column("page_type_hint", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("capture_error", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("meta_description", sa.Text(), nullable=True),
        sa.Column("suggested_template_family", sa.Text(), nullable=True),
        sa.Column(
            "theme_candidate",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "normalized_sections",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_external_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "idx_site_imports_org_client", "site_imports", ["org_id", "client_id"], unique=False
    )
    op.create_index("idx_site_imports_status", "site_imports", ["status"], unique=False)

    op.create_table(
        "site_import_snapshots",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "site_import_id",
            uuid,
            sa.ForeignKey("site_imports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("html_snapshot", sa.Text(), nullable=False),
        sa.Column("desktop_screenshot_data_url", sa.Text(), nullable=False),
        sa.Column("mobile_screenshot_data_url", sa.Text(), nullable=False),
        sa.Column(
            "capture_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("site_import_id", name="uq_site_import_snapshots_site_import"),
    )
    op.create_index(
        "idx_site_import_snapshots_org_client",
        "site_import_snapshots",
        ["org_id", "client_id"],
        unique=False,
    )

    op.create_table(
        "template_style_presets",
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
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
        sa.Column(
            "tokens",
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
    op.create_index(
        "idx_template_style_presets_org_client",
        "template_style_presets",
        ["org_id", "client_id"],
        unique=False,
    )

    op.create_table(
        "template_variants",
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
            "style_preset_id",
            uuid,
            sa.ForeignKey("template_style_presets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("family", sa.Text(), nullable=False),
        sa.Column("page_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
        sa.Column(
            "accepted_sections",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "provenance",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_external_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "idx_template_variants_org_client",
        "template_variants",
        ["org_id", "client_id"],
        unique=False,
    )
    op.create_index("idx_template_variants_status", "template_variants", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_template_variants_status", table_name="template_variants")
    op.drop_index("idx_template_variants_org_client", table_name="template_variants")
    op.drop_table("template_variants")

    op.drop_index("idx_template_style_presets_org_client", table_name="template_style_presets")
    op.drop_table("template_style_presets")

    op.drop_index("idx_site_import_snapshots_org_client", table_name="site_import_snapshots")
    op.drop_table("site_import_snapshots")

    op.drop_index("idx_site_imports_status", table_name="site_imports")
    op.drop_index("idx_site_imports_org_client", table_name="site_imports")
    op.drop_table("site_imports")
