"""Add product_id to onboarding payloads and workflow runs."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0028_product_id_links"
down_revision = "0027_artifacts_product"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.add_column(
        "onboarding_payloads",
        sa.Column("product_id", uuid, sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("idx_onboarding_payloads_product", "onboarding_payloads", ["product_id"])
    op.add_column(
        "workflow_runs",
        sa.Column("product_id", uuid, sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("idx_workflow_runs_product", "workflow_runs", ["product_id"])


def downgrade() -> None:
    op.drop_index("idx_workflow_runs_product", table_name="workflow_runs")
    op.drop_column("workflow_runs", "product_id")
    op.drop_index("idx_onboarding_payloads_product", table_name="onboarding_payloads")
    op.drop_column("onboarding_payloads", "product_id")
