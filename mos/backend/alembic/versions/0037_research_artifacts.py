"""Add research_artifacts table for incremental doc availability."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0037_research_artifacts"
down_revision = "0036_funnel_page_next_page"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "workflow_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_key", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("doc_id", sa.Text(), nullable=False),
        sa.Column("doc_url", sa.Text(), nullable=False),
        sa.Column("prompt_sha256", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("org_id", "workflow_run_id", "step_key", name="uq_research_artifacts_run_step"),
    )
    op.create_index(
        "idx_research_artifacts_run",
        "research_artifacts",
        ["org_id", "workflow_run_id"],
    )
    op.create_index(
        "idx_research_artifacts_created_at",
        "research_artifacts",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_research_artifacts_created_at", table_name="research_artifacts")
    op.drop_index("idx_research_artifacts_run", table_name="research_artifacts")
    op.drop_table("research_artifacts")

