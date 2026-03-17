from __future__ import annotations

import mimetypes
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.config import settings
from app.db.deps import get_session
from app.db.models import Campaign, WorkflowRun
from app.db.repositories.swipes import CompanySwipesRepository, ClientSwipesRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.schemas.swipe_image_ads import (
    SwipeImageAdGenerateRequest,
    SwipeTemplateTestimonialsGenerateRequest,
    SwipeTemplateTestimonialsGenerateResponse,
)
from app.services.funnels import create_funnel_upload_asset
from app.services.meta_review import clean_optional_text, load_campaign_asset_brief_map
from app.temporal.client import get_temporal_client
from app.temporal.workflows.swipe_image_ad import SwipeImageAdInput, SwipeImageAdWorkflow

router = APIRouter(prefix="/swipes", tags=["swipes"])
_TEMPLATE_IMAGES_DIR = Path(__file__).resolve().parents[4] / "template-images"
_IMAGE_REQUIREMENT_FORMATS = {"image", "image_ad", "image-ad"}


def _normalize_requirement_format(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def _require_public_asset_base_url() -> str:
    base_url = str(settings.PUBLIC_ASSET_BASE_URL or "").strip()
    if not base_url:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="PUBLIC_ASSET_BASE_URL is required for swipe template testimonial generation.",
        )
    return base_url.rstrip("/")


def _collect_template_image_paths() -> list[Path]:
    if not _TEMPLATE_IMAGES_DIR.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Swipe template image directory does not exist: {_TEMPLATE_IMAGES_DIR}",
        )
    if not _TEMPLATE_IMAGES_DIR.is_dir():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Swipe template image path must be a directory: {_TEMPLATE_IMAGES_DIR}",
        )

    files: list[Path] = []
    for path in sorted(_TEMPLATE_IMAGES_DIR.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        content_type = mimetypes.guess_type(path.name)[0] or ""
        if not content_type.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Swipe template image file has unsupported content type: {path.name}",
            )
        files.append(path)

    if not files:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Swipe template image directory is empty: {_TEMPLATE_IMAGES_DIR}",
        )
    return files


def _resolve_single_image_requirement_index(brief: dict) -> int:
    requirements = brief.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Asset brief has no requirements.",
        )

    image_indexes: list[int] = []
    for index, requirement in enumerate(requirements):
        if not isinstance(requirement, dict):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Asset brief requirement at index {index} must be an object.",
            )
        normalized_format = _normalize_requirement_format(str(requirement.get("format") or ""))
        if normalized_format in _IMAGE_REQUIREMENT_FORMATS:
            image_indexes.append(index)

    if not image_indexes:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Asset brief has no image requirement for swipe template testimonial generation.",
        )
    if len(image_indexes) != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Asset brief must contain exactly one image requirement for swipe template testimonial generation. "
                f"Found indexes: {image_indexes}."
            ),
        )
    return image_indexes[0]


async def _start_swipe_image_ad_run(
    *,
    payload: SwipeImageAdGenerateRequest,
    auth: AuthContext,
    session: Session,
    temporal=None,
) -> dict[str, str]:
    temporal_client = temporal or await get_temporal_client()
    temporal_workflow_id = f"swipe-image-ad-{auth.org_id}-{payload.campaign_id}-{uuid4()}"

    run = WorkflowRun(
        org_id=auth.org_id,
        client_id=payload.client_id,
        product_id=payload.product_id,
        campaign_id=payload.campaign_id,
        temporal_workflow_id=temporal_workflow_id,
        temporal_run_id="pending",
        kind="swipe_image_ad",
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    try:
        handle = await temporal_client.start_workflow(
            SwipeImageAdWorkflow.run,
            SwipeImageAdInput(
                org_id=auth.org_id,
                client_id=payload.client_id,
                product_id=payload.product_id,
                campaign_id=payload.campaign_id,
                asset_brief_id=payload.asset_brief_id,
                requirement_index=payload.requirement_index,
                company_swipe_id=payload.company_swipe_id,
                swipe_image_url=payload.swipe_image_url,
                swipe_requires_product_image=payload.swipe_requires_product_image,
                model=payload.model,
                render_model_id=payload.render_model_id,
                max_output_tokens=payload.max_output_tokens,
                aspect_ratio=payload.aspect_ratio,
                count=payload.count,
                workflow_run_id=str(run.id),
            ),
            id=temporal_workflow_id,
            task_queue=settings.TEMPORAL_TASK_QUEUE,
        )
    except Exception as exc:  # noqa: BLE001
        session.delete(run)
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to start swipe image ad workflow.",
        ) from exc

    run.temporal_run_id = handle.first_execution_run_id
    session.commit()

    WorkflowsRepository(session).log_activity(
        workflow_run_id=str(run.id),
        step="swipe_image_ad",
        status="started",
        payload_in=payload.model_dump(mode="json"),
    )

    return {"workflow_run_id": str(run.id), "temporal_workflow_id": handle.id}


