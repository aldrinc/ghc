"""Add quiz funnel event types

Revision ID: 0090_quiz_funnel_event_types
Revises: 0089_rmbc_funnel_event_ids_and_types
Create Date: 2026-05-05 09:00:00.000000
"""

from __future__ import annotations

from alembic import op

revision = "0090_quiz_funnel_event_types"
down_revision = "0089_rmbc_funnel_event_ids_and_types"
branch_labels = None
depends_on = None

_EVENT_TYPES = (
    "quiz_lead_viewed",
    "quiz_question_viewed",
    "quiz_option_presented",
    "quiz_option_selected",
    "quiz_option_deselected",
    "quiz_question_submitted",
    "quiz_completed",
    "quiz_result_viewed",
    "quiz_mechanism_viewed",
    "quiz_proof_viewed",
    "quiz_recommendation_viewed",
    "quiz_cta_viewed",
)


def upgrade() -> None:
    for event_type in _EVENT_TYPES:
        op.execute(f"ALTER TYPE funnel_event_type ADD VALUE IF NOT EXISTS '{event_type}'")


def downgrade() -> None:
    pass
