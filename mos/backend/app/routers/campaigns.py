from uuid import uuid4
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.config import settings
from app.db.deps import get_session
from app.db.enums import ArtifactTypeEnum, CampaignDeliveryValidationStatusEnum, WorkflowStatusEnum
from app.db.models import Asset, Funnel, FunnelPage, WorkflowRun
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.campaigns import CampaignsRepository
from app.db.repositories.campaign_delivery_configs import CampaignDeliveryConfigsRepository
from app.db.repositories.funnels import FunnelsRepository
from app.db.repositories.meta_ads import MetaAdsRepository
from app.db.repositories.products import ProductsRepository
from app.db.repositories.strategy_v2_launches import StrategyV2LaunchesRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.schemas.asset_brief_types import normalize_required_asset_brief_types
from app.schemas.campaign_creative_context import (
    CampaignCreativeContextProviderRequest,
    CampaignCreativeContextProviderResponse,
    CampaignCreativeContextReadinessResponse,
    CampaignManualCreativeContextUpsertRequest,
    CampaignManualCreativeContextUpsertResponse,
)
from app.schemas.campaign_delivery import (
    CampaignDeliveryResponse,
    CampaignDeliveryUpsertRequest,
    CampaignDeliveryValidationResponse,
)
from app.schemas.common import CampaignCreate
from app.schemas.campaign_funnels import CampaignFunnelGenerationRequest
from app.schemas.creative_generation import SwipeAdCopyPack, SwipeCopyInputs
from app.schemas.creative_production import CreativeProductionRequest
from app.schemas.experiment_spec import ExperimentSpecSet, ExperimentSpecsUpdateRequest
from app.schemas.meta_ads import CampaignMetaReviewSetupRequest
from app.services.meta_review import (
    asset_generation_key,
    brief_funnel_id,
    collect_brief_funnel_ids,
    load_campaign_asset_brief_map,
    normalize_meta_review_destination_page,
    resolve_meta_review_destination_url,
    select_assets_for_generation,
)
from app.services.meta_account_configs import MetaWorkspaceConfigError, resolve_workspace_config
from app.services.campaign_destinations import (
    CampaignDestinationError,
    campaign_delivery_destination_map,
    campaign_delivery_snapshot,
    requirement_destination_type,
    require_valid_external_delivery,
)
from app.services.campaign_delivery import (
    CampaignDeliveryConfigError,
    CampaignDeliveryValidationError,
    apply_normalized_delivery_update,
    campaign_delivery_response_payload,
    normalize_delivery_payload,
    validate_campaign_delivery_config,
    validation_response_payload,
)
from app.services.campaign_creative_context import (
    ensure_campaign_creative_context_ready,
    persist_manual_campaign_creative_context,
    set_campaign_creative_context_provider,
)
from app.services.paid_ads_qa import list_meta_copy_policy_issues
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


def _select_assets_for_meta_review(
    assets: list[Asset],
    *,
    generation_batch_id: str | None = None,
) -> list[Asset]:
    _, selected_assets = select_assets_for_generation(
        assets,
        generation_batch_id=generation_batch_id,
    )
    return selected_assets


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


def _resolve_meta_review_destination_url(
    *,
    destination_page: str,
    review_paths: dict[str, str],
) -> str | None:
    return resolve_meta_review_destination_url(destination_page=destination_page, review_paths=review_paths)


def _campaign_delivery_config_or_404(
    *,
    session: Session,
    org_id: str,
    campaign_id: str,
):
    config = _campaign_delivery_repo(session).get_by_campaign(org_id=org_id, campaign_id=campaign_id)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign delivery config not found.",
        )
    return config


def _require_campaign_creative_context_ready(
    *,
    session: Session,
    org_id: str,
    campaign_id: str,
) -> None:
    campaign = _get_campaign_or_404(session=session, org_id=org_id, campaign_id=campaign_id)
    readiness = ensure_campaign_creative_context_ready(
        session=session,
        org_id=org_id,
        campaign=campaign,
    )
    if not readiness["ready"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Campaign creative context is not ready for downstream execution.",
                "creativeContextReadiness": readiness,
            },
        )


