"""campaign delivery configs and strategy v2 launch context artifact

Revision ID: 0059_campaign_delivery_configs
Revises: 0058_meta_publish_runs
Create Date: 2026-03-16 12:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0059_campaign_delivery_configs"
down_revision = "0058_meta_publish_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE artifact_type ADD VALUE IF NOT EXISTS 'strategy_v2_launch_context';")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'campaign_delivery_mode') THEN
                CREATE TYPE campaign_delivery_mode AS ENUM ('internal_funnel', 'external_urls');
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'campaign_delivery_validation_status') THEN
                CREATE TYPE campaign_delivery_validation_status AS ENUM (
                    'not_applicable',
                    'not_validated',
                    'valid',
                    'invalid'
                );
            END IF;
        END
        $$;
        """
    )

    op.create_table(
        "campaign_delivery_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "delivery_mode",
            postgresql.ENUM("internal_funnel", "external_urls", name="campaign_delivery_mode", create_type=False),
            nullable=False,
            server_default="internal_funnel",
        ),
        sa.Column("pre_sales_url", sa.Text(), nullable=True),
        sa.Column("sales_url", sa.Text(), nullable=True),
        sa.Column("checkout_url", sa.Text(), nullable=True),
        sa.Column("thank_you_url", sa.Text(), nullable=True),
        sa.Column(
            "validation_status",
            postgresql.ENUM(
                "not_applicable",
                "not_validated",
                "valid",
                "invalid",
                name="campaign_delivery_validation_status",
                create_type=False,
            ),
            nullable=False,
            server_default="not_applicable",
        ),
        sa.Column("validation_error", sa.Text(), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", name="uq_campaign_delivery_configs_campaign"),
    )
    op.create_index(
        "idx_campaign_delivery_configs_org_campaign",
        "campaign_delivery_configs",
        ["org_id", "campaign_id"],
        unique=False,
    )

    op.execute(
        """
        INSERT INTO campaign_delivery_configs (
            org_id,
            client_id,
            campaign_id,
            delivery_mode,
            validation_status,
            created_at,
            updated_at
        )
        SELECT
            campaigns.org_id,
            campaigns.client_id,
            campaigns.id,
            'internal_funnel'::campaign_delivery_mode,
            'not_applicable'::campaign_delivery_validation_status,
            now(),
            now()
        FROM campaigns
        ON CONFLICT (campaign_id) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.drop_index("idx_campaign_delivery_configs_org_campaign", table_name="campaign_delivery_configs")
    op.drop_table("campaign_delivery_configs")
    op.execute("DROP TYPE IF EXISTS campaign_delivery_validation_status")
    op.execute("DROP TYPE IF EXISTS campaign_delivery_mode")
