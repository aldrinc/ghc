from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from uuid import uuid4

from app.auth.dependencies import AuthContext, get_current_user
from app.config import settings
from app.db.deps import get_session
from app.db.repositories.swipes import CompanySwipesRepository, ClientSwipesRepository
from app.db.models import WorkflowRun
from app.db.repositories.workflows import WorkflowsRepository
from app.schemas.swipe_image_ads import SwipeImageAdGenerateRequest
from app.temporal.client import get_temporal_client
from app.temporal.workflows.swipe_image_ad import SwipeImageAdInput, SwipeImageAdWorkflow

router = APIRouter(prefix="/swipes", tags=["swipes"])


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
      - Generates a generation-ready image prompt from a competitor swipe image (Gemini vision)
      - Renders the final image(s) via the creative service (Freestyle)
      - Persists generated assets attached to the provided asset brief
    """

    temporal = await get_temporal_client()
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
        handle = await temporal.start_workflow(
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
                model=payload.model,
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
