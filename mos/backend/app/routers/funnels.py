from __future__ import annotations

import json
import mimetypes
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.config import settings
from app.db.deps import get_session
from app.db.enums import (
    ArtifactTypeEnum,
    FunnelDomainStatusEnum,
    FunnelPageReviewStatusEnum,
    FunnelPageVersionSourceEnum,
    FunnelPageVersionStatusEnum,
    FunnelStatusEnum,
)
from app.db.models import (
    Campaign,
    FunnelDomain,
    FunnelPageSlugRedirect,
    FunnelPageVersion,
    Product,
    ProductOffer,
)
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.design_systems import DesignSystemsRepository
from app.db.repositories.funnels import FunnelPageVersionsRepository, FunnelPagesRepository, FunnelsRepository
from app.schemas.funnels import (
    FunnelCreateRequest,
    FunnelDuplicateRequest,
    FunnelPageAIGenerateRequest,
    FunnelPageCreateRequest,
    FunnelPageSaveDraftRequest,
    FunnelPageTestimonialGenerateRequest,
    FunnelPageUpdateRequest,
    FunnelPublishRequest,
    FunnelTemplateDetail,
    FunnelTemplateSummary,
    FunnelUpdateRequest,
)
from app.services import deploy as deploy_service
from app.agent.funnel_objectives import (
    run_generate_page_draft,
    run_generate_page_draft_stream,
    run_generate_page_testimonials,
    run_publish_funnel,
)
from app.services.design_systems import resolve_design_system_tokens
from app.services.funnel_ai import AiAttachmentError
from app.services.funnel_templates import apply_template_assets, get_funnel_template, list_funnel_templates
from app.services.funnel_testimonials import (
    TestimonialGenerationError,
    TestimonialGenerationNotFoundError,
)
from app.services.funnels import (
    create_funnel_upload_asset,
    default_puck_data,
    duplicate_funnel,
    generate_unique_slug,
)

router = APIRouter(prefix="/funnels", tags=["funnels"])


_AI_ATTACHMENT_MAX_COUNT = int(os.getenv("AI_ATTACHMENT_MAX_COUNT", "8"))
_AI_ATTACHMENT_MAX_BYTES = int(os.getenv("AI_ATTACHMENT_MAX_BYTES", str(12 * 1024 * 1024)))
_AI_ATTACHMENT_ALLOWED_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/gif",
}


