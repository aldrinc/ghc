"""Add client_compliance_policy_overrides table

Revision ID: 0084_client_compliance_policy_overrides
Revises: 0083_ember_skills_runtime_registry
Create Date: 2026-04-16 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "0084_client_compliance_policy_overrides"
down_revision = "0083_ember_skills_runtime_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_compliance_policy_overrides",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_key", sa.Text(), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_compliance_policy_overrides_org_client",
        "client_compliance_policy_overrides",
        ["org_id", "client_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_compliance_policy_overrides_org_client_page",
        "client_compliance_policy_overrides",
        ["org_id", "client_id", "page_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_compliance_policy_overrides_org_client_page",
        "client_compliance_policy_overrides",
        type_="unique",
    )
    op.drop_index(
        "idx_compliance_policy_overrides_org_client",
        table_name="client_compliance_policy_overrides",
    )
    op.drop_table("client_compliance_policy_overrides")
