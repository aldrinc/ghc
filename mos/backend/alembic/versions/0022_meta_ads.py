"""Add Meta Ads integration tables."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0022_meta_ads"
down_revision = "0021_funnel_orders_and_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    jsonb = postgresql.JSONB(astext_type=sa.Text())

    op.create_table(
        "meta_asset_uploads",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", uuid, sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ad_account_id", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=False),
        sa.Column("meta_image_hash", sa.Text(), nullable=True),
        sa.Column("meta_video_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("metadata", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("org_id", "ad_account_id", "asset_id", name="uq_meta_asset_upload_asset"),
        sa.UniqueConstraint("org_id", "ad_account_id", "request_id", name="uq_meta_asset_upload_request"),
    )
    op.create_index(
        "idx_meta_asset_uploads_org_asset", "meta_asset_uploads", ["org_id", "asset_id"]
    )

    op.create_table(
        "meta_ad_creatives",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", uuid, sa.ForeignKey("assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ad_account_id", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("meta_creative_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("object_story_spec", jsonb, nullable=False),
        sa.Column("metadata", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("org_id", "ad_account_id", "request_id", name="uq_meta_ad_creatives_request"),
    )
    op.create_index(
        "idx_meta_ad_creatives_org_asset", "meta_ad_creatives", ["org_id", "asset_id"]
    )

    op.create_table(
        "meta_campaigns",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", uuid, sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ad_account_id", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("meta_campaign_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("metadata", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("org_id", "ad_account_id", "request_id", name="uq_meta_campaigns_request"),
    )
    op.create_index(
        "idx_meta_campaigns_org_campaign", "meta_campaigns", ["org_id", "campaign_id"]
    )

    op.create_table(
        "meta_ad_sets",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", uuid, sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ad_account_id", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("meta_campaign_id", sa.Text(), nullable=False),
        sa.Column("meta_adset_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("metadata", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("org_id", "ad_account_id", "request_id", name="uq_meta_ad_sets_request"),
    )
    op.create_index("idx_meta_ad_sets_org_campaign", "meta_ad_sets", ["org_id", "campaign_id"])
    op.create_index("idx_meta_ad_sets_meta_campaign", "meta_ad_sets", ["meta_campaign_id"])

    op.create_table(
        "meta_ads",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", uuid, sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ad_account_id", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("meta_ad_id", sa.Text(), nullable=False),
        sa.Column("meta_adset_id", sa.Text(), nullable=False),
        sa.Column("meta_creative_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("metadata", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("org_id", "ad_account_id", "request_id", name="uq_meta_ads_request"),
    )
    op.create_index("idx_meta_ads_org_campaign", "meta_ads", ["org_id", "campaign_id"])
    op.create_index("idx_meta_ads_meta_adset", "meta_ads", ["meta_adset_id"])
    op.create_index("idx_meta_ads_meta_creative", "meta_ads", ["meta_creative_id"])


def downgrade() -> None:
    op.drop_index("idx_meta_ads_meta_creative", table_name="meta_ads")
    op.drop_index("idx_meta_ads_meta_adset", table_name="meta_ads")
    op.drop_index("idx_meta_ads_org_campaign", table_name="meta_ads")
    op.drop_table("meta_ads")

    op.drop_index("idx_meta_ad_sets_meta_campaign", table_name="meta_ad_sets")
    op.drop_index("idx_meta_ad_sets_org_campaign", table_name="meta_ad_sets")
    op.drop_table("meta_ad_sets")

    op.drop_index("idx_meta_campaigns_org_campaign", table_name="meta_campaigns")
    op.drop_table("meta_campaigns")

    op.drop_index("idx_meta_ad_creatives_org_asset", table_name="meta_ad_creatives")
    op.drop_table("meta_ad_creatives")

    op.drop_index("idx_meta_asset_uploads_org_asset", table_name="meta_asset_uploads")
    op.drop_table("meta_asset_uploads")
