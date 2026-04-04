"""Add Hermes sidecar prototype thread/session/approval tables

Revision ID: 0082_agent_threads_hermes_sidecar
Revises: c6b8e5d71a24
Create Date: 2026-03-31 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision = "0082_agent_threads_hermes_sidecar"
down_revision = "c6b8e5d71a24"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_threads",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Text(), nullable=False),
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
            "site_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "page_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_pages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("agent_profile", sa.Text(), nullable=False),
        sa.Column("objective_type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("bundle_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'open'")),
        sa.Column(
            "bundle_manifest",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
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
    )
    op.create_index("idx_agent_threads_org_created_at", "agent_threads", ["org_id", "created_at"])
    op.create_index(
        "idx_agent_threads_org_client_profile",
        "agent_threads",
        ["org_id", "client_id", "agent_profile"],
    )
    op.create_index("idx_agent_threads_org_page", "agent_threads", ["org_id", "page_id"])

    op.create_table(
        "runtime_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "thread_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agent_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
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
        sa.Column("agent_profile", sa.Text(), nullable=False),
        sa.Column("scope_key", sa.Text(), nullable=False),
        sa.Column("runtime_home", sa.Text(), nullable=False),
        sa.Column("projection_hash", sa.Text(), nullable=False),
        sa.Column("hermes_session_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'ready'")),
        sa.Column(
            "toolsets",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
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
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("thread_id", name="uq_runtime_sessions_thread"),
        sa.UniqueConstraint("scope_key", name="uq_runtime_sessions_scope_key"),
    )
    op.create_index("idx_runtime_sessions_org_last_used", "runtime_sessions", ["org_id", "last_used_at"])

    op.create_table(
        "agent_turns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "thread_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agent_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "artifact_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agent_artifacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "site_page_version_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_page_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
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
        sa.UniqueConstraint("thread_id", "seq", name="uq_agent_turns_thread_seq"),
    )
    op.create_index("idx_agent_turns_thread_created", "agent_turns", ["thread_id", "created_at"])
    op.create_index("idx_agent_turns_run", "agent_turns", ["run_id"])

    op.create_table(
        "site_page_context_bindings",
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
            "site_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "page_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_pages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("bundle_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column(
            "binding_json",
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
        sa.UniqueConstraint("page_id", name="uq_site_page_context_bindings_page"),
    )
    op.create_index(
        "idx_site_page_context_bindings_org_page",
        "site_page_context_bindings",
        ["org_id", "page_id"],
    )

    op.create_table(
        "approval_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "thread_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agent_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "artifact_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agent_artifacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "site_page_version_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site_page_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("target_kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("decision", sa.Text(), nullable=True),
        sa.Column("resolved_by_user_id", sa.Text(), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_approval_items_thread_created", "approval_items", ["thread_id", "created_at"])
    op.create_index("idx_approval_items_org_status", "approval_items", ["org_id", "status"])


def downgrade() -> None:
    op.drop_index("idx_approval_items_org_status", table_name="approval_items")
    op.drop_index("idx_approval_items_thread_created", table_name="approval_items")
    op.drop_table("approval_items")

    op.drop_index("idx_site_page_context_bindings_org_page", table_name="site_page_context_bindings")
    op.drop_table("site_page_context_bindings")

    op.drop_index("idx_agent_turns_run", table_name="agent_turns")
    op.drop_index("idx_agent_turns_thread_created", table_name="agent_turns")
    op.drop_table("agent_turns")

    op.drop_index("idx_runtime_sessions_org_last_used", table_name="runtime_sessions")
    op.drop_table("runtime_sessions")

    op.drop_index("idx_agent_threads_org_page", table_name="agent_threads")
    op.drop_index("idx_agent_threads_org_client_profile", table_name="agent_threads")
    op.drop_index("idx_agent_threads_org_created_at", table_name="agent_threads")
    op.drop_table("agent_threads")
