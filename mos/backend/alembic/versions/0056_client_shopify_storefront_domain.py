"""Persist selected Shopify storefront/custom domain per client/user."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0056_client_shopify_storefront_domain"
down_revision = "0055_paid_ads_qa_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "client_user_preferences",
        sa.Column("selected_shop_storefront_domain", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("client_user_preferences", "selected_shop_storefront_domain")
