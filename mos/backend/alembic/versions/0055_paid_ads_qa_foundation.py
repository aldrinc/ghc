"""Add paid ads QA platform profiles, runs, and findings.

Revision ID: 0055_paid_ads_qa_foundation
Revises: 0054_creative_generation_plan_artifacts
Create Date: 2026-03-10 16:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0055_paid_ads_qa_foundation"
down_revision = "0054_creative_generation_plan_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    op.create_table(
        "paid_ads_platform_profiles",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.Text(), nullable=False),
        sa.Column("ruleset_version", sa.Text(), nullable=False),
        sa.Column("business_manager_id", sa.Text(), nullable=True),
        sa.Column("business_manager_name", sa.Text(), nullable=True),
        sa.Column("page_id", sa.Text(), nullable=True),
        sa.Column("page_name", sa.Text(), nullable=True),
        sa.Column("ad_account_id", sa.Text(), nullable=True),
        sa.Column("ad_account_name", sa.Text(), nullable=True),
        sa.Column("payment_method_type", sa.Text(), nullable=True),
        sa.Column("payment_method_status", sa.Text(), nullable=True),
        sa.Column("pixel_id", sa.Text(), nullable=True),
        sa.Column("data_set_id", sa.Text(), nullable=True),
        sa.Column("data_set_shopify_partner_installed", sa.Boolean(), nullable=True),
        sa.Column("data_set_data_sharing_level", sa.Text(), nullable=True),
        sa.Column("data_set_assigned_to_ad_account", sa.Boolean(), nullable=True),
        sa.Column("verified_domain", sa.Text(), nullable=True),
        sa.Column("verified_domain_status", sa.Text(), nullable=True),
        sa.Column("attribution_click_window", sa.Text(), nullable=True),
        sa.Column("attribution_view_window", sa.Text(), nullable=True),
        sa.Column("view_through_enabled", sa.Boolean(), nullable=True),
        sa.Column("tracking_provider", sa.Text(), nullable=True),
        sa.Column("tracking_url_parameters", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint(
            "org_id",
            "client_id",
            "platform",
            name="uq_paid_ads_platform_profiles_org_client_platform",
        ),
    )
    op.create_index(
        "idx_paid_ads_platform_profiles_org_client",
        "paid_ads_platform_profiles",
        ["org_id", "client_id"],
    )

    op.create_table(
        "paid_ads_qa_runs",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", uuid, sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=True),
        sa.Column("platform", sa.Text(), nullable=False),
        sa.Column("subject_type", sa.Text(), nullable=False),
        sa.Column("subject_id", sa.Text(), nullable=False),
        sa.Column("ruleset_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("blocker_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("high_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("medium_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("low_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("needs_manual_review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "checked_rule_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("report_markdown", sa.Text(), nullable=False),
        sa.Column("report_file_path", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_paid_ads_qa_runs_org_client", "paid_ads_qa_runs", ["org_id", "client_id"])
    op.create_index("idx_paid_ads_qa_runs_org_campaign", "paid_ads_qa_runs", ["org_id", "campaign_id"])

    op.create_table(
        "paid_ads_qa_findings",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("qa_run_id", uuid, sa.ForeignKey("paid_ads_qa_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_id", sa.Text(), nullable=False),
        sa.Column("rule_type", sa.Text(), nullable=False),
        sa.Column("platform", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("artifact_type", sa.Text(), nullable=False),
        sa.Column("artifact_ref", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "fix_guidance_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "evidence_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("needs_verification", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("source_title", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("policy_anchor_quote", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_paid_ads_qa_findings_run", "paid_ads_qa_findings", ["qa_run_id"])
    op.create_index("idx_paid_ads_qa_findings_org_rule", "paid_ads_qa_findings", ["org_id", "rule_id"])


def downgrade() -> None:
    op.drop_index("idx_paid_ads_qa_findings_org_rule", table_name="paid_ads_qa_findings")
    op.drop_index("idx_paid_ads_qa_findings_run", table_name="paid_ads_qa_findings")
    op.drop_table("paid_ads_qa_findings")

    op.drop_index("idx_paid_ads_qa_runs_org_campaign", table_name="paid_ads_qa_runs")
    op.drop_index("idx_paid_ads_qa_runs_org_client", table_name="paid_ads_qa_runs")
    op.drop_table("paid_ads_qa_runs")

    op.drop_index("idx_paid_ads_platform_profiles_org_client", table_name="paid_ads_platform_profiles")
    op.drop_table("paid_ads_platform_profiles")
