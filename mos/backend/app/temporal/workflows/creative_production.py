from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Dict, List, Set

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.asset_activities import generate_assets_for_brief_activity
    from app.temporal.activities.qa_activities import run_brand_qa_activity, run_compliance_qa_activity


_CREATIVE_ASSET_GENERATION_RETRY_POLICY = RetryPolicy(maximum_attempts=1)


@dataclass
class CreativeProductionInput:
    org_id: str
    client_id: str
    product_id: str
    campaign_id: str
    asset_brief_ids: List[str]
    swipe_collection_id: str = ""
    swipe_collection_name: str = ""
    swipe_asset_ids: List[str] = field(default_factory=list)
    workflow_run_id: str | None = None


def _raise_invalid_creative_production_input(*missing_fields: str) -> None:
    joined_fields = ", ".join(field_name for field_name in missing_fields if field_name)
    raise ApplicationError(
        "CreativeProductionWorkflow received invalid input: "
        f"missing required field(s): {joined_fields}. "
        "This workflow input is already recorded in Temporal history, so retrying the workflow task "
        "will not populate missing fields.",
        type="InvalidWorkflowInput",
        non_retryable=True,
    )


@workflow.defn
class CreativeProductionWorkflow:
    def __init__(self) -> None:
        self.asset_ids: List[str] = []
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
        missing_fields: list[str] = []
        if not input.asset_brief_ids:
            missing_fields.append("asset_brief_ids")
        if not input.swipe_collection_id:
            missing_fields.append("swipe_collection_id")
        if not input.swipe_collection_name:
            missing_fields.append("swipe_collection_name")
        if not input.swipe_asset_ids:
            missing_fields.append("swipe_asset_ids")
        if missing_fields:
            _raise_invalid_creative_production_input(*missing_fields)

        for brief_id in input.asset_brief_ids:
            result = await workflow.execute_activity(
                generate_assets_for_brief_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "campaign_id": input.campaign_id,
                    "product_id": input.product_id,
                    "asset_brief_id": brief_id,
                    "swipe_collection_id": input.swipe_collection_id,
                    "swipe_collection_name": input.swipe_collection_name,
                    "swipe_asset_ids": list(input.swipe_asset_ids),
                    "workflow_run_id": input.workflow_run_id,
                },
                start_to_close_timeout=timedelta(hours=6),
                retry_policy=_CREATIVE_ASSET_GENERATION_RETRY_POLICY,
            )
            created_ids = result.get("asset_ids") if isinstance(result, dict) else None
            if not isinstance(created_ids, list) or not created_ids:
                raise RuntimeError(f"Asset generation returned no asset_ids for brief {brief_id}.")
            self.asset_ids.extend([str(asset_id) for asset_id in created_ids if asset_id])
            await workflow.execute_activity(
                run_brand_qa_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "campaign_id": input.campaign_id,
                    "asset_brief_id": brief_id,
                    "assets": [{"asset_id": asset_id} for asset_id in created_ids],
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
                    "assets": [{"asset_id": asset_id} for asset_id in created_ids],
                },
                schedule_to_close_timeout=timedelta(minutes=2),
            )

        if not self.asset_ids:
            raise RuntimeError("No assets were generated.")

        await workflow.wait_condition(
            lambda: len(self._approved_asset_ids.union(self._rejected_asset_ids)) >= len(set(self.asset_ids))
        )
