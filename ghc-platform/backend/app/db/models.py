from __future__ import annotations

from datetime import datetime, date
from typing import Any, Optional
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID, CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import (
    AdChannelEnum,
    AdIngestStatusEnum,
    AdStatusEnum,
    ArtifactTypeEnum,
    AssetSourceEnum,
    AssetStatusEnum,
    BrandChannelVerificationStatusEnum,
    BrandRoleEnum,
    ClaudeContextFileStatusEnum,
    CampaignStatusEnum,
    ClientStatusEnum,
    FunnelAssetKindEnum,
    FunnelAssetSourceEnum,
    FunnelAssetStatusEnum,
    FunnelDomainStatusEnum,
    FunnelEventTypeEnum,
    FunnelPageVersionSourceEnum,
    FunnelPageVersionStatusEnum,
    FunnelPublicationLinkKindEnum,
    FunnelStatusEnum,
    MediaAssetTypeEnum,
    MediaMirrorStatusEnum,
    ResearchJobStatusEnum,
    UserRoleEnum,
    WorkflowKindEnum,
    WorkflowStatusEnum,
)


class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    external_id: Mapped[Optional[str]] = mapped_column(Text, unique=True, nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("org_id", "email", name="uq_users_org_email"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    clerk_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(CITEXT(), nullable=False)
    role: Mapped[UserRoleEnum] = mapped_column(Enum(UserRoleEnum, name="user_role"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    industry: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    primary_markets: Mapped[list[str]] = mapped_column(
    ARRAY(Text), server_default=sa.text("'{}'::text[]"), nullable=False
)
    primary_languages: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=sa.text("'{}'::text[]"), nullable=False
    )
    status: Mapped[ClientStatusEnum] = mapped_column(
        Enum(ClientStatusEnum, name="client_status"),
        server_default=ClientStatusEnum.active.value,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProductOffer(Base):
    __tablename__ = "product_offers"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    business_model: Mapped[str] = mapped_column(Text, nullable=False)
    differentiation_bullets: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=sa.text("'{}'::text[]"), nullable=False
    )
    guarantee_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProductOfferPricePoint(Base):
    __tablename__ = "product_offer_price_points"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    offer_id: Mapped[str] = mapped_column(ForeignKey("product_offers.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(length=3), nullable=False)


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[CampaignStatusEnum] = mapped_column(
        Enum(CampaignStatusEnum, name="campaign_status"),
        nullable=False,
        server_default=CampaignStatusEnum.draft.value,
    )
    goal_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    objective_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    numeric_target: Mapped[Optional[Numeric]] = mapped_column(Numeric, nullable=True)
    baseline: Mapped[Optional[Numeric]] = mapped_column(Numeric, nullable=True)
    timeframe_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    budget_min: Mapped[Optional[Numeric]] = mapped_column(Numeric, nullable=True)
    budget_max: Mapped[Optional[Numeric]] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Funnel(Base):
    __tablename__ = "funnels"
    __table_args__ = (
        UniqueConstraint("public_id", name="uq_funnels_public_id"),
        sa.Index("idx_funnels_org_client", "org_id", "client_id"),
        sa.Index("idx_funnels_client_campaign", "client_id", "campaign_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[FunnelStatusEnum] = mapped_column(
        Enum(FunnelStatusEnum, name="funnel_status"),
        nullable=False,
        server_default=FunnelStatusEnum.draft.value,
    )
    public_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, default=uuid4)
    entry_page_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("funnel_pages.id", ondelete="SET NULL"), nullable=True
    )
    active_publication_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("funnel_publications.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FunnelPage(Base):
    __tablename__ = "funnel_pages"
    __table_args__ = (
        UniqueConstraint("funnel_id", "slug", name="uq_funnel_pages_funnel_slug"),
        sa.Index("idx_funnel_pages_funnel", "funnel_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    funnel_id: Mapped[str] = mapped_column(
        ForeignKey("funnels.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    ordering: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FunnelPageVersion(Base):
    __tablename__ = "funnel_page_versions"
    __table_args__ = (sa.Index("idx_funnel_page_versions_page_status", "page_id", "status"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    page_id: Mapped[str] = mapped_column(
        ForeignKey("funnel_pages.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[FunnelPageVersionStatusEnum] = mapped_column(
        Enum(FunnelPageVersionStatusEnum, name="funnel_page_version_status"),
        nullable=False,
        server_default=FunnelPageVersionStatusEnum.draft.value,
    )
    puck_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source: Mapped[FunnelPageVersionSourceEnum] = mapped_column(
        Enum(FunnelPageVersionSourceEnum, name="funnel_page_version_source"),
        nullable=False,
        server_default=FunnelPageVersionSourceEnum.human.value,
    )
    ai_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FunnelPublication(Base):
    __tablename__ = "funnel_publications"
    __table_args__ = (sa.Index("idx_funnel_publications_funnel", "funnel_id"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    funnel_id: Mapped[str] = mapped_column(
        ForeignKey("funnels.id", ondelete="CASCADE"), nullable=False
    )
    entry_page_id: Mapped[str] = mapped_column(
        ForeignKey("funnel_pages.id", ondelete="RESTRICT"), nullable=False
    )
    created_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FunnelPublicationPage(Base):
    __tablename__ = "funnel_publication_pages"
    __table_args__ = (
        sa.Index("idx_funnel_publication_pages_pub", "publication_id"),
        sa.Index(
            "uq_funnel_publication_pages_pub_slug",
            "publication_id",
            "slug_at_publish",
            unique=True,
        ),
    )

    publication_id: Mapped[str] = mapped_column(
        ForeignKey("funnel_publications.id", ondelete="CASCADE"), primary_key=True
    )
    page_id: Mapped[str] = mapped_column(
        ForeignKey("funnel_pages.id", ondelete="CASCADE"), primary_key=True
    )
    page_version_id: Mapped[str] = mapped_column(
        ForeignKey("funnel_page_versions.id", ondelete="RESTRICT"), nullable=False
    )
    slug_at_publish: Mapped[str] = mapped_column(Text, nullable=False)
    title_at_publish: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description_at_publish: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    og_image_asset_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("funnel_assets.id", ondelete="SET NULL"), nullable=True
    )


class FunnelPublicationLink(Base):
    __tablename__ = "funnel_publication_links"
    __table_args__ = (sa.Index("idx_funnel_publication_links_pub_from", "publication_id", "from_page_id"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    publication_id: Mapped[str] = mapped_column(
        ForeignKey("funnel_publications.id", ondelete="CASCADE"), nullable=False
    )
    from_page_id: Mapped[str] = mapped_column(
        ForeignKey("funnel_pages.id", ondelete="CASCADE"), nullable=False
    )
    to_page_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("funnel_pages.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[FunnelPublicationLinkKindEnum] = mapped_column(
        Enum(FunnelPublicationLinkKindEnum, name="funnel_publication_link_kind"),
        nullable=False,
        server_default=FunnelPublicationLinkKindEnum.cta.value,
    )
    label: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FunnelPageSlugRedirect(Base):
    __tablename__ = "funnel_page_slug_redirects"
    __table_args__ = (
        UniqueConstraint("funnel_id", "from_slug", name="uq_funnel_slug_redirect_from"),
        sa.Index("idx_funnel_slug_redirect_funnel", "funnel_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    funnel_id: Mapped[str] = mapped_column(
        ForeignKey("funnels.id", ondelete="CASCADE"), nullable=False
    )
    page_id: Mapped[str] = mapped_column(
        ForeignKey("funnel_pages.id", ondelete="CASCADE"), nullable=False
    )
    from_slug: Mapped[str] = mapped_column(Text, nullable=False)
    to_slug: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FunnelDomain(Base):
    __tablename__ = "funnel_domains"
    __table_args__ = (
        UniqueConstraint("hostname", name="uq_funnel_domains_hostname"),
        sa.Index("idx_funnel_domains_funnel", "funnel_id"),
        sa.Index("idx_funnel_domains_org_client", "org_id", "client_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    funnel_id: Mapped[str] = mapped_column(
        ForeignKey("funnels.id", ondelete="CASCADE"), nullable=False
    )
    hostname: Mapped[str] = mapped_column(CITEXT(), nullable=False)
    status: Mapped[FunnelDomainStatusEnum] = mapped_column(
        Enum(FunnelDomainStatusEnum, name="funnel_domain_status"),
        nullable=False,
        server_default=FunnelDomainStatusEnum.pending.value,
    )
    verification_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FunnelAsset(Base):
    __tablename__ = "funnel_assets"
    __table_args__ = (
        UniqueConstraint("public_id", name="uq_funnel_assets_public_id"),
        sa.Index("idx_funnel_assets_org_client", "org_id", "client_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    public_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, default=uuid4)
    kind: Mapped[FunnelAssetKindEnum] = mapped_column(
        Enum(FunnelAssetKindEnum, name="funnel_asset_kind"), nullable=False
    )
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    alt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[FunnelAssetSourceEnum] = mapped_column(
        Enum(FunnelAssetSourceEnum, name="funnel_asset_source"),
        nullable=False,
        server_default=FunnelAssetSourceEnum.upload.value,
    )
    ai_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    status: Mapped[FunnelAssetStatusEnum] = mapped_column(
        Enum(FunnelAssetStatusEnum, name="funnel_asset_status"),
        nullable=False,
        server_default=FunnelAssetStatusEnum.pending.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FunnelEvent(Base):
    __tablename__ = "funnel_events"
    __table_args__ = (
        sa.Index("idx_funnel_events_occurred_at", "occurred_at"),
        sa.Index("idx_funnel_events_funnel_pub", "funnel_id", "publication_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    funnel_id: Mapped[str] = mapped_column(
        ForeignKey("funnels.id", ondelete="CASCADE"), nullable=False
    )
    publication_id: Mapped[str] = mapped_column(
        ForeignKey("funnel_publications.id", ondelete="CASCADE"), nullable=False
    )
    page_id: Mapped[str] = mapped_column(
        ForeignKey("funnel_pages.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[FunnelEventTypeEnum] = mapped_column(
        Enum(FunnelEventTypeEnum, name="funnel_event_type"), nullable=False
    )
    visitor_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    host: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    referrer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    utm: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    props: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[ArtifactTypeEnum] = mapped_column(Enum(ArtifactTypeEnum, name="artifact_type"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by_user: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ClaudeContextFile(Base):
    __tablename__ = "claude_context_files"
    __table_args__ = (
        UniqueConstraint(
            "org_id",
            "idea_workspace_id",
            "doc_key",
            "sha256",
            name="uq_claude_context_workspace_doc_hash",
        ),
        sa.Index("idx_claude_ctx_org_workspace", "org_id", "idea_workspace_id"),
        sa.Index("idx_claude_ctx_client", "client_id"),
        sa.Index("idx_claude_ctx_campaign", "campaign_id"),
        sa.Index("idx_claude_ctx_doc_key", "doc_key"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    idea_workspace_id: Mapped[str] = mapped_column(Text, nullable=False)
    client_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"), nullable=True
    )
    campaign_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    doc_key: Mapped[str] = mapped_column(Text, nullable=False)
    doc_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    step_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    claude_file_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    filename: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    drive_doc_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    drive_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[ClaudeContextFileStatusEnum] = mapped_column(
        Enum(ClaudeContextFileStatusEnum, name="claude_context_file_status"),
        nullable=False,
        server_default=ClaudeContextFileStatusEnum.ready.value,
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    experiment_spec_artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="planned")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    experiment_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True
    )
    asset_brief_artifact_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True
    )
    variant_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_type: Mapped[AssetSourceEnum] = mapped_column(
        Enum(AssetSourceEnum, name="asset_source_type"), nullable=False
    )
    status: Mapped[AssetStatusEnum] = mapped_column(
        Enum(AssetStatusEnum, name="asset_status"),
        nullable=False,
        server_default=AssetStatusEnum.draft.value,
    )
    channel_id: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str] = mapped_column(Text, nullable=False)
    icp_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    funnel_stage_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    concept_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    angle_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AssetPerformanceSnapshot(Base):
    __tablename__ = "asset_performance_snapshots"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    experiment_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True
    )
    time_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    time_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    segments: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CompanySwipeBrand(Base):
    __tablename__ = "company_swipe_brands"
    __table_args__ = (UniqueConstraint("org_id", "external_brand_id", name="uq_company_swipe_brand_org_ext"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    external_brand_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ad_library_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    brand_page_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    categories: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CompanySwipeAsset(Base):
    __tablename__ = "company_swipe_assets"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    external_ad_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    external_platform_ad_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    brand_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("company_swipe_brands.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    platforms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cta_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cta_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    display_format: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    landing_page: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    link_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ad_source_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    days_active: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    active_in_library: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    active: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    used_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    saved_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    likes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    winning_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    winning_score_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    performance_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    performance_score_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    age_audience_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    age_audience_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gender_audience: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    eu_total_reach: Mapped[Optional[Numeric]] = mapped_column(Numeric, nullable=True)
    ad_spend_range_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ad_spend_range_score_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    added_human_time: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_by_user_human_time: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    saved_by_this_user: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    share_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embed_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_aaa_eligible: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    is_saved: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    is_used: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    is_liked: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    ad_script: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    ad_reach_by_location: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    ad_spend: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    ad_library_object: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CompanySwipeMedia(Base):
    __tablename__ = "company_swipe_media"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    swipe_asset_id: Mapped[str] = mapped_column(
        ForeignKey("company_swipe_assets.id", ondelete="CASCADE"), nullable=False
    )
    external_media_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    disk: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(sa.BigInteger, nullable=True)
    video_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    download_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ClientSwipeAsset(Base):
    __tablename__ = "client_swipe_assets"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    company_swipe_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("company_swipe_assets.id", ondelete="SET NULL"), nullable=True
    )
    custom_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    custom_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    custom_channel: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    custom_format: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    custom_landing_page: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    custom_media: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=sa.text("'{}'::text[]"), nullable=False
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_good_example: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    is_bad_example: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    client_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"), nullable=True
    )
    campaign_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    temporal_workflow_id: Mapped[str] = mapped_column(Text, nullable=False)
    temporal_run_id: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[WorkflowKindEnum] = mapped_column(
        Enum(WorkflowKindEnum, name="workflow_kind"), nullable=False
    )
    status: Mapped[WorkflowStatusEnum] = mapped_column(
        Enum(WorkflowStatusEnum, name="workflow_status"),
        nullable=False,
        server_default=WorkflowStatusEnum.running.value,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workflow_run_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False
    )
    step: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    payload_in: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    payload_out: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OnboardingPayload(Base):
    __tablename__ = "onboarding_payloads"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Brand(Base):
    __tablename__ = "brands"
    __table_args__ = (
        sa.Index(
            "uq_brands_org_domain",
            "org_id",
            "primary_domain",
            unique=True,
            postgresql_where=sa.text("primary_domain IS NOT NULL"),
        ),
        sa.Index(
            "uq_brands_org_normalized_name",
            "org_id",
            "normalized_name",
            unique=True,
            postgresql_where=sa.text("primary_domain IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(CITEXT(), nullable=False)
    primary_website_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    primary_domain: Mapped[Optional[str]] = mapped_column(CITEXT(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BrandChannelIdentity(Base):
    __tablename__ = "brand_channel_identities"
    __table_args__ = (
        sa.Index(
            "idx_brand_channel_identities_channel_external_id",
            "channel",
            "external_id",
            unique=False,
        ),
        sa.Index(
            "idx_brand_channel_identities_brand_channel",
            "brand_id",
            "channel",
            unique=False,
        ),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    brand_id: Mapped[str] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[AdChannelEnum] = mapped_column(
        Enum(AdChannelEnum, name="ad_channel"), nullable=False
    )
    external_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    external_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    verification_status: Mapped[BrandChannelVerificationStatusEnum] = mapped_column(
        Enum(BrandChannelVerificationStatusEnum, name="brand_channel_verification_status"),
        nullable=False,
        server_default=BrandChannelVerificationStatusEnum.unverified.value,
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[Optional[Numeric]] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BrandUserPreference(Base):
    __tablename__ = "brand_user_preferences"
    __table_args__ = (
        UniqueConstraint("org_id", "user_external_id", "brand_id", name="uq_brand_user_pref"),
        sa.Index("idx_brand_user_pref_user", "org_id", "user_external_id"),
        sa.Index("idx_brand_user_pref_brand", "brand_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), nullable=False)
    user_external_id: Mapped[str] = mapped_column(Text, nullable=False)
    hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ResearchRun(Base):
    __tablename__ = "research_runs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    campaign_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    brand_discovery_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    ads_context: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    ads_context_generated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ResearchRunBrand(Base):
    __tablename__ = "research_run_brands"
    __table_args__ = (UniqueConstraint("research_run_id", "brand_id", name="uq_run_brand"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    research_run_id: Mapped[str] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False
    )
    brand_id: Mapped[str] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[BrandRoleEnum] = mapped_column(
        Enum(BrandRoleEnum, name="brand_role"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DeepResearchJob(Base):
    __tablename__ = "deep_research_jobs"
    __table_args__ = (
        sa.Index(
            "idx_deep_research_jobs_response_id",
            "response_id",
            unique=True,
            postgresql_where=sa.text("response_id IS NOT NULL"),
        ),
        sa.Index("idx_deep_research_jobs_org_client", "org_id", "client_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    workflow_run_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True
    )
    onboarding_payload_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("onboarding_payloads.id", ondelete="SET NULL"), nullable=True
    )
    temporal_workflow_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    step_key: Mapped[str] = mapped_column(Text, nullable=False, server_default="04")
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_sha256: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    use_web_search: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("false")
    )
    max_output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[ResearchJobStatusEnum] = mapped_column(
        Enum(ResearchJobStatusEnum, name="research_job_status"),
        nullable=False,
        server_default=ResearchJobStatusEnum.created.value,
    )
    output_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    full_response_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    incomplete_details: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    last_webhook_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        sa.Index(
            "uq_jobs_dedupe_key",
            "dedupe_key",
            unique=True,
            postgresql_where=sa.text("dedupe_key IS NOT NULL"),
        ),
        sa.Index("idx_jobs_type_status", "job_type", "status"),
        sa.Index("idx_jobs_subject", "subject_type", "subject_id"),
        sa.Index("idx_jobs_research_run", "research_run_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    client_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=True,
    )
    research_run_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("research_runs.id", ondelete="SET NULL"),
        nullable=True,
    )

    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)

    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    dedupe_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    input: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    output: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    raw_output_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class AdIngestRun(Base):
    __tablename__ = "ad_ingest_runs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    research_run_id: Mapped[str] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False
    )
    brand_channel_identity_id: Mapped[str] = mapped_column(
        ForeignKey("brand_channel_identities.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[AdChannelEnum] = mapped_column(
        Enum(AdChannelEnum, name="ad_channel"), nullable=False
    )
    requested_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False, server_default="APIFY")
    provider_actor_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider_run_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider_dataset_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[AdIngestStatusEnum] = mapped_column(
        Enum(AdIngestStatusEnum, name="ad_ingest_status"),
        nullable=False,
        server_default=AdIngestStatusEnum.RUNNING.value,
    )
    is_partial: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.text("false"))
    results_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    items_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Ad(Base):
    __tablename__ = "ads"
    __table_args__ = (
        UniqueConstraint("channel", "external_ad_id", name="uq_ads_channel_external_id"),
        sa.Index("idx_ads_brand_channel_identity", "brand_channel_identity_id"),
        sa.Index("idx_ads_brand", "brand_id"),
        sa.Index("idx_ads_last_seen", "last_seen_at"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), nullable=False)
    brand_channel_identity_id: Mapped[str] = mapped_column(
        ForeignKey("brand_channel_identities.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[AdChannelEnum] = mapped_column(
        Enum(AdChannelEnum, name="ad_channel"), nullable=False
    )
    external_ad_id: Mapped[str] = mapped_column(Text, nullable=False)
    ad_status: Mapped[AdStatusEnum] = mapped_column(
        Enum(AdStatusEnum, name="ad_status"), nullable=False, server_default=AdStatusEnum.unknown.value
    )
    started_running_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_running_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    body_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    headline: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cta_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cta_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    landing_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    destination_domain: Mapped[Optional[str]] = mapped_column(CITEXT(), nullable=True)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AdFacts(Base):
    __tablename__ = "ad_facts"
    __table_args__ = (
        sa.Index("idx_ad_facts_org", "org_id"),
        sa.Index("idx_ad_facts_brand", "brand_id"),
        sa.Index("idx_ad_facts_channel", "channel"),
        sa.Index("idx_ad_facts_status", "status"),
        sa.Index("idx_ad_facts_start_date", "start_date"),
        sa.Index("idx_ad_facts_days_active", "days_active"),
        sa.Index("idx_ad_facts_video_length", "video_length_seconds"),
        sa.Index("idx_ad_facts_media_types", "media_types", postgresql_using="gin"),
        sa.Index("idx_ad_facts_language_codes", "language_codes", postgresql_using="gin"),
        sa.Index("idx_ad_facts_country_codes", "country_codes", postgresql_using="gin"),
    )

    ad_id: Mapped[str] = mapped_column(ForeignKey("ads.id", ondelete="CASCADE"), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), nullable=False)
    channel: Mapped[AdChannelEnum] = mapped_column(
        Enum(AdChannelEnum, name="ad_channel"), nullable=False
    )
    status: Mapped[AdStatusEnum] = mapped_column(
        Enum(AdStatusEnum, name="ad_status"),
        nullable=False,
        server_default=AdStatusEnum.unknown.value,
    )
    display_format: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media_types: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=sa.text("'{}'::text[]")
    )
    video_length_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    language_codes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=sa.text("'{}'::text[]")
    )
    country_codes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=sa.text("'{}'::text[]")
    )
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    days_active: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AdScore(Base):
    __tablename__ = "ad_scores"
    __table_args__ = (
        sa.Index("idx_ad_scores_org", "org_id"),
        sa.Index("idx_ad_scores_brand", "brand_id"),
        sa.Index("idx_ad_scores_channel", "channel"),
    )

    ad_id: Mapped[str] = mapped_column(ForeignKey("ads.id", ondelete="CASCADE"), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), nullable=False)
    channel: Mapped[AdChannelEnum] = mapped_column(
        Enum(AdChannelEnum, name="ad_channel"), nullable=False
    )
    score_version: Mapped[str] = mapped_column(Text, nullable=False, server_default="v1")
    performance_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    performance_stars: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    winning_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    confidence: Mapped[Optional[Numeric]] = mapped_column(Numeric, nullable=True)
    score_breakdown: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        sa.Index(
            "uq_media_assets_sha256",
            "sha256",
            unique=True,
            postgresql_where=sa.text("sha256 IS NOT NULL"),
        ),
        sa.Index(
            "uq_media_assets_channel_source_url",
            "channel",
            "source_url",
            unique=True,
            postgresql_where=sa.text("source_url IS NOT NULL"),
        ),
        sa.Index(
            "uq_media_assets_storage_key",
            "storage_key",
            unique=True,
            postgresql_where=sa.text("storage_key IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    channel: Mapped[AdChannelEnum] = mapped_column(
        Enum(AdChannelEnum, name="ad_channel"), nullable=False
    )
    asset_type: Mapped[MediaAssetTypeEnum] = mapped_column(
        Enum(MediaAssetTypeEnum, name="media_asset_type"), nullable=False
    )
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stored_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    storage_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    preview_storage_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bucket: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    preview_bucket: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mirror_status: Mapped[MediaMirrorStatusEnum] = mapped_column(
        Enum(MediaMirrorStatusEnum, name="media_mirror_status"),
        nullable=False,
        default=MediaMirrorStatusEnum.pending,
        server_default=MediaMirrorStatusEnum.pending.value,
    )
    mirror_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mirrored_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sha256: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AdAssetLink(Base):
    __tablename__ = "ad_asset_links"
    __table_args__ = (UniqueConstraint("ad_id", "media_asset_id", name="uq_ad_media_link"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    ad_id: Mapped[str] = mapped_column(ForeignKey("ads.id", ondelete="CASCADE"), nullable=False)
    media_asset_id: Mapped[str] = mapped_column(
        ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AdCreative(Base):
    __tablename__ = "ad_creatives"
    __table_args__ = (
        UniqueConstraint(
            "org_id",
            "brand_id",
            "channel",
            "fingerprint_algo",
            "creative_fingerprint",
            name="uq_ad_creatives_fingerprint",
        ),
        sa.Index("idx_ad_creatives_org_brand", "org_id", "brand_id"),
        sa.Index(
            "idx_ad_creatives_org_brand_media_fp",
            "org_id",
            "brand_id",
            "media_fingerprint",
            postgresql_where=sa.text("media_fingerprint IS NOT NULL"),
        ),
        sa.Index(
            "idx_ad_creatives_org_brand_copy_fp",
            "org_id",
            "brand_id",
            "copy_fingerprint",
            postgresql_where=sa.text("copy_fingerprint IS NOT NULL"),
        ),
        sa.Index("idx_ad_creatives_org_creative_fp", "org_id", "creative_fingerprint"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), nullable=False)
    channel: Mapped[AdChannelEnum] = mapped_column(
        Enum(AdChannelEnum, name="ad_channel"), nullable=False
    )
    fingerprint_algo: Mapped[str] = mapped_column(Text, nullable=False)
    creative_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    primary_media_asset_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    media_fingerprint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    copy_fingerprint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AdCreativeMembership(Base):
    __tablename__ = "ad_creative_memberships"
    __table_args__ = (
        UniqueConstraint("ad_id", name="uq_ad_creative_memberships_ad"),
        UniqueConstraint("creative_id", "ad_id", name="uq_ad_creative_memberships_creative_ad"),
        sa.Index("idx_ad_creative_memberships_creative", "creative_id"),
        sa.Index("idx_ad_creative_memberships_ad", "ad_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    creative_id: Mapped[str] = mapped_column(
        ForeignKey("ad_creatives.id", ondelete="CASCADE"), nullable=False
    )
    ad_id: Mapped[str] = mapped_column(ForeignKey("ads.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AdTeardown(Base):
    __tablename__ = "ad_teardowns"
    __table_args__ = (
        sa.Index("idx_ad_teardowns_creative", "creative_id"),
        sa.Index("idx_ad_teardowns_org_client", "org_id", "client_id"),
        sa.Index("idx_ad_teardowns_raw_payload_gin", "raw_payload", postgresql_using="gin"),
        sa.Index(
            "uq_ad_teardowns_org_creative_canonical",
            "org_id",
            "creative_id",
            unique=True,
            postgresql_where=sa.text("is_canonical = true"),
        ),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    creative_id: Mapped[str] = mapped_column(
        ForeignKey("ad_creatives.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"), nullable=True
    )
    campaign_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    research_run_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("research_runs.id", ondelete="SET NULL"), nullable=True
    )
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    captured_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    funnel_stage: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    one_liner: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    algorithmic_thesis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hook_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    is_canonical: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AdTeardownEvidenceItem(Base):
    __tablename__ = "ad_teardown_evidence_items"
    __table_args__ = (
        sa.Index(
            "idx_ad_teardown_evidence_items_teardown_type",
            "teardown_id",
            "evidence_type",
        ),
        sa.Index(
            "idx_ad_teardown_evidence_items_teardown_start",
            "teardown_id",
            "start_ms",
        ),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    teardown_id: Mapped[str] = mapped_column(
        ForeignKey("ad_teardowns.id", ondelete="CASCADE"), nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(Text, nullable=False)
    start_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    end_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AdTeardownTranscriptSegment(Base):
    __tablename__ = "ad_teardown_transcript_segments"

    evidence_item_id: Mapped[str] = mapped_column(
        ForeignKey("ad_teardown_evidence_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    speaker_role: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    spoken_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    onscreen_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    audio_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AdTeardownStoryboardScene(Base):
    __tablename__ = "ad_teardown_storyboard_scenes"

    evidence_item_id: Mapped[str] = mapped_column(
        ForeignKey("ad_teardown_evidence_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    scene_no: Mapped[int] = mapped_column(Integer, nullable=False)
    visual_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    action_blocking: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    narrative_job: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    onscreen_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AdTeardownNumericClaim(Base):
    __tablename__ = "ad_teardown_numeric_claims"

    evidence_item_id: Mapped[str] = mapped_column(
        ForeignKey("ad_teardown_evidence_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    value_numeric: Mapped[Optional[Numeric]] = mapped_column(Numeric, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_topic: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=sa.text("'unverified'")
    )
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AdTeardownTargetingSignal(Base):
    __tablename__ = "ad_teardown_targeting_signals"

    evidence_item_id: Mapped[str] = mapped_column(
        ForeignKey("ad_teardown_evidence_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    modality: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    is_observation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("true")
    )
    confidence: Mapped[Optional[Numeric]] = mapped_column(Numeric, nullable=True)


class AdTeardownNarrativeBeat(Base):
    __tablename__ = "ad_teardown_narrative_beats"

    evidence_item_id: Mapped[str] = mapped_column(
        ForeignKey("ad_teardown_evidence_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    beat_key: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class AdTeardownProofUsage(Base):
    __tablename__ = "ad_teardown_proof_usages"

    evidence_item_id: Mapped[str] = mapped_column(
        ForeignKey("ad_teardown_evidence_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    proof_type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AdTeardownCTA(Base):
    __tablename__ = "ad_teardown_ctas"

    evidence_item_id: Mapped[str] = mapped_column(
        ForeignKey("ad_teardown_evidence_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    cta_kind: Mapped[str] = mapped_column(Text, nullable=False)
    cta_text: Mapped[str] = mapped_column(Text, nullable=False)
    offer_stack_present: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    risk_reversal_present: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AdTeardownProductionRequirement(Base):
    __tablename__ = "ad_teardown_production_requirements"

    evidence_item_id: Mapped[str] = mapped_column(
        ForeignKey("ad_teardown_evidence_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    req_type: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class AdTeardownAdCopyBlock(Base):
    __tablename__ = "ad_teardown_ad_copy_blocks"

    evidence_item_id: Mapped[str] = mapped_column(
        ForeignKey("ad_teardown_evidence_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    field: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AdTeardownAssertion(Base):
    __tablename__ = "ad_teardown_assertions"
    __table_args__ = (
        sa.Index("idx_ad_teardown_assertions_type", "teardown_id", "assertion_type"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    teardown_id: Mapped[str] = mapped_column(
        ForeignKey("ad_teardowns.id", ondelete="CASCADE"), nullable=False
    )
    assertion_type: Mapped[str] = mapped_column(Text, nullable=False)
    assertion_text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Optional[Numeric]] = mapped_column(Numeric, nullable=True)
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AdTeardownAssertionEvidence(Base):
    __tablename__ = "ad_teardown_assertion_evidence"
    __table_args__ = (
        UniqueConstraint(
            "assertion_id",
            "evidence_item_id",
            name="uq_ad_assertion_evidence_pair",
        ),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    assertion_id: Mapped[str] = mapped_column(
        ForeignKey("ad_teardown_assertions.id", ondelete="CASCADE"), nullable=False
    )
    evidence_item_id: Mapped[str] = mapped_column(
        ForeignKey("ad_teardown_evidence_items.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
