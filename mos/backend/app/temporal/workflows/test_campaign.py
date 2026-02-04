from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.client_onboarding_activities import build_client_canon_activity, build_metric_schema_activity
    from app.temporal.activities.strategy_activities import build_strategy_sheet_activity
    from app.temporal.activities.experiment_activities import build_experiment_specs_activity, create_asset_briefs_for_experiments_activity
    from app.temporal.activities.asset_activities import generate_assets_for_brief_activity
    from app.temporal.activities.qa_activities import run_brand_qa_activity, run_compliance_qa_activity


@dataclass
class TestCampaignInput:
    org_id: str
    client_id: str
    product_id: str
    onboarding_payload_id: str
    business_goal_id: str


@workflow.defn
class TestCampaignWorkflow:
    @workflow.run
    async def run(self, input: TestCampaignInput) -> Dict[str, Any]:
        idea_workspace_id = workflow.info().workflow_id
        canon = await workflow.execute_activity(
            build_client_canon_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "product_id": input.product_id,
                "onboarding_payload_id": input.onboarding_payload_id,
            },
            schedule_to_close_timeout=timedelta(minutes=5),
        )

        metric = await workflow.execute_activity(
            build_metric_schema_activity,
            {"org_id": input.org_id, "client_id": input.client_id, "product_id": input.product_id},
            schedule_to_close_timeout=timedelta(minutes=5),
        )

        strategy = await workflow.execute_activity(
            build_strategy_sheet_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "product_id": input.product_id,
                "campaign_id": None,
                "business_goal_id": input.business_goal_id,
                "idea_workspace_id": idea_workspace_id,
            },
            schedule_to_close_timeout=timedelta(minutes=5),
        )

        experiments = await workflow.execute_activity(
            build_experiment_specs_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "product_id": input.product_id,
                "campaign_id": None,
                "idea_workspace_id": idea_workspace_id,
            },
            schedule_to_close_timeout=timedelta(minutes=5),
        )

        briefs = await workflow.execute_activity(
            create_asset_briefs_for_experiments_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "product_id": input.product_id,
                "campaign_id": None,
                "experiment_specs": experiments.get("experiment_specs", []),
                "idea_workspace_id": idea_workspace_id,
            },
            schedule_to_close_timeout=timedelta(minutes=5),
        )
        brief_id = briefs.get("asset_brief_ids", [None])[0]

        assets = await workflow.execute_activity(
            generate_assets_for_brief_activity,
            {"org_id": input.org_id, "client_id": input.client_id, "campaign_id": None, "asset_brief_id": brief_id},
            schedule_to_close_timeout=timedelta(minutes=5),
        )

        brand_qa = await workflow.execute_activity(
            run_brand_qa_activity,
            {"org_id": input.org_id, "client_id": input.client_id, "campaign_id": None, "asset_brief_id": brief_id, "assets": assets},
            schedule_to_close_timeout=timedelta(minutes=2),
        )
        compliance_qa = await workflow.execute_activity(
            run_compliance_qa_activity,
            {"org_id": input.org_id, "client_id": input.client_id, "campaign_id": None, "asset_brief_id": brief_id, "assets": assets},
            schedule_to_close_timeout=timedelta(minutes=2),
        )

        return {
            "canon": canon,
            "metric_schema": metric,
            "strategy_sheet": strategy,
            "experiment_specs": experiments.get("experiment_specs", []),
            "asset_brief_id": brief_id,
            "assets": assets,
            "brand_qa": brand_qa,
            "compliance_qa": compliance_qa,
        }
