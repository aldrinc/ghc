"""Add ad teardown assertions and evidence linking"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0009_teardown_assertions"
down_revision = "0008_teardown_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    op.create_table(
        "ad_teardown_assertions",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "teardown_id",
            uuid,
            sa.ForeignKey("ad_teardowns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("assertion_type", sa.Text(), nullable=False),
        sa.Column("assertion_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(), nullable=True),
        sa.Column("created_by_user_id", uuid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index(
        "idx_ad_teardown_assertions_type",
        "ad_teardown_assertions",
        ["teardown_id", "assertion_type"],
    )

    op.create_table(
        "ad_teardown_assertion_evidence",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "assertion_id",
            uuid,
            sa.ForeignKey("ad_teardown_assertions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "evidence_item_id",
            uuid,
            sa.ForeignKey("ad_teardown_evidence_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("assertion_id", "evidence_item_id", name="uq_ad_assertion_evidence_pair"),
    )


def downgrade() -> None:
    op.drop_table("ad_teardown_assertion_evidence")
    op.drop_index("idx_ad_teardown_assertions_type", table_name="ad_teardown_assertions")
    op.drop_table("ad_teardown_assertions")
