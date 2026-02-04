from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional
from uuid import uuid4

from temporalio import activity

from app.db.enums import ArtifactTypeEnum
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.campaigns import CampaignsRepository
from app.db.repositories.claude_context_files import ClaudeContextFilesRepository
from app.db.base import session_scope
from app.schemas.experiment_spec import ExperimentSpecSet
from app.schemas.asset_brief import AssetBrief
from app.services.claude_files import (
    CLAUDE_DEFAULT_MODEL,
    build_document_blocks,
    call_claude_structured_message,
    ensure_uploaded_to_claude,
)


CLAUDE_EXPERIMENT_MODEL = os.getenv("CLAUDE_EXPERIMENT_MODEL", CLAUDE_DEFAULT_MODEL)
CLAUDE_ASSET_BRIEF_MODEL = os.getenv("CLAUDE_ASSET_BRIEF_MODEL", CLAUDE_DEFAULT_MODEL)
CLAUDE_STRUCTURED_MAX_TOKENS = int(os.getenv("CLAUDE_STRUCTURED_MAX_TOKENS", "4096"))


def _normalize_token(value: str) -> str:
    return " ".join(value.strip().lower().split())

EXPERIMENT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "experiments": {
            "type": "array",
            "minItems": 1,
            "maxItems": 4,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "hypothesis": {"type": "string"},
                    "metricIds": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "variants": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"},
                                "description": {"type": "string"},
                                "channels": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                                "guardrails": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["id", "name", "channels"],
                        },
                    },
                    "sampleSizeEstimate": {"type": "integer"},
                    "durationDays": {"type": "integer"},
                    "budgetEstimate": {"type": "number"},
                },
                "required": ["id", "name", "metricIds", "variants"],
            },
        }
    },
    "required": ["experiments"],
}

ASSET_BRIEFS_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "asset_briefs": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "experimentId": {"type": "string"},
                    "variantId": {"type": "string"},
                    "variantName": {"type": "string"},
                    "creativeConcept": {"type": "string"},
                    "requirements": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "channel": {"type": "string"},
                                "format": {"type": "string"},
                                "angle": {"type": "string"},
                                "hook": {"type": "string"},
                                "funnelStage": {"type": "string"},
                            },
                            "required": ["channel", "format"],
                        },
                    },
                    "constraints": {"type": "array", "items": {"type": "string"}},
                    "toneGuidelines": {"type": "array", "items": {"type": "string"}},
                    "visualGuidelines": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "experimentId", "variantId", "requirements"],
            },
        }
    },
    "required": ["asset_briefs"],
}


def _load_metric(repo: ArtifactsRepository, org_id: str, client_id: str, product_id: str) -> Dict[str, Any]:
    artifact = repo.get_latest_by_type(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        artifact_type=ArtifactTypeEnum.metric_schema,
    )
    return artifact.data if artifact else {}


def _load_canon(repo: ArtifactsRepository, org_id: str, client_id: str, product_id: str) -> Dict[str, Any]:
    artifact = repo.get_latest_by_type(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        artifact_type=ArtifactTypeEnum.client_canon,
    )
    return artifact.data if artifact else {}


def _build_experiment_prompt(
    metric: Dict[str, Any],
    campaign_channels: Optional[list[str]] = None,
    asset_brief_types: Optional[list[str]] = None,
) -> str:
    kpis = metric.get("kpis") or metric.get("metrics") or []
    channel_hint = ""
    format_hint = ""
    if campaign_channels:
        channel_hint = (
            f"\nCampaign channels (use ONLY these identifiers in variants): {campaign_channels}"
        )
    if asset_brief_types:
        format_hint = f"\nCreative brief types for this campaign: {asset_brief_types}"
    return f"""
You are a media & experiment architect. Use the attached client canon and metric schema (including any precanon research in canon) to propose 2-3 high-leverage experiments.

Context hints:
- KPIs: {kpis}
{channel_hint}{format_hint}

Rules:
- Keep strings concise and actionable; no markdown.
- Include 2-3 variants per experiment with clear changes + channels.
- Use only the campaign channels for each variant's channels list when provided.
- Map to metricIds that exist in the attached metric schema.
Return JSON only that conforms to the requested schema.
"""


