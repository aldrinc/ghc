"""Add site theme binding mode column

Revision ID: 0081_site_theme_binding_mode
Revises: 0080_site_publications
Create Date: 2026-03-26 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0081_site_theme_binding_mode"
down_revision = "0080_site_publications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create the enum type first (PostgreSQL will auto-create if not exists, but we do it explicitly)
    op.execute(
        "CREATE TYPE site_theme_binding_mode AS ENUM ('standalone', 'workspace_default', 'design_system');"
    )

    # Add theme_binding_mode column with default 'standalone' for new sites
    op.add_column(
        "sites",
        sa.Column(
            "theme_binding_mode",
            sa.Enum(
                "standalone", "workspace_default", "design_system", name="site_theme_binding_mode"
            ),
            nullable=False,
            server_default="standalone",
        ),
    )

    # Backfill existing sites based on their current design_system_id:
    # - if design_system_id is set => theme_binding_mode = 'design_system'
    # - else => theme_binding_mode = 'workspace_default'
    op.execute(
        """
        UPDATE sites
        SET theme_binding_mode = CASE
            WHEN design_system_id IS NOT NULL THEN 'design_system'::site_theme_binding_mode
            ELSE 'workspace_default'::site_theme_binding_mode
        END
        """
    )

    # Remove the server_default after backfill. A follow-up migration restores the
    # steady-state default after the parallel 0081 heads are merged.
    op.alter_column(
        "sites",
        "theme_binding_mode",
        server_default=None,
    )

def downgrade() -> None:
    op.drop_column("sites", "theme_binding_mode")
    op.execute("DROP TYPE site_theme_binding_mode;")
