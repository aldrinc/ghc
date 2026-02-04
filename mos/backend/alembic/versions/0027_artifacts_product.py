"""Add product_id to artifacts."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0027_artifacts_product"
down_revision = "0026_funnel_experiment_spec"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.add_column(
        "artifacts",
        sa.Column("product_id", uuid, sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("idx_artifacts_product", "artifacts", ["product_id"])


def downgrade() -> None:
    op.drop_index("idx_artifacts_product", table_name="artifacts")
    op.drop_column("artifacts", "product_id")
