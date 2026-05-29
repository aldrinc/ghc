"""Add prepared page/version state to site_funnels.

Revision ID: 0085_site_funnel_preparation_state
Revises: 0084_site_funnel_html_template_imports
Create Date: 2026-04-08 21:45:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0085_site_funnel_preparation_state"
down_revision = "0084_site_funnel_html_template_imports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "site_funnels",
        sa.Column(
            "prepared_page_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("site_pages.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "site_funnels",
        sa.Column(
            "latest_prepared_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("site_page_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "site_funnels",
        sa.Column(
            "preparation_readiness",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "site_funnels",
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_site_funnels_prepared_page",
        "site_funnels",
        ["prepared_page_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_site_funnels_prepared_page", table_name="site_funnels")
    op.drop_column("site_funnels", "prepared_at")
    op.drop_column("site_funnels", "preparation_readiness")
    op.drop_column("site_funnels", "latest_prepared_version_id")
    op.drop_column("site_funnels", "prepared_page_id")
