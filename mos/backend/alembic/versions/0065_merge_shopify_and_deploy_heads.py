"""merge shopify credentials and workspace deploy domain heads

Revision ID: 0065_merge_shopify_and_deploy_heads
Revises: 0057_client_shopify_app_credentials, 0064_workspace_scoped_deploy_domains
Create Date: 2026-03-18 12:50:00.000000
"""

from __future__ import annotations


revision = "0065_merge_shopify_and_deploy_heads"
down_revision = (
    "0057_client_shopify_app_credentials",
    "0064_workspace_scoped_deploy_domains",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
