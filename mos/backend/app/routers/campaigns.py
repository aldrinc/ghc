from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.config import settings
from app.db.deps import get_session
from app.db.repositories.campaigns import CampaignsRepository
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.enums import ArtifactTypeEnum
from app.db.repositories.workflows import WorkflowsRepository
from app.db.repositories.products import ProductsRepository
from app.schemas.common import CampaignCreate
from app.schemas.campaign_funnels import CampaignFunnelGenerationRequest
from app.schemas.experiment_spec import ExperimentSpecSet, ExperimentSpecsUpdateRequest
from app.temporal.client import get_temporal_client
from app.temporal.workflows.campaign_planning import CampaignPlanningInput, CampaignPlanningWorkflow
from app.temporal.workflows.campaign_funnel_generation import (
    CampaignFunnelGenerationInput,
    CampaignFunnelGenerationWorkflow,
)


def _validate_planning_prereqs(
    *,
    org_id: str,
    client_id: str,
    product_id: str,
    session: Session,
) -> None:
    artifacts_repo = ArtifactsRepository(session)
    canon = artifacts_repo.get_latest_by_type(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        artifact_type=ArtifactTypeEnum.client_canon,
    )
    metric = artifacts_repo.get_latest_by_type(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        artifact_type=ArtifactTypeEnum.metric_schema,
    )
    wf_repo = WorkflowsRepository(session)
    approvals_ok = wf_repo.has_onboarding_approvals(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
    )
    if (not canon or not metric) and not approvals_ok:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete client onboarding (canon + metric schema) before starting campaign planning.",
        )


async def _start_campaign_planning(
    *,
    org_id: str,
    client_id: str,
    product_id: str,
    campaign_id: str,
    business_goal_id: str | None,
    session: Session,
) -> dict:
    business_goal_id = business_goal_id or str(uuid4())
    temporal = await get_temporal_client()
    handle = await temporal.start_workflow(
        CampaignPlanningWorkflow.run,
        CampaignPlanningInput(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            business_goal_id=business_goal_id,
        ),
        id=f"campaign-planning-{org_id}-{campaign_id}",
        task_queue=settings.TEMPORAL_TASK_QUEUE,
    )

    wf_repo = WorkflowsRepository(session)
    run = wf_repo.create_run(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        temporal_workflow_id=handle.id,
        temporal_run_id=handle.first_execution_run_id,
        kind="campaign_planning",
    )
    wf_repo.log_activity(
        workflow_run_id=str(run.id),
        step="campaign_planning",
        status="started",
        payload_in={
            "campaign_id": campaign_id,
            "product_id": product_id,
            "business_goal_id": business_goal_id,
        },
    )

    return {"workflow_run_id": str(run.id), "temporal_workflow_id": handle.id}

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("")
def list_campaigns(
    client_id: str | None = None,
    product_id: str | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list:
    if (client_id and not product_id) or (product_id and not client_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="client_id and product_id are required together.",
        )
    repo = CampaignsRepository(session)
    return jsonable_encoder(repo.list(org_id=auth.org_id, client_id=client_id, product_id=product_id))


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreate,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if not payload.channels or not all(isinstance(ch, str) and ch.strip() for ch in payload.channels):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="channels must include at least one non-empty value.",
        )
    if not payload.asset_brief_types or not all(
        isinstance(t, str) and t.strip() for t in payload.asset_brief_types
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="asset_brief_types must include at least one non-empty value.",
        )
    product_repo = ProductsRepository(session)
    product = product_repo.get(org_id=auth.org_id, product_id=payload.product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if str(product.client_id) != payload.client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="product_id does not belong to the selected workspace.",
        )
    if payload.start_planning:
        _validate_planning_prereqs(
            org_id=auth.org_id,
            client_id=payload.client_id,
            product_id=payload.product_id,
            session=session,
        )
    repo = CampaignsRepository(session)
    campaign = repo.create(
        org_id=auth.org_id,
        client_id=payload.client_id,
        product_id=payload.product_id,
        name=payload.name,
        channels=payload.channels,
        asset_brief_types=payload.asset_brief_types,
        goal_description=payload.goal_description,
        objective_type=payload.objective_type,
        numeric_target=payload.numeric_target,
        baseline=payload.baseline,
        timeframe_days=payload.timeframe_days,
        budget_min=payload.budget_min,
        budget_max=payload.budget_max,
    )
    if payload.start_planning:
        try:
            await _start_campaign_planning(
                org_id=auth.org_id,
                client_id=campaign.client_id,
                product_id=str(campaign.product_id),
                campaign_id=str(campaign.id),
                business_goal_id=None,
                session=session,
            )
        except HTTPException:
            repo.delete(auth.org_id, str(campaign.id))
            raise
        except Exception as exc:
            repo.delete(auth.org_id, str(campaign.id))
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to start campaign planning workflow.",
            ) from exc
    return jsonable_encoder(campaign)


