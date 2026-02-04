from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from temporalio import activity

from app.db.enums import ArtifactTypeEnum
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.campaigns import CampaignsRepository
from app.db.base import session_scope
from app.schemas.strategy_sheet import StrategySheet
from app.services.claude_files import CLAUDE_DEFAULT_MODEL, call_claude_structured_message, ensure_uploaded_to_claude


CLAUDE_STRATEGY_MODEL = os.getenv("CLAUDE_STRATEGY_MODEL", CLAUDE_DEFAULT_MODEL)
CLAUDE_STRUCTURED_MAX_TOKENS = int(os.getenv("CLAUDE_STRUCTURED_MAX_TOKENS", "4096"))

def _build_strategy_schema(channel_count: int) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "goal": {"type": "string"},
            "hypothesis": {"type": "string"},
            "channelPlan": {
                "type": "array",
                "minItems": channel_count,
                "maxItems": channel_count,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "channel": {"type": "string"},
                        "objective": {"type": "string"},
                        "budgetSplitPercent": {"type": "number"},
                        "notes": {"type": "string"},
                    },
                    "required": ["channel", "objective", "budgetSplitPercent"],
                },
            },
            "messaging": {
                "type": "array",
                "minItems": 3,
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "proofPoints": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["title", "proofPoints"],
                },
            },
            "risks": {"type": "array", "minItems": 2, "items": {"type": "string"}},
            "mitigations": {"type": "array", "minItems": 2, "items": {"type": "string"}},
        },
        "required": ["goal", "hypothesis", "channelPlan", "messaging", "risks", "mitigations"],
    }


