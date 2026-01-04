from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, Any, List, Optional, Set

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.experiment_activities import create_asset_briefs_for_experiments_activity
    from app.temporal.activities.asset_activities import generate_assets_for_brief_activity, persist_assets_activity
    from app.temporal.activities.qa_activities import run_brand_qa_activity, run_compliance_qa_activity


@dataclass
class CreativeProductionInput:
    org_id: str
    client_id: str
    campaign_id: str
    experiment_ids: List[str]


@workflow.defn
class CreativeProductionWorkflow:
    def __init__(self) -> None:
        self.asset_brief_ids: List[str] = []
        self._approved_asset_ids: Set[str] = set()
        self._rejected_asset_ids: Set[str] = set()

    @workflow.signal
    def approve_assets(self, payload: Any) -> None:
        approved_ids: List[str] = []
        rejected_ids: List[str] = []
        if isinstance(payload, dict):
            approved_ids = payload.get("approved_ids") or payload.get("approvedIds") or []
            rejected_ids = payload.get("rejected_ids") or payload.get("rejectedIds") or []
        elif isinstance(payload, list):
            approved_ids = payload
        self._approved_asset_ids.update(approved_ids)
        if rejected_ids:
            self._rejected_asset_ids.update(rejected_ids)

    @workflow.run
    async def run(self, input: CreativeProductionInput) -> None:
        idea_workspace_id = workflow.info().workflow_id
        briefs_result = await workflow.execute_activity(
            create_asset_briefs_for_experiments_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "campaign_id": input.campaign_id,
                "experiment_ids": input.experiment_ids,
                "idea_workspace_id": idea_workspace_id,
            },
            schedule_to_close_timeout=timedelta(minutes=5),
        )
        self.asset_brief_ids = briefs_result.get("asset_brief_ids", [])

        for brief_id in self.asset_brief_ids:
            assets = await workflow.execute_activity(
                generate_assets_for_brief_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "campaign_id": input.campaign_id,
                    "asset_brief_id": brief_id,
                },
                schedule_to_close_timeout=timedelta(minutes=5),
            )
            await workflow.execute_activity(
                run_brand_qa_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "campaign_id": input.campaign_id,
                    "asset_brief_id": brief_id,
                    "assets": assets,
                },
                schedule_to_close_timeout=timedelta(minutes=2),
            )
            await workflow.execute_activity(
                run_compliance_qa_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "campaign_id": input.campaign_id,
                    "asset_brief_id": brief_id,
                    "assets": assets,
                },
                schedule_to_close_timeout=timedelta(minutes=2),
            )
            await workflow.execute_activity(
                persist_assets_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "campaign_id": input.campaign_id,
                    "asset_brief_id": brief_id,
                    "assets": assets,
                },
                schedule_to_close_timeout=timedelta(minutes=5),
            )

        await workflow.wait_condition(lambda: len(self._approved_asset_ids) > 0 or len(self._rejected_asset_ids) > 0)
