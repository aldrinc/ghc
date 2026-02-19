"""Persist explicit default Shopify shop selection per client/user."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0046_client_shopify_default_shop"
down_revision = "0045_offer_bonuses_and_shopify_product_gid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("client_user_preferences", sa.Column("selected_shop_domain", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("client_user_preferences", "selected_shop_domain")
