"""Widen alembic_version.version_num to support long revision identifiers.

Alembic creates `alembic_version.version_num` as VARCHAR(32) by default.
Our human-readable revision ids exceed 32 chars starting at 0043, which makes
`alembic upgrade head` fail on a brand new database when it tries to stamp the
current revision.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0042b_extend_alembic_version"
down_revision = "0042_client_user_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)")


def downgrade() -> None:
    raise RuntimeError(
        "Refusing to shrink alembic_version.version_num back to VARCHAR(32); "
        "0043+ revision ids exceed 32 chars and would be truncated."
    )
