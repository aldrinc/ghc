from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.config import settings
from app.db.deps import get_session
from app.db.enums import ArtifactTypeEnum, WorkflowStatusEnum
from app.db.models import WorkflowRun
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.campaigns import CampaignsRepository
from app.db.repositories.funnels import FunnelsRepository
from app.db.repositories.products import ProductsRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.schemas.common import CampaignCreate
from app.schemas.campaign_funnels import CampaignFunnelGenerationRequest
from app.schemas.creative_production import CreativeProductionRequest
from app.schemas.experiment_spec import ExperimentSpecSet, ExperimentSpecsUpdateRequest
from app.temporal.client import get_temporal_client
from app.temporal.workflows.campaign_planning import CampaignPlanningInput, CampaignPlanningWorkflow
from app.temporal.workflows.campaign_funnel_generation import (
    CampaignFunnelGenerationInput,
    CampaignFunnelGenerationWorkflow,
)
from app.temporal.workflows.creative_production import CreativeProductionInput, CreativeProductionWorkflow
from temporalio.api.enums.v1 import WorkflowExecutionStatus


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
    if not canon or not metric:
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
    if not payload.experiment_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="experimentIds must include at least one angle.",
        )
    requested_experiment_ids: list[str] = []
    seen_experiment_ids: set[str] = set()
    for experiment_id in payload.experiment_ids:
        normalized_id = experiment_id.strip()
        if not normalized_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="experimentIds cannot include empty values.",
            )
        if normalized_id in seen_experiment_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"experimentIds contains duplicate angle id '{normalized_id}'.",
            )
        seen_experiment_ids.add(normalized_id)
        requested_experiment_ids.append(normalized_id)

    wf_repo = WorkflowsRepository(session)
    temporal = await get_temporal_client()
    campaign_workflows = wf_repo.list(org_id=auth.org_id, campaign_id=str(campaign.id))
    running_funnel_workflows = [
        run
        for run in campaign_workflows
        if run.kind == "campaign_funnel_generation" and run.status == "running"
    ]
    if running_funnel_workflows:
        status_map = {
            WorkflowExecutionStatus.RUNNING: WorkflowStatusEnum.running,
            WorkflowExecutionStatus.COMPLETED: WorkflowStatusEnum.completed,
            WorkflowExecutionStatus.FAILED: WorkflowStatusEnum.failed,
            WorkflowExecutionStatus.CANCELED: WorkflowStatusEnum.cancelled,
            WorkflowExecutionStatus.TERMINATED: WorkflowStatusEnum.cancelled,
            WorkflowExecutionStatus.TIMED_OUT: WorkflowStatusEnum.failed,
            WorkflowExecutionStatus.CONTINUED_AS_NEW: WorkflowStatusEnum.running,
        }
        for running_run in running_funnel_workflows:
            try:
                handle = temporal.get_workflow_handle(
                    running_run.temporal_workflow_id,
                    first_execution_run_id=running_run.temporal_run_id,
                )
                desc = await handle.describe()
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=(
                        "Failed to verify the status of an in-progress funnel workflow. "
                        "Retry after Temporal is reachable."
                    ),
                ) from exc
            new_status = status_map.get(desc.status) if desc else None
            finished_at = getattr(desc, "close_time", None)
            if new_status and (new_status != running_run.status or finished_at):
                wf_repo.set_status(
                    org_id=auth.org_id,
                    workflow_run_id=str(running_run.id),
                    status=new_status,
                    finished_at=finished_at,
                )
        campaign_workflows = wf_repo.list(org_id=auth.org_id, campaign_id=str(campaign.id))
    running_funnel_workflow = next(
        (
            run
            for run in campaign_workflows
            if run.kind == "campaign_funnel_generation" and run.status == "running"
        ),
        None,
    )
    if running_funnel_workflow:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A funnel generation workflow is already running for this campaign. Wait for it to finish.",
        )

    funnels_repo = FunnelsRepository(session)
    existing_funnels = funnels_repo.list(org_id=auth.org_id, campaign_id=str(campaign.id))
    existing_experiment_ids = {
        str(funnel.experiment_spec_id).strip()
        for funnel in existing_funnels
        if isinstance(funnel.experiment_spec_id, str) and funnel.experiment_spec_id.strip()
    }
    duplicate_experiment_ids = [exp_id for exp_id in requested_experiment_ids if exp_id in existing_experiment_ids]
    if duplicate_experiment_ids:
        joined_ids = ", ".join(duplicate_experiment_ids)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Funnels already exist for angle ids: {joined_ids}.",
        )

    handle = await temporal.start_workflow(
        CampaignFunnelGenerationWorkflow.run,
        CampaignFunnelGenerationInput(
            org_id=auth.org_id,
            client_id=str(campaign.client_id),
            product_id=str(campaign.product_id),
            campaign_id=str(campaign.id),
            experiment_ids=requested_experiment_ids,
            variant_ids_by_experiment=payload.variant_ids_by_experiment,
            funnel_name_prefix=f"{campaign.name} Funnel",
            generate_testimonials=bool(payload.generateTestimonials),
        ),
        id=f"campaign-funnels-{auth.org_id}-{campaign_id}-{uuid4()}",
        task_queue=settings.TEMPORAL_TASK_QUEUE,
    )

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
            "experiment_ids": requested_experiment_ids,
            "variant_ids_by_experiment": payload.variant_ids_by_experiment,
        },
    )

    return {"workflow_run_id": str(run.id), "temporal_workflow_id": handle.id}


