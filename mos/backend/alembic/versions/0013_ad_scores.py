"""Add ad_scores table"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0013_ad_scores"
down_revision = "0012_ad_facts_and_brand_prefs"
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

    op.create_table(
        "ad_scores",
        sa.Column("ad_id", uuid, sa.ForeignKey("ads.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand_id", uuid, sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", ad_channel_enum, nullable=False),
        sa.Column("score_version", sa.Text(), nullable=False, server_default=sa.text("'v1'")),
        sa.Column("performance_score", sa.Integer(), nullable=True),
        sa.Column("performance_stars", sa.Integer(), nullable=True),
        sa.Column("winning_score", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Numeric(), nullable=True),
        sa.Column("score_breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_ad_scores_org", "ad_scores", ["org_id"])
    op.create_index("idx_ad_scores_brand", "ad_scores", ["brand_id"])
    op.create_index("idx_ad_scores_channel", "ad_scores", ["channel"])


def downgrade() -> None:
    op.drop_index("idx_ad_scores_channel", table_name="ad_scores")
    op.drop_index("idx_ad_scores_brand", table_name="ad_scores")
    op.drop_index("idx_ad_scores_org", table_name="ad_scores")
    op.drop_table("ad_scores")
