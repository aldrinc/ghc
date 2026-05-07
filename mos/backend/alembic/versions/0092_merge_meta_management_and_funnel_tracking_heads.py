"""merge meta management and funnel tracking heads

Revision ID: 0092_merge_meta_management_and_funnel_tracking_heads
Revises: 0089_meta_management_report_artifact, 0091_checkout_redirect_timing_event_types
Create Date: 2026-05-06 17:20:00.000000
"""

from __future__ import annotations


revision = "0092_merge_meta_management_and_funnel_tracking_heads"
down_revision = (
    "0089_meta_management_report_artifact",
    "0091_checkout_redirect_timing_event_types",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