@activity.defn
def build_experiment_specs_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    client_id = params["client_id"]
    product_id = params.get("product_id")
    campaign_id = params.get("campaign_id")
    idea_workspace_id = (
        params.get("idea_workspace_id")
        or params.get("workflow_id")
        or params.get("campaign_id")
        or params.get("client_id")
    )
    if not idea_workspace_id:
        idea_workspace_id = f"client-{client_id}"
    allow_claude_stub = bool(params.get("allow_claude_stub", False))
    model = params.get("model") or CLAUDE_EXPERIMENT_MODEL
    if not product_id:
        raise RuntimeError("product_id is required to generate experiment specs.")

    campaign_channels: Optional[list[str]] = None
    asset_brief_types: Optional[list[str]] = None
    with session_scope() as session:
        repo = ArtifactsRepository(session)
        metric = _load_metric(repo, org_id, client_id, product_id)
        canon = _load_canon(repo, org_id, client_id, product_id)
        if campaign_id:
            campaigns_repo = CampaignsRepository(session)
            campaign = campaigns_repo.get(org_id=org_id, campaign_id=campaign_id)
            if not campaign:
                raise RuntimeError(f"Campaign not found for experiment generation: {campaign_id}")
            campaign_channels = [
                str(ch).strip() for ch in (campaign.channels or []) if isinstance(ch, str) and ch.strip()
            ]
            asset_brief_types = [
                str(t).strip() for t in (campaign.asset_brief_types or []) if isinstance(t, str) and t.strip()
            ]
            if not campaign_channels:
                raise RuntimeError("Campaign has no channels configured; update the campaign before generating angles.")
            if not asset_brief_types:
                raise RuntimeError(
                    "Campaign has no creative brief types configured; update the campaign before generating angles."
                )

    available_metrics = (
        metric.get("primaryKpis")
        or metric.get("primary_kpis")
        or metric.get("secondaryKpis")
        or metric.get("secondary_kpis")
        or metric.get("kpis")
        or metric.get("metrics")
        or []
    )
    if not available_metrics:
        raise RuntimeError("Metric schema has no KPI definitions; update metric schema before generating experiments.")

    with session_scope() as session:
        ctx_repo = ClaudeContextFilesRepository(session)
        context_files = ctx_repo.list_for_generation_context(
            org_id=org_id,
            idea_workspace_id=idea_workspace_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
        )

    context_files = [
        cf for cf in context_files if not (cf.doc_key or "").startswith("strategy_sheet")
    ]

    if not context_files:
        raise RuntimeError(
            f"No eligible Claude context files registered for workspace {idea_workspace_id}; "
            "client_canon and metric_schema are required."
        )

    def _has_prefix(prefix: str) -> bool:
        return any((cf.doc_key or "").startswith(prefix) for cf in context_files)

    missing_required = [p for p in ("metric_schema", "client_canon") if not _has_prefix(p)]
    if missing_required:
        uploads_made = False
        if "metric_schema" in missing_required and metric:
            metric_bytes = json.dumps(metric, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
            ensure_uploaded_to_claude(
                org_id=org_id,
                idea_workspace_id=idea_workspace_id,
                client_id=client_id,
                product_id=product_id,
                campaign_id=campaign_id,
                doc_key="metric_schema",
                doc_title="Metric Schema",
                source_kind="metric_schema",
                step_key=None,
                filename="metric_schema.json",
                mime_type="text/plain",
                content_bytes=metric_bytes,
                drive_doc_id=None,
                drive_url=None,
                allow_stub=allow_claude_stub,
            )
            uploads_made = True
        if "client_canon" in missing_required and canon:
            canon_bytes = json.dumps(canon, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
            ensure_uploaded_to_claude(
                org_id=org_id,
                idea_workspace_id=idea_workspace_id,
                client_id=client_id,
                product_id=product_id,
                campaign_id=campaign_id,
                doc_key="client_canon",
                doc_title="Client Canon",
                source_kind="client_canon",
                step_key=None,
                filename="client_canon.json",
                mime_type="text/plain",
                content_bytes=canon_bytes,
                drive_doc_id=None,
                drive_url=None,
                allow_stub=allow_claude_stub,
            )
            uploads_made = True
        if uploads_made:
            with session_scope() as session:
                ctx_repo = ClaudeContextFilesRepository(session)
                context_files = ctx_repo.list_for_generation_context(
                    org_id=org_id,
                    idea_workspace_id=idea_workspace_id,
                    client_id=client_id,
                    product_id=product_id,
                    campaign_id=campaign_id,
                )
            missing_required = [p for p in ("metric_schema", "client_canon") if not _has_prefix(p)]
        if missing_required:
            raise RuntimeError(f"Missing required Claude context files: {missing_required}")

    documents = build_document_blocks(context_files)
    prompt = _build_experiment_prompt(metric, campaign_channels, asset_brief_types)
    user_content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}, *documents]
    claude_response = call_claude_structured_message(
        model=model,
        system="Generate sharp, testable marketing experiments grounded in the attached context. Return JSON only.",
        user_content=user_content,
        output_schema=EXPERIMENT_SCHEMA,
        max_tokens=CLAUDE_STRUCTURED_MAX_TOKENS,
        temperature=0.2,
    )
    parsed = claude_response.get("parsed") or {}
    experiments = parsed.get("experiments") if isinstance(parsed, dict) else None

    if not experiments:
        raise RuntimeError("Claude did not return any experiments")

    missing_experiment_fields: list[str] = []
    invalid_channels: set[str] = set()
    allowed_channels = {_normalize_token(ch) for ch in campaign_channels or []}
    for exp in experiments:
        if not isinstance(exp, dict):
            missing_experiment_fields.append("experiment_object")
            continue
        if not exp.get("id") or not exp.get("name"):
            missing_experiment_fields.append("experiment_id_or_name")
        variants = exp.get("variants") or []
        if not isinstance(variants, list) or not variants:
            missing_experiment_fields.append("variants")
            continue
        for variant in variants:
            if not isinstance(variant, dict):
                missing_experiment_fields.append("variant_object")
                continue
            if not variant.get("id") or not variant.get("name"):
                missing_experiment_fields.append("variant_id_or_name")
            if not variant.get("description"):
                missing_experiment_fields.append("variant_description")
            channels = variant.get("channels") or []
            if not isinstance(channels, list) or not channels:
                missing_experiment_fields.append("variant_channels")
            if campaign_channels and isinstance(channels, list):
                for channel in channels:
                    if not isinstance(channel, str) or _normalize_token(channel) not in allowed_channels:
                        invalid_channels.add(str(channel))
        metric_ids = exp.get("metricIds") or []
        if not isinstance(metric_ids, list) or not metric_ids:
            missing_experiment_fields.append("metricIds")
    if invalid_channels:
        invalid_list = ", ".join(sorted(invalid_channels))
        raise RuntimeError(
            f"Experiment spec variants include unsupported channels: {invalid_list}. "
            f"Allowed channels: {campaign_channels}."
        )
    if missing_experiment_fields:
        unique_missing = sorted(set(missing_experiment_fields))
        raise RuntimeError(
            f"Experiment spec generation missing required fields: {', '.join(unique_missing)}"
        )

    specs = ExperimentSpecSet(
        clientId=client_id,
        campaignId=campaign_id,
        experimentSpecs=experiments,  # type: ignore[arg-type]
    )
    data_out = specs.model_dump()
    data_out["rawPrompt"] = prompt
    data_out["claudeResponse"] = claude_response.get("raw")
    with session_scope() as session:
        repo = ArtifactsRepository(session)
        repo.insert(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            artifact_type=ArtifactTypeEnum.experiment_spec,
            data=data_out,
        )
    experiments_bytes = json.dumps(data_out, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    experiments_doc_key = f"experiment_specs:{campaign_id or 'none'}"
    experiments_file_id = ensure_uploaded_to_claude(
        org_id=org_id,
        idea_workspace_id=idea_workspace_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        doc_key=experiments_doc_key,
        doc_title="Experiment Specs",
        source_kind="experiment_specs",
        step_key=None,
        filename=f"{experiments_doc_key}.json",
        mime_type="text/plain",
        content_bytes=experiments_bytes,
        drive_doc_id=None,
        drive_url=None,
        allow_stub=allow_claude_stub,
    )
    data_out["claudeFileId"] = experiments_file_id
    return {"experiment_specs": experiments, "claude_file_id": experiments_file_id}


@activity.defn
def fetch_experiment_specs_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    campaign_id = params.get("campaign_id")
    experiment_ids = params.get("experiment_ids") or []

    if not campaign_id:
        raise RuntimeError("campaign_id is required to fetch experiment specs.")

    with session_scope() as session:
        repo = ArtifactsRepository(session)
        latest_spec = repo.get_latest_by_type_for_campaign(
            org_id=org_id,
            campaign_id=campaign_id,
            artifact_type=ArtifactTypeEnum.experiment_spec,
        )
        if not latest_spec or not isinstance(latest_spec.data, dict):
            raise RuntimeError("Experiment specs not found for this campaign.")
        candidates = latest_spec.data.get("experimentSpecs") or latest_spec.data.get("experiment_specs") or []

    if experiment_ids:
        filtered = [spec for spec in candidates if isinstance(spec, dict) and spec.get("id") in experiment_ids]
    else:
        filtered = [spec for spec in candidates if isinstance(spec, dict)]

    if not filtered:
        raise RuntimeError("No experiment specs matched the selected angles.")

    return {"experiment_specs": filtered}


@activity.defn
def create_asset_briefs_for_experiments_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    client_id = params["client_id"]
    campaign_id = params.get("campaign_id")
    org_id = params["org_id"]
    product_id = params.get("product_id")
    experiments = params.get("experiment_specs") or []
    experiment_ids = params.get("experiment_ids") or []
    funnel_map = params.get("funnel_map") or {}

    idea_workspace_id = (
        params.get("idea_workspace_id")
        or params.get("workflow_id")
        or params.get("campaign_id")
        or params.get("client_id")
    )
    if not idea_workspace_id:
        idea_workspace_id = f"client-{client_id}"
    allow_claude_stub = bool(params.get("allow_claude_stub", False))
    model = params.get("model") or CLAUDE_ASSET_BRIEF_MODEL
    if not product_id:
        raise RuntimeError("product_id is required to generate asset briefs.")

    campaign_channels: Optional[list[str]] = None
    asset_brief_types: Optional[list[str]] = None
    with session_scope() as session:
        ctx_repo = ClaudeContextFilesRepository(session)
        context_files = ctx_repo.list_for_generation_context(
            org_id=org_id,
            idea_workspace_id=idea_workspace_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
        )
        artifacts_repo = ArtifactsRepository(session)
        canon = artifacts_repo.get_latest_by_type(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            artifact_type=ArtifactTypeEnum.client_canon,
        )
        if campaign_id:
            campaigns_repo = CampaignsRepository(session)
            campaign = campaigns_repo.get(org_id=org_id, campaign_id=campaign_id)
            if not campaign:
                raise RuntimeError(f"Campaign not found for asset brief generation: {campaign_id}")
            campaign_channels = [
                str(ch).strip() for ch in (campaign.channels or []) if isinstance(ch, str) and ch.strip()
            ]
            asset_brief_types = [
                str(t).strip() for t in (campaign.asset_brief_types or []) if isinstance(t, str) and t.strip()
            ]
            if not campaign_channels:
                raise RuntimeError("Campaign has no channels configured; update the campaign before creating briefs.")
            if not asset_brief_types:
                raise RuntimeError(
                    "Campaign has no creative brief types configured; update the campaign before creating briefs."
                )
        if not experiments and experiment_ids:
            latest_spec = (
                artifacts_repo.get_latest_by_type_for_campaign(
                    org_id=org_id,
                    campaign_id=campaign_id,
                    artifact_type=ArtifactTypeEnum.experiment_spec,
                )
                if campaign_id
                else artifacts_repo.get_latest_by_type(
                    org_id=org_id,
                    client_id=client_id,
                    product_id=product_id,
                    artifact_type=ArtifactTypeEnum.experiment_spec,
                )
            )
            if latest_spec and isinstance(latest_spec.data, dict):
                candidates = latest_spec.data.get("experimentSpecs") or latest_spec.data.get("experiment_specs") or []
                experiments = [spec for spec in candidates if spec.get("id") in experiment_ids] or candidates

    if not experiments:
        raise RuntimeError("No experiment_specs provided for asset brief generation")

    if funnel_map and not isinstance(funnel_map, dict):
        raise RuntimeError("funnel_map must be a dictionary of experimentId:variantId -> funnelId")

    if not context_files:
        raise RuntimeError(f"No Claude context files registered for workspace {idea_workspace_id}")

    tone_guidelines = []
    constraints = []
    if canon and isinstance(canon.data, dict):
        tone = canon.data.get("brand", {}).get("toneOfVoice") or canon.data.get("tone_of_voice")
        if tone:
            tone_guidelines = (tone.get("do") or []) + (tone.get("dont") or [])
        cons = canon.data.get("constraints") or {}
        constraints = cons.get("brand") or cons.get("legal") or []

    documents = build_document_blocks(context_files)
    experiments_json = json.dumps({"experiments": experiments}, ensure_ascii=True, indent=2)
    channel_hint = ""
    format_hint = ""
    if campaign_channels:
        channel_hint = f"Allowed channels (use ONLY these identifiers): {campaign_channels}"
    if asset_brief_types:
        format_hint = f"Allowed formats (use ONLY these identifiers): {asset_brief_types}"
    prompt = f"""
You are a creative strategist. Using the experiment specs below and the attached canon/strategy/research documents, create precise creative asset briefs.

- Cover each experiment variant with at least one brief.
- Include variantId (must match the experiment variant id) and variantName for each brief.
- Include 1-3 requirements per brief with channel + format + angle/hook and optional funnelStage.
- Respect tone guidelines and constraints if present; keep strings concise and production-ready.
{channel_hint}
{format_hint}

Experiment specs (inline):
{experiments_json}

Known tone guidelines: {tone_guidelines}
Known constraints: {constraints}

Return JSON that matches the asset_briefs schema.
"""
    user_content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}, *documents]
    claude_response = call_claude_structured_message(
        model=model,
        system="Generate actionable creative briefs that align with the attached context and experiment goals.",
        user_content=user_content,
        output_schema=ASSET_BRIEFS_SCHEMA,
        max_tokens=CLAUDE_STRUCTURED_MAX_TOKENS,
        temperature=0.4,
    )
    parsed = claude_response.get("parsed") or {}
    briefs_raw = parsed.get("asset_briefs") if isinstance(parsed, dict) else None
    if not briefs_raw:
        raise RuntimeError("Claude did not return any asset_briefs")

    invalid_channels: set[str] = set()
    invalid_formats: set[str] = set()
    allowed_channels = {_normalize_token(ch) for ch in campaign_channels or []}
    allowed_formats = {_normalize_token(fmt) for fmt in asset_brief_types or []}
    for brief in briefs_raw:
        requirements = brief.get("requirements") or []
        if not isinstance(requirements, list):
            continue
        for req in requirements:
            if not isinstance(req, dict):
                continue
            if campaign_channels:
                channel_value = req.get("channel")
                if not isinstance(channel_value, str) or _normalize_token(channel_value) not in allowed_channels:
                    invalid_channels.add(str(channel_value))
            if asset_brief_types:
                format_value = req.get("format")
                if not isinstance(format_value, str) or _normalize_token(format_value) not in allowed_formats:
                    invalid_formats.add(str(format_value))
    if invalid_channels:
        invalid_list = ", ".join(sorted(invalid_channels))
        raise RuntimeError(
            f"Asset brief requirements include unsupported channels: {invalid_list}. "
            f"Allowed channels: {campaign_channels}."
        )
    if invalid_formats:
        invalid_list = ", ".join(sorted(invalid_formats))
        raise RuntimeError(
            f"Asset brief requirements include unsupported formats: {invalid_list}. "
            f"Allowed formats: {asset_brief_types}."
        )

    briefs: List[AssetBrief] = []
    brief_ids: List[str] = []
    for brief in briefs_raw:
        brief_id = brief.get("id") or str(uuid4())
        variant_id = brief.get("variantId") or brief.get("variant_id")
        if not variant_id:
            raise RuntimeError("Asset brief generation missing variantId.")
        experiment_id = brief.get("experimentId")
        if funnel_map:
            if not experiment_id:
                raise RuntimeError("Asset brief generation missing experimentId for funnel mapping.")
            funnel_key = f"{experiment_id}:{variant_id}"
            funnel_id = funnel_map.get(funnel_key)
            if not funnel_id:
                raise RuntimeError(f"Funnel mapping missing for {funnel_key}.")
            brief["funnelId"] = funnel_id
        brief_obj = AssetBrief(
            id=brief_id,
            clientId=client_id,
            campaignId=campaign_id,
            experimentId=experiment_id,
            variantId=variant_id,
            funnelId=brief.get("funnelId"),
            variantName=brief.get("variantName") or brief.get("variant_name"),
            creativeConcept=brief.get("creativeConcept"),
            requirements=brief.get("requirements") or [],  # type: ignore[arg-type]
            constraints=brief.get("constraints") or constraints,
            toneGuidelines=brief.get("toneGuidelines") or tone_guidelines,
            visualGuidelines=brief.get("visualGuidelines") or [],
        )
        briefs.append(brief_obj)
        brief_ids.append(brief_id)

    data_out = [b.model_dump() for b in briefs]
    payload_to_store = {"asset_briefs": data_out, "rawPrompt": prompt, "claudeResponse": claude_response.get("raw")}
    with session_scope() as session:
        repo = ArtifactsRepository(session)
        repo.insert(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            artifact_type=ArtifactTypeEnum.asset_brief,
            data=payload_to_store,
        )

    briefs_bytes = json.dumps(payload_to_store, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    briefs_doc_key = f"asset_briefs:{campaign_id or 'none'}"
    claude_file_id = ensure_uploaded_to_claude(
        org_id=org_id,
        idea_workspace_id=idea_workspace_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        doc_key=briefs_doc_key,
        doc_title="Asset Briefs",
        source_kind="asset_briefs",
        step_key=None,
        filename=f"{briefs_doc_key}.json",
        mime_type="text/plain",
        content_bytes=briefs_bytes,
        drive_doc_id=None,
        drive_url=None,
        allow_stub=allow_claude_stub,
    )

    return {"asset_brief_ids": brief_ids, "briefs": data_out, "claude_file_id": claude_file_id}
