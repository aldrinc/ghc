from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.config import settings
from app.db.deps import get_session
from app.db.enums import ArtifactTypeEnum, WorkflowStatusEnum
from app.db.models import Asset, Funnel, FunnelPage, WorkflowRun
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.campaigns import CampaignsRepository
from app.db.repositories.funnels import FunnelsRepository
from app.db.repositories.meta_ads import MetaAdsRepository
from app.db.repositories.products import ProductsRepository
from app.db.repositories.strategy_v2_launches import StrategyV2LaunchesRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.schemas.common import CampaignCreate
from app.schemas.campaign_funnels import CampaignFunnelGenerationRequest
from app.schemas.creative_production import CreativeProductionRequest
from app.schemas.experiment_spec import ExperimentSpecSet, ExperimentSpecsUpdateRequest
from app.schemas.meta_ads import CampaignMetaReviewSetupRequest
from app.services.public_routing import require_product_route_slug
from app.temporal.client import get_temporal_client
from app.temporal.workflows.campaign_planning import CampaignPlanningInput, CampaignPlanningWorkflow
from app.temporal.workflows.campaign_funnel_generation import (
    CampaignFunnelGenerationInput,
    CampaignFunnelGenerationWorkflow,
)
from app.temporal.workflows.creative_production import CreativeProductionInput, CreativeProductionWorkflow
from app.strategy_v2.downstream import require_strategy_v2_outputs_if_enabled
from app.strategy_v2.feature_flags import is_strategy_v2_enabled
from temporalio.api.enums.v1 import WorkflowExecutionStatus


def _workflow_execution_status_member(*names: str):
    for name in names:
        member = getattr(WorkflowExecutionStatus, name, None)
        if member is not None:
            return member
    return None


def _workflow_status_map() -> dict[object, WorkflowStatusEnum]:
    mapping: dict[object, WorkflowStatusEnum] = {}
    candidates: list[tuple[tuple[str, ...], WorkflowStatusEnum]] = [
        (("RUNNING", "WORKFLOW_EXECUTION_STATUS_RUNNING"), WorkflowStatusEnum.running),
        (("COMPLETED", "WORKFLOW_EXECUTION_STATUS_COMPLETED"), WorkflowStatusEnum.completed),
        (("FAILED", "WORKFLOW_EXECUTION_STATUS_FAILED"), WorkflowStatusEnum.failed),
        (("CANCELED", "CANCELLED", "WORKFLOW_EXECUTION_STATUS_CANCELED"), WorkflowStatusEnum.cancelled),
        (("TERMINATED", "WORKFLOW_EXECUTION_STATUS_TERMINATED"), WorkflowStatusEnum.cancelled),
        (("TIMED_OUT", "WORKFLOW_EXECUTION_STATUS_TIMED_OUT"), WorkflowStatusEnum.failed),
        (("CONTINUED_AS_NEW", "WORKFLOW_EXECUTION_STATUS_CONTINUED_AS_NEW"), WorkflowStatusEnum.running),
    ]
    for names, internal_status in candidates:
        member = _workflow_execution_status_member(*names)
        if member is not None:
            mapping[member] = internal_status
    return mapping


def _load_campaign_asset_brief_map(
    *,
    org_id: str,
    client_id: str,
    campaign_id: str,
    session: Session,
) -> dict[str, dict]:
    artifacts_repo = ArtifactsRepository(session)
    brief_artifacts = artifacts_repo.list(
        org_id=org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        artifact_type=ArtifactTypeEnum.asset_brief,
        limit=200,
    )
    brief_map: dict[str, dict] = {}
    for artifact in brief_artifacts:
        data = artifact.data if isinstance(artifact.data, dict) else {}
        briefs = data.get("asset_briefs") or data.get("assetBriefs") or []
        if not isinstance(briefs, list):
            continue
        for brief in briefs:
            if not isinstance(brief, dict):
                continue
            brief_id = brief.get("id")
            if isinstance(brief_id, str) and brief_id.strip() and brief_id.strip() not in brief_map:
                brief_map[brief_id.strip()] = brief
    return brief_map


