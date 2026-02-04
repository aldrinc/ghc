"""Add Meta creative/ad set spec tables."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0023_meta_specs"
down_revision = "0022_meta_ads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    jsonb = postgresql.JSONB(astext_type=sa.Text())

    op.create_table(
        "meta_creative_specs",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", uuid, sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("experiment_id", uuid, sa.ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("asset_id", uuid, sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("primary_text", sa.Text(), nullable=True),
        sa.Column("headline", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("call_to_action_type", sa.Text(), nullable=True),
        sa.Column("destination_url", sa.Text(), nullable=True),
        sa.Column("page_id", sa.Text(), nullable=True),
        sa.Column("instagram_actor_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("metadata", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("org_id", "asset_id", name="uq_meta_creative_specs_org_asset"),
    )
    op.create_index(
        "idx_meta_creative_specs_org_campaign", "meta_creative_specs", ["org_id", "campaign_id"]
    )
    op.create_index(
        "idx_meta_creative_specs_org_experiment", "meta_creative_specs", ["org_id", "experiment_id"]
    )

    op.create_table(
        "meta_adset_specs",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", uuid, sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("experiment_id", uuid, sa.ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("optimization_goal", sa.Text(), nullable=True),
        sa.Column("billing_event", sa.Text(), nullable=True),
        sa.Column("targeting", jsonb, nullable=True),
        sa.Column("placements", jsonb, nullable=True),
        sa.Column("daily_budget", sa.Integer(), nullable=True),
        sa.Column("lifetime_budget", sa.Integer(), nullable=True),
        sa.Column("bid_amount", sa.Integer(), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promoted_object", jsonb, nullable=True),
        sa.Column("conversion_domain", sa.Text(), nullable=True),
        sa.Column("metadata", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index(
        "idx_meta_adset_specs_org_campaign", "meta_adset_specs", ["org_id", "campaign_id"]
    )
    op.create_index(
        "idx_meta_adset_specs_org_experiment", "meta_adset_specs", ["org_id", "experiment_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_meta_adset_specs_org_experiment", table_name="meta_adset_specs")
    op.drop_index("idx_meta_adset_specs_org_campaign", table_name="meta_adset_specs")
    op.drop_table("meta_adset_specs")

    op.drop_index("idx_meta_creative_specs_org_experiment", table_name="meta_creative_specs")
    op.drop_index("idx_meta_creative_specs_org_campaign", table_name="meta_creative_specs")
    op.drop_table("meta_creative_specs")
