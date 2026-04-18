"""Add prepared_funnel_checkouts table

Revision ID: 0085_prepared_funnel_checkouts
Revises: 0084_client_compliance_policy_overrides
Create Date: 2026-04-18 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision = "0085_prepared_funnel_checkouts"
down_revision = "0084_client_compliance_policy_overrides"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prepared_funnel_checkouts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "funnel_id",
            UUID(as_uuid=True),
            sa.ForeignKey("funnels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "publication_id",
            UUID(as_uuid=True),
            sa.ForeignKey("funnel_publications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "page_id",
            UUID(as_uuid=True),
            sa.ForeignKey("funnel_pages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "variant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("product_offer_price_points.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("request_key", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("external_variant_id", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("visitor_id", sa.Text(), nullable=True),
        sa.Column("session_id", sa.Text(), nullable=True),
        sa.Column(
            "selection",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "utm",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "checkout_metadata",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("checkout_url", sa.Text(), nullable=True),
        sa.Column("checkout_session_id", sa.Text(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("last_prepared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_prepared_funnel_checkouts_status_expires",
        "prepared_funnel_checkouts",
        ["status", "expires_at"],
        unique=False,
    )
    op.create_index(
        "idx_prepared_funnel_checkouts_funnel_session",
        "prepared_funnel_checkouts",
        ["funnel_id", "session_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_prepared_funnel_checkouts_request_key",
        "prepared_funnel_checkouts",
        ["request_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_prepared_funnel_checkouts_request_key",
        "prepared_funnel_checkouts",
        type_="unique",
    )
    op.drop_index(
        "idx_prepared_funnel_checkouts_funnel_session",
        table_name="prepared_funnel_checkouts",
    )
    op.drop_index(
        "idx_prepared_funnel_checkouts_status_expires",
        table_name="prepared_funnel_checkouts",
    )
    op.drop_table("prepared_funnel_checkouts")
