from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, List, Optional

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.campaign_intent_activities import (
        create_campaign_activity,
    )
    from app.temporal.activities.strategy_activities import build_strategy_sheet_activity
    from app.temporal.activities.experiment_activities import build_experiment_specs_activity


@dataclass
class CampaignIntentInput:
    org_id: str
    client_id: str
    product_id: str
    campaign_name: str
    channels: List[str]
    asset_brief_types: List[str]
    goal_description: Optional[str] = None
    objective_type: Optional[str] = None
    numeric_target: Optional[float] = None
    baseline: Optional[float] = None
    timeframe_days: Optional[int] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None


@workflow.defn
class CampaignIntentWorkflow:
    def __init__(self) -> None:
        self.strategy_sheet: Optional[Dict[str, Any]] = None
        self.experiment_specs: List[Dict[str, Any]] = []
        self._strategy_approved = False
        self._approved_experiment_ids: List[str] = []
        self._rejected_experiment_ids: List[str] = []
        self._approved_asset_brief_ids: List[str] = []
        self._stop_requested = False

    @workflow.signal
    def approve_strategy_sheet(self, payload: Any) -> None:
        approved = payload if isinstance(payload, bool) else bool(payload.get("approved", False))
        updated_strategy_sheet = None
        if isinstance(payload, dict):
            updated_strategy_sheet = payload.get("updated_strategy_sheet") or payload.get("updatedStrategy")
        if approved and updated_strategy_sheet:
            self.strategy_sheet = updated_strategy_sheet
        self._strategy_approved = approved

    @workflow.signal
    def approve_experiments(self, payload: Any) -> None:
        approved_ids: List[str] = []
        rejected_ids: List[str] = []
        edited_specs: Optional[Dict[str, Dict[str, Any]]] = None
        if isinstance(payload, dict):
            approved_ids = payload.get("approved_ids") or payload.get("approvedIds") or []
            rejected_ids = payload.get("rejected_ids") or payload.get("rejectedIds") or []
            edited_specs = payload.get("edited_specs") or payload.get("editedSpecs")
        elif isinstance(payload, list):
            approved_ids = payload
        self._approved_experiment_ids = approved_ids or []
        self._rejected_experiment_ids = rejected_ids or []
        if edited_specs:
            for spec in self.experiment_specs:
                if spec.get("id") in edited_specs:
                    spec.update(edited_specs[spec["id"]])

    @workflow.signal
    def approve_asset_briefs(self, payload: Any) -> None:
        approved_ids: List[str] = []
        if isinstance(payload, dict):
            approved_ids = payload.get("approved_ids") or payload.get("approvedIds") or []
        elif isinstance(payload, list):
            approved_ids = payload
        self._approved_asset_brief_ids = approved_ids or []

    @workflow.signal
    def stop(self, payload: Any) -> None:
        self._stop_requested = True

    @workflow.run
    async def run(self, input: CampaignIntentInput) -> Dict[str, Any]:
        campaign_result = await workflow.execute_activity(
            create_campaign_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "product_id": input.product_id,
                "campaign_name": input.campaign_name,
                "channels": input.channels,
                "asset_brief_types": input.asset_brief_types,
                "goal_description": input.goal_description,
                "objective_type": input.objective_type,
                "numeric_target": input.numeric_target,
                "baseline": input.baseline,
                "timeframe_days": input.timeframe_days,
                "budget_min": input.budget_min,
                "budget_max": input.budget_max,
                "temporal_workflow_id": workflow.info().workflow_id,
                "temporal_run_id": workflow.info().run_id,
            },
            schedule_to_close_timeout=timedelta(minutes=2),
        )
        campaign_id = campaign_result.get("campaign_id")
        if not campaign_id:
            raise RuntimeError("Campaign creation did not return a campaign_id")

        self.strategy_sheet = await workflow.execute_activity(
            build_strategy_sheet_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "product_id": input.product_id,
                "campaign_id": campaign_id,
                "idea_workspace_id": workflow.info().workflow_id,
            },
            schedule_to_close_timeout=timedelta(minutes=5),
        )

        await workflow.wait_condition(lambda: self._strategy_approved)

        specs_result = await workflow.execute_activity(
            build_experiment_specs_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "product_id": input.product_id,
                "campaign_id": campaign_id,
                "idea_workspace_id": workflow.info().workflow_id,
            },
            schedule_to_close_timeout=timedelta(minutes=5),
        )
        self.experiment_specs = specs_result.get("experiment_specs") if isinstance(specs_result, dict) else []

        return {
            "campaign_id": campaign_id,
            "strategy_sheet": self.strategy_sheet,
            "experiment_specs": specs_result,
        }
