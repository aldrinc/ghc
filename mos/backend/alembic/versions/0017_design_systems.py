"""Add design systems and overrides"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0017_design_systems"
down_revision = "0016_funnel_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    jsonb = postgresql.JSONB(astext_type=sa.Text())

    op.create_table(
        "design_systems",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("tokens", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_design_systems_org_client", "design_systems", ["org_id", "client_id"])

    op.add_column(
        "clients",
        sa.Column("design_system_id", uuid, sa.ForeignKey("design_systems.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "funnels",
        sa.Column("design_system_id", uuid, sa.ForeignKey("design_systems.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "funnel_pages",
        sa.Column("design_system_id", uuid, sa.ForeignKey("design_systems.id", ondelete="SET NULL"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("funnel_pages", "design_system_id")
    op.drop_column("funnels", "design_system_id")
    op.drop_column("clients", "design_system_id")
    op.drop_index("idx_design_systems_org_client", table_name="design_systems")
    op.drop_table("design_systems")