def _normalize_token(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _load_artifact(
    repo: ArtifactsRepository, org_id: str, client_id: str, product_id: str, kind: ArtifactTypeEnum
) -> Optional[Dict]:
    artifact = repo.get_latest_by_type(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        artifact_type=kind,
    )
    return artifact.data if artifact else None


def _resolve_research_summaries(canon: Dict[str, Any]) -> Dict[str, Any]:
    precanon = canon.get("precanon_research")
    if isinstance(precanon, dict):
        step_summaries = precanon.get("step_summaries")
        if isinstance(step_summaries, dict) and step_summaries:
            return step_summaries
    highlights = canon.get("research_highlights")
    if isinstance(highlights, dict):
        return highlights
    return {}


def _build_prompt(
    canon: Dict[str, Any],
    metric: Dict[str, Any],
    campaign_id: Optional[str],
    campaign_channels: Optional[list[str]] = None,
    asset_brief_types: Optional[list[str]] = None,
) -> str:
    brand = canon.get("brand", {}) or {}
    story = brand.get("story") or brand.get("mission") or "Unknown brand story"
    values = brand.get("values") or []
    manifesto = brand.get("manifesto") or ""
    tone = brand.get("toneOfVoice") or brand.get("tone_of_voice") or {}
    voice_of_customer = canon.get("voiceOfCustomer") or {}
    content_patterns = canon.get("contentPatterns") or {}
    constraints = canon.get("constraints") or {}

    research_summaries = _resolve_research_summaries(canon)
    primary_kpis = metric.get("primaryKpis") or metric.get("primary_kpis") or []
    secondary_kpis = metric.get("secondaryKpis") or metric.get("secondary_kpis") or []

    channel_constraint = "Channel constraint: Facebook Ads only."
    channel_plan_rule = "channelPlan (list of 1 object for Facebook Ads only with channel, objective, budgetSplitPercent, notes)"
    asset_brief_hint = ""
    if campaign_channels:
        channel_constraint = (
            "Channel constraints: Use ONLY these channels, exactly as listed: "
            f"{campaign_channels}"
        )
        channel_plan_rule = (
            "channelPlan (list of one object per campaign channel in the exact identifiers "
            f"{campaign_channels}, with channel, objective, budgetSplitPercent, notes)"
        )
        if asset_brief_types:
            asset_brief_hint = f"Creative brief types for this campaign: {asset_brief_types}"

    return f"""
You are a performance marketing strategist. Create a detailed campaign strategy JSON for this client.

Brand story: {story}
Brand values: {values}
Manifesto (if any): {manifesto}
Tone of voice: {tone}
Voice of customer: {voice_of_customer}
Content patterns: {content_patterns}
Constraints: {constraints}
Primary KPIs: {primary_kpis}
Secondary KPIs: {secondary_kpis}
Research summaries: {research_summaries}
Campaign ID: {campaign_id}
{channel_constraint}
{asset_brief_hint}

Return ONLY JSON with keys:
  goal (string)
  hypothesis (string)
  {channel_plan_rule}
  messaging (list of 3-4 pillars with title, proofPoints)
  risks (list of at least 2 strings)
  mitigations (list of at least 2 strings)
Keep each string under 240 characters. Avoid markdown.
Do not include any demographic or targeting details anywhere in the output.
"""


@activity.defn
def build_strategy_sheet_activity(params: Dict[str, Any]) -> Dict[str, Any]:
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
    if not product_id:
        raise ValueError("product_id is required to build a strategy sheet")

    campaign_channels: Optional[list[str]] = None
    asset_brief_types: Optional[list[str]] = None
    with session_scope() as session:
        repo = ArtifactsRepository(session)
        canon = _load_artifact(repo, org_id, client_id, product_id, ArtifactTypeEnum.client_canon) or {}
        metric = _load_artifact(repo, org_id, client_id, product_id, ArtifactTypeEnum.metric_schema) or {}
        if campaign_id:
            campaigns_repo = CampaignsRepository(session)
            campaign = campaigns_repo.get(org_id=org_id, campaign_id=campaign_id)
            if not campaign:
                raise RuntimeError(f"Campaign not found for strategy generation: {campaign_id}")
            campaign_channels = [
                str(ch).strip() for ch in (campaign.channels or []) if isinstance(ch, str) and ch.strip()
            ]
            asset_brief_types = [
                str(t).strip() for t in (campaign.asset_brief_types or []) if isinstance(t, str) and t.strip()
            ]
            if not campaign_channels:
                raise RuntimeError("Campaign has no channels configured; update the campaign before planning.")
            if not asset_brief_types:
                raise RuntimeError(
                    "Campaign has no creative brief types configured; update the campaign before planning."
                )

    def _upload_context(doc: Dict[str, Any], *, doc_key: str, title: str, source_kind: str) -> Optional[str]:
        if not doc:
            return None
        content_bytes = json.dumps(doc, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        return ensure_uploaded_to_claude(
            org_id=org_id,
            idea_workspace_id=idea_workspace_id or "",
            client_id=client_id,
            product_id=product_id,
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

    prompt = _build_prompt(canon, metric, campaign_id, campaign_channels, asset_brief_types)
    strategy_schema = _build_strategy_schema(len(campaign_channels) if campaign_channels else 1)
    claude_response = call_claude_structured_message(
        model=CLAUDE_STRATEGY_MODEL,
        system="Generate a concrete, decision-ready campaign strategy. Return JSON only.",
        user_content=[{"type": "text", "text": prompt}],
        output_schema=strategy_schema,
        max_tokens=CLAUDE_STRUCTURED_MAX_TOKENS,
        temperature=0.2,
    )
    parsed = claude_response.get("parsed")
    if not isinstance(parsed, dict):
        raise RuntimeError("Strategy sheet generation returned invalid JSON")

    goal = parsed.get("goal")
    hypothesis = parsed.get("hypothesis")
    channel_plan = parsed.get("channelPlan")
    messaging = parsed.get("messaging")
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
            pillar["proofPoints"] = proof
            normalized.append(pillar)
        messaging = normalized
    risks = parsed.get("risks")
    mitigations = parsed.get("mitigations")

    missing_sections = []
    if not isinstance(goal, str) or not goal.strip():
        missing_sections.append("goal")
    if not isinstance(hypothesis, str) or not hypothesis.strip():
        missing_sections.append("hypothesis")
    if not isinstance(channel_plan, list) or not channel_plan:
        missing_sections.append("channelPlan")
    if not isinstance(messaging, list) or not messaging:
        missing_sections.append("messaging")
    if not isinstance(risks, list) or not risks:
        missing_sections.append("risks")
    if not isinstance(mitigations, list) or not mitigations:
        missing_sections.append("mitigations")
    if missing_sections:
        raise RuntimeError(
            f"Strategy sheet generation missing required sections: {', '.join(missing_sections)}"
        )

    for idx, pillar in enumerate(messaging):
        if not isinstance(pillar, dict):
            raise RuntimeError("Strategy sheet messaging pillar must be an object.")
        forbidden_keys = {"targetSegments", "target_segments", "segments", "demographics", "targeting"}
        if forbidden_keys.intersection(pillar.keys()):
            raise RuntimeError(
                f"Strategy sheet messaging pillar {idx} contains demographic/targeting fields, which are not allowed."
            )

    if campaign_channels:
        allowed_channels = {_normalize_token(ch) for ch in campaign_channels}
        normalized_plan: list[str] = []
        for entry in channel_plan:
            if not isinstance(entry, dict):
                raise RuntimeError("Strategy sheet channelPlan entries must be objects.")
            channel_value = entry.get("channel")
            if not isinstance(channel_value, str) or not channel_value.strip():
                raise RuntimeError("Strategy sheet channelPlan entries must include a channel value.")
            normalized_plan.append(_normalize_token(channel_value))
        plan_set = set(normalized_plan)
        missing = allowed_channels - plan_set
        extra = plan_set - allowed_channels
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise RuntimeError(f"Strategy sheet channelPlan missing entries for channels: {missing_list}.")
        if extra:
            extra_list = ", ".join(sorted(extra))
            raise RuntimeError(
                f"Strategy sheet channelPlan includes unsupported channels: {extra_list}. "
                f"Allowed channels: {campaign_channels}."
            )
        if len(normalized_plan) != len(plan_set):
            raise RuntimeError("Strategy sheet channelPlan contains duplicate channels.")
        if len(channel_plan) != len(campaign_channels):
            raise RuntimeError("Strategy sheet channelPlan must include one entry per campaign channel.")
    else:
        allowed_channels = {"facebook", "facebook ads", "meta", "meta ads"}
        if len(channel_plan) != 1:
            raise RuntimeError("Strategy sheet channelPlan must include exactly one entry for Facebook Ads.")
        channel_value = channel_plan[0].get("channel") if isinstance(channel_plan[0], dict) else None
        if not isinstance(channel_value, str) or channel_value.strip().lower() not in allowed_channels:
            raise RuntimeError("Strategy sheet channelPlan must target Facebook Ads only.")

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
    data_out["claudeResponse"] = claude_response.get("raw")

    with session_scope() as session:
        repo = ArtifactsRepository(session)
        repo.insert(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
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
        product_id=product_id,
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
