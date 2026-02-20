"""Merge 0048 funnel/runtime and variant-sync heads.

Revision ID: 0049_merge_0048_heads
Revises: 0048_funnel_runtime_bundle_artifact, 0048_variant_shopify_sync_status
Create Date: 2026-02-19 12:00:00.000000
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "0049_merge_0048_heads"
down_revision = ("0048_funnel_runtime_bundle_artifact", "0048_variant_shopify_sync_status")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
