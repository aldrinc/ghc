"""Add brand-centric ads ingestion schema"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0004_brand_ads_ingestion"
down_revision = "0003_onboarding_payloads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE ad_channel AS ENUM ('META_ADS_LIBRARY','TIKTOK_CREATIVE_CENTER','GOOGLE_ADS_TRANSPARENCY');"
    )
    op.execute("CREATE TYPE brand_role AS ENUM ('client','peer');")
    op.execute(
        "CREATE TYPE brand_channel_verification_status AS ENUM ('unverified','verified','mismatch');"
    )
    op.execute("CREATE TYPE ad_ingest_status AS ENUM ('RUNNING','SUCCEEDED','FAILED');")
    op.execute("CREATE TYPE ad_status AS ENUM ('active','inactive','unknown');")
    op.execute("CREATE TYPE media_asset_type AS ENUM ('IMAGE','VIDEO','TEXT','HTML','SCREENSHOT','OTHER');")

    uuid = postgresql.UUID(as_uuid=True)
    ad_channel_enum = postgresql.ENUM(name="ad_channel", create_type=False)
    brand_role_enum = postgresql.ENUM(name="brand_role", create_type=False)
    brand_verification_enum = postgresql.ENUM(name="brand_channel_verification_status", create_type=False)
    ad_ingest_status_enum = postgresql.ENUM(name="ad_ingest_status", create_type=False)
    ad_status_enum = postgresql.ENUM(name="ad_status", create_type=False)
    media_asset_type_enum = postgresql.ENUM(name="media_asset_type", create_type=False)

    op.create_table(
        "brands",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("normalized_name", postgresql.CITEXT(), nullable=False),
        sa.Column("primary_website_url", sa.Text(), nullable=True),
        sa.Column("primary_domain", postgresql.CITEXT(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index(
        "uq_brands_org_domain",
        "brands",
        ["org_id", "primary_domain"],
        unique=True,
        postgresql_where=sa.text("primary_domain IS NOT NULL"),
    )
    op.create_index(
        "uq_brands_org_normalized_name",
        "brands",
        ["org_id", "normalized_name"],
        unique=True,
        postgresql_where=sa.text("primary_domain IS NULL"),
    )

    op.create_table(
        "brand_channel_identities",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("brand_id", uuid, sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", ad_channel_enum, nullable=False),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "verification_status",
            brand_verification_enum,
            nullable=False,
            server_default=sa.text("'unverified'"),
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Numeric(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index(
        "idx_brand_channel_identities_channel_external_id",
        "brand_channel_identities",
        ["channel", "external_id"],
    )
    op.create_index(
        "idx_brand_channel_identities_brand_channel",
        "brand_channel_identities",
        ["brand_id", "channel"],
    )

    op.create_table(
        "research_runs",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", uuid, sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("brand_discovery_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ads_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ads_context_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_research_runs_org_client", "research_runs", ["org_id", "client_id"])
    op.create_index("idx_research_runs_campaign", "research_runs", ["campaign_id"])

    op.create_table(
        "research_run_brands",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("research_run_id", uuid, sa.ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand_id", uuid, sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", brand_role_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("research_run_id", "brand_id", name="uq_run_brand"),
    )

    op.create_table(
        "ad_ingest_runs",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("research_run_id", uuid, sa.ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "brand_channel_identity_id",
            uuid,
            sa.ForeignKey("brand_channel_identities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", ad_channel_enum, nullable=False),
        sa.Column("requested_url", sa.Text(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=False, server_default=sa.text("'APIFY'")),
        sa.Column("provider_actor_id", sa.Text(), nullable=True),
        sa.Column("provider_run_id", sa.Text(), nullable=True),
        sa.Column("provider_dataset_id", sa.Text(), nullable=True),
        sa.Column("status", ad_ingest_status_enum, nullable=False, server_default=sa.text("'RUNNING'")),
        sa.Column("is_partial", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("results_limit", sa.Integer(), nullable=True),
        sa.Column("items_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "ads",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("brand_id", uuid, sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "brand_channel_identity_id",
            uuid,
            sa.ForeignKey("brand_channel_identities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", ad_channel_enum, nullable=False),
        sa.Column("external_ad_id", sa.Text(), nullable=False),
        sa.Column("ad_status", ad_status_enum, nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("started_running_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_running_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("headline", sa.Text(), nullable=True),
        sa.Column("cta_type", sa.Text(), nullable=True),
        sa.Column("cta_text", sa.Text(), nullable=True),
        sa.Column("landing_url", sa.Text(), nullable=True),
        sa.Column("destination_domain", postgresql.CITEXT(), nullable=True),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("channel", "external_ad_id", name="uq_ads_channel_external_id"),
    )
    op.create_index("idx_ads_brand_channel_identity", "ads", ["brand_channel_identity_id"])
    op.create_index("idx_ads_brand", "ads", ["brand_id"])
    op.create_index("idx_ads_last_seen", "ads", ["last_seen_at"])

    op.create_table(
        "media_assets",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("channel", ad_channel_enum, nullable=False),
        sa.Column("asset_type", media_asset_type_enum, nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("stored_url", sa.Text(), nullable=True),
        sa.Column("sha256", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index(
        "uq_media_assets_sha256",
        "media_assets",
        ["sha256"],
        unique=True,
        postgresql_where=sa.text("sha256 IS NOT NULL"),
    )
    op.create_index(
        "uq_media_assets_channel_source_url",
        "media_assets",
        ["channel", "source_url"],
        unique=True,
        postgresql_where=sa.text("source_url IS NOT NULL"),
    )

    op.create_table(
        "ad_asset_links",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("ad_id", uuid, sa.ForeignKey("ads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_asset_id", uuid, sa.ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("ad_id", "media_asset_id", name="uq_ad_media_link"),
    )


def downgrade() -> None:
    op.drop_table("ad_asset_links")
    op.drop_index("uq_media_assets_channel_source_url", table_name="media_assets")
    op.drop_index("uq_media_assets_sha256", table_name="media_assets")
    op.drop_table("media_assets")
    op.drop_index("idx_ads_last_seen", table_name="ads")
    op.drop_index("idx_ads_brand", table_name="ads")
    op.drop_index("idx_ads_brand_channel_identity", table_name="ads")
    op.drop_table("ads")
    op.drop_table("ad_ingest_runs")
    op.drop_table("research_run_brands")
    op.drop_index("idx_research_runs_campaign", table_name="research_runs")
    op.drop_index("idx_research_runs_org_client", table_name="research_runs")
    op.drop_table("research_runs")
    op.drop_index("idx_brand_channel_identities_brand_channel", table_name="brand_channel_identities")
    op.drop_index(
        "idx_brand_channel_identities_channel_external_id", table_name="brand_channel_identities"
    )
    op.drop_table("brand_channel_identities")
    op.drop_index("uq_brands_org_normalized_name", table_name="brands")
    op.drop_index("uq_brands_org_domain", table_name="brands")
    op.drop_table("brands")

    op.execute("DROP TYPE media_asset_type;")
    op.execute("DROP TYPE ad_status;")
    op.execute("DROP TYPE ad_ingest_status;")
    op.execute("DROP TYPE brand_channel_verification_status;")
    op.execute("DROP TYPE brand_role;")
    op.execute("DROP TYPE ad_channel;")
