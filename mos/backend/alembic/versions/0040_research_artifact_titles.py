"""Backfill research artifact titles and persist them into canon artifact refs.

This migration standardizes titles for the precanon research documents so the UI
can display human-readable names instead of "Step XX".
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0040_research_artifact_titles"
down_revision = "0039_funnel_page_review_status"
branch_labels = None
depends_on = None


TITLE_BY_STEP_KEY: dict[str, str] = {
    "01": "Competitor Research (Web)",
    "015": "Purple Ocean Angle Analysis",
    "02": "Competitor Facebook Page Resolution",
    "03": "Deep Research Prompt",
    "04": "Deep Research Output",
    "06": "Avatar Brief",
    "07": "Offer Brief",
    "08": "Necessary Beliefs",
    "09": "I Believe Statements",
}

LEGACY_TITLE_BY_STEP_KEY: dict[str, str] = {
    "01": "Competitor research",
    "015": "Purple ocean angle research",
    "02": "Competitor Facebook Page Resolution",
    "03": "Deep research prompt",
    "04": "Deep research execution",
    "06": "Avatar brief",
    "07": "Offer brief",
    "08": "Necessary beliefs (prompt 1)",
    "09": '"I believe" statements',
}

STEP_KEYS_SQL = ", ".join(f"'{k}'" for k in TITLE_BY_STEP_KEY.keys())


def _validate_no_missing_titles_in_research_artifacts(conn) -> None:
    missing = conn.execute(
        sa.text(
            """
            SELECT COUNT(*) AS cnt
            FROM research_artifacts
            WHERE step_key IN ("""
            + STEP_KEYS_SQL
            + """)
              AND (title IS NULL OR btrim(title) = '')
            """
        )
    ).scalar_one()
    if missing:
        raise RuntimeError(
            "research_artifacts contains rows for precanon steps with missing titles. "
            "This indicates unexpected data and should be fixed before proceeding."
        )


def _validate_no_missing_titles_in_canon_artifact_refs(conn) -> None:
    missing = conn.execute(
        sa.text(
            """
            SELECT COUNT(*) AS cnt
            FROM artifacts a,
                 LATERAL jsonb_array_elements(a.data->'precanon_research'->'artifact_refs') AS elem
            WHERE a."type" = 'client_canon'
              AND jsonb_typeof(a.data->'precanon_research') = 'object'
              AND jsonb_typeof(a.data->'precanon_research'->'artifact_refs') = 'array'
              AND (elem->>'step_key') IN ("""
            + STEP_KEYS_SQL
            + """)
              AND (elem->>'title' IS NULL OR btrim(elem->>'title') = '')
            """
        )
    ).scalar_one()
    if missing:
        raise RuntimeError(
            "client_canon.precanon_research.artifact_refs contains precanon refs missing titles. "
            "This indicates unexpected data and should be fixed before proceeding."
        )


def upgrade() -> None:
    conn = op.get_bind()

    # 1) Standardize titles for persisted research artifacts.
    conn.execute(
        sa.text(
            """
            UPDATE research_artifacts
            SET title = CASE step_key
                WHEN '01' THEN :t01
                WHEN '015' THEN :t015
                WHEN '02' THEN :t02
                WHEN '03' THEN :t03
                WHEN '04' THEN :t04
                WHEN '06' THEN :t06
                WHEN '07' THEN :t07
                WHEN '08' THEN :t08
                WHEN '09' THEN :t09
                ELSE title
            END
            WHERE step_key IN ("""
            + STEP_KEYS_SQL
            + """)
            """
        ),
        {
            "t01": TITLE_BY_STEP_KEY["01"],
            "t015": TITLE_BY_STEP_KEY["015"],
            "t02": TITLE_BY_STEP_KEY["02"],
            "t03": TITLE_BY_STEP_KEY["03"],
            "t04": TITLE_BY_STEP_KEY["04"],
            "t06": TITLE_BY_STEP_KEY["06"],
            "t07": TITLE_BY_STEP_KEY["07"],
            "t08": TITLE_BY_STEP_KEY["08"],
            "t09": TITLE_BY_STEP_KEY["09"],
        },
    )

    # 2) Add/standardize titles in client_canon.precanon_research.artifact_refs.
    conn.execute(
        sa.text(
            """
            UPDATE artifacts
            SET data = jsonb_set(
                data,
                '{precanon_research,artifact_refs}',
                COALESCE((
                    SELECT jsonb_agg(
                        CASE
                            WHEN (elem->>'step_key') = '01' THEN (elem - 'title') || jsonb_build_object('title', :t01)
                            WHEN (elem->>'step_key') = '015' THEN (elem - 'title') || jsonb_build_object('title', :t015)
                            WHEN (elem->>'step_key') = '02' THEN (elem - 'title') || jsonb_build_object('title', :t02)
                            WHEN (elem->>'step_key') = '03' THEN (elem - 'title') || jsonb_build_object('title', :t03)
                            WHEN (elem->>'step_key') = '04' THEN (elem - 'title') || jsonb_build_object('title', :t04)
                            WHEN (elem->>'step_key') = '06' THEN (elem - 'title') || jsonb_build_object('title', :t06)
                            WHEN (elem->>'step_key') = '07' THEN (elem - 'title') || jsonb_build_object('title', :t07)
                            WHEN (elem->>'step_key') = '08' THEN (elem - 'title') || jsonb_build_object('title', :t08)
                            WHEN (elem->>'step_key') = '09' THEN (elem - 'title') || jsonb_build_object('title', :t09)
                            ELSE elem
                        END
                    )
                    FROM jsonb_array_elements(data->'precanon_research'->'artifact_refs') AS elem
                ), '[]'::jsonb),
                true
            )
            WHERE "type" = 'client_canon'
              AND jsonb_typeof(data->'precanon_research') = 'object'
              AND jsonb_typeof(data->'precanon_research'->'artifact_refs') = 'array'
            """
        ),
        {
            "t01": TITLE_BY_STEP_KEY["01"],
            "t015": TITLE_BY_STEP_KEY["015"],
            "t02": TITLE_BY_STEP_KEY["02"],
            "t03": TITLE_BY_STEP_KEY["03"],
            "t04": TITLE_BY_STEP_KEY["04"],
            "t06": TITLE_BY_STEP_KEY["06"],
            "t07": TITLE_BY_STEP_KEY["07"],
            "t08": TITLE_BY_STEP_KEY["08"],
            "t09": TITLE_BY_STEP_KEY["09"],
        },
    )

    _validate_no_missing_titles_in_research_artifacts(conn)
    _validate_no_missing_titles_in_canon_artifact_refs(conn)


def downgrade() -> None:
    conn = op.get_bind()
    # Best-effort revert to legacy names.
    conn.execute(
        sa.text(
            """
            UPDATE research_artifacts
            SET title = CASE step_key
                WHEN '01' THEN :t01
                WHEN '015' THEN :t015
                WHEN '02' THEN :t02
                WHEN '03' THEN :t03
                WHEN '04' THEN :t04
                WHEN '06' THEN :t06
                WHEN '07' THEN :t07
                WHEN '08' THEN :t08
                WHEN '09' THEN :t09
                ELSE title
            END
            WHERE step_key IN ("""
            + STEP_KEYS_SQL
            + """)
            """
        ),
        {
            "t01": LEGACY_TITLE_BY_STEP_KEY["01"],
            "t015": LEGACY_TITLE_BY_STEP_KEY["015"],
            "t02": LEGACY_TITLE_BY_STEP_KEY["02"],
            "t03": LEGACY_TITLE_BY_STEP_KEY["03"],
            "t04": LEGACY_TITLE_BY_STEP_KEY["04"],
            "t06": LEGACY_TITLE_BY_STEP_KEY["06"],
            "t07": LEGACY_TITLE_BY_STEP_KEY["07"],
            "t08": LEGACY_TITLE_BY_STEP_KEY["08"],
            "t09": LEGACY_TITLE_BY_STEP_KEY["09"],
        },
    )

    conn.execute(
        sa.text(
            """
            UPDATE artifacts
            SET data = jsonb_set(
                data,
                '{precanon_research,artifact_refs}',
                COALESCE((
                    SELECT jsonb_agg(
                        CASE
                            WHEN (elem->>'step_key') = '01' THEN (elem - 'title') || jsonb_build_object('title', :t01)
                            WHEN (elem->>'step_key') = '015' THEN (elem - 'title') || jsonb_build_object('title', :t015)
                            WHEN (elem->>'step_key') = '02' THEN (elem - 'title') || jsonb_build_object('title', :t02)
                            WHEN (elem->>'step_key') = '03' THEN (elem - 'title') || jsonb_build_object('title', :t03)
                            WHEN (elem->>'step_key') = '04' THEN (elem - 'title') || jsonb_build_object('title', :t04)
                            WHEN (elem->>'step_key') = '06' THEN (elem - 'title') || jsonb_build_object('title', :t06)
                            WHEN (elem->>'step_key') = '07' THEN (elem - 'title') || jsonb_build_object('title', :t07)
                            WHEN (elem->>'step_key') = '08' THEN (elem - 'title') || jsonb_build_object('title', :t08)
                            WHEN (elem->>'step_key') = '09' THEN (elem - 'title') || jsonb_build_object('title', :t09)
                            ELSE elem
                        END
                    )
                    FROM jsonb_array_elements(data->'precanon_research'->'artifact_refs') AS elem
                ), '[]'::jsonb),
                true
            )
            WHERE "type" = 'client_canon'
              AND jsonb_typeof(data->'precanon_research') = 'object'
              AND jsonb_typeof(data->'precanon_research'->'artifact_refs') = 'array'
            """
        ),
        {
            "t01": LEGACY_TITLE_BY_STEP_KEY["01"],
            "t015": LEGACY_TITLE_BY_STEP_KEY["015"],
            "t02": LEGACY_TITLE_BY_STEP_KEY["02"],
            "t03": LEGACY_TITLE_BY_STEP_KEY["03"],
            "t04": LEGACY_TITLE_BY_STEP_KEY["04"],
            "t06": LEGACY_TITLE_BY_STEP_KEY["06"],
            "t07": LEGACY_TITLE_BY_STEP_KEY["07"],
            "t08": LEGACY_TITLE_BY_STEP_KEY["08"],
            "t09": LEGACY_TITLE_BY_STEP_KEY["09"],
        },
    )
