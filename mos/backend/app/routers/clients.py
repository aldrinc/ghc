from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.config import settings
from app.db.deps import get_session
from app.db.repositories.clients import ClientsRepository
from app.db.repositories.design_systems import DesignSystemsRepository
from app.db.repositories.products import ProductsRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.enums import ArtifactTypeEnum
from app.db.repositories.onboarding_payloads import OnboardingPayloadsRepository
from app.schemas.common import ClientCreate
from app.schemas.clients import ClientDeleteRequest, ClientUpdateRequest
from app.schemas.onboarding import OnboardingStartRequest
from app.schemas.intent import CampaignIntentRequest
from app.temporal.client import get_temporal_client
from app.temporal.workflows.client_onboarding import ClientOnboardingInput, ClientOnboardingWorkflow
from app.temporal.workflows.campaign_intent import CampaignIntentInput, CampaignIntentWorkflow

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get("")
def list_clients(
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list:
    repo = ClientsRepository(session)
    return jsonable_encoder(repo.list(org_id=auth.org_id))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_client(
    payload: ClientCreate,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = ClientsRepository(session)
    client = repo.create(org_id=auth.org_id, name=payload.name, industry=payload.industry)
    return jsonable_encoder(client)


@router.get("/{client_id}")
def get_client(
    client_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = ClientsRepository(session)
    client = repo.get(org_id=auth.org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return jsonable_encoder(client)


@router.patch("/{client_id}")
def update_client(
    client_id: str,
    payload: ClientUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = ClientsRepository(session)
    client = repo.get(org_id=auth.org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    fields: dict[str, object] = {}
    if payload.name is not None:
        fields["name"] = payload.name
    if payload.industry is not None:
        fields["industry"] = payload.industry
    if "designSystemId" in payload.model_fields_set:
        design_system_id = payload.designSystemId or None
        if design_system_id:
            design_system_repo = DesignSystemsRepository(session)
            design_system = design_system_repo.get(org_id=auth.org_id, design_system_id=design_system_id)
            if not design_system:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Design system not found")
            if design_system.client_id and str(design_system.client_id) != str(client_id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Design system must belong to the same client",
                )
        fields["design_system_id"] = design_system_id

    updated = repo.update(org_id=auth.org_id, client_id=client_id, **fields)
    return jsonable_encoder(updated)


@router.delete("/{client_id}")
def delete_client(
    client_id: str,
    payload: ClientDeleteRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = ClientsRepository(session)
    client = repo.get(org_id=auth.org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    if not payload.confirm:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Deletion not confirmed")

    if payload.confirm_name != client.name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation name does not match workspace name",
        )

    deleted = repo.delete(org_id=auth.org_id, client_id=client_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete client")

    return {"ok": True}


@router.post("/{client_id}/onboarding")
async def start_client_onboarding(
    client_id: str,
    payload: OnboardingStartRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if payload.business_type != "new":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Existing customer onboarding is not supported yet.",
        )
    onboarding_repo = OnboardingPayloadsRepository(session)
    clients_repo = ClientsRepository(session)
    products_repo = ProductsRepository(session)

    client = clients_repo.get(org_id=auth.org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    product_fields: dict[str, object] = {"name": payload.product_name}
    if payload.product_description is not None:
        product_fields["description"] = payload.product_description
    if payload.product_category is not None:
        product_fields["category"] = payload.product_category
    if payload.primary_benefits is not None:
        product_fields["primary_benefits"] = payload.primary_benefits
    if payload.feature_bullets is not None:
        product_fields["feature_bullets"] = payload.feature_bullets
    if payload.guarantee_text is not None:
        product_fields["guarantee_text"] = payload.guarantee_text
    if payload.disclaimers is not None:
        product_fields["disclaimers"] = payload.disclaimers

    product = products_repo.create(
        org_id=auth.org_id,
        client_id=client_id,
        **product_fields,
    )

    payload_data = payload.model_dump()
    payload_data["product_id"] = str(product.id)

    onboarding_payload = onboarding_repo.create(
        org_id=auth.org_id,
        client_id=client_id,
        product_id=str(product.id),
        data=payload_data,
    )

    temporal = await get_temporal_client()
    handle = await temporal.start_workflow(
        ClientOnboardingWorkflow.run,
        ClientOnboardingInput(
            org_id=auth.org_id,
            client_id=client_id,
            onboarding_payload_id=str(onboarding_payload.id),
            product_id=str(product.id),
        ),
        id=f"client-onboarding-{auth.org_id}-{client_id}-{onboarding_payload.id}",
        task_queue=settings.TEMPORAL_TASK_QUEUE,
    )

    workflows_repo = WorkflowsRepository(session)
    run = workflows_repo.create_run(
        org_id=auth.org_id,
        client_id=client_id,
        product_id=str(product.id),
        campaign_id=None,
        temporal_workflow_id=handle.id,
        temporal_run_id=handle.first_execution_run_id,
        kind="client_onboarding",
    )
    workflows_repo.log_activity(
        workflow_run_id=str(run.id),
        step="client_onboarding",
        status="started",
        payload_in={
            "client_id": client_id,
            "product_id": str(product.id),
            "onboarding_payload_id": str(onboarding_payload.id),
        },
    )

    return {
        "workflow_run_id": str(run.id),
        "temporal_workflow_id": handle.id,
        "product_id": str(product.id),
        "product_name": product.name,
    }


@router.post("/{client_id}/intent")
async def start_campaign_intent(
    client_id: str,
    payload: CampaignIntentRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    clients_repo = ClientsRepository(session)
    client = clients_repo.get(org_id=auth.org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    product_id = payload.productId
    products_repo = ProductsRepository(session)
    product = products_repo.get(org_id=auth.org_id, product_id=product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if str(product.client_id) != client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="productId does not belong to the selected workspace.",
        )
    if not payload.channels or not all(isinstance(ch, str) and ch.strip() for ch in payload.channels):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="channels must include at least one non-empty value.",
        )
    if not payload.assetBriefTypes or not all(
        isinstance(t, str) and t.strip() for t in payload.assetBriefTypes
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="assetBriefTypes must include at least one non-empty value.",
        )

    artifacts_repo = ArtifactsRepository(session)
    canon = artifacts_repo.get_latest_by_type(
        org_id=auth.org_id,
        client_id=client_id,
        product_id=product_id,
        artifact_type=ArtifactTypeEnum.client_canon,
    )
    metric = artifacts_repo.get_latest_by_type(
        org_id=auth.org_id,
        client_id=client_id,
        product_id=product_id,
        artifact_type=ArtifactTypeEnum.metric_schema,
    )
    wf_repo = WorkflowsRepository(session)
    approvals_ok = wf_repo.has_onboarding_approvals(
        org_id=auth.org_id, client_id=client_id, product_id=product_id
    )
    if (not canon or not metric) and not approvals_ok:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete client onboarding (canon + metric schema) before starting campaign intent.",
        )

    temporal = await get_temporal_client()
    handle = await temporal.start_workflow(
        CampaignIntentWorkflow.run,
        CampaignIntentInput(
            org_id=auth.org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_name=payload.campaignName,
            channels=payload.channels,
            asset_brief_types=payload.assetBriefTypes,
            goal_description=payload.goalDescription,
            objective_type=payload.objectiveType,
            numeric_target=payload.numericTarget,
            baseline=payload.baseline,
            timeframe_days=payload.timeframeDays,
            budget_min=payload.budgetMin,
            budget_max=payload.budgetMax,
        ),
        id=f"campaign-intent-{auth.org_id}-{client_id}-{uuid4()}",
        task_queue=settings.TEMPORAL_TASK_QUEUE,
    )

    run = wf_repo.create_run(
        org_id=auth.org_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=None,
        temporal_workflow_id=handle.id,
        temporal_run_id=handle.first_execution_run_id,
        kind="campaign_intent",
    )
    wf_repo.log_activity(
        workflow_run_id=str(run.id),
        step="campaign_intent",
        status="started",
        payload_in={"client_id": client_id, "product_id": product_id, "campaign_name": payload.campaignName},
    )

    return {"workflow_run_id": str(run.id), "temporal_workflow_id": handle.id}
