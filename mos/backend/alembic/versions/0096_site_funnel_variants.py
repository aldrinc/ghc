"""Add site funnel variants and campaign attachments.

Revision ID: 0096_site_funnel_variants
Revises: 0095_merge_meta_min_spend_and_sales_purchase_intent_heads
Create Date: 2026-05-15 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision = "0096_site_funnel_variants"
down_revision = "0095_merge_meta_min_spend_and_sales_purchase_intent_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_funnel_step_options",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "site_funnel_step_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_funnel_steps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "site_page_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_pages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("option_key", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("traffic_weight", sa.Integer(), nullable=True),
        sa.Column("is_control", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("metadata", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
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
        "idx_site_funnel_step_options_step",
        "site_funnel_step_options",
        ["site_funnel_step_id"],
    )
    op.create_index(
        "idx_site_funnel_step_options_page",
        "site_funnel_step_options",
        ["site_page_id"],
    )
    op.create_unique_constraint(
        "uq_site_funnel_step_options_step_page",
        "site_funnel_step_options",
        ["site_funnel_step_id", "site_page_id"],
    )
    op.create_unique_constraint(
        "uq_site_funnel_step_options_step_key",
        "site_funnel_step_options",
        ["site_funnel_step_id", "option_key"],
    )

    op.create_table(
        "site_funnel_paths",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "site_funnel_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_funnels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "campaign_id",
            UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("traffic_weight", sa.Integer(), nullable=True),
        sa.Column("is_control", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("experiment_spec_id", sa.Text(), nullable=True),
        sa.Column("variant_id", sa.Text(), nullable=True),
        sa.Column("metadata", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
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
    op.create_index("idx_site_funnel_paths_funnel", "site_funnel_paths", ["site_funnel_id"])
    op.create_index("idx_site_funnel_paths_campaign", "site_funnel_paths", ["campaign_id"])
    op.create_unique_constraint(
        "uq_site_funnel_paths_funnel_slug",
        "site_funnel_paths",
        ["site_funnel_id", "slug"],
    )

    op.create_table(
        "site_funnel_path_steps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "site_funnel_path_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_funnel_paths.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "site_funnel_step_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_funnel_steps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "site_funnel_step_option_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_funnel_step_options.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "site_page_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_pages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordering", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("step_role", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_site_funnel_path_steps_path",
        "site_funnel_path_steps",
        ["site_funnel_path_id"],
    )
    op.create_index(
        "idx_site_funnel_path_steps_step",
        "site_funnel_path_steps",
        ["site_funnel_step_id"],
    )
    op.create_index(
        "idx_site_funnel_path_steps_page",
        "site_funnel_path_steps",
        ["site_page_id"],
    )
    op.create_unique_constraint(
        "uq_site_funnel_path_steps_path_step",
        "site_funnel_path_steps",
        ["site_funnel_path_id", "site_funnel_step_id"],
    )
    op.create_unique_constraint(
        "uq_site_funnel_path_steps_path_ordering",
        "site_funnel_path_steps",
        ["site_funnel_path_id", "ordering"],
    )

    op.create_table(
        "site_publication_funnel_step_options",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "publication_funnel_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_publication_funnels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "site_funnel_step_option_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_funnel_step_options.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("site_funnel_step_id_at_publish", UUID(as_uuid=True), nullable=False),
        sa.Column("page_id_at_publish", UUID(as_uuid=True), nullable=False),
        sa.Column("slug_at_publish", sa.Text(), nullable=False),
        sa.Column("option_key_at_publish", sa.Text(), nullable=False),
        sa.Column("label_at_publish", sa.Text(), nullable=False),
        sa.Column("status_at_publish", sa.Text(), nullable=False),
        sa.Column("traffic_weight_at_publish", sa.Integer(), nullable=True),
        sa.Column("is_control_at_publish", sa.Boolean(), nullable=False),
        sa.Column(
            "metadata_at_publish", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_site_publication_funnel_step_options_pub",
        "site_publication_funnel_step_options",
        ["publication_funnel_id"],
    )
    op.create_index(
        "idx_site_publication_funnel_step_options_step",
        "site_publication_funnel_step_options",
        ["site_funnel_step_id_at_publish"],
    )
    op.create_unique_constraint(
        "uq_site_publication_funnel_step_options_pub_option",
        "site_publication_funnel_step_options",
        ["publication_funnel_id", "site_funnel_step_option_id"],
    )

    op.create_table(
        "site_publication_funnel_paths",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "publication_funnel_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_publication_funnels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "site_funnel_path_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_funnel_paths.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("campaign_id_at_publish", UUID(as_uuid=True), nullable=True),
        sa.Column("name_at_publish", sa.Text(), nullable=False),
        sa.Column("slug_at_publish", sa.Text(), nullable=False),
        sa.Column("status_at_publish", sa.Text(), nullable=False),
        sa.Column("traffic_weight_at_publish", sa.Integer(), nullable=True),
        sa.Column("is_control_at_publish", sa.Boolean(), nullable=False),
        sa.Column("experiment_spec_id_at_publish", sa.Text(), nullable=True),
        sa.Column("variant_id_at_publish", sa.Text(), nullable=True),
        sa.Column(
            "metadata_at_publish", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_site_publication_funnel_paths_pub",
        "site_publication_funnel_paths",
        ["publication_funnel_id"],
    )
    op.create_unique_constraint(
        "uq_site_publication_funnel_paths_pub_path",
        "site_publication_funnel_paths",
        ["publication_funnel_id", "site_funnel_path_id"],
    )
    op.create_unique_constraint(
        "uq_site_publication_funnel_paths_pub_slug",
        "site_publication_funnel_paths",
        ["publication_funnel_id", "slug_at_publish"],
    )

    op.create_table(
        "site_publication_funnel_path_steps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "publication_funnel_path_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_publication_funnel_paths.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "site_funnel_path_step_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_funnel_path_steps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("site_funnel_step_id_at_publish", UUID(as_uuid=True), nullable=False),
        sa.Column("site_funnel_step_option_id_at_publish", UUID(as_uuid=True), nullable=False),
        sa.Column("page_id_at_publish", UUID(as_uuid=True), nullable=False),
        sa.Column("slug_at_publish", sa.Text(), nullable=False),
        sa.Column("ordering_at_publish", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("step_role_at_publish", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_site_publication_funnel_path_steps_path",
        "site_publication_funnel_path_steps",
        ["publication_funnel_path_id"],
    )
    op.create_unique_constraint(
        "uq_site_publication_funnel_path_steps_path_step",
        "site_publication_funnel_path_steps",
        ["publication_funnel_path_id", "site_funnel_step_id_at_publish"],
    )
    op.create_unique_constraint(
        "uq_site_publication_funnel_path_steps_path_ordering",
        "site_publication_funnel_path_steps",
        ["publication_funnel_path_id", "ordering_at_publish"],
    )

    op.create_table(
        "campaign_site_funnels",
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
            "campaign_id",
            UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "site_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "site_funnel_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_funnels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("routing_config", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
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
    op.create_index("idx_campaign_site_funnels_campaign", "campaign_site_funnels", ["campaign_id"])
    op.create_index(
        "idx_campaign_site_funnels_site_funnel",
        "campaign_site_funnels",
        ["site_funnel_id"],
    )
    op.create_index("idx_campaign_site_funnels_site", "campaign_site_funnels", ["site_id"])
    op.create_unique_constraint(
        "uq_campaign_site_funnels_campaign_funnel",
        "campaign_site_funnels",
        ["campaign_id", "site_funnel_id"],
    )

    op.execute("""
        INSERT INTO site_funnel_step_options (
            id,
            site_funnel_step_id,
            site_page_id,
            option_key,
            label,
            status,
            traffic_weight,
            is_control,
            metadata
        )
        SELECT
            gen_random_uuid(),
            steps.id,
            steps.site_page_id,
            'primary',
            pages.name,
            'active',
            100,
            true,
            jsonb_build_object('backfilledFromSiteFunnelStep', true)
        FROM site_funnel_steps steps
        JOIN site_pages pages ON pages.id = steps.site_page_id
        """)

    op.execute("""
        WITH inserted_paths AS (
            INSERT INTO site_funnel_paths (
                id,
                site_funnel_id,
                name,
                slug,
                status,
                traffic_weight,
                is_control,
                metadata
            )
            SELECT
                gen_random_uuid(),
                funnels.id,
                'Primary path',
                'primary',
                'active',
                100,
                true,
                jsonb_build_object('backfilledFromSiteFunnelSteps', true)
            FROM site_funnels funnels
            WHERE EXISTS (
                SELECT 1
                FROM site_funnel_steps steps
                WHERE steps.site_funnel_id = funnels.id
            )
            RETURNING id, site_funnel_id
        )
        INSERT INTO site_funnel_path_steps (
            id,
            site_funnel_path_id,
            site_funnel_step_id,
            site_funnel_step_option_id,
            site_page_id,
            ordering,
            step_role
        )
        SELECT
            gen_random_uuid(),
            inserted_paths.id,
            steps.id,
            options.id,
            steps.site_page_id,
            steps.ordering,
            steps.step_role
        FROM inserted_paths
        JOIN site_funnel_steps steps
            ON steps.site_funnel_id = inserted_paths.site_funnel_id
        JOIN site_funnel_step_options options
            ON options.site_funnel_step_id = steps.id
            AND options.site_page_id = steps.site_page_id
        """)


def downgrade() -> None:
    op.drop_constraint(
        "uq_campaign_site_funnels_campaign_funnel",
        "campaign_site_funnels",
        type_="unique",
    )
    op.drop_index("idx_campaign_site_funnels_site", table_name="campaign_site_funnels")
    op.drop_index("idx_campaign_site_funnels_site_funnel", table_name="campaign_site_funnels")
    op.drop_index("idx_campaign_site_funnels_campaign", table_name="campaign_site_funnels")
    op.drop_table("campaign_site_funnels")

    op.drop_constraint(
        "uq_site_publication_funnel_path_steps_path_ordering",
        "site_publication_funnel_path_steps",
        type_="unique",
    )
    op.drop_constraint(
        "uq_site_publication_funnel_path_steps_path_step",
        "site_publication_funnel_path_steps",
        type_="unique",
    )
    op.drop_index(
        "idx_site_publication_funnel_path_steps_path",
        table_name="site_publication_funnel_path_steps",
    )
    op.drop_table("site_publication_funnel_path_steps")

    op.drop_constraint(
        "uq_site_publication_funnel_paths_pub_slug",
        "site_publication_funnel_paths",
        type_="unique",
    )
    op.drop_constraint(
        "uq_site_publication_funnel_paths_pub_path",
        "site_publication_funnel_paths",
        type_="unique",
    )
    op.drop_index(
        "idx_site_publication_funnel_paths_pub",
        table_name="site_publication_funnel_paths",
    )
    op.drop_table("site_publication_funnel_paths")

    op.drop_constraint(
        "uq_site_publication_funnel_step_options_pub_option",
        "site_publication_funnel_step_options",
        type_="unique",
    )
    op.drop_index(
        "idx_site_publication_funnel_step_options_step",
        table_name="site_publication_funnel_step_options",
    )
    op.drop_index(
        "idx_site_publication_funnel_step_options_pub",
        table_name="site_publication_funnel_step_options",
    )
    op.drop_table("site_publication_funnel_step_options")

    op.drop_constraint(
        "uq_site_funnel_path_steps_path_ordering",
        "site_funnel_path_steps",
        type_="unique",
    )
    op.drop_constraint(
        "uq_site_funnel_path_steps_path_step",
        "site_funnel_path_steps",
        type_="unique",
    )
    op.drop_index("idx_site_funnel_path_steps_page", table_name="site_funnel_path_steps")
    op.drop_index("idx_site_funnel_path_steps_step", table_name="site_funnel_path_steps")
    op.drop_index("idx_site_funnel_path_steps_path", table_name="site_funnel_path_steps")
    op.drop_table("site_funnel_path_steps")

    op.drop_constraint("uq_site_funnel_paths_funnel_slug", "site_funnel_paths", type_="unique")
    op.drop_index("idx_site_funnel_paths_campaign", table_name="site_funnel_paths")
    op.drop_index("idx_site_funnel_paths_funnel", table_name="site_funnel_paths")
    op.drop_table("site_funnel_paths")

    op.drop_constraint(
        "uq_site_funnel_step_options_step_key",
        "site_funnel_step_options",
        type_="unique",
    )
    op.drop_constraint(
        "uq_site_funnel_step_options_step_page",
        "site_funnel_step_options",
        type_="unique",
    )
    op.drop_index("idx_site_funnel_step_options_page", table_name="site_funnel_step_options")
    op.drop_index("idx_site_funnel_step_options_step", table_name="site_funnel_step_options")
    op.drop_table("site_funnel_step_options")
