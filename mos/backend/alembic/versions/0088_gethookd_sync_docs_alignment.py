"""align gethookd sync defaults and credits accounting

Revision ID: 0088_gethookd_sync_docs_alignment
Revises: 0087_product_variant_shopify_selling_plan_id
Create Date: 2026-04-17 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0088_gethookd_sync_docs_alignment"
down_revision = "0087_product_variant_shopify_selling_plan_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "client_gethookd_sync_feeds",
        "max_pages_per_run",
        existing_type=sa.Integer(),
        server_default=sa.text("0"),
        existing_nullable=False,
    )
    op.alter_column(
        "client_gethookd_sync_feeds",
        "per_page",
        existing_type=sa.Integer(),
        server_default=sa.text("20"),
        existing_nullable=False,
    )
    op.alter_column(
        "gethookd_sync_runs",
        "credits_used",
        existing_type=sa.Integer(),
        type_=sa.Numeric(10, 2),
        postgresql_using="credits_used::numeric(10,2)",
        server_default=sa.text("0"),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "gethookd_sync_runs",
        "credits_used",
        existing_type=sa.Numeric(10, 2),
        type_=sa.Integer(),
        postgresql_using="ROUND(credits_used)::integer",
        server_default=sa.text("0"),
        existing_nullable=False,
    )
    op.alter_column(
        "client_gethookd_sync_feeds",
        "per_page",
        existing_type=sa.Integer(),
        server_default=sa.text("100"),
        existing_nullable=False,
    )
    op.alter_column(
        "client_gethookd_sync_feeds",
        "max_pages_per_run",
        existing_type=sa.Integer(),
        server_default=sa.text("5"),
        existing_nullable=False,
    )
