from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional, Tuple

from temporalio import activity

from app.db.enums import ArtifactTypeEnum
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.base import session_scope
from app.schemas.strategy_sheet import StrategySheet
from app.llm import LLMClient, LLMGenerationParams
from app.services.claude_files import ensure_uploaded_to_claude


DEFAULT_LLM_MODEL = os.getenv("LLM_DEFAULT_MODEL", "gpt-5.2-2025-12-11")


def _load_artifact(repo: ArtifactsRepository, org_id: str, client_id: str, kind: ArtifactTypeEnum) -> Optional[Dict]:
    artifact = repo.get_latest_by_type(org_id=org_id, client_id=client_id, artifact_type=kind)
    return artifact.data if artifact else None


def _build_prompt(canon: Dict[str, Any], metric: Dict[str, Any], campaign_id: Optional[str]) -> str:
    story = (canon.get("brand", {}) or {}).get("story") or "Unknown brand story"
    research = canon.get("research_highlights") or canon.get("precanon_research", {})
    step_summaries = research.get("step_summaries") if isinstance(research, dict) else {}
    icps = (canon.get("icps") or []) if isinstance(canon, dict) else []
    markets = metric.get("primaryMarkets") or metric.get("primary_markets") or []

    return f"""
You are a performance marketing strategist. Create a concise campaign strategy JSON for this client.

Brand story: {story}
Primary markets: {markets}
ICP (if any): {icps}
Research summaries: {step_summaries}
Campaign ID: {campaign_id}

Return ONLY compact JSON with keys:
  goal (string)
  hypothesis (string)
  channelPlan (list of up to 4 objects with channel, objective, budgetSplitPercent, notes)
  messaging (list of up to 4 pillars with title, proofPoints, targetSegments)
  risks (list of strings)
  mitigations (list of strings)
Keep each string under 240 characters. Avoid markdown.
"""


def _parse_json(text: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(text)
    except Exception:
        return None


@activity.defn
def build_strategy_sheet_activity(params: Dict[str, Any]) -> Dict[str, Any]:
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

    with session_scope() as session:
        repo = ArtifactsRepository(session)
        canon = _load_artifact(repo, org_id, client_id, ArtifactTypeEnum.client_canon) or {}
        metric = _load_artifact(repo, org_id, client_id, ArtifactTypeEnum.metric_schema) or {}

    def _upload_context(doc: Dict[str, Any], *, doc_key: str, title: str, source_kind: str) -> Optional[str]:
        if not doc:
            return None
        content_bytes = json.dumps(doc, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        return ensure_uploaded_to_claude(
            org_id=org_id,
            idea_workspace_id=idea_workspace_id or "",
            client_id=client_id,
            campaign_id=campaign_id,
            doc_key=doc_key,
            doc_title=title,
            source_kind=source_kind,
            step_key=None,
            filename=f"{doc_key}.json",
            mime_type="text/plain",
            content_bytes=content_bytes,
            drive_doc_id=None,
            drive_url=None,
            allow_stub=allow_claude_stub,
        )

    canon_file_id = _upload_context(canon, doc_key="client_canon", title="Client Canon", source_kind="client_canon")
    metric_file_id = _upload_context(metric, doc_key="metric_schema", title="Metric Schema", source_kind="metric_schema")

    llm = LLMClient()
    prompt = _build_prompt(canon, metric, campaign_id)
    raw = llm.generate_text(prompt, LLMGenerationParams(model=DEFAULT_LLM_MODEL))
    parsed = _parse_json(raw) or {}

    def _fallback_goal() -> Tuple[str, str]:
        story = (canon.get("brand", {}) or {}).get("story") or ""
        market = (metric.get("primaryMarkets") or metric.get("primary_markets") or ["target market"])[0]
        goal = f"Prove traction in {market} with a focused launch campaign."
        hypothesis = "If we target the highest intent segment with tight creative messaging, we can hit early CAC benchmarks."
        if story:
            goal = f"Launch campaign grounded in brand story: {story[:140]}"
        return goal, hypothesis

    goal, hypothesis = _fallback_goal()
    if isinstance(parsed, dict):
        goal = parsed.get("goal") or goal
        hypothesis = parsed.get("hypothesis") or hypothesis

    channel_plan = parsed.get("channelPlan") if isinstance(parsed, dict) else None
    messaging = parsed.get("messaging") if isinstance(parsed, dict) else None
    if messaging and isinstance(messaging, list):
        normalized = []
        for pillar in messaging:
            if not isinstance(pillar, dict):
                continue
            proof = pillar.get("proofPoints")
            if isinstance(proof, str):
                proof = [proof]
            elif not isinstance(proof, list):
                proof = []
            targets = pillar.get("targetSegments")
            if isinstance(targets, str):
                targets = [targets]
            elif not isinstance(targets, list):
                targets = []
            pillar["proofPoints"] = proof
            pillar["targetSegments"] = targets
            normalized.append(pillar)
        messaging = normalized
    risks = parsed.get("risks") if isinstance(parsed, dict) else None
    mitigations = parsed.get("mitigations") if isinstance(parsed, dict) else None

    strategy = StrategySheet(
        clientId=client_id,
        campaignId=campaign_id,
        goal=goal,
        hypothesis=hypothesis,
        channelPlan=channel_plan or [],
        messaging=messaging or [],
        risks=risks or [],
        mitigations=mitigations or [],
    )

    data_out = strategy.model_dump()
    data_out["inputs"] = {
        "client_canon_present": bool(canon),
        "metric_schema_present": bool(metric),
    }
    data_out["rawPrompt"] = prompt

    with session_scope() as session:
        repo = ArtifactsRepository(session)
        repo.insert(
            org_id=org_id,
            client_id=client_id,
            campaign_id=campaign_id,
            artifact_type=ArtifactTypeEnum.strategy_sheet,
            data=data_out,
        )

    strategy_bytes = json.dumps(data_out, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    strategy_doc_key = f"strategy_sheet:{campaign_id or 'none'}"
    strategy_file_id = ensure_uploaded_to_claude(
        org_id=org_id,
        idea_workspace_id=idea_workspace_id or "",
        client_id=client_id,
        campaign_id=campaign_id,
        doc_key=strategy_doc_key,
        doc_title="Campaign Strategy Sheet",
        source_kind="strategy_sheet",
        step_key=None,
        filename=f"{strategy_doc_key}.json",
        mime_type="text/plain",
        content_bytes=strategy_bytes,
        drive_doc_id=None,
        drive_url=None,
        allow_stub=allow_claude_stub,
    )

    data_out["claudeFileId"] = strategy_file_id
    data_out["claudeContext"] = {
        "idea_workspace_id": idea_workspace_id,
        "canon_file_id": canon_file_id,
        "metric_file_id": metric_file_id,
        "strategy_file_id": strategy_file_id,
    }
    return data_out