def _normalize_server_names(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in values:
        host = raw.strip().lower()
        if not host or host in seen:
            continue
        seen.add(host)
        normalized.append(host)
    return normalized


def _resolve_deploy_server_names(
    *,
    session: Session,
    org_id: str,
    funnel_id: str,
    requested_server_names: list[str],
) -> list[str]:
    requested = _normalize_server_names(requested_server_names)
    if requested:
        return requested

    rows = session.scalars(
        select(FunnelDomain.hostname).where(
            FunnelDomain.org_id == org_id,
            FunnelDomain.funnel_id == funnel_id,
            FunnelDomain.status.in_(
                [
                    FunnelDomainStatusEnum.active,
                    FunnelDomainStatusEnum.verified,
                ]
            ),
        )
    ).all()

    from_db = _normalize_server_names([str(hostname) for hostname in rows if hostname])
    if from_db:
        return from_db

    return []


def _deploy_access_urls(*, server_names: list[str], https_enabled: bool) -> list[str]:
    if not server_names:
        return []
    scheme = "https" if https_enabled else "http"
    return [f"{scheme}://{hostname}/" for hostname in server_names]


def _validate_design_system(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    design_system_id: str,
):
    design_systems_repo = DesignSystemsRepository(session)
    design_system = design_systems_repo.get(org_id=org_id, design_system_id=design_system_id)
    if not design_system:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Design system not found")
    if design_system.client_id and str(design_system.client_id) != str(client_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Design system must belong to the same client",
        )
    return design_system


@router.get("")
def list_funnels(
    clientId: str | None = None,
    productId: str | None = None,
    campaignId: str | None = None,
    experimentId: str | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list:
    if (clientId and not productId and campaignId is None) or (productId and not clientId):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="clientId and productId are required together unless campaignId is provided.",
        )
    repo = FunnelsRepository(session)
    campaign_is_null = campaignId == "null"
    campaign_id_value = None if campaign_is_null else campaignId
    return jsonable_encoder(
        repo.list(
            org_id=auth.org_id,
            client_id=clientId,
            product_id=productId,
            campaign_id=campaign_id_value,
            campaign_is_null=campaign_is_null if campaignId is not None else None,
            experiment_spec_id=experimentId,
        )
    )


@router.get("/templates", response_model=list[FunnelTemplateSummary])
def list_templates() -> list[FunnelTemplateSummary]:
    return [
        FunnelTemplateSummary(
            id=tmpl.template_id,
            name=tmpl.name,
            description=tmpl.description,
            previewImage=tmpl.preview_image,
        )
        for tmpl in list_funnel_templates()
    ]


@router.get("/templates/{template_id}", response_model=FunnelTemplateDetail)
def get_template(template_id: str) -> FunnelTemplateDetail:
    tmpl = get_funnel_template(template_id)
    if not tmpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return FunnelTemplateDetail(
        id=tmpl.template_id,
        name=tmpl.name,
        description=tmpl.description,
        previewImage=tmpl.preview_image,
        puckData=tmpl.puck_data,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_funnel(
    payload: FunnelCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    campaign_id = payload.campaignId or None
    experiment_id = payload.experimentId or None
    if campaign_id:
        campaign = session.scalars(
            select(Campaign).where(Campaign.org_id == auth.org_id, Campaign.id == campaign_id)
        ).first()
        if not campaign:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
        if str(campaign.client_id) != str(payload.clientId):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Campaign must belong to the same client",
            )
        if campaign.product_id and payload.productId and str(campaign.product_id) != str(payload.productId):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Campaign product does not match productId.",
            )
        if campaign.product_id is None and payload.productId:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Campaign is missing a productId. Attach a product before creating funnels.",
            )
    if experiment_id:
        if not campaign_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Experiment requires a campaignId.",
            )
        artifacts_repo = ArtifactsRepository(session)
        specs_artifact = artifacts_repo.get_latest_by_type_for_campaign(
            org_id=auth.org_id,
            campaign_id=campaign_id,
            artifact_type=ArtifactTypeEnum.experiment_spec,
        )
        if not specs_artifact or not isinstance(specs_artifact.data, dict):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Experiment specs not found for this campaign.",
            )
        specs = specs_artifact.data.get("experimentSpecs") or specs_artifact.data.get("experiment_specs") or []
        if not any(isinstance(spec, dict) and spec.get("id") == experiment_id for spec in specs):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experiment not found in specs")

    product_id = payload.productId
    selected_offer_id = payload.selectedOfferId
    if not product_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="productId is required.")
    if product_id is not None and not str(product_id).strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="productId cannot be empty.")
    if selected_offer_id is not None and not str(selected_offer_id).strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="selectedOfferId cannot be empty.")
    if selected_offer_id and not product_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="selectedOfferId requires a productId.",
        )
    if product_id:
        product = session.scalars(
            select(Product).where(
                Product.org_id == auth.org_id,
                Product.client_id == payload.clientId,
                Product.id == product_id,
            )
        ).first()
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if selected_offer_id:
        offer = session.scalars(
            select(ProductOffer).where(
                ProductOffer.id == selected_offer_id,
                ProductOffer.product_id == product_id,
                ProductOffer.client_id == payload.clientId,
            )
        ).first()
        if not offer:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Selected offer must belong to the selected product.",
            )

    repo = FunnelsRepository(session)
    try:
        funnel = repo.create(
            org_id=auth.org_id,
            client_id=payload.clientId,
            campaign_id=campaign_id,
            experiment_spec_id=experiment_id,
            product_id=product_id,
            selected_offer_id=selected_offer_id,
            name=payload.name,
            description=payload.description,
            status=FunnelStatusEnum.draft,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return jsonable_encoder(funnel)


@router.get("/{funnel_id}")
def get_funnel(
    funnel_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    funnels_repo = FunnelsRepository(session)
    pages_repo = FunnelPagesRepository(session)
    versions_repo = FunnelPageVersionsRepository(session)

    funnel = funnels_repo.get(org_id=auth.org_id, funnel_id=funnel_id)
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")

    pages = pages_repo.list(funnel_id=funnel_id)
    page_summaries = []
    all_ready = True
    for page in pages:
        draft = versions_repo.latest_for_page(page_id=str(page.id), status=FunnelPageVersionStatusEnum.draft)
        approved = versions_repo.latest_for_page(page_id=str(page.id), status=FunnelPageVersionStatusEnum.approved)
        if not draft and not approved:
            all_ready = False
        page_summaries.append(
            {
                **jsonable_encoder(page),
                "latestDraftVersionId": str(draft.id) if draft else None,
                "latestApprovedVersionId": str(approved.id) if approved else None,
            }
        )

    can_publish = bool(funnel.entry_page_id) and bool(pages) and all_ready
    return {
        **jsonable_encoder(funnel),
        "pages": page_summaries,
        "canPublish": can_publish,
    }


@router.patch("/{funnel_id}")
def update_funnel(
    funnel_id: str,
    payload: FunnelUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    funnels_repo = FunnelsRepository(session)
    funnel = funnels_repo.get(org_id=auth.org_id, funnel_id=funnel_id)
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")

    fields = {}
    if payload.name is not None:
        fields["name"] = payload.name
    if payload.description is not None:
        fields["description"] = payload.description
    if payload.campaignId is not None:
        campaign_id = payload.campaignId or None
        if campaign_id:
            campaign = session.scalars(
                select(Campaign).where(Campaign.org_id == auth.org_id, Campaign.id == campaign_id)
            ).first()
            if not campaign:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
            if str(campaign.client_id) != str(funnel.client_id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Campaign must belong to the same client",
                )
        fields["campaign_id"] = campaign_id
    if "experimentId" in payload.model_fields_set:
        experiment_id = payload.experimentId or None
        if experiment_id:
            if not (fields.get("campaign_id") or funnel.campaign_id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Experiment requires the funnel to have a campaignId.",
                )
            effective_campaign_id = fields.get("campaign_id") or funnel.campaign_id
            artifacts_repo = ArtifactsRepository(session)
            specs_artifact = artifacts_repo.get_latest_by_type_for_campaign(
                org_id=auth.org_id,
                campaign_id=str(effective_campaign_id),
                artifact_type=ArtifactTypeEnum.experiment_spec,
            )
            if not specs_artifact or not isinstance(specs_artifact.data, dict):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Experiment specs not found for this campaign.",
                )
            specs = specs_artifact.data.get("experimentSpecs") or specs_artifact.data.get("experiment_specs") or []
            if not any(isinstance(spec, dict) and spec.get("id") == experiment_id for spec in specs):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experiment not found in specs")
        fields["experiment_spec_id"] = experiment_id

    product_id = funnel.product_id
    if payload.productId is not None:
        if not str(payload.productId).strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="productId cannot be empty.")
        product_id = payload.productId
        if product_id:
            product = session.scalars(
                select(Product).where(
                    Product.org_id == auth.org_id,
                    Product.client_id == str(funnel.client_id),
                    Product.id == product_id,
                )
            ).first()
            if not product:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        fields["product_id"] = product_id

    if payload.selectedOfferId is not None:
        if not str(payload.selectedOfferId).strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="selectedOfferId cannot be empty.")
        if not product_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="selectedOfferId requires a productId.",
            )
        selected_offer_id = payload.selectedOfferId
        if selected_offer_id:
            offer = session.scalars(
                select(ProductOffer).where(
                    ProductOffer.id == selected_offer_id,
                    ProductOffer.product_id == product_id,
                    ProductOffer.client_id == str(funnel.client_id),
                )
            ).first()
            if not offer:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Selected offer must belong to the selected product.",
                )
        fields["selected_offer_id"] = selected_offer_id
    elif product_id and funnel.selected_offer_id:
        offer = session.scalars(
            select(ProductOffer).where(
                ProductOffer.id == funnel.selected_offer_id,
                ProductOffer.product_id == product_id,
                ProductOffer.client_id == str(funnel.client_id),
            )
        ).first()
        if not offer:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Existing selected offer does not belong to the selected product.",
            )
    if payload.entryPageId is not None:
        entry_page_id = payload.entryPageId or None
        if entry_page_id:
            pages_repo = FunnelPagesRepository(session)
            page = pages_repo.get(funnel_id=funnel_id, page_id=entry_page_id)
            if not page:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Entry page must belong to the funnel",
                )
        fields["entry_page_id"] = entry_page_id
    if "designSystemId" in payload.model_fields_set:
        design_system_id = payload.designSystemId or None
        if design_system_id:
            _validate_design_system(
                session=session,
                org_id=auth.org_id,
                client_id=str(funnel.client_id),
                design_system_id=design_system_id,
            )
        fields["design_system_id"] = design_system_id

    updated = funnels_repo.update(org_id=auth.org_id, funnel_id=funnel_id, **fields)
    return jsonable_encoder(updated)


