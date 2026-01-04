"""Add ad_creatives deduplication layer"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0006_ad_creatives"
down_revision = "0005_deep_research_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    ad_channel_enum = postgresql.ENUM(name="ad_channel", create_type=False)
    jsonb = postgresql.JSONB(astext_type=sa.Text())

    op.create_table(
        "ad_creatives",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand_id", uuid, sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", ad_channel_enum, nullable=False),
        sa.Column("fingerprint_algo", sa.Text(), nullable=False),
        sa.Column("creative_fingerprint", sa.Text(), nullable=False),
        sa.Column(
            "primary_media_asset_id",
            uuid,
            sa.ForeignKey("media_assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("media_fingerprint", sa.Text(), nullable=True),
        sa.Column("copy_fingerprint", sa.Text(), nullable=True),
        sa.Column("metadata", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint(
            "org_id",
            "brand_id",
            "channel",
            "fingerprint_algo",
            "creative_fingerprint",
            name="uq_ad_creatives_fingerprint",
        ),
    )
    op.create_index("idx_ad_creatives_org_brand", "ad_creatives", ["org_id", "brand_id"])
    op.create_index(
        "idx_ad_creatives_org_brand_media_fp",
        "ad_creatives",
        ["org_id", "brand_id", "media_fingerprint"],
        postgresql_where=sa.text("media_fingerprint IS NOT NULL"),
    )
    op.create_index(
        "idx_ad_creatives_org_brand_copy_fp",
        "ad_creatives",
        ["org_id", "brand_id", "copy_fingerprint"],
        postgresql_where=sa.text("copy_fingerprint IS NOT NULL"),
    )
    op.create_index(
        "idx_ad_creatives_org_creative_fp",
        "ad_creatives",
        ["org_id", "creative_fingerprint"],
    )

    op.create_table(
        "ad_creative_memberships",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creative_id", uuid, sa.ForeignKey("ad_creatives.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ad_id", uuid, sa.ForeignKey("ads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("ad_id", name="uq_ad_creative_memberships_ad"),
        sa.UniqueConstraint("creative_id", "ad_id", name="uq_ad_creative_memberships_creative_ad"),
    )
    op.create_index("idx_ad_creative_memberships_creative", "ad_creative_memberships", ["creative_id"])
    op.create_index("idx_ad_creative_memberships_ad", "ad_creative_memberships", ["ad_id"])


def downgrade() -> None:
    op.drop_index("idx_ad_creative_memberships_ad", table_name="ad_creative_memberships")
    op.drop_index("idx_ad_creative_memberships_creative", table_name="ad_creative_memberships")
    op.drop_table("ad_creative_memberships")
    op.drop_index("idx_ad_creatives_org_creative_fp", table_name="ad_creatives")
    op.drop_index("idx_ad_creatives_org_brand_copy_fp", table_name="ad_creatives")
    op.drop_index("idx_ad_creatives_org_brand_media_fp", table_name="ad_creatives")
    op.drop_index("idx_ad_creatives_org_brand", table_name="ad_creatives")
    op.drop_table("ad_creatives")
