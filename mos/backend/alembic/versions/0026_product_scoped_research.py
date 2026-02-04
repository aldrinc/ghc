"""Add product scoping to onboarding/research artifacts."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0026_product_scoped_research"
down_revision = "0025_funnel_experiment_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    op.add_column("research_runs", sa.Column("product_id", uuid, nullable=True))
    op.create_foreign_key(
        "fk_research_runs_product_id",
        "research_runs",
        "products",
        ["product_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_research_runs_product", "research_runs", ["product_id"])


def downgrade() -> None:
    op.drop_index("idx_research_runs_product", table_name="research_runs")
    op.drop_constraint("fk_research_runs_product_id", "research_runs", type_="foreignkey")
    op.drop_column("research_runs", "product_id")
