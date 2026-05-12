"""add animated template manifest tables

Revision ID: 0093_animated_template_manifests
Revises: 0092_merge_meta_management_and_funnel_tracking_heads
Create Date: 2026-05-07 14:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0093_animated_template_manifests"
down_revision = "0092_merge_meta_management_and_funnel_tracking_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE workflow_kind ADD VALUE IF NOT EXISTS 'swipe_animated_template_analysis';")
    op.execute("ALTER TYPE workflow_kind ADD VALUE IF NOT EXISTS 'swipe_animated_template_render';")

    op.create_table(
        "animated_template_manifests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("workflow_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("company_swipe_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("company_swipe_media_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_label", sa.Text(), nullable=True),
        sa.Column("source_sha256", sa.Text(), nullable=False),
        sa.Column("source_mime_type", sa.Text(), nullable=False),
        sa.Column("manifest_schema_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("analyzer_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'needs_review'"), nullable=False),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("manifest_sha256", sa.Text(), nullable=False),
        sa.Column(
            "validation",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "summary",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("approved_by_user_id", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by_user_id", sa.Text(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("supersedes_manifest_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["company_swipe_id"], ["company_swipe_assets.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["company_swipe_media_id"], ["company_swipe_media.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["supersedes_manifest_id"], ["animated_template_manifests.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_animated_template_manifests_campaign",
        "animated_template_manifests",
        ["org_id", "campaign_id"],
        unique=False,
    )
    op.create_index(
        "idx_animated_template_manifests_company_swipe",
        "animated_template_manifests",
        ["company_swipe_id"],
        unique=False,
    )
    op.create_index(
        "idx_animated_template_manifests_org_source",
        "animated_template_manifests",
        ["org_id", "source_sha256"],
        unique=False,
    )
    op.create_index(
        "idx_animated_template_manifests_org_status",
        "animated_template_manifests",
        ["org_id", "status"],
        unique=False,
    )
    op.create_index(
        "uq_animated_template_manifests_org_idempotency",
        "animated_template_manifests",
        ["org_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "animated_template_manifest_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("manifest_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["manifest_id"], ["animated_template_manifests.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_animated_template_manifest_events_manifest",
        "animated_template_manifest_events",
        ["manifest_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_animated_template_manifest_events_org",
        "animated_template_manifest_events",
        ["org_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "animated_template_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("manifest_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("workflow_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'queued'"), nullable=False),
        sa.Column(
            "render_request",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "render_plan",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "cost_estimate",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "cost_actual",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "qa_report",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "output_asset_ids",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column(
            "output_artifact_ids",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["manifest_id"], ["animated_template_manifests.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_animated_template_runs_manifest",
        "animated_template_runs",
        ["manifest_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_animated_template_runs_org_status",
        "animated_template_runs",
        ["org_id", "status"],
        unique=False,
    )
    op.create_index(
        "uq_animated_template_runs_org_idempotency",
        "animated_template_runs",
        ["org_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "animated_template_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("manifest_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("artifact_kind", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["manifest_id"], ["animated_template_manifests.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["animated_template_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_animated_template_artifacts_manifest",
        "animated_template_artifacts",
        ["manifest_id", "artifact_kind"],
        unique=False,
    )
    op.create_index(
        "idx_animated_template_artifacts_run",
        "animated_template_artifacts",
        ["run_id", "artifact_kind"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_animated_template_artifacts_run", table_name="animated_template_artifacts")
    op.drop_index(
        "idx_animated_template_artifacts_manifest", table_name="animated_template_artifacts"
    )
    op.drop_table("animated_template_artifacts")

    op.drop_index("uq_animated_template_runs_org_idempotency", table_name="animated_template_runs")
    op.drop_index("idx_animated_template_runs_org_status", table_name="animated_template_runs")
    op.drop_index("idx_animated_template_runs_manifest", table_name="animated_template_runs")
    op.drop_table("animated_template_runs")

    op.drop_index(
        "idx_animated_template_manifest_events_org",
        table_name="animated_template_manifest_events",
    )
    op.drop_index(
        "idx_animated_template_manifest_events_manifest",
        table_name="animated_template_manifest_events",
    )
    op.drop_table("animated_template_manifest_events")

    op.drop_index(
        "uq_animated_template_manifests_org_idempotency",
        table_name="animated_template_manifests",
    )
    op.drop_index(
        "idx_animated_template_manifests_org_status",
        table_name="animated_template_manifests",
    )
    op.drop_index(
        "idx_animated_template_manifests_org_source",
        table_name="animated_template_manifests",
    )
    op.drop_index(
        "idx_animated_template_manifests_company_swipe",
        table_name="animated_template_manifests",
    )
    op.drop_index(
        "idx_animated_template_manifests_campaign",
        table_name="animated_template_manifests",
    )
    op.drop_table("animated_template_manifests")