@router.post("/{campaign_id}/creative/produce")
async def start_creative_production(
    campaign_id: str,
    payload: CreativeProductionRequest,
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
            detail="Campaign is missing a product_id. Attach a product before starting creative production.",
        )

    asset_brief_ids = payload.asset_brief_ids
    artifacts_repo = ArtifactsRepository(session)
    brief_artifacts = artifacts_repo.list(
        org_id=auth.org_id,
        client_id=str(campaign.client_id),
        campaign_id=str(campaign.id),
        artifact_type=ArtifactTypeEnum.asset_brief,
        limit=200,
    )
    brief_map: dict[str, dict] = {}
    for art in brief_artifacts:
        data = art.data if isinstance(art.data, dict) else {}
        briefs = data.get("asset_briefs") or data.get("assetBriefs") or []
        if not isinstance(briefs, list):
            continue
        for brief in briefs:
            if not isinstance(brief, dict):
                continue
            brief_id = brief.get("id")
            if isinstance(brief_id, str) and brief_id.strip():
                # Keep the first-seen (latest artifact list is already newest-first).
                brief_map.setdefault(brief_id.strip(), brief)

    missing = [brief_id for brief_id in asset_brief_ids if brief_id not in brief_map]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Some asset briefs were not found.", "missingAssetBriefIds": missing},
        )

    temporal = await get_temporal_client()
    temporal_workflow_id = f"creative-production-{auth.org_id}-{campaign_id}-{uuid4()}"

    wf_repo = WorkflowsRepository(session)
    run = WorkflowRun(
        org_id=auth.org_id,
        client_id=str(campaign.client_id),
        product_id=str(campaign.product_id),
        campaign_id=str(campaign.id),
        temporal_workflow_id=temporal_workflow_id,
        temporal_run_id="pending",
        kind="creative_production",
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    try:
        handle = await temporal.start_workflow(
            CreativeProductionWorkflow.run,
            CreativeProductionInput(
                org_id=auth.org_id,
                client_id=str(campaign.client_id),
                product_id=str(campaign.product_id),
                campaign_id=str(campaign.id),
                asset_brief_ids=asset_brief_ids,
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
            detail="Failed to start creative production workflow.",
        ) from exc

    run.temporal_run_id = handle.first_execution_run_id
    session.commit()

    wf_repo.log_activity(
        workflow_run_id=str(run.id),
        step="creative_production",
        status="started",
        payload_in={"campaign_id": str(campaign.id), "asset_brief_ids": asset_brief_ids},
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
