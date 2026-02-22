"""Add org_deploy_domains for persisted deploy domain configuration.

Revision ID: 0050_org_deploy_domains
Revises: 0049_merge_0048_heads
Create Date: 2026-02-22 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0050_org_deploy_domains"
down_revision = "0049_merge_0048_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    op.create_table(
        "org_deploy_domains",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hostname", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("org_id", "hostname", name="uq_org_deploy_domains_org_hostname"),
    )
    op.create_index(
        "idx_org_deploy_domains_org",
        "org_deploy_domains",
        ["org_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_org_deploy_domains_org", table_name="org_deploy_domains")
    op.drop_table("org_deploy_domains")
