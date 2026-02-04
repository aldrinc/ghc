"""Initial schema"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_init_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')
    op.execute("CREATE EXTENSION IF NOT EXISTS citext;")

    op.execute(
        "CREATE TYPE user_role AS ENUM ('partner','strategy','creative','performance','ops','data','experiment','admin');"
    )
    op.execute("CREATE TYPE client_status AS ENUM ('active','paused','archived');")
    op.execute("CREATE TYPE campaign_status AS ENUM ('draft','planning','running','completed','cancelled');")
    op.execute(
        "CREATE TYPE artifact_type AS ENUM ('client_canon','metric_schema','strategy_sheet','experiment_spec','asset_brief','qa_report','experiment_report','playbook');"
    )
    op.execute(
        "CREATE TYPE workflow_kind AS ENUM ('client_onboarding','campaign_planning','creative_production','experiment_cycle','playbook_update','test_campaign');"
    )
    op.execute("CREATE TYPE workflow_status AS ENUM ('running','completed','failed','cancelled');")
    op.execute("CREATE TYPE asset_status AS ENUM ('draft','qa_passed','approved','rejected');")
    op.execute("CREATE TYPE asset_source_type AS ENUM ('generated','historical','competitor_example');")

    uuid = postgresql.UUID(as_uuid=True)

    user_role_enum = postgresql.ENUM(name="user_role", create_type=False)
    client_status_enum = postgresql.ENUM(name="client_status", create_type=False)
    campaign_status_enum = postgresql.ENUM(name="campaign_status", create_type=False)
    artifact_type_enum = postgresql.ENUM(name="artifact_type", create_type=False)
    workflow_kind_enum = postgresql.ENUM(name="workflow_kind", create_type=False)
    workflow_status_enum = postgresql.ENUM(name="workflow_status", create_type=False)
    asset_status_enum = postgresql.ENUM(name="asset_status", create_type=False)
    asset_source_enum = postgresql.ENUM(name="asset_source_type", create_type=False)

    op.create_table(
        "orgs",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )

    op.create_table(
        "users",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clerk_user_id", sa.Text(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("role", user_role_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("org_id", "email", name="uq_users_org_email"),
    )

    op.create_table(
        "clients",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("industry", sa.Text(), nullable=True),
        sa.Column("primary_markets", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]"), nullable=False),
        sa.Column("primary_languages", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]"), nullable=False),
        sa.Column("status", client_status_enum, nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_clients_org", "clients", ["org_id"])

    op.create_table(
        "product_offers",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("business_model", sa.Text(), nullable=False),
        sa.Column("differentiation_bullets", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]"), nullable=False),
        sa.Column("guarantee_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )

    op.create_table(
        "product_offer_price_points",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("offer_id", uuid, sa.ForeignKey("product_offers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
    )

    op.create_table(
        "campaigns",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", campaign_status_enum, nullable=False, server_default=sa.text("'draft'")),
        sa.Column("goal_description", sa.Text(), nullable=True),
        sa.Column("objective_type", sa.Text(), nullable=True),
        sa.Column("numeric_target", sa.Numeric(), nullable=True),
        sa.Column("baseline", sa.Numeric(), nullable=True),
        sa.Column("timeframe_days", sa.Integer(), nullable=True),
        sa.Column("budget_min", sa.Numeric(), nullable=True),
        sa.Column("budget_max", sa.Numeric(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_campaigns_client", "campaigns", ["client_id"])

    op.create_table(
        "artifacts",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", uuid, sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("type", artifact_type_enum, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by_user", uuid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_artifacts_org_client_type", "artifacts", ["org_id", "client_id", "type"])
    op.create_index("idx_artifacts_campaign_type", "artifacts", ["campaign_id", "type"])
    op.create_index("idx_artifacts_gin_data", "artifacts", [sa.text("data")], postgresql_using="gin")

    op.create_table(
        "experiments",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", uuid, sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("experiment_spec_artifact_id", uuid, sa.ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'planned'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_experiments_campaign", "experiments", ["campaign_id"])

    op.create_table(
        "assets",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", uuid, sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("experiment_id", uuid, sa.ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("asset_brief_artifact_id", uuid, sa.ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("variant_id", sa.Text(), nullable=True),
        sa.Column("source_type", asset_source_enum, nullable=False),
        sa.Column("status", asset_status_enum, nullable=False, server_default=sa.text("'draft'")),
        sa.Column("channel_id", sa.Text(), nullable=False),
        sa.Column("format", sa.Text(), nullable=False),
        sa.Column("icp_id", sa.Text(), nullable=True),
        sa.Column("funnel_stage_id", sa.Text(), nullable=True),
        sa.Column("concept_id", sa.Text(), nullable=True),
        sa.Column("angle_type", sa.Text(), nullable=True),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_assets_client_campaign", "assets", ["client_id", "campaign_id"])
    op.create_index("idx_assets_experiment", "assets", ["experiment_id"])
    op.create_index("idx_assets_gin_content", "assets", [sa.text("content")], postgresql_using="gin")

    op.create_table(
        "asset_performance_snapshots",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("asset_id", uuid, sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("experiment_id", uuid, sa.ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("time_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("time_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("segments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_asset_perf_asset", "asset_performance_snapshots", ["asset_id"])
    op.create_index("idx_asset_perf_experiment", "asset_performance_snapshots", ["experiment_id"])

    op.create_table(
        "company_swipe_brands",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_brand_id", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=True),
        sa.Column("ad_library_link", sa.Text(), nullable=True),
        sa.Column("brand_page_link", sa.Text(), nullable=True),
        sa.Column("logo_url", sa.Text(), nullable=True),
        sa.Column("categories", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("org_id", "external_brand_id", name="uq_company_swipe_brand_org_ext"),
    )

    op.create_table(
        "company_swipe_assets",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_ad_id", sa.Text(), nullable=True),
        sa.Column("external_platform_ad_id", sa.Text(), nullable=True),
        sa.Column("brand_id", uuid, sa.ForeignKey("company_swipe_brands.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("platforms", sa.Text(), nullable=True),
        sa.Column("cta_type", sa.Text(), nullable=True),
        sa.Column("cta_text", sa.Text(), nullable=True),
        sa.Column("display_format", sa.Text(), nullable=True),
        sa.Column("landing_page", sa.Text(), nullable=True),
        sa.Column("link_description", sa.Text(), nullable=True),
        sa.Column("ad_source_link", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("days_active", sa.Integer(), nullable=True),
        sa.Column("active_in_library", sa.Boolean(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=True),
        sa.Column("used_count", sa.Integer(), nullable=True),
        sa.Column("saved_count", sa.Integer(), nullable=True),
        sa.Column("likes", sa.Integer(), nullable=True),
        sa.Column("winning_score", sa.Integer(), nullable=True),
        sa.Column("winning_score_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("performance_score", sa.Integer(), nullable=True),
        sa.Column("performance_score_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("age_audience_min", sa.Integer(), nullable=True),
        sa.Column("age_audience_max", sa.Integer(), nullable=True),
        sa.Column("gender_audience", sa.Text(), nullable=True),
        sa.Column("eu_total_reach", sa.Numeric(), nullable=True),
        sa.Column("ad_spend_range_score", sa.Integer(), nullable=True),
        sa.Column("ad_spend_range_score_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("added_human_time", sa.Text(), nullable=True),
        sa.Column("added_by_user_human_time", sa.Text(), nullable=True),
        sa.Column("saved_by_this_user", sa.Boolean(), nullable=True),
        sa.Column("share_url", sa.Text(), nullable=True),
        sa.Column("embed_url", sa.Text(), nullable=True),
        sa.Column("is_aaa_eligible", sa.Boolean(), nullable=True),
        sa.Column("is_saved", sa.Boolean(), nullable=True),
        sa.Column("is_used", sa.Boolean(), nullable=True),
        sa.Column("is_liked", sa.Boolean(), nullable=True),
        sa.Column("ad_script", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ad_reach_by_location", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ad_spend", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ad_library_object", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_company_swipe_org", "company_swipe_assets", ["org_id"])
    op.create_index("idx_company_swipe_brand", "company_swipe_assets", ["brand_id"])

    op.create_table(
        "company_swipe_media",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("swipe_asset_id", uuid, sa.ForeignKey("company_swipe_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_media_id", sa.Text(), nullable=True),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("thumbnail_path", sa.Text(), nullable=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("disk", sa.Text(), nullable=True),
        sa.Column("type", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("video_length", sa.Integer(), nullable=True),
        sa.Column("download_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_company_swipe_media_swipe", "company_swipe_media", ["swipe_asset_id"])

    op.create_table(
        "client_swipe_assets",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_swipe_id", uuid, sa.ForeignKey("company_swipe_assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("custom_title", sa.Text(), nullable=True),
        sa.Column("custom_body", sa.Text(), nullable=True),
        sa.Column("custom_channel", sa.Text(), nullable=True),
        sa.Column("custom_format", sa.Text(), nullable=True),
        sa.Column("custom_landing_page", sa.Text(), nullable=True),
        sa.Column("custom_media", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_good_example", sa.Boolean(), nullable=True),
        sa.Column("is_bad_example", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_client_swipe_client", "client_swipe_assets", ["client_id"])

    op.create_table(
        "workflow_runs",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("campaign_id", uuid, sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("temporal_workflow_id", sa.Text(), nullable=False),
        sa.Column("temporal_run_id", sa.Text(), nullable=False),
        sa.Column("kind", workflow_kind_enum, nullable=False),
        sa.Column("status", workflow_status_enum, nullable=False, server_default=sa.text("'running'")),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_workflow_runs_client", "workflow_runs", ["client_id"])
    op.create_index("idx_workflow_runs_campaign", "workflow_runs", ["campaign_id"])

    op.create_table(
        "activity_logs",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workflow_run_id", uuid, sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("payload_in", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("payload_out", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_activity_logs_workflow", "activity_logs", ["workflow_run_id"])


def downgrade() -> None:
    op.drop_index("idx_activity_logs_workflow", table_name="activity_logs")
    op.drop_table("activity_logs")

    op.drop_index("idx_workflow_runs_campaign", table_name="workflow_runs")
    op.drop_index("idx_workflow_runs_client", table_name="workflow_runs")
    op.drop_table("workflow_runs")

    op.drop_index("idx_client_swipe_client", table_name="client_swipe_assets")
    op.drop_table("client_swipe_assets")

    op.drop_index("idx_company_swipe_media_swipe", table_name="company_swipe_media")
    op.drop_table("company_swipe_media")

    op.drop_index("idx_company_swipe_brand", table_name="company_swipe_assets")
    op.drop_index("idx_company_swipe_org", table_name="company_swipe_assets")
    op.drop_table("company_swipe_assets")

    op.drop_table("company_swipe_brands")

    op.drop_index("idx_asset_perf_experiment", table_name="asset_performance_snapshots")
    op.drop_index("idx_asset_perf_asset", table_name="asset_performance_snapshots")
    op.drop_table("asset_performance_snapshots")

    op.drop_index("idx_assets_gin_content", table_name="assets")
    op.drop_index("idx_assets_experiment", table_name="assets")
    op.drop_index("idx_assets_client_campaign", table_name="assets")
    op.drop_table("assets")

    op.drop_index("idx_experiments_campaign", table_name="experiments")
    op.drop_table("experiments")

    op.drop_index("idx_artifacts_gin_data", table_name="artifacts")
    op.drop_index("idx_artifacts_campaign_type", table_name="artifacts")
    op.drop_index("idx_artifacts_org_client_type", table_name="artifacts")
    op.drop_table("artifacts")

    op.drop_index("idx_campaigns_client", table_name="campaigns")
    op.drop_table("campaigns")

    op.drop_table("product_offer_price_points")
    op.drop_table("product_offers")

    op.drop_index("idx_clients_org", table_name="clients")
    op.drop_table("clients")

    op.drop_table("users")
    op.drop_table("orgs")

    op.execute("DROP TYPE asset_source_type;")
    op.execute("DROP TYPE asset_status;")
    op.execute("DROP TYPE workflow_status;")
    op.execute("DROP TYPE workflow_kind;")
    op.execute("DROP TYPE artifact_type;")
    op.execute("DROP TYPE campaign_status;")
    op.execute("DROP TYPE client_status;")
    op.execute("DROP TYPE user_role;")
