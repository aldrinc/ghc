from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.swipe_taxonomy_activities import analyze_swipe_asset_activity


@dataclass
class SwipeTaxonomyInput:
    org_id: str
    swipe_asset_id: str
    model: str | None = None


@workflow.defn
class SwipeTaxonomyWorkflow:
    @workflow.run
    async def run(self, input: SwipeTaxonomyInput) -> dict[str, Any]:
        if not input.org_id:
            raise RuntimeError("org_id is required for swipe taxonomy analysis.")
        if not input.swipe_asset_id:
            raise RuntimeError("swipe_asset_id is required for swipe taxonomy analysis.")

        return await workflow.execute_activity(
            analyze_swipe_asset_activity,
            {
                "org_id": input.org_id,
                "swipe_asset_id": input.swipe_asset_id,
                "model": input.model,
            },
            schedule_to_close_timeout=timedelta(minutes=10),
        )
