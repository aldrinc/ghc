"""add swipe collections and taxonomy fields

Revision ID: 0069_swipe_collections_and_taxonomy
Revises: 0068_meta_adset_spec_dsa_fields
Create Date: 2026-03-19 14:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0069_swipe_collections_and_taxonomy"
down_revision = "0068_meta_adset_spec_dsa_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company_swipe_assets",
        sa.Column("source_kind", sa.Text(), nullable=False, server_default=sa.text("'catalog'")),
    )
    op.add_column(
        "company_swipe_assets",
        sa.Column("origin_system", sa.Text(), nullable=False, server_default=sa.text("'internal_seed_set'")),
    )
    op.add_column(
        "company_swipe_assets",
        sa.Column("analysis_status", sa.Text(), nullable=False, server_default=sa.text("'ready'")),
    )
    op.add_column("company_swipe_assets", sa.Column("analysis_error", sa.Text(), nullable=True))
    op.add_column("company_swipe_assets", sa.Column("analysis_model", sa.Text(), nullable=True))
    op.add_column("company_swipe_assets", sa.Column("analysis_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("company_swipe_assets", sa.Column("ad_unit_format", sa.Text(), nullable=True))
    op.add_column("company_swipe_assets", sa.Column("placement_shape", sa.Text(), nullable=True))
    op.add_column("company_swipe_assets", sa.Column("channel", sa.Text(), nullable=True))
    op.add_column("company_swipe_assets", sa.Column("destination_type", sa.Text(), nullable=True))
    op.add_column("company_swipe_assets", sa.Column("funnel_stage", sa.Text(), nullable=True))
    op.add_column("company_swipe_assets", sa.Column("angle_family", sa.Text(), nullable=True))
    op.add_column("company_swipe_assets", sa.Column("hook_type", sa.Text(), nullable=True))
    op.add_column("company_swipe_assets", sa.Column("visual_archetype", sa.Text(), nullable=True))
    op.add_column("company_swipe_assets", sa.Column("product_presence", sa.Text(), nullable=True))
    op.add_column("company_swipe_assets", sa.Column("proof_type", sa.Text(), nullable=True))
    op.add_column("company_swipe_assets", sa.Column("claim_risk", sa.Text(), nullable=True))
    op.add_column("company_swipe_assets", sa.Column("product_image_policy", sa.Text(), nullable=True))
    op.create_index(
        "idx_company_swipe_assets_org_analysis_status",
        "company_swipe_assets",
        ["org_id", "analysis_status"],
        unique=False,
    )

    op.create_table(
        "swipe_collections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column(
            "cloned_from_collection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("swipe_collections.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_by_user_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("org_id", "name", name="uq_swipe_collections_org_name"),
    )
    op.create_index("idx_swipe_collections_org_kind", "swipe_collections", ["org_id", "kind"], unique=False)

    op.create_table(
        "swipe_collection_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "collection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("swipe_collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "swipe_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_swipe_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "collection_id",
            "swipe_asset_id",
            name="uq_swipe_collection_items_collection_asset",
        ),
    )
    op.create_index(
        "idx_swipe_collection_items_org_collection",
        "swipe_collection_items",
        ["org_id", "collection_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_swipe_collection_items_org_collection", table_name="swipe_collection_items")
    op.drop_table("swipe_collection_items")

    op.drop_index("idx_swipe_collections_org_kind", table_name="swipe_collections")
    op.drop_table("swipe_collections")

    op.drop_index("idx_company_swipe_assets_org_analysis_status", table_name="company_swipe_assets")
    op.drop_column("company_swipe_assets", "product_image_policy")
    op.drop_column("company_swipe_assets", "claim_risk")
    op.drop_column("company_swipe_assets", "proof_type")
    op.drop_column("company_swipe_assets", "product_presence")
    op.drop_column("company_swipe_assets", "visual_archetype")
    op.drop_column("company_swipe_assets", "hook_type")
    op.drop_column("company_swipe_assets", "angle_family")
    op.drop_column("company_swipe_assets", "funnel_stage")
    op.drop_column("company_swipe_assets", "destination_type")
    op.drop_column("company_swipe_assets", "channel")
    op.drop_column("company_swipe_assets", "placement_shape")
    op.drop_column("company_swipe_assets", "ad_unit_format")
    op.drop_column("company_swipe_assets", "analysis_updated_at")
    op.drop_column("company_swipe_assets", "analysis_model")
    op.drop_column("company_swipe_assets", "analysis_error")
    op.drop_column("company_swipe_assets", "analysis_status")
    op.drop_column("company_swipe_assets", "origin_system")
    op.drop_column("company_swipe_assets", "source_kind")
