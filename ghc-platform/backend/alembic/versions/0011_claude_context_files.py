"""Add Claude context file registry"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0011_claude_context_files"
down_revision = "0010_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    status_enum = sa.Enum("ready", "failed", "deleted", name="claude_context_file_status")
    status_enum.create(op.get_bind(), checkfirst=True)
    status_enum_no_create = postgresql.ENUM(
        "ready",
        "failed",
        "deleted",
        name="claude_context_file_status",
        create_type=False,
    )

    op.create_table(
        "claude_context_files",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idea_workspace_id", sa.Text(), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("campaign_id", uuid, sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("doc_key", sa.Text(), nullable=False),
        sa.Column("doc_title", sa.Text(), nullable=True),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("step_key", sa.Text(), nullable=True),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("claude_file_id", sa.Text(), nullable=True),
        sa.Column("filename", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("drive_doc_id", sa.Text(), nullable=True),
        sa.Column("drive_url", sa.Text(), nullable=True),
        sa.Column("status", status_enum_no_create, nullable=False, server_default=sa.text("'ready'")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint(
            "org_id",
            "idea_workspace_id",
            "doc_key",
            "sha256",
            name="uq_claude_context_workspace_doc_hash",
        ),
    )
    op.create_index(
        "idx_claude_ctx_org_workspace",
        "claude_context_files",
        ["org_id", "idea_workspace_id"],
    )
    op.create_index("idx_claude_ctx_client", "claude_context_files", ["client_id"])
    op.create_index("idx_claude_ctx_campaign", "claude_context_files", ["campaign_id"])
    op.create_index("idx_claude_ctx_doc_key", "claude_context_files", ["doc_key"])


def downgrade() -> None:
    op.drop_index("idx_claude_ctx_doc_key", table_name="claude_context_files")
    op.drop_index("idx_claude_ctx_campaign", table_name="claude_context_files")
    op.drop_index("idx_claude_ctx_client", table_name="claude_context_files")
    op.drop_index("idx_claude_ctx_org_workspace", table_name="claude_context_files")
    op.drop_table("claude_context_files")
    status_enum = sa.Enum(
        "ready",
        "failed",
        "deleted",
        name="claude_context_file_status",
        create_type=False,
    )
    status_enum.drop(op.get_bind(), checkfirst=True)
