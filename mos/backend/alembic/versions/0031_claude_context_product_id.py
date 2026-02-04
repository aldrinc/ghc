"""Add product_id to claude_context_files."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0031_claude_context_product_id"
down_revision = "0030_campaign_product_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.add_column(
        "claude_context_files",
        sa.Column("product_id", uuid, nullable=True),
    )
    op.create_foreign_key(
        "fk_claude_context_files_product_id",
        "claude_context_files",
        "products",
        ["product_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_claude_ctx_product", "claude_context_files", ["product_id"])
    op.drop_constraint("uq_claude_context_workspace_doc_hash", "claude_context_files", type_="unique")
    op.create_unique_constraint(
        "uq_claude_context_workspace_doc_hash",
        "claude_context_files",
        ["org_id", "idea_workspace_id", "product_id", "doc_key", "sha256"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_claude_context_workspace_doc_hash", "claude_context_files", type_="unique")
    op.create_unique_constraint(
        "uq_claude_context_workspace_doc_hash",
        "claude_context_files",
        ["org_id", "idea_workspace_id", "doc_key", "sha256"],
    )
    op.drop_index("idx_claude_ctx_product", table_name="claude_context_files")
    op.drop_constraint("fk_claude_context_files_product_id", "claude_context_files", type_="foreignkey")
    op.drop_column("claude_context_files", "product_id")