@router.get("/company")
def list_company_swipes(
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list:
    repo = CompanySwipesRepository(session)
    return jsonable_encoder(repo.list_assets(org_id=auth.org_id))


@router.get("/client/{client_id}")
def list_client_swipes(
    client_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list:
    repo = ClientSwipesRepository(session)
    return jsonable_encoder(repo.list(org_id=auth.org_id, client_id=client_id))


@router.post("/generate-image-ad")
async def generate_image_ad_from_swipe(
    payload: SwipeImageAdGenerateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Start a Temporal workflow that:
      - Generates a generation-ready image prompt from a competitor swipe image
        (Gemini vision + Gemini File Search workspace context)
      - Renders the final image(s) via the MOS-embedded Freestyle renderer
      - Persists generated assets attached to the provided asset brief
    """
    return await _start_swipe_image_ad_run(payload=payload, auth=auth, session=session)


@router.post(
    "/generate-template-testimonials",
    response_model=SwipeTemplateTestimonialsGenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_template_testimonials(
    payload: SwipeTemplateTestimonialsGenerateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    campaign = session.scalars(
        select(Campaign).where(
            Campaign.org_id == auth.org_id,
            Campaign.id == payload.campaign_id,
        )
    ).first()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if not campaign.product_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Campaign must have a product before generating swipe template testimonials.",
        )

    brief_map = load_campaign_asset_brief_map(
        org_id=auth.org_id,
        client_id=str(campaign.client_id),
        campaign_id=payload.campaign_id,
        session=session,
    )
    brief = brief_map.get(payload.asset_brief_id)
    if not isinstance(brief, dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset brief not found")

    requirement_index = _resolve_single_image_requirement_index(brief)
    template_paths = _collect_template_image_paths()
    public_asset_base_url = _require_public_asset_base_url()
    temporal = await get_temporal_client()
    brief_funnel_id = clean_optional_text(brief.get("funnelId"))

    template_runs: list[dict[str, str]] = []
    for template_path in template_paths:
        content_bytes = template_path.read_bytes()
        if not content_bytes:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Swipe template image is empty: {template_path.name}",
            )
        content_type = mimetypes.guess_type(template_path.name)[0] or ""
        if not content_type.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Swipe template image has unsupported content type: {template_path.name}",
            )

        staged_asset = create_funnel_upload_asset(
            session=session,
            org_id=auth.org_id,
            client_id=str(campaign.client_id),
            content_bytes=content_bytes,
            filename=template_path.name,
            content_type=content_type,
            usage_context={
                "kind": "swipe_template_source",
                "campaignId": payload.campaign_id,
                "assetBriefId": payload.asset_brief_id,
                "templateFile": template_path.relative_to(_TEMPLATE_IMAGES_DIR).as_posix(),
            },
            funnel_id=brief_funnel_id,
            product_id=str(campaign.product_id),
            tags=["swipe", "swipe_template_source"],
        )
        staged_public_id = str(staged_asset.public_id)
        staged_public_url = f"{public_asset_base_url}/public/assets/{staged_public_id}"

        workflow_payload = SwipeImageAdGenerateRequest(
            clientId=str(campaign.client_id),
            productId=str(campaign.product_id),
            campaignId=payload.campaign_id,
            assetBriefId=payload.asset_brief_id,
            requirementIndex=requirement_index,
            swipeImageUrl=staged_public_url,
            aspectRatio=payload.aspect_ratio,
            count=1,
            model=payload.model,
            renderModelId=payload.render_model_id,
            maxOutputTokens=payload.max_output_tokens,
        )
        started = await _start_swipe_image_ad_run(
            payload=workflow_payload,
            auth=auth,
            session=session,
            temporal=temporal,
        )
        template_runs.append(
            {
                "templateFile": template_path.relative_to(_TEMPLATE_IMAGES_DIR).as_posix(),
                "templateLabel": template_path.stem,
                "stagedAssetId": str(staged_asset.id),
                "stagedPublicId": staged_public_id,
                "stagedPublicUrl": staged_public_url,
                "workflowRunId": started["workflow_run_id"],
                "temporalWorkflowId": started["temporal_workflow_id"],
            }
        )

    return {
        "campaignId": payload.campaign_id,
        "assetBriefId": payload.asset_brief_id,
        "clientId": str(campaign.client_id),
        "productId": str(campaign.product_id),
        "requirementIndex": requirement_index,
        "templateRuns": template_runs,
    }
