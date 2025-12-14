from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, Optional

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.strategy_activities import build_strategy_sheet_activity
    from app.temporal.activities.experiment_activities import (
        build_experiment_specs_activity,
        create_asset_briefs_for_experiments_activity,
    )


@dataclass
class CampaignPlanningInput:
    org_id: str
    client_id: str
    campaign_id: str
    business_goal_id: Optional[str] = None


@workflow.defn
class CampaignPlanningWorkflow:
    def __init__(self) -> None:
        self.strategy_sheet: Optional[Dict[str, Any]] = None
        self._approved = False

    @workflow.signal
    def approve_strategy_sheet(self, payload: Any) -> None:
        approved = payload if isinstance(payload, bool) else bool(payload.get("approved", False))
        updated_strategy_sheet = None
        if isinstance(payload, dict):
            updated_strategy_sheet = payload.get("updated_strategy_sheet") or payload.get("updatedStrategy")
        if approved and updated_strategy_sheet:
            self.strategy_sheet = updated_strategy_sheet
        self._approved = approved

    @workflow.run
    async def run(self, input: CampaignPlanningInput) -> None:
        self.strategy_sheet = await workflow.execute_activity(
            build_strategy_sheet_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "campaign_id": input.campaign_id,
                "business_goal_id": input.business_goal_id,
            },
            schedule_to_close_timeout=timedelta(minutes=5),
        )

        await workflow.wait_condition(lambda: self._approved)

        # After approval, generate experiment specs and asset briefs.
        specs_result = await workflow.execute_activity(
            build_experiment_specs_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "campaign_id": input.campaign_id,
            },
            schedule_to_close_timeout=timedelta(minutes=5),
        )

        experiment_specs = specs_result.get("experiment_specs") if isinstance(specs_result, dict) else []
        await workflow.execute_activity(
            create_asset_briefs_for_experiments_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "campaign_id": input.campaign_id,
                "experiment_specs": experiment_specs,
            },
            schedule_to_close_timeout=timedelta(minutes=5),
        )
