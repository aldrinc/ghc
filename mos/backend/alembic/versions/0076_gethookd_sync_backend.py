"""add gethookd sync backend tables and review fields

Revision ID: 0076_gethookd_sync_backend
Revises: 0075_add_site_family_hint
Create Date: 2026-03-25 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0076_gethookd_sync_backend"
down_revision = "0075_add_site_family_hint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # === GetHookd credentials table ===
    op.create_table(
        "client_gethookd_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("credentials_encrypted", sa.Text(), nullable=False),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_validation_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("org_id", "client_id", name="uq_gethookd_credentials_org_client"),
    )
    op.create_index(
        "idx_gethookd_credentials_org_client",
        "client_gethookd_credentials",
        ["org_id", "client_id"],
        unique=False,
    )

    # === GetHookd sync feeds table ===
    op.create_table(
        "client_gethookd_sync_feeds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "filters_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("max_pages_per_run", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("per_page", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "idx_gethookd_sync_feeds_org_client",
        "client_gethookd_sync_feeds",
        ["org_id", "client_id"],
        unique=False,
    )
    op.create_index(
        "idx_gethookd_sync_feeds_org_client_enabled",
        "client_gethookd_sync_feeds",
        ["org_id", "client_id", "enabled"],
        unique=False,
    )

    # === GetHookd sync runs table ===
    op.create_table(
        "gethookd_sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'running'")),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("feeds_attempted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("feeds_succeeded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assets_new", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assets_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assets_marked_stale", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assets_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("credits_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_gethookd_sync_runs_org_client",
        "gethookd_sync_runs",
        ["org_id", "client_id"],
        unique=False,
    )
    op.create_index(
        "idx_gethookd_sync_runs_started_at",
        "gethookd_sync_runs",
        ["started_at"],
        unique=False,
    )

    # === Campaign default swipe collection ===
    op.add_column(
        "campaigns",
        sa.Column(
            "default_swipe_collection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("swipe_collections.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_campaigns_default_swipe_collection",
        "campaigns",
        ["default_swipe_collection_id"],
        unique=False,
    )

    # === CompanySwipeAsset review fields ===
    op.add_column(
        "company_swipe_assets",
        sa.Column("review_status", sa.Text(), nullable=True),
    )
    op.add_column(
        "company_swipe_assets",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "company_swipe_assets",
        sa.Column("reviewed_by_user_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "company_swipe_assets",
        sa.Column("source_first_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "company_swipe_assets",
        sa.Column("source_last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "company_swipe_assets",
        sa.Column("source_last_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "company_swipe_assets",
        sa.Column("source_payload_hash", sa.Text(), nullable=True),
    )
    op.add_column(
        "company_swipe_assets",
        sa.Column("source_content_changed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "company_swipe_assets",
        sa.Column("source_metadata_json", postgresql.JSONB(), nullable=True),
    )
    # Index for review status filtering
    op.create_index(
        "idx_company_swipe_assets_review_status",
        "company_swipe_assets",
        ["review_status"],
        unique=False,
    )
    op.create_index(
        "uq_company_swipe_assets_org_origin_external_ad",
        "company_swipe_assets",
        ["org_id", "origin_system", "external_ad_id"],
        unique=True,
        postgresql_where=sa.text("external_ad_id IS NOT NULL"),
    )

    # === CompanySwipeMedia media_asset_id FK ===
    op.add_column(
        "company_swipe_media",
        sa.Column(
            "media_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("media_assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    # Unique index on (swipe_asset_id, media_asset_id) where media_asset_id IS NOT NULL
    op.create_index(
        "uq_company_swipe_media_swipe_asset_media_asset",
        "company_swipe_media",
        ["swipe_asset_id", "media_asset_id"],
        unique=True,
        postgresql_where=sa.text("media_asset_id IS NOT NULL"),
    )


def downgrade() -> None:
    # === CompanySwipeMedia media_asset_id ===
    op.drop_index(
        "uq_company_swipe_media_swipe_asset_media_asset",
        table_name="company_swipe_media",
    )
    op.drop_column("company_swipe_media", "media_asset_id")

    # === CompanySwipeAsset review fields ===
    op.drop_index(
        "uq_company_swipe_assets_org_origin_external_ad",
        table_name="company_swipe_assets",
    )
    op.drop_index(
        "idx_company_swipe_assets_review_status",
        table_name="company_swipe_assets",
    )
    op.drop_column("company_swipe_assets", "source_metadata_json")
    op.drop_column("company_swipe_assets", "source_content_changed_at")
    op.drop_column("company_swipe_assets", "source_payload_hash")
    op.drop_column("company_swipe_assets", "source_last_synced_at")
    op.drop_column("company_swipe_assets", "source_last_seen_at")
    op.drop_column("company_swipe_assets", "source_first_seen_at")
    op.drop_column("company_swipe_assets", "reviewed_by_user_id")
    op.drop_column("company_swipe_assets", "reviewed_at")
    op.drop_column("company_swipe_assets", "review_status")

    # === Campaign default swipe collection ===
    op.drop_index(
        "idx_campaigns_default_swipe_collection",
        table_name="campaigns",
    )
    op.drop_column("campaigns", "default_swipe_collection_id")

    # === GetHookd sync runs ===
    op.drop_index(
        "idx_gethookd_sync_runs_started_at",
        table_name="gethookd_sync_runs",
    )
    op.drop_index(
        "idx_gethookd_sync_runs_org_client",
        table_name="gethookd_sync_runs",
    )
    op.drop_table("gethookd_sync_runs")

    # === GetHookd sync feeds ===
    op.drop_index(
        "idx_gethookd_sync_feeds_org_client_enabled",
        table_name="client_gethookd_sync_feeds",
    )
    op.drop_index(
        "idx_gethookd_sync_feeds_org_client",
        table_name="client_gethookd_sync_feeds",
    )
    op.drop_table("client_gethookd_sync_feeds")

    # === GetHookd credentials ===
    op.drop_index(
        "idx_gethookd_credentials_org_client",
        table_name="client_gethookd_credentials",
    )
    op.drop_table("client_gethookd_credentials")
