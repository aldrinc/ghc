"""add workspace-owned PostHog settings

Revision ID: 0088_client_posthog_settings
Revises: 0087_product_variant_shopify_selling_plan_id
Create Date: 2026-04-22 12:00:00.000000
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "0088_client_posthog_settings"
down_revision = "0087_product_variant_shopify_selling_plan_id"
branch_labels = None
depends_on = None

_ALLOWED_PERSON_PROFILES = {"identified_only", "always"}
_METADATA_KEY = "mosPosthogTracking"


def _clean_optional_text(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _normalize_https_origin(value: object, *, field_name: str) -> str | None:
    cleaned = _clean_optional_text(value)
    if not cleaned:
        return None
    parsed = urlsplit(cleaned)
    if parsed.scheme != "https" or not parsed.netloc:
        raise RuntimeError(f"{field_name} must be an https origin without a path during PostHog backfill.")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise RuntimeError(f"{field_name} must be an https origin without a path during PostHog backfill.")
    return f"{parsed.scheme}://{parsed.netloc}"


def _env_flag_is_enabled(value: object) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _resolve_env_backfill_config() -> dict[str, str] | None:
    if not _env_flag_is_enabled(os.getenv("POSTHOG_FUNNELS_ENABLED")):
        return None

    project_api_key = _clean_optional_text(os.getenv("POSTHOG_FUNNELS_PROJECT_API_KEY"))
    api_host = _normalize_https_origin(os.getenv("POSTHOG_FUNNELS_API_HOST"), field_name="POSTHOG_FUNNELS_API_HOST")
    ui_host = _normalize_https_origin(os.getenv("POSTHOG_FUNNELS_UI_HOST"), field_name="POSTHOG_FUNNELS_UI_HOST")
    defaults = _clean_optional_text(os.getenv("POSTHOG_FUNNELS_DEFAULTS")) or "2026-01-30"
    person_profiles = (
        _clean_optional_text(os.getenv("POSTHOG_FUNNELS_PERSON_PROFILES")) or "identified_only"
    )

    if not project_api_key:
        raise RuntimeError(
            "POSTHOG_FUNNELS_PROJECT_API_KEY is required during PostHog workspace backfill."
        )
    if not api_host:
        raise RuntimeError(
            "POSTHOG_FUNNELS_API_HOST is required during PostHog workspace backfill."
        )
    if person_profiles not in _ALLOWED_PERSON_PROFILES:
        raise RuntimeError(
            "POSTHOG_FUNNELS_PERSON_PROFILES must be 'identified_only' or 'always' during PostHog workspace backfill."
        )

    return {
        "project_api_key": project_api_key,
        "api_host": api_host,
        "ui_host": ui_host,
        "defaults": defaults,
        "person_profiles": person_profiles,
    }


def _resolve_metadata_override(metadata_json: object) -> dict[str, str] | None:
    if not isinstance(metadata_json, dict):
        return None
    tracking = metadata_json.get(_METADATA_KEY)
    if not isinstance(tracking, dict):
        return None

    status_value = _clean_optional_text(tracking.get("status"))
    if status_value and status_value.lower() != "active":
        return None

    mode_value = _clean_optional_text(tracking.get("mode"))
    if mode_value and mode_value not in {"managed_reverse_proxy", "public_funnel_runtime"}:
        raise RuntimeError(
            f"{_METADATA_KEY}.mode must be 'managed_reverse_proxy' or 'public_funnel_runtime' during PostHog backfill."
        )

    api_host = _normalize_https_origin(
        tracking.get("apiHost") or tracking.get("posthogApiHost"),
        field_name=f"{_METADATA_KEY}.apiHost",
    )
    ui_host = _normalize_https_origin(
        tracking.get("uiHost") or tracking.get("posthogUiHost"),
        field_name=f"{_METADATA_KEY}.uiHost",
    )
    resolved: dict[str, str] = {}
    if api_host:
        resolved["api_host"] = api_host
    if ui_host:
        resolved["ui_host"] = ui_host
    return resolved or None


def _backfill_existing_posthog_settings() -> None:
    env_config = _resolve_env_backfill_config()
    if env_config is None:
        return

    connection = op.get_bind()
    candidate_rows = connection.execute(
        sa.text(
            """
            SELECT DISTINCT org_id::text AS org_id, client_id::text AS client_id
            FROM funnels
            """
        )
    ).mappings()
    profile_rows = connection.execute(
        sa.text(
            """
            SELECT org_id::text AS org_id, client_id::text AS client_id, metadata AS metadata_json
            FROM paid_ads_platform_profiles
            WHERE platform = 'meta'
              AND metadata ? 'mosPosthogTracking'
            """
        )
    ).mappings()

    overrides: dict[tuple[str, str], dict[str, str]] = {}
    candidates: set[tuple[str, str]] = set()
    for row in candidate_rows:
        candidates.add((row["org_id"], row["client_id"]))
    for row in profile_rows:
        key = (row["org_id"], row["client_id"])
        candidates.add(key)
        override = _resolve_metadata_override(row["metadata_json"])
        if override:
            overrides[key] = override

    if not candidates:
        return

    metadata = sa.MetaData()
    table = sa.Table(
        "client_posthog_settings",
        metadata,
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.Column("org_id", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.Column("client_id", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.Column("enabled", sa.Boolean()),
        sa.Column("project_api_key", sa.Text()),
        sa.Column("api_host", sa.Text()),
        sa.Column("ui_host", sa.Text()),
        sa.Column("defaults", sa.Text()),
        sa.Column("person_profiles", sa.Text()),
        sa.Column("source_mode", sa.Text()),
        sa.Column("source_snippet", sa.Text()),
        sa.Column("created_by_user_id", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    now = datetime.now(timezone.utc)
    for org_id, client_id in sorted(candidates):
        override = overrides.get((org_id, client_id), {})
        connection.execute(
            table.insert().values(
                id=uuid4(),
                org_id=org_id,
                client_id=client_id,
                enabled=True,
                project_api_key=env_config["project_api_key"],
                api_host=override.get("api_host") or env_config["api_host"],
                ui_host=override.get("ui_host") or env_config["ui_host"],
                defaults=env_config["defaults"],
                person_profiles=env_config["person_profiles"],
                source_mode="structured",
                source_snippet=None,
                created_by_user_id=None,
                created_at=now,
                updated_at=now,
            )
        )


def upgrade() -> None:
    op.create_table(
        "client_posthog_settings",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("project_api_key", sa.Text(), nullable=True),
        sa.Column("api_host", sa.Text(), nullable=True),
        sa.Column("ui_host", sa.Text(), nullable=True),
        sa.Column("defaults", sa.Text(), nullable=True),
        sa.Column("person_profiles", sa.Text(), nullable=True),
        sa.Column("source_mode", sa.Text(), nullable=False, server_default=sa.text("'structured'")),
        sa.Column("source_snippet", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "client_id", name="uq_client_posthog_settings_org_client"),
    )
    op.create_index(
        "idx_client_posthog_settings_org_client",
        "client_posthog_settings",
        ["org_id", "client_id"],
        unique=False,
    )
    _backfill_existing_posthog_settings()


def downgrade() -> None:
    op.drop_index("idx_client_posthog_settings_org_client", table_name="client_posthog_settings")
    op.drop_table("client_posthog_settings")
