"""Add funnel_pages.review_status to support agent-ready review flow."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0039_funnel_page_review_status"
down_revision = "0038_agent_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    status_enum = sa.Enum("draft", "review", "approved", name="funnel_page_review_status")
    status_enum.create(op.get_bind(), checkfirst=True)
    status_no_create = postgresql.ENUM(
        "draft",
        "review",
        "approved",
        name="funnel_page_review_status",
        create_type=False,
    )

    op.add_column(
        "funnel_pages",
        sa.Column("review_status", status_no_create, nullable=False, server_default=sa.text("'draft'")),
    )


def downgrade() -> None:
    op.drop_column("funnel_pages", "review_status")
    status_enum = sa.Enum("draft", "review", "approved", name="funnel_page_review_status", create_type=False)
    status_enum.drop(op.get_bind(), checkfirst=True)

