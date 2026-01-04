"""Add ad facts and brand user preferences"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0012_ad_facts_and_brand_prefs"
down_revision = "0011_claude_context_files"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    ad_channel_enum = postgresql.ENUM(
        "META_ADS_LIBRARY",
        "TIKTOK_CREATIVE_CENTER",
        "GOOGLE_ADS_TRANSPARENCY",
        name="ad_channel",
        create_type=False,
    )
    ad_status_enum = postgresql.ENUM("active", "inactive", "unknown", name="ad_status", create_type=False)

    op.create_table(
        "ad_facts",
        sa.Column("ad_id", uuid, sa.ForeignKey("ads.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand_id", uuid, sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", ad_channel_enum, nullable=False),
        sa.Column("status", ad_status_enum, nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("display_format", sa.Text(), nullable=True),
        sa.Column(
            "media_types",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("video_length_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "language_codes",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "country_codes",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("days_active", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_ad_facts_org", "ad_facts", ["org_id"])
    op.create_index("idx_ad_facts_brand", "ad_facts", ["brand_id"])
    op.create_index("idx_ad_facts_channel", "ad_facts", ["channel"])
    op.create_index("idx_ad_facts_status", "ad_facts", ["status"])
    op.create_index("idx_ad_facts_start_date", "ad_facts", ["start_date"])
    op.create_index("idx_ad_facts_days_active", "ad_facts", ["days_active"])
    op.create_index("idx_ad_facts_video_length", "ad_facts", ["video_length_seconds"])
    op.create_index("idx_ad_facts_media_types", "ad_facts", ["media_types"], postgresql_using="gin")
    op.create_index("idx_ad_facts_language_codes", "ad_facts", ["language_codes"], postgresql_using="gin")
    op.create_index("idx_ad_facts_country_codes", "ad_facts", ["country_codes"], postgresql_using="gin")

    op.create_table(
        "brand_user_preferences",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand_id", uuid, sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_external_id", sa.Text(), nullable=False),
        sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("org_id", "user_external_id", "brand_id", name="uq_brand_user_pref"),
    )
    op.create_index(
        "idx_brand_user_pref_user",
        "brand_user_preferences",
        ["org_id", "user_external_id"],
    )
    op.create_index("idx_brand_user_pref_brand", "brand_user_preferences", ["brand_id"])


def downgrade() -> None:
    op.drop_index("idx_brand_user_pref_brand", table_name="brand_user_preferences")
    op.drop_index("idx_brand_user_pref_user", table_name="brand_user_preferences")
    op.drop_table("brand_user_preferences")

    op.drop_index("idx_ad_facts_country_codes", table_name="ad_facts")
    op.drop_index("idx_ad_facts_language_codes", table_name="ad_facts")
    op.drop_index("idx_ad_facts_media_types", table_name="ad_facts")
    op.drop_index("idx_ad_facts_video_length", table_name="ad_facts")
    op.drop_index("idx_ad_facts_days_active", table_name="ad_facts")
    op.drop_index("idx_ad_facts_start_date", table_name="ad_facts")
    op.drop_index("idx_ad_facts_status", table_name="ad_facts")
    op.drop_index("idx_ad_facts_channel", table_name="ad_facts")
    op.drop_index("idx_ad_facts_brand", table_name="ad_facts")
    op.drop_index("idx_ad_facts_org", table_name="ad_facts")
    op.drop_table("ad_facts")
