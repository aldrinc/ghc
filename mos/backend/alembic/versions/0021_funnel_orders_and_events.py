"""Add funnel orders and order_completed event type."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0021_funnel_orders_and_events"
down_revision = "0020_price_points"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    jsonb = postgresql.JSONB(astext_type=sa.Text())

    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE funnel_event_type ADD VALUE IF NOT EXISTS 'order_completed'")

    op.create_table(
        "funnel_orders",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("funnel_id", uuid, sa.ForeignKey("funnels.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "publication_id",
            uuid,
            sa.ForeignKey("funnel_publications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("page_id", uuid, sa.ForeignKey("funnel_pages.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "offer_id",
            uuid,
            sa.ForeignKey("product_offers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "price_point_id",
            uuid,
            sa.ForeignKey("product_offer_price_points.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("stripe_session_id", sa.Text(), nullable=False),
        sa.Column("stripe_payment_intent_id", sa.Text(), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("selection", jsonb, nullable=True),
        sa.Column("checkout_metadata", jsonb, nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'completed'")),
        sa.Column("fulfillment_status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("stripe_session_id", name="uq_funnel_orders_stripe_session"),
    )
    op.create_index("idx_funnel_orders_funnel", "funnel_orders", ["funnel_id"])
    op.create_index("idx_funnel_orders_created_at", "funnel_orders", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_funnel_orders_created_at", table_name="funnel_orders")
    op.drop_index("idx_funnel_orders_funnel", table_name="funnel_orders")
    op.drop_table("funnel_orders")
