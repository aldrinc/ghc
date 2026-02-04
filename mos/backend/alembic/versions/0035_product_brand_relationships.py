"""Add product brand relationships."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0035_product_brand_relationships"
down_revision = "0034_campaign_funnel_gen"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE product_brand_relationship_type AS ENUM ('competitor');")
    op.execute(
        "CREATE TYPE product_brand_relationship_source AS ENUM "
        "('onboarding_seed','competitor_discovery','ads_ingestion','manual_admin');"
    )

    uuid = postgresql.UUID(as_uuid=True)
    relationship_type_enum = postgresql.ENUM(
        name="product_brand_relationship_type",
        create_type=False,
    )
    source_type_enum = postgresql.ENUM(
        name="product_brand_relationship_source",
        create_type=False,
    )

    op.create_table(
        "product_brand_relationships",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", uuid, sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand_id", uuid, sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relationship_type", relationship_type_enum, nullable=False),
        sa.Column("source_type", source_type_enum, nullable=False),
        sa.Column("source_id", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", uuid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint(
            "org_id",
            "client_id",
            "product_id",
            "brand_id",
            "relationship_type",
            name="uq_product_brand_relationship",
        ),
    )

    op.create_index(
        "idx_product_brand_relationships_org_client_product",
        "product_brand_relationships",
        ["org_id", "client_id", "product_id"],
    )
    op.create_index(
        "idx_product_brand_relationships_org_client_brand",
        "product_brand_relationships",
        ["org_id", "client_id", "brand_id"],
    )
    op.create_index(
        "idx_product_brand_relationships_product",
        "product_brand_relationships",
        ["product_id"],
    )
    op.create_index(
        "idx_product_brand_relationships_brand",
        "product_brand_relationships",
        ["brand_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_product_brand_relationships_brand", table_name="product_brand_relationships")
    op.drop_index("idx_product_brand_relationships_product", table_name="product_brand_relationships")
    op.drop_index(
        "idx_product_brand_relationships_org_client_brand",
        table_name="product_brand_relationships",
    )
    op.drop_index(
        "idx_product_brand_relationships_org_client_product",
        table_name="product_brand_relationships",
    )
    op.drop_table("product_brand_relationships")
    op.execute("DROP TYPE product_brand_relationship_source;")
    op.execute("DROP TYPE product_brand_relationship_type;")
