from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, List, Optional

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.strategy_activities import build_strategy_sheet_activity
    from app.temporal.activities.experiment_activities import (
        build_experiment_specs_activity,
        fetch_experiment_specs_activity,
        create_asset_briefs_for_experiments_activity,
    )


@dataclass
class CampaignPlanningInput:
    org_id: str
    client_id: str
    product_id: str
    campaign_id: str
    business_goal_id: Optional[str] = None


@workflow.defn
class CampaignPlanningWorkflow:
    def __init__(self) -> None:
        self.strategy_sheet: Optional[Dict[str, Any]] = None
        self._approved_experiment_ids: List[str] = []
        self._rejected_experiment_ids: List[str] = []

    @workflow.signal
    def approve_experiments(self, payload: Any) -> None:
        approved_ids: List[str] = []
        rejected_ids: List[str] = []
        if isinstance(payload, dict):
            approved_ids = payload.get("approved_ids") or payload.get("approvedIds") or []
            rejected_ids = payload.get("rejected_ids") or payload.get("rejectedIds") or []
        elif isinstance(payload, list):
            approved_ids = payload
        self._approved_experiment_ids = approved_ids or []
        self._rejected_experiment_ids = rejected_ids or []

    @workflow.run
    async def run(self, input: CampaignPlanningInput) -> None:
        idea_workspace_id = workflow.info().workflow_id
        self.strategy_sheet = await workflow.execute_activity(
            build_strategy_sheet_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "product_id": input.product_id,
                "campaign_id": input.campaign_id,
                "business_goal_id": input.business_goal_id,
                "idea_workspace_id": idea_workspace_id,
            },
            schedule_to_close_timeout=timedelta(minutes=5),
        )

        # Auto-approved strategy: immediately move to experiment design.
        specs_result = await workflow.execute_activity(
            build_experiment_specs_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "product_id": input.product_id,
                "campaign_id": input.campaign_id,
                "idea_workspace_id": idea_workspace_id,
            },
            schedule_to_close_timeout=timedelta(minutes=5),
        )

        _ = specs_result

        # Human gate: require explicit experiment approval before generating creative briefs.
        await workflow.wait_condition(
            lambda: len(self._approved_experiment_ids) > 0 or len(self._rejected_experiment_ids) > 0
        )

        if not self._approved_experiment_ids:
            raise RuntimeError("No approved experiments selected; approve at least one experiment to continue.")

        selected_specs = await workflow.execute_activity(
            fetch_experiment_specs_activity,
            {
                "org_id": input.org_id,
                "campaign_id": input.campaign_id,
                "experiment_ids": self._approved_experiment_ids,
            },
            schedule_to_close_timeout=timedelta(minutes=2),
        )
        experiment_specs = selected_specs.get("experiment_specs") if isinstance(selected_specs, dict) else []
        if not experiment_specs:
            raise RuntimeError("No experiment specs matched the approved experiment IDs.")

        await workflow.execute_activity(
            create_asset_briefs_for_experiments_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "product_id": input.product_id,
                "campaign_id": input.campaign_id,
                "experiment_specs": experiment_specs,
                "idea_workspace_id": idea_workspace_id,
            },
            schedule_to_close_timeout=timedelta(minutes=5),
        )
