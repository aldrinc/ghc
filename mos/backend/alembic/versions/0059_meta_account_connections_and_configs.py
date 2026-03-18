"""Add reusable Meta ad account connections and workspace configs.

Revision ID: 0059_meta_account_connections_and_configs
Revises: 0058_meta_publish_runs
Create Date: 2026-03-13 14:30:00.000000
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0059_meta_account_connections_and_configs"
down_revision = "0058_meta_publish_runs"
branch_labels = None
depends_on = None

jsonb = postgresql.JSONB(astext_type=sa.Text())


def _typed_metadata_insert(sql: str) -> sa.TextClause:
    return sa.text(sql).bindparams(sa.bindparam("metadata", type_=jsonb))


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    op.create_table(
        "meta_ad_account_connections",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("ad_account_id", sa.Text(), nullable=True),
        sa.Column("ad_account_name", sa.Text(), nullable=True),
        sa.Column("business_manager_id", sa.Text(), nullable=True),
        sa.Column("business_manager_name", sa.Text(), nullable=True),
        sa.Column("graph_api_version", sa.Text(), nullable=False),
        sa.Column(
            "graph_api_base_url",
            sa.Text(),
            nullable=False,
            server_default="https://graph.facebook.com",
        ),
        sa.Column("credential_type", sa.Text(), nullable=False, server_default="access_token"),
        sa.Column("credentials_encrypted", sa.Text(), nullable=True),
        sa.Column("credentials_last_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("validation_status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_validation_error", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            jsonb,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_by_user_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint(
            "org_id",
            "ad_account_id",
            name="uq_meta_ad_account_connections_org_account",
        ),
    )
    op.create_index(
        "idx_meta_ad_account_connections_org_status",
        "meta_ad_account_connections",
        ["org_id", "status"],
    )

    op.create_table(
        "meta_workspace_ad_configs",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "meta_connection_id",
            uuid,
            sa.ForeignKey("meta_ad_account_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("page_id", sa.Text(), nullable=True),
        sa.Column("page_name", sa.Text(), nullable=True),
        sa.Column("instagram_actor_id", sa.Text(), nullable=True),
        sa.Column("pixel_id", sa.Text(), nullable=True),
        sa.Column("data_set_id", sa.Text(), nullable=True),
        sa.Column("verified_domain", sa.Text(), nullable=True),
        sa.Column("verified_domain_status", sa.Text(), nullable=True),
        sa.Column("tracking_provider", sa.Text(), nullable=True),
        sa.Column("tracking_url_parameters", sa.Text(), nullable=True),
        sa.Column("attribution_click_window", sa.Text(), nullable=True),
        sa.Column("attribution_view_window", sa.Text(), nullable=True),
        sa.Column("view_through_enabled", sa.Boolean(), nullable=True),
        sa.Column("validation_status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_validation_error", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            jsonb,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_by_user_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint(
            "org_id",
            "client_id",
            "meta_connection_id",
            name="uq_meta_workspace_ad_configs_org_client_connection",
        ),
    )
    op.create_index(
        "idx_meta_workspace_ad_configs_org_client",
        "meta_workspace_ad_configs",
        ["org_id", "client_id"],
    )
    op.create_index(
        "idx_meta_workspace_ad_configs_org_connection",
        "meta_workspace_ad_configs",
        ["org_id", "meta_connection_id"],
    )
    op.create_index(
        "uq_meta_workspace_ad_configs_default",
        "meta_workspace_ad_configs",
        ["org_id", "client_id"],
        unique=True,
        postgresql_where=sa.text("is_default = true"),
    )

    op.add_column("meta_asset_uploads", sa.Column("meta_workspace_config_id", uuid, nullable=True))
    op.create_foreign_key(
        "fk_meta_asset_uploads_workspace_config",
        "meta_asset_uploads",
        "meta_workspace_ad_configs",
        ["meta_workspace_config_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_meta_asset_uploads_workspace_config",
        "meta_asset_uploads",
        ["meta_workspace_config_id"],
    )

    op.add_column("meta_ad_creatives", sa.Column("meta_workspace_config_id", uuid, nullable=True))
    op.create_foreign_key(
        "fk_meta_ad_creatives_workspace_config",
        "meta_ad_creatives",
        "meta_workspace_ad_configs",
        ["meta_workspace_config_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_meta_ad_creatives_workspace_config",
        "meta_ad_creatives",
        ["meta_workspace_config_id"],
    )

    op.add_column("meta_campaigns", sa.Column("meta_workspace_config_id", uuid, nullable=True))
    op.create_foreign_key(
        "fk_meta_campaigns_workspace_config",
        "meta_campaigns",
        "meta_workspace_ad_configs",
        ["meta_workspace_config_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_meta_campaigns_workspace_config",
        "meta_campaigns",
        ["meta_workspace_config_id"],
    )

    op.add_column("meta_ad_sets", sa.Column("meta_workspace_config_id", uuid, nullable=True))
    op.create_foreign_key(
        "fk_meta_ad_sets_workspace_config",
        "meta_ad_sets",
        "meta_workspace_ad_configs",
        ["meta_workspace_config_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_meta_ad_sets_workspace_config",
        "meta_ad_sets",
        ["meta_workspace_config_id"],
    )

    op.add_column("meta_ads", sa.Column("meta_workspace_config_id", uuid, nullable=True))
    op.create_foreign_key(
        "fk_meta_ads_workspace_config",
        "meta_ads",
        "meta_workspace_ad_configs",
        ["meta_workspace_config_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_meta_ads_workspace_config",
        "meta_ads",
        ["meta_workspace_config_id"],
    )

    op.add_column("meta_publish_runs", sa.Column("meta_workspace_config_id", uuid, nullable=True))
    op.create_foreign_key(
        "fk_meta_publish_runs_workspace_config",
        "meta_publish_runs",
        "meta_workspace_ad_configs",
        ["meta_workspace_config_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_meta_publish_runs_workspace_config",
        "meta_publish_runs",
        ["meta_workspace_config_id"],
    )

    _backfill_meta_workspace_configs()


def downgrade() -> None:
    op.drop_index("idx_meta_publish_runs_workspace_config", table_name="meta_publish_runs")
    op.drop_constraint("fk_meta_publish_runs_workspace_config", "meta_publish_runs", type_="foreignkey")
    op.drop_column("meta_publish_runs", "meta_workspace_config_id")

    op.drop_index("idx_meta_ads_workspace_config", table_name="meta_ads")
    op.drop_constraint("fk_meta_ads_workspace_config", "meta_ads", type_="foreignkey")
    op.drop_column("meta_ads", "meta_workspace_config_id")

    op.drop_index("idx_meta_ad_sets_workspace_config", table_name="meta_ad_sets")
    op.drop_constraint("fk_meta_ad_sets_workspace_config", "meta_ad_sets", type_="foreignkey")
    op.drop_column("meta_ad_sets", "meta_workspace_config_id")

    op.drop_index("idx_meta_campaigns_workspace_config", table_name="meta_campaigns")
    op.drop_constraint("fk_meta_campaigns_workspace_config", "meta_campaigns", type_="foreignkey")
    op.drop_column("meta_campaigns", "meta_workspace_config_id")

    op.drop_index("idx_meta_ad_creatives_workspace_config", table_name="meta_ad_creatives")
    op.drop_constraint("fk_meta_ad_creatives_workspace_config", "meta_ad_creatives", type_="foreignkey")
    op.drop_column("meta_ad_creatives", "meta_workspace_config_id")

    op.drop_index("idx_meta_asset_uploads_workspace_config", table_name="meta_asset_uploads")
    op.drop_constraint("fk_meta_asset_uploads_workspace_config", "meta_asset_uploads", type_="foreignkey")
    op.drop_column("meta_asset_uploads", "meta_workspace_config_id")

    op.drop_index("uq_meta_workspace_ad_configs_default", table_name="meta_workspace_ad_configs")
    op.drop_index("idx_meta_workspace_ad_configs_org_connection", table_name="meta_workspace_ad_configs")
    op.drop_index("idx_meta_workspace_ad_configs_org_client", table_name="meta_workspace_ad_configs")
    op.drop_table("meta_workspace_ad_configs")

    op.drop_index("idx_meta_ad_account_connections_org_status", table_name="meta_ad_account_connections")
    op.drop_table("meta_ad_account_connections")


def _backfill_meta_workspace_configs() -> None:
    bind = op.get_bind()
    profiles = bind.execute(
        sa.text(
            """
            SELECT
                id,
                org_id,
                client_id,
                business_manager_id,
                business_manager_name,
                page_id,
                page_name,
                ad_account_id,
                ad_account_name,
                pixel_id,
                data_set_id,
                verified_domain,
                verified_domain_status,
                attribution_click_window,
                attribution_view_window,
                view_through_enabled,
                tracking_provider,
                tracking_url_parameters,
                metadata,
                created_at,
                updated_at
            FROM paid_ads_platform_profiles
            WHERE platform = 'meta'
            """
        )
    ).mappings()

    connection_ids_by_key: dict[tuple[str, str | None], str] = {}
    for profile in profiles:
        profile_metadata = profile["metadata"] if isinstance(profile["metadata"], dict) else {}
        api_version = (
            ((profile_metadata.get("metaGraphValidation") or {}).get("apiVersion"))
            if isinstance(profile_metadata.get("metaGraphValidation"), dict)
            else None
        ) or "v24.0"
        ad_account_id = profile["ad_account_id"]
        connection_key = (str(profile["org_id"]), ad_account_id or f"profile:{profile['id']}")
        connection_id = connection_ids_by_key.get(connection_key)
        if connection_id is None:
            connection_id = str(uuid4())
            connection_name = (
                profile["ad_account_name"]
                or profile["business_manager_name"]
                or (f"Meta account {ad_account_id}" if ad_account_id else "Meta account")
            )
            bind.execute(
                _typed_metadata_insert(
                    """
                    INSERT INTO meta_ad_account_connections (
                        id,
                        org_id,
                        name,
                        ad_account_id,
                        ad_account_name,
                        business_manager_id,
                        business_manager_name,
                        graph_api_version,
                        graph_api_base_url,
                        credential_type,
                        credentials_encrypted,
                        credentials_last_updated_at,
                        token_expires_at,
                        status,
                        validation_status,
                        last_validated_at,
                        last_validation_error,
                        metadata,
                        created_by_user_id,
                        created_at,
                        updated_at
                    ) VALUES (
                        :id,
                        :org_id,
                        :name,
                        :ad_account_id,
                        :ad_account_name,
                        :business_manager_id,
                        :business_manager_name,
                        :graph_api_version,
                        'https://graph.facebook.com',
                        'access_token',
                        NULL,
                        NULL,
                        NULL,
                        'active',
                        'pending',
                        NULL,
                        NULL,
                        CAST(:metadata AS jsonb),
                        NULL,
                        :created_at,
                        :updated_at
                    )
                    """
                ),
                {
                    "id": connection_id,
                    "org_id": profile["org_id"],
                    "name": connection_name,
                    "ad_account_id": ad_account_id,
                    "ad_account_name": profile["ad_account_name"],
                    "business_manager_id": profile["business_manager_id"],
                    "business_manager_name": profile["business_manager_name"],
                    "graph_api_version": api_version,
                    "metadata": json.dumps(profile_metadata),
                    "created_at": profile["created_at"] or datetime.now(timezone.utc),
                    "updated_at": profile["updated_at"] or datetime.now(timezone.utc),
                },
            )
            connection_ids_by_key[connection_key] = connection_id

        bind.execute(
            _typed_metadata_insert(
                """
                INSERT INTO meta_workspace_ad_configs (
                    id,
                    org_id,
                    client_id,
                    meta_connection_id,
                    name,
                    is_default,
                    status,
                    page_id,
                    page_name,
                    instagram_actor_id,
                    pixel_id,
                    data_set_id,
                    verified_domain,
                    verified_domain_status,
                    tracking_provider,
                    tracking_url_parameters,
                    attribution_click_window,
                    attribution_view_window,
                    view_through_enabled,
                    validation_status,
                    last_validated_at,
                    last_validation_error,
                    metadata,
                    created_by_user_id,
                    created_at,
                    updated_at
                ) VALUES (
                    :id,
                    :org_id,
                    :client_id,
                    :meta_connection_id,
                    :name,
                    true,
                    'active',
                    :page_id,
                    :page_name,
                    NULL,
                    :pixel_id,
                    :data_set_id,
                    :verified_domain,
                    :verified_domain_status,
                    :tracking_provider,
                    :tracking_url_parameters,
                    :attribution_click_window,
                    :attribution_view_window,
                    :view_through_enabled,
                    'pending',
                    NULL,
                    NULL,
                    CAST(:metadata AS jsonb),
                    NULL,
                    :created_at,
                    :updated_at
                )
                """
            ),
            {
                "id": str(uuid4()),
                "org_id": profile["org_id"],
                "client_id": profile["client_id"],
                "meta_connection_id": connection_id,
                "name": profile["ad_account_name"] or profile["page_name"] or "Primary Meta",
                "page_id": profile["page_id"],
                "page_name": profile["page_name"],
                "pixel_id": profile["pixel_id"],
                "data_set_id": profile["data_set_id"],
                "verified_domain": profile["verified_domain"],
                "verified_domain_status": profile["verified_domain_status"],
                "tracking_provider": profile["tracking_provider"],
                "tracking_url_parameters": (
                    json.dumps(profile["tracking_url_parameters"])
                    if isinstance(profile["tracking_url_parameters"], (dict, list))
                    else profile["tracking_url_parameters"]
                ),
                "attribution_click_window": profile["attribution_click_window"],
                "attribution_view_window": profile["attribution_view_window"],
                "view_through_enabled": profile["view_through_enabled"],
                "metadata": json.dumps(profile_metadata),
                "created_at": profile["created_at"] or datetime.now(timezone.utc),
                "updated_at": profile["updated_at"] or datetime.now(timezone.utc),
            },
        )
