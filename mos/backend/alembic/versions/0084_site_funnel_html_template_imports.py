"""Add site funnel HTML template imports and funnel template metadata.

Revision ID: 0084_site_funnel_html_template_imports
Revises: 0083_ember_skills_runtime_registry
Create Date: 2026-04-08 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "0084_site_funnel_html_template_imports"
down_revision = "0083_ember_skills_runtime_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_funnel_template_imports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "site_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_label", sa.Text(), nullable=False),
        sa.Column("html_snapshot", sa.Text(), nullable=False),
        sa.Column("html_sha256", sa.Text(), nullable=False),
        sa.Column("created_by_user_external_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_site_funnel_template_imports_site",
        "site_funnel_template_imports",
        ["site_id"],
    )
    op.create_index(
        "idx_site_funnel_template_imports_site_created",
        "site_funnel_template_imports",
        ["site_id", "created_at"],
    )

    op.add_column(
        "site_funnels",
        sa.Column(
            "template_import_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_funnel_template_imports.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "site_funnels",
        sa.Column("page_intent", sa.Text(), nullable=True),
    )
    op.add_column(
        "site_funnels",
        sa.Column(
            "campaign_id",
            UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "site_funnels",
        sa.Column("selected_angle_id", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_site_funnels_template_import",
        "site_funnels",
        ["template_import_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_site_funnels_template_import", table_name="site_funnels")
    op.drop_column("site_funnels", "selected_angle_id")
    op.drop_column("site_funnels", "campaign_id")
    op.drop_column("site_funnels", "page_intent")
    op.drop_column("site_funnels", "template_import_id")

    op.drop_index(
        "idx_site_funnel_template_imports_site_created",
        table_name="site_funnel_template_imports",
    )
    op.drop_index(
        "idx_site_funnel_template_imports_site",
        table_name="site_funnel_template_imports",
    )
    op.drop_table("site_funnel_template_imports")
