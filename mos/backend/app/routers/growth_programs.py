"""Content growth program API routes."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.models import Client
from app.db.repositories.connected_social import AgentActionProposalsRepository
from app.db.repositories.growth_programs import GrowthProgramsRepository
from app.schemas.growth_programs import (
    ContentExperimentCreateRequest,
    ContentExperimentResponse,
    ContentGrowthProgramCreateRequest,
    ContentGrowthProgramResponse,
    ContentVariantApproveRequest,
    ContentVariantCreateRequest,
    ContentVariantPostizProposalCreateRequest,
    ContentVariantPostizProposalResponse,
    ContentVariantResponse,
    ContentVariantSlideResponse,
    ConversionEventCreateRequest,
    ConversionSourceCreateRequest,
    ConversionSourceResponse,
)


router = APIRouter(prefix="/clients/{client_id}/growth-programs", tags=["growth-programs"])


def _require_client(session: Session, *, org_id: str, client_id: str) -> Client:
    client = session.scalars(
        select(Client).where(Client.id == client_id, Client.org_id == org_id)
    ).first()
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found.")
    return client


def _serialize_conversion_source(source) -> ConversionSourceResponse:
    return ConversionSourceResponse.model_validate(
        {
            "id": str(source.id),
            "provider": source.provider,
            "name": source.name,
            "status": source.status,
            "goalEvents": list(source.goal_events_json or []),
            "config": source.config_json or {},
            "credentialsMetadata": source.credentials_metadata_json or {},
            "lastSyncedAt": source.last_synced_at,
            "lastError": source.last_error,
            "createdAt": source.created_at,
            "updatedAt": source.updated_at,
        }
    )


def _serialize_program(program) -> ContentGrowthProgramResponse:
    return ContentGrowthProgramResponse.model_validate(
        {
            "id": str(program.id),
            "productId": str(program.product_id) if program.product_id else None,
            "campaignId": str(program.campaign_id) if program.campaign_id else None,
            "conversionSourceId": str(program.conversion_source_id) if program.conversion_source_id else None,
            "name": program.name,
            "objective": program.objective,
            "platformKey": program.platform_key,
            "formatKey": program.format_key,
            "authorityMode": program.authority_mode,
            "status": program.status,
            "settings": program.settings_json or {},
            "metadata": program.metadata_json or {},
            "createdAt": program.created_at,
            "updatedAt": program.updated_at,
        }
    )


def _serialize_experiment(experiment) -> ContentExperimentResponse:
    return ContentExperimentResponse.model_validate(
        {
            "id": str(experiment.id),
            "growthProgramId": str(experiment.growth_program_id),
            "name": experiment.name,
            "hypothesis": experiment.hypothesis,
            "hookFamily": experiment.hook_family,
            "ctaFamily": experiment.cta_family,
            "audience": experiment.audience,
            "status": experiment.status,
            "metadata": experiment.metadata_json or {},
            "createdAt": experiment.created_at,
            "updatedAt": experiment.updated_at,
        }
    )


def _serialize_slide(slide) -> ContentVariantSlideResponse:
    return ContentVariantSlideResponse.model_validate(
        {
            "id": str(slide.id),
            "slideIndex": slide.slide_index,
            "visualRole": slide.visual_role,
            "prompt": slide.prompt,
            "overlayText": slide.overlay_text,
            "sourceAssetId": str(slide.source_asset_id) if slide.source_asset_id else None,
            "renderedAssetId": str(slide.rendered_asset_id) if slide.rendered_asset_id else None,
            "renderStatus": slide.render_status,
            "rendererVersion": slide.renderer_version,
            "metadata": slide.metadata_json or {},
            "createdAt": slide.created_at,
            "updatedAt": slide.updated_at,
        }
    )


def _serialize_variant(repo: GrowthProgramsRepository, variant) -> ContentVariantResponse:
    slides = repo.list_slides(org_id=str(variant.org_id), variant_id=str(variant.id))
    return ContentVariantResponse.model_validate(
        {
            "id": str(variant.id),
            "growthProgramId": str(variant.growth_program_id),
            "experimentId": str(variant.experiment_id) if variant.experiment_id else None,
            "platformKey": variant.platform_key,
            "formatKey": variant.format_key,
            "title": variant.title,
            "caption": variant.caption,
            "cta": variant.cta,
            "slideCount": variant.slide_count,
            "status": variant.status,
            "approvedByUserId": variant.approved_by_user_id,
            "approvedAt": variant.approved_at,
            "storyboard": variant.storyboard_json or {},
            "providerPayload": variant.provider_payload_json or {},
            "metadata": variant.metadata_json or {},
            "slides": [_serialize_slide(slide) for slide in slides],
            "createdAt": variant.created_at,
            "updatedAt": variant.updated_at,
        }
    )


@router.get("")
def list_programs(
    client_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = GrowthProgramsRepository(session)
    return jsonable_encoder(
        [_serialize_program(program) for program in repo.list_programs(org_id=auth.org_id, client_id=client_id)]
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_program(
    client_id: str,
    payload: ContentGrowthProgramCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = GrowthProgramsRepository(session)
    program = repo.create_program(
        org_id=auth.org_id,
        client_id=client_id,
        product_id=payload.product_id,
        campaign_id=payload.campaign_id,
        conversion_source_id=payload.conversion_source_id,
        name=payload.name,
        objective=payload.objective,
        platform_key=payload.platform_key,
        format_key=payload.format_key,
        authority_mode=payload.authority_mode,
        status=payload.status,
        settings_json=payload.settings,
        metadata_json=payload.metadata,
    )
    session.commit()
    return jsonable_encoder(_serialize_program(program))


@router.post("/{program_id}/conversion-sources", status_code=status.HTTP_201_CREATED)
def create_conversion_source(
    client_id: str,
    program_id: str,
    payload: ConversionSourceCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = GrowthProgramsRepository(session)
    program = repo.get_program(org_id=auth.org_id, program_id=program_id)
    if program is None or str(program.client_id) != str(client_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Growth program not found.")
    source = repo.create_conversion_source(
        org_id=auth.org_id,
        client_id=client_id,
        provider=payload.provider,
        name=payload.name,
        status=payload.status,
        goal_events_json=payload.goal_events,
        config_json=payload.config,
        credentials_metadata_json=payload.credentials_metadata,
    )
    program.conversion_source_id = source.id
    session.commit()
    return jsonable_encoder(_serialize_conversion_source(source))


@router.get("/{program_id}/conversion-sources")
def list_conversion_sources(
    client_id: str,
    program_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = GrowthProgramsRepository(session)
    program = repo.get_program(org_id=auth.org_id, program_id=program_id)
    if program is None or str(program.client_id) != str(client_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Growth program not found.")
    return jsonable_encoder(
        [_serialize_conversion_source(source) for source in repo.list_conversion_sources(org_id=auth.org_id, client_id=client_id)]
    )


@router.post("/{program_id}/experiments", status_code=status.HTTP_201_CREATED)
def create_experiment(
    client_id: str,
    program_id: str,
    payload: ContentExperimentCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = GrowthProgramsRepository(session)
    program = repo.get_program(org_id=auth.org_id, program_id=program_id)
    if program is None or str(program.client_id) != str(client_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Growth program not found.")
    experiment = repo.create_experiment(
        org_id=auth.org_id,
        client_id=client_id,
        growth_program_id=program_id,
        name=payload.name,
        hypothesis=payload.hypothesis,
        hook_family=payload.hook_family,
        cta_family=payload.cta_family,
        audience=payload.audience,
        status=payload.status,
        metadata_json=payload.metadata,
    )
    session.commit()
    return jsonable_encoder(_serialize_experiment(experiment))


@router.get("/{program_id}/experiments")
def list_experiments(
    client_id: str,
    program_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = GrowthProgramsRepository(session)
    program = repo.get_program(org_id=auth.org_id, program_id=program_id)
    if program is None or str(program.client_id) != str(client_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Growth program not found.")
    return jsonable_encoder(
        [_serialize_experiment(experiment) for experiment in repo.list_experiments(org_id=auth.org_id, growth_program_id=program_id)]
    )


@router.post("/{program_id}/variants", status_code=status.HTTP_201_CREATED)
def create_variant(
    client_id: str,
    program_id: str,
    payload: ContentVariantCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = GrowthProgramsRepository(session)
    program = repo.get_program(org_id=auth.org_id, program_id=program_id)
    if program is None or str(program.client_id) != str(client_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Growth program not found.")
    if payload.experiment_id:
        experiment = repo.get_experiment(org_id=auth.org_id, experiment_id=payload.experiment_id)
        if experiment is None or str(experiment.growth_program_id) != str(program_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experiment not found.")
    slides = [
        {
            "slide_index": slide.slide_index,
            "visual_role": slide.visual_role,
            "prompt": slide.prompt,
            "overlay_text": slide.overlay_text,
            "source_asset_id": slide.source_asset_id,
            "rendered_asset_id": slide.rendered_asset_id,
            "render_status": slide.render_status,
            "renderer_version": slide.renderer_version,
            "metadata_json": slide.metadata,
        }
        for slide in payload.slides
    ]
    variant = repo.create_variant(
        org_id=auth.org_id,
        client_id=client_id,
        growth_program_id=program_id,
        experiment_id=payload.experiment_id,
        platform_key=payload.platform_key,
        format_key=payload.format_key,
        title=payload.title,
        caption=payload.caption,
        cta=payload.cta,
        slide_count=payload.slide_count,
        status=payload.status,
        storyboard_json=payload.storyboard,
        provider_payload_json=payload.provider_payload,
        metadata_json=payload.metadata,
        slides=slides,
    )
    session.commit()
    return jsonable_encoder(_serialize_variant(repo, variant))


@router.get("/{program_id}/variants")
def list_variants(
    client_id: str,
    program_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = GrowthProgramsRepository(session)
    program = repo.get_program(org_id=auth.org_id, program_id=program_id)
    if program is None or str(program.client_id) != str(client_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Growth program not found.")
    return jsonable_encoder(
        [_serialize_variant(repo, variant) for variant in repo.list_variants(org_id=auth.org_id, growth_program_id=program_id)]
    )


@router.post("/{program_id}/variants/{variant_id}/approve")
def approve_variant(
    client_id: str,
    program_id: str,
    variant_id: str,
    payload: ContentVariantApproveRequest | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = GrowthProgramsRepository(session)
    variant = repo.get_variant(org_id=auth.org_id, variant_id=variant_id)
    if variant is None or str(variant.client_id) != str(client_id) or str(variant.growth_program_id) != str(program_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content variant not found.")
    if variant.status not in {"draft", "review"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only draft/review variants can be approved.")
    approved = repo.approve_variant(
        org_id=auth.org_id,
        variant_id=variant_id,
        approved_by_user_id=auth.user_id,
        notes=payload.notes if payload else None,
    )
    session.commit()
    return jsonable_encoder(_serialize_variant(repo, approved))


@router.post(
    "/{program_id}/variants/{variant_id}/postiz-handoff-proposals",
    status_code=status.HTTP_201_CREATED,
)
def create_postiz_handoff_proposal(
    client_id: str,
    program_id: str,
    variant_id: str,
    payload: ContentVariantPostizProposalCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = GrowthProgramsRepository(session)
    program = repo.get_program(org_id=auth.org_id, program_id=program_id)
    if program is None or str(program.client_id) != str(client_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Growth program not found.")
    variant = repo.get_variant(org_id=auth.org_id, variant_id=variant_id)
    if variant is None or str(variant.growth_program_id) != str(program_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content variant not found.")
    if variant.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Content variant must be approved before creating a Postiz handoff proposal.",
        )

    content = next(
        (
            str(part).strip()
            for part in (payload.content, variant.caption, variant.cta, variant.title)
            if str(part or "").strip()
        ),
        None,
    )
    if content is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Content variant needs caption/title text or explicit content before Postiz handoff.",
        )
    if payload.post_type in {"now", "schedule"} and not payload.channel_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="channelIds is required when postType is now or schedule.",
        )
    if variant.format_key == "tiktok_carousel" and len(payload.media_urls) != int(variant.slide_count):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="TikTok carousel Postiz handoff requires mediaUrls count to match slideCount.",
        )

    postiz_payload = {
        "source": "mos_growth_program_variant",
        "growthProgramId": str(program.id),
        "variantId": str(variant.id),
        "platformKey": variant.platform_key,
        "formatKey": variant.format_key,
        "content": content,
        "postType": payload.post_type,
        "scheduledFor": payload.scheduled_for.isoformat() if payload.scheduled_for else None,
        "channelIds": payload.channel_ids,
        "mediaUrls": payload.media_urls,
        "linkUrl": payload.link_url,
        "postingProfileId": payload.posting_profile_id,
        "providerSettingsByIdentifier": payload.provider_settings_by_identifier,
        "slideCount": variant.slide_count,
        "storyboard": variant.storyboard_json or {},
        "postizOwnership": {
            "systemOfRecord": "postiz",
            "mosStores": "approval and handoff proposal only",
        },
    }
    proposal = AgentActionProposalsRepository(session).create(
        org_id=auth.org_id,
        client_id=client_id,
        campaign_id=str(program.campaign_id) if program.campaign_id else None,
        action_type="postiz.composer_handoff",
        target_provider="postiz",
        target_asset_id=payload.channel_ids[0] if payload.channel_ids else payload.posting_profile_id,
        target_asset_type="postiz_channel" if payload.channel_ids else "postiz_composer",
        before_snapshot_json={"variantStatus": variant.status, "existingPostizPostId": None},
        proposed_after_json={"postizPayload": postiz_payload},
        rationale="Approved content variant is ready for Postiz-owned composer, scheduling, and publishing.",
        risk_label="medium",
        required_capability="postiz.compose",
        rollback_hint_json={
            "owner": "postiz",
            "instruction": "Cancel, edit, or delete the draft inside Postiz if the operator rejects it later.",
        },
        metadata_json={
            **(payload.metadata or {}),
            "growthProgramId": str(program.id),
            "variantId": str(variant.id),
            "postizSystemOfRecord": True,
        },
    )
    session.commit()
    return jsonable_encoder(
        ContentVariantPostizProposalResponse.model_validate(
            {
                "proposalId": str(proposal.id),
                "actionType": proposal.action_type,
                "targetProvider": proposal.target_provider,
                "growthProgramId": str(program.id),
                "variantId": str(variant.id),
                "status": proposal.status,
                "postizPayload": postiz_payload,
                "createdAt": proposal.created_at,
            }
        )
    )


@router.post("/{program_id}/conversion-events", status_code=status.HTTP_201_CREATED)
def create_conversion_event(
    client_id: str,
    program_id: str,
    payload: ConversionEventCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = GrowthProgramsRepository(session)
    program = repo.get_program(org_id=auth.org_id, program_id=program_id)
    if program is None or str(program.client_id) != str(client_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Growth program not found.")
    source = repo.get_conversion_source(org_id=auth.org_id, source_id=payload.conversion_source_id)
    if source is None or str(source.client_id) != str(client_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversion source not found.")
    try:
        event = repo.create_conversion_event(
            org_id=auth.org_id,
            client_id=client_id,
            conversion_source_id=payload.conversion_source_id,
            provider=source.provider,
            provider_event_id=payload.provider_event_id,
            event_name=payload.event_name,
            occurred_at=payload.occurred_at,
            value=Decimal(payload.value) if payload.value is not None else None,
            currency=payload.currency,
            user_id_hash=payload.user_id_hash,
            campaign_ref=payload.campaign_ref,
            content_experiment_id=payload.content_experiment_id,
            content_variant_id=payload.content_variant_id,
            postiz_post_id=payload.postiz_post_id,
            postiz_channel_id=payload.postiz_channel_id,
            attribution_json=payload.attribution,
            raw_payload_json=payload.raw_payload,
            provenance=payload.provenance,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    session.commit()
    return jsonable_encoder(
        {
            "id": str(event.id),
            "conversionSourceId": str(event.conversion_source_id),
            "provider": event.provider,
            "providerEventId": event.provider_event_id,
            "eventName": event.event_name,
            "occurredAt": event.occurred_at,
            "value": event.value,
            "currency": event.currency,
            "contentVariantId": str(event.content_variant_id) if event.content_variant_id else None,
            "postizPostId": event.postiz_post_id,
            "postizChannelId": event.postiz_channel_id,
            "provenance": event.provenance,
            "createdAt": event.created_at,
        }
    )
