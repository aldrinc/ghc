"""Add campaign_funnel_generation to workflow_kind enum."""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0034_campaign_funnel_gen"
down_revision = "0033_product_primary_asset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE workflow_kind ADD VALUE IF NOT EXISTS 'campaign_funnel_generation';")


def downgrade() -> None:
    # Enum value removal is not straightforward in Postgres.
    # Leave as a no-op to avoid destructive changes.
    pass
