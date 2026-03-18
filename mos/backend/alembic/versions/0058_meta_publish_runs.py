"""meta publish runs

Revision ID: 0058_meta_publish_runs
Revises: 0057_meta_publish_selections
Create Date: 2026-03-13 10:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0058_meta_publish_runs"
down_revision = "0057_meta_publish_selections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meta_publish_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("campaign_name", sa.Text(), nullable=False),
        sa.Column("campaign_objective", sa.Text(), nullable=False),
        sa.Column("buying_type", sa.Text(), nullable=True),
        sa.Column(
            "special_ad_categories",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("publish_base_url", sa.Text(), nullable=False),
        sa.Column("publish_domain", sa.Text(), nullable=True),
        sa.Column("ad_account_id", sa.Text(), nullable=True),
        sa.Column("page_id", sa.Text(), nullable=True),
        sa.Column("meta_campaign_id", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_meta_publish_runs_org_campaign", "meta_publish_runs", ["org_id", "campaign_id"], unique=False)
    op.create_index("idx_meta_publish_runs_org_created", "meta_publish_runs", ["org_id", "created_at"], unique=False)

    op.create_table(
        "meta_publish_run_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("publish_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("creative_spec_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("adset_spec_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("resolved_destination_url", sa.Text(), nullable=True),
        sa.Column("meta_asset_upload_id", sa.Text(), nullable=True),
        sa.Column("meta_creative_id", sa.Text(), nullable=True),
        sa.Column("meta_adset_id", sa.Text(), nullable=True),
        sa.Column("meta_ad_id", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["adset_spec_id"], ["meta_adset_specs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["creative_spec_id"], ["meta_creative_specs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["publish_run_id"], ["meta_publish_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("publish_run_id", "asset_id", name="uq_meta_publish_run_items_run_asset"),
    )
    op.create_index("idx_meta_publish_run_items_org_run", "meta_publish_run_items", ["org_id", "publish_run_id"], unique=False)
    op.create_index("idx_meta_publish_run_items_org_asset", "meta_publish_run_items", ["org_id", "asset_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_meta_publish_run_items_org_asset", table_name="meta_publish_run_items")
    op.drop_index("idx_meta_publish_run_items_org_run", table_name="meta_publish_run_items")
    op.drop_table("meta_publish_run_items")
    op.drop_index("idx_meta_publish_runs_org_created", table_name="meta_publish_runs")
    op.drop_index("idx_meta_publish_runs_org_campaign", table_name="meta_publish_runs")
    op.drop_table("meta_publish_runs")
