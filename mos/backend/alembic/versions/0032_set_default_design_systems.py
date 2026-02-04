"""Set client defaults to first design system."""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0032_set_default_design_systems"
down_revision = "0031_claude_context_product_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE clients AS c
        SET design_system_id = ds.id
        FROM (
            SELECT DISTINCT ON (client_id) client_id, id
            FROM design_systems
            WHERE client_id IS NOT NULL
            ORDER BY client_id, created_at ASC, id ASC
        ) AS ds
        WHERE c.design_system_id IS NULL
          AND c.id = ds.client_id
        """
    )


def downgrade() -> None:
    pass
