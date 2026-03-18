from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from sqlalchemy.orm import Session

from app.db.enums import ArtifactTypeEnum
from app.db.models import Campaign
from app.db.repositories.artifacts import ArtifactsRepository
from app.schemas.campaign_creative_context import (
    CampaignCreativeContextProviderEnum,
    CampaignManualCreativeContextUpsertRequest,
)
from app.schemas.experiment_spec import ExperimentSpecSet
from app.services.campaign_launch_context import ensure_campaign_launch_context_artifact
from app.services.claude_files import ensure_uploaded_to_claude
from app.services.gemini_file_search import ensure_uploaded_to_gemini_file_search, is_gemini_file_search_enabled
from app.strategy_v2.downstream import load_strategy_v2_outputs


_MANUAL_DOC_SPECS: tuple[tuple[str, ArtifactTypeEnum, str], ...] = (
    ("campaign_loaded_angles", ArtifactTypeEnum.campaign_loaded_angles, "Campaign Loaded Angles"),
    ("campaign_loaded_offer", ArtifactTypeEnum.campaign_loaded_offer, "Campaign Loaded Offer"),
    ("campaign_loaded_copy", ArtifactTypeEnum.campaign_loaded_copy, "Campaign Loaded Copy"),
    ("campaign_loaded_copy_context", ArtifactTypeEnum.campaign_loaded_copy_context, "Campaign Loaded Copy Context"),
    ("campaign_creative_context", ArtifactTypeEnum.campaign_creative_context, "Campaign Creative Context"),
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _artifact_payload(artifact: Any) -> dict[str, Any] | None:
    if artifact is None:
        return None
    payload = getattr(artifact, "data", None)
    if not isinstance(payload, dict):
        return None
    return payload


def resolve_campaign_creative_context_provider(
    *,
    session: Session,
    org_id: str,
    campaign_id: str,
) -> CampaignCreativeContextProviderEnum:
    artifact = ArtifactsRepository(session).get_latest_by_type_for_campaign(
        org_id=org_id,
        campaign_id=campaign_id,
        artifact_type=ArtifactTypeEnum.campaign_creative_context,
    )
    payload = _artifact_payload(artifact) or {}
    provider_value = str(payload.get("provider") or "").strip()
    if provider_value == CampaignCreativeContextProviderEnum.manual.value:
        return CampaignCreativeContextProviderEnum.manual
    return CampaignCreativeContextProviderEnum.strategy_v2


def _build_manual_downstream_packet(
    *,
    angles: dict[str, Any] | None,
    offer: dict[str, Any] | None,
    copy: dict[str, Any] | None,
    copy_context: dict[str, Any] | None,
    artifact_ids: dict[str, str | None],
) -> dict[str, Any] | None:
    if not isinstance(angles, dict) or not isinstance(offer, dict) or not isinstance(copy, dict):
        return None
    if not isinstance(copy_context, dict):
        return None

    angle_library = angles.get("angleLibrary") if isinstance(angles.get("angleLibrary"), list) else []
    selected_angle_id = str(angles.get("selectedAngleId") or "").strip()
    selected_angle = next(
        (
            entry
            for entry in angle_library
            if isinstance(entry, dict) and str(entry.get("angleId") or "").strip() == selected_angle_id
        ),
        {},
    )

    return {
        "selected_angle": {
            "angle_id": selected_angle.get("angleId"),
            "angle_name": selected_angle.get("angleName"),
            "description": selected_angle.get("description"),
            "evidence": selected_angle.get("evidence") or [],
        },
        "angle_library": angle_library,
        "offer": {
            "ump": offer.get("ump"),
            "ums": offer.get("ums"),
            "core_promise": offer.get("corePromise"),
            "value_stack_summary": offer.get("valueStackSummary"),
            "guarantee_type": offer.get("guaranteeType"),
            "pricing_rationale": offer.get("pricingRationale"),
            "selected_variant": {
                "id": offer.get("selectedVariantId"),
                "name": offer.get("selectedVariantName"),
            },
            "offer_details_markdown": offer.get("offerDetailsMarkdown"),
        },
        "copy": {
            "headline": copy.get("headline"),
            "promise_contract": {
                "loop_question": ((copy.get("promiseContract") or {}) if isinstance(copy.get("promiseContract"), dict) else {}).get("loopQuestion"),
                "specific_promise": ((copy.get("promiseContract") or {}) if isinstance(copy.get("promiseContract"), dict) else {}).get("specificPromise"),
                "delivery_test": ((copy.get("promiseContract") or {}) if isinstance(copy.get("promiseContract"), dict) else {}).get("deliveryTest"),
                "minimum_delivery": ((copy.get("promiseContract") or {}) if isinstance(copy.get("promiseContract"), dict) else {}).get("minimumDelivery"),
            },
            "presell_markdown": copy.get("presellMarkdown"),
            "sales_page_markdown": copy.get("salesPageMarkdown"),
            "template_payloads": copy.get("templatePayloads"),
        },
        "copy_context": {
            "audience_product_markdown": copy_context.get("audienceProductMarkdown"),
            "brand_voice_markdown": copy_context.get("brandVoiceMarkdown"),
            "compliance_markdown": copy_context.get("complianceMarkdown"),
            "mental_models_markdown": copy_context.get("mentalModelsMarkdown"),
            "awareness_angle_matrix_markdown": copy_context.get("awarenessAngleMatrixMarkdown"),
        },
        "awareness_angle_matrix": {
            "markdown": copy_context.get("awarenessAngleMatrixMarkdown"),
        },
        "provenance": {
            "angles_artifact_id": artifact_ids.get("angles"),
            "offer_artifact_id": artifact_ids.get("offer"),
            "copy_artifact_id": artifact_ids.get("copy"),
            "copy_context_artifact_id": artifact_ids.get("copy_context"),
        },
    }


def load_campaign_creative_context(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    product_id: str,
    campaign_id: str,
) -> dict[str, Any]:
    provider = resolve_campaign_creative_context_provider(
        session=session,
        org_id=org_id,
        campaign_id=campaign_id,
    )
    artifacts_repo = ArtifactsRepository(session)

    if provider == CampaignCreativeContextProviderEnum.strategy_v2:
        strategy_outputs = load_strategy_v2_outputs(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
        )
        angle_names: list[str] = []
        stage3 = strategy_outputs.get("stage3")
        if isinstance(stage3, dict):
            selected_angle = stage3.get("selected_angle")
            if isinstance(selected_angle, dict):
                angle_name = str(selected_angle.get("angle_name") or "").strip()
                if angle_name:
                    angle_names.append(angle_name)
        return {
            "provider": provider,
            "downstream_packet": strategy_outputs.get("downstream_packet"),
            "angle_names": angle_names,
            **strategy_outputs,
        }

    manual_context_artifact = artifacts_repo.get_latest_by_type_for_campaign(
        org_id=org_id,
        campaign_id=campaign_id,
        artifact_type=ArtifactTypeEnum.campaign_creative_context,
    )
    angles_artifact = artifacts_repo.get_latest_by_type_for_campaign(
        org_id=org_id,
        campaign_id=campaign_id,
        artifact_type=ArtifactTypeEnum.campaign_loaded_angles,
    )
    offer_artifact = artifacts_repo.get_latest_by_type_for_campaign(
        org_id=org_id,
        campaign_id=campaign_id,
        artifact_type=ArtifactTypeEnum.campaign_loaded_offer,
    )
    copy_artifact = artifacts_repo.get_latest_by_type_for_campaign(
        org_id=org_id,
        campaign_id=campaign_id,
        artifact_type=ArtifactTypeEnum.campaign_loaded_copy,
    )
    copy_context_artifact = artifacts_repo.get_latest_by_type_for_campaign(
        org_id=org_id,
        campaign_id=campaign_id,
        artifact_type=ArtifactTypeEnum.campaign_loaded_copy_context,
    )

    angles = _artifact_payload(angles_artifact)
    offer = _artifact_payload(offer_artifact)
    copy = _artifact_payload(copy_artifact)
    copy_context = _artifact_payload(copy_context_artifact)
    artifact_ids = {
        "angles": str(getattr(angles_artifact, "id", "")) if angles_artifact is not None else None,
        "offer": str(getattr(offer_artifact, "id", "")) if offer_artifact is not None else None,
        "copy": str(getattr(copy_artifact, "id", "")) if copy_artifact is not None else None,
        "copy_context": str(getattr(copy_context_artifact, "id", "")) if copy_context_artifact is not None else None,
        "creative_context": str(getattr(manual_context_artifact, "id", "")) if manual_context_artifact is not None else None,
    }
    downstream_packet = _build_manual_downstream_packet(
        angles=angles,
        offer=offer,
        copy=copy,
        copy_context=copy_context,
        artifact_ids=artifact_ids,
    )

    angle_names: list[str] = []
    angle_library = angles.get("angleLibrary") if isinstance(angles, dict) else None
    if isinstance(angle_library, list):
        for entry in angle_library:
            if not isinstance(entry, dict):
                continue
            angle_name = str(entry.get("angleName") or "").strip()
            if angle_name:
                angle_names.append(angle_name)

    return {
        "provider": provider,
        "manual_context_artifact": manual_context_artifact,
        "angles_artifact": angles_artifact,
        "offer_artifact": offer_artifact,
        "copy_artifact": copy_artifact,
        "copy_context_artifact": copy_context_artifact,
        "angles": angles,
        "offer": offer,
        "copy": copy,
        "copy_context": copy_context,
        "artifact_ids": artifact_ids,
        "downstream_packet": downstream_packet,
        "angle_names": angle_names,
    }


def ensure_campaign_creative_context_ready(
    *,
    session: Session,
    org_id: str,
    campaign: Campaign,
) -> dict[str, Any]:
    provider = resolve_campaign_creative_context_provider(
        session=session,
        org_id=org_id,
        campaign_id=str(campaign.id),
    )

    if provider == CampaignCreativeContextProviderEnum.strategy_v2:
        readiness = ensure_campaign_launch_context_artifact(
            session=session,
            org_id=org_id,
            campaign=campaign,
        )
        readiness["provider"] = provider.value
        readiness["manualCreativeContextArtifactId"] = None
        readiness["missingArtifacts"] = []
        return readiness

    artifacts_repo = ArtifactsRepository(session)
    aggregate_artifact = artifacts_repo.get_latest_by_type_for_campaign(
        org_id=org_id,
        campaign_id=str(campaign.id),
        artifact_type=ArtifactTypeEnum.campaign_creative_context,
    )
    section_artifacts = {
        "campaign_loaded_angles": artifacts_repo.get_latest_by_type_for_campaign(
            org_id=org_id,
            campaign_id=str(campaign.id),
            artifact_type=ArtifactTypeEnum.campaign_loaded_angles,
        ),
        "campaign_loaded_offer": artifacts_repo.get_latest_by_type_for_campaign(
            org_id=org_id,
            campaign_id=str(campaign.id),
            artifact_type=ArtifactTypeEnum.campaign_loaded_offer,
        ),
        "campaign_loaded_copy": artifacts_repo.get_latest_by_type_for_campaign(
            org_id=org_id,
            campaign_id=str(campaign.id),
            artifact_type=ArtifactTypeEnum.campaign_loaded_copy,
        ),
        "campaign_loaded_copy_context": artifacts_repo.get_latest_by_type_for_campaign(
            org_id=org_id,
            campaign_id=str(campaign.id),
            artifact_type=ArtifactTypeEnum.campaign_loaded_copy_context,
        ),
        "experiment_spec": artifacts_repo.get_latest_by_type_for_campaign(
            org_id=org_id,
            campaign_id=str(campaign.id),
            artifact_type=ArtifactTypeEnum.experiment_spec,
        ),
    }
    missing_artifacts = [key for key, artifact in section_artifacts.items() if artifact is None]
    ready = aggregate_artifact is not None and not missing_artifacts

    return {
        "provider": provider.value,
        "ready": ready,
        "checkedAt": _iso_now(),
        "reason": None if ready else "Manual campaign creative context is incomplete.",
        "sourceStrategyV2WorkflowRunId": None,
        "sourceStrategyV2TemporalWorkflowId": None,
        "launchContextArtifactId": None,
        "manualCreativeContextArtifactId": str(aggregate_artifact.id) if aggregate_artifact is not None else None,
        "refreshed": False,
        "staleArtifactId": None,
        "missingArtifacts": missing_artifacts,
    }


def _persist_workspace_docs(
    *,
    org_id: str,
    client_id: str,
    product_id: str | None,
    campaign_id: str,
    docs: list[dict[str, Any]],
) -> list[str]:
    uploaded_doc_keys: list[str] = []
    gemini_enabled = is_gemini_file_search_enabled()
    for doc in docs:
        payload = doc["payload"]
        doc_key = doc["doc_key"]
        doc_title = doc["doc_title"]
        source_kind = doc["source_kind"]
        content_bytes = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        ensure_uploaded_to_claude(
            org_id=org_id,
            idea_workspace_id=campaign_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            doc_key=doc_key,
            doc_title=doc_title,
            source_kind=source_kind,
            step_key=None,
            filename=f"{doc_key}.json",
            mime_type="text/plain",
            content_bytes=content_bytes,
            drive_doc_id=None,
            drive_url=None,
            allow_stub=False,
        )
        if gemini_enabled:
            ensure_uploaded_to_gemini_file_search(
                org_id=org_id,
                idea_workspace_id=campaign_id,
                client_id=client_id,
                product_id=product_id,
                campaign_id=campaign_id,
                doc_key=doc_key,
                doc_title=doc_title,
                source_kind=source_kind,
                step_key=None,
                filename=f"{doc_key}.json",
                mime_type="text/plain",
                content_bytes=content_bytes,
                drive_doc_id=None,
                drive_url=None,
            )
        uploaded_doc_keys.append(doc_key)
    return uploaded_doc_keys


def set_campaign_creative_context_provider(
    *,
    session: Session,
    org_id: str,
    campaign: Campaign,
    provider: CampaignCreativeContextProviderEnum,
    created_by_user: str | None,
) -> Any:
    payload = {
        "schemaVersion": 1,
        "provider": provider.value,
        "campaignId": str(campaign.id),
        "clientId": str(campaign.client_id),
        "productId": str(campaign.product_id) if campaign.product_id else None,
        "checkedAt": _iso_now(),
    }
    return ArtifactsRepository(session).insert(
        org_id=org_id,
        client_id=str(campaign.client_id),
        product_id=str(campaign.product_id) if campaign.product_id else None,
        campaign_id=str(campaign.id),
        artifact_type=ArtifactTypeEnum.campaign_creative_context,
        data=payload,
        created_by_user=created_by_user,
    )


def persist_manual_campaign_creative_context(
    *,
    session: Session,
    org_id: str,
    campaign: Campaign,
    payload: CampaignManualCreativeContextUpsertRequest,
    created_by_user: str | None,
) -> dict[str, Any]:
    artifacts_repo = ArtifactsRepository(session)
    product_id = str(campaign.product_id) if campaign.product_id else None
    checked_at = _iso_now()

    angles_payload = payload.angles.model_dump(mode="json", by_alias=True)
    offer_payload = payload.offer.model_dump(mode="json", by_alias=True)
    copy_payload = payload.copyDocument.model_dump(mode="json", by_alias=True)
    copy_context_payload = payload.copyContext.model_dump(mode="json", by_alias=True)
    experiment_spec_set = ExperimentSpecSet(
        clientId=str(campaign.client_id),
        campaignId=str(campaign.id),
        experimentSpecs=payload.experimentSpecs,
    )
    experiment_spec_payload = experiment_spec_set.model_dump(mode="json", by_alias=True)

    angles_artifact = artifacts_repo.insert(
        org_id=org_id,
        client_id=str(campaign.client_id),
        product_id=product_id,
        campaign_id=str(campaign.id),
        artifact_type=ArtifactTypeEnum.campaign_loaded_angles,
        data=angles_payload,
        created_by_user=created_by_user,
    )
    offer_artifact = artifacts_repo.insert(
        org_id=org_id,
        client_id=str(campaign.client_id),
        product_id=product_id,
        campaign_id=str(campaign.id),
        artifact_type=ArtifactTypeEnum.campaign_loaded_offer,
        data=offer_payload,
        created_by_user=created_by_user,
    )
    copy_artifact = artifacts_repo.insert(
        org_id=org_id,
        client_id=str(campaign.client_id),
        product_id=product_id,
        campaign_id=str(campaign.id),
        artifact_type=ArtifactTypeEnum.campaign_loaded_copy,
        data=copy_payload,
        created_by_user=created_by_user,
    )
    copy_context_artifact = artifacts_repo.insert(
        org_id=org_id,
        client_id=str(campaign.client_id),
        product_id=product_id,
        campaign_id=str(campaign.id),
        artifact_type=ArtifactTypeEnum.campaign_loaded_copy_context,
        data=copy_context_payload,
        created_by_user=created_by_user,
    )
    experiment_spec_artifact = artifacts_repo.insert(
        org_id=org_id,
        client_id=str(campaign.client_id),
        product_id=product_id,
        campaign_id=str(campaign.id),
        artifact_type=ArtifactTypeEnum.experiment_spec,
        data=experiment_spec_payload,
        created_by_user=created_by_user,
    )

    aggregate_payload = {
        "schemaVersion": payload.schemaVersion,
        "provider": CampaignCreativeContextProviderEnum.manual.value,
        "campaignId": str(campaign.id),
        "clientId": str(campaign.client_id),
        "productId": product_id,
        "checkedAt": checked_at,
        "artifactIds": {
            "campaign_loaded_angles": str(angles_artifact.id),
            "campaign_loaded_offer": str(offer_artifact.id),
            "campaign_loaded_copy": str(copy_artifact.id),
            "campaign_loaded_copy_context": str(copy_context_artifact.id),
            "experiment_spec": str(experiment_spec_artifact.id),
        },
        "manualContext": {
            "angles": angles_payload,
            "offer": offer_payload,
            "copy": copy_payload,
            "copyContext": copy_context_payload,
            "experimentSpecs": experiment_spec_payload.get("experimentSpecs") or [],
        },
        "downstreamPacket": _build_manual_downstream_packet(
            angles=angles_payload,
            offer=offer_payload,
            copy=copy_payload,
            copy_context=copy_context_payload,
            artifact_ids={
                "angles": str(angles_artifact.id),
                "offer": str(offer_artifact.id),
                "copy": str(copy_artifact.id),
                "copy_context": str(copy_context_artifact.id),
            },
        ),
    }
    creative_context_artifact = artifacts_repo.insert(
        org_id=org_id,
        client_id=str(campaign.client_id),
        product_id=product_id,
        campaign_id=str(campaign.id),
        artifact_type=ArtifactTypeEnum.campaign_creative_context,
        data=aggregate_payload,
        created_by_user=created_by_user,
    )

    uploaded_doc_keys = _persist_workspace_docs(
        org_id=org_id,
        client_id=str(campaign.client_id),
        product_id=product_id,
        campaign_id=str(campaign.id),
        docs=[
            {
                "doc_key": "campaign_loaded_angles",
                "doc_title": "Campaign Loaded Angles",
                "source_kind": ArtifactTypeEnum.campaign_loaded_angles.value,
                "payload": angles_payload,
            },
            {
                "doc_key": "campaign_loaded_offer",
                "doc_title": "Campaign Loaded Offer",
                "source_kind": ArtifactTypeEnum.campaign_loaded_offer.value,
                "payload": offer_payload,
            },
            {
                "doc_key": "campaign_loaded_copy",
                "doc_title": "Campaign Loaded Copy",
                "source_kind": ArtifactTypeEnum.campaign_loaded_copy.value,
                "payload": copy_payload,
            },
            {
                "doc_key": "campaign_loaded_copy_context",
                "doc_title": "Campaign Loaded Copy Context",
                "source_kind": ArtifactTypeEnum.campaign_loaded_copy_context.value,
                "payload": copy_context_payload,
            },
            {
                "doc_key": "campaign_creative_context",
                "doc_title": "Campaign Creative Context",
                "source_kind": ArtifactTypeEnum.campaign_creative_context.value,
                "payload": aggregate_payload,
            },
            {
                "doc_key": f"experiment_specs:{campaign.id}",
                "doc_title": "Experiment Specs",
                "source_kind": ArtifactTypeEnum.experiment_spec.value,
                "payload": experiment_spec_payload,
            },
        ],
    )

    return {
        "campaignId": str(campaign.id),
        "provider": CampaignCreativeContextProviderEnum.manual.value,
        "creativeContextArtifactId": str(creative_context_artifact.id),
        "experimentSpecArtifactId": str(experiment_spec_artifact.id),
        "artifactIds": {
            "campaign_loaded_angles": str(angles_artifact.id),
            "campaign_loaded_offer": str(offer_artifact.id),
            "campaign_loaded_copy": str(copy_artifact.id),
            "campaign_loaded_copy_context": str(copy_context_artifact.id),
            "campaign_creative_context": str(creative_context_artifact.id),
        },
        "uploadedDocKeys": uploaded_doc_keys,
        "checkedAt": checked_at,
    }
