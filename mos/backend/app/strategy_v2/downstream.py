from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.enums import ArtifactTypeEnum
from app.db.repositories.artifacts import ArtifactsRepository
from app.strategy_v2.feature_flags import is_strategy_v2_enabled


def _artifact_payload(artifact: Any) -> dict[str, Any] | None:
    if artifact is None:
        return None
    payload = getattr(artifact, "data", None)
    if not isinstance(payload, dict):
        return None
    return payload


def normalize_strategy_v2_copy_payload(copy_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(copy_payload, dict):
        return None
    approved = copy_payload.get("approved_copy")
    if isinstance(approved, dict):
        return approved
    return copy_payload


def build_strategy_v2_downstream_packet(
    *,
    stage3: dict[str, Any] | None,
    offer: dict[str, Any] | None,
    copy: dict[str, Any] | None,
    copy_context: dict[str, Any] | None,
    awareness_angle_matrix: dict[str, Any] | None,
    artifact_ids: dict[str, str | None],
) -> dict[str, Any] | None:
    if not isinstance(stage3, dict) or not isinstance(offer, dict) or not isinstance(copy, dict):
        return None
    if not isinstance(copy_context, dict):
        return None

    selected_angle = stage3.get("selected_angle") if isinstance(stage3.get("selected_angle"), dict) else {}
    offer_decision = offer.get("decision") if isinstance(offer.get("decision"), dict) else {}
    copy_decision = None
    if isinstance(copy.get("decision"), dict):
        copy_decision = copy.get("decision")

    return {
        "selected_angle": {
            "angle_id": selected_angle.get("angle_id"),
            "angle_name": selected_angle.get("angle_name"),
            "evidence": selected_angle.get("evidence"),
        },
        "offer": {
            "ump": stage3.get("ump"),
            "ums": stage3.get("ums"),
            "core_promise": stage3.get("core_promise"),
            "value_stack_summary": stage3.get("value_stack_summary"),
            "guarantee_type": stage3.get("guarantee_type"),
            "pricing_rationale": stage3.get("pricing_rationale"),
            "variant_selected": stage3.get("variant_selected"),
            "composite_score": stage3.get("composite_score"),
        },
        "copy": {
            "headline": copy.get("headline"),
            "promise_contract": copy.get("promise_contract"),
            "presell_markdown": copy.get("presell_markdown"),
            "sales_page_markdown": copy.get("sales_page_markdown"),
            "quality_gate_report": copy.get("quality_gate_report"),
            "semantic_gates": copy.get("semantic_gates"),
            "congruency": copy.get("congruency"),
        },
        "copy_context": copy_context,
        "awareness_angle_matrix": awareness_angle_matrix,
        "decision_metadata": {
            "offer_winner": offer_decision,
            "final_copy_approval": copy_decision,
        },
        "provenance": {
            "stage3_artifact_id": artifact_ids.get("stage3"),
            "offer_artifact_id": artifact_ids.get("offer"),
            "copy_artifact_id": artifact_ids.get("copy"),
            "copy_context_artifact_id": artifact_ids.get("copy_context"),
            "awareness_matrix_artifact_id": artifact_ids.get("awareness_angle_matrix"),
        },
    }


def load_strategy_v2_outputs(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    product_id: str,
) -> dict[str, Any]:
    artifacts_repo = ArtifactsRepository(session)
    stage3_artifact = artifacts_repo.get_latest_by_type(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        artifact_type=ArtifactTypeEnum.strategy_v2_stage3,
    )
    offer_artifact = artifacts_repo.get_latest_by_type(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        artifact_type=ArtifactTypeEnum.strategy_v2_offer,
    )
    copy_artifact = artifacts_repo.get_latest_by_type(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        artifact_type=ArtifactTypeEnum.strategy_v2_copy,
    )
    copy_context_artifact = artifacts_repo.get_latest_by_type(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        artifact_type=ArtifactTypeEnum.strategy_v2_copy_context,
    )
    awareness_matrix_artifact = artifacts_repo.get_latest_by_type(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        artifact_type=ArtifactTypeEnum.strategy_v2_awareness_angle_matrix,
    )

    stage3 = _artifact_payload(stage3_artifact)
    offer = _artifact_payload(offer_artifact)
    copy_raw = _artifact_payload(copy_artifact)
    copy = normalize_strategy_v2_copy_payload(copy_raw)
    copy_context = _artifact_payload(copy_context_artifact)
    awareness_angle_matrix = _artifact_payload(awareness_matrix_artifact)

    artifact_ids = {
        "stage3": str(getattr(stage3_artifact, "id", "")) if stage3_artifact is not None else None,
        "offer": str(getattr(offer_artifact, "id", "")) if offer_artifact is not None else None,
        "copy": str(getattr(copy_artifact, "id", "")) if copy_artifact is not None else None,
        "copy_context": str(getattr(copy_context_artifact, "id", "")) if copy_context_artifact is not None else None,
        "awareness_angle_matrix": str(getattr(awareness_matrix_artifact, "id", ""))
        if awareness_matrix_artifact is not None
        else None,
    }

    downstream_packet = build_strategy_v2_downstream_packet(
        stage3=stage3,
        offer=offer,
        copy=copy,
        copy_context=copy_context,
        awareness_angle_matrix=awareness_angle_matrix,
        artifact_ids=artifact_ids,
    )

    return {
        "stage3_artifact": stage3_artifact,
        "offer_artifact": offer_artifact,
        "copy_artifact": copy_artifact,
        "copy_context_artifact": copy_context_artifact,
        "awareness_angle_matrix_artifact": awareness_matrix_artifact,
        "stage3": stage3,
        "offer": offer,
        "copy_raw": copy_raw,
        "copy": copy,
        "copy_context": copy_context,
        "awareness_angle_matrix": awareness_angle_matrix,
        "artifact_ids": artifact_ids,
        "downstream_packet": downstream_packet,
    }


def require_strategy_v2_outputs_if_enabled(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    product_id: str,
) -> dict[str, Any]:
    outputs = load_strategy_v2_outputs(
        session=session,
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
    )
    required = is_strategy_v2_enabled(session=session, org_id=org_id, client_id=client_id)
    if not required:
        return outputs

    missing: list[str] = []
    if outputs["stage3"] is None:
        missing.append(ArtifactTypeEnum.strategy_v2_stage3.value)
    if outputs["offer"] is None:
        missing.append(ArtifactTypeEnum.strategy_v2_offer.value)
    if outputs["copy"] is None:
        missing.append(ArtifactTypeEnum.strategy_v2_copy.value)
    if outputs["copy_context"] is None:
        missing.append(ArtifactTypeEnum.strategy_v2_copy_context.value)
    if missing:
        raise RuntimeError(
            "Strategy V2 output missing for required tenant. "
            f"Missing artifacts: {', '.join(missing)}. "
            "Run Strategy V2 to completion before starting campaign workflows."
        )
    return outputs
