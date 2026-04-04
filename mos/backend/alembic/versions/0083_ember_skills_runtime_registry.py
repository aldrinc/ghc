"""Add EMBER skills registry, product bundles, and runtime export tables

Revision ID: 0083_ember_skills_runtime_registry
Revises: 0082_agent_threads_hermes_sidecar
Create Date: 2026-04-01 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision = "0083_ember_skills_runtime_registry"
down_revision = "0082_agent_threads_hermes_sidecar"
branch_labels = None
depends_on = None


_SKILL_ARTIFACT_ENUM_VALUES = (
    "skill_foundational_input",
    "skill_angle_library",
    "skill_angle_selection",
    "skill_knowledge_base",
    "skill_signal_report",
    "skill_cso",
    "skill_offer_document",
    "skill_headline_pool",
    "skill_headline_selection",
    "skill_presell_page",
    "skill_sales_page",
    "skill_brand_profile",
    "skill_runtime_bundle",
)


def upgrade() -> None:
    for enum_value in _SKILL_ARTIFACT_ENUM_VALUES:
        op.execute(f"ALTER TYPE artifact_type ADD VALUE IF NOT EXISTS '{enum_value}'")

    op.create_table(
        "skill_packages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_repo", sa.Text(), nullable=True),
        sa.Column("source_root", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("org_id", "key", name="uq_skill_packages_org_key"),
    )
    op.create_index(
        "idx_skill_packages_org_created_at",
        "skill_packages",
        ["org_id", "created_at"],
    )

    op.create_table(
        "skill_package_releases",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "skill_package_id",
            UUID(as_uuid=True),
            sa.ForeignKey("skill_packages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column(
            "manifest",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("source_revision", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "skill_package_id",
            "version",
            name="uq_skill_package_releases_package_version",
        ),
    )
    op.create_index(
        "idx_skill_package_releases_org_created_at",
        "skill_package_releases",
        ["org_id", "created_at"],
    )
    op.create_index(
        "idx_skill_package_releases_org_package_status",
        "skill_package_releases",
        ["org_id", "skill_package_id", "status"],
    )

    op.create_table(
        "skill_package_release_assets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "skill_package_release_id",
            UUID(as_uuid=True),
            sa.ForeignKey("skill_package_releases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset_kind", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=True),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "skill_package_release_id",
            "relative_path",
            name="uq_skill_package_release_assets_release_path",
        ),
    )
    op.create_index(
        "idx_skill_package_release_assets_org_release",
        "skill_package_release_assets",
        ["org_id", "skill_package_release_id"],
    )
    op.create_index(
        "idx_skill_package_release_assets_org_kind_role",
        "skill_package_release_assets",
        ["org_id", "asset_kind", "role"],
    )

    op.create_table(
        "runtime_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "skill_package_release_id",
            UUID(as_uuid=True),
            sa.ForeignKey("skill_package_releases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "profile",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "skill_package_release_id",
            "key",
            name="uq_runtime_profiles_release_key",
        ),
    )
    op.create_index(
        "idx_runtime_profiles_org_created_at",
        "runtime_profiles",
        ["org_id", "created_at"],
    )

    op.create_table(
        "workspace_skill_bindings",
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
            "product_id",
            UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "skill_package_release_id",
            UUID(as_uuid=True),
            sa.ForeignKey("skill_package_releases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("bundle_key", sa.Text(), nullable=False),
        sa.Column("bundle_family", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column(
            "metadata",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "org_id",
            "client_id",
            "product_id",
            "bundle_key",
            name="uq_workspace_skill_bindings_scope_bundle_key",
        ),
    )
    op.create_index(
        "idx_workspace_skill_bindings_org_scope",
        "workspace_skill_bindings",
        ["org_id", "client_id", "product_id"],
    )

    op.create_table(
        "project_doc_bundles",
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
            "product_id",
            UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("bundle_type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "metadata",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_by_user",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "approved_by_user",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_project_doc_bundles_org_scope_type",
        "project_doc_bundles",
        ["org_id", "client_id", "product_id", "bundle_type"],
    )
    op.create_index(
        "idx_project_doc_bundles_org_scope_active",
        "project_doc_bundles",
        ["org_id", "client_id", "product_id", "is_active"],
    )

    op.create_table(
        "project_doc_bundle_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "project_doc_bundle_id",
            UUID(as_uuid=True),
            sa.ForeignKey("project_doc_bundles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "artifact_id",
            UUID(as_uuid=True),
            sa.ForeignKey("artifacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("item_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "metadata",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "project_doc_bundle_id",
            "role",
            name="uq_project_doc_bundle_items_bundle_role",
        ),
    )
    op.create_index(
        "idx_project_doc_bundle_items_bundle_order",
        "project_doc_bundle_items",
        ["project_doc_bundle_id", "item_order"],
    )
    op.create_index(
        "idx_project_doc_bundle_items_artifact",
        "project_doc_bundle_items",
        ["artifact_id"],
    )

    op.create_table(
        "runtime_bundle_exports",
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
            "product_id",
            UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_skill_binding_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspace_skill_bindings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_doc_bundle_id",
            UUID(as_uuid=True),
            sa.ForeignKey("project_doc_bundles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("bundle_key", sa.Text(), nullable=False),
        sa.Column("runtime_profile_key", sa.Text(), nullable=False),
        sa.Column("export_root", sa.Text(), nullable=False),
        sa.Column("export_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'ready'")),
        sa.Column(
            "manifest",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_runtime_bundle_exports_org_scope_created_at",
        "runtime_bundle_exports",
        ["org_id", "client_id", "product_id", "created_at"],
    )
    op.create_index(
        "idx_runtime_bundle_exports_binding_profile",
        "runtime_bundle_exports",
        ["workspace_skill_binding_id", "runtime_profile_key"],
    )

    op.add_column("agent_threads", sa.Column("runtime_profile_key", sa.Text(), nullable=True))
    op.add_column(
        "agent_threads",
        sa.Column("strategy_bundle_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_threads_strategy_bundle_id",
        "agent_threads",
        "project_doc_bundles",
        ["strategy_bundle_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "site_page_context_bindings",
        sa.Column("strategy_bundle_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "site_page_context_bindings",
        sa.Column("runtime_profile_key", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_site_page_context_bindings_strategy_bundle_id",
        "site_page_context_bindings",
        "project_doc_bundles",
        ["strategy_bundle_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_site_page_context_bindings_strategy_bundle_id",
        "site_page_context_bindings",
        type_="foreignkey",
    )
    op.drop_column("site_page_context_bindings", "runtime_profile_key")
    op.drop_column("site_page_context_bindings", "strategy_bundle_id")

    op.drop_constraint(
        "fk_agent_threads_strategy_bundle_id",
        "agent_threads",
        type_="foreignkey",
    )
    op.drop_column("agent_threads", "strategy_bundle_id")
    op.drop_column("agent_threads", "runtime_profile_key")

    op.drop_index("idx_runtime_bundle_exports_binding_profile", table_name="runtime_bundle_exports")
    op.drop_index(
        "idx_runtime_bundle_exports_org_scope_created_at",
        table_name="runtime_bundle_exports",
    )
    op.drop_table("runtime_bundle_exports")

    op.drop_index("idx_project_doc_bundle_items_artifact", table_name="project_doc_bundle_items")
    op.drop_index(
        "idx_project_doc_bundle_items_bundle_order",
        table_name="project_doc_bundle_items",
    )
    op.drop_table("project_doc_bundle_items")

    op.drop_index("idx_project_doc_bundles_org_scope_active", table_name="project_doc_bundles")
    op.drop_index("idx_project_doc_bundles_org_scope_type", table_name="project_doc_bundles")
    op.drop_table("project_doc_bundles")

    op.drop_index(
        "idx_workspace_skill_bindings_org_scope",
        table_name="workspace_skill_bindings",
    )
    op.drop_table("workspace_skill_bindings")

    op.drop_index("idx_runtime_profiles_org_created_at", table_name="runtime_profiles")
    op.drop_table("runtime_profiles")

    op.drop_index(
        "idx_skill_package_release_assets_org_kind_role",
        table_name="skill_package_release_assets",
    )
    op.drop_index(
        "idx_skill_package_release_assets_org_release",
        table_name="skill_package_release_assets",
    )
    op.drop_table("skill_package_release_assets")

    op.drop_index(
        "idx_skill_package_releases_org_package_status",
        table_name="skill_package_releases",
    )
    op.drop_index(
        "idx_skill_package_releases_org_created_at",
        table_name="skill_package_releases",
    )
    op.drop_table("skill_package_releases")

    op.drop_index("idx_skill_packages_org_created_at", table_name="skill_packages")
    op.drop_table("skill_packages")

    # PostgreSQL enum value removal is intentionally omitted.
