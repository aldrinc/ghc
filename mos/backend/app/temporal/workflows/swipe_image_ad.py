from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, Optional

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.swipe_image_ad_activities import generate_swipe_image_ad_activity


@dataclass
class SwipeImageAdInput:
    org_id: str
    client_id: str
    product_id: str
    asset_brief_id: str
    campaign_id: Optional[str] = None
    requirement_index: int = 0
    company_swipe_id: Optional[str] = None
    swipe_image_url: Optional[str] = None
    model: Optional[str] = None
    max_output_tokens: Optional[int] = None
    aspect_ratio: str = "1:1"
    count: int = 1
    workflow_run_id: Optional[str] = None


@workflow.defn
class SwipeImageAdWorkflow:
    @workflow.run
    async def run(self, input: SwipeImageAdInput) -> Dict[str, Any]:
        if not input.asset_brief_id:
            raise RuntimeError("asset_brief_id is required to generate swipe image ad assets.")
        if not input.product_id:
            raise RuntimeError("product_id is required to generate swipe image ad assets.")

        params: Dict[str, Any] = {
            "org_id": input.org_id,
            "client_id": input.client_id,
            "product_id": input.product_id,
            "campaign_id": input.campaign_id,
            "asset_brief_id": input.asset_brief_id,
            "requirement_index": input.requirement_index,
            "company_swipe_id": input.company_swipe_id,
            "swipe_image_url": input.swipe_image_url,
            "model": input.model,
            "max_output_tokens": input.max_output_tokens,
            "aspect_ratio": input.aspect_ratio,
            "count": input.count,
            "workflow_run_id": input.workflow_run_id,
        }

        return await workflow.execute_activity(
            generate_swipe_image_ad_activity,
            params,
            schedule_to_close_timeout=timedelta(minutes=20),
        )

