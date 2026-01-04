"""Add ad teardown evidence base and subtype tables"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0008_teardown_evidence"
down_revision = "0007_ad_teardowns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    op.create_table(
        "ad_teardown_evidence_items",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "teardown_id",
            uuid,
            sa.ForeignKey("ad_teardowns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("evidence_type", sa.Text(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=True),
        sa.Column("end_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index(
        "idx_ad_teardown_evidence_items_teardown_type",
        "ad_teardown_evidence_items",
        ["teardown_id", "evidence_type"],
    )
    op.create_index(
        "idx_ad_teardown_evidence_items_teardown_start",
        "ad_teardown_evidence_items",
        ["teardown_id", "start_ms"],
    )

    op.create_table(
        "ad_teardown_transcript_segments",
        sa.Column(
            "evidence_item_id",
            uuid,
            sa.ForeignKey("ad_teardown_evidence_items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("speaker_role", sa.Text(), nullable=True),
        sa.Column("spoken_text", sa.Text(), nullable=True),
        sa.Column("onscreen_text", sa.Text(), nullable=True),
        sa.Column("audio_notes", sa.Text(), nullable=True),
    )

    op.create_table(
        "ad_teardown_storyboard_scenes",
        sa.Column(
            "evidence_item_id",
            uuid,
            sa.ForeignKey("ad_teardown_evidence_items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("scene_no", sa.Integer(), nullable=False),
        sa.Column("visual_description", sa.Text(), nullable=True),
        sa.Column("action_blocking", sa.Text(), nullable=True),
        sa.Column("narrative_job", sa.Text(), nullable=True),
        sa.Column("onscreen_text", sa.Text(), nullable=True),
    )

    op.create_table(
        "ad_teardown_numeric_claims",
        sa.Column(
            "evidence_item_id",
            uuid,
            sa.ForeignKey("ad_teardown_evidence_items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("value_numeric", sa.Numeric(), nullable=True),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("claim_topic", sa.Text(), nullable=True),
        sa.Column("verification_status", sa.Text(), nullable=False, server_default=sa.text("'unverified'")),
        sa.Column("source_url", sa.Text(), nullable=True),
    )

    op.create_table(
        "ad_teardown_targeting_signals",
        sa.Column(
            "evidence_item_id",
            uuid,
            sa.ForeignKey("ad_teardown_evidence_items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("modality", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("is_observation", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("confidence", sa.Numeric(), nullable=True),
    )

    op.create_table(
        "ad_teardown_narrative_beats",
        sa.Column(
            "evidence_item_id",
            uuid,
            sa.ForeignKey("ad_teardown_evidence_items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("beat_key", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
    )

    op.create_table(
        "ad_teardown_proof_usages",
        sa.Column(
            "evidence_item_id",
            uuid,
            sa.ForeignKey("ad_teardown_evidence_items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("proof_type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
    )

    op.create_table(
        "ad_teardown_ctas",
        sa.Column(
            "evidence_item_id",
            uuid,
            sa.ForeignKey("ad_teardown_evidence_items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("cta_kind", sa.Text(), nullable=False),
        sa.Column("cta_text", sa.Text(), nullable=False),
        sa.Column("offer_stack_present", sa.Boolean(), nullable=True),
        sa.Column("risk_reversal_present", sa.Boolean(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )

    op.create_table(
        "ad_teardown_production_requirements",
        sa.Column(
            "evidence_item_id",
            uuid,
            sa.ForeignKey("ad_teardown_evidence_items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("req_type", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
    )

    op.create_table(
        "ad_teardown_ad_copy_blocks",
        sa.Column(
            "evidence_item_id",
            uuid,
            sa.ForeignKey("ad_teardown_evidence_items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("language", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ad_teardown_ad_copy_blocks")
    op.drop_table("ad_teardown_production_requirements")
    op.drop_table("ad_teardown_ctas")
    op.drop_table("ad_teardown_proof_usages")
    op.drop_table("ad_teardown_narrative_beats")
    op.drop_table("ad_teardown_targeting_signals")
    op.drop_table("ad_teardown_numeric_claims")
    op.drop_table("ad_teardown_storyboard_scenes")
    op.drop_table("ad_teardown_transcript_segments")
    op.drop_index("idx_ad_teardown_evidence_items_teardown_start", table_name="ad_teardown_evidence_items")
    op.drop_index("idx_ad_teardown_evidence_items_teardown_type", table_name="ad_teardown_evidence_items")
    op.drop_table("ad_teardown_evidence_items")
