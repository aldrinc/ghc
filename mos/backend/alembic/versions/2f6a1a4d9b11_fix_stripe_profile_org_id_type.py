"""repair stripe_account_profiles org_id type

Revision ID: 2f6a1a4d9b11
Revises: 7c8d2e1f9b44
Create Date: 2026-03-26 18:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "2f6a1a4d9b11"
down_revision = "7c8d2e1f9b44"
branch_labels = None
depends_on = None


def _drop_constraint_if_exists(table_name: str, constraint_name: str) -> None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text(
            """
            select 1
            from pg_constraint
            where conname = :constraint_name
            and conrelid = to_regclass(:table_name)
            """
        ),
        {"constraint_name": constraint_name, "table_name": table_name},
    ).scalar()
    if exists:
        op.drop_constraint(constraint_name, table_name, type_="foreignkey")


def _drop_index_if_exists(index_name: str) -> None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text(
            """
            select 1
            from pg_indexes
            where schemaname = current_schema()
            and indexname = :index_name
            """
        ),
        {"index_name": index_name},
    ).scalar()
    if exists:
        op.drop_index(index_name)


def _drop_unique_if_exists(table_name: str, constraint_name: str) -> None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text(
            """
            select 1
            from pg_constraint
            where conname = :constraint_name
            and conrelid = to_regclass(:table_name)
            and contype = 'u'
            """
        ),
        {"constraint_name": constraint_name, "table_name": table_name},
    ).scalar()
    if exists:
        op.drop_constraint(constraint_name, table_name, type_="unique")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = {column["name"]: column for column in inspector.get_columns("stripe_account_profiles")}
    org_id_column = columns.get("org_id")
    if org_id_column is None:
        return

    if isinstance(org_id_column["type"], postgresql.UUID):
        fk_names = {fk["name"] for fk in inspector.get_foreign_keys("stripe_account_profiles")}
        if "fk_stripe_account_profiles_org_id" not in fk_names:
            op.create_foreign_key(
                "fk_stripe_account_profiles_org_id",
                "stripe_account_profiles",
                "orgs",
                ["org_id"],
                ["id"],
                ondelete="CASCADE",
            )
        return

    _drop_constraint_if_exists("stripe_account_profiles", "fk_stripe_account_profiles_org_id")
    _drop_unique_if_exists("stripe_account_profiles", "uq_stripe_account_profiles_org_label")
    _drop_index_if_exists("idx_stripe_account_profiles_org_id")

    op.alter_column(
        "stripe_account_profiles",
        "org_id",
        existing_type=sa.Text(),
        type_=postgresql.UUID(as_uuid=True),
        postgresql_using="org_id::uuid",
        existing_nullable=False,
    )

    op.create_foreign_key(
        "fk_stripe_account_profiles_org_id",
        "stripe_account_profiles",
        "orgs",
        ["org_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_stripe_account_profiles_org_label",
        "stripe_account_profiles",
        ["org_id", "label"],
    )
    op.create_index("idx_stripe_account_profiles_org_id", "stripe_account_profiles", ["org_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"]: column for column in inspector.get_columns("stripe_account_profiles")}
    org_id_column = columns.get("org_id")
    if org_id_column is None or isinstance(org_id_column["type"], sa.Text):
        return

    _drop_constraint_if_exists("stripe_account_profiles", "fk_stripe_account_profiles_org_id")
    _drop_unique_if_exists("stripe_account_profiles", "uq_stripe_account_profiles_org_label")
    _drop_index_if_exists("idx_stripe_account_profiles_org_id")

    op.alter_column(
        "stripe_account_profiles",
        "org_id",
        existing_type=postgresql.UUID(as_uuid=True),
        type_=sa.Text(),
        postgresql_using="org_id::text",
        existing_nullable=False,
    )

    op.create_unique_constraint(
        "uq_stripe_account_profiles_org_label",
        "stripe_account_profiles",
        ["org_id", "label"],
    )
    op.create_index("idx_stripe_account_profiles_org_id", "stripe_account_profiles", ["org_id"])
