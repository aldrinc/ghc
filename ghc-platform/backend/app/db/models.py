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
    ArtifactTypeEnum,
    AssetSourceEnum,
    AssetStatusEnum,
    CampaignStatusEnum,
    ClientStatusEnum,
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
