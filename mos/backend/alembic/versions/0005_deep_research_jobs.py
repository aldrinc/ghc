"""Add deep research jobs for background responses"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0005_deep_research_jobs"
down_revision = "0004_brand_ads_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE research_job_status AS ENUM ('created','queued','in_progress','completed','failed','cancelled','incomplete','errored');"
    )

    uuid = postgresql.UUID(as_uuid=True)
    research_job_status_enum = postgresql.ENUM(name="research_job_status", create_type=False)

    op.create_table(
        "deep_research_jobs",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "workflow_run_id",
            uuid,
            sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "onboarding_payload_id",
            uuid,
            sa.ForeignKey("onboarding_payloads.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("temporal_workflow_id", sa.Text(), nullable=True),
        sa.Column("step_key", sa.Text(), nullable=False, server_default=sa.text("'04'")),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("prompt_sha256", sa.Text(), nullable=True),
        sa.Column("use_web_search", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
        sa.Column("response_id", sa.Text(), nullable=True),
        sa.Column(
            "status",
            research_job_status_enum,
            nullable=False,
            server_default=sa.text("'created'"),
        ),
        sa.Column("output_text", sa.Text(), nullable=True),
        sa.Column("full_response_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("incomplete_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_webhook_id", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_deep_research_jobs_response_id",
        "deep_research_jobs",
        ["response_id"],
        unique=True,
        postgresql_where=sa.text("response_id IS NOT NULL"),
    )
    op.create_index(
        "idx_deep_research_jobs_org_client",
        "deep_research_jobs",
        ["org_id", "client_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_deep_research_jobs_org_client", table_name="deep_research_jobs")
    op.drop_index("idx_deep_research_jobs_response_id", table_name="deep_research_jobs")
    op.drop_table("deep_research_jobs")
    op.execute("DROP TYPE research_job_status;")
