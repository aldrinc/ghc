"""Compatibility revision for legacy client Shopify default shop migration.

Revision ID: 0046_client_shopify_default_shop
Revises: 0045_offer_bonuses_and_shopify_product_gid
Create Date: 2026-02-19 00:00:00.000000

This revision existed in a previous deployment lineage. It is kept as a
no-op so databases stamped/applied at this revision can continue upgrading.
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "0046_client_shopify_default_shop"
down_revision = "0045_offer_bonuses_and_shopify_product_gid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
