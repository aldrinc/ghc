"""No-op migration reserved for funnel experiment linking."""
from __future__ import annotations

# This revision exists to satisfy a historical merge head.

# revision identifiers, used by Alembic.
revision = "0025_funnel_experiment_link"
down_revision = "0024_campaign_channels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
