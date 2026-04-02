from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.repositories.products import ProductsRepository
from app.schemas.product_strategy_skills import (
    StrategySkillsActivationRequest,
    StrategySkillsActivationResponse,
    StrategySkillsApprovalRequest,
    StrategySkillsApprovalResponse,
    StrategySkillsBootstrapRequest,
    StrategySkillsBootstrapResponse,
    StrategySkillsFoundationalApprovalRequest,
    StrategySkillsFoundationalApprovalResponse,
    StrategySkillsSelectionRequest,
    StrategySkillsSelectionResponse,
    StrategySkillsStageRunRequest,
    StrategySkillsStageRunResponse,
    StrategySkillsStatusResponse,
)
from app.services.ember_skills_flow import EmberSkillsFlowError, EmberSkillsFlowService
from app.services.product_strategy_bundles import (
    FOUNDATIONAL_BUNDLE_TYPE,
    ProductStrategyBundlesError,
    ProductStrategyBundlesService,
    SKILLS_HANDOFF_BUNDLE_TYPE,
    SKILLS_WORKING_BUNDLE_TYPE,
)
from app.services.skills_runtime_registry import (
    DEFAULT_SKILL_BUNDLE_KEY,
    SkillsRuntimeRegistryError,
    SkillsRuntimeRegistryService,
)


router = APIRouter(prefix="/products/{product_id}/strategy-skills", tags=["product-strategy-skills"])


