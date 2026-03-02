"""Add Shopify theme template draft persistence.

Revision ID: 0051_shopify_theme_template_drafts
Revises: 0050_org_deploy_domains
Create Date: 2026-02-26 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0051_shopify_theme_template_drafts"
down_revision = "0050_org_deploy_domains"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    op.create_table(
        "shopify_theme_template_drafts",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "client_id",
            uuid,
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "design_system_id",
            uuid,
            sa.ForeignKey("design_systems.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "product_id",
            uuid,
            sa.ForeignKey("products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("shop_domain", sa.Text(), nullable=False),
        sa.Column("theme_id", sa.Text(), nullable=False),
        sa.Column("theme_name", sa.Text(), nullable=False),
        sa.Column("theme_role", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_external_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "idx_shopify_theme_template_drafts_org_client",
        "shopify_theme_template_drafts",
        ["org_id", "client_id"],
    )
    op.create_index(
        "idx_shopify_theme_template_drafts_theme",
        "shopify_theme_template_drafts",
        ["shop_domain", "theme_id"],
    )
    op.create_index(
        "idx_shopify_theme_template_drafts_status",
        "shopify_theme_template_drafts",
        ["status"],
    )

    op.create_table(
        "shopify_theme_template_draft_versions",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "draft_id",
            uuid,
            sa.ForeignKey("shopify_theme_template_drafts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "client_id",
            uuid,
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False, server_default=sa.text("'build_job'")),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_external_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "draft_id",
            "version_number",
            name="uq_shopify_theme_template_draft_versions_draft_version",
        ),
    )
    op.create_index(
        "idx_shopify_theme_template_draft_versions_draft",
        "shopify_theme_template_draft_versions",
        ["draft_id"],
    )
    op.create_index(
        "idx_shopify_theme_template_draft_versions_org_client",
        "shopify_theme_template_draft_versions",
        ["org_id", "client_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_shopify_theme_template_draft_versions_org_client",
        table_name="shopify_theme_template_draft_versions",
    )
    op.drop_index(
        "idx_shopify_theme_template_draft_versions_draft",
        table_name="shopify_theme_template_draft_versions",
    )
    op.drop_table("shopify_theme_template_draft_versions")

    op.drop_index(
        "idx_shopify_theme_template_drafts_status",
        table_name="shopify_theme_template_drafts",
    )
    op.drop_index(
        "idx_shopify_theme_template_drafts_theme",
        table_name="shopify_theme_template_drafts",
    )
    op.drop_index(
        "idx_shopify_theme_template_drafts_org_client",
        table_name="shopify_theme_template_drafts",
    )
    op.drop_table("shopify_theme_template_drafts")
