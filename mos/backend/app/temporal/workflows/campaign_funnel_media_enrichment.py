from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.config import settings
    from app.temporal.activities.campaign_intent_activities import enrich_funnel_page_media_activity


@dataclass
class CampaignFunnelMediaEnrichmentInput:
    org_id: str
    actor_user_id: str
    funnel_id: str
    page_id: str
    page_name: str
    prompt: str
    template_id: Optional[str] = None
    idea_workspace_id: Optional[str] = None
    workflow_run_id: Optional[str] = None
    generate_testimonials: bool = False
    experiment_id: Optional[str] = None
    variant_id: Optional[str] = None


@workflow.defn
class CampaignFunnelMediaEnrichmentWorkflow:
    @workflow.run
    async def run(self, input: CampaignFunnelMediaEnrichmentInput) -> Dict[str, Any]:
        result = await workflow.execute_activity(
            enrich_funnel_page_media_activity,
            {
                "org_id": input.org_id,
                "actor_user_id": input.actor_user_id,
                "workflow_run_id": input.workflow_run_id,
                "funnel_id": input.funnel_id,
                "page_id": input.page_id,
                "page_name": input.page_name,
                "template_id": input.template_id,
                "prompt": input.prompt,
                "idea_workspace_id": input.idea_workspace_id,
                "generate_testimonials": bool(input.generate_testimonials),
                "experiment_id": input.experiment_id,
                "variant_id": input.variant_id,
            },
            schedule_to_close_timeout=timedelta(
                minutes=max(1, settings.FUNNEL_MEDIA_ENRICHMENT_ACTIVITY_TIMEOUT_MINUTES)
            ),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=30),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(minutes=5),
                maximum_attempts=max(1, settings.FUNNEL_MEDIA_ENRICHMENT_ACTIVITY_MAX_ATTEMPTS),
            ),
        )
        if not isinstance(result, dict):
            raise RuntimeError("Media enrichment activity returned invalid payload.")
        return result
