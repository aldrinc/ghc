"""Add storage keys and mirroring metadata to media assets"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0014_media_mirroring"
down_revision = "0013_ad_scores"
branch_labels = None
depends_on = None


def upgrade() -> None:
    mirror_status_enum = postgresql.ENUM(
        "pending",
        "succeeded",
        "failed",
        "partial",
        name="media_mirror_status",
    )
    mirror_status_enum.create(op.get_bind(), checkfirst=True)

    op.add_column("media_assets", sa.Column("storage_key", sa.Text(), nullable=True))
    op.add_column("media_assets", sa.Column("preview_storage_key", sa.Text(), nullable=True))
    op.add_column("media_assets", sa.Column("bucket", sa.Text(), nullable=True))
    op.add_column("media_assets", sa.Column("preview_bucket", sa.Text(), nullable=True))
    op.add_column(
        "media_assets",
        sa.Column(
            "mirror_status",
            mirror_status_enum,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
    )
    op.add_column("media_assets", sa.Column("mirror_error", sa.Text(), nullable=True))
    op.add_column("media_assets", sa.Column("mirrored_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index(
        "uq_media_assets_storage_key",
        "media_assets",
        ["storage_key"],
        unique=True,
        postgresql_where=sa.text("storage_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_media_assets_storage_key", table_name="media_assets")
    op.drop_column("media_assets", "mirrored_at")
    op.drop_column("media_assets", "mirror_error")
    op.drop_column("media_assets", "mirror_status")
    op.drop_column("media_assets", "preview_bucket")
    op.drop_column("media_assets", "bucket")
    op.drop_column("media_assets", "preview_storage_key")
    op.drop_column("media_assets", "storage_key")

    mirror_status_enum = postgresql.ENUM(
        "pending",
        "succeeded",
        "failed",
        "partial",
        name="media_mirror_status",
    )
    mirror_status_enum.drop(op.get_bind(), checkfirst=True)
