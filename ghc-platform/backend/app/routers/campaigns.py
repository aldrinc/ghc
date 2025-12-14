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
from app.schemas.common import CampaignCreate
from app.temporal.client import get_temporal_client
from app.temporal.workflows.campaign_planning import CampaignPlanningInput, CampaignPlanningWorkflow

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("")
def list_campaigns(
    client_id: str | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list:
    repo = CampaignsRepository(session)
    return jsonable_encoder(repo.list(org_id=auth.org_id, client_id=client_id))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_campaign(
    payload: CampaignCreate,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = CampaignsRepository(session)
    campaign = repo.create(
        org_id=auth.org_id,
        client_id=payload.client_id,
        name=payload.name,
        goal_description=payload.goal_description,
        objective_type=payload.objective_type,
        numeric_target=payload.numeric_target,
        baseline=payload.baseline,
        timeframe_days=payload.timeframe_days,
        budget_min=payload.budget_min,
        budget_max=payload.budget_max,
    )
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

    artifacts_repo = ArtifactsRepository(session)
    canon = artifacts_repo.get_latest_by_type(
        org_id=auth.org_id, client_id=campaign.client_id, artifact_type=ArtifactTypeEnum.client_canon
    )
    metric = artifacts_repo.get_latest_by_type(
        org_id=auth.org_id, client_id=campaign.client_id, artifact_type=ArtifactTypeEnum.metric_schema
    )
    wf_repo = WorkflowsRepository(session)
    approvals_ok = wf_repo.has_onboarding_approvals(org_id=auth.org_id, client_id=campaign.client_id)
    if (not canon or not metric) and not approvals_ok:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete client onboarding (canon + metric schema) before starting campaign planning.",
        )

    business_goal_id = str(payload.get("business_goal_id") or uuid4())
    temporal = await get_temporal_client()
    handle = await temporal.start_workflow(
        CampaignPlanningWorkflow.run,
        CampaignPlanningInput(
            org_id=auth.org_id,
            client_id=campaign.client_id,
            campaign_id=campaign_id,
            business_goal_id=business_goal_id,
        ),
        id=f"campaign-planning-{auth.org_id}-{campaign_id}",
        task_queue=settings.TEMPORAL_TASK_QUEUE,
    )

    wf_repo = WorkflowsRepository(session)
    run = wf_repo.create_run(
        org_id=auth.org_id,
        client_id=campaign.client_id,
        campaign_id=campaign_id,
        temporal_workflow_id=handle.id,
        temporal_run_id=handle.first_execution_run_id,
        kind="campaign_planning",
    )
    wf_repo.log_activity(
        workflow_run_id=str(run.id),
        step="campaign_planning",
        status="started",
        payload_in={"campaign_id": campaign_id, "business_goal_id": business_goal_id},
    )

    return {"workflow_run_id": str(run.id), "temporal_workflow_id": handle.id}
