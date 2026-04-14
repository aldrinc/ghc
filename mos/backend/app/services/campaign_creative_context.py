from __future__ import annotations

from datetime import datetime, timezone
import hashlib
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
from app.services.product_strategy_bundles import (
    ProductStrategyBundlesError,
    ProductStrategyBundlesService,
)
from app.strategy_v2.downstream import load_strategy_v2_outputs


_MANUAL_DOC_SPECS: tuple[tuple[str, ArtifactTypeEnum, str], ...] = (
    ("campaign_loaded_angles", ArtifactTypeEnum.campaign_loaded_angles, "Campaign Loaded Angles"),
    ("campaign_loaded_offer", ArtifactTypeEnum.campaign_loaded_offer, "Campaign Loaded Offer"),
    ("campaign_loaded_copy", ArtifactTypeEnum.campaign_loaded_copy, "Campaign Loaded Copy"),
    ("campaign_loaded_copy_context", ArtifactTypeEnum.campaign_loaded_copy_context, "Campaign Loaded Copy Context"),
    ("campaign_creative_context", ArtifactTypeEnum.campaign_creative_context, "Campaign Creative Context"),
)

_SKILLS_COMPATIBILITY_REQUIRED_ROLES: tuple[str, ...] = (
    "signal_report",
    "angle_library",
    "angle_selection",
    "knowledge_base",
    "cso",
    "offer_document",
    "headline_selection",
    "presell_page",
    "sales_page",
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


def _stable_json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


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
    if provider_value == CampaignCreativeContextProviderEnum.skills.value:
        return CampaignCreativeContextProviderEnum.skills
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


def _load_active_skills_bundle(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    product_id: str,
) -> dict[str, Any]:
    service = ProductStrategyBundlesService(
        session=session,
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        created_by_user=None,
    )
    return service.get_active_bundle(bundle_type="skills_handoff")


def _latest_materialized_skills_creative_context_artifact(
    *,
    artifacts_repo: ArtifactsRepository,
    org_id: str,
    campaign_id: str,
) -> Any | None:
    candidates = artifacts_repo.list(
        org_id=org_id,
        campaign_id=campaign_id,
        artifact_type=ArtifactTypeEnum.campaign_creative_context,
        limit=50,
    )
    for artifact in candidates:
        payload = _artifact_payload(artifact) or {}
        if str(payload.get("provider") or "").strip() != CampaignCreativeContextProviderEnum.skills.value:
            continue
        if isinstance(payload.get("materializedContext"), dict):
            return artifact
    return None


def _skills_materialization_signature(
    *,
    strategy_bundle_id: str,
    strategy_bundle_type: str,
    angles: dict[str, Any],
    offer: dict[str, Any],
    copy: dict[str, Any],
    copy_context: dict[str, Any],
    source_artifact_ids: dict[str, str | None],
    angle_names: list[str],
) -> str:
    signature_payload = {
        "strategyBundleId": strategy_bundle_id,
        "strategyBundleType": strategy_bundle_type,
        "angles": angles,
        "offer": offer,
        "copy": copy,
        "copyContext": copy_context,
        "sourceArtifactIds": source_artifact_ids,
        "angleNames": angle_names,
    }
    return hashlib.sha256(_stable_json_dumps(signature_payload).encode("utf-8")).hexdigest()


def _materialized_skills_context_payload(artifact: Any | None) -> dict[str, Any] | None:
    payload = _artifact_payload(artifact)
    if not isinstance(payload, dict):
        return None
    if str(payload.get("provider") or "").strip() != CampaignCreativeContextProviderEnum.skills.value:
        return None
    materialized_context = payload.get("materializedContext")
    if not isinstance(materialized_context, dict):
        return None
    return payload


def _skills_bundle_items_by_role(bundle_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = bundle_payload.get("items") or []
    return {
        str(item.get("role") or "").strip(): item
        for item in items
        if isinstance(item, dict) and str(item.get("role") or "").strip()
    }


def _skills_missing_roles(bundle_payload: dict[str, Any]) -> list[str]:
    roles = _skills_bundle_items_by_role(bundle_payload)
    return [role for role in _SKILLS_COMPATIBILITY_REQUIRED_ROLES if role not in roles]


def _bundle_item_artifact_id(item: dict[str, Any] | None) -> str | None:
    if not isinstance(item, dict):
        return None
    value = str(item.get("artifactId") or "").strip()
    return value or None


def _require_skills_item(role_map: dict[str, dict[str, Any]], *, role: str) -> dict[str, Any]:
    item = role_map.get(role)
    if item is None:
        raise ValueError(
            "Skills campaign creative context is incomplete. "
            f"Missing required active bundle role '{role}'."
        )
    return item


def _require_skills_markdown(item: dict[str, Any], *, role: str) -> str:
    artifact_data = item.get("artifactData")
    if not isinstance(artifact_data, dict):
        raise ValueError(f"Skills bundle role '{role}' is missing artifact data.")
    if str(artifact_data.get("documentFormat") or "").strip().lower() != "markdown":
        raise ValueError(f"Skills bundle role '{role}' must be a markdown document.")
    markdown = str(artifact_data.get("markdown") or "").strip()
    if not markdown:
        raise ValueError(f"Skills bundle role '{role}' markdown is empty.")
    return markdown


def _require_skills_json(item: dict[str, Any], *, role: str) -> dict[str, Any]:
    artifact_data = item.get("artifactData")
    if not isinstance(artifact_data, dict):
        raise ValueError(f"Skills bundle role '{role}' is missing artifact data.")
    if str(artifact_data.get("documentFormat") or "").strip().lower() != "json":
        raise ValueError(f"Skills bundle role '{role}' must be a JSON document.")
    payload = artifact_data.get("json")
    if not isinstance(payload, dict):
        raise ValueError(f"Skills bundle role '{role}' JSON payload is invalid.")
    return payload


def _derived_markdown_document(*, title: str, source_role: str, content: str) -> str:
    normalized = content.strip()
    if not normalized:
        raise ValueError(
            "Skills campaign creative context is missing required source content for "
            f"derived '{title}' from role '{source_role}'."
        )
    return "\n".join(
        [
            f"# {title}",
            "",
            f"Derived from approved `{source_role}` artifact.",
            "",
            normalized,
        ]
    ).strip()


def _build_derived_awareness_angle_matrix_markdown(
    *,
    angle_library: dict[str, Any],
    angle_selection: dict[str, Any],
) -> str:
    selected_angle = angle_selection.get("selectedAngle")
    if not isinstance(selected_angle, dict):
        raise ValueError("Skills angle_selection artifact is missing selectedAngle.")
    selected_angle_name = str(selected_angle.get("angleName") or "").strip()
    if not selected_angle_name:
        raise ValueError("Skills angle_selection artifact is missing selectedAngle.angleName.")

    lines = [
        "# Awareness Angle Matrix",
        "",
        "Derived from approved `angle_library` and `angle_selection` artifacts.",
        "",
        "## Selected Angle",
        f"- ID: {str(selected_angle.get('angleId') or '').strip()}",
        f"- Name: {selected_angle_name}",
    ]
    selected_description = str(selected_angle.get("description") or "").strip()
    if selected_description:
        lines.append(f"- Description: {selected_description}")
    selected_evidence = selected_angle.get("evidence")
    if isinstance(selected_evidence, list):
        for evidence in selected_evidence:
            if isinstance(evidence, str) and evidence.strip():
                lines.append(f"- Evidence: {evidence.strip()}")

    lines.extend(["", "## Angle Library"])
    angles = angle_library.get("angles")
    if not isinstance(angles, list) or not angles:
        raise ValueError("Skills angle_library artifact must contain a non-empty angles list.")
    for entry in angles:
        if not isinstance(entry, dict):
            continue
        angle_name = str(entry.get("angleName") or "").strip()
        if not angle_name:
            continue
        lines.extend(["", f"### {angle_name}"])
        description = str(entry.get("description") or "").strip()
        mechanism = str(entry.get("mechanism") or "").strip()
        if description:
            lines.append(f"- Description: {description}")
        if mechanism:
            lines.append(f"- Mechanism: {mechanism}")
        evidence_list = entry.get("evidence")
        if isinstance(evidence_list, list):
            for evidence in evidence_list:
                if isinstance(evidence, str) and evidence.strip():
                    lines.append(f"- Evidence: {evidence.strip()}")
    return "\n".join(lines).strip()


def _build_skills_compatibility_payload(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    product_id: str,
) -> dict[str, Any]:
    bundle_payload = _load_active_skills_bundle(
        session=session,
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
    )
    missing_roles = _skills_missing_roles(bundle_payload)
    if missing_roles:
        raise ValueError(
            "Skills campaign creative context is incomplete. "
            "Active bundle is missing required roles: "
            + ", ".join(missing_roles)
            + "."
        )

    roles = _skills_bundle_items_by_role(bundle_payload)
    angle_library_item = _require_skills_item(roles, role="angle_library")
    angle_selection_item = _require_skills_item(roles, role="angle_selection")
    signal_report_item = _require_skills_item(roles, role="signal_report")
    knowledge_base_item = _require_skills_item(roles, role="knowledge_base")
    cso_item = _require_skills_item(roles, role="cso")
    offer_item = _require_skills_item(roles, role="offer_document")
    headline_selection_item = _require_skills_item(roles, role="headline_selection")
    presell_item = _require_skills_item(roles, role="presell_page")
    sales_item = _require_skills_item(roles, role="sales_page")

    angle_library = _require_skills_json(angle_library_item, role="angle_library")
    angle_selection = _require_skills_json(angle_selection_item, role="angle_selection")
    offer_payload = _require_skills_json(offer_item, role="offer_document")
    headline_selection = _require_skills_json(headline_selection_item, role="headline_selection")
    signal_report_markdown = _require_skills_markdown(signal_report_item, role="signal_report")
    knowledge_base_markdown = _require_skills_markdown(knowledge_base_item, role="knowledge_base")
    cso_markdown = _require_skills_markdown(cso_item, role="cso")
    presell_markdown = _require_skills_markdown(presell_item, role="presell_page")
    sales_markdown = _require_skills_markdown(sales_item, role="sales_page")

    selected_angle_id = str(angle_selection.get("selectedAngleId") or "").strip()
    if not selected_angle_id:
        raise ValueError("Skills angle_selection artifact is missing selectedAngleId.")

    angles = angle_library.get("angles")
    if not isinstance(angles, list) or not angles:
        raise ValueError("Skills angle_library artifact must contain a non-empty angles list.")

    selected_headline = headline_selection.get("selectedHeadline")
    if not isinstance(selected_headline, dict):
        raise ValueError("Skills headline_selection artifact is missing selectedHeadline.")
    headline_text = str(selected_headline.get("headline") or "").strip()
    if not headline_text:
        raise ValueError("Skills headline_selection artifact is missing selectedHeadline.headline.")

    angles_payload = {
        "selectedAngleId": selected_angle_id,
        "angleLibrary": angles,
    }
    copy_payload = {
        "headline": headline_text,
        "promiseContract": {
            "loopQuestion": "",
            "specificPromise": str(offer_payload.get("corePromise") or "").strip(),
            "deliveryTest": "",
            "minimumDelivery": "",
        },
        "presellMarkdown": presell_markdown,
        "salesPageMarkdown": sales_markdown,
        "templatePayloads": None,
    }
    copy_context_payload = {
        "audienceProductMarkdown": _derived_markdown_document(
            title="Audience + Product",
            source_role="knowledge_base",
            content=knowledge_base_markdown,
        ),
        "brandVoiceMarkdown": _derived_markdown_document(
            title="Brand Voice",
            source_role="cso",
            content=cso_markdown,
        ),
        "complianceMarkdown": _derived_markdown_document(
            title="Compliance",
            source_role="cso",
            content=cso_markdown,
        ),
        "mentalModelsMarkdown": _derived_markdown_document(
            title="Mental Models",
            source_role="signal_report",
            content=signal_report_markdown,
        ),
        "awarenessAngleMatrixMarkdown": _build_derived_awareness_angle_matrix_markdown(
            angle_library=angle_library,
            angle_selection=angle_selection,
        ),
    }
    artifact_ids = {
        "angles": _bundle_item_artifact_id(angle_library_item),
        "offer": _bundle_item_artifact_id(offer_item),
        "copy": _bundle_item_artifact_id(presell_item),
        "copy_context": _bundle_item_artifact_id(knowledge_base_item),
        "signal_report": _bundle_item_artifact_id(signal_report_item),
        "knowledge_base": _bundle_item_artifact_id(knowledge_base_item),
        "cso": _bundle_item_artifact_id(cso_item),
        "headline_selection": _bundle_item_artifact_id(headline_selection_item),
        "presell_page": _bundle_item_artifact_id(presell_item),
        "sales_page": _bundle_item_artifact_id(sales_item),
    }

    angle_names: list[str] = []
    for entry in angles:
        if not isinstance(entry, dict):
            continue
        angle_name = str(entry.get("angleName") or "").strip()
        if angle_name:
            angle_names.append(angle_name)

    return {
        "provider": CampaignCreativeContextProviderEnum.skills,
        "skills_bundle": bundle_payload,
        "angles": angles_payload,
        "offer": offer_payload,
        "copy": copy_payload,
        "copy_context": copy_context_payload,
        "artifact_ids": artifact_ids,
        "downstream_packet": _build_manual_downstream_packet(
            angles=angles_payload,
            offer=offer_payload,
            copy=copy_payload,
            copy_context=copy_context_payload,
            artifact_ids=artifact_ids,
        ),
        "angle_names": angle_names,
    }


def materialize_skills_campaign_creative_context(
    *,
    session: Session,
    org_id: str,
    campaign: Campaign,
    created_by_user: str | None,
) -> dict[str, Any]:
    provider = resolve_campaign_creative_context_provider(
        session=session,
        org_id=org_id,
        campaign_id=str(campaign.id),
    )
    if provider != CampaignCreativeContextProviderEnum.skills:
        raise ValueError(
            "Campaign creative context materialization requires provider 'skills'."
        )
    if not campaign.product_id:
        raise ValueError(
            "Campaign creative context provider 'skills' requires the campaign to have a product_id."
        )

    compatibility_payload = _build_skills_compatibility_payload(
        session=session,
        org_id=org_id,
        client_id=str(campaign.client_id),
        product_id=str(campaign.product_id),
    )
    skills_bundle = compatibility_payload["skills_bundle"]
    strategy_bundle_id = str(skills_bundle.get("id") or "").strip()
    strategy_bundle_type = str(skills_bundle.get("bundleType") or "").strip()
    if not strategy_bundle_id or not strategy_bundle_type:
        raise ValueError("Active skills handoff bundle is missing identity metadata.")

    source_artifact_ids = {
        "angle_library": compatibility_payload["artifact_ids"].get("angles"),
        "offer_document": compatibility_payload["artifact_ids"].get("offer"),
        "presell_page": compatibility_payload["artifact_ids"].get("presell_page"),
        "knowledge_base": compatibility_payload["artifact_ids"].get("knowledge_base"),
        "signal_report": compatibility_payload["artifact_ids"].get("signal_report"),
        "cso": compatibility_payload["artifact_ids"].get("cso"),
        "headline_selection": compatibility_payload["artifact_ids"].get("headline_selection"),
        "sales_page": compatibility_payload["artifact_ids"].get("sales_page"),
        "angle_selection": _bundle_item_artifact_id(
            _skills_bundle_items_by_role(skills_bundle).get("angle_selection")
        ),
    }
    compatibility_signature = _skills_materialization_signature(
        strategy_bundle_id=strategy_bundle_id,
        strategy_bundle_type=strategy_bundle_type,
        angles=compatibility_payload["angles"],
        offer=compatibility_payload["offer"],
        copy=compatibility_payload["copy"],
        copy_context=compatibility_payload["copy_context"],
        source_artifact_ids=source_artifact_ids,
        angle_names=compatibility_payload["angle_names"],
    )

    artifacts_repo = ArtifactsRepository(session)
    latest_materialized_artifact = _latest_materialized_skills_creative_context_artifact(
        artifacts_repo=artifacts_repo,
        org_id=org_id,
        campaign_id=str(campaign.id),
    )
    latest_materialized_payload = _materialized_skills_context_payload(latest_materialized_artifact)
    if latest_materialized_payload is not None:
        existing_signature = str(latest_materialized_payload.get("compatibilitySignature") or "").strip()
        existing_artifact_ids = latest_materialized_payload.get("artifactIds")
        if existing_signature == compatibility_signature and isinstance(existing_artifact_ids, dict):
            return {
                "campaignId": str(campaign.id),
                "provider": CampaignCreativeContextProviderEnum.skills.value,
                "creativeContextArtifactId": str(latest_materialized_artifact.id),
                "artifactIds": {str(key): str(value) for key, value in existing_artifact_ids.items()},
                "sourceArtifactIds": source_artifact_ids,
                "strategyBundleId": strategy_bundle_id,
                "strategyBundleType": strategy_bundle_type,
                "uploadedDocKeys": [
                    "campaign_loaded_angles",
                    "campaign_loaded_offer",
                    "campaign_loaded_copy",
                    "campaign_loaded_copy_context",
                    "campaign_creative_context",
                ],
                "refreshed": False,
                "staleArtifactId": None,
                "checkedAt": str(latest_materialized_payload.get("checkedAt") or _iso_now()),
            }

    product_id = str(campaign.product_id)
    checked_at = _iso_now()
    angles_payload = compatibility_payload["angles"]
    offer_payload = compatibility_payload["offer"]
    copy_payload = compatibility_payload["copy"]
    copy_context_payload = compatibility_payload["copy_context"]

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

    aggregate_payload = {
        "schemaVersion": 1,
        "provider": CampaignCreativeContextProviderEnum.skills.value,
        "campaignId": str(campaign.id),
        "clientId": str(campaign.client_id),
        "productId": product_id,
        "checkedAt": checked_at,
        "compatibilitySignature": compatibility_signature,
        "strategyBundleId": strategy_bundle_id,
        "strategyBundleType": strategy_bundle_type,
        "sourceArtifactIds": source_artifact_ids,
        "artifactIds": {
            "campaign_loaded_angles": str(angles_artifact.id),
            "campaign_loaded_offer": str(offer_artifact.id),
            "campaign_loaded_copy": str(copy_artifact.id),
            "campaign_loaded_copy_context": str(copy_context_artifact.id),
        },
        "materializedContext": {
            "angles": angles_payload,
            "offer": offer_payload,
            "copy": copy_payload,
            "copyContext": copy_context_payload,
        },
        "downstreamPacket": compatibility_payload["downstream_packet"],
        "angleNames": compatibility_payload["angle_names"],
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
    aggregate_payload["artifactIds"]["campaign_creative_context"] = str(creative_context_artifact.id)

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
        ],
    )

    return {
        "campaignId": str(campaign.id),
        "provider": CampaignCreativeContextProviderEnum.skills.value,
        "creativeContextArtifactId": str(creative_context_artifact.id),
        "artifactIds": aggregate_payload["artifactIds"],
        "sourceArtifactIds": source_artifact_ids,
        "strategyBundleId": strategy_bundle_id,
        "strategyBundleType": strategy_bundle_type,
        "uploadedDocKeys": uploaded_doc_keys,
        "refreshed": True,
        "staleArtifactId": str(latest_materialized_artifact.id) if latest_materialized_artifact is not None else None,
        "checkedAt": checked_at,
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

    if provider == CampaignCreativeContextProviderEnum.skills:
        if not product_id:
            raise ValueError(
                "Campaign creative context provider 'skills' requires the campaign to have a product_id."
            )
        materialized_artifact = _latest_materialized_skills_creative_context_artifact(
            artifacts_repo=artifacts_repo,
            org_id=org_id,
            campaign_id=campaign_id,
        )
        materialized_payload = _materialized_skills_context_payload(materialized_artifact)
        if materialized_payload is None:
            raise ValueError(
                "Skills campaign creative context has not been materialized for this campaign. "
                "Run skills creative-context materialization before downstream execution."
            )
        materialized_context = materialized_payload["materializedContext"]
        artifact_ids = materialized_payload.get("artifactIds")
        if not isinstance(artifact_ids, dict):
            raise ValueError("Materialized skills campaign creative context is missing artifactIds.")
        angle_names = materialized_payload.get("angleNames")
        if not isinstance(angle_names, list):
            angle_names = []
        downstream_packet = materialized_payload.get("downstreamPacket")
        if not isinstance(downstream_packet, dict):
            downstream_packet = _build_manual_downstream_packet(
                angles=materialized_context.get("angles"),
                offer=materialized_context.get("offer"),
                copy=materialized_context.get("copy"),
                copy_context=materialized_context.get("copyContext"),
                artifact_ids={
                    "angles": artifact_ids.get("campaign_loaded_angles"),
                    "offer": artifact_ids.get("campaign_loaded_offer"),
                    "copy": artifact_ids.get("campaign_loaded_copy"),
                    "copy_context": artifact_ids.get("campaign_loaded_copy_context"),
                },
            )
        return {
            "provider": provider,
            "materialized_context_artifact": materialized_artifact,
            "skills_bundle": {
                "id": materialized_payload.get("strategyBundleId"),
                "bundleType": materialized_payload.get("strategyBundleType"),
            },
            "angles": materialized_context.get("angles"),
            "offer": materialized_context.get("offer"),
            "copy": materialized_context.get("copy"),
            "copy_context": materialized_context.get("copyContext"),
            "artifact_ids": {
                "angles": artifact_ids.get("campaign_loaded_angles"),
                "offer": artifact_ids.get("campaign_loaded_offer"),
                "copy": artifact_ids.get("campaign_loaded_copy"),
                "copy_context": artifact_ids.get("campaign_loaded_copy_context"),
                "creative_context": artifact_ids.get("campaign_creative_context"),
            },
            "downstream_packet": downstream_packet,
            "angle_names": [str(value).strip() for value in angle_names if str(value).strip()],
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
        readiness["creativeContextArtifactId"] = None
        readiness["strategyBundleId"] = None
        readiness["strategyBundleType"] = None
        readiness["missingArtifacts"] = []
        return readiness

    artifacts_repo = ArtifactsRepository(session)
    aggregate_artifact = artifacts_repo.get_latest_by_type_for_campaign(
        org_id=org_id,
        campaign_id=str(campaign.id),
        artifact_type=ArtifactTypeEnum.campaign_creative_context,
    )

    if provider == CampaignCreativeContextProviderEnum.skills:
        materialized_artifact = _latest_materialized_skills_creative_context_artifact(
            artifacts_repo=artifacts_repo,
            org_id=org_id,
            campaign_id=str(campaign.id),
        )
        materialized_payload = _materialized_skills_context_payload(materialized_artifact)
        if not campaign.product_id:
            return {
                "provider": provider.value,
                "ready": False,
                "checkedAt": _iso_now(),
                "reason": "Skills campaign creative context requires the campaign to have a product_id.",
                "sourceStrategyV2WorkflowRunId": None,
                "sourceStrategyV2TemporalWorkflowId": None,
                "launchContextArtifactId": None,
                "manualCreativeContextArtifactId": None,
                "creativeContextArtifactId": str(aggregate_artifact.id) if aggregate_artifact is not None else None,
                "materializedCreativeContextArtifactId": str(materialized_artifact.id)
                if materialized_artifact is not None
                else None,
                "materializedArtifactIds": materialized_payload.get("artifactIds")
                if materialized_payload is not None and isinstance(materialized_payload.get("artifactIds"), dict)
                else None,
                "strategyBundleId": None,
                "strategyBundleType": None,
                "refreshed": False,
                "staleArtifactId": None,
                "missingArtifacts": ["product_id"],
            }
        try:
            bundle_payload = _load_active_skills_bundle(
                session=session,
                org_id=org_id,
                client_id=str(campaign.client_id),
                product_id=str(campaign.product_id),
            )
        except ProductStrategyBundlesError as exc:
            return {
                "provider": provider.value,
                "ready": False,
                "checkedAt": _iso_now(),
                "reason": str(exc),
                "sourceStrategyV2WorkflowRunId": None,
                "sourceStrategyV2TemporalWorkflowId": None,
                "launchContextArtifactId": None,
                "manualCreativeContextArtifactId": None,
                "creativeContextArtifactId": str(aggregate_artifact.id) if aggregate_artifact is not None else None,
                "materializedCreativeContextArtifactId": str(materialized_artifact.id)
                if materialized_artifact is not None
                else None,
                "materializedArtifactIds": materialized_payload.get("artifactIds")
                if materialized_payload is not None and isinstance(materialized_payload.get("artifactIds"), dict)
                else None,
                "strategyBundleId": None,
                "strategyBundleType": None,
                "refreshed": False,
                "staleArtifactId": None,
                "missingArtifacts": ["skills_handoff"],
            }

        missing_roles = _skills_missing_roles(bundle_payload)
        ready = not missing_roles and materialized_payload is not None
        return {
            "provider": provider.value,
            "ready": ready,
            "checkedAt": _iso_now(),
            "reason": None
            if ready
            else (
                "Skills campaign creative context is incomplete."
                if missing_roles
                else "Skills campaign creative context has not been materialized for this campaign."
            ),
            "sourceStrategyV2WorkflowRunId": None,
            "sourceStrategyV2TemporalWorkflowId": None,
            "launchContextArtifactId": None,
            "manualCreativeContextArtifactId": None,
            "creativeContextArtifactId": str(aggregate_artifact.id) if aggregate_artifact is not None else None,
            "materializedCreativeContextArtifactId": str(materialized_artifact.id)
            if materialized_artifact is not None
            else None,
            "materializedArtifactIds": materialized_payload.get("artifactIds")
            if materialized_payload is not None and isinstance(materialized_payload.get("artifactIds"), dict)
            else None,
            "strategyBundleId": str(bundle_payload.get("id") or "") or None,
            "strategyBundleType": str(bundle_payload.get("bundleType") or "") or None,
            "refreshed": False,
            "staleArtifactId": None,
            "missingArtifacts": missing_roles if missing_roles else ([] if materialized_payload is not None else ["materialized_creative_context"]),
        }

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
        "creativeContextArtifactId": str(aggregate_artifact.id) if aggregate_artifact is not None else None,
        "materializedCreativeContextArtifactId": None,
        "materializedArtifactIds": None,
        "strategyBundleId": None,
        "strategyBundleType": None,
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
