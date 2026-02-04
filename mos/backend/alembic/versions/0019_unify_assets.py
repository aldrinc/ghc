"""Unify funnel assets into assets"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0019_unify_assets"
down_revision = "0018_products_and_funnel_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    text_array = postgresql.ARRAY(sa.Text())

    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE asset_source_type ADD VALUE IF NOT EXISTS 'upload'")
        op.execute("ALTER TYPE asset_source_type ADD VALUE IF NOT EXISTS 'ai'")

    op.add_column(
        "assets",
        sa.Column("public_id", uuid, nullable=False, server_default=sa.text("gen_random_uuid()")),
    )
    op.add_column(
        "assets",
        sa.Column("asset_kind", sa.Text(), nullable=False, server_default=sa.text("'creative'")),
    )
    op.add_column(
        "assets",
        sa.Column("product_id", uuid, sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "assets",
        sa.Column("funnel_id", uuid, sa.ForeignKey("funnels.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("assets", sa.Column("storage_key", sa.Text(), nullable=True))
    op.add_column("assets", sa.Column("content_type", sa.Text(), nullable=True))
    op.add_column("assets", sa.Column("size_bytes", sa.Integer(), nullable=True))
    op.add_column("assets", sa.Column("width", sa.Integer(), nullable=True))
    op.add_column("assets", sa.Column("height", sa.Integer(), nullable=True))
    op.add_column("assets", sa.Column("alt", sa.Text(), nullable=True))
    op.add_column("assets", sa.Column("file_source", sa.Text(), nullable=True))
    op.add_column("assets", sa.Column("file_status", sa.Text(), nullable=True))
    op.add_column("assets", sa.Column("ai_metadata", jsonb, nullable=True))
    op.add_column(
        "assets",
        sa.Column("tags", text_array, nullable=False, server_default=sa.text("'{}'::text[]")),
    )

    op.create_unique_constraint("uq_assets_public_id", "assets", ["public_id"])
    op.create_index("idx_assets_product", "assets", ["product_id"])
    op.create_index("idx_assets_funnel", "assets", ["funnel_id"])
    op.create_index("idx_assets_kind", "assets", ["asset_kind"])
    op.create_index("idx_assets_tags", "assets", ["tags"], postgresql_using="gin")

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM assets a
                JOIN funnel_assets f ON a.id = f.id
            ) THEN
                RAISE EXCEPTION 'Cannot migrate funnel_assets: id collision with assets.';
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        INSERT INTO assets (
            id,
            org_id,
            client_id,
            campaign_id,
            experiment_id,
            asset_brief_artifact_id,
            variant_id,
            source_type,
            status,
            public_id,
            asset_kind,
            channel_id,
            format,
            product_id,
            funnel_id,
            icp_id,
            funnel_stage_id,
            concept_id,
            angle_type,
            content,
            storage_key,
            content_type,
            size_bytes,
            width,
            height,
            alt,
            file_source,
            file_status,
            ai_metadata,
            tags,
            created_at
        )
        SELECT
            f.id,
            f.org_id,
            f.client_id,
            NULL,
            NULL,
            NULL,
            NULL,
            CASE f.source
                WHEN 'ai' THEN 'ai'::asset_source_type
                WHEN 'upload' THEN 'upload'::asset_source_type
                ELSE 'generated'::asset_source_type
            END,
            CASE f.status
                WHEN 'ready' THEN 'approved'::asset_status
                WHEN 'pending' THEN 'draft'::asset_status
                WHEN 'failed' THEN 'rejected'::asset_status
                ELSE 'draft'::asset_status
            END,
            f.public_id,
            'image',
            'funnel',
            'image',
            NULL,
            NULL,
            NULL,
            NULL,
            NULL,
            NULL,
            '{}'::jsonb,
            f.storage_key,
            f.content_type,
            f.bytes,
            f.width,
            f.height,
            f.alt,
            f.source,
            f.status,
            f.ai_metadata,
            '{}'::text[],
            f.created_at
        FROM funnel_assets f;
        """
    )

    op.drop_constraint(
        "funnel_publication_pages_og_image_asset_id_fkey",
        "funnel_publication_pages",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_funnel_publication_pages_og_image_asset",
        "funnel_publication_pages",
        "assets",
        ["og_image_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_funnel_publication_pages_og_image_asset",
        "funnel_publication_pages",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "funnel_publication_pages_og_image_asset_id_fkey",
        "funnel_publication_pages",
        "funnel_assets",
        ["og_image_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_index("idx_assets_tags", table_name="assets")
    op.drop_index("idx_assets_kind", table_name="assets")
    op.drop_index("idx_assets_funnel", table_name="assets")
    op.drop_index("idx_assets_product", table_name="assets")
    op.drop_constraint("uq_assets_public_id", "assets", type_="unique")

    op.drop_column("assets", "tags")
    op.drop_column("assets", "ai_metadata")
    op.drop_column("assets", "file_status")
    op.drop_column("assets", "file_source")
    op.drop_column("assets", "alt")
    op.drop_column("assets", "height")
    op.drop_column("assets", "width")
    op.drop_column("assets", "size_bytes")
    op.drop_column("assets", "content_type")
    op.drop_column("assets", "storage_key")
    op.drop_column("assets", "funnel_id")
    op.drop_column("assets", "product_id")
    op.drop_column("assets", "asset_kind")
    op.drop_column("assets", "public_id")
