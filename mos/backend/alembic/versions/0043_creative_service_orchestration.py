"""Add creative service orchestration trace tables and asset retention timestamp."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0043_creative_service_orchestration"
down_revision = "0042b_extend_alembic_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    op.add_column("assets", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("idx_assets_product_created", "assets", ["product_id", "created_at"])
    op.create_index("idx_assets_expires_at", "assets", ["expires_at"])

    op.create_table(
        "creative_service_runs",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("campaign_id", uuid, sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("product_id", uuid, sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "workflow_run_id",
            uuid,
            sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("asset_brief_id", sa.Text(), nullable=False),
        sa.Column("requirement_index", sa.Integer(), nullable=True),
        sa.Column("variant_index", sa.Integer(), nullable=True),
        sa.Column("service_kind", sa.Text(), nullable=False),
        sa.Column("operation_kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("remote_job_id", sa.Text(), nullable=True),
        sa.Column("remote_session_id", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("request_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("response_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index(
        "idx_creative_service_runs_org_created",
        "creative_service_runs",
        ["org_id", "created_at"],
    )
    op.create_index(
        "idx_creative_service_runs_org_product",
        "creative_service_runs",
        ["org_id", "product_id"],
    )
    op.create_index(
        "idx_creative_service_runs_org_brief",
        "creative_service_runs",
        ["org_id", "asset_brief_id"],
    )
    op.create_index(
        "uq_creative_service_runs_remote_job",
        "creative_service_runs",
        ["remote_job_id"],
        unique=True,
        postgresql_where=sa.text("remote_job_id IS NOT NULL"),
    )
    op.create_index(
        "uq_creative_service_runs_idempotency_key",
        "creative_service_runs",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "creative_service_turns",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "run_id",
            uuid,
            sa.ForeignKey("creative_service_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("turn_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("remote_turn_id", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("request_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("response_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("run_id", "remote_turn_id", name="uq_creative_service_turns_run_remote_turn"),
    )
    op.create_index(
        "idx_creative_service_turns_run_idx",
        "creative_service_turns",
        ["run_id", "turn_index"],
    )
    op.create_index(
        "uq_creative_service_turns_idempotency_key",
        "creative_service_turns",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "creative_service_events",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "run_id",
            uuid,
            sa.ForeignKey("creative_service_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "turn_id",
            uuid,
            sa.ForeignKey("creative_service_turns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_creative_service_events_run_occurred",
        "creative_service_events",
        ["run_id", "occurred_at"],
    )
    op.create_index(
        "idx_creative_service_events_retention",
        "creative_service_events",
        ["retention_expires_at"],
    )

    op.create_table(
        "creative_service_outputs",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "run_id",
            uuid,
            sa.ForeignKey("creative_service_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "turn_id",
            uuid,
            sa.ForeignKey("creative_service_turns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("output_kind", sa.Text(), nullable=False),
        sa.Column("output_index", sa.Integer(), nullable=True),
        sa.Column("remote_asset_id", sa.Text(), nullable=True),
        sa.Column("primary_uri", sa.Text(), nullable=True),
        sa.Column("primary_url", sa.Text(), nullable=True),
        sa.Column("prompt_used", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("local_asset_id", uuid, sa.ForeignKey("assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index(
        "idx_creative_service_outputs_run_kind",
        "creative_service_outputs",
        ["run_id", "output_kind"],
    )
    op.create_index(
        "idx_creative_service_outputs_local_asset",
        "creative_service_outputs",
        ["local_asset_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_creative_service_outputs_local_asset", table_name="creative_service_outputs")
    op.drop_index("idx_creative_service_outputs_run_kind", table_name="creative_service_outputs")
    op.drop_table("creative_service_outputs")

    op.drop_index("idx_creative_service_events_retention", table_name="creative_service_events")
    op.drop_index("idx_creative_service_events_run_occurred", table_name="creative_service_events")
    op.drop_table("creative_service_events")

    op.drop_index("uq_creative_service_turns_idempotency_key", table_name="creative_service_turns")
    op.drop_index("idx_creative_service_turns_run_idx", table_name="creative_service_turns")
    op.drop_table("creative_service_turns")

    op.drop_index("uq_creative_service_runs_idempotency_key", table_name="creative_service_runs")
    op.drop_index("uq_creative_service_runs_remote_job", table_name="creative_service_runs")
    op.drop_index("idx_creative_service_runs_org_brief", table_name="creative_service_runs")
    op.drop_index("idx_creative_service_runs_org_product", table_name="creative_service_runs")
    op.drop_index("idx_creative_service_runs_org_created", table_name="creative_service_runs")
    op.drop_table("creative_service_runs")

    op.drop_index("idx_assets_expires_at", table_name="assets")
    op.drop_index("idx_assets_product_created", table_name="assets")
    op.drop_column("assets", "expires_at")
