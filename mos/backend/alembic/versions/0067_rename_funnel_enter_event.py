"""rename funnel_enter event label

Revision ID: 0067_rename_funnel_enter_event
Revises: 0066_explicit_funnel_stage_events
Create Date: 2026-03-18 18:40:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "0067_rename_funnel_enter_event"
down_revision = "0066_explicit_funnel_stage_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'funnel_event_type' AND e.enumlabel = 'funnel_enter'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'funnel_event_type' AND e.enumlabel = 'Entered Funnel'
                ) THEN
                    ALTER TYPE funnel_event_type RENAME VALUE 'funnel_enter' TO 'Entered Funnel';
                END IF;
            END
            $$;
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'funnel_event_type' AND e.enumlabel = 'Entered Funnel'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'funnel_event_type' AND e.enumlabel = 'funnel_enter'
                ) THEN
                    ALTER TYPE funnel_event_type RENAME VALUE 'Entered Funnel' TO 'funnel_enter';
                END IF;
            END
            $$;
            """
        )
