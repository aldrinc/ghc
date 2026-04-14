"""add client_medusa_configs table

Revision ID: 0071_client_medusa_configs
Revises: 0070_storefront_site_imports
Create Date: 2026-03-23 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0071_client_medusa_configs"
down_revision = "0070_storefront_site_imports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    op.create_table(
        "client_medusa_configs",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("admin_api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("publishable_key_encrypted", sa.Text(), nullable=True),
        sa.Column(
            "connection_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'not_configured'"),
        ),
        sa.Column("last_connection_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_connection_error", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("org_id", "client_id", name="uq_client_medusa_configs_org_client"),
        sa.Index("idx_client_medusa_configs_org_client", "org_id", "client_id"),
    )


def downgrade() -> None:
    op.drop_index("idx_client_medusa_configs_org_client", table_name="client_medusa_configs")
    op.drop_table("client_medusa_configs")
