"""Add connected social and content growth agent tables.

Revision ID: 0098_connected_social_growth_agents
Revises: 0097_foundation_research_bundle_artifact
Create Date: 2026-05-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "0098_connected_social_growth_agents"
down_revision = "0097_foundation_research_bundle_artifact"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "social_provider_connections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("external_user_id", sa.Text(), nullable=True),
        sa.Column("auth_type", sa.Text(), nullable=False, server_default="oauth"),
        sa.Column("scopes_json", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("token_metadata_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("last_health_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("metadata_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_timestamps(),
    )
    op.create_index(
        "idx_social_provider_connections_org_client",
        "social_provider_connections",
        ["org_id", "client_id"],
    )
    op.create_index(
        "idx_social_provider_connections_provider_status",
        "social_provider_connections",
        ["provider", "status"],
    )

    op.create_table(
        "social_provider_assets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", UUID(as_uuid=True), sa.ForeignKey("social_provider_connections.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_asset_id", sa.Text(), nullable=False),
        sa.Column("asset_type", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("parent_provider_asset_id", sa.Text(), nullable=True),
        sa.Column("capability_flags_json", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("raw_payload_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint(
            "org_id",
            "client_id",
            "provider",
            "provider_asset_id",
            "asset_type",
            name="uq_social_provider_assets_provider_asset_type",
        ),
    )
    op.create_index("idx_social_provider_assets_org_client", "social_provider_assets", ["org_id", "client_id"])
    op.create_index("idx_social_provider_assets_connection", "social_provider_assets", ["connection_id"])
    op.create_index("idx_social_provider_assets_type_status", "social_provider_assets", ["asset_type", "status"])

    op.create_table(
        "social_provider_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_asset_id", UUID(as_uuid=True), sa.ForeignKey("social_provider_assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("snapshot_type", sa.Text(), nullable=False),
        sa.Column("time_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("time_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metrics_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("raw_payload_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("provenance", sa.Text(), nullable=False, server_default="concrete"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_social_provider_snapshots_org_client", "social_provider_snapshots", ["org_id", "client_id"])
    op.create_index("idx_social_provider_snapshots_asset_created", "social_provider_snapshots", ["provider_asset_id", "created_at"])
    op.create_index("idx_social_provider_snapshots_type", "social_provider_snapshots", ["snapshot_type"])

    op.create_table(
        "agent_action_proposals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_agent_run_id", UUID(as_uuid=True), sa.ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("target_provider", sa.Text(), nullable=False),
        sa.Column("target_asset_id", sa.Text(), nullable=True),
        sa.Column("target_asset_type", sa.Text(), nullable=True),
        sa.Column("before_snapshot_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("proposed_after_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("risk_label", sa.Text(), nullable=False, server_default="medium"),
        sa.Column("required_capability", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("approved_by_user_id", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_response_json", JSONB(), nullable=True),
        sa.Column("rollback_hint_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_timestamps(),
    )
    op.create_index("idx_agent_action_proposals_org_client_status", "agent_action_proposals", ["org_id", "client_id", "status"])
    op.create_index("idx_agent_action_proposals_target", "agent_action_proposals", ["target_provider", "target_asset_id"])

    op.create_table(
        "conversion_sources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("goal_events_json", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("config_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("credentials_metadata_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        *_timestamps(),
    )
    op.create_index("idx_conversion_sources_org_client", "conversion_sources", ["org_id", "client_id"])
    op.create_index("idx_conversion_sources_provider_status", "conversion_sources", ["provider", "status"])

    op.create_table(
        "content_growth_programs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("campaign_id", UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("conversion_source_id", UUID(as_uuid=True), sa.ForeignKey("conversion_sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("platform_key", sa.Text(), nullable=False, server_default="tiktok"),
        sa.Column("format_key", sa.Text(), nullable=False, server_default="tiktok_carousel"),
        sa.Column("authority_mode", sa.Text(), nullable=False, server_default="approval_required"),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("settings_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_timestamps(),
    )
    op.create_index("idx_content_growth_programs_org_client", "content_growth_programs", ["org_id", "client_id"])
    op.create_index("idx_content_growth_programs_status", "content_growth_programs", ["status"])

    op.create_table(
        "content_experiments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("growth_program_id", UUID(as_uuid=True), sa.ForeignKey("content_growth_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("hook_family", sa.Text(), nullable=True),
        sa.Column("cta_family", sa.Text(), nullable=True),
        sa.Column("audience", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("metadata_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_timestamps(),
    )
    op.create_index("idx_content_experiments_program", "content_experiments", ["growth_program_id"])
    op.create_index("idx_content_experiments_org_client", "content_experiments", ["org_id", "client_id"])

    op.create_table(
        "content_variants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("growth_program_id", UUID(as_uuid=True), sa.ForeignKey("content_growth_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("experiment_id", UUID(as_uuid=True), sa.ForeignKey("content_experiments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("platform_key", sa.Text(), nullable=False, server_default="tiktok"),
        sa.Column("format_key", sa.Text(), nullable=False, server_default="tiktok_carousel"),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("cta", sa.Text(), nullable=True),
        sa.Column("slide_count", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("approved_by_user_id", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("storyboard_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("provider_payload_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_timestamps(),
    )
    op.create_index("idx_content_variants_program", "content_variants", ["growth_program_id"])
    op.create_index("idx_content_variants_experiment", "content_variants", ["experiment_id"])
    op.create_index("idx_content_variants_status", "content_variants", ["status"])

    op.create_table(
        "content_variant_slides",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_id", UUID(as_uuid=True), sa.ForeignKey("content_variants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slide_index", sa.Integer(), nullable=False),
        sa.Column("visual_role", sa.Text(), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("overlay_text", sa.Text(), nullable=False),
        sa.Column("source_asset_id", UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rendered_asset_id", UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("render_status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("renderer_version", sa.Text(), nullable=True),
        sa.Column("metadata_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_timestamps(),
        sa.UniqueConstraint("variant_id", "slide_index", name="uq_content_variant_slides_index"),
    )
    op.create_index("idx_content_variant_slides_variant", "content_variant_slides", ["variant_id"])

    op.create_table(
        "conversion_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversion_source_id", UUID(as_uuid=True), sa.ForeignKey("conversion_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_event_id", sa.Text(), nullable=False),
        sa.Column("event_name", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Numeric(14, 4), nullable=True),
        sa.Column("currency", sa.Text(), nullable=True),
        sa.Column("user_id_hash", sa.Text(), nullable=True),
        sa.Column("campaign_ref", sa.Text(), nullable=True),
        sa.Column("content_experiment_id", UUID(as_uuid=True), sa.ForeignKey("content_experiments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("content_variant_id", UUID(as_uuid=True), sa.ForeignKey("content_variants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("postiz_post_id", sa.Text(), nullable=True),
        sa.Column("postiz_channel_id", sa.Text(), nullable=True),
        sa.Column("attribution_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("raw_payload_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("provenance", sa.Text(), nullable=False, server_default="concrete"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("org_id", "conversion_source_id", "provider_event_id", name="uq_conversion_events_source_event"),
    )
    op.create_index("idx_conversion_events_org_client_occurred", "conversion_events", ["org_id", "client_id", "occurred_at"])
    op.create_index("idx_conversion_events_event_name", "conversion_events", ["event_name"])
    op.create_index("idx_conversion_events_content_variant", "conversion_events", ["content_variant_id"])
    op.create_index("idx_conversion_events_postiz_post", "conversion_events", ["postiz_post_id"])

    op.create_table(
        "hook_cta_rollups",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("growth_program_id", UUID(as_uuid=True), sa.ForeignKey("content_growth_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hook_key", sa.Text(), nullable=False),
        sa.Column("cta_key", sa.Text(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metrics_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("provenance", sa.Text(), nullable=False, server_default="concrete"),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint(
            "org_id",
            "client_id",
            "growth_program_id",
            "hook_key",
            "cta_key",
            name="uq_hook_cta_rollups_program_hook_cta",
        ),
    )
    op.create_index("idx_hook_cta_rollups_program", "hook_cta_rollups", ["growth_program_id"])


def downgrade() -> None:
    op.drop_index("idx_hook_cta_rollups_program", table_name="hook_cta_rollups")
    op.drop_table("hook_cta_rollups")
    op.drop_index("idx_conversion_events_postiz_post", table_name="conversion_events")
    op.drop_index("idx_conversion_events_content_variant", table_name="conversion_events")
    op.drop_index("idx_conversion_events_event_name", table_name="conversion_events")
    op.drop_index("idx_conversion_events_org_client_occurred", table_name="conversion_events")
    op.drop_table("conversion_events")
    op.drop_index("idx_content_variant_slides_variant", table_name="content_variant_slides")
    op.drop_table("content_variant_slides")
    op.drop_index("idx_content_variants_status", table_name="content_variants")
    op.drop_index("idx_content_variants_experiment", table_name="content_variants")
    op.drop_index("idx_content_variants_program", table_name="content_variants")
    op.drop_table("content_variants")
    op.drop_index("idx_content_experiments_org_client", table_name="content_experiments")
    op.drop_index("idx_content_experiments_program", table_name="content_experiments")
    op.drop_table("content_experiments")
    op.drop_index("idx_content_growth_programs_status", table_name="content_growth_programs")
    op.drop_index("idx_content_growth_programs_org_client", table_name="content_growth_programs")
    op.drop_table("content_growth_programs")
    op.drop_index("idx_conversion_sources_provider_status", table_name="conversion_sources")
    op.drop_index("idx_conversion_sources_org_client", table_name="conversion_sources")
    op.drop_table("conversion_sources")
    op.drop_index("idx_agent_action_proposals_target", table_name="agent_action_proposals")
    op.drop_index("idx_agent_action_proposals_org_client_status", table_name="agent_action_proposals")
    op.drop_table("agent_action_proposals")
    op.drop_index("idx_social_provider_snapshots_type", table_name="social_provider_snapshots")
    op.drop_index("idx_social_provider_snapshots_asset_created", table_name="social_provider_snapshots")
    op.drop_index("idx_social_provider_snapshots_org_client", table_name="social_provider_snapshots")
    op.drop_table("social_provider_snapshots")
    op.drop_index("idx_social_provider_assets_type_status", table_name="social_provider_assets")
    op.drop_index("idx_social_provider_assets_connection", table_name="social_provider_assets")
    op.drop_index("idx_social_provider_assets_org_client", table_name="social_provider_assets")
    op.drop_table("social_provider_assets")
    op.drop_index("idx_social_provider_connections_provider_status", table_name="social_provider_connections")
    op.drop_index("idx_social_provider_connections_org_client", table_name="social_provider_connections")
    op.drop_table("social_provider_connections")
