from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.swipe_animated_template_activities import (
        analyze_animated_template_source_activity,
        render_animated_template_activity,
    )


_ANIMATED_TEMPLATE_ACTIVITY_RETRY_POLICY = RetryPolicy(maximum_attempts=1)


@dataclass
class SwipeAnimatedTemplateAnalysisInput:
    org_id: str
    company_swipe_id: str | None = None
    company_swipe_media_id: str | None = None
    source_url: str | None = None
    source_label: str | None = None
    client_id: str | None = None
    product_id: str | None = None
    campaign_id: str | None = None
    analyzer_version: str | None = None
    idempotency_key: str | None = None
    workflow_run_id: str | None = None


@dataclass
class SwipeAnimatedTemplateRenderInput:
    org_id: str
    manifest_id: str
    run_id: str
    workflow_run_id: str | None = None


@workflow.defn
class SwipeAnimatedTemplateAnalysisWorkflow:
    @workflow.run
    async def run(self, input: SwipeAnimatedTemplateAnalysisInput) -> dict[str, Any]:
        if not input.org_id:
            raise RuntimeError("org_id is required for animated template analysis.")
        if bool(input.company_swipe_id) == bool(input.source_url):
            raise RuntimeError("Provide exactly one of company_swipe_id or source_url.")
        if input.company_swipe_media_id and not input.company_swipe_id:
            raise RuntimeError("company_swipe_media_id requires company_swipe_id.")

        return await workflow.execute_activity(
            analyze_animated_template_source_activity,
            {
                "org_id": input.org_id,
                "company_swipe_id": input.company_swipe_id,
                "company_swipe_media_id": input.company_swipe_media_id,
                "source_url": input.source_url,
                "source_label": input.source_label,
                "client_id": input.client_id,
                "product_id": input.product_id,
                "campaign_id": input.campaign_id,
                "analyzer_version": input.analyzer_version,
                "idempotency_key": input.idempotency_key,
                "workflow_run_id": input.workflow_run_id,
            },
            schedule_to_close_timeout=timedelta(minutes=10),
            retry_policy=_ANIMATED_TEMPLATE_ACTIVITY_RETRY_POLICY,
        )


@workflow.defn
class SwipeAnimatedTemplateRenderWorkflow:
    @workflow.run
    async def run(self, input: SwipeAnimatedTemplateRenderInput) -> dict[str, Any]:
        if not input.org_id:
            raise RuntimeError("org_id is required for animated template rendering.")
        if not input.manifest_id:
            raise RuntimeError("manifest_id is required for animated template rendering.")
        if not input.run_id:
            raise RuntimeError("run_id is required for animated template rendering.")

        return await workflow.execute_activity(
            render_animated_template_activity,
            {
                "org_id": input.org_id,
                "manifest_id": input.manifest_id,
                "run_id": input.run_id,
                "workflow_run_id": input.workflow_run_id,
            },
            schedule_to_close_timeout=timedelta(minutes=20),
            retry_policy=_ANIMATED_TEMPLATE_ACTIVITY_RETRY_POLICY,
        )
