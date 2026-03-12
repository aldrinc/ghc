from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from temporalio import activity

from app.db.base import session_scope
from app.db.enums import ArtifactTypeEnum
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.strategy_v2_launches import StrategyV2LaunchesRepository
from app.services.claude_files import ensure_uploaded_to_claude
from app.services.gemini_file_search import (
    ensure_uploaded_to_gemini_file_search,
    is_gemini_file_search_enabled,
)


def _coerce_uuid_string(value: Any, *, field_name: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return str(UUID(value.strip()))
    except ValueError as exc:
        raise RuntimeError(f"{field_name} must be a valid UUID string.") from exc


def _require_nonempty_string(value: Any, *, field_name: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise RuntimeError(f"{field_name} is required.")


def _require_string_list(value: Any, *, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise RuntimeError(f"{field_name} must be an array.")
    normalized: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            normalized.append(item.strip())
    if not normalized:
        raise RuntimeError(f"{field_name} must include at least one non-empty string.")
    return normalized


def _require_dict(value: Any, *, field_name: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    raise RuntimeError(f"{field_name} must be an object.")


def _build_experiment_spec_payload(
    *,
    angle_id: str,
    angle_name: str,
    selected_ums_id: str | None,
    selected_variant_id: str | None,
    channels: list[str],
) -> dict[str, Any]:
    experiment_id = f"exp-{angle_id}" if not selected_ums_id else f"exp-{angle_id}-{selected_ums_id}"
    variant_id = selected_variant_id or (f"var-{selected_ums_id}" if selected_ums_id else f"var-{angle_id}")
    variant_name = (
        f"{angle_name} · {selected_ums_id}"
        if selected_ums_id
        else f"{angle_name} · launch"
    )
    hypothesis = (
        f"{angle_name} will improve conversion for this campaign segment."
        if not selected_ums_id
        else f"{angle_name} with UMS {selected_ums_id} will improve conversion for this campaign segment."
    )
    return {
        "id": experiment_id,
        "name": angle_name,
        "hypothesis": hypothesis,
        "metricIds": ["conversion_rate"],
        "variants": [
            {
                "id": variant_id,
                "name": variant_name,
                "description": hypothesis,
                "channels": channels,
                "guardrails": [
                    "Use approved Strategy V2 template payloads only.",
                    "No unverified claims.",
                ],
            }
        ],
    }


def _build_asset_brief_payload(
    *,
    experiment: dict[str, Any],
    angle_name: str,
    selected_ums_id: str | None,
    channels: list[str],
    asset_brief_types: list[str],
) -> list[dict[str, Any]]:
    experiment_id = _require_nonempty_string(experiment.get("id"), field_name="experiment.id")
    variants = experiment.get("variants")
    if not isinstance(variants, list) or not variants:
        raise RuntimeError("experiment.variants must include at least one variant.")

    briefs: list[dict[str, Any]] = []
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        variant_id = _require_nonempty_string(variant.get("id"), field_name="variant.id")
        variant_name = _require_nonempty_string(variant.get("name"), field_name="variant.name")
        requirements: list[dict[str, Any]] = []
        for channel in channels:
            for brief_type in asset_brief_types:
                requirements.append(
                    {
                        "channel": channel,
                        "format": brief_type,
                        "angle": angle_name,
                        "hook": (
                            f"{angle_name} framed for {selected_ums_id}"
                            if selected_ums_id
                            else f"{angle_name} framed for launch intent"
                        ),
                        "funnelStage": "mid",
                    }
                )
        briefs.append(
            {
                "id": f"brief-{experiment_id}-{variant_id}",
                "experimentId": experiment_id,
                "variantId": variant_id,
                "variantName": variant_name,
                "creativeConcept": f"{angle_name} conversion creative",
                "requirements": requirements,
                "constraints": [
                    "Use approved claims only.",
                ],
                "toneGuidelines": ["Clear", "Specific", "Evidence-led"],
                "visualGuidelines": ["Keep hierarchy simple"],
            }
        )
    return briefs


def _build_launch_workspace_context_docs(
    *,
    campaign_id: str,
    source_stage3: dict[str, Any],
    source_offer: dict[str, Any],
    source_copy: dict[str, Any],
    source_copy_context: dict[str, Any],
    strategy_sheet: dict[str, Any],
    experiment_spec_payload: dict[str, Any],
    asset_brief_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        {
            "doc_key": "strategy_v2_stage3",
            "doc_title": "Strategy V2 Stage3",
            "source_kind": "strategy_v2_stage3",
            "payload": source_stage3,
        },
        {
            "doc_key": "strategy_v2_offer",
            "doc_title": "Strategy V2 Offer",
            "source_kind": "strategy_v2_offer",
            "payload": source_offer,
        },
        {
            "doc_key": "strategy_v2_copy",
            "doc_title": "Strategy V2 Copy",
            "source_kind": "strategy_v2_copy",
            "payload": source_copy,
        },
        {
            "doc_key": "strategy_v2_copy_context",
            "doc_title": "Strategy V2 Copy Context",
            "source_kind": "strategy_v2_copy_context",
            "payload": source_copy_context,
        },
        {
            "doc_key": f"strategy_sheet:{campaign_id}",
            "doc_title": "Strategy Sheet",
            "source_kind": "strategy_sheet",
            "payload": strategy_sheet,
        },
        {
            "doc_key": f"experiment_specs:{campaign_id}",
            "doc_title": "Experiment Specs",
            "source_kind": "experiment_specs",
            "payload": experiment_spec_payload,
        },
        {
            "doc_key": f"asset_briefs:{campaign_id}",
            "doc_title": "Asset Briefs",
            "source_kind": "asset_briefs",
            "payload": asset_brief_payload,
        },
    ]


def _persist_launch_workspace_context_docs(
    *,
    org_id: str,
    client_id: str,
    product_id: str,
    campaign_id: str,
    docs: list[dict[str, Any]],
    allow_claude_stub: bool,
) -> None:
    gemini_enabled = is_gemini_file_search_enabled()
    for doc in docs:
        payload = _require_dict(doc.get("payload"), field_name=f"{doc.get('doc_key')}.payload")
        doc_key = _require_nonempty_string(doc.get("doc_key"), field_name="doc_key")
        doc_title = _require_nonempty_string(doc.get("doc_title"), field_name=f"{doc_key}.doc_title")
        source_kind = _require_nonempty_string(doc.get("source_kind"), field_name=f"{doc_key}.source_kind")
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
            allow_stub=allow_claude_stub,
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


@activity.defn(name="strategy_v2_launch.create_launch_artifacts")
def create_strategy_v2_launch_artifacts_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = _require_nonempty_string(params.get("org_id"), field_name="org_id")
    client_id = _require_nonempty_string(params.get("client_id"), field_name="client_id")
    product_id = _require_nonempty_string(params.get("product_id"), field_name="product_id")
    campaign_id = _require_nonempty_string(params.get("campaign_id"), field_name="campaign_id")
    angle_id = _require_nonempty_string(params.get("angle_id"), field_name="angle_id")
    angle_name = _require_nonempty_string(params.get("angle_name"), field_name="angle_name")
    selected_ums_id_raw = params.get("selected_ums_id")
    selected_ums_id = selected_ums_id_raw.strip() if isinstance(selected_ums_id_raw, str) and selected_ums_id_raw.strip() else None
    selected_variant_id_raw = params.get("selected_variant_id")
    selected_variant_id = (
        selected_variant_id_raw.strip()
        if isinstance(selected_variant_id_raw, str) and selected_variant_id_raw.strip()
        else None
    )
    channels = _require_string_list(params.get("channels"), field_name="channels")
    asset_brief_types = _require_string_list(params.get("asset_brief_types"), field_name="asset_brief_types")
    allow_claude_stub = bool(params.get("allow_claude_stub", False))
    strategy_v2_packet = params.get("strategy_v2_packet")
    strategy_v2_packet = _require_dict(strategy_v2_packet, field_name="strategy_v2_packet")
    source_stage3 = _require_dict(params.get("source_stage3"), field_name="source_stage3")
    source_offer = _require_dict(params.get("source_offer"), field_name="source_offer")
    source_copy = _require_dict(params.get("source_copy"), field_name="source_copy")
    strategy_v2_copy_context = _require_dict(
        params.get("strategy_v2_copy_context"),
        field_name="strategy_v2_copy_context",
    )

    template_payloads = strategy_v2_packet.get("template_payloads")
    if not isinstance(template_payloads, dict):
        raise RuntimeError("strategy_v2_packet.template_payloads is required.")
    for template_id in ("pre-sales-listicle", "sales-pdp"):
        template_entry = template_payloads.get(template_id)
        if not isinstance(template_entry, dict):
            raise RuntimeError(f"strategy_v2_packet.template_payloads missing '{template_id}'.")
        patch_ops = template_entry.get("template_patch")
        if not isinstance(patch_ops, list) or not patch_ops:
            raise RuntimeError(f"strategy_v2 template payload for {template_id} is missing template_patch operations.")

    experiment = _build_experiment_spec_payload(
        angle_id=angle_id,
        angle_name=angle_name,
        selected_ums_id=selected_ums_id,
        selected_variant_id=selected_variant_id,
        channels=channels,
    )
    asset_briefs = _build_asset_brief_payload(
        experiment=experiment,
        angle_name=angle_name,
        selected_ums_id=selected_ums_id,
        channels=channels,
        asset_brief_types=asset_brief_types,
    )
    strategy_sheet = {
        "goal": "Launch approved Strategy V2 angle campaign.",
        "hypothesis": experiment.get("hypothesis"),
        "channelPlan": [
            {
                "channel": channel,
                "objective": "Acquire qualified traffic for approved angle test.",
                "notes": "Pinned to Strategy V2 approved copy payload.",
            }
            for channel in channels
        ],
        "messaging": [
            {
                "title": angle_name,
                "proofPoints": [
                    f"angle_id={angle_id}",
                    f"selected_ums_id={selected_ums_id}" if selected_ums_id else "selected_ums_id=primary",
                ],
            }
        ],
        "risks": ["Invalid claim usage", "Template mismatch"],
        "mitigations": ["Use template payload patches only", "Preserve Strategy V2 provenance"],
        "strategy_v2_provenance": {
            "angle_id": angle_id,
            "selected_ums_id": selected_ums_id,
            "selected_variant_id": selected_variant_id,
            "source": strategy_v2_packet.get("provenance"),
        },
    }

    created_by_user = params.get("created_by_user")
    created_by_user_value = created_by_user.strip() if isinstance(created_by_user, str) and created_by_user.strip() else None
    experiment_artifact_payload = {
        "experiment_specs": [experiment],
        "strategy_v2_packet": strategy_v2_packet,
        "strategy_v2_copy_context": strategy_v2_copy_context,
    }
    asset_brief_artifact_payload = {
        "asset_briefs": asset_briefs,
    }

    with session_scope() as session:
        artifacts_repo = ArtifactsRepository(session)
        strategy_sheet_artifact = artifacts_repo.insert(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            artifact_type=ArtifactTypeEnum.strategy_sheet,
            data=strategy_sheet,
            created_by_user=created_by_user_value,
        )
        strategy_sheet_artifact_id = str(strategy_sheet_artifact.id)
        experiment_artifact = artifacts_repo.insert(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            artifact_type=ArtifactTypeEnum.experiment_spec,
            data=experiment_artifact_payload,
            created_by_user=created_by_user_value,
        )
        experiment_spec_artifact_id = str(experiment_artifact.id)
        asset_brief_artifact = artifacts_repo.insert(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            artifact_type=ArtifactTypeEnum.asset_brief,
            data=asset_brief_artifact_payload,
            created_by_user=created_by_user_value,
        )
        asset_brief_artifact_id = str(asset_brief_artifact.id)

    # Seed the campaign workspace immediately so downstream copy-pack generation
    # can attach the canonical Strategy V2 context without a separate backfill step.
    _persist_launch_workspace_context_docs(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        docs=_build_launch_workspace_context_docs(
            campaign_id=campaign_id,
            source_stage3=source_stage3,
            source_offer=source_offer,
            source_copy=source_copy,
            source_copy_context=strategy_v2_copy_context,
            strategy_sheet=strategy_sheet,
            experiment_spec_payload=experiment_artifact_payload,
            asset_brief_payload=asset_brief_artifact_payload,
        ),
        allow_claude_stub=allow_claude_stub,
    )

    return {
        "strategy_sheet_artifact_id": strategy_sheet_artifact_id,
        "experiment_spec_artifact_id": experiment_spec_artifact_id,
        "asset_brief_artifact_id": asset_brief_artifact_id,
        "experiment_specs": [experiment],
        "asset_briefs": asset_briefs,
    }


@activity.defn(name="strategy_v2_launch.persist_launch_record")
def persist_strategy_v2_launch_record_activity(params: dict[str, Any]) -> dict[str, Any]:
    required_fields = (
        "org_id",
        "source_strategy_v2_workflow_run_id",
        "source_strategy_v2_temporal_workflow_id",
        "client_id",
        "product_id",
        "angle_id",
        "angle_run_id",
        "launch_type",
        "launch_key",
    )
    normalized: dict[str, Any] = {}
    for field_name in required_fields:
        normalized[field_name] = _require_nonempty_string(params.get(field_name), field_name=field_name)

    nullable_uuid_fields = (
        "campaign_id",
        "funnel_id",
        "source_stage3_artifact_id",
        "source_offer_artifact_id",
        "source_copy_artifact_id",
        "source_copy_context_artifact_id",
        "launch_workflow_run_id",
    )
    for field_name in nullable_uuid_fields:
        normalized[field_name] = _coerce_uuid_string(params.get(field_name), field_name=field_name)

    nullable_text_fields = (
        "selected_ums_id",
        "selected_variant_id",
        "launch_temporal_workflow_id",
        "created_by_user",
    )
    for field_name in nullable_text_fields:
        value = params.get(field_name)
        normalized[field_name] = value.strip() if isinstance(value, str) and value.strip() else None

    launch_index_raw = params.get("launch_index")
    if launch_index_raw is None:
        normalized["launch_index"] = None
    else:
        try:
            launch_index = int(launch_index_raw)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("launch_index must be an integer when provided.") from exc
        if launch_index < 1:
            raise RuntimeError("launch_index must be >= 1 when provided.")
        normalized["launch_index"] = launch_index

    with session_scope() as session:
        repo = StrategyV2LaunchesRepository(session)
        try:
            row = repo.create(**normalized)
        except IntegrityError:
            existing = repo.get_by_launch_key(
                org_id=normalized["org_id"],
                launch_key=normalized["launch_key"],
            )
            if existing is None:
                selected_ums_id = normalized.get("selected_ums_id")
                if isinstance(selected_ums_id, str) and selected_ums_id.strip():
                    existing = repo.get_by_angle_run_and_ums(
                        org_id=normalized["org_id"],
                        angle_run_id=normalized["angle_run_id"],
                        selected_ums_id=selected_ums_id,
                    )
            if existing is None:
                raise RuntimeError(
                    "Failed to persist launch record due to uniqueness conflict and no existing row was found."
                )
            return {
                "id": str(existing.id),
                "launch_key": existing.launch_key,
                "launch_type": existing.launch_type,
                "campaign_id": str(existing.campaign_id) if existing.campaign_id else None,
                "funnel_id": str(existing.funnel_id) if existing.funnel_id else None,
                "angle_id": existing.angle_id,
                "angle_run_id": existing.angle_run_id,
                "selected_ums_id": existing.selected_ums_id,
                "selected_variant_id": existing.selected_variant_id,
                "created_at": existing.created_at.isoformat(),
                "idempotent": True,
            }

        return {
            "id": str(row.id),
            "launch_key": row.launch_key,
            "launch_type": row.launch_type,
            "campaign_id": str(row.campaign_id) if row.campaign_id else None,
            "funnel_id": str(row.funnel_id) if row.funnel_id else None,
            "angle_id": row.angle_id,
            "angle_run_id": row.angle_run_id,
            "selected_ums_id": row.selected_ums_id,
            "selected_variant_id": row.selected_variant_id,
            "created_at": row.created_at.isoformat(),
            "idempotent": False,
        }
