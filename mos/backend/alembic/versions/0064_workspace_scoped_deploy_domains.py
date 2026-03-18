"""Scope deploy domains by workspace.

Revision ID: 0064_workspace_scoped_deploy_domains
Revises: 0063_checkout_started_event_type
Create Date: 2026-03-18 15:20:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0064_workspace_scoped_deploy_domains"
down_revision = "0063_checkout_started_event_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    op.add_column("org_deploy_domains", sa.Column("client_id", uuid, nullable=True))
    op.create_foreign_key(
        "fk_org_deploy_domains_client_id_clients",
        "org_deploy_domains",
        "clients",
        ["client_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "idx_org_deploy_domains_org_client",
        "org_deploy_domains",
        ["org_id", "client_id"],
    )
    op.create_unique_constraint(
        "uq_org_deploy_domains_org_client_hostname",
        "org_deploy_domains",
        ["org_id", "client_id", "hostname"],
    )
    op.drop_constraint("uq_org_deploy_domains_org_hostname", "org_deploy_domains", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_org_deploy_domains_org_hostname",
        "org_deploy_domains",
        ["org_id", "hostname"],
    )
    op.drop_constraint(
        "uq_org_deploy_domains_org_client_hostname",
        "org_deploy_domains",
        type_="unique",
    )
    op.drop_index("idx_org_deploy_domains_org_client", table_name="org_deploy_domains")
    op.drop_constraint(
        "fk_org_deploy_domains_client_id_clients",
        "org_deploy_domains",
        type_="foreignkey",
    )
    op.drop_column("org_deploy_domains", "client_id")
