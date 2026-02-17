"""Add client user preferences for persisting active product selection."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0042_client_user_preferences"
down_revision = "0041_ad_library_page_totals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    op.create_table(
        "client_user_preferences",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_external_id", sa.Text(), nullable=False),
        sa.Column(
            "active_product_id",
            uuid,
            sa.ForeignKey("products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("org_id", "user_external_id", "client_id", name="uq_client_user_pref"),
    )

    op.create_index(
        "idx_client_user_pref_user",
        "client_user_preferences",
        ["org_id", "user_external_id"],
    )
    op.create_index(
        "idx_client_user_pref_client",
        "client_user_preferences",
        ["client_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_client_user_pref_client", table_name="client_user_preferences")
    op.drop_index("idx_client_user_pref_user", table_name="client_user_preferences")
    op.drop_table("client_user_preferences")

