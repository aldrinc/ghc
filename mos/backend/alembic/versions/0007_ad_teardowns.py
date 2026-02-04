"""Add ad_teardowns table"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0007_ad_teardowns"
down_revision = "0006_ad_creatives"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    jsonb = postgresql.JSONB(astext_type=sa.Text())

    op.create_table(
        "ad_teardowns",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("creative_id", uuid, sa.ForeignKey("ad_creatives.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("campaign_id", uuid, sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "research_run_id",
            uuid,
            sa.ForeignKey("research_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_by_user_id", uuid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("funnel_stage", sa.Text(), nullable=True),
        sa.Column("one_liner", sa.Text(), nullable=True),
        sa.Column("algorithmic_thesis", sa.Text(), nullable=True),
        sa.Column("hook_score", sa.Integer(), nullable=True),
        sa.Column("raw_payload", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_canonical", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_ad_teardowns_creative", "ad_teardowns", ["creative_id"])
    op.create_index("idx_ad_teardowns_org_client", "ad_teardowns", ["org_id", "client_id"])
    op.create_index(
        "idx_ad_teardowns_raw_payload_gin",
        "ad_teardowns",
        ["raw_payload"],
        postgresql_using="gin",
    )
    op.create_index(
        "uq_ad_teardowns_org_creative_canonical",
        "ad_teardowns",
        ["org_id", "creative_id"],
        unique=True,
        postgresql_where=sa.text("is_canonical = true"),
    )


def downgrade() -> None:
    op.drop_index("uq_ad_teardowns_org_creative_canonical", table_name="ad_teardowns")
    op.drop_index("idx_ad_teardowns_raw_payload_gin", table_name="ad_teardowns")
    op.drop_index("idx_ad_teardowns_org_client", table_name="ad_teardowns")
    op.drop_index("idx_ad_teardowns_creative", table_name="ad_teardowns")
    op.drop_table("ad_teardowns")
