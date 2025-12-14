"""Add external_id to orgs"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0002_add_org_external_id"
down_revision = "0001_init_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orgs", sa.Column("external_id", sa.Text(), nullable=True, unique=True))


def downgrade() -> None:
    op.drop_column("orgs", "external_id")
