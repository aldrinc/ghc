"""Add client compliance profiles for policy-page readiness and business model mapping."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0047_client_compliance_profiles"
down_revision = "0046_client_shopify_default_shop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    op.create_table(
        "client_compliance_profiles",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", uuid, sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ruleset_version", sa.Text(), nullable=False),
        sa.Column(
            "business_models",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("legal_business_name", sa.Text(), nullable=True),
        sa.Column("operating_entity_name", sa.Text(), nullable=True),
        sa.Column("company_address_text", sa.Text(), nullable=True),
        sa.Column("business_license_identifier", sa.Text(), nullable=True),
        sa.Column("support_email", sa.Text(), nullable=True),
        sa.Column("support_phone", sa.Text(), nullable=True),
        sa.Column("support_hours_text", sa.Text(), nullable=True),
        sa.Column("response_time_commitment", sa.Text(), nullable=True),
        sa.Column("privacy_policy_url", sa.Text(), nullable=True),
        sa.Column("terms_of_service_url", sa.Text(), nullable=True),
        sa.Column("returns_refunds_policy_url", sa.Text(), nullable=True),
        sa.Column("shipping_policy_url", sa.Text(), nullable=True),
        sa.Column("contact_support_url", sa.Text(), nullable=True),
        sa.Column("company_information_url", sa.Text(), nullable=True),
        sa.Column("subscription_terms_and_cancellation_url", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("org_id", "client_id", name="uq_client_compliance_profiles_org_client"),
    )

    op.create_index(
        "idx_client_compliance_profiles_org_client",
        "client_compliance_profiles",
        ["org_id", "client_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_client_compliance_profiles_org_client", table_name="client_compliance_profiles")
    op.drop_table("client_compliance_profiles")
