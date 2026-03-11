"""Persist selected Shopify storefront/custom domain per client/user."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0056_client_shopify_storefront_domain"
down_revision = "0055_client_shopify_storefront_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_columns = {
        str(column.get("name", "")).strip().lower()
        for column in sa.inspect(bind).get_columns("client_user_preferences")
    }
    if "selected_shop_storefront_domain" in existing_columns:
        return

    op.add_column(
        "client_user_preferences",
        sa.Column("selected_shop_storefront_domain", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    existing_columns = {
        str(column.get("name", "")).strip().lower()
        for column in sa.inspect(bind).get_columns("client_user_preferences")
    }
    if "selected_shop_storefront_domain" not in existing_columns:
        return
    op.drop_column("client_user_preferences", "selected_shop_storefront_domain")
