"""add stripe_account_profiles table and extend client_medusa_configs

Revision ID: 0081_stripe_account_profiles
Revises: 0080_site_publications
Create Date: 2026-03-26 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0081_stripe_account_profiles"
down_revision = "0080_site_publications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    # Create stripe_account_profiles table
    op.create_table(
        "stripe_account_profiles",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("stripe_account_id", sa.Text(), nullable=True),
        sa.Column("secret_key_ref", sa.Text(), nullable=True),
        sa.Column("webhook_secret_ref", sa.Text(), nullable=True),
        sa.Column(
            "mode",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'shared'"),
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
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
        sa.UniqueConstraint("org_id", "label", name="uq_stripe_account_profiles_org_label"),
        sa.Index("idx_stripe_account_profiles_org_id", "org_id"),
    )

    # Add new columns to client_medusa_configs
    op.add_column(
        "client_medusa_configs",
        sa.Column(
            "stripe_account_profile_id",
            uuid,
            sa.ForeignKey("stripe_account_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "client_medusa_configs",
        sa.Column("default_payment_provider_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "client_medusa_configs",
        sa.Column(
            "allowed_payment_provider_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
    )
    op.add_column(
        "client_medusa_configs",
        sa.Column(
            "webhook_routing_mode",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'shared_ingress'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("client_medusa_configs", "webhook_routing_mode")
    op.drop_column("client_medusa_configs", "allowed_payment_provider_ids")
    op.drop_column("client_medusa_configs", "default_payment_provider_id")
    op.drop_column("client_medusa_configs", "stripe_account_profile_id")
    op.drop_index("idx_stripe_account_profiles_org_id", table_name="stripe_account_profiles")
    op.drop_table("stripe_account_profiles")
