"""Compatibility revision for legacy storefront-domain migration identifier.

Revision ID: 0055_client_shopify_storefront_domain
Revises: 0055_paid_ads_qa_foundation
Create Date: 2026-03-11 00:00:00.000000
"""

from __future__ import annotations


# revision identifiers, used by Alembic.
revision = "0055_client_shopify_storefront_domain"
down_revision = "0055_paid_ads_qa_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Legacy compatibility placeholder.

    The actual column addition runs in revision 0056_client_shopify_storefront_domain.
    """


def downgrade() -> None:
    """No-op downgrade for legacy compatibility placeholder."""

