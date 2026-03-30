"""Add Postiz integration tables

Revision ID: c6b8e5d71a24
Revises: 91c4e2aa7d5b
Create Date: 2026-03-26 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID


# revision identifiers, used by Alembic.
revision = "c6b8e5d71a24"
down_revision = "91c4e2aa7d5b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # client_postiz_credentials
    # -------------------------------------------------------------------------
    op.create_table(
        "client_postiz_credentials",
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
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("auth_type", sa.Text(), nullable=False, server_default="api_key"),
        sa.Column("credentials_encrypted", sa.Text(), nullable=False),
        sa.Column(
            "last_validated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("last_validation_error", sa.Text(), nullable=True),
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
        "idx_postiz_credentials_org_client",
        "client_postiz_credentials",
        ["org_id", "client_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_postiz_credentials_org_client",
        "client_postiz_credentials",
        ["org_id", "client_id"],
    )

    # -------------------------------------------------------------------------
    # client_postiz_channels
    # -------------------------------------------------------------------------
    op.create_table(
        "client_postiz_channels",
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
        sa.Column("postiz_integration_id", sa.Text(), nullable=False),
        sa.Column("postiz_channel_id", sa.Text(), nullable=False),
        sa.Column("identifier", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("profile", sa.Text(), nullable=True),
        sa.Column("picture_url", sa.Text(), nullable=True),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "metadata_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
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
        "idx_postiz_channels_org_client",
        "client_postiz_channels",
        ["org_id", "client_id"],
        unique=False,
    )
    op.create_index(
        "idx_postiz_channels_postiz_integration",
        "client_postiz_channels",
        ["postiz_integration_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_postiz_channels_org_client_integration_channel",
        "client_postiz_channels",
        ["org_id", "client_id", "postiz_integration_id", "postiz_channel_id"],
    )

    # -------------------------------------------------------------------------
    # client_postiz_posting_profiles
    # -------------------------------------------------------------------------
    op.create_table(
        "client_postiz_posting_profiles",
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
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "default_channel_ids",
            ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("timezone", sa.Text(), nullable=True),
        sa.Column("short_link", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "provider_settings_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("postiz_posting_profile_id", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
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
        "idx_postiz_posting_profiles_org_client",
        "client_postiz_posting_profiles",
        ["org_id", "client_id"],
        unique=False,
    )

    # -------------------------------------------------------------------------
    # postiz_publications
    # -------------------------------------------------------------------------
    op.create_table(
        "postiz_publications",
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
            "postiz_posting_profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("client_postiz_posting_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("postiz_post_id", sa.Text(), nullable=True),
        sa.Column(
            "postiz_post_ids_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("post_type", sa.Text(), nullable=False, server_default="now"),
        sa.Column(
            "scheduled_for",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "target_channels_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "media_urls_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("link_url", sa.Text(), nullable=True),
        sa.Column(
            "provider_settings_by_identifier_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "request_payload_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "response_payload_json",
            JSONB(),
            nullable=True,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column(
            "error_payload_json",
            JSONB(),
            nullable=True,
        ),
        sa.Column(
            "release_urls_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("postiz_post_status", sa.Text(), nullable=True),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
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
        "idx_postiz_publications_org_client",
        "postiz_publications",
        ["org_id", "client_id"],
        unique=False,
    )
    op.create_index(
        "idx_postiz_publications_postiz_post_id",
        "postiz_publications",
        ["postiz_post_id"],
        unique=False,
    )
    op.create_index(
        "idx_postiz_publications_status",
        "postiz_publications",
        ["status"],
        unique=False,
    )
    op.create_index(
        "idx_postiz_publications_scheduled_for",
        "postiz_publications",
        ["scheduled_for"],
        unique=False,
    )
    op.create_index(
        "idx_postiz_publications_created_at",
        "postiz_publications",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_postiz_publications_created_at", table_name="postiz_publications")
    op.drop_index("idx_postiz_publications_scheduled_for", table_name="postiz_publications")
    op.drop_index("idx_postiz_publications_status", table_name="postiz_publications")
    op.drop_index("idx_postiz_publications_postiz_post_id", table_name="postiz_publications")
    op.drop_index("idx_postiz_publications_org_client", table_name="postiz_publications")
    op.drop_table("postiz_publications")

    op.drop_index(
        "idx_postiz_posting_profiles_org_client",
        table_name="client_postiz_posting_profiles",
    )
    op.drop_table("client_postiz_posting_profiles")

    op.drop_constraint(
        "uq_postiz_channels_org_client_integration_channel",
        "client_postiz_channels",
        type_="unique",
    )
    op.drop_index("idx_postiz_channels_postiz_integration", table_name="client_postiz_channels")
    op.drop_index("idx_postiz_channels_org_client", table_name="client_postiz_channels")
    op.drop_table("client_postiz_channels")

    op.drop_constraint(
        "uq_postiz_credentials_org_client",
        "client_postiz_credentials",
        type_="unique",
    )
    op.drop_index("idx_postiz_credentials_org_client", table_name="client_postiz_credentials")
    op.drop_table("client_postiz_credentials")
