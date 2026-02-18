from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, List, Optional

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.campaign_intent_activities import create_funnels_from_experiments_activity
    from app.temporal.activities.experiment_activities import (
        fetch_experiment_specs_activity,
        create_asset_briefs_for_experiments_activity,
    )


DEFAULT_FUNNEL_PAGES = [
    {"template_id": "pre-sales-listicle", "name": "Pre-Sales", "slug": "pre-sales"},
    {"template_id": "sales-pdp", "name": "Sales", "slug": "sales"},
]


@dataclass
class CampaignFunnelGenerationInput:
    org_id: str
    client_id: str
    product_id: str
    campaign_id: str
    experiment_ids: List[str]
    funnel_name_prefix: Optional[str] = None
    generate_testimonials: bool = False


@workflow.defn
class CampaignFunnelGenerationWorkflow:
    @workflow.run
    async def run(self, input: CampaignFunnelGenerationInput) -> Dict[str, Any]:
        if not input.experiment_ids:
            raise RuntimeError("experiment_ids are required to generate funnels.")

        specs_result = await workflow.execute_activity(
            fetch_experiment_specs_activity,
            {
                "org_id": input.org_id,
                "campaign_id": input.campaign_id,
                "experiment_ids": input.experiment_ids,
            },
            schedule_to_close_timeout=timedelta(minutes=2),
        )
        experiment_specs = specs_result.get("experiment_specs") if isinstance(specs_result, dict) else []
        if not experiment_specs:
            raise RuntimeError("No experiment specs available for funnel generation.")

        # This activity generates N funnels (each with multiple pages, images, and optionally testimonials).
        # The runtime scales with the number of variants, so size the timeout accordingly.
        funnel_count = 0
        for exp in experiment_specs:
            if not isinstance(exp, dict):
                continue
            variants = exp.get("variants") or []
            if isinstance(variants, list):
                funnel_count += len(variants)
        funnel_count = max(1, funnel_count)
        funnel_batch_timeout = max(timedelta(minutes=45), timedelta(minutes=15) * funnel_count)

        funnel_batch = await workflow.execute_activity(
            create_funnels_from_experiments_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "product_id": input.product_id,
                "campaign_id": input.campaign_id,
                "experiment_specs": experiment_specs,
                "pages": DEFAULT_FUNNEL_PAGES,
                "funnel_name_prefix": input.funnel_name_prefix or "Funnel",
                "idea_workspace_id": workflow.info().workflow_id,
                "actor_user_id": "workflow",
                "generate_ai_drafts": True,
                "generate_testimonials": bool(input.generate_testimonials),
                "temporal_workflow_id": workflow.info().workflow_id,
                "temporal_run_id": workflow.info().run_id,
            },
            schedule_to_close_timeout=funnel_batch_timeout,
        )

        funnel_map: Dict[str, str] = {}
        if isinstance(funnel_batch, dict):
            batch_items = funnel_batch.get("funnels") or []
            if isinstance(batch_items, list):
                for item in batch_items:
                    if not isinstance(item, dict):
                        continue
                    funnel_payload = item.get("funnel")
                    if not isinstance(funnel_payload, dict):
                        continue
                    funnel_id = funnel_payload.get("funnel_id")
                    experiment_id = item.get("experiment_id")
                    variant_id = item.get("variant_id")
                    if funnel_id and experiment_id and variant_id:
                        funnel_map[f"{experiment_id}:{variant_id}"] = funnel_id

        briefs_result = await workflow.execute_activity(
            create_asset_briefs_for_experiments_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "product_id": input.product_id,
                "campaign_id": input.campaign_id,
                "experiment_specs": experiment_specs,
                "idea_workspace_id": workflow.info().workflow_id,
                "funnel_map": funnel_map,
            },
            schedule_to_close_timeout=timedelta(minutes=5),
        )

        return {
            "campaign_id": input.campaign_id,
            "funnels": funnel_batch,
            "asset_briefs": briefs_result,
        }