@router.delete("/{funnel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_funnel(
    funnel_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = FunnelsRepository(session)
    deleted = repo.delete(org_id=auth.org_id, funnel_id=funnel_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")
    return None


@router.post("/{funnel_id}/disable")
def disable_funnel(
    funnel_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = FunnelsRepository(session)
    funnel = repo.update(org_id=auth.org_id, funnel_id=funnel_id, status=FunnelStatusEnum.disabled)
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")
    return jsonable_encoder(funnel)


@router.post("/{funnel_id}/enable")
def enable_funnel(
    funnel_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = FunnelsRepository(session)
    funnel = repo.get(org_id=auth.org_id, funnel_id=funnel_id)
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")
    next_status = FunnelStatusEnum.published if funnel.active_publication_id else FunnelStatusEnum.draft
    funnel = repo.update(org_id=auth.org_id, funnel_id=funnel_id, status=next_status)
    return jsonable_encoder(funnel)


@router.post("/{funnel_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_funnel_route(
    funnel_id: str,
    payload: FunnelDuplicateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    try:
        new_funnel = duplicate_funnel(
            session=session,
            org_id=auth.org_id,
            source_funnel_id=funnel_id,
            target_campaign_id=payload.targetCampaignId,
            name=payload.name,
            copy_mode=payload.copyMode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return jsonable_encoder(new_funnel)


@router.post("/{funnel_id}/pages", status_code=status.HTTP_201_CREATED)
def create_page(
    funnel_id: str,
    payload: FunnelPageCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    funnels_repo = FunnelsRepository(session)
    funnel = funnels_repo.get(org_id=auth.org_id, funnel_id=funnel_id)
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")

    design_system_id = payload.designSystemId or None
    design_system_tokens = None
    if design_system_id:
        design_system = _validate_design_system(
            session=session,
            org_id=auth.org_id,
            client_id=str(funnel.client_id),
            design_system_id=design_system_id,
        )
        design_system_tokens = design_system.tokens
        if design_system_tokens is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Design system tokens are required to apply brand assets.",
            )
        if not isinstance(design_system_tokens, dict):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Design system tokens must be a JSON object.",
            )
    else:
        design_system_tokens = resolve_design_system_tokens(
            session=session,
            org_id=auth.org_id,
            client_id=str(funnel.client_id),
        )
        if design_system_tokens is not None and not isinstance(design_system_tokens, dict):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Design system tokens must be a JSON object.",
            )

    template_id = payload.templateId
    template_puck_data = None
    if template_id:
        template = get_funnel_template(template_id)
        if not template:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
        try:
            template_puck_data = apply_template_assets(
                session=session,
                org_id=auth.org_id,
                client_id=str(funnel.client_id),
                template=template,
                design_system_tokens=design_system_tokens,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    pages_repo = FunnelPagesRepository(session)
    next_page_id = payload.nextPageId or None
    if next_page_id:
        next_page = pages_repo.get(funnel_id=funnel_id, page_id=next_page_id)
        if not next_page:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Next page must belong to the funnel.",
            )
    pages = pages_repo.list(funnel_id=funnel_id)
    ordering = len(pages)
    desired = payload.slug or payload.name
    unique_slug = generate_unique_slug(session, funnel_id=funnel_id, desired_slug=desired)

    page = pages_repo.create(
        funnel_id=funnel_id,
        name=payload.name,
        slug=unique_slug,
        ordering=ordering,
        template_id=template_id,
        design_system_id=design_system_id,
        next_page_id=next_page_id,
    )

    version = FunnelPageVersion(
        page_id=page.id,
        status=FunnelPageVersionStatusEnum.draft,
        puck_data=template_puck_data or default_puck_data(),
        source=FunnelPageVersionSourceEnum.human,
        created_at=datetime.now(timezone.utc),
    )
    session.add(version)
    session.commit()
    session.refresh(page)
    session.refresh(version)

    return {"page": jsonable_encoder(page), "draftVersion": jsonable_encoder(version)}


@router.get("/{funnel_id}/pages/{page_id}")
def get_page(
    funnel_id: str,
    page_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    funnels_repo = FunnelsRepository(session)
    funnel = funnels_repo.get(org_id=auth.org_id, funnel_id=funnel_id)
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")

    pages_repo = FunnelPagesRepository(session)
    page = pages_repo.get(funnel_id=funnel_id, page_id=page_id)
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    versions_repo = FunnelPageVersionsRepository(session)
    draft = versions_repo.latest_for_page(page_id=str(page.id), status=FunnelPageVersionStatusEnum.draft)
    approved = versions_repo.latest_for_page(page_id=str(page.id), status=FunnelPageVersionStatusEnum.approved)

    design_system_tokens = resolve_design_system_tokens(
        session=session,
        org_id=auth.org_id,
        client_id=str(funnel.client_id),
        funnel=funnel,
        page=page,
    )

    return {
        "page": jsonable_encoder(page),
        "latestDraft": jsonable_encoder(draft) if draft else None,
        "latestApproved": jsonable_encoder(approved) if approved else None,
        "designSystemTokens": design_system_tokens,
    }


@router.put("/{funnel_id}/pages/{page_id}")
def save_draft(
    funnel_id: str,
    page_id: str,
    payload: FunnelPageSaveDraftRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    funnels_repo = FunnelsRepository(session)
    funnel = funnels_repo.get(org_id=auth.org_id, funnel_id=funnel_id)
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")

    pages_repo = FunnelPagesRepository(session)
    page = pages_repo.get(funnel_id=funnel_id, page_id=page_id)
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    version = FunnelPageVersion(
        page_id=page.id,
        status=FunnelPageVersionStatusEnum.draft,
        puck_data=payload.puckData,
        source=FunnelPageVersionSourceEnum.human,
        created_at=datetime.now(timezone.utc),
    )
    session.add(version)
    session.commit()
    session.refresh(version)
    return jsonable_encoder(version)


@router.patch("/{funnel_id}/pages/{page_id}")
def update_page(
    funnel_id: str,
    page_id: str,
    payload: FunnelPageUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    funnels_repo = FunnelsRepository(session)
    funnel = funnels_repo.get(org_id=auth.org_id, funnel_id=funnel_id)
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")

    pages_repo = FunnelPagesRepository(session)
    page = pages_repo.get(funnel_id=funnel_id, page_id=page_id)
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    update_fields = {}
    if payload.name is not None:
        update_fields["name"] = payload.name
    if payload.ordering is not None:
        update_fields["ordering"] = payload.ordering
    if payload.slug is not None:
        new_slug = generate_unique_slug(
            session,
            funnel_id=funnel_id,
            desired_slug=payload.slug,
            exclude_page_id=str(page.id),
        )
        if page.slug != new_slug:
            session.add(
                FunnelPageSlugRedirect(
                    funnel_id=funnel_id,
                    page_id=page.id,
                    from_slug=page.slug,
                    to_slug=new_slug,
                )
            )
        update_fields["slug"] = new_slug
    if "designSystemId" in payload.model_fields_set:
        design_system_id = payload.designSystemId or None
        if design_system_id:
            _validate_design_system(
                session=session,
                org_id=auth.org_id,
                client_id=str(funnel.client_id),
                design_system_id=design_system_id,
            )
        update_fields["design_system_id"] = design_system_id
    if "nextPageId" in payload.model_fields_set:
        next_page_id = payload.nextPageId or None
        if next_page_id:
            if next_page_id == page_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Next page cannot reference itself.",
                )
            next_page = pages_repo.get(funnel_id=funnel_id, page_id=next_page_id)
            if not next_page:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Next page must belong to the funnel.",
                )
        update_fields["next_page_id"] = next_page_id

    updated = pages_repo.update(page_id=page_id, **update_fields)
    return jsonable_encoder(updated)


@router.post("/{funnel_id}/publish", status_code=status.HTTP_201_CREATED)
async def publish_funnel_route(
    funnel_id: str,
    payload: FunnelPublishRequest | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if not payload or not payload.deploy:
        try:
            result = run_publish_funnel(
                session=session,
                org_id=auth.org_id,
                user_id=auth.user_id,
                funnel_id=funnel_id,
            )
        except ValueError as exc:
            message = str(exc)
            code = status.HTTP_404_NOT_FOUND if "not found" in message.lower() else status.HTTP_409_CONFLICT
            raise HTTPException(status_code=code, detail=message) from exc
        return {
            "publicationId": result.get("publicationId") or "",
            **({"runId": result.get("runId")} if result.get("runId") else {}),
        }

    deploy = payload.deploy
    funnels_repo = FunnelsRepository(session)
    funnel = funnels_repo.get(org_id=auth.org_id, funnel_id=funnel_id)
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")

    server_names = _resolve_deploy_server_names(
        session=session,
        org_id=auth.org_id,
        funnel_id=funnel_id,
        requested_server_names=deploy.serverNames,
    )

    upstream_base_url = (deploy.upstreamBaseUrl or settings.DEPLOY_PUBLIC_BASE_URL or "").strip()

    upstream_api_base_root = (deploy.upstreamApiBaseUrl or settings.DEPLOY_PUBLIC_API_BASE_URL or "").strip()
    if not upstream_api_base_root:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Deploy upstream API base URL is required. "
                "Set deploy.upstreamApiBaseUrl or DEPLOY_PUBLIC_API_BASE_URL."
            ),
        )
    try:
        workload_patch = deploy_service.build_funnel_artifact_workload_patch(
            workload_name=deploy.workloadName,
            client_id=str(funnel.client_id),
            upstream_base_url=upstream_base_url,
            upstream_api_base_url=upstream_api_base_root,
            server_names=server_names,
            https=deploy.https,
            destination_path=deploy.destinationPath,
        )
        https_enabled = bool(deploy.https and server_names)
        access_urls = _deploy_access_urls(server_names=server_names, https_enabled=https_enabled)
        job = deploy_service.start_funnel_publish_job(
            org_id=auth.org_id,
            user_id=auth.user_id,
            funnel_id=funnel_id,
            deploy_request={
                "workload_patch": workload_patch,
                "plan_path": deploy.planPath,
                "instance_name": deploy.instanceName,
                "create_if_missing": deploy.createIfMissing,
                "in_place": deploy.inPlace,
                "apply_plan": deploy.applyPlan,
                "bunny_pull_zone": deploy.bunnyPullZone,
                "bunny_pull_zone_origin_ip": deploy.bunnyPullZoneOriginIp,
                "access_urls": access_urls,
            },
            access_urls=access_urls,
        )
    except deploy_service.DeployError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Publish job start failed: {exc}",
        ) from exc

    return {
        "publicationId": None,
        "deploy": {
            "apply": {
                "mode": "async",
                "jobId": job["id"],
                "status": job["status"],
                "statusPath": f"/funnels/{funnel_id}/publish-jobs/{job['id']}",
                "accessUrls": job.get("access_urls", []),
            }
        },
    }


@router.get("/{funnel_id}/publish-jobs/{job_id}")
def get_publish_job_status(
    funnel_id: str,
    job_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    funnels_repo = FunnelsRepository(session)
    funnel = funnels_repo.get(org_id=auth.org_id, funnel_id=funnel_id)
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")

    try:
        job = deploy_service.get_funnel_publish_job(
            job_id=job_id,
            org_id=auth.org_id,
            funnel_id=funnel_id,
        )
    except deploy_service.DeployError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return job


@router.get("/{funnel_id}/deploy-jobs/{job_id}")
def get_deploy_job_status(
    funnel_id: str,
    job_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    funnels_repo = FunnelsRepository(session)
    funnel = funnels_repo.get(org_id=auth.org_id, funnel_id=funnel_id)
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")

    try:
        job = deploy_service.get_apply_plan_job(job_id=job_id)
    except deploy_service.DeployError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return job


@router.post("/{funnel_id}/pages/{page_id}/ai/attachments", status_code=status.HTTP_201_CREATED)
async def ai_upload_attachments(
    funnel_id: str,
    page_id: str,
    files: list[UploadFile] = File(...),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files uploaded")
    if len(files) > _AI_ATTACHMENT_MAX_COUNT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many files (max {_AI_ATTACHMENT_MAX_COUNT}).",
        )

    funnels_repo = FunnelsRepository(session)
    funnel = funnels_repo.get(org_id=auth.org_id, funnel_id=funnel_id)
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")

    pages_repo = FunnelPagesRepository(session)
    page = pages_repo.get(funnel_id=funnel_id, page_id=page_id)
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    uploads: list[tuple[UploadFile, bytes, str]] = []
    for file in files:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"File {file.filename or ''} is empty")
        if len(content) > _AI_ATTACHMENT_MAX_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File {file.filename or ''} exceeds {_AI_ATTACHMENT_MAX_BYTES} bytes.",
            )
        content_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or ""
        if content_type not in _AI_ATTACHMENT_ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Unsupported file type for {file.filename or 'upload'} "
                    f"({content_type or 'unknown'}). Allowed: png, jpeg, webp, gif."
                ),
            )
        uploads.append((file, content, content_type))

    attachments = []
    for file, content, content_type in uploads:
        asset = create_funnel_upload_asset(
            session=session,
            org_id=auth.org_id,
            client_id=str(funnel.client_id),
            content_bytes=content,
            filename=file.filename,
            content_type=content_type,
            usage_context={
                "kind": "ai_attachment",
                "funnelId": funnel_id,
                "pageId": page_id,
            },
            funnel_id=funnel_id,
            product_id=str(funnel.product_id) if funnel.product_id else None,
            tags=["funnel", "ai_attachment"],
        )
        attachments.append(
            {
                "assetId": str(asset.id),
                "publicId": str(asset.public_id),
                "filename": file.filename or "",
                "contentType": asset.content_type,
                "width": asset.width,
                "height": asset.height,
                "url": f"/public/assets/{asset.public_id}",
            }
        )

    return {"attachments": attachments}


@router.post("/{funnel_id}/pages/{page_id}/ai/generate", status_code=status.HTTP_201_CREATED)
def ai_generate_page_draft(
    funnel_id: str,
    page_id: str,
    payload: FunnelPageAIGenerateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if payload.attachedAssets and len(payload.attachedAssets) > _AI_ATTACHMENT_MAX_COUNT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many attached images (max {_AI_ATTACHMENT_MAX_COUNT}).",
        )
    try:
        result = run_generate_page_draft(
            session=session,
            org_id=auth.org_id,
            user_id=auth.user_id,
            funnel_id=funnel_id,
            page_id=page_id,
            prompt=payload.prompt,
            messages=[m.model_dump() for m in payload.messages] if payload.messages else None,
            attachments=[a.model_dump() for a in payload.attachedAssets] if payload.attachedAssets else None,
            current_puck_data=payload.currentPuckData,
            template_id=payload.templateId,
            idea_workspace_id=payload.ideaWorkspaceId,
            model=payload.model,
            temperature=payload.temperature,
            max_tokens=payload.maxTokens,
            generate_images=payload.generateImages,
            max_images=payload.maxImages,
            copy_pack=getattr(payload, "copyPack", None),
        )
    except AiAttachmentError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return {
        "assistantMessage": result.get("assistantMessage") or "",
        "puckData": result.get("puckData") or {},
        "draftVersionId": result.get("draftVersionId") or "",
        "generatedImages": result.get("generatedImages") or [],
        "imagePlans": result.get("imagePlans") or [],
        **({"runId": result.get("runId")} if result.get("runId") else {}),
    }


@router.post("/{funnel_id}/pages/{page_id}/ai/testimonials", status_code=status.HTTP_201_CREATED)
def ai_generate_page_testimonials(
    funnel_id: str,
    page_id: str,
    payload: FunnelPageTestimonialGenerateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    try:
        result = run_generate_page_testimonials(
            session=session,
            org_id=auth.org_id,
            user_id=auth.user_id,
            funnel_id=funnel_id,
            page_id=page_id,
            draft_version_id=payload.draftVersionId,
            current_puck_data=payload.currentPuckData,
            template_id=payload.templateId,
            idea_workspace_id=payload.ideaWorkspaceId,
            model=payload.model,
            temperature=payload.temperature,
            max_tokens=payload.maxTokens,
            synthetic=payload.synthetic,
        )
    except TestimonialGenerationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TestimonialGenerationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return {
        "draftVersionId": result.get("draftVersionId") or "",
        "puckData": result.get("puckData") or {},
        "generatedTestimonials": result.get("generatedTestimonials") or [],
        **({"runId": result.get("runId")} if result.get("runId") else {}),
    }


@router.post("/{funnel_id}/pages/{page_id}/ai/generate/stream")
def ai_generate_page_draft_stream(
    funnel_id: str,
    page_id: str,
    payload: FunnelPageAIGenerateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    if payload.attachedAssets and len(payload.attachedAssets) > _AI_ATTACHMENT_MAX_COUNT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many attached images (max {_AI_ATTACHMENT_MAX_COUNT}).",
        )
    def _sse(data: dict) -> bytes:
        return f"data: {json.dumps(data, separators=(',', ':'))}\n\n".encode("utf-8")

    def event_stream():
        for event in run_generate_page_draft_stream(
            session=session,
            org_id=auth.org_id,
            user_id=auth.user_id,
            funnel_id=funnel_id,
            page_id=page_id,
            prompt=payload.prompt,
            messages=[m.model_dump() for m in payload.messages] if payload.messages else None,
            attachments=[a.model_dump() for a in payload.attachedAssets] if payload.attachedAssets else None,
            current_puck_data=payload.currentPuckData,
            template_id=payload.templateId,
            idea_workspace_id=payload.ideaWorkspaceId,
            model=payload.model,
            temperature=payload.temperature,
            max_tokens=payload.maxTokens,
            generate_images=payload.generateImages,
            max_images=payload.maxImages,
            copy_pack=getattr(payload, "copyPack", None),
        ):
            yield _sse(event)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