def _require_product(*, session: Session, org_id: str, product_id: str):
    product = ProductsRepository(session).get(org_id=org_id, product_id=product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    return product


def _runtime_service(*, session: Session, auth: AuthContext, product_id: str) -> SkillsRuntimeRegistryService:
    product = _require_product(session=session, org_id=auth.org_id, product_id=product_id)
    return SkillsRuntimeRegistryService(
        session=session,
        org_id=auth.org_id,
        client_id=str(product.client_id),
        product_id=str(product.id),
        created_by_user=auth.user_id,
    )


def _bundle_service(*, session: Session, auth: AuthContext, product_id: str) -> ProductStrategyBundlesService:
    product = _require_product(session=session, org_id=auth.org_id, product_id=product_id)
    return ProductStrategyBundlesService(
        session=session,
        org_id=auth.org_id,
        client_id=str(product.client_id),
        product_id=str(product.id),
        created_by_user=auth.user_id,
    )


def _flow_service(*, session: Session, auth: AuthContext, product_id: str) -> EmberSkillsFlowService:
    product = _require_product(session=session, org_id=auth.org_id, product_id=product_id)
    return EmberSkillsFlowService(
        session=session,
        org_id=auth.org_id,
        client_id=str(product.client_id),
        product_id=str(product.id),
        created_by_user=auth.user_id,
    )


@router.get("/status", response_model=StrategySkillsStatusResponse)
def get_strategy_skills_status(
    product_id: str,
    bundle_key: str = DEFAULT_SKILL_BUNDLE_KEY,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    product = _require_product(session=session, org_id=auth.org_id, product_id=product_id)
    runtime = _runtime_service(session=session, auth=auth, product_id=product_id)
    bundles = _bundle_service(session=session, auth=auth, product_id=product_id)

    try:
        foundational_bundle = bundles.get_active_bundle(bundle_type=FOUNDATIONAL_BUNDLE_TYPE)
    except ProductStrategyBundlesError:
        foundational_bundle = None
    try:
        working_bundle = bundles.get_active_bundle(bundle_type=SKILLS_WORKING_BUNDLE_TYPE)
    except ProductStrategyBundlesError:
        working_bundle = None
    try:
        handoff_bundle = bundles.get_active_bundle(bundle_type=SKILLS_HANDOFF_BUNDLE_TYPE)
    except ProductStrategyBundlesError:
        handoff_bundle = None
    handoff_bundles = bundles.list_bundles(bundle_type=SKILLS_HANDOFF_BUNDLE_TYPE)
    pending_handoff_bundles: list[dict[str, object]] = []
    historical_handoff_bundles: list[dict[str, object]] = []
    active_handoff_created_at = str(handoff_bundle.get("createdAt") or "").strip() if handoff_bundle else ""
    for bundle in handoff_bundles:
        if bool(bundle.get("isActive")):
            continue
        bundle_created_at = str(bundle.get("createdAt") or "").strip()
        if active_handoff_created_at and bundle_created_at > active_handoff_created_at:
            pending_handoff_bundles.append(bundle)
        else:
            historical_handoff_bundles.append(bundle)
    foundational_completeness = None
    if foundational_bundle is not None:
        foundational_metadata = foundational_bundle.get("metadata") or {}
        foundational_completeness = {
            "isComplete": bool(foundational_metadata.get("isComplete")),
            "expectedDocKeys": list(foundational_metadata.get("expectedDocKeys") or []),
            "presentDocKeys": list(foundational_metadata.get("presentDocKeys") or []),
            "missingDocKeys": list(foundational_metadata.get("missingDocKeys") or []),
        }

    return StrategySkillsStatusResponse.model_validate(
        {
            "clientId": str(product.client_id),
            "productId": str(product.id),
            "bundleKey": bundle_key,
            "skillsBinding": runtime.get_workspace_binding(bundle_key=bundle_key),
            "activeFoundationalBundle": foundational_bundle,
            "activeWorkingBundle": working_bundle,
            "activeHandoffBundle": handoff_bundle,
            "pendingHandoffBundles": pending_handoff_bundles,
            "historicalHandoffBundles": historical_handoff_bundles,
            "foundationalCompleteness": foundational_completeness,
        }
    ).model_dump(mode="json")


@router.post("/bootstrap", response_model=StrategySkillsBootstrapResponse, status_code=status.HTTP_201_CREATED)
def bootstrap_strategy_skills(
    product_id: str,
    payload: StrategySkillsBootstrapRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    product = _require_product(session=session, org_id=auth.org_id, product_id=product_id)
    runtime = _runtime_service(session=session, auth=auth, product_id=product_id)
    bundles = _bundle_service(session=session, auth=auth, product_id=product_id)
    flow = _flow_service(session=session, auth=auth, product_id=product_id)
    try:
        release = runtime.sync_ember_skills_release(
            strategy_root=Path(payload.strategyRoot),
            version=payload.releaseVersion,
            source_revision=payload.sourceRevision,
            source_ref=payload.sourceRef,
        )
        binding = runtime.ensure_workspace_binding(
            release_id=release["releaseId"],
            bundle_key=payload.bundleKey,
            bundle_family=payload.bundleFamily,
        )
        foundational = bundles.import_foundational_bundle(
            source_dir=Path(payload.foundationalRoot),
            title="EMBER Foundational Docs",
            doc_key_prefix="foundational",
        )
    except (SkillsRuntimeRegistryError, ProductStrategyBundlesError, EmberSkillsFlowError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return StrategySkillsBootstrapResponse.model_validate(
        {
            "clientId": str(product.client_id),
            "productId": str(product.id),
            "release": release,
            "binding": binding,
            "foundationalBundle": foundational,
        }
    ).model_dump(mode="json")


@router.post("/foundational/approve", response_model=StrategySkillsFoundationalApprovalResponse)
def approve_foundational_strategy_bundle(
    product_id: str,
    payload: StrategySkillsFoundationalApprovalRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    product = _require_product(session=session, org_id=auth.org_id, product_id=product_id)
    flow = _flow_service(session=session, auth=auth, product_id=product_id)
    try:
        result = flow.seed_working_bundle_from_foundation(allow_incomplete=payload.allowIncomplete)
    except (EmberSkillsFlowError, ProductStrategyBundlesError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return StrategySkillsFoundationalApprovalResponse.model_validate(
        {
            "clientId": str(product.client_id),
            "productId": str(product.id),
            "result": result,
        }
    ).model_dump(mode="json")


@router.post("/stages/{stage_key}", response_model=StrategySkillsStageRunResponse)
def run_strategy_stage(
    product_id: str,
    stage_key: str,
    payload: StrategySkillsStageRunRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    product = _require_product(session=session, org_id=auth.org_id, product_id=product_id)
    flow = _flow_service(session=session, auth=auth, product_id=product_id)
    try:
        result = flow.run_stage(
            stage_key=stage_key,
            bundle_key=payload.bundleKey,
            promote_to_active_bundle=payload.promoteToActiveBundle,
        )
    except (EmberSkillsFlowError, SkillsRuntimeRegistryError, ProductStrategyBundlesError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return StrategySkillsStageRunResponse.model_validate(
        {
            "clientId": str(product.client_id),
            "productId": str(product.id),
            "result": result,
        }
    ).model_dump(mode="json")


@router.post("/select-angle", response_model=StrategySkillsSelectionResponse)
def select_strategy_angle(
    product_id: str,
    payload: StrategySkillsSelectionRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    product = _require_product(session=session, org_id=auth.org_id, product_id=product_id)
    flow = _flow_service(session=session, auth=auth, product_id=product_id)
    try:
        result = flow.select_angle(angle_id=payload.selectedId, rationale=payload.rationale)
    except (EmberSkillsFlowError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return StrategySkillsSelectionResponse.model_validate(
        {
            "clientId": str(product.client_id),
            "productId": str(product.id),
            "result": result,
        }
    ).model_dump(mode="json")


@router.post("/approve-role", response_model=StrategySkillsApprovalResponse)
def approve_strategy_role(
    product_id: str,
    payload: StrategySkillsApprovalRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    product = _require_product(session=session, org_id=auth.org_id, product_id=product_id)
    flow = _flow_service(session=session, auth=auth, product_id=product_id)
    try:
        result = flow.approve_working_role(role=payload.role)
    except (EmberSkillsFlowError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return StrategySkillsApprovalResponse.model_validate(
        {
            "clientId": str(product.client_id),
            "productId": str(product.id),
            "result": result,
        }
    ).model_dump(mode="json")


@router.post("/handoff/activate", response_model=StrategySkillsActivationResponse)
def activate_strategy_handoff_bundle(
    product_id: str,
    payload: StrategySkillsActivationRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    product = _require_product(session=session, org_id=auth.org_id, product_id=product_id)
    flow = _flow_service(session=session, auth=auth, product_id=product_id)
    try:
        result = flow.activate_handoff_bundle(bundle_id=payload.bundleId)
    except (EmberSkillsFlowError, ProductStrategyBundlesError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return StrategySkillsActivationResponse.model_validate(
        {
            "clientId": str(product.client_id),
            "productId": str(product.id),
            "result": result,
        }
    ).model_dump(mode="json")


@router.post("/select-headline", response_model=StrategySkillsSelectionResponse)
def select_strategy_headline(
    product_id: str,
    payload: StrategySkillsSelectionRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    product = _require_product(session=session, org_id=auth.org_id, product_id=product_id)
    flow = _flow_service(session=session, auth=auth, product_id=product_id)
    try:
        result = flow.select_headline(headline_id=payload.selectedId, rationale=payload.rationale)
    except (EmberSkillsFlowError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return StrategySkillsSelectionResponse.model_validate(
        {
            "clientId": str(product.client_id),
            "productId": str(product.id),
            "result": result,
        }
    ).model_dump(mode="json")