def _resolve_funnel_review_paths(
    *,
    org_id: str,
    product_id: str,
    funnel_ids: set[str],
    session: Session,
) -> dict[str, dict[str, str]]:
    if not funnel_ids:
        return {}

    product = ProductsRepository(session).get(org_id=org_id, product_id=product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    product_route_slug = require_product_route_slug(product=product)

    funnels = session.scalars(
        select(Funnel).where(
            Funnel.org_id == org_id,
            Funnel.id.in_(list(funnel_ids)),
        )
    ).all()
    funnel_map = {str(funnel.id): funnel for funnel in funnels}
    pages = session.scalars(
        select(FunnelPage).where(
            FunnelPage.funnel_id.in_(list(funnel_ids)),
        )
    ).all()

    by_funnel_id: dict[str, dict[str, str]] = {}
    for page in pages:
        funnel = funnel_map.get(str(page.funnel_id))
        if not funnel:
            continue
        by_funnel_id.setdefault(str(page.funnel_id), {})[page.slug] = (
            f"/f/{product_route_slug}/{funnel.route_slug}/{page.slug}"
        )
    return by_funnel_id


def _validate_planning_prereqs(
    *,
    org_id: str,
    client_id: str,
    product_id: str,
    session: Session,
) -> None:
    artifacts_repo = ArtifactsRepository(session)
    strategy_v2_required = is_strategy_v2_enabled(
        session=session,
        org_id=org_id,
        client_id=client_id,
    )
    if not strategy_v2_required:
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
    try:
        require_strategy_v2_outputs_if_enabled(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


def _strategy_v2_launch_row_payload(row, *, launch_status: str | None = None) -> dict:
    launch_type_raw = str(getattr(row, "launch_type", "") or "").strip()
    if launch_type_raw not in {"initial_angle", "additional_ums", "additional_angle"}:
        launch_type = "initial_angle"
    else:
        launch_type = launch_type_raw
    created_at = getattr(row, "created_at", None)
    created_at_iso = created_at.isoformat() if created_at else ""
    return {
        "id": str(getattr(row, "id")),
        "launch_type": launch_type,
        "launch_key": str(getattr(row, "launch_key", "") or ""),
        "campaign_id": str(getattr(row, "campaign_id")) if getattr(row, "campaign_id", None) else None,
        "funnel_id": str(getattr(row, "funnel_id")) if getattr(row, "funnel_id", None) else None,
        "angle_id": str(getattr(row, "angle_id", "") or ""),
        "angle_run_id": str(getattr(row, "angle_run_id", "") or ""),
        "selected_ums_id": str(getattr(row, "selected_ums_id")) if getattr(row, "selected_ums_id", None) else None,
        "selected_variant_id": (
            str(getattr(row, "selected_variant_id")) if getattr(row, "selected_variant_id", None) else None
        ),
        "launch_index": int(getattr(row, "launch_index")) if getattr(row, "launch_index", None) is not None else None,
        "launch_workflow_run_id": (
            str(getattr(row, "launch_workflow_run_id")) if getattr(row, "launch_workflow_run_id", None) else None
        ),
        "launch_temporal_workflow_id": (
            str(getattr(row, "launch_temporal_workflow_id"))
            if getattr(row, "launch_temporal_workflow_id", None)
            else None
        ),
        "launch_status": launch_status,
        "created_by_user": str(getattr(row, "created_by_user")) if getattr(row, "created_by_user", None) else None,
        "created_at": created_at_iso,
    }


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


@router.get("/{campaign_id}/strategy-v2-launches")
def list_campaign_strategy_v2_launches(
    campaign_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    campaign = CampaignsRepository(session).get(org_id=auth.org_id, campaign_id=campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    launches_repo = StrategyV2LaunchesRepository(session)
    workflow_repo = WorkflowsRepository(session)
    rows = launches_repo.list_for_campaign(org_id=auth.org_id, campaign_id=campaign_id)
    status_by_workflow_run_id: dict[str, str | None] = {}
    for row in rows:
        launch_workflow_run_id_raw = getattr(row, "launch_workflow_run_id", None)
        if launch_workflow_run_id_raw is None:
            continue
        launch_workflow_run_id = str(launch_workflow_run_id_raw)
        if launch_workflow_run_id in status_by_workflow_run_id:
            continue
        linked_run = workflow_repo.get(org_id=auth.org_id, workflow_run_id=launch_workflow_run_id)
        status_by_workflow_run_id[launch_workflow_run_id] = linked_run.status.value if linked_run else None

    payload_rows = []
    for row in rows:
        launch_workflow_run_id_raw = getattr(row, "launch_workflow_run_id", None)
        launch_status = (
            status_by_workflow_run_id.get(str(launch_workflow_run_id_raw))
            if launch_workflow_run_id_raw is not None
            else None
        )
        payload_rows.append(_strategy_v2_launch_row_payload(row, launch_status=launch_status))

    return jsonable_encoder(payload_rows)


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
    try:
        require_strategy_v2_outputs_if_enabled(
            session=session,
            org_id=auth.org_id,
            client_id=str(campaign.client_id),
            product_id=str(campaign.product_id),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
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
        status_map = _workflow_status_map()
        for running_run in running_funnel_workflows:
            try:
                handle = temporal.get_workflow_handle(
                    running_run.temporal_workflow_id,
                    first_execution_run_id=running_run.temporal_run_id,
                )
                desc = await handle.describe()
            except Exception:
                continue
            new_status = status_map.get(getattr(desc, "status", None)) if desc else None
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
            variant_activity_concurrency=payload.variant_activity_concurrency,
            async_media_enrichment=bool(payload.async_media_enrichment),
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
            "variant_activity_concurrency": payload.variant_activity_concurrency,
            "async_media_enrichment": bool(payload.async_media_enrichment),
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


@router.post("/{campaign_id}/meta/review-setup")
def setup_campaign_meta_review(
    campaign_id: str,
    payload: CampaignMetaReviewSetupRequest,
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
            detail="Campaign is missing a product_id. Attach a product before setting up Meta review.",
        )

    brief_map = _load_campaign_asset_brief_map(
        org_id=auth.org_id,
        client_id=str(campaign.client_id),
        campaign_id=str(campaign.id),
        session=session,
    )
    if not brief_map:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No asset briefs exist for this campaign. Generate briefs before setting up Meta review.",
        )

    selected_brief_ids = payload.assetBriefIds or list(brief_map.keys())
    missing_brief_ids = [brief_id for brief_id in selected_brief_ids if brief_id not in brief_map]
    if missing_brief_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "Some asset briefs were not found for this campaign.",
                "missingAssetBriefIds": missing_brief_ids,
            },
        )

    campaign_assets = session.scalars(
        select(Asset).where(
            Asset.org_id == auth.org_id,
            Asset.campaign_id == str(campaign.id),
            Asset.file_status == "ready",
        )
    ).all()

    assets_by_brief_id: dict[str, list[Asset]] = {brief_id: [] for brief_id in selected_brief_ids}
    for asset in campaign_assets:
        metadata = asset.ai_metadata if isinstance(asset.ai_metadata, dict) else {}
        brief_id = metadata.get("assetBriefId")
        if isinstance(brief_id, str) and brief_id in assets_by_brief_id:
            assets_by_brief_id[brief_id].append(asset)

    missing_asset_briefs = [brief_id for brief_id, assets in assets_by_brief_id.items() if not assets]
    if missing_asset_briefs:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "No generated campaign assets exist for some selected briefs. Run creative generation first.",
                "missingAssetBriefIds": missing_asset_briefs,
            },
        )

    funnel_ids = {
        str(brief.get("funnelId")).strip()
        for brief in (brief_map[brief_id] for brief_id in selected_brief_ids)
        if isinstance(brief.get("funnelId"), str) and brief.get("funnelId").strip()
    }
    review_paths_by_funnel_id = _resolve_funnel_review_paths(
        org_id=auth.org_id,
        product_id=str(campaign.product_id),
        funnel_ids=funnel_ids,
        session=session,
    )

    meta_repo = MetaAdsRepository(session)
    existing_creative_specs = {
        str(record.asset_id): record
        for record in meta_repo.list_creative_specs(org_id=auth.org_id, campaign_id=str(campaign.id))
    }
    existing_adset_specs_by_experiment: dict[str, object] = {}
    for record in meta_repo.list_adset_specs(org_id=auth.org_id, campaign_id=str(campaign.id)):
        metadata = record.metadata_json if isinstance(record.metadata_json, dict) else {}
        experiment_key = None
        if record.experiment_id:
            experiment_key = str(record.experiment_id)
        elif isinstance(metadata.get("experimentSpecId"), str) and metadata.get("experimentSpecId").strip():
            experiment_key = metadata.get("experimentSpecId").strip()
        if experiment_key and experiment_key not in existing_adset_specs_by_experiment:
            existing_adset_specs_by_experiment[experiment_key] = record

    created_creative_spec_ids: list[str] = []
    reused_creative_spec_ids: list[str] = []
    created_adset_spec_ids: list[str] = []
    reused_adset_spec_ids: list[str] = []

    for brief_id in selected_brief_ids:
        brief = brief_map[brief_id]
        experiment_id = brief.get("experimentId")
        if not isinstance(experiment_id, str) or not experiment_id.strip():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Asset brief '{brief_id}' is missing experimentId.",
            )
        experiment_id = experiment_id.strip()

        adset_spec = existing_adset_specs_by_experiment.get(experiment_id)
        if adset_spec is None:
            new_adset_spec = meta_repo.create_adset_spec(
                org_id=auth.org_id,
                campaign_id=str(campaign.id),
                name=brief.get("variantName") or brief.get("creativeConcept") or experiment_id,
                status="draft",
                metadata_json={
                    "source": "campaign_meta_review_setup",
                    "experimentSpecId": experiment_id,
                    "campaignGoalDescription": campaign.goal_description,
                    "campaignChannels": campaign.channels or [],
                    "variantId": brief.get("variantId"),
                    "variantName": brief.get("variantName"),
                    "assetBriefIds": [candidate for candidate in selected_brief_ids if brief_map[candidate].get("experimentId") == experiment_id],
                },
            )
            existing_adset_specs_by_experiment[experiment_id] = new_adset_spec
            created_adset_spec_ids.append(str(new_adset_spec.id))
        else:
            reused_adset_spec_ids.append(str(adset_spec.id))

        requirements = brief.get("requirements") or []
        if not isinstance(requirements, list) or not requirements:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Asset brief '{brief_id}' has no requirements.",
            )

        review_paths = {}
        raw_funnel_id = brief.get("funnelId")
        if isinstance(raw_funnel_id, str) and raw_funnel_id.strip():
            review_paths = review_paths_by_funnel_id.get(raw_funnel_id.strip(), {})

        for asset in assets_by_brief_id[brief_id]:
            existing_creative = existing_creative_specs.get(str(asset.id))
            if existing_creative is not None:
                reused_creative_spec_ids.append(str(existing_creative.id))
                continue

            metadata = asset.ai_metadata if isinstance(asset.ai_metadata, dict) else {}
            requirement_index = metadata.get("requirementIndex")
            if not isinstance(requirement_index, int):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Generated asset '{asset.id}' is missing an integer ai_metadata.requirementIndex.",
                )
            if requirement_index < 0 or requirement_index >= len(requirements):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Generated asset '{asset.id}' requirementIndex={requirement_index} is out of range "
                        f"for asset brief '{brief_id}'."
                    ),
                )

            requirement = requirements[requirement_index]
            if not isinstance(requirement, dict):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Asset brief '{brief_id}' requirement at index {requirement_index} must be an object.",
                )

            new_creative_spec = meta_repo.create_creative_spec(
                org_id=auth.org_id,
                asset_id=str(asset.id),
                campaign_id=str(campaign.id),
                name=" · ".join(
                    [
                        str(campaign.name).strip(),
                        str(brief.get("variantName") or experiment_id).strip(),
                        str(requirement.get("funnelStage") or requirement.get("channel") or "creative").strip(),
                    ]
                ),
                primary_text=brief.get("creativeConcept"),
                headline=requirement.get("hook"),
                description=requirement.get("angle"),
                page_id=settings.META_PAGE_ID,
                instagram_actor_id=settings.META_INSTAGRAM_ACTOR_ID,
                status="draft",
                metadata_json={
                    "source": "campaign_meta_review_setup",
                    "experimentSpecId": experiment_id,
                    "experimentName": brief.get("variantName") or experiment_id,
                    "assetBriefId": brief_id,
                    "requirementIndex": requirement_index,
                    "requirement": requirement,
                    "reviewPaths": review_paths,
                    "variantId": brief.get("variantId"),
                    "variantName": brief.get("variantName"),
                    "funnelId": raw_funnel_id,
                },
            )
            created_creative_spec_ids.append(str(new_creative_spec.id))

    return {
        "campaignId": str(campaign.id),
        "assetBriefIds": selected_brief_ids,
        "assetCount": sum(len(items) for items in assets_by_brief_id.values()),
        "createdCreativeSpecIds": created_creative_spec_ids,
        "reusedCreativeSpecIds": reused_creative_spec_ids,
        "createdAdSetSpecIds": created_adset_spec_ids,
        "reusedAdSetSpecIds": reused_adset_spec_ids,
    }


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
