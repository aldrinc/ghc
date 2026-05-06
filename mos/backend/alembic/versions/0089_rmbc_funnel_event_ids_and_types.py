"""Add RMBC funnel event IDs and event types

Revision ID: 0089_rmbc_funnel_event_ids_and_types
Revises: 0088_client_posthog_settings
Create Date: 2026-05-02 15:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0089_rmbc_funnel_event_ids_and_types"
down_revision = "0088_client_posthog_settings"
branch_labels = None
depends_on = None

_EVENT_TYPES = (
    "ad_click",
    "presell_page_view",
    "offer_page_view",
    "qualified_session",
    "scroll_depth",
    "section_view",
    "proof_view",
    "cta_view",
    "offer_stack_view",
    "value_stack_view",
    "price_reveal_view",
    "selector_interaction",
    "subscription_selected",
    "guarantee_view",
    "trust_element_view",
    "product_detail_interaction",
    "purchase",
    "refund",
    "chargeback",
    "support_ticket",
    "tracking_chain_check",
)


def upgrade() -> None:
    for event_type in _EVENT_TYPES:
        op.execute(f"ALTER TYPE funnel_event_type ADD VALUE IF NOT EXISTS '{event_type}'")

    op.add_column("funnel_events", sa.Column("event_id", sa.Text(), nullable=True))
    op.create_index(
        "uq_funnel_events_event_id",
        "funnel_events",
        ["event_id"],
        unique=True,
        postgresql_where=sa.text("event_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_funnel_events_event_id", table_name="funnel_events")
    op.drop_column("funnel_events", "event_id")
