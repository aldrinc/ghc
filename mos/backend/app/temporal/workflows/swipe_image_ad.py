from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.swipe_image_ad_activities import generate_swipe_image_ad_activity


_SWIPE_IMAGE_AD_ACTIVITY_RETRY_POLICY = RetryPolicy(maximum_attempts=1)


@dataclass
class SwipeImageAdInput:
    org_id: str
    client_id: str
    product_id: str
    asset_brief_id: str
    campaign_id: Optional[str] = None
    selected_offer_id: Optional[str] = None
    requirement_index: int = 0
    company_swipe_id: Optional[str] = None
    swipe_image_url: Optional[str] = None
    swipe_requires_product_image: Optional[bool] = None
    swipe_context_mode: str = "workspace"
    swipe_brand_name: Optional[str] = None
    swipe_product_name: Optional[str] = None
    swipe_angle: Optional[str] = None
    swipe_hook: Optional[str] = None
    model: Optional[str] = None
    render_model_id: Optional[str] = None
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
            "selected_offer_id": input.selected_offer_id,
            "asset_brief_id": input.asset_brief_id,
            "requirement_index": input.requirement_index,
            "company_swipe_id": input.company_swipe_id,
            "swipe_image_url": input.swipe_image_url,
            "swipe_requires_product_image": input.swipe_requires_product_image,
            "swipe_context_mode": input.swipe_context_mode,
            "swipe_brand_name": input.swipe_brand_name,
            "swipe_product_name": input.swipe_product_name,
            "swipe_angle": input.swipe_angle,
            "swipe_hook": input.swipe_hook,
            "model": input.model,
            "render_model_id": input.render_model_id,
            "max_output_tokens": input.max_output_tokens,
            "aspect_ratio": input.aspect_ratio,
            "count": input.count,
            "workflow_run_id": input.workflow_run_id,
        }

        return await workflow.execute_activity(
            generate_swipe_image_ad_activity,
            params,
            schedule_to_close_timeout=timedelta(minutes=20),
            retry_policy=_SWIPE_IMAGE_AD_ACTIVITY_RETRY_POLICY,
        )
