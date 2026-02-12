"""Add agent_runs tables for tool-based objective runner traces."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0038_agent_runs"
down_revision = "0037_research_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    run_status_enum = sa.Enum(
        "running",
        "completed",
        "failed",
        "cancelled",
        name="agent_run_status",
    )
    run_status_enum.create(op.get_bind(), checkfirst=True)
    run_status = postgresql.ENUM(
        "running",
        "completed",
        "failed",
        "cancelled",
        name="agent_run_status",
        create_type=False,
    )

    tool_status_enum = sa.Enum(
        "running",
        "completed",
        "failed",
        "cancelled",
        name="agent_tool_call_status",
    )
    tool_status_enum.create(op.get_bind(), checkfirst=True)
    tool_status = postgresql.ENUM(
        "running",
        "completed",
        "failed",
        "cancelled",
        name="agent_tool_call_status",
        create_type=False,
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("funnel_id", uuid, sa.ForeignKey("funnels.id", ondelete="SET NULL"), nullable=True),
        sa.Column("page_id", uuid, sa.ForeignKey("funnel_pages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("objective_type", sa.Text(), nullable=False),
        sa.Column("status", run_status, nullable=False, server_default=sa.text("'running'")),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("ruleset_version", sa.Text(), nullable=True),
        sa.Column("inputs_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("outputs_json", postgresql.JSONB(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("idx_agent_runs_org_created_at", "agent_runs", ["org_id", "started_at"])
    op.create_index("idx_agent_runs_org_funnel", "agent_runs", ["org_id", "funnel_id"])
    op.create_index("idx_agent_runs_org_page", "agent_runs", ["org_id", "page_id"])

    op.create_table(
        "agent_tool_calls",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("run_id", uuid, sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("status", tool_status, nullable=False, server_default=sa.text("'running'")),
        sa.Column("args_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("result_json", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
    )
    op.create_index("idx_agent_tool_calls_run_seq", "agent_tool_calls", ["run_id", "seq"])
    op.create_index("idx_agent_tool_calls_run_tool", "agent_tool_calls", ["run_id", "tool_name"])

    op.create_table(
        "agent_artifacts",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("run_id", uuid, sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=True),
        sa.Column("data_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_agent_artifacts_run_kind", "agent_artifacts", ["run_id", "kind"])


def downgrade() -> None:
    op.drop_index("idx_agent_artifacts_run_kind", table_name="agent_artifacts")
    op.drop_table("agent_artifacts")

    op.drop_index("idx_agent_tool_calls_run_tool", table_name="agent_tool_calls")
    op.drop_index("idx_agent_tool_calls_run_seq", table_name="agent_tool_calls")
    op.drop_table("agent_tool_calls")

    op.drop_index("idx_agent_runs_org_page", table_name="agent_runs")
    op.drop_index("idx_agent_runs_org_funnel", table_name="agent_runs")
    op.drop_index("idx_agent_runs_org_created_at", table_name="agent_runs")
    op.drop_table("agent_runs")

    tool_status_enum = sa.Enum(
        "running",
        "completed",
        "failed",
        "cancelled",
        name="agent_tool_call_status",
        create_type=False,
    )
    tool_status_enum.drop(op.get_bind(), checkfirst=True)

    run_status_enum = sa.Enum(
        "running",
        "completed",
        "failed",
        "cancelled",
        name="agent_run_status",
        create_type=False,
    )
    run_status_enum.drop(op.get_bind(), checkfirst=True)