def _resolve_meta_review_paths_for_campaign(
    *,
    campaign,
    session: Session,
    org_id: str,
    funnel_id: str | None,
):
    delivery_config = _campaign_delivery_config_or_404(
        session=session,
        org_id=org_id,
        campaign_id=str(campaign.id),
    )
    if delivery_config.delivery_mode.value == "external_urls":
        try:
            validated_config = require_valid_external_delivery(delivery_config)
        except CampaignDestinationError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": f"Campaign delivery config is not ready for external Meta review: {exc}",
                    "delivery": campaign_delivery_snapshot(delivery_config),
                },
            ) from exc
        return campaign_delivery_destination_map(validated_config), delivery_config
    if not funnel_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Meta review for internal-funnel campaigns requires one explicit funnel.",
        )
    review_paths_by_funnel_id = _resolve_funnel_review_paths(
        org_id=org_id,
        product_id=str(campaign.product_id),
        funnel_ids={funnel_id},
        session=session,
    )
    return review_paths_by_funnel_id.get(funnel_id, {}), delivery_config


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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _campaign_delivery_repo(session: Session) -> CampaignDeliveryConfigsRepository:
    return CampaignDeliveryConfigsRepository(session)


def _get_campaign_or_404(*, session: Session, org_id: str, campaign_id: str):
    campaign = CampaignsRepository(session).get(org_id=org_id, campaign_id=campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


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
    try:
        asset_brief_types = normalize_required_asset_brief_types(
            payload.asset_brief_types,
            field_name="asset_brief_types",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
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
        asset_brief_types=asset_brief_types,
        goal_description=payload.goal_description,
        objective_type=payload.objective_type,
        numeric_target=payload.numeric_target,
        baseline=payload.baseline,
        timeframe_days=payload.timeframe_days,
        budget_min=payload.budget_min,
        budget_max=payload.budget_max,
    )
    _campaign_delivery_repo(session).create(
        org_id=auth.org_id,
        client_id=payload.client_id,
        campaign_id=str(campaign.id),
    )
    session.refresh(campaign)
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
    campaign = _get_campaign_or_404(session=session, org_id=auth.org_id, campaign_id=campaign_id)
    return jsonable_encoder(campaign)


@router.get("/{campaign_id}/delivery")
def get_campaign_delivery(
    campaign_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    campaign = _get_campaign_or_404(session=session, org_id=auth.org_id, campaign_id=campaign_id)
    config = _campaign_delivery_repo(session).get_by_campaign(org_id=auth.org_id, campaign_id=str(campaign.id))
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Campaign delivery config is missing. Run the delivery-config backfill or recreate the campaign.",
        )
    payload = campaign_delivery_response_payload(config)
    return CampaignDeliveryResponse.model_validate(payload).model_dump(mode="json")


@router.put("/{campaign_id}/delivery")
def upsert_campaign_delivery(
    campaign_id: str,
    payload: CampaignDeliveryUpsertRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    campaign = _get_campaign_or_404(session=session, org_id=auth.org_id, campaign_id=campaign_id)
    repo = _campaign_delivery_repo(session)
    config = repo.get_by_campaign(org_id=auth.org_id, campaign_id=str(campaign.id))
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Campaign delivery config is missing. Run the delivery-config backfill or recreate the campaign.",
        )
    try:
        normalized = normalize_delivery_payload(
            delivery_mode=payload.deliveryMode,
            pre_sales_url=payload.preSalesUrl,
            sales_url=payload.salesUrl,
            checkout_url=payload.checkoutUrl,
            thank_you_url=payload.thankYouUrl,
        )
    except CampaignDeliveryConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if normalized.delivery_mode.value == "external_urls":
        _require_campaign_creative_context_ready(
            session=session,
            org_id=auth.org_id,
            campaign_id=str(campaign.id),
        )

    fields = apply_normalized_delivery_update(config=config, normalized=normalized)
    fields["updated_at"] = _utcnow()
    config = repo.update(config, **fields)
    response_payload = campaign_delivery_response_payload(config)
    return CampaignDeliveryResponse.model_validate(response_payload).model_dump(mode="json")


@router.post("/{campaign_id}/delivery/validate")
def validate_campaign_delivery(
    campaign_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    campaign = _get_campaign_or_404(session=session, org_id=auth.org_id, campaign_id=campaign_id)
    repo = _campaign_delivery_repo(session)
    config = repo.get_by_campaign(org_id=auth.org_id, campaign_id=str(campaign.id))
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Campaign delivery config is missing. Run the delivery-config backfill or recreate the campaign.",
        )
    try:
        results = validate_campaign_delivery_config(config)
    except CampaignDeliveryConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except CampaignDeliveryValidationError as exc:
        config = repo.update(
            config,
            validation_status=CampaignDeliveryValidationStatusEnum.invalid,
            validation_error=str(exc),
            validated_at=_utcnow(),
            updated_at=_utcnow(),
        )
        response_payload = validation_response_payload(
            config=config,
            validation_status=config.validation_status,
            validation_error=config.validation_error,
            results=exc.results,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=CampaignDeliveryValidationResponse.model_validate(response_payload).model_dump(mode="json"),
        ) from exc

    config = repo.update(
        config,
        validation_status=CampaignDeliveryValidationStatusEnum.valid,
        validation_error=None,
        validated_at=_utcnow(),
        updated_at=_utcnow(),
    )
    response_payload = validation_response_payload(
        config=config,
        validation_status=config.validation_status,
        validation_error=config.validation_error,
        results=results,
    )
    return CampaignDeliveryValidationResponse.model_validate(response_payload).model_dump(mode="json")


@router.get("/{campaign_id}/launch-context-readiness")
def get_campaign_launch_context_readiness(
    campaign_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    campaign = _get_campaign_or_404(session=session, org_id=auth.org_id, campaign_id=campaign_id)
    payload = ensure_campaign_creative_context_ready(
        session=session,
        org_id=auth.org_id,
        campaign=campaign,
    )
    return CampaignCreativeContextReadinessResponse.model_validate(payload).model_dump(mode="json")


@router.put("/{campaign_id}/creative-context/provider")
def update_campaign_creative_context_provider(
    campaign_id: str,
    payload: CampaignCreativeContextProviderRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    campaign = _get_campaign_or_404(session=session, org_id=auth.org_id, campaign_id=campaign_id)
    artifact = set_campaign_creative_context_provider(
        session=session,
        org_id=auth.org_id,
        campaign=campaign,
        provider=payload.provider,
        created_by_user=auth.user_id,
    )
    return CampaignCreativeContextProviderResponse.model_validate(
        {
            "campaignId": str(campaign.id),
            "provider": payload.provider.value,
            "creativeContextArtifactId": str(artifact.id),
            "checkedAt": artifact.created_at.isoformat() if artifact.created_at else _utcnow().isoformat(),
        }
    ).model_dump(mode="json")


@router.post("/{campaign_id}/creative-context/loaded", status_code=status.HTTP_201_CREATED)
def upsert_campaign_manual_creative_context(
    campaign_id: str,
    payload: CampaignManualCreativeContextUpsertRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    campaign = _get_campaign_or_404(session=session, org_id=auth.org_id, campaign_id=campaign_id)
    if not campaign.product_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Campaign is missing a product_id. Attach a product before loading manual creative context.",
        )
    response_payload = persist_manual_campaign_creative_context(
        session=session,
        org_id=auth.org_id,
        campaign=campaign,
        payload=payload,
        created_by_user=auth.user_id,
    )
    return CampaignManualCreativeContextUpsertResponse.model_validate(response_payload).model_dump(mode="json")


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
    _require_campaign_creative_context_ready(
        session=session,
        org_id=auth.org_id,
        campaign_id=str(campaign.id),
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
    _require_campaign_creative_context_ready(
        session=session,
        org_id=auth.org_id,
        campaign_id=str(campaign.id),
    )
    delivery_config = _campaign_delivery_config_or_404(
        session=session,
        org_id=auth.org_id,
        campaign_id=str(campaign.id),
    )
    if delivery_config.delivery_mode.value == "external_urls":
        try:
            require_valid_external_delivery(delivery_config)
        except CampaignDestinationError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": f"Campaign delivery config is not ready for external creative production: {exc}",
                    "delivery": campaign_delivery_snapshot(delivery_config),
                },
            ) from exc

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
    try:
        meta_workspace_context = resolve_workspace_config(
            session=session,
            org_id=auth.org_id,
            client_id=str(campaign.client_id),
        )
    except MetaWorkspaceConfigError:
        meta_workspace_context = None
    default_meta_page_id = (
        getattr(meta_workspace_context.workspace_config, "page_id", None)
        if meta_workspace_context is not None
        else None
    )
    default_instagram_actor_id = (
        getattr(meta_workspace_context.workspace_config, "instagram_actor_id", None)
        if meta_workspace_context is not None
        else None
    )

    brief_map = load_campaign_asset_brief_map(
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
    selected_generation_batch_id = payload.generationBatchId
    missing_brief_ids = [brief_id for brief_id in selected_brief_ids if brief_id not in brief_map]
    if missing_brief_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "Some asset briefs were not found for this campaign.",
                "missingAssetBriefIds": missing_brief_ids,
            },
        )
    _require_campaign_creative_context_ready(
        session=session,
        org_id=auth.org_id,
        campaign_id=str(campaign.id),
    )
    delivery_config = _campaign_delivery_config_or_404(
        session=session,
        org_id=auth.org_id,
        campaign_id=str(campaign.id),
    )
    is_external_delivery = delivery_config.delivery_mode.value == "external_urls"
    if is_external_delivery:
        try:
            require_valid_external_delivery(delivery_config)
        except CampaignDestinationError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": f"Campaign delivery config is not ready for external Meta review: {exc}",
                    "delivery": campaign_delivery_snapshot(delivery_config),
                },
            ) from exc
    requested_funnel_id = brief_funnel_id({"funnelId": payload.funnelId}) if payload.funnelId else None
    selected_brief_funnel_ids = collect_brief_funnel_ids(brief_map=brief_map, brief_ids=selected_brief_ids)
    if is_external_delivery:
        if selected_brief_funnel_ids:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "External-delivery Meta review does not accept funnel-scoped briefs in the selected set.",
                    "selectedAssetBriefIds": selected_brief_ids,
                    "availableFunnelIds": sorted(selected_brief_funnel_ids),
                },
            )
        requested_funnel_id = None
    else:
        if not requested_funnel_id:
            if not selected_brief_funnel_ids:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "message": "Selected asset briefs are missing funnel scope. Meta review must run for one explicit funnel.",
                        "selectedAssetBriefIds": selected_brief_ids,
                    },
                )
            if len(selected_brief_funnel_ids) > 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "message": "Selected asset briefs span multiple funnels. Pick one funnel in the Meta ads tab before preparing review.",
                        "selectedAssetBriefIds": selected_brief_ids,
                        "availableFunnelIds": sorted(selected_brief_funnel_ids),
                    },
                )
            requested_funnel_id = next(iter(selected_brief_funnel_ids))
        missing_funnel_brief_ids = [
            brief_id for brief_id in selected_brief_ids if not brief_funnel_id(brief_map.get(brief_id))
        ]
        if missing_funnel_brief_ids:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Some selected asset briefs are missing funnelId. Meta review must run for one explicit funnel.",
                    "invalidAssetBriefIds": missing_funnel_brief_ids,
                },
            )
        mismatched_funnel_brief_ids = [
            brief_id
            for brief_id in selected_brief_ids
            if brief_funnel_id(brief_map.get(brief_id)) != requested_funnel_id
        ]
        if mismatched_funnel_brief_ids:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Some selected asset briefs do not belong to the requested funnel.",
                    "requestedFunnelId": requested_funnel_id,
                    "invalidAssetBriefIds": mismatched_funnel_brief_ids,
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

    for brief_id, assets in assets_by_brief_id.items():
        assets_by_brief_id[brief_id] = _select_assets_for_meta_review(
            assets,
            generation_batch_id=selected_generation_batch_id,
        )

    missing_asset_briefs = [brief_id for brief_id, assets in assets_by_brief_id.items() if not assets]
    if missing_asset_briefs:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "No generated campaign assets exist for some selected briefs. Run creative generation first.",
                "missingAssetBriefIds": missing_asset_briefs,
            },
        )

    review_paths, resolved_delivery_config = _resolve_meta_review_paths_for_campaign(
        campaign=campaign,
        session=session,
        org_id=auth.org_id,
        funnel_id=requested_funnel_id,
    )
    if not review_paths:
        if requested_funnel_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "The selected funnel has no review pages configured for Meta review.",
                    "funnelId": requested_funnel_id,
                },
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Campaign delivery config did not resolve any destination URLs for Meta review.",
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
    updated_creative_spec_ids: list[str] = []
    reused_creative_spec_ids: list[str] = []
    created_adset_spec_ids: list[str] = []
    reused_adset_spec_ids: list[str] = []
    prepared_creative_specs: list[dict[str, object]] = []
    invalid_assets: list[dict[str, object]] = []
    experiment_config_by_id: dict[str, dict[str, object]] = {}

    for brief_id in selected_brief_ids:
        brief = brief_map[brief_id]
        experiment_id = brief.get("experimentId")
        if not isinstance(experiment_id, str) or not experiment_id.strip():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Asset brief '{brief_id}' is missing experimentId.",
            )
        experiment_id = experiment_id.strip()
        if experiment_id not in experiment_config_by_id:
            experiment_config_by_id[experiment_id] = {
                "name": brief.get("variantName") or brief.get("creativeConcept") or experiment_id,
                "metadata_json": {
                    "source": "campaign_meta_review_setup",
                    "experimentSpecId": experiment_id,
                    "campaignGoalDescription": campaign.goal_description,
                    "campaignChannels": campaign.channels or [],
                    "variantId": brief.get("variantId"),
                    "variantName": brief.get("variantName"),
                    "assetBriefIds": [
                        candidate
                        for candidate in selected_brief_ids
                        if brief_map[candidate].get("experimentId") == experiment_id
                    ],
                },
            }

        requirements = brief.get("requirements") or []
        if not isinstance(requirements, list) or not requirements:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Asset brief '{brief_id}' has no requirements.",
            )

        for asset in assets_by_brief_id[brief_id]:
            metadata = asset.ai_metadata if isinstance(asset.ai_metadata, dict) else {}
            existing_creative = existing_creative_specs.get(str(asset.id))
            if existing_creative is None:
                existing_creative = meta_repo.get_creative_spec_by_asset(
                    org_id=auth.org_id,
                    asset_id=str(asset.id),
                )
                if existing_creative is not None:
                    existing_creative_specs[str(asset.id)] = existing_creative
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
            swipe_copy_pack_payload = metadata.get("swipeCopyPack")
            if not isinstance(swipe_copy_pack_payload, dict):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Generated asset '{asset.id}' is missing ai_metadata.swipeCopyPack.",
                )
            try:
                swipe_copy_pack = SwipeAdCopyPack.model_validate(swipe_copy_pack_payload)
            except ValidationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Generated asset '{asset.id}' has an invalid ai_metadata.swipeCopyPack: {exc}",
                ) from exc
            if swipe_copy_pack.platform.strip().lower() != "meta":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Generated asset '{asset.id}' swipeCopyPack.platform must be 'Meta' for Meta review.",
                )

            swipe_copy_inputs_payload = metadata.get("swipeCopyInputs")
            if not isinstance(swipe_copy_inputs_payload, dict):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Generated asset '{asset.id}' is missing ai_metadata.swipeCopyInputs.",
                )
            try:
                swipe_copy_inputs = SwipeCopyInputs.model_validate(swipe_copy_inputs_payload)
            except ValidationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Generated asset '{asset.id}' has an invalid ai_metadata.swipeCopyInputs: {exc}",
                )
            if swipe_copy_inputs.ad_image_or_video.source_kind != "rendered_output":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Generated asset '{asset.id}' swipeCopyInputs.adImageOrVideo.sourceKind must be "
                        "'rendered_output' for Meta review."
                    ),
                )
            rendered_copy_image_label = (
                swipe_copy_inputs.ad_image_or_video.source_label.strip()
                if isinstance(swipe_copy_inputs.ad_image_or_video.source_label, str)
                and swipe_copy_inputs.ad_image_or_video.source_label.strip()
                else None
            )
            rendered_copy_image_url = swipe_copy_inputs.ad_image_or_video.source_url.strip()
            swipe_source_label = (
                swipe_copy_inputs.source_swipe.source_label.strip()
                if swipe_copy_inputs.source_swipe
                and isinstance(swipe_copy_inputs.source_swipe.source_label, str)
                and swipe_copy_inputs.source_swipe.source_label.strip()
                else None
            )
            swipe_source_media_url = (
                swipe_copy_inputs.source_swipe.source_url.strip()
                if swipe_copy_inputs.source_swipe
                and isinstance(swipe_copy_inputs.source_swipe.source_url, str)
                and swipe_copy_inputs.source_swipe.source_url.strip()
                else None
            )
            angle_used = swipe_copy_inputs.angle_used
            destination_page = swipe_copy_inputs.destination_page
            normalized_destination_page = normalize_meta_review_destination_page(
                destination_page,
                review_paths=review_paths,
            ) or destination_page.strip()
            destination_type = requirement_destination_type(brief=brief, requirement=requirement)
            generation_batch_id = metadata.get("creativeGenerationBatchId")
            if isinstance(generation_batch_id, str):
                generation_batch_id = generation_batch_id.strip() or None
            else:
                generation_batch_id = None
            creative_spec_name = " · ".join(
                [
                    str(campaign.name).strip(),
                    str(brief.get("variantName") or experiment_id).strip(),
                    str(requirement.get("funnelStage") or requirement.get("channel") or "creative").strip(),
                ]
            )
            desired_metadata_json = {
                "source": "campaign_meta_review_setup_swipe_copy",
                "experimentSpecId": experiment_id,
                "experimentName": brief.get("variantName") or experiment_id,
                "assetBriefId": brief_id,
                "generationBatchId": generation_batch_id,
                "swipeSourceLabel": swipe_source_label,
                "swipeSourceMediaUrl": swipe_source_media_url,
                "swipeCopyImageLabel": rendered_copy_image_label,
                "swipeCopyImageUrl": rendered_copy_image_url,
                "requirementIndex": requirement_index,
                "requirement": requirement,
                "swipeCopyPack": swipe_copy_pack.model_dump(mode="json", by_alias=True),
                "swipeCopyInputs": jsonable_encoder(swipe_copy_inputs.model_dump(mode="json", by_alias=True)),
                "swipeCopyModel": metadata.get("swipeCopyModel"),
                "swipeCopyRequestId": metadata.get("swipeCopyRequestId"),
                "swipeCopyStopReason": metadata.get("swipeCopyStopReason"),
                "swipeCopyOutputTokens": metadata.get("swipeCopyOutputTokens"),
                "reviewPaths": review_paths,
                "variantId": brief.get("variantId"),
                "variantName": brief.get("variantName"),
                "funnelId": requested_funnel_id,
                "deliveryMode": resolved_delivery_config.delivery_mode.value,
                "campaignDeliveryConfigId": str(resolved_delivery_config.id),
                "campaignDelivery": campaign_delivery_snapshot(resolved_delivery_config),
                "destinationSource": "campaign_delivery_config" if is_external_delivery else "review_path",
                "resolvedDestinationUrl": _resolve_meta_review_destination_url(
                    destination_page=normalized_destination_page,
                    review_paths=review_paths,
                ),
                "destinationType": destination_type,
                "destinationPage": normalized_destination_page,
                "angleUsed": angle_used.strip(),
            }
            desired_creative_spec_fields = {
                "campaign_id": str(campaign.id),
                "name": creative_spec_name,
                "primary_text": swipe_copy_pack.meta_primary_text,
                "headline": swipe_copy_pack.meta_headline,
                "description": swipe_copy_pack.meta_description,
                "call_to_action_type": swipe_copy_pack.meta_cta,
                "destination_url": desired_metadata_json["resolvedDestinationUrl"],
                "page_id": default_meta_page_id,
                "instagram_actor_id": default_instagram_actor_id,
                "status": "draft",
                "metadata_json": desired_metadata_json,
            }
            spec_copy_issues = list_meta_copy_policy_issues(
                {
                    "primary_text": desired_creative_spec_fields["primary_text"],
                    "headline": desired_creative_spec_fields["headline"],
                    "description": desired_creative_spec_fields["description"],
                }
            )
            destination_url = desired_creative_spec_fields["destination_url"]
            asset_issues: list[dict[str, str]] = []
            if not destination_url:
                asset_issues.append(
                    {
                        "ruleId": "META-LP-001",
                        "title": "Destination URL missing",
                        "message": "The destination page could not be resolved to a funnel review path for this asset.",
                    }
                )
            asset_issues.extend(spec_copy_issues)
            if asset_issues:
                invalid_assets.append(
                    {
                        "assetId": str(asset.id),
                        "assetBriefId": brief_id,
                        "generationKey": asset_generation_key(asset),
                        "funnelId": requested_funnel_id,
                        "destinationPage": destination_page.strip(),
                        "normalizedDestinationPage": normalized_destination_page,
                        "issues": asset_issues,
                    }
                )
                continue

            prepared_creative_specs.append(
                {
                    "asset_id": str(asset.id),
                    "existing_creative": existing_creative,
                    "desired_fields": desired_creative_spec_fields,
                }
            )

    if invalid_assets:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Some generated assets cannot be prepared for Meta review until destination mapping or copy issues are fixed.",
                "invalidAssets": invalid_assets,
            },
        )

    for experiment_id in [brief_map[brief_id]["experimentId"].strip() for brief_id in selected_brief_ids]:
        adset_spec = existing_adset_specs_by_experiment.get(experiment_id)
        if adset_spec is None:
            experiment_config = experiment_config_by_id[experiment_id]
            new_adset_spec = meta_repo.create_adset_spec(
                org_id=auth.org_id,
                campaign_id=str(campaign.id),
                name=str(experiment_config["name"]),
                status="draft",
                metadata_json=experiment_config["metadata_json"],
            )
            existing_adset_specs_by_experiment[experiment_id] = new_adset_spec
            created_adset_spec_ids.append(str(new_adset_spec.id))
        else:
            reused_adset_spec_ids.append(str(adset_spec.id))

    for prepared_creative in prepared_creative_specs:
        asset_id = str(prepared_creative["asset_id"])
        existing_creative = prepared_creative["existing_creative"]
        desired_creative_spec_fields = prepared_creative["desired_fields"]

        if existing_creative is None:
            new_creative_spec = meta_repo.create_creative_spec(
                org_id=auth.org_id,
                asset_id=asset_id,
                **desired_creative_spec_fields,
            )
            created_creative_spec_ids.append(str(new_creative_spec.id))
            existing_creative_specs[asset_id] = new_creative_spec
            continue

        requires_update = any(
            (
                getattr(existing_creative, field_name) != expected_value
                for field_name, expected_value in desired_creative_spec_fields.items()
            )
        )
        if requires_update:
            updated_creative_spec = meta_repo.update_creative_spec(existing_creative, **desired_creative_spec_fields)
            updated_creative_spec_ids.append(str(updated_creative_spec.id))
            existing_creative_specs[asset_id] = updated_creative_spec
        else:
            reused_creative_spec_ids.append(str(existing_creative.id))

    return {
        "campaignId": str(campaign.id),
        "assetBriefIds": selected_brief_ids,
        "assetCount": sum(len(items) for items in assets_by_brief_id.values()),
        "createdCreativeSpecIds": created_creative_spec_ids,
        "updatedCreativeSpecIds": updated_creative_spec_ids,
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
