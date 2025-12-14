from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional
from uuid import uuid4

from temporalio import activity

from app.db.enums import ArtifactTypeEnum
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.base import SessionLocal
from app.schemas.experiment_spec import ExperimentSpecSet
from app.schemas.asset_brief import AssetBrief
from app.llm import LLMClient, LLMGenerationParams


DEFAULT_LLM_MODEL = os.getenv("LLM_DEFAULT_MODEL", "gpt-5.2-2025-12-11")


def _repo() -> ArtifactsRepository:
    return ArtifactsRepository(SessionLocal())


def _parse_json(text: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(text)
    except Exception:
        return None


def _load_strategy(repo: ArtifactsRepository, org_id: str, campaign_id: str) -> Dict[str, Any]:
    artifact = repo.get_latest_by_type_for_campaign(
        org_id=org_id, campaign_id=campaign_id, artifact_type=ArtifactTypeEnum.strategy_sheet
    )
    return artifact.data if artifact else {}


def _load_metric(repo: ArtifactsRepository, org_id: str, client_id: str) -> Dict[str, Any]:
    artifact = repo.get_latest_by_type(org_id=org_id, client_id=client_id, artifact_type=ArtifactTypeEnum.metric_schema)
    return artifact.data if artifact else {}


def _build_experiment_prompt(strategy: Dict[str, Any], metric: Dict[str, Any]) -> str:
    goal = strategy.get("goal") or strategy.get("objective", {}).get("description")
    hypothesis = strategy.get("hypothesis") or strategy.get("objective", {}).get("description")
    messaging = strategy.get("messaging") or strategy.get("positioning", {}).get("key_messages") or []
    channel_plan = strategy.get("channelPlan") or strategy.get("channel_roles") or []
    kpis = metric.get("kpis") or metric.get("metrics") or []
    return f"""
You are a media & experiment architect. Propose 2-3 experiments.
Context:
- Goal: {goal}
- Hypothesis: {hypothesis}
- Messaging/key messages: {messaging}
- Channel plan: {channel_plan}
- KPIs: {kpis}

Return JSON:
{{
  "experiments": [
    {{
      "id": "exp_meta_hooks",
      "name": "short name",
      "hypothesis": "text",
      "metricIds": ["metric_ctr", "metric_cvr"],
      "variants": [
        {{"id": "v1", "name": "Variant 1", "description": "what changes", "channels": ["paid_social"]}},
        {{"id": "v2", "name": "Variant 2", "description": "what changes", "channels": ["paid_social"]}}
      ],
      "sampleSizeEstimate": 1000,
      "durationDays": 14,
      "budgetEstimate": 5000
    }}
  ]
}}
Use compact JSON. Keep strings under 200 chars.
"""


@activity.defn
def build_experiment_specs_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    client_id = params["client_id"]
    campaign_id = params.get("campaign_id")
    repo = _repo()

    strategy = _load_strategy(repo, org_id, campaign_id) if campaign_id else {}
    metric = _load_metric(repo, org_id, client_id)

    llm = LLMClient()
    prompt = _build_experiment_prompt(strategy, metric)
    raw = llm.generate_text(prompt, LLMGenerationParams(model=DEFAULT_LLM_MODEL))
    parsed = _parse_json(raw) or {}
    experiments = parsed.get("experiments") if isinstance(parsed, dict) else None

    # Fallback if LLM parsing fails
    if not experiments:
        experiments = [
            {
                "id": "exp_top_hooks",
                "name": "Top-of-funnel hooks",
                "hypothesis": "Story-led hook will beat feature-led on CTR and CVR.",
                "metricIds": ["metric_ctr", "metric_cvr"],
                "variants": [
                    {"id": "v1_story", "name": "Story-led", "description": "Narrative opener", "channels": ["paid_social"]},
                    {"id": "v2_feature", "name": "Feature-led", "description": "Benefit-first", "channels": ["paid_social"]},
                ],
                "sampleSizeEstimate": 1000,
                "durationDays": 14,
                "budgetEstimate": 5000,
            }
        ]

    specs = ExperimentSpecSet(
        clientId=client_id,
        campaignId=campaign_id,
        experimentSpecs=experiments,  # type: ignore[arg-type]
    )
    data_out = specs.model_dump()
    data_out["rawPrompt"] = prompt
    repo.insert(
        org_id=org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        artifact_type=ArtifactTypeEnum.experiment_spec,
        data=data_out,
    )
    return {"experiment_specs": experiments}


@activity.defn
def create_asset_briefs_for_experiments_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    client_id = params["client_id"]
    campaign_id = params.get("campaign_id")
    org_id = params["org_id"]
    experiments = params.get("experiment_specs") or []
    repo = _repo()
    canon = repo.get_latest_by_type(org_id=org_id, client_id=client_id, artifact_type=ArtifactTypeEnum.client_canon)
    tone_guidelines = []
    constraints = []
    if canon and isinstance(canon.data, dict):
        tone = canon.data.get("brand", {}).get("toneOfVoice") or canon.data.get("tone_of_voice")
        if tone:
            tone_guidelines = (tone.get("do") or []) + (tone.get("dont") or [])
        cons = canon.data.get("constraints") or {}
        constraints = cons.get("brand") or cons.get("legal") or []

    briefs: List[AssetBrief] = []
    brief_ids: List[str] = []
    for exp in experiments:
        exp_id = exp.get("id") or str(uuid4())
        variants = exp.get("variants") or []
        for var in variants:
            var_id = var.get("id") or str(uuid4())
            channels = var.get("channels") or ["paid_social"]
            brief_id = f"{exp_id}-{var_id}-brief"
            reqs = [
                {
                    "channel": ch,
                    "format": "video_30s" if ch == "paid_social" else "single_image",
                    "angle": var.get("name"),
                    "hook": var.get("description"),
                }
                for ch in channels
            ]
            brief = AssetBrief(
                id=brief_id,
                clientId=client_id,
                campaignId=campaign_id,
                experimentId=exp_id,
                creativeConcept=var.get("description"),
                requirements=reqs,  # type: ignore[arg-type]
                constraints=constraints,
                toneGuidelines=tone_guidelines,
            )
            briefs.append(brief)
            brief_ids.append(brief_id)

    data_out = [b.model_dump() for b in briefs]
    if data_out:
        repo.insert(
            org_id=org_id,
            client_id=client_id,
            campaign_id=campaign_id,
            artifact_type=ArtifactTypeEnum.asset_brief,
            data={"asset_briefs": data_out},
        )

    return {"asset_brief_ids": brief_ids, "briefs": data_out}
