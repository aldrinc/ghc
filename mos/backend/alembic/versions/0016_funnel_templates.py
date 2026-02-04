"""Add funnel page template id"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0016_funnel_templates"
down_revision = "0015_funnels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("funnel_pages", sa.Column("template_id", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("funnel_pages", "template_id")
