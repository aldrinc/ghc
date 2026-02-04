"""Add generic jobs table for background processing"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0010_jobs"
down_revision = "0009_teardown_assertions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    jsonb = postgresql.JSONB(astext_type=sa.Text())

    op.create_table(
        "jobs",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=True),
        sa.Column(
            "research_run_id",
            uuid,
            sa.ForeignKey("research_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("job_type", sa.Text(), nullable=False),
        sa.Column("subject_type", sa.Text(), nullable=False),
        sa.Column("subject_id", uuid, nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("dedupe_key", sa.Text(), nullable=True),
        sa.Column("input", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("output", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("raw_output_text", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )

    op.create_index(
        "uq_jobs_dedupe_key",
        "jobs",
        ["dedupe_key"],
        unique=True,
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
    )
    op.create_index("idx_jobs_type_status", "jobs", ["job_type", "status"])
    op.create_index("idx_jobs_subject", "jobs", ["subject_type", "subject_id"])
    op.create_index("idx_jobs_research_run", "jobs", ["research_run_id"])


def downgrade() -> None:
    op.drop_index("idx_jobs_research_run", table_name="jobs")
    op.drop_index("idx_jobs_subject", table_name="jobs")
    op.drop_index("idx_jobs_type_status", table_name="jobs")
    op.drop_index("uq_jobs_dedupe_key", table_name="jobs")
    op.drop_table("jobs")

