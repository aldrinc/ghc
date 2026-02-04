"""Add experiment_spec_id to funnels."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0026_funnel_experiment_spec"
down_revision = "0025_funnel_experiment_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("funnels", sa.Column("experiment_spec_id", sa.Text(), nullable=True))
    op.create_index("idx_funnels_experiment_spec", "funnels", ["experiment_spec_id"])


def downgrade() -> None:
    op.drop_index("idx_funnels_experiment_spec", table_name="funnels")
    op.drop_column("funnels", "experiment_spec_id")
