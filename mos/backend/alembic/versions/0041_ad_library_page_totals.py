"""Add ad library page totals for competitor strength ranking."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0041_ad_library_page_totals"
down_revision = "0040_research_artifact_titles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    ad_channel_enum = postgresql.ENUM(name="ad_channel", create_type=False)

    op.create_table(
        "ad_library_page_totals",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "research_run_id",
            uuid,
            sa.ForeignKey("research_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("brand_id", uuid, sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "brand_channel_identity_id",
            uuid,
            sa.ForeignKey("brand_channel_identities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", ad_channel_enum, nullable=False),
        sa.Column("query_key", sa.Text(), nullable=False),
        sa.Column("active_status", sa.Text(), nullable=True),
        sa.Column("input_url", sa.Text(), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("page_id", sa.Text(), nullable=True),
        sa.Column("page_name", sa.Text(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=False, server_default=sa.text("'APIFY'")),
        sa.Column("provider_actor_id", sa.Text(), nullable=True),
        sa.Column("provider_run_id", sa.Text(), nullable=True),
        sa.Column("provider_dataset_id", sa.Text(), nullable=True),
        sa.Column("actor_input", postgresql.JSONB(), nullable=True),
        sa.Column("raw_result", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint(
            "research_run_id",
            "brand_channel_identity_id",
            "query_key",
            name="uq_ad_library_page_totals_run_identity_query",
        ),
    )

    op.create_index("idx_ad_library_page_totals_org", "ad_library_page_totals", ["org_id"])
    op.create_index("idx_ad_library_page_totals_run", "ad_library_page_totals", ["research_run_id"])
    op.create_index("idx_ad_library_page_totals_brand", "ad_library_page_totals", ["brand_id"])
    op.create_index("idx_ad_library_page_totals_channel", "ad_library_page_totals", ["channel"])


def downgrade() -> None:
    op.drop_index("idx_ad_library_page_totals_channel", table_name="ad_library_page_totals")
    op.drop_index("idx_ad_library_page_totals_brand", table_name="ad_library_page_totals")
    op.drop_index("idx_ad_library_page_totals_run", table_name="ad_library_page_totals")
    op.drop_index("idx_ad_library_page_totals_org", table_name="ad_library_page_totals")
    op.drop_table("ad_library_page_totals")
