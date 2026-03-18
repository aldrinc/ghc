"""Persist generation-scoped Meta publish selections."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0057_meta_publish_selections"
down_revision = "0056_client_shopify_storefront_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    op.create_table(
        "meta_publish_selections",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", uuid, sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", uuid, sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("generation_key", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("decided_by_user_id", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint(
            "org_id",
            "campaign_id",
            "generation_key",
            "asset_id",
            name="uq_meta_publish_selections_org_campaign_generation_asset",
        ),
    )
    op.create_index(
        "idx_meta_publish_selections_org_campaign_generation",
        "meta_publish_selections",
        ["org_id", "campaign_id", "generation_key"],
    )
    op.create_index(
        "idx_meta_publish_selections_org_asset",
        "meta_publish_selections",
        ["org_id", "asset_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_meta_publish_selections_org_asset", table_name="meta_publish_selections")
    op.drop_index("idx_meta_publish_selections_org_campaign_generation", table_name="meta_publish_selections")
    op.drop_table("meta_publish_selections")
