"""Funnels builder schema"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0015_funnels"
down_revision = "0014_media_mirroring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    funnel_status_enum = postgresql.ENUM(
        "draft",
        "published",
        "disabled",
        "archived",
        name="funnel_status",
        create_type=False,
    )
    funnel_page_version_status_enum = postgresql.ENUM(
        "draft",
        "approved",
        name="funnel_page_version_status",
        create_type=False,
    )
    funnel_page_version_source_enum = postgresql.ENUM(
        "human",
        "ai",
        "duplicate",
        name="funnel_page_version_source",
        create_type=False,
    )
    funnel_publication_link_kind_enum = postgresql.ENUM(
        "cta",
        "back",
        "default",
        "auto",
        name="funnel_publication_link_kind",
        create_type=False,
    )
    funnel_domain_status_enum = postgresql.ENUM(
        "pending",
        "verified",
        "active",
        "disabled",
        name="funnel_domain_status",
        create_type=False,
    )
    funnel_asset_kind_enum = postgresql.ENUM(
        "image",
        name="funnel_asset_kind",
        create_type=False,
    )
    funnel_asset_source_enum = postgresql.ENUM(
        "upload",
        "ai",
        name="funnel_asset_source",
        create_type=False,
    )
    funnel_asset_status_enum = postgresql.ENUM(
        "pending",
        "ready",
        "failed",
        name="funnel_asset_status",
        create_type=False,
    )
    funnel_event_type_enum = postgresql.ENUM(
        "page_view",
        "cta_click",
        "funnel_enter",
        "funnel_exit",
        name="funnel_event_type",
        create_type=False,
    )

    bind = op.get_bind()
    funnel_status_enum.create(bind, checkfirst=True)
    funnel_page_version_status_enum.create(bind, checkfirst=True)
    funnel_page_version_source_enum.create(bind, checkfirst=True)
    funnel_publication_link_kind_enum.create(bind, checkfirst=True)
    funnel_domain_status_enum.create(bind, checkfirst=True)
    funnel_asset_kind_enum.create(bind, checkfirst=True)
    funnel_asset_source_enum.create(bind, checkfirst=True)
    funnel_asset_status_enum.create(bind, checkfirst=True)
    funnel_event_type_enum.create(bind, checkfirst=True)

    op.create_table(
        "funnels",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", uuid, sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            funnel_status_enum,
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("public_id", uuid, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("entry_page_id", uuid, nullable=True),
        sa.Column("active_publication_id", uuid, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("public_id", name="uq_funnels_public_id"),
    )
    op.create_index("idx_funnels_org_client", "funnels", ["org_id", "client_id"])
    op.create_index("idx_funnels_client_campaign", "funnels", ["client_id", "campaign_id"])

    op.create_table(
        "funnel_pages",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("funnel_id", uuid, sa.ForeignKey("funnels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("ordering", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("funnel_id", "slug", name="uq_funnel_pages_funnel_slug"),
    )
    op.create_index("idx_funnel_pages_funnel", "funnel_pages", ["funnel_id"])

    op.create_table(
        "funnel_page_versions",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("page_id", uuid, sa.ForeignKey("funnel_pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "status",
            funnel_page_version_status_enum,
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("puck_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "source",
            funnel_page_version_source_enum,
            nullable=False,
            server_default=sa.text("'human'"),
        ),
        sa.Column("ai_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index(
        "idx_funnel_page_versions_page_status",
        "funnel_page_versions",
        ["page_id", "status"],
    )

    op.create_table(
        "funnel_assets",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("public_id", uuid, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("kind", funnel_asset_kind_enum, nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=True),
        sa.Column("bytes", sa.Integer(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("alt", sa.Text(), nullable=True),
        sa.Column(
            "source",
            funnel_asset_source_enum,
            nullable=False,
            server_default=sa.text("'upload'"),
        ),
        sa.Column("ai_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "status",
            funnel_asset_status_enum,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("public_id", name="uq_funnel_assets_public_id"),
    )
    op.create_index("idx_funnel_assets_org_client", "funnel_assets", ["org_id", "client_id"])

    op.create_table(
        "funnel_publications",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("funnel_id", uuid, sa.ForeignKey("funnels.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "entry_page_id",
            uuid,
            sa.ForeignKey("funnel_pages.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_funnel_publications_funnel", "funnel_publications", ["funnel_id"])

    op.create_table(
        "funnel_publication_pages",
        sa.Column(
            "publication_id",
            uuid,
            sa.ForeignKey("funnel_publications.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "page_id",
            uuid,
            sa.ForeignKey("funnel_pages.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "page_version_id",
            uuid,
            sa.ForeignKey("funnel_page_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("slug_at_publish", sa.Text(), nullable=False),
        sa.Column("title_at_publish", sa.Text(), nullable=True),
        sa.Column("description_at_publish", sa.Text(), nullable=True),
        sa.Column(
            "og_image_asset_id",
            uuid,
            sa.ForeignKey("funnel_assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("idx_funnel_publication_pages_pub", "funnel_publication_pages", ["publication_id"])
    op.create_index(
        "uq_funnel_publication_pages_pub_slug",
        "funnel_publication_pages",
        ["publication_id", "slug_at_publish"],
        unique=True,
    )

    op.create_table(
        "funnel_publication_links",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "publication_id",
            uuid,
            sa.ForeignKey("funnel_publications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_page_id",
            uuid,
            sa.ForeignKey("funnel_pages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_page_id",
            uuid,
            sa.ForeignKey("funnel_pages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "kind",
            funnel_publication_link_kind_enum,
            nullable=False,
            server_default=sa.text("'cta'"),
        ),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index(
        "idx_funnel_publication_links_pub_from",
        "funnel_publication_links",
        ["publication_id", "from_page_id"],
    )

    op.create_table(
        "funnel_page_slug_redirects",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("funnel_id", uuid, sa.ForeignKey("funnels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_id", uuid, sa.ForeignKey("funnel_pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_slug", sa.Text(), nullable=False),
        sa.Column("to_slug", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("funnel_id", "from_slug", name="uq_funnel_slug_redirect_from"),
    )
    op.create_index("idx_funnel_slug_redirect_funnel", "funnel_page_slug_redirects", ["funnel_id"])

    op.create_table(
        "funnel_domains",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("funnel_id", uuid, sa.ForeignKey("funnels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hostname", postgresql.CITEXT(), nullable=False),
        sa.Column(
            "status",
            funnel_domain_status_enum,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("verification_token", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("hostname", name="uq_funnel_domains_hostname"),
    )
    op.create_index("idx_funnel_domains_funnel", "funnel_domains", ["funnel_id"])
    op.create_index("idx_funnel_domains_org_client", "funnel_domains", ["org_id", "client_id"])

    op.create_table(
        "funnel_events",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", uuid, sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("funnel_id", uuid, sa.ForeignKey("funnels.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "publication_id",
            uuid,
            sa.ForeignKey("funnel_publications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_id", uuid, sa.ForeignKey("funnel_pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", funnel_event_type_enum, nullable=False),
        sa.Column("visitor_id", sa.Text(), nullable=True),
        sa.Column("session_id", sa.Text(), nullable=True),
        sa.Column("host", sa.Text(), nullable=True),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("referrer", sa.Text(), nullable=True),
        sa.Column(
            "utm",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "props",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index("idx_funnel_events_occurred_at", "funnel_events", ["occurred_at"])
    op.create_index("idx_funnel_events_funnel_pub", "funnel_events", ["funnel_id", "publication_id"])

    op.create_foreign_key(
        "fk_funnels_entry_page",
        "funnels",
        "funnel_pages",
        ["entry_page_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_funnels_active_publication",
        "funnels",
        "funnel_publications",
        ["active_publication_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_funnels_active_publication", "funnels", type_="foreignkey")
    op.drop_constraint("fk_funnels_entry_page", "funnels", type_="foreignkey")

    op.drop_index("idx_funnel_events_funnel_pub", table_name="funnel_events")
    op.drop_index("idx_funnel_events_occurred_at", table_name="funnel_events")
    op.drop_table("funnel_events")

    op.drop_index("idx_funnel_domains_org_client", table_name="funnel_domains")
    op.drop_index("idx_funnel_domains_funnel", table_name="funnel_domains")
    op.drop_table("funnel_domains")

    op.drop_index("idx_funnel_slug_redirect_funnel", table_name="funnel_page_slug_redirects")
    op.drop_table("funnel_page_slug_redirects")

    op.drop_index("idx_funnel_publication_links_pub_from", table_name="funnel_publication_links")
    op.drop_table("funnel_publication_links")

    op.drop_index("uq_funnel_publication_pages_pub_slug", table_name="funnel_publication_pages")
    op.drop_index("idx_funnel_publication_pages_pub", table_name="funnel_publication_pages")
    op.drop_table("funnel_publication_pages")

    op.drop_index("idx_funnel_publications_funnel", table_name="funnel_publications")
    op.drop_table("funnel_publications")

    op.drop_index("idx_funnel_assets_org_client", table_name="funnel_assets")
    op.drop_table("funnel_assets")

    op.drop_index("idx_funnel_page_versions_page_status", table_name="funnel_page_versions")
    op.drop_table("funnel_page_versions")

    op.drop_index("idx_funnel_pages_funnel", table_name="funnel_pages")
    op.drop_table("funnel_pages")

    op.drop_index("idx_funnels_client_campaign", table_name="funnels")
    op.drop_index("idx_funnels_org_client", table_name="funnels")
    op.drop_table("funnels")

    bind = op.get_bind()
    postgresql.ENUM(name="funnel_event_type").drop(bind, checkfirst=True)
    postgresql.ENUM(name="funnel_asset_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="funnel_asset_source").drop(bind, checkfirst=True)
    postgresql.ENUM(name="funnel_asset_kind").drop(bind, checkfirst=True)
    postgresql.ENUM(name="funnel_domain_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="funnel_publication_link_kind").drop(bind, checkfirst=True)
    postgresql.ENUM(name="funnel_page_version_source").drop(bind, checkfirst=True)
    postgresql.ENUM(name="funnel_page_version_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="funnel_status").drop(bind, checkfirst=True)
