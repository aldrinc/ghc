"""Add campaign_intent to workflow_kind enum."""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0021_campaign_intent_workflow"
down_revision = "0020_price_points"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE workflow_kind ADD VALUE IF NOT EXISTS 'campaign_intent';")


def downgrade() -> None:
    # Enum value removal is not straightforward in Postgres.
    # Leave as a no-op to avoid destructive changes.
    pass
