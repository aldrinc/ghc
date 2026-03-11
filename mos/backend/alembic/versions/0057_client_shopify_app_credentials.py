"""Persist per-workspace Shopify app credentials.

Revision ID: 0057_client_shopify_app_credentials
Revises: 0056_client_shopify_storefront_domain
Create Date: 2026-03-11 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0057_client_shopify_app_credentials"
down_revision = "0056_client_shopify_storefront_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    op.create_table(
        "client_shopify_app_credentials",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=False),
        sa.Column("api_secret", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint(
            "org_id",
            "client_id",
            name="uq_client_shopify_app_credentials_org_client",
        ),
    )
    op.create_index(
        "idx_client_shopify_app_credentials_org_client",
        "client_shopify_app_credentials",
        ["org_id", "client_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_client_shopify_app_credentials_org_client",
        table_name="client_shopify_app_credentials",
    )
    op.drop_table("client_shopify_app_credentials")
