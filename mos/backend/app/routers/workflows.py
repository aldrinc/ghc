from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from uuid import UUID

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.enums import ArtifactTypeEnum, AssetStatusEnum, WorkflowStatusEnum
from app.db.models import Asset
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.research_artifacts import ResearchArtifactsRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.google_clients import download_drive_text_file
from app.temporal.client import get_temporal_client
from temporalio.api.enums.v1 import WorkflowExecutionStatus

router = APIRouter(prefix="/workflows", tags=["workflows"])


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


def _maybe_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


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
    run = None
    parsed_run_id = _maybe_uuid(workflow_run_id)
    if parsed_run_id:
        run = repo.get(org_id=auth.org_id, workflow_run_id=str(parsed_run_id))
    if not run:
        # Allow using Temporal workflow IDs (e.g. campaign-planning-...) to fetch runs.
        run = repo.get_by_temporal_workflow_id(org_id=auth.org_id, temporal_workflow_id=workflow_run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")

    temporal_status = None
    try:
        client = await get_temporal_client()
        handle = client.get_workflow_handle(
            run.temporal_workflow_id,
            first_execution_run_id=run.temporal_run_id,
        )
        desc = await handle.describe()
        temporal_status = desc.status.name if desc and getattr(desc, "status", None) else None
        status_map = _workflow_status_map()
        new_status = status_map.get(getattr(desc, "status", None)) if desc else None
        finished_at = getattr(desc, "close_time", None)
        if new_status and (new_status != run.status or finished_at):
            repo.set_status(
                org_id=auth.org_id,
                workflow_run_id=workflow_run_id,
                status=new_status,
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

    research_artifacts_repo = ResearchArtifactsRepository(session)
    research_artifacts_rows = research_artifacts_repo.list_for_workflow_run(
        org_id=auth.org_id,
        workflow_run_id=str(run.id),
    )
    research_artifacts = [
        {
            "step_key": row.step_key,
            "title": row.title,
            "doc_url": row.doc_url,
            "doc_id": row.doc_id,
            "summary": row.summary,
        }
        for row in research_artifacts_rows
    ]

    precanon_research = None
    research_highlights = None
    if client_canon and isinstance(client_canon.data, dict):
        precanon_research = client_canon.data.get("precanon_research")
        research_highlights = client_canon.data.get("research_highlights")

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


@router.get("/{workflow_run_id}/research/{step_key}")
def get_workflow_research_artifact(
    workflow_run_id: str,
    step_key: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Return the *full* research artifact content for a given workflow + step.

    The workflow detail endpoint returns only lightweight research artifact refs + summaries.
    Full text is retrieved from the persisted Drive file on-demand so the UI can render the
    complete document even while a workflow is still running (before client canon exists).
    """
    repo = WorkflowsRepository(session)
    run = None
    parsed_run_id = _maybe_uuid(workflow_run_id)
    if parsed_run_id:
        run = repo.get(org_id=auth.org_id, workflow_run_id=str(parsed_run_id))
    if not run:
        run = repo.get_by_temporal_workflow_id(org_id=auth.org_id, temporal_workflow_id=workflow_run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")

    research_repo = ResearchArtifactsRepository(session)
    record = research_repo.get_for_step(org_id=auth.org_id, workflow_run_id=str(run.id), step_key=step_key)
    if not record:
        raise HTTPException(status_code=404, detail="Research artifact not found for this step")

    doc_url = getattr(record, "doc_url", None) or ""
    doc_id = getattr(record, "doc_id", None) or ""
    if not doc_id:
        raise HTTPException(status_code=500, detail="Research artifact is missing a doc_id")

    if isinstance(doc_url, str) and doc_url.startswith("drive-stub://"):
        raise HTTPException(
            status_code=409,
            detail="Research artifact was persisted with a Drive stub; full content is unavailable.",
        )

    try:
        content = download_drive_text_file(file_id=doc_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return jsonable_encoder(
        {
            "step_key": record.step_key,
            "title": record.title,
            "doc_url": record.doc_url,
            "doc_id": record.doc_id,
            "summary": record.summary,
            "content": content,
        }
    )


async def _get_handle(session: Session, auth: AuthContext, workflow_run_id: str):
    repo = WorkflowsRepository(session)
    run = None
    parsed_run_id = _maybe_uuid(workflow_run_id)
    if parsed_run_id:
        run = repo.get(org_id=auth.org_id, workflow_run_id=str(parsed_run_id))
    if not run:
        # Allow using Temporal workflow IDs (e.g. campaign-planning-...) for signals.
        run = repo.get_by_temporal_workflow_id(org_id=auth.org_id, temporal_workflow_id=workflow_run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    client = await get_temporal_client()
    return repo, run, client.get_workflow_handle(
        run.temporal_workflow_id,
        first_execution_run_id=run.temporal_run_id,
    )


@router.post("/{workflow_run_id}/signals/approve-canon")
async def approve_canon(
    workflow_run_id: str,
    body: dict,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    raise HTTPException(
        status_code=410,
        detail="Canon approval has been removed. Client onboarding is auto-approved and no longer waits for canon approval.",
    )


@router.post("/{workflow_run_id}/signals/approve-metric-schema")
async def approve_metric_schema(
    workflow_run_id: str,
    body: dict,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    raise HTTPException(
        status_code=410,
        detail="Metric schema approval has been removed. Client onboarding is auto-approved and no longer waits for metric schema approval.",
    )


@router.post("/{workflow_run_id}/signals/approve-strategy")
async def approve_strategy(
    workflow_run_id: str,
    body: dict,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    raise HTTPException(
        status_code=410,
        detail="Strategy approval has been removed. Campaign planning and campaign intent now auto-approve the strategy sheet and wait for experiment approvals instead.",
    )


@router.post("/{workflow_run_id}/signals/approve-experiments")
async def approve_experiments(
    workflow_run_id: str,
    body: dict,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo, run, handle = await _get_handle(session, auth, workflow_run_id)
    await handle.signal(
        "approve_experiments",
        {
            "approved_ids": body.get("approved_ids", []),
            "rejected_ids": body.get("rejected_ids", []),
            "edited_specs": body.get("edited_specs"),
        },
    )
    repo.log_activity(
        workflow_run_id=str(run.id),
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

    repo, run, handle = await _get_handle(session, auth, workflow_run_id)
    await handle.signal("approve_asset_briefs", {"approved_ids": approved_ids})
    repo.log_activity(
        workflow_run_id=str(run.id),
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

    repo, run, handle = await _get_handle(session, auth, workflow_run_id)
    await handle.signal(
        "approve_assets",
        {"approved_ids": approved_ids, "rejected_ids": rejected_ids},
    )
    repo.log_activity(
        workflow_run_id=str(run.id),
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
    repo, run, handle = await _get_handle(session, auth, workflow_run_id)
    await handle.signal("stop")
    repo.log_activity(
        workflow_run_id=str(run.id),
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
    run = None
    parsed_run_id = _maybe_uuid(workflow_run_id)
    if parsed_run_id:
        run = repo.get(org_id=auth.org_id, workflow_run_id=str(parsed_run_id))
    if not run:
        run = repo.get_by_temporal_workflow_id(org_id=auth.org_id, temporal_workflow_id=workflow_run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    logs = repo.list_logs(org_id=auth.org_id, workflow_run_id=str(run.id))
    return jsonable_encoder(logs)