@router.get("/{campaign_id}")
def get_campaign(
    campaign_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = CampaignsRepository(session)
    campaign = repo.get(org_id=auth.org_id, campaign_id=campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return jsonable_encoder(campaign)


@router.post("/{campaign_id}/plan")
async def start_campaign_planning(
    campaign_id: str,
    payload: dict,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = CampaignsRepository(session)
    campaign = repo.get(org_id=auth.org_id, campaign_id=campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if not campaign.product_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Campaign is missing a product_id. Attach a product before starting planning.",
        )
    _validate_planning_prereqs(
        org_id=auth.org_id,
        client_id=campaign.client_id,
        product_id=str(campaign.product_id),
        session=session,
    )

    return await _start_campaign_planning(
        org_id=auth.org_id,
        client_id=campaign.client_id,
        product_id=str(campaign.product_id),
        campaign_id=campaign_id,
        business_goal_id=payload.get("business_goal_id"),
        session=session,
    )


@router.post("/{campaign_id}/funnels/generate")
async def generate_campaign_funnels(
    campaign_id: str,
    payload: CampaignFunnelGenerationRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = CampaignsRepository(session)
    campaign = repo.get(org_id=auth.org_id, campaign_id=campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if not campaign.product_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Campaign is missing a product_id. Attach a product before creating funnels.",
        )
    if not campaign.channels:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Campaign is missing channels. Set channels before creating funnels.",
        )
    if not campaign.asset_brief_types:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Campaign is missing creative brief types. Set creative brief types before creating funnels.",
        )
    if not payload.experimentIds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="experimentIds must include at least one angle.",
        )

    temporal = await get_temporal_client()
    handle = await temporal.start_workflow(
        CampaignFunnelGenerationWorkflow.run,
        CampaignFunnelGenerationInput(
            org_id=auth.org_id,
            client_id=str(campaign.client_id),
            product_id=str(campaign.product_id),
            campaign_id=str(campaign.id),
            experiment_ids=payload.experimentIds,
            funnel_name_prefix=f"{campaign.name} Funnel",
        ),
        id=f"campaign-funnels-{auth.org_id}-{campaign_id}-{uuid4()}",
        task_queue=settings.TEMPORAL_TASK_QUEUE,
    )

    wf_repo = WorkflowsRepository(session)
    run = wf_repo.create_run(
        org_id=auth.org_id,
        client_id=str(campaign.client_id),
        product_id=str(campaign.product_id),
        campaign_id=str(campaign.id),
        temporal_workflow_id=handle.id,
        temporal_run_id=handle.first_execution_run_id,
        kind="campaign_funnel_generation",
    )
    wf_repo.log_activity(
        workflow_run_id=str(run.id),
        step="campaign_funnel_generation",
        status="started",
        payload_in={
            "campaign_id": str(campaign.id),
            "product_id": str(campaign.product_id),
            "experiment_ids": payload.experimentIds,
        },
    )

    return {"workflow_run_id": str(run.id), "temporal_workflow_id": handle.id}


@router.post("/{campaign_id}/experiment-specs", status_code=status.HTTP_201_CREATED)
def update_experiment_specs(
    campaign_id: str,
    payload: ExperimentSpecsUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = CampaignsRepository(session)
    campaign = repo.get(org_id=auth.org_id, campaign_id=campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    if not payload.experimentSpecs:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="experimentSpecs cannot be empty.")

    spec_set = ExperimentSpecSet(
        clientId=campaign.client_id,
        campaignId=campaign_id,
        experimentSpecs=payload.experimentSpecs,
    )
    data_out = spec_set.model_dump()

    artifacts_repo = ArtifactsRepository(session)
    artifact = artifacts_repo.insert(
        org_id=auth.org_id,
        client_id=campaign.client_id,
        campaign_id=campaign_id,
        artifact_type=ArtifactTypeEnum.experiment_spec,
        data=data_out,
        created_by_user=auth.user_id,
    )
    return jsonable_encoder(artifact)
