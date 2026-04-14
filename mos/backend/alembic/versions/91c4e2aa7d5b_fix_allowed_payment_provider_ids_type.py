"""repair client_medusa_configs allowed_payment_provider_ids type

Revision ID: 91c4e2aa7d5b
Revises: 2f6a1a4d9b11
Create Date: 2026-03-26 16:58:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "91c4e2aa7d5b"
down_revision = "2f6a1a4d9b11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"]: column for column in inspector.get_columns("client_medusa_configs")}
    allowed_column = columns.get("allowed_payment_provider_ids")
    if allowed_column is None or isinstance(allowed_column["type"], postgresql.ARRAY):
        return

    op.alter_column(
        "client_medusa_configs",
        "allowed_payment_provider_ids",
        existing_type=sa.Text(),
        type_=postgresql.ARRAY(sa.Text()),
        existing_nullable=False,
        existing_server_default=sa.text("'{}'::text[]"),
        postgresql_using="""
        CASE
          WHEN allowed_payment_provider_ids IS NULL THEN ARRAY[]::text[]
          WHEN btrim(allowed_payment_provider_ids) = '' THEN ARRAY[]::text[]
          WHEN left(btrim(allowed_payment_provider_ids), 1) = '{' THEN allowed_payment_provider_ids::text[]
          ELSE regexp_split_to_array(allowed_payment_provider_ids, '\\s*,\\s*')
        END
        """,
    )
    op.alter_column(
        "client_medusa_configs",
        "allowed_payment_provider_ids",
        server_default=sa.text("'{}'::text[]"),
        existing_type=postgresql.ARRAY(sa.Text()),
        existing_nullable=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"]: column for column in inspector.get_columns("client_medusa_configs")}
    allowed_column = columns.get("allowed_payment_provider_ids")
    if allowed_column is None or isinstance(allowed_column["type"], sa.Text):
        return

    op.alter_column(
        "client_medusa_configs",
        "allowed_payment_provider_ids",
        existing_type=postgresql.ARRAY(sa.Text()),
        type_=sa.Text(),
        existing_nullable=False,
        existing_server_default=sa.text("'{}'::text[]"),
        postgresql_using="coalesce(array_to_string(allowed_payment_provider_ids, ','), '')",
    )
