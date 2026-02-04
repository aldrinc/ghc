from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.enums import ArtifactTypeEnum, AssetStatusEnum, WorkflowStatusEnum
from app.db.models import Asset
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.temporal.client import get_temporal_client
from temporalio.api.enums.v1 import WorkflowExecutionStatus

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("")
def list_workflows(
    clientId: str | None = None,
    productId: str | None = None,
    campaignId: str | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list:
    if (clientId and not productId and campaignId is None) or (productId and not clientId):
        raise HTTPException(
            status_code=400,
            detail="clientId and productId are required together unless campaignId is provided.",
        )
    repo = WorkflowsRepository(session)
    return jsonable_encoder(
        repo.list(
            org_id=auth.org_id,
            client_id=clientId,
            product_id=productId,
            campaign_id=campaignId,
        )
    )


@router.get("/{workflow_run_id}")
async def get_workflow_run(
    workflow_run_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = WorkflowsRepository(session)
    run = repo.get(org_id=auth.org_id, workflow_run_id=workflow_run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")

    temporal_status = None
    try:
        client = await get_temporal_client()
        handle = client.get_workflow_handle(run.temporal_workflow_id)
        desc = await handle.describe()
        temporal_status = desc.status.name if desc and getattr(desc, "status", None) else None
        status_map = {
            WorkflowExecutionStatus.RUNNING: WorkflowStatusEnum.running,
            WorkflowExecutionStatus.COMPLETED: WorkflowStatusEnum.completed,
            WorkflowExecutionStatus.FAILED: WorkflowStatusEnum.failed,
            WorkflowExecutionStatus.CANCELED: WorkflowStatusEnum.cancelled,
            WorkflowExecutionStatus.TERMINATED: WorkflowStatusEnum.cancelled,
            WorkflowExecutionStatus.TIMED_OUT: WorkflowStatusEnum.failed,
            WorkflowExecutionStatus.CONTINUED_AS_NEW: WorkflowStatusEnum.running,
        }
        new_status = status_map.get(desc.status) if desc else None
        finished_at = getattr(desc, "close_time", None)
        if new_status and (new_status != run.status or finished_at):
            repo.set_status(
                org_id=auth.org_id,
                workflow_run_id=workflow_run_id,
                status=new_status,  # type: ignore[arg-type]
                finished_at=finished_at,
            )
            run = repo.get(org_id=auth.org_id, workflow_run_id=workflow_run_id) or run
    except Exception:
        # If Temporal is unreachable, still return persisted data.
        pass

    logs = repo.list_logs(org_id=auth.org_id, workflow_run_id=workflow_run_id)

    artifacts_repo = ArtifactsRepository(session)
    client_canon = None
    metric_schema = None
    strategy_sheet = None
    if run.client_id and run.product_id:
        client_canon = artifacts_repo.get_latest_by_type(
            org_id=auth.org_id,
            client_id=run.client_id,
            artifact_type=ArtifactTypeEnum.client_canon,
            product_id=run.product_id,
        )
        metric_schema = artifacts_repo.get_latest_by_type(
            org_id=auth.org_id,
            client_id=run.client_id,
            artifact_type=ArtifactTypeEnum.metric_schema,
            product_id=run.product_id,
        )
    if run.campaign_id:
        strategy_sheet = artifacts_repo.get_latest_by_type_for_campaign(
            org_id=auth.org_id, campaign_id=run.campaign_id, artifact_type=ArtifactTypeEnum.strategy_sheet
        )
        experiment_specs = artifacts_repo.list(
            org_id=auth.org_id,
            campaign_id=run.campaign_id,
            artifact_type=ArtifactTypeEnum.experiment_spec,
            limit=50,
        )
        asset_briefs = artifacts_repo.list(
            org_id=auth.org_id,
            campaign_id=run.campaign_id,
            artifact_type=ArtifactTypeEnum.asset_brief,
            limit=50,
        )
    else:
        experiment_specs = []
        asset_briefs = []

    precanon_research = None
    research_artifacts = None
    research_highlights = None
    if client_canon and isinstance(client_canon.data, dict):
        precanon_research = client_canon.data.get("precanon_research")
        research_highlights = client_canon.data.get("research_highlights")
        if isinstance(precanon_research, dict):
            research_artifacts = precanon_research.get("artifact_refs")

    return jsonable_encoder(
        {
            "run": run,
            "logs": logs,
            "client_canon": client_canon,
            "metric_schema": metric_schema,
            "strategy_sheet": strategy_sheet,
            "experiment_specs": experiment_specs,
            "asset_briefs": asset_briefs,
            "precanon_research": precanon_research,
            "research_artifacts": research_artifacts,
            "research_highlights": research_highlights,
            "temporal_status": temporal_status,
        }
    )


async def _get_handle(session: Session, auth: AuthContext, workflow_run_id: str):
    repo = WorkflowsRepository(session)
    run = repo.get(org_id=auth.org_id, workflow_run_id=workflow_run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    client = await get_temporal_client()
    return repo, client.get_workflow_handle(run.temporal_workflow_id)


@router.post("/{workflow_run_id}/signals/approve-canon")
async def approve_canon(
    workflow_run_id: str,
    body: dict,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo, handle = await _get_handle(session, auth, workflow_run_id)
    await handle.signal(
        "approve_canon",
        {"approved": body.get("approved", False), "updated_canon": body.get("updatedCanon")},
    )
    repo.log_activity(
        workflow_run_id=workflow_run_id,
        step="approve_canon",
        status="sent",
        payload_in={"approved": body.get("approved", False)},
    )
    return {"ok": True}


@router.post("/{workflow_run_id}/signals/approve-metric-schema")
async def approve_metric_schema(
    workflow_run_id: str,
    body: dict,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo, handle = await _get_handle(session, auth, workflow_run_id)
    await handle.signal(
        "approve_metric_schema",
        {"approved": body.get("approved", False), "updated_schema": body.get("updatedSchema")},
    )
    repo.log_activity(
        workflow_run_id=workflow_run_id,
        step="approve_metric_schema",
        status="sent",
        payload_in={"approved": body.get("approved", False)},
    )
    return {"ok": True}


@router.post("/{workflow_run_id}/signals/approve-strategy")
async def approve_strategy(
    workflow_run_id: str,
    body: dict,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo, handle = await _get_handle(session, auth, workflow_run_id)
    await handle.signal(
        "approve_strategy_sheet",
        {"approved": body.get("approved", False), "updated_strategy_sheet": body.get("updatedStrategy")},
    )
    repo.log_activity(
        workflow_run_id=workflow_run_id,
        step="approve_strategy_sheet",
        status="sent",
        payload_in={"approved": body.get("approved", False)},
    )
    return {"ok": True}


@router.post("/{workflow_run_id}/signals/approve-experiments")
async def approve_experiments(
    workflow_run_id: str,
    body: dict,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo, handle = await _get_handle(session, auth, workflow_run_id)
    await handle.signal(
        "approve_experiments",
        {
            "approved_ids": body.get("approved_ids", []),
            "rejected_ids": body.get("rejected_ids", []),
            "edited_specs": body.get("edited_specs"),
        },
    )
    repo.log_activity(
        workflow_run_id=workflow_run_id,
        step="approve_experiments",
        status="sent",
        payload_in={
            "approved_ids": body.get("approved_ids", []),
            "rejected_ids": body.get("rejected_ids", []),
        },
    )
    return {"ok": True}


@router.post("/{workflow_run_id}/signals/approve-asset-briefs")
async def approve_asset_briefs(
    workflow_run_id: str,
    body: dict,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    approved_ids = body.get("approved_ids", [])
    if not isinstance(approved_ids, list):
        raise HTTPException(status_code=400, detail="approved_ids must be a list.")

    repo, handle = await _get_handle(session, auth, workflow_run_id)
    await handle.signal("approve_asset_briefs", {"approved_ids": approved_ids})
    repo.log_activity(
        workflow_run_id=workflow_run_id,
        step="approve_asset_briefs",
        status="sent",
        payload_in={"approved_ids": approved_ids},
    )
    return {"ok": True}


@router.post("/{workflow_run_id}/signals/approve-assets")
async def approve_assets(
    workflow_run_id: str,
    body: dict,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    approved_ids = body.get("approved_ids", [])
    rejected_ids = body.get("rejected_ids", [])
    if not isinstance(approved_ids, list) or not isinstance(rejected_ids, list):
        raise HTTPException(status_code=400, detail="approved_ids and rejected_ids must be lists.")
    approved_set = {str(asset_id) for asset_id in approved_ids}
    rejected_set = {str(asset_id) for asset_id in rejected_ids}
    overlap = approved_set.intersection(rejected_set)
    if overlap:
        raise HTTPException(status_code=400, detail="Assets cannot be both approved and rejected.")

    all_ids = approved_set.union(rejected_set)
    if all_ids:
        existing_ids = session.scalars(
            select(Asset.id).where(Asset.org_id == auth.org_id, Asset.id.in_(list(all_ids)))
        ).all()
        existing_set = {str(asset_id) for asset_id in existing_ids}
        missing = all_ids.difference(existing_set)
        if missing:
            raise HTTPException(
                status_code=404,
                detail={"message": "Some assets were not found.", "missingAssetIds": sorted(missing)},
            )
        if approved_set:
            session.execute(
                update(Asset)
                .where(Asset.org_id == auth.org_id, Asset.id.in_(list(approved_set)))
                .values(status=AssetStatusEnum.approved)
            )
        if rejected_set:
            session.execute(
                update(Asset)
                .where(Asset.org_id == auth.org_id, Asset.id.in_(list(rejected_set)))
                .values(status=AssetStatusEnum.rejected)
            )
        session.commit()

    repo, handle = await _get_handle(session, auth, workflow_run_id)
    await handle.signal(
        "approve_assets",
        {"approved_ids": approved_ids, "rejected_ids": rejected_ids},
    )
    repo.log_activity(
        workflow_run_id=workflow_run_id,
        step="approve_assets",
        status="sent",
        payload_in={
            "approved_ids": approved_ids,
            "rejected_ids": rejected_ids,
        },
    )
    return {"ok": True}


@router.post("/{workflow_run_id}/signals/stop")
async def stop_workflow(
    workflow_run_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo, handle = await _get_handle(session, auth, workflow_run_id)
    await handle.signal("stop")
    repo.log_activity(
        workflow_run_id=workflow_run_id,
        step="stop",
        status="sent",
        payload_in={},
    )
    return {"ok": True}


@router.get("/{workflow_run_id}/logs")
def get_workflow_logs(
    workflow_run_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = WorkflowsRepository(session)
    logs = repo.list_logs(org_id=auth.org_id, workflow_run_id=workflow_run_id)
    return jsonable_encoder(logs)
