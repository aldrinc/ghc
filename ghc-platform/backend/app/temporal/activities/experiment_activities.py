from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional
from uuid import uuid4

from temporalio import activity

from app.db.enums import ArtifactTypeEnum
from app.db.repositories.artifacts import ArtifactsRepository
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
                "required": ["id", "experimentId", "requirements"],
            },
        }
    },
    "required": ["asset_briefs"],
}


def _load_strategy(repo: ArtifactsRepository, org_id: str, campaign_id: str) -> Dict[str, Any]:
    artifact = repo.get_latest_by_type_for_campaign(
        org_id=org_id, campaign_id=campaign_id, artifact_type=ArtifactTypeEnum.strategy_sheet
    )
    return artifact.data if artifact else {}


def _load_metric(repo: ArtifactsRepository, org_id: str, client_id: str) -> Dict[str, Any]:
    artifact = repo.get_latest_by_type(org_id=org_id, client_id=client_id, artifact_type=ArtifactTypeEnum.metric_schema)
    return artifact.data if artifact else {}


def _load_canon(repo: ArtifactsRepository, org_id: str, client_id: str) -> Dict[str, Any]:
    artifact = repo.get_latest_by_type(org_id=org_id, client_id=client_id, artifact_type=ArtifactTypeEnum.client_canon)
    return artifact.data if artifact else {}


def _build_experiment_prompt(strategy: Dict[str, Any], metric: Dict[str, Any]) -> str:
    goal = strategy.get("goal") or strategy.get("objective", {}).get("description")
    hypothesis = strategy.get("hypothesis") or strategy.get("objective", {}).get("description")
    messaging = strategy.get("messaging") or strategy.get("positioning", {}).get("key_messages") or []
    channel_plan = strategy.get("channelPlan") or strategy.get("channel_roles") or []
    kpis = metric.get("kpis") or metric.get("metrics") or []
    return f"""
You are a media & experiment architect. Use the attached documents (strategy, canon, metric schema, precanon research) to propose 2-3 high-leverage experiments.

Context hints:
- Goal: {goal}
- Hypothesis: {hypothesis}
- Messaging/key messages: {messaging}
- Channel plan: {channel_plan}
- KPIs: {kpis}

Rules:
- Keep strings concise and actionable; no markdown.
- Include 2-3 variants per experiment with clear changes + channels.
- Map to metricIds that exist in the attached metric schema.
Return JSON only that conforms to the requested schema.
"""


@activity.defn
def build_experiment_specs_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    client_id = params["client_id"]
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

    with session_scope() as session:
        repo = ArtifactsRepository(session)
        strategy = _load_strategy(repo, org_id, campaign_id) if campaign_id else {}
        metric = _load_metric(repo, org_id, client_id)
        canon = _load_canon(repo, org_id, client_id)

    with session_scope() as session:
        ctx_repo = ClaudeContextFilesRepository(session)
        context_files = ctx_repo.list_for_generation_context(
            org_id=org_id,
            idea_workspace_id=idea_workspace_id,
            client_id=client_id,
            campaign_id=campaign_id,
        )

    if not context_files:
        raise RuntimeError(f"No Claude context files registered for workspace {idea_workspace_id}")

    def _has_prefix(prefix: str) -> bool:
        return any((cf.doc_key or "").startswith(prefix) for cf in context_files)

    missing_required = [p for p in ("strategy_sheet", "metric_schema", "client_canon") if not _has_prefix(p)]
    if missing_required:
        uploads_made = False
        if "strategy_sheet" in missing_required and strategy:
            strategy_bytes = json.dumps(strategy, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
            ensure_uploaded_to_claude(
                org_id=org_id,
                idea_workspace_id=idea_workspace_id,
                client_id=client_id,
                campaign_id=campaign_id,
                doc_key=f"strategy_sheet:{campaign_id or 'none'}",
                doc_title="Campaign Strategy Sheet",
                source_kind="strategy_sheet",
                step_key=None,
                filename="strategy_sheet.json",
                mime_type="text/plain",
                content_bytes=strategy_bytes,
                drive_doc_id=None,
                drive_url=None,
                allow_stub=allow_claude_stub,
            )
            uploads_made = True
        if "metric_schema" in missing_required and metric:
            metric_bytes = json.dumps(metric, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
            ensure_uploaded_to_claude(
                org_id=org_id,
                idea_workspace_id=idea_workspace_id,
                client_id=client_id,
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
                    campaign_id=campaign_id,
                )
            missing_required = [p for p in ("strategy_sheet", "metric_schema", "client_canon") if not _has_prefix(p)]
        if missing_required:
            raise RuntimeError(f"Missing required Claude context files: {missing_required}")

    documents = build_document_blocks(context_files)
    prompt = _build_experiment_prompt(strategy, metric)
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
def create_asset_briefs_for_experiments_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    client_id = params["client_id"]
    campaign_id = params.get("campaign_id")
    org_id = params["org_id"]
    experiments = params.get("experiment_specs") or []
    experiment_ids = params.get("experiment_ids") or []

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

    with session_scope() as session:
        ctx_repo = ClaudeContextFilesRepository(session)
        context_files = ctx_repo.list_for_generation_context(
            org_id=org_id,
            idea_workspace_id=idea_workspace_id,
            client_id=client_id,
            campaign_id=campaign_id,
        )
        artifacts_repo = ArtifactsRepository(session)
        canon = artifacts_repo.get_latest_by_type(
            org_id=org_id,
            client_id=client_id,
            artifact_type=ArtifactTypeEnum.client_canon,
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
                    artifact_type=ArtifactTypeEnum.experiment_spec,
                )
            )
            if latest_spec and isinstance(latest_spec.data, dict):
                candidates = latest_spec.data.get("experimentSpecs") or latest_spec.data.get("experiment_specs") or []
                experiments = [spec for spec in candidates if spec.get("id") in experiment_ids] or candidates

    if not experiments:
        raise RuntimeError("No experiment_specs provided for asset brief generation")

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
    prompt = f"""
You are a creative strategist. Using the experiment specs below and the attached canon/strategy/research documents, create precise creative asset briefs.

- Cover each experiment variant with at least one brief.
- Include 1-3 requirements per brief with channel + format + angle/hook and optional funnelStage.
- Respect tone guidelines and constraints if present; keep strings concise and production-ready.

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

    briefs: List[AssetBrief] = []
    brief_ids: List[str] = []
    for brief in briefs_raw:
        brief_id = brief.get("id") or str(uuid4())
        brief_obj = AssetBrief(
            id=brief_id,
            clientId=client_id,
            campaignId=campaign_id,
            experimentId=brief.get("experimentId"),
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
