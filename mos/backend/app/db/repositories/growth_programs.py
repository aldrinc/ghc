"""Repositories for content growth programs."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ContentExperiment,
    ContentGrowthProgram,
    ContentVariant,
    ContentVariantSlide,
    ConversionEvent,
    ConversionSource,
)


class GrowthProgramsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_program(
        self,
        *,
        org_id: str,
        client_id: str,
        name: str,
        objective: str,
        product_id: str | None = None,
        campaign_id: str | None = None,
        conversion_source_id: str | None = None,
        platform_key: str = "tiktok",
        format_key: str = "tiktok_carousel",
        authority_mode: str = "approval_required",
        status: str = "draft",
        settings_json: dict[str, Any] | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> ContentGrowthProgram:
        program = ContentGrowthProgram(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            conversion_source_id=conversion_source_id,
            name=name,
            objective=objective,
            platform_key=platform_key,
            format_key=format_key,
            authority_mode=authority_mode,
            status=status,
            settings_json=settings_json or {},
            metadata_json=metadata_json or {},
        )
        self.session.add(program)
        self.session.flush()
        self.session.refresh(program)
        return program

    def list_programs(self, *, org_id: str, client_id: str) -> list[ContentGrowthProgram]:
        stmt = (
            select(ContentGrowthProgram)
            .where(ContentGrowthProgram.org_id == org_id, ContentGrowthProgram.client_id == client_id)
            .order_by(ContentGrowthProgram.created_at.desc())
        )
        return list(self.session.scalars(stmt).all())

    def get_program(self, *, org_id: str, program_id: str) -> ContentGrowthProgram | None:
        stmt = select(ContentGrowthProgram).where(
            ContentGrowthProgram.id == program_id,
            ContentGrowthProgram.org_id == org_id,
        )
        return self.session.scalars(stmt).first()

    def create_conversion_source(
        self,
        *,
        org_id: str,
        client_id: str,
        provider: str,
        name: str,
        status: str = "draft",
        goal_events_json: list[str] | None = None,
        config_json: dict[str, Any] | None = None,
        credentials_metadata_json: dict[str, Any] | None = None,
    ) -> ConversionSource:
        source = ConversionSource(
            org_id=org_id,
            client_id=client_id,
            provider=provider,
            name=name,
            status=status,
            goal_events_json=goal_events_json or [],
            config_json=config_json or {},
            credentials_metadata_json=credentials_metadata_json or {},
        )
        self.session.add(source)
        self.session.flush()
        self.session.refresh(source)
        return source

    def list_conversion_sources(self, *, org_id: str, client_id: str) -> list[ConversionSource]:
        stmt = (
            select(ConversionSource)
            .where(ConversionSource.org_id == org_id, ConversionSource.client_id == client_id)
            .order_by(ConversionSource.created_at.desc())
        )
        return list(self.session.scalars(stmt).all())

    def get_conversion_source(self, *, org_id: str, source_id: str) -> ConversionSource | None:
        stmt = select(ConversionSource).where(
            ConversionSource.id == source_id,
            ConversionSource.org_id == org_id,
        )
        return self.session.scalars(stmt).first()

    def create_experiment(
        self,
        *,
        org_id: str,
        client_id: str,
        growth_program_id: str,
        name: str,
        hypothesis: str,
        hook_family: str | None = None,
        cta_family: str | None = None,
        audience: str | None = None,
        status: str = "draft",
        metadata_json: dict[str, Any] | None = None,
    ) -> ContentExperiment:
        experiment = ContentExperiment(
            org_id=org_id,
            client_id=client_id,
            growth_program_id=growth_program_id,
            name=name,
            hypothesis=hypothesis,
            hook_family=hook_family,
            cta_family=cta_family,
            audience=audience,
            status=status,
            metadata_json=metadata_json or {},
        )
        self.session.add(experiment)
        self.session.flush()
        self.session.refresh(experiment)
        return experiment

    def list_experiments(self, *, org_id: str, growth_program_id: str) -> list[ContentExperiment]:
        stmt = (
            select(ContentExperiment)
            .where(
                ContentExperiment.org_id == org_id,
                ContentExperiment.growth_program_id == growth_program_id,
            )
            .order_by(ContentExperiment.created_at.desc())
        )
        return list(self.session.scalars(stmt).all())

    def get_experiment(self, *, org_id: str, experiment_id: str) -> ContentExperiment | None:
        stmt = select(ContentExperiment).where(
            ContentExperiment.id == experiment_id,
            ContentExperiment.org_id == org_id,
        )
        return self.session.scalars(stmt).first()

    def create_variant(
        self,
        *,
        org_id: str,
        client_id: str,
        growth_program_id: str,
        experiment_id: str | None = None,
        platform_key: str = "tiktok",
        format_key: str = "tiktok_carousel",
        title: str | None = None,
        caption: str | None = None,
        cta: str | None = None,
        slide_count: int = 6,
        status: str = "draft",
        storyboard_json: dict[str, Any] | None = None,
        provider_payload_json: dict[str, Any] | None = None,
        metadata_json: dict[str, Any] | None = None,
        slides: list[dict[str, Any]] | None = None,
    ) -> ContentVariant:
        variant = ContentVariant(
            org_id=org_id,
            client_id=client_id,
            growth_program_id=growth_program_id,
            experiment_id=experiment_id,
            platform_key=platform_key,
            format_key=format_key,
            title=title,
            caption=caption,
            cta=cta,
            slide_count=slide_count,
            status=status,
            storyboard_json=storyboard_json or {},
            provider_payload_json=provider_payload_json or {},
            metadata_json=metadata_json or {},
        )
        self.session.add(variant)
        self.session.flush()
        for slide in slides or []:
            self.session.add(
                ContentVariantSlide(
                    org_id=org_id,
                    client_id=client_id,
                    variant_id=str(variant.id),
                    slide_index=slide["slide_index"],
                    visual_role=slide.get("visual_role"),
                    prompt=slide.get("prompt"),
                    overlay_text=slide["overlay_text"],
                    source_asset_id=slide.get("source_asset_id"),
                    rendered_asset_id=slide.get("rendered_asset_id"),
                    render_status=slide.get("render_status") or "draft",
                    renderer_version=slide.get("renderer_version"),
                    metadata_json=slide.get("metadata_json") or {},
                )
            )
        self.session.flush()
        self.session.refresh(variant)
        return variant

    def get_variant(self, *, org_id: str, variant_id: str) -> ContentVariant | None:
        stmt = select(ContentVariant).where(
            ContentVariant.id == variant_id,
            ContentVariant.org_id == org_id,
        )
        return self.session.scalars(stmt).first()

    def list_variants(self, *, org_id: str, growth_program_id: str) -> list[ContentVariant]:
        stmt = (
            select(ContentVariant)
            .where(ContentVariant.org_id == org_id, ContentVariant.growth_program_id == growth_program_id)
            .order_by(ContentVariant.created_at.desc())
        )
        return list(self.session.scalars(stmt).all())

    def list_slides(self, *, org_id: str, variant_id: str) -> list[ContentVariantSlide]:
        stmt = (
            select(ContentVariantSlide)
            .where(ContentVariantSlide.org_id == org_id, ContentVariantSlide.variant_id == variant_id)
            .order_by(ContentVariantSlide.slide_index.asc())
        )
        return list(self.session.scalars(stmt).all())

    def approve_variant(
        self,
        *,
        org_id: str,
        variant_id: str,
        approved_by_user_id: str,
        notes: str | None = None,
    ) -> ContentVariant | None:
        variant = self.get_variant(org_id=org_id, variant_id=variant_id)
        if variant is None:
            return None
        variant.status = "approved"
        variant.approved_by_user_id = approved_by_user_id
        variant.approved_at = datetime.now(timezone.utc)
        variant.updated_at = datetime.now(timezone.utc)
        if notes:
            variant.metadata_json = {**(variant.metadata_json or {}), "approvalNotes": notes}
        self.session.flush()
        self.session.refresh(variant)
        return variant

    def create_conversion_event(
        self,
        *,
        org_id: str,
        client_id: str,
        conversion_source_id: str,
        provider: str,
        provider_event_id: str,
        event_name: str,
        occurred_at: datetime,
        value: Decimal | None = None,
        currency: str | None = None,
        user_id_hash: str | None = None,
        campaign_ref: str | None = None,
        content_experiment_id: str | None = None,
        content_variant_id: str | None = None,
        postiz_post_id: str | None = None,
        postiz_channel_id: str | None = None,
        attribution_json: dict[str, Any] | None = None,
        raw_payload_json: dict[str, Any] | None = None,
        provenance: str = "concrete",
    ) -> ConversionEvent:
        source = self.get_conversion_source(org_id=org_id, source_id=conversion_source_id)
        if source is None:
            raise ValueError("Conversion source not found.")
        if content_variant_id is not None:
            variant = self.get_variant(org_id=org_id, variant_id=content_variant_id)
            if variant is None or str(variant.client_id) != str(client_id):
                raise ValueError("Content variant not found.")
        event = ConversionEvent(
            org_id=org_id,
            client_id=client_id,
            conversion_source_id=conversion_source_id,
            provider=provider,
            provider_event_id=provider_event_id,
            event_name=event_name,
            occurred_at=occurred_at,
            value=value,
            currency=currency,
            user_id_hash=user_id_hash,
            campaign_ref=campaign_ref,
            content_experiment_id=content_experiment_id,
            content_variant_id=content_variant_id,
            postiz_post_id=postiz_post_id,
            postiz_channel_id=postiz_channel_id,
            attribution_json=attribution_json or {},
            raw_payload_json=raw_payload_json or {},
            provenance=provenance,
        )
        self.session.add(event)
        self.session.flush()
        self.session.refresh(event)
        return event
